"""Stock Take view for physical inventory counting and variance workflow."""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QComboBox,
    QDateEdit,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
    QDialog,
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QDate, QModelIndex
from PyQt6.QtGui import QColor

from cbpos.core.services.stock_count_service import StockCountService
from cbpos.core.services.product_service import ProductService
from cbpos.core.constants.status import DocumentStatus, Precision
from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)


class StockCountItemModel(QAbstractTableModel):
    """Table model for stock count items with editable Counted column."""

    HEADERS = ["Barcode", "Product", "Expected", "Counted", "Variance", "Value"]
    COL_COUNTED = 3

    def __init__(self, items=None):
        super().__init__()
        self.items = items or []

    def rowCount(self, parent=None):
        return len(self.items)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def data(self, index, role):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return item.product.barcode if item.product else ""
            if col == 1:
                return item.product.name_en if item.product else "Unknown"
            if col == 2:
                return f"{item.expected_qty:.3f}"  # noqa: E231
            if col == 3:
                return f"{item.counted_qty:.3f}" if item.counted_qty is not None else ""  # noqa: E231
            if col == 4:
                return f"{item.variance_qty:.3f}" if item.variance_qty is not None else ""  # noqa: E231
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
        if role != Qt.ItemDataRole.EditRole or index.column() != self.COL_COUNTED:
            return False

        item = self.items[index.row()]
        try:
            counted = Decimal(str(value)).quantize(Precision.QUANTITY)
            if counted < 0:
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
        flags = super().flags(index)
        if index.column() == self.COL_COUNTED:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def get_item(self, row: int):
        if 0 <= row < len(self.items):
            return self.items[row]
        return None


class StockCountReportDialog(QDialog):
    """Read-only dialog showing stock count variance report."""

    def __init__(self, stock_count_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stock Count Report")
        self.setMinimumSize(700, 500)
        self.resize(800, 550)
        self.init_ui(stock_count_id)

    def init_ui(self, stock_count_id: int) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        stock_count = StockCountService.get_stock_count(stock_count_id)
        if not stock_count:
            layout.addWidget(QLabel("Stock count not found."))
            return

        # Header
        title = QLabel(f"Stock Count: {stock_count.document_number}")
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel(f"Status: {stock_count.status}"))
        info_layout.addWidget(
            QLabel(f"Date: {stock_count.date.strftime('%Y-%m-%d %H:%M') if stock_count.date else 'N/A'}")
        )
        info_layout.addWidget(QLabel(f"Note: {stock_count.note or 'N/A'}"))
        info_layout.addStretch()
        info_layout.addWidget(QLabel(f"Total Variance: {format_currency(stock_count.total_variance_value)}"))
        layout.addLayout(info_layout)

        # Items table
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Barcode", "Product", "Expected", "Counted", "Variance", "Value"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)

        for item in stock_count.items:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(item.product.barcode if item.product else ""))
            table.setItem(row, 1, QTableWidgetItem(item.product.name_en if item.product else "Unknown"))

            for col, val in [
                (2, item.expected_qty),
                (3, item.counted_qty),
                (4, item.variance_qty),
            ]:
                text = f"{val:.3f}" if val is not None else ""  # noqa: E231
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

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class StockTakeView(QWidget):
    """Stock take view with New Count and History tabs."""

    def __init__(self) -> None:
        super().__init__()
        self.current_stock_count = None
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: New Count
        self.new_count_tab = QWidget()
        self.setup_new_count_tab()
        self.tabs.addTab(self.new_count_tab, "New Count")

        # Tab 2: History
        self.history_tab = QWidget()
        self.setup_history_tab()
        self.tabs.addTab(self.history_tab, "History")

    def setup_new_count_tab(self) -> None:
        layout = QVBoxLayout(self.new_count_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header row
        header_layout = QHBoxLayout()

        header_layout.addWidget(QLabel("Note:"))
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Stock count description (optional)")
        header_layout.addWidget(self.note_input)

        header_layout.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", None)
        self._load_categories()
        header_layout.addWidget(self.category_combo)

        self.btn_load = QPushButton("Load Products")
        self.btn_load.setProperty("class", "primary")
        self.btn_load.clicked.connect(self.load_products)
        header_layout.addWidget(self.btn_load)

        layout.addLayout(header_layout)

        # Product search
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Scan barcode or search product to add...")
        self.search_input.returnPressed.connect(self.add_single_product)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Items table
        self.item_model = StockCountItemModel()
        self.item_table = QTableView()
        self.item_table.setModel(self.item_model)
        self.item_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.item_table.setAlternatingRowColors(True)
        self.item_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.item_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.item_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.item_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.item_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.item_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.item_table, 1)

        # Stats bar
        stats_layout = QHBoxLayout()
        self.lbl_items = QLabel("Items: 0")
        self.lbl_counted = QLabel("Counted: 0/0")
        self.lbl_variance = QLabel("Variance: Rs. 0.00")
        self.lbl_status = QLabel("Status: ---")
        stats_layout.addWidget(self.lbl_items)
        stats_layout.addWidget(self.lbl_counted)
        stats_layout.addWidget(self.lbl_variance)
        stats_layout.addStretch()
        stats_layout.addWidget(self.lbl_status)
        layout.addLayout(stats_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_save_draft = QPushButton("Save Draft")
        self.btn_save_draft.setProperty("class", "accent")
        self.btn_save_draft.clicked.connect(self.save_draft)
        btn_layout.addWidget(self.btn_save_draft)

        self.btn_finalize = QPushButton("Finalize Count")
        self.btn_finalize.setProperty("class", "primary")
        self.btn_finalize.clicked.connect(self.finalize_count)
        btn_layout.addWidget(self.btn_finalize)

        self.btn_approve = QPushButton("Approve && Apply")
        self.btn_approve.setStyleSheet("background-color: #39FF14; color: black; font-weight: bold; padding: 8px;")
        self.btn_approve.clicked.connect(self.approve_and_apply)
        btn_layout.addWidget(self.btn_approve)

        self.btn_void = QPushButton("Void")
        self.btn_void.setProperty("class", "danger")
        self.btn_void.clicked.connect(self.void_count)
        btn_layout.addWidget(self.btn_void)

        btn_layout.addStretch()

        self.btn_new = QPushButton("New Count")
        self.btn_new.clicked.connect(self.reset_form)
        btn_layout.addWidget(self.btn_new)

        layout.addLayout(btn_layout)

    def setup_history_tab(self) -> None:
        layout = QVBoxLayout(self.history_tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Filters
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Status:"))
        self.hist_status_combo = QComboBox()
        self.hist_status_combo.addItem("All", None)
        self.hist_status_combo.addItem("Draft", DocumentStatus.DRAFT)
        self.hist_status_combo.addItem("Counted", DocumentStatus.COUNTED)
        self.hist_status_combo.addItem("Completed", DocumentStatus.COMPLETED)
        self.hist_status_combo.addItem("Void", DocumentStatus.VOID)
        filter_layout.addWidget(self.hist_status_combo)

        filter_layout.addWidget(QLabel("From:"))
        self.hist_date_from = QDateEdit()
        self.hist_date_from.setCalendarPopup(True)
        self.hist_date_from.setDate(QDate.currentDate().addMonths(-3))
        filter_layout.addWidget(self.hist_date_from)

        filter_layout.addWidget(QLabel("To:"))
        self.hist_date_to = QDateEdit()
        self.hist_date_to.setCalendarPopup(True)
        self.hist_date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.hist_date_to)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setProperty("class", "primary")
        refresh_btn.clicked.connect(self.refresh_history)
        filter_layout.addWidget(refresh_btn)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # History table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(["STK #", "Date", "User", "Items", "Variance Total", "Status"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.doubleClicked.connect(self.on_history_double_click)
        layout.addWidget(self.history_table, 1)

        # Store IDs for double-click lookup
        self._history_ids = []

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
            QMessageBox.warning(self, "Error", "User not logged in.")
            return

        if not self.current_stock_count:
            note = self.note_input.text().strip() or None
            self.current_stock_count = StockCountService.create_stock_count(user_id=self.user.id, note=note)

        category_id = self.category_combo.currentData()
        try:
            count = StockCountService.add_all_products(self.current_stock_count.id, category_id=category_id)
            QMessageBox.information(self, "Loaded", f"{count} products added to stock count.")
            self._reload_items()
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def add_single_product(self) -> None:
        """Add a single product via barcode/search."""
        query = self.search_input.text().strip()
        if not query:
            return

        if not self.current_stock_count:
            if not hasattr(self, "user") or not self.user:
                QMessageBox.warning(self, "Error", "User not logged in.")
                return
            note = self.note_input.text().strip() or None
            self.current_stock_count = StockCountService.create_stock_count(user_id=self.user.id, note=note)

        products = ProductService.search(query)
        if not products:
            QMessageBox.warning(self, "Not Found", "Product not found.")
            return

        product = products[0]
        try:
            StockCountService.add_single_item(self.current_stock_count.id, product.id)
            self.search_input.clear()
            self._reload_items()
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def _reload_items(self) -> None:
        """Reload items from the database for the current stock count."""
        if not self.current_stock_count:
            return
        sc = StockCountService.get_stock_count(self.current_stock_count.id)
        if sc:
            self.current_stock_count = sc
            self.item_model = StockCountItemModel(list(sc.items))
            self.item_table.setModel(self.item_model)
            self._update_stats()

    def _update_stats(self) -> None:
        """Update the stats bar labels."""
        if not self.current_stock_count:
            self.lbl_items.setText("Items: 0")
            self.lbl_counted.setText("Counted: 0/0")
            self.lbl_variance.setText("Variance: Rs. 0.00")
            self.lbl_status.setText("Status: ---")
            return

        items = self.item_model.items
        total = len(items)
        counted = sum(1 for i in items if i.counted_qty is not None)
        variance = sum(abs(i.variance_value) for i in items if i.variance_value is not None)

        self.lbl_items.setText(f"Items: {total}")
        self.lbl_counted.setText(f"Counted: {counted}/{total}")
        self.lbl_variance.setText(f"Variance: {format_currency(variance)}")
        self.lbl_status.setText(f"Status: {self.current_stock_count.status}")

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
        QMessageBox.information(self, "Saved", "Stock count saved as draft.")

    def finalize_count(self) -> None:
        """Finalize the count — validate and set to COUNTED status."""
        if not self.current_stock_count:
            return

        try:
            self.current_stock_count = StockCountService.finalize_count(self.current_stock_count.id)
            QMessageBox.information(
                self,
                "Finalized",
                f"Stock count {self.current_stock_count.document_number} finalized.\n"
                f"Total variance: {format_currency(self.current_stock_count.total_variance_value)}\n\n"
                "Click 'Approve & Apply' to adjust stock.",
            )
            self._reload_items()
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def approve_and_apply(self) -> None:
        """Approve the count and apply stock adjustments."""
        if not self.current_stock_count:
            return

        if not hasattr(self, "user") or not self.user:
            QMessageBox.warning(self, "Error", "User not logged in.")
            return

        # Confirmation
        variance = self.current_stock_count.total_variance_value
        reply = QMessageBox.question(
            self,
            "Confirm Approval",
            f"Apply stock adjustments?\n\n"
            f"Total variance value: {format_currency(variance)}\n\n"
            f"This will update product stock quantities and cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.current_stock_count = StockCountService.approve_and_apply(self.current_stock_count.id, self.user.id)
            QMessageBox.information(
                self,
                "Applied",
                f"Stock count {self.current_stock_count.document_number} approved.\n"
                "Stock quantities have been adjusted.",
            )
            self._reload_items()
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def void_count(self) -> None:
        """Void the current stock count."""
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.STOCK_TAKE_APPROVE, self):
            return

        if not self.current_stock_count:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Void",
            "Are you sure you want to void this stock count?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.current_stock_count = StockCountService.void_stock_count(self.current_stock_count.id)
            QMessageBox.information(self, "Voided", "Stock count voided.")
            self._reload_items()
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def reset_form(self) -> None:
        """Reset the form for a new stock count."""
        self.current_stock_count = None
        self.item_model = StockCountItemModel()
        self.item_table.setModel(self.item_model)
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

    def set_user(self, user) -> None:
        self.user = user
