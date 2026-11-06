from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.import_service import ImportService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.utils.terminal_guard import catalog_is_read_only
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.components.activation import Activatable
from cbpos.ui.dialogs.product_editor import ProductEditor
from cbpos.ui.dialogs.stock_adjustment_dialog import StockAdjustmentDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.empty_state_widget import EmptyStateWidget
from cbpos.ui.widgets.loading_overlay import LoadingOverlay
from cbpos.ui.widgets.pagination_widget import PaginationWidget
from cbpos.ui.widgets.read_only_banner import ReadOnlyBanner
from cbpos.ui.widgets.table_helpers import NUMERIC_ALIGNMENT, batch_table_update, configure_table_columns


class InventoryModel(QAbstractTableModel):
    """Table model backing the inventory table: barcode, name, category, price, stock, unit."""

    def __init__(self, products=None):
        """Store the initial page of products to display."""
        super().__init__()
        self.products = products or []
        self.headers = ["", "", "", "", "", ""]

    def rowCount(self, parent=QModelIndex()):
        """Return the number of products currently loaded."""
        return len(self.products)

    def columnCount(self, parent=QModelIndex()):
        """Return the number of columns (matches `headers`)."""
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return the display text for a cell, or a background tint for low-stock rows."""
        if not index.isValid():
            return None

        product = self.products[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return product.barcode
            elif col == 1:
                return product.name_en
            elif col == 2:
                return product.category.name if product.category else "-"
            elif col == 3:
                return f"{product.price:.2f}"
            elif col == 4:
                return f"{product.stock_qty:.3f}"
            elif col == 5:
                if product.unit:
                    return product.unit.abbreviation
                return "kg" if product.is_weighted else "pcs"

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (3, 4):  # Price, Stock
                return NUMERIC_ALIGNMENT

        elif role == Qt.ItemDataRole.BackgroundRole:
            # Low stock warning - theme-aware colors via QSS alternate rows
            if product.stock_qty <= product.reorder_point:
                from cbpos.core.services.theme_service import ThemeService

                if ThemeService.current_theme.lower() == "light":
                    return QBrush(QColor(254, 226, 226))  # Very light red for light theme
                else:
                    return QBrush(QColor(60, 30, 30))  # Dark red tint for dark theme

        return None

    def headerData(self, section, orientation, role):
        """Return the translated column header text."""
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return self.headers[section]
            if role == Qt.ItemDataRole.TextAlignmentRole and section in (3, 4):
                return NUMERIC_ALIGNMENT
        return None

    def update_data(self, products):
        """Replace the displayed products and reset the model."""
        self.beginResetModel()
        self.products = products
        self.endResetModel()

    def update_headers(self, headers: list[str]) -> None:
        """Update header labels and notify views."""
        self.headers = headers
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(headers) - 1)


class InventoryView(QWidget, Activatable):
    """Paginated, searchable product table with add/import/category/unit/label actions."""

    def __init__(self):
        """Build the UI and load the first page of products."""
        super().__init__()
        self.inventory_service = InventoryService()
        self.import_service = ImportService()
        self.all_products: list = []
        self._filtered_products: list = []
        self._search_query: str = ""
        self.init_ui()
        self.load_data()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def init_ui(self):
        """Build the toolbar, product table, empty-state placeholder, and pagination."""
        layout = QVBoxLayout(self)

        self.read_only_banner = ReadOnlyBanner()
        layout.addWidget(self.read_only_banner)

        # Top Bar
        top_bar = QHBoxLayout()

        self.search_input = QLineEdit()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._do_debounced_search)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._do_immediate_search)

        self.add_btn = QPushButton()
        self.add_btn.setProperty("class", "primary")
        self.add_btn.clicked.connect(self.open_add_dialog)

        self.adjust_btn = QPushButton()
        self.adjust_btn.setObjectName("BtnAdjustStock")
        self.adjust_btn.clicked.connect(self.open_stock_adjustment)

        self.import_btn = QPushButton()
        self.import_btn.clicked.connect(self.import_csv)

        self.cat_btn = QPushButton()
        self.cat_btn.clicked.connect(self.open_category_dialog)

        self.unit_btn = QPushButton()
        self.unit_btn.clicked.connect(self.open_unit_manager)

        self.label_btn = QPushButton()
        self.label_btn.clicked.connect(self.open_label_print)

        top_bar.addWidget(self.search_input)
        top_bar.addWidget(self.add_btn)
        top_bar.addWidget(self.adjust_btn)
        top_bar.addWidget(self.import_btn)
        top_bar.addWidget(self.cat_btn)
        top_bar.addWidget(self.unit_btn)
        top_bar.addWidget(self.label_btn)

        layout.addLayout(top_bar)

        # Table
        self.table = QTableView()
        self.model = InventoryModel()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # Barcode
                1: QHeaderView.ResizeMode.Stretch,  # Name - needs the room
                2: QHeaderView.ResizeMode.ResizeToContents,  # Category
                3: QHeaderView.ResizeMode.ResizeToContents,  # Price
                4: QHeaderView.ResizeMode.ResizeToContents,  # Stock
                5: QHeaderView.ResizeMode.ResizeToContents,  # Unit
            },
        )
        self.table.doubleClicked.connect(self.open_edit_dialog)

        # Keyboard shortcuts
        self.shortcut_adjust = QShortcut(QKeySequence("Ctrl+J"), self)
        self.shortcut_adjust.activated.connect(self.open_stock_adjustment)

        # Context Menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_context_menu)

        # Empty state placeholder
        self.empty_label = EmptyStateWidget(Icons.INVENTORY)
        self.empty_label.setObjectName("EmptyStateLabel")

        self.table_stack = QStackedWidget()
        self.table_stack.addWidget(self.table)  # index 0
        self.table_stack.addWidget(self.empty_label)  # index 1

        layout.addWidget(self.table_stack)

        # Pagination
        self.pagination = PaginationWidget(page_size=100)
        self.pagination.set_info_formatter(
            lambda first, last, total: _t("inventory.page_info", first=first, last=last, total=total)
        )
        self.pagination.page_changed.connect(self._on_page_changed)
        layout.addWidget(self.pagination)

        self.loading_overlay = LoadingOverlay(self.table)

    def _update_read_only_state(self) -> None:
        """Update action buttons and tooltip based on terminal catalog read-only state."""
        is_ro = self.read_only_banner.refresh_visibility()
        self.add_btn.setEnabled(not is_ro)
        self.adjust_btn.setEnabled(not is_ro)
        self.import_btn.setEnabled(not is_ro)
        self.cat_btn.setEnabled(not is_ro)
        self.unit_btn.setEnabled(not is_ro)
        tip = _t("catalog.read_only_tooltip") if is_ro else ""
        self.add_btn.setToolTip(tip)
        self.adjust_btn.setToolTip(tip)
        self.import_btn.setToolTip(tip)
        self.cat_btn.setToolTip(tip)
        self.unit_btn.setToolTip(tip)

    def retranslate_ui(self) -> None:
        """Update all widget text from the translation system."""
        self.read_only_banner.retranslate_ui()
        self._update_read_only_state()
        self.search_input.setPlaceholderText(_t("inventory.search_placeholder"))
        self.add_btn.setText(_t("inventory.btn_add_product"))
        self.adjust_btn.setText(_t("inventory.btn_adjust_stock"))
        self.import_btn.setText(_t("inventory.btn_import_csv"))
        self.cat_btn.setText(_t("inventory.btn_manage_categories"))
        self.unit_btn.setText(_t("inventory.btn_units"))
        self.label_btn.setText(_t("inventory.btn_print_labels"))
        self.empty_label.setText(_t("inventory.empty_state"))
        self.model.update_headers(
            [
                _t("inventory.header_barcode"),
                _t("inventory.header_name"),
                _t("inventory.header_category"),
                _t("inventory.header_price"),
                _t("inventory.header_stock"),
                _t("inventory.header_unit"),
            ]
        )

    def _on_search_text_changed(self, text: str) -> None:
        self._search_query = text
        self._search_timer.start(300)

    def _do_immediate_search(self) -> None:
        self._search_timer.stop()
        self._do_debounced_search()

    def _do_debounced_search(self) -> None:
        self._load_page(page=0)

    def load_data(self):
        """Load all products and display the current page."""
        self._load_page(page=self.pagination.current_page)

    def filter_data(self, text: str):
        """Filter products by barcode or name with server-side search."""
        self._search_query = text
        self._load_page(page=0)

    def _load_page(self, page: int = 0) -> None:
        """Fetch the requested page of products from the service."""
        query = (self._search_query or "").strip()
        self.loading_overlay.show_loading()
        try:
            items, total_count = self.inventory_service.list_products(
                query=query if query else None,
                page=page,
                page_size=self.pagination.page_size,
            )
            self.all_products = items
            self._filtered_products = items
            with batch_table_update(self.table):
                self.model.update_data(items)
            self.pagination.set_total(total_count, reset_page=(page == 0))
            self._update_empty_state(total_count=total_count, query=query)
        finally:
            self.loading_overlay.hide_loading()

    def _on_page_changed(self, page: int) -> None:
        self._load_page(page=page)

    def _update_empty_state(self, total_count: int | None = None, query: str = "") -> None:
        """Show empty state label when model has no rows."""
        count = self.model.rowCount() if total_count is None else total_count
        if count == 0:
            if query:
                self.empty_label.setText(_t("inventory.no_match", query=query))
            else:
                self.empty_label.setText(_t("inventory.empty_state"))
            self.table_stack.setCurrentIndex(1)
        else:
            self.table_stack.setCurrentIndex(0)

    def open_add_dialog(self):
        """Open the product editor to create a new product, if permitted."""
        if catalog_is_read_only():
            return

        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.INVENTORY_EDIT, self):
            return

        dialog = ProductEditor(parent=self)
        if dialog.exec():
            self.load_data()

    def open_edit_dialog(self, index):
        """Open the product editor for the double-clicked row, if permitted."""
        if catalog_is_read_only():
            return

        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.INVENTORY_EDIT, self):
            return

        product = self.model.products[index.row()]
        dialog = ProductEditor(product=product, parent=self)
        if dialog.exec():
            self.load_data()

    def open_category_dialog(self):
        """Open the category manager and reload products afterward."""
        if catalog_is_read_only():
            return

        from cbpos.ui.dialogs.category_manager import CategoryManagerDialog

        dialog = CategoryManagerDialog(parent=self)
        dialog.exec()
        self.load_data()

    def open_unit_manager(self):
        """Open the unit manager dialog."""
        if catalog_is_read_only():
            return

        from cbpos.ui.dialogs.unit_manager import UnitManagerDialog

        dialog = UnitManagerDialog(parent=self)
        dialog.exec()

    def open_label_print(self):
        """Open the label printing dialog."""
        from cbpos.ui.dialogs.label_print_dialog import LabelPrintDialog

        dialog = LabelPrintDialog(parent=self)
        dialog.exec()

    def open_context_menu(self, position):
        """Show the right-click context menu with stock adjustment and history actions."""
        from PyQt6.QtWidgets import QMenu

        from cbpos.ui.dialogs.stock_history_dialog import StockHistoryDialog

        index = self.table.indexAt(position)
        if not index.isValid():
            return

        menu = QMenu()
        adjust_action = menu.addAction(_t("inventory.context_adjust_stock"))
        history_action = menu.addAction(_t("inventory.context_stock_history"))

        action = menu.exec(self.table.viewport().mapToGlobal(position))

        if action == adjust_action:
            self._open_adjustment_for_row(index.row())
        elif action == history_action:
            product = self.model.products[index.row()]
            dialog = StockHistoryDialog(product, parent=self)
            dialog.exec()

    def open_stock_adjustment(self):
        """Open stock adjustment dialog for the currently selected product row."""
        if catalog_is_read_only():
            return

        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return
        self._open_adjustment_for_row(indexes[0].row())

    def _open_adjustment_for_row(self, row: int):
        """Open stock adjustment dialog for product at `row`."""
        if catalog_is_read_only():
            return

        if row < 0 or row >= len(self.model.products):
            return

        product = self.model.products[row]
        if getattr(product, "is_service", False):
            QMessageBox.information(self, _t("common.notice"), _t("inventory.service_item_no_stock"))
            return

        dialog = StockAdjustmentDialog(product, inventory_service=self.inventory_service, parent=self)
        if dialog.exec():
            self.load_data()

    def import_csv(self) -> None:
        """Open the CSV import dialog and reload products afterward."""
        if catalog_is_read_only():
            return

        from cbpos.ui.dialogs.csv_import_dialog import CsvImportDialog

        dialog = CsvImportDialog(self.import_service, parent=self)
        if dialog.exec():
            self.load_data()

    def on_activated(self) -> None:
        """Reload when this view is shown again, so the user never sees stale data."""
        self._update_read_only_state()
        self.load_data()
