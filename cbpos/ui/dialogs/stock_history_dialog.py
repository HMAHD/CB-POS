from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QPushButton,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.stock_service import StockService
from cbpos.core.models import Product
from cbpos.i18n import _t


class StockHistoryDialog(QDialog):
    def __init__(self, product: Product, parent=None):
        super().__init__(parent)
        self.product = product
        self.stock_service = StockService()
        self.setWindowTitle(_t("stock_history.title", name=product.name_en))
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)

        self.setup_ui()
        self.load_data()

    def setup_ui(self):
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
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Close Button
        btn_close = QPushButton(_t("common.close"))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def load_data(self):
        history = self.stock_service.get_history(self.product.id)
        self.table.setRowCount(0)

        for move in history:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(move.timestamp.strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 1, QTableWidgetItem(move.type))
            self.table.setItem(row, 2, QTableWidgetItem(move.reference))

            user_name = move.user.username if move.user else "System"
            self.table.setItem(row, 3, QTableWidgetItem(user_name))

            # Change Column (Color Coded)
            change_item = QTableWidgetItem(f"{move.qty_change:+.3f}")  # noqa: E231
            if move.qty_change > 0:
                change_item.setForeground(Qt.GlobalColor.green)
            elif move.qty_change < 0:
                change_item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 4, change_item)

            self.table.setItem(row, 5, QTableWidgetItem(f"{move.balance_after:.3f}"))  # noqa: E231
