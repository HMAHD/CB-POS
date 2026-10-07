"""Stock Take view for physical inventory counting and variance workflow."""

import logging
import weakref
from datetime import datetime
from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import QAbstractTableModel, QDate, QEvent, QModelIndex, QRegularExpression, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.constants.status import DocumentStatus, Precision
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.stock_count_service import StockCountService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.infrastructure.hardware.scanner import BarcodeScanner
from cbpos.ui.widgets.table_helpers import configure_table_columns

logger = logging.getLogger(__name__)


class StockCountItemModel(QAbstractTableModel):
    """Table model for stock count items with editable Counted column."""

    COL_COUNTED = 3
    # Six integer digits: far above any real shelf count, far below a
    # barcode, so a scan typed into the cell can't pass as a quantity (#547).
    MAX_COUNTED = Decimal("999999.999")

    def __init__(self, items=None):
        """Initialize the model with the given stock count items."""
        super().__init__()
        self.items = items or []
        self._headers = [
            _t("stock_take.col_barcode"),
            _t("stock_take.col_product"),
            _t("stock_take.col_expected"),
            _t("stock_take.col_counted"),
            _t("stock_take.col_variance"),
            _t("stock_take.col_value"),
        ]

    def update_headers(self, headers: list[str]) -> None:
        """Update column headers and refresh the header view."""
        self._headers = headers
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(headers) - 1)

    def rowCount(self, parent=None):
        """Return the number of stock count item rows."""
        return len(self.items)

    def columnCount(self, parent=None):
        """Return the number of columns."""
        return len(self._headers)

    def data(self, index, role):
        """Return display text, color, alignment, or edit value for a cell."""
        if not index.isValid():
            return None
        item = self.items[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return item.product.barcode if item.product else ""
            if col == 1:
                return item.product.name_en if item.product else _t("stock_take.unknown_product")
            if col == 2:
                return f"{item.expected_qty:.3f}"
            if col == 3:
                return f"{item.counted_qty:.3f}" if item.counted_qty is not None else ""
            if col == 4:
                return f"{item.variance_qty:.3f}" if item.variance_qty is not None else ""
            if col == 5:
                return format_currency(item.variance_value) if item.variance_value is not None else ""

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col in (4, 5) and item.variance_qty is not None:
                if item.variance_qty < 0:
                    return QColor("#FF4136")  # Red for shortage
                elif item.variance_qty > 0:
                    return QColor("#39FF14")  # Green for surplus
                else:
                    return QColor("#888888")  # Gray for zero

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col >= 2:
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        elif role == Qt.ItemDataRole.EditRole:
            if col == self.COL_COUNTED:
                return str(item.counted_qty) if item.counted_qty is not None else ""

        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        """Persist an edited Counted value and recompute the row's variance."""
        if role != Qt.ItemDataRole.EditRole or index.column() != self.COL_COUNTED:
            return False

        item = self.items[index.row()]
        try:
            counted = Decimal(str(value)).quantize(Precision.QUANTITY)
            if counted < 0 or counted > self.MAX_COUNTED:
                return False
        except (InvalidOperation, ValueError):
            return False

        try:
            StockCountService.update_count(item.id, counted)
            item.counted_qty = counted
            item.variance_qty = (counted - item.expected_qty).quantize(Precision.QUANTITY)
            if item.product:
                item.variance_value = (item.variance_qty * item.product.cost).quantize(Precision.MONEY)
            self.dataChanged.emit(
                self.index(index.row(), 0),
                self.index(index.row(), self.columnCount() - 1),
            )
            return True
        except Exception as e:
            logger.error("Error updating count: %s", e)
            return False

    def flags(self, index):
        """Mark the Counted column as editable."""
        flags = super().flags(index)
        if index.column() == self.COL_COUNTED:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def headerData(self, section, orientation, role):
        """Return the translated header label for a column."""
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return None

    def get_item(self, row: int):
        """Return the stock count item at the given row, or None."""
        if 0 <= row < len(self.items):
            return self.items[row]
        return None


def _count_decimals(product) -> int:
    """Decimal places a product is counted in: its unit's, else 3 if weighed, else 0."""
    if product is None:
        return 0
    if product.unit is not None:
        return min(product.unit.decimal_places or 0, 3)
    return 3 if product.is_weighted else 0


class CountedDelegate(QStyledItemDelegate):
    """Editor for the Counted column built for fast keyboard counting (#615).

    Numbers only, with the product unit's decimals and at most six integer
    digits. Enter commits and asks the view to open the next row's Counted
    cell (``next_row_requested``); Enter on an empty cell just moves on.
    """

    next_row_requested = pyqtSignal()

    def createEditor(self, parent, option, index):
        """Return a QLineEdit limited to a valid count for this row's product."""
        editor = QLineEdit(parent)
        item = index.model().get_item(index.row())
        decimals = _count_decimals(item.product if item else None)
        pattern = rf"\d{{0,6}}(\.\d{{0,{decimals}}})?" if decimals else r"\d{0,6}"
        editor.setValidator(QRegularExpressionValidator(QRegularExpression(pattern), editor))
        # A scan landing here is routed to the view, not typed in as a count (#547)
        editor.setProperty(BarcodeScanner.SCAN_PASSTHROUGH_PROPERTY, True)
        return editor

    def eventFilter(self, editor, event):
        """Commit on Enter and move down instead of only closing the editor."""
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if editor.text() and not editor.hasAcceptableInput():
                return True  # e.g. "." alone -- keep editing
            if editor.text():
                self.commitData.emit(editor)
            self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
            self.next_row_requested.emit()
            return True
        return super().eventFilter(editor, event)


class StockCountReportDialog(QDialog):
    """Read-only dialog showing stock count variance report."""

    def __init__(self, stock_count_id: int, parent=None):
        """Initialize the dialog and build the report for the given stock count."""
        super().__init__(parent)
        self.setWindowTitle(_t("stock_take.report_title"))
        self.setMinimumSize(700, 500)
        self.resize(800, 550)
        self.init_ui(stock_count_id)

    def init_ui(self, stock_count_id: int) -> None:
        """Build the header info and read-only items table for the report."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        stock_count = StockCountService.get_stock_count(stock_count_id)
        if not stock_count:
            layout.addWidget(QLabel(_t("stock_take.count_not_found")))
            return

        # Header
        title = QLabel(_t("stock_take.count_label", number=stock_count.document_number))
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel(_t("stock_take.status_label", status=stock_count.status)))
        info_layout.addWidget(
            QLabel(
                _t(
                    "stock_take.date_label",
                    date=stock_count.date.strftime("%Y-%m-%d %H:%M") if stock_count.date else _t("common.na"),
                )
            )
        )
        info_layout.addWidget(QLabel(_t("stock_take.note_label", note=stock_count.note or _t("common.na"))))
        info_layout.addStretch()
        info_layout.addWidget(
            QLabel(_t("stock_take.total_variance_label", amount=format_currency(stock_count.total_variance_value)))
        )
        layout.addLayout(info_layout)

        # Items table
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(
            [
                _t("stock_take.col_barcode"),
                _t("stock_take.col_product"),
                _t("stock_take.col_expected"),
                _t("stock_take.col_counted"),
                _t("stock_take.col_variance"),
                _t("stock_take.col_value"),
            ]
        )
        configure_table_columns(
            table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # Barcode
                1: QHeaderView.ResizeMode.Stretch,  # Product - needs the room
                2: QHeaderView.ResizeMode.ResizeToContents,  # Expected
                3: QHeaderView.ResizeMode.ResizeToContents,  # Counted
                4: QHeaderView.ResizeMode.ResizeToContents,  # Variance
                5: QHeaderView.ResizeMode.ResizeToContents,  # Value
            },
            minimum_section_size=70,
        )
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)

        for item in stock_count.items:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(item.product.barcode if item.product else ""))
            table.setItem(
                row, 1, QTableWidgetItem(item.product.name_en if item.product else _t("stock_take.unknown_product"))
            )

            for col, val in [
                (2, item.expected_qty),
                (3, item.counted_qty),
                (4, item.variance_qty),
            ]:
                text = f"{val:.3f}" if val is not None else ""
                cell = QTableWidgetItem(text)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col == 4 and val is not None:
                    if val < 0:
                        cell.setForeground(QColor("#FF4136"))
                    elif val > 0:
                        cell.setForeground(QColor("#39FF14"))
                table.setItem(row, col, cell)

            val_text = format_currency(item.variance_value) if item.variance_value is not None else ""
            val_cell = QTableWidgetItem(val_text)
            val_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if item.variance_value is not None:
                if item.variance_value < 0:
                    val_cell.setForeground(QColor("#FF4136"))
                elif item.variance_value > 0:
                    val_cell.setForeground(QColor("#39FF14"))
            table.setItem(row, 5, val_cell)

        layout.addWidget(table, 1)

        close_btn = QPushButton(_t("common.close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class StockTakeView(QWidget):
    """Stock take view with New Count and History tabs."""

    def __init__(self) -> None:
        """Initialize the view, build its UI, and register for language updates."""
        super().__init__()
        self.current_stock_count = None
        self.init_ui()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        # weakref avoids a self -> destroyed-connection -> lambda -> self
        # reference cycle that only a full gc.collect() can break, which
        # can segfault mid-teardown (#392).
        self_ref = weakref.ref(self)

        def _unregister():
            view = self_ref()
            if view is not None:
                unregister_language_callback(view.retranslate_ui)

        self.destroyed.connect(_unregister)

    def init_ui(self) -> None:
        """Build the page header and the New Count / History tabs."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        from cbpos.ui.resources.icons import Icons
        from cbpos.ui.widgets.page_header import PageHeader

        self._page_header = PageHeader(icon_name=Icons.STOCK_TAKE)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(16, 12, 16, 0)
        header_row.addWidget(self._page_header)
        layout.addLayout(header_row)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: New Count
        self.new_count_tab = QWidget()
        self.setup_new_count_tab()
        self.tabs.addTab(self.new_count_tab, _t("stock_take.tab_new_count"))

        # Tab 2: History
        self.history_tab = QWidget()
        self.setup_history_tab()
        self.tabs.addTab(self.history_tab, _t("stock_take.tab_history"))

    def setup_new_count_tab(self) -> None:
        """Build the New Count tab: header controls, items table, stats bar, and action buttons."""
        layout = QVBoxLayout(self.new_count_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header row
        header_layout = QHBoxLayout()

        self.note_label = QLabel(_t("stock_take.note_field"))
        header_layout.addWidget(self.note_label)
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText(_t("stock_take.note_placeholder"))
        header_layout.addWidget(self.note_input)

        self.category_label = QLabel(_t("stock_take.category_field"))
        header_layout.addWidget(self.category_label)
        self.category_combo = QComboBox()
        self.category_combo.addItem(_t("stock_take.all_categories"), None)
        self._load_categories()
        header_layout.addWidget(self.category_combo)

        self.btn_load = QPushButton(_t("stock_take.btn_load_products"))
        self.btn_load.setProperty("class", "secondary")
        self.btn_load.clicked.connect(self.load_products)
        header_layout.addWidget(self.btn_load)

        layout.addLayout(header_layout)

        # Product search
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_t("stock_take.search_placeholder"))
        self.search_input.returnPressed.connect(self.add_single_product)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Items table
        self.item_table = QTableView()
        self._set_item_model(StockCountItemModel())
        self.item_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # Keyboard counting (#615): a click on the selected Counted cell or
        # any typed digit edits; Enter saves and opens the next row.
        self.item_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.counted_delegate = CountedDelegate(self.item_table)
        self.counted_delegate.next_row_requested.connect(self._edit_next_counted)
        self.item_table.setItemDelegateForColumn(StockCountItemModel.COL_COUNTED, self.counted_delegate)
        self.item_table.setAlternatingRowColors(True)
        # minimum_section_size floors COUNTED (col 3) so ResizeToContents --
        # computed while every cell is still empty at load time -- can't
        # collapse the column its own live-typed editor then has to render in.
        configure_table_columns(
            self.item_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # Barcode
                1: QHeaderView.ResizeMode.Stretch,  # Product - needs the room
                2: QHeaderView.ResizeMode.ResizeToContents,  # Expected
                3: QHeaderView.ResizeMode.ResizeToContents,  # Counted
                4: QHeaderView.ResizeMode.ResizeToContents,  # Variance
                5: QHeaderView.ResizeMode.ResizeToContents,  # Value
            },
            minimum_section_size=70,
        )
        layout.addWidget(self.item_table, 1)

        # Stats bar
        stats_layout = QHBoxLayout()
        self.lbl_items = QLabel(_t("stock_take.items_count", count=0))
        self.lbl_counted = QLabel(_t("stock_take.counted_progress", counted=0, total=0))
        self.lbl_variance = QLabel(_t("stock_take.variance_amount", amount="Rs. 0.00"))
        self.lbl_status = QLabel(_t("stock_take.status_display", status="---"))
        stats_layout.addWidget(self.lbl_items)
        stats_layout.addWidget(self.lbl_counted)
        stats_layout.addWidget(self.lbl_variance)
        stats_layout.addStretch()
        stats_layout.addWidget(self.lbl_status)
        layout.addLayout(stats_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_save_draft = QPushButton(_t("stock_take.btn_save_draft"))
        self.btn_save_draft.setProperty("class", "accent")
        self.btn_save_draft.clicked.connect(self.save_draft)
        btn_layout.addWidget(self.btn_save_draft)

        self.btn_finalize = QPushButton(_t("stock_take.btn_finalize"))
        self.btn_finalize.setProperty("class", "primary")
        self.btn_finalize.clicked.connect(self.finalize_count)
        btn_layout.addWidget(self.btn_finalize)

        self.btn_approve = QPushButton(_t("stock_take.btn_approve_apply"))
        self.btn_approve.setProperty("class", "primary")
        self.btn_approve.clicked.connect(self.approve_and_apply)
        btn_layout.addWidget(self.btn_approve)

        self.btn_void = QPushButton(_t("stock_take.btn_void"))
        self.btn_void.setProperty("class", "danger")
        self.btn_void.clicked.connect(self.void_count)
        btn_layout.addWidget(self.btn_void)

        btn_layout.addStretch()

        self.btn_new = QPushButton(_t("stock_take.btn_new_count"))
        self.btn_new.setProperty("class", "secondary")
        self.btn_new.clicked.connect(self.reset_form)
        btn_layout.addWidget(self.btn_new)

        layout.addLayout(btn_layout)

    def setup_history_tab(self) -> None:
        """Build the History tab: status/date filters and the count history table."""
        layout = QVBoxLayout(self.history_tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Filters
        filter_layout = QHBoxLayout()

        self.hist_status_label = QLabel(_t("common.status") + ":")
        filter_layout.addWidget(self.hist_status_label)
        self.hist_status_combo = QComboBox()
        self.hist_status_combo.addItem(_t("common.all"), None)
        self.hist_status_combo.addItem(_t("stock_take.status_draft"), DocumentStatus.DRAFT)
        self.hist_status_combo.addItem(_t("stock_take.status_counted"), DocumentStatus.COUNTED)
        self.hist_status_combo.addItem(_t("stock_take.status_completed"), DocumentStatus.COMPLETED)
        self.hist_status_combo.addItem(_t("stock_take.status_void"), DocumentStatus.VOID)
        filter_layout.addWidget(self.hist_status_combo)

        self.hist_from_label = QLabel(_t("common.from"))
        filter_layout.addWidget(self.hist_from_label)
        self.hist_date_from = QDateEdit()
        self.hist_date_from.setCalendarPopup(True)
        self.hist_date_from.setDate(QDate.currentDate().addMonths(-3))
        filter_layout.addWidget(self.hist_date_from)

        self.hist_to_label = QLabel(_t("common.to"))
        filter_layout.addWidget(self.hist_to_label)
        self.hist_date_to = QDateEdit()
        self.hist_date_to.setCalendarPopup(True)
        self.hist_date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.hist_date_to)

        self.hist_refresh_btn = QPushButton(_t("common.refresh"))
        self.hist_refresh_btn.setProperty("class", "secondary")
        self.hist_refresh_btn.clicked.connect(self.refresh_history)
        filter_layout.addWidget(self.hist_refresh_btn)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # History table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(
            [
                _t("stock_take.hist_col_stk"),
                _t("common.date"),
                _t("stock_take.hist_col_user"),
                _t("stock_take.hist_col_items"),
                _t("stock_take.hist_col_variance_total"),
                _t("common.status"),
            ]
        )
        configure_table_columns(
            self.history_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # STK #
                1: QHeaderView.ResizeMode.ResizeToContents,  # Date
                2: QHeaderView.ResizeMode.Stretch,  # User - needs the room
                3: QHeaderView.ResizeMode.ResizeToContents,  # Items
                4: QHeaderView.ResizeMode.ResizeToContents,  # Variance Total
                5: QHeaderView.ResizeMode.ResizeToContents,  # Status
            },
            minimum_section_size=70,
        )
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.doubleClicked.connect(self.on_history_double_click)
        self.history_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self.show_history_context_menu)
        layout.addWidget(self.history_table, 1)

        # Store IDs for double-click lookup
        self._history_ids = []

    def retranslate_ui(self) -> None:
        """Update all widget text from the translation system."""
        self._page_header.set_title(_t("management.sidebar_stock_take"))
        # Tabs
        self.tabs.setTabText(0, _t("stock_take.tab_new_count"))
        self.tabs.setTabText(1, _t("stock_take.tab_history"))

        # New count tab - header
        self.note_label.setText(_t("stock_take.note_field"))
        self.note_input.setPlaceholderText(_t("stock_take.note_placeholder"))
        self.category_label.setText(_t("stock_take.category_field"))
        self.category_combo.setItemText(0, _t("stock_take.all_categories"))
        self.btn_load.setText(_t("stock_take.btn_load_products"))
        self.search_input.setPlaceholderText(_t("stock_take.search_placeholder"))

        # Buttons
        self.btn_save_draft.setText(_t("stock_take.btn_save_draft"))
        self.btn_finalize.setText(_t("stock_take.btn_finalize"))
        self.btn_approve.setText(_t("stock_take.btn_approve_apply"))
        self.btn_void.setText(_t("stock_take.btn_void"))
        self.btn_new.setText(_t("stock_take.btn_new_count"))

        # Update stats
        self._update_stats()

        # Update item model headers
        self.item_model.update_headers(
            [
                _t("stock_take.col_barcode"),
                _t("stock_take.col_product"),
                _t("stock_take.col_expected"),
                _t("stock_take.col_counted"),
                _t("stock_take.col_variance"),
                _t("stock_take.col_value"),
            ]
        )

        # History tab
        self.hist_status_label.setText(_t("common.status") + ":")
        self.hist_status_combo.setItemText(0, _t("common.all"))
        self.hist_status_combo.setItemText(1, _t("stock_take.status_draft"))
        self.hist_status_combo.setItemText(2, _t("stock_take.status_counted"))
        self.hist_status_combo.setItemText(3, _t("stock_take.status_completed"))
        self.hist_status_combo.setItemText(4, _t("stock_take.status_void"))
        self.hist_from_label.setText(_t("common.from"))
        self.hist_to_label.setText(_t("common.to"))
        self.hist_refresh_btn.setText(_t("common.refresh"))

        self.history_table.setHorizontalHeaderLabels(
            [
                _t("stock_take.hist_col_stk"),
                _t("common.date"),
                _t("stock_take.hist_col_user"),
                _t("stock_take.hist_col_items"),
                _t("stock_take.hist_col_variance_total"),
                _t("common.status"),
            ]
        )

    # ========== New Count Methods ==========

    def _load_categories(self) -> None:
        """Load categories into the filter combo."""
        from cbpos.core.services.category_service import CategoryService

        categories = CategoryService.get_all()
        for cat in categories:
            self.category_combo.addItem(cat.name, cat.id)

    def load_products(self) -> None:
        """Create stock count and load products."""
        if not hasattr(self, "user") or not self.user:
            QMessageBox.warning(self, _t("common.error"), _t("stock_take.user_not_logged_in"))
            return

        if not self.current_stock_count:
            note = self.note_input.text().strip() or None
            self.current_stock_count = StockCountService.create_stock_count(user_id=self.user.id, note=note)

        category_id = self.category_combo.currentData()
        try:
            count = StockCountService.add_all_products(self.current_stock_count.id, category_id=category_id)
            QMessageBox.information(self, _t("stock_take.loaded_title"), _t("stock_take.products_loaded", count=count))
            self._reload_items()
        except ValueError as e:
            QMessageBox.warning(self, _t("common.error"), str(e))

    def add_single_product(self) -> None:
        """Add a single product via barcode/search."""
        query = self.search_input.text().strip()
        if not query:
            return

        if not self.current_stock_count:
            if not hasattr(self, "user") or not self.user:
                QMessageBox.warning(self, _t("common.error"), _t("stock_take.user_not_logged_in"))
                return
            note = self.note_input.text().strip() or None
            self.current_stock_count = StockCountService.create_stock_count(user_id=self.user.id, note=note)

        products = ProductService.search(query)
        if not products:
            QMessageBox.warning(self, _t("stock_take.not_found_title"), _t("stock_take.product_not_found"))
            return

        product = products[0]
        try:
            StockCountService.add_single_item(self.current_stock_count.id, product.id)
            self.search_input.clear()
            self._reload_items()
        except ValueError as e:
            QMessageBox.warning(self, _t("common.error"), str(e))

    def _reload_items(self) -> None:
        """Reload items from the database for the current stock count."""
        if not self.current_stock_count:
            return
        sc = StockCountService.get_stock_count(self.current_stock_count.id)
        if sc:
            self.current_stock_count = sc
            self._set_item_model(StockCountItemModel(list(sc.items)))
            self._update_stats()

    def _set_item_model(self, model: StockCountItemModel) -> None:
        """Show ``model`` in the items table, keeping the current cell on Counted."""
        self.item_model = model
        self.item_table.setModel(model)
        # setModel() makes a new selection model, so reconnect every time.
        self.item_table.selectionModel().currentChanged.connect(self._snap_to_counted)

    def _snap_to_counted(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Keep the current cell on Counted so typing a number edits it (#615)."""
        if current.isValid() and current.column() != StockCountItemModel.COL_COUNTED:
            self.item_table.setCurrentIndex(current.siblingAtColumn(StockCountItemModel.COL_COUNTED))

    def _edit_next_counted(self) -> None:
        """Open the Counted editor on the row below the current one, if any."""
        row = self.item_table.currentIndex().row() + 1
        if 0 < row < self.item_model.rowCount():
            index = self.item_model.index(row, StockCountItemModel.COL_COUNTED)
            self.item_table.setCurrentIndex(index)
            self.item_table.scrollTo(index)
            self.item_table.edit(index)

    def _update_stats(self) -> None:
        """Update the stats bar labels."""
        if not self.current_stock_count:
            self.lbl_items.setText(_t("stock_take.items_count", count=0))
            self.lbl_counted.setText(_t("stock_take.counted_progress", counted=0, total=0))
            self.lbl_variance.setText(_t("stock_take.variance_amount", amount="Rs. 0.00"))
            self.lbl_status.setText(_t("stock_take.status_display", status="---"))
            # No count yet: only starting one makes sense. Without this the
            # buttons kept the last count's state, so Load Products stayed
            # disabled after a Void/Approve even past "New Count" (#615).
            self.btn_load.setEnabled(True)
            for btn in (self.btn_save_draft, self.btn_finalize, self.btn_approve, self.btn_void):
                btn.setEnabled(False)
            return

        items = self.item_model.items
        total = len(items)
        counted = sum(1 for i in items if i.counted_qty is not None)
        variance = sum(abs(i.variance_value) for i in items if i.variance_value is not None)

        self.lbl_items.setText(_t("stock_take.items_count", count=total))
        self.lbl_counted.setText(_t("stock_take.counted_progress", counted=counted, total=total))
        self.lbl_variance.setText(_t("stock_take.variance_amount", amount=format_currency(variance)))
        self.lbl_status.setText(_t("stock_take.status_display", status=self.current_stock_count.status))

        # Button state
        is_draft = self.current_stock_count.status == DocumentStatus.DRAFT
        is_counted = self.current_stock_count.status == DocumentStatus.COUNTED
        self.btn_load.setEnabled(is_draft)
        self.btn_save_draft.setEnabled(is_draft)
        self.btn_finalize.setEnabled(is_draft and counted == total and total > 0)
        self.btn_approve.setEnabled(is_counted)
        self.btn_void.setEnabled(is_draft or is_counted)

    def save_draft(self) -> None:
        """Save current state (items are already persisted via update_count)."""
        QMessageBox.information(self, _t("common.saved"), _t("stock_take.draft_saved"))

    def finalize_count(self) -> None:
        """Finalize the count -- validate and set to COUNTED status."""
        if not self.current_stock_count:
            return

        try:
            self.current_stock_count = StockCountService.finalize_count(self.current_stock_count.id)
            QMessageBox.information(
                self,
                _t("stock_take.finalized_title"),
                _t(
                    "stock_take.finalized_message",
                    number=self.current_stock_count.document_number,
                    variance=format_currency(self.current_stock_count.total_variance_value),
                ),
            )
            self._reload_items()
        except ValueError as e:
            QMessageBox.warning(self, _t("common.error"), str(e))

    def approve_and_apply(self) -> None:
        """Approve the count and apply stock adjustments."""
        if not self.current_stock_count:
            return

        if not hasattr(self, "user") or not self.user:
            QMessageBox.warning(self, _t("common.error"), _t("stock_take.user_not_logged_in"))
            return

        # Confirmation
        variance = self.current_stock_count.total_variance_value
        reply = QMessageBox.question(
            self,
            _t("stock_take.confirm_approval_title"),
            _t("stock_take.confirm_approval_message", variance=format_currency(variance)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.current_stock_count = StockCountService.approve_and_apply(self.current_stock_count.id, self.user.id)
            QMessageBox.information(
                self,
                _t("stock_take.applied_title"),
                _t("stock_take.applied_message", number=self.current_stock_count.document_number),
            )
            # The count is finished (it stays in History); clear the form so
            # the next count can start straight away (#615).
            self.reset_form()
        except ValueError as e:
            QMessageBox.warning(self, _t("common.error"), str(e))

    def void_count(self) -> None:
        """Void the current stock count."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.STOCK_TAKE_APPROVE, self):
            return

        if not self.current_stock_count:
            return

        reply = QMessageBox.question(
            self,
            _t("stock_take.confirm_void_title"),
            _t("stock_take.confirm_void_message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.current_stock_count = StockCountService.void_stock_count(self.current_stock_count.id)
            QMessageBox.information(self, _t("stock_take.voided_title"), _t("stock_take.voided_message"))
            self.reset_form()  # Same as after Approve: ready for a new count (#615)
        except ValueError as e:
            QMessageBox.warning(self, _t("common.error"), str(e))

    def reset_form(self) -> None:
        """Reset the form for a new stock count."""
        self.current_stock_count = None
        self._set_item_model(StockCountItemModel())
        self.note_input.clear()
        self.search_input.clear()
        self.category_combo.setCurrentIndex(0)
        self._update_stats()

    # ========== History Methods ==========

    def refresh_history(self) -> None:
        """Refresh the stock count history table."""
        status = self.hist_status_combo.currentData()

        qd_from = self.hist_date_from.date()
        date_from = datetime(qd_from.year(), qd_from.month(), qd_from.day())

        qd_to = self.hist_date_to.date()
        date_to = datetime(qd_to.year(), qd_to.month(), qd_to.day(), 23, 59, 59)

        counts = StockCountService.get_all_stock_counts(status=status, date_from=date_from, date_to=date_to)

        self.history_table.setRowCount(0)
        self._history_ids = []

        for sc in counts:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            self._history_ids.append(sc.id)

            self.history_table.setItem(row, 0, QTableWidgetItem(sc.document_number))
            self.history_table.setItem(row, 1, QTableWidgetItem(sc.date.strftime("%Y-%m-%d %H:%M") if sc.date else ""))
            self.history_table.setItem(row, 2, QTableWidgetItem(sc.user.username if sc.user else ""))

            items_item = QTableWidgetItem(str(len(sc.items)) if sc.items else "0")
            items_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.history_table.setItem(row, 3, items_item)

            var_item = QTableWidgetItem(format_currency(sc.total_variance_value))
            var_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.history_table.setItem(row, 4, var_item)

            self.history_table.setItem(row, 5, QTableWidgetItem(sc.status))

    def on_history_double_click(self, index: QModelIndex) -> None:
        """Open stock count report dialog on double-click."""
        row = index.row()
        if 0 <= row < len(self._history_ids):
            dialog = StockCountReportDialog(self._history_ids[row], self)
            dialog.exec()

    def show_history_context_menu(self, position) -> None:
        """Offer Resume/Discard on a DRAFT history row (#312).

        Without this, a DRAFT count that outlives the session it was
        started in (app restart, navigating away) has no way back into an
        editable state and no way to be discarded either -- it just
        accumulates as permanent, unfinishable clutter.
        """
        row = self.history_table.indexAt(position).row()
        if row < 0 or row >= len(self._history_ids):
            return
        self.history_table.selectRow(row)

        status_item = self.history_table.item(row, 5)
        if not status_item or status_item.text() != DocumentStatus.DRAFT:
            return

        stock_count_id = self._history_ids[row]

        menu = QMenu(self)
        resume_action = menu.addAction(_t("stock_take.context_resume"))
        resume_action.triggered.connect(lambda: self.resume_draft_count(stock_count_id))
        discard_action = menu.addAction(_t("stock_take.context_discard_draft"))
        discard_action.triggered.connect(lambda: self.discard_draft_count(stock_count_id))
        menu.exec(self.history_table.viewport().mapToGlobal(position))

    def resume_draft_count(self, stock_count_id: int) -> None:
        """Reload a DRAFT count from History as the active count in New Count."""
        sc = StockCountService.get_stock_count(stock_count_id)
        if not sc or sc.status != DocumentStatus.DRAFT:
            QMessageBox.warning(self, _t("common.error"), _t("stock_take.resume_failed"))
            return

        self.current_stock_count = sc
        self._set_item_model(StockCountItemModel(list(sc.items)))
        self._update_stats()
        self.tabs.setCurrentIndex(0)

    def discard_draft_count(self, stock_count_id: int) -> None:
        """Void an abandoned DRAFT count directly from History."""
        reply = QMessageBox.question(
            self,
            _t("stock_take.confirm_discard_title"),
            _t("stock_take.confirm_discard_message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            StockCountService.void_stock_count(stock_count_id)
            if self.current_stock_count and self.current_stock_count.id == stock_count_id:
                self.reset_form()
            self.refresh_history()
        except ValueError as e:
            QMessageBox.warning(self, _t("common.error"), str(e))

    def set_user(self, user) -> None:
        """Store the logged-in user for permission checks and count creation."""
        self.user = user
