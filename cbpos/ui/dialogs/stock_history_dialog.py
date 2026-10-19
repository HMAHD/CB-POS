from PyQt6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.models import Product
from cbpos.core.services.stock_service import StockService
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, SUCCESS, status_color
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    RelativeTimeTableWidgetItem,
    StatusPillDelegate,
    align_numeric_headers,
    attach_table_empty_state,
    configure_table_columns,
    set_status_pill,
)


class StockHistoryDialog(QDialog):
    """Dialog listing a product's stock movement history (audit trail of every quantity change)."""

    def __init__(self, product: Product, parent=None):
        """Build the dialog and load the stock movement history for `product`."""
        super().__init__(parent)
        self.product = product
        self.stock_service = StockService()
        self.setWindowTitle(_t("stock_history.title", name=product.name_en))
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)

        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        """Build the header, movement history table, and close button."""
        layout = QVBoxLayout(self)

        # Header
        lbl_header = QLabel(_t("stock_history.heading", product=self.product.name_en))
        lbl_header.setProperty("class", "dialog-title")
        layout.addWidget(lbl_header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                _t("common.date"),
                _t("common.type"),
                _t("stock_history.reference"),
                _t("stock_history.user"),
                _t("stock_history.change"),
                _t("stock_history.balance"),
            ]
        )
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.Stretch,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.ResizeToContents,
                5: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        align_numeric_headers(self.table.horizontalHeader(), (4, 5))
        self.table.setItemDelegateForColumn(1, StatusPillDelegate(self.table))
        self.table.setAlternatingRowColors(True)
        attach_table_empty_state(self.table, Icons.INVENTORY, "common.no_items")
        layout.addWidget(self.table)

        # Close Button
        btn_close = QPushButton(_t("common.close"))
        btn_close.setObjectName("BtnCancel")
        btn_close.setProperty("class", "secondary")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def load_data(self):
        """Fetch the product's stock movement history and populate the table, color-coding the change column."""
        history = self.stock_service.get_history(self.product.id)
        self.table.setRowCount(0)
        type_labels = {
            "SALE": _t("stock_history.type_sale"),
            "PURCHASE": _t("stock_history.type_purchase"),
            "ADJUSTMENT": _t("stock_history.type_adjustment"),
            "RETURN": _t("stock_history.type_return"),
            "VOID": _t("stock_history.type_void"),
        }
        type_meanings = {
            "SALE": "neutral",
            "PURCHASE": "success",
            "ADJUSTMENT": "info",
            "RETURN": "warning",
            "VOID": "danger",
        }

        for move in history:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, RelativeTimeTableWidgetItem(move.timestamp))

            type_text = type_labels.get(move.type, move.type)
            type_item = QTableWidgetItem(type_text)
            set_status_pill(type_item, type_text, type_meanings.get(move.type, "neutral"))
            self.table.setItem(row, 1, type_item)

            self.table.setItem(row, 2, QTableWidgetItem(move.document.document_number if move.document else ""))

            user_name = move.user.username if move.user else _t("stock_history.system")
            self.table.setItem(row, 3, QTableWidgetItem(user_name))

            # Change Column (Color Coded & Numeric Alignment)
            change_item = QTableWidgetItem(f"{move.qty_change:+.3f}")
            if move.qty_change > 0:
                change_item.setForeground(status_color(SUCCESS))
            elif move.qty_change < 0:
                change_item.setForeground(status_color(DANGER))
            change_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table.setItem(row, 4, change_item)

            bal_item = QTableWidgetItem(f"{move.balance_after:.3f}")
            bal_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table.setItem(row, 5, bal_item)
