from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.import_service import ImportService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.dialogs.product_editor import ProductEditor
from cbpos.ui.widgets.pagination_widget import PaginationWidget
from cbpos.ui.widgets.table_helpers import configure_table_columns


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
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
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


class InventoryView(QWidget):
    """Paginated, searchable product table with add/import/category/unit/label actions."""

    def __init__(self):
        """Build the UI and load the first page of products."""
        super().__init__()
        self.inventory_service = InventoryService()
        self.import_service = ImportService()
        self._filtered_products: list = []
        self.init_ui()
        self.load_data()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def init_ui(self):
        """Build the toolbar, product table, empty-state placeholder, and pagination."""
        layout = QVBoxLayout(self)

        from cbpos.ui.resources.icons import Icons
        from cbpos.ui.widgets.page_header import PageHeader

        self._page_header = PageHeader(icon_name=Icons.INVENTORY)
        layout.addWidget(self._page_header)

        # Top Bar
        top_bar = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.textChanged.connect(self.filter_data)

        self.add_btn = QPushButton()
        self.add_btn.clicked.connect(self.open_add_dialog)

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

        # Context Menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_context_menu)

        # Empty state placeholder
        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: gray; font-size: 14px;")

        self.table_stack = QStackedWidget()
        self.table_stack.addWidget(self.table)  # index 0
        self.table_stack.addWidget(self.empty_label)  # index 1

        layout.addWidget(self.table_stack)

        # Pagination
        self.pagination = PaginationWidget()
        self.pagination.page_changed.connect(self._on_page_changed)
        layout.addWidget(self.pagination)

    def retranslate_ui(self) -> None:
        """Update all widget text from the translation system."""
        self._page_header.set_title(_t("management.sidebar_inventory"))
        self.search_input.setPlaceholderText(_t("inventory.search_placeholder"))
        self.add_btn.setText(_t("inventory.btn_add_product"))
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

    def _update_empty_state(self) -> None:
        """Show empty state label when model has no rows."""
        if self.model.rowCount() == 0:
            self.table_stack.setCurrentIndex(1)
        else:
            self.table_stack.setCurrentIndex(0)

    def load_data(self):
        """Load all products and display the current page."""
        self.all_products = self.inventory_service.get_all_products()
        self._filtered_products = self.all_products
        self._apply_pagination()

    def filter_data(self, text):
        """Filter products by barcode or name, or show all if text is empty."""
        if not text:
            self._filtered_products = self.all_products
        else:
            text = text.lower()
            self._filtered_products = [
                p for p in self.all_products if text in p.barcode.lower() or text in p.name_en.lower()
            ]
        self._apply_pagination()

    def _apply_pagination(self) -> None:
        self.pagination.set_total(len(self._filtered_products))
        page_items = self.pagination.get_page_slice(self._filtered_products)
        self.model.update_data(page_items)
        self._update_empty_state()

    def _on_page_changed(self, _page: int) -> None:
        page_items = self.pagination.get_page_slice(self._filtered_products)
        self.model.update_data(page_items)
        self._update_empty_state()

    def open_add_dialog(self):
        """Open the product editor to create a new product, if permitted."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.INVENTORY_EDIT, self):
            return

        dialog = ProductEditor(parent=self)
        if dialog.exec():
            self.load_data()

    def open_edit_dialog(self, index):
        """Open the product editor for the double-clicked row, if permitted."""
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
        from cbpos.ui.dialogs.category_manager import CategoryManagerDialog

        dialog = CategoryManagerDialog(parent=self)
        dialog.exec()
        self.load_data()

    def open_unit_manager(self):
        """Open the unit manager dialog."""
        from cbpos.ui.dialogs.unit_manager import UnitManagerDialog

        dialog = UnitManagerDialog(parent=self)
        dialog.exec()

    def open_label_print(self):
        """Open the label printing dialog."""
        from cbpos.ui.dialogs.label_print_dialog import LabelPrintDialog

        dialog = LabelPrintDialog(parent=self)
        dialog.exec()

    def open_context_menu(self, position):
        """Show the right-click context menu with a stock history action."""
        from PyQt6.QtWidgets import QMenu

        from cbpos.ui.dialogs.stock_history_dialog import StockHistoryDialog

        index = self.table.indexAt(position)
        if not index.isValid():
            return

        menu = QMenu()
        history_action = menu.addAction(_t("inventory.context_stock_history"))

        action = menu.exec(self.table.viewport().mapToGlobal(position))

        if action == history_action:
            product = self.model.products[index.row()]
            dialog = StockHistoryDialog(product, parent=self)
            dialog.exec()

    def import_csv(self) -> None:
        """Open the CSV import dialog and reload products afterward."""
        from cbpos.ui.dialogs.csv_import_dialog import CsvImportDialog

        dialog = CsvImportDialog(self.import_service, parent=self)
        if dialog.exec():
            self.load_data()
