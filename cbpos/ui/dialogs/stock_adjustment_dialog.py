from decimal import Decimal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QMessageBox,
    QFormLayout,
)

from PyQt6.QtGui import QDoubleValidator
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.models import Product


class StockAdjustmentDialog(QDialog):
    def __init__(self, product: Product, parent=None):
        super().__init__(parent)
        self.product = product

        self.setWindowTitle(f"Adjust Stock: {product.name_en}")
        self.setFixedSize(400, 300)
        self.setStyleSheet("background-color: #001F3F; color: white;")

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.lbl_current = QLabel(f"{self.product.stock_qty:.3f}")  # noqa: E231
        self.lbl_current.setStyleSheet("font-weight: bold; color: #39FF14;")
        form_layout.addRow("Current Stock:", self.lbl_current)

        self.txt_change = QLineEdit()
        self.txt_change.setPlaceholderText("+/- Amount (e.g. 10 or -5)")
        self.txt_change.setStyleSheet(
            "padding: 5px; color: black; background-color: white;"
        )
        # Allow negative numbers
        self.txt_change.setValidator(QDoubleValidator(-99999.99, 99999.99, 3))
        form_layout.addRow("Adjustment:", self.txt_change)

        self.cmb_reason = QComboBox()
        self.cmb_reason.addItems(
            ["Inventory Count", "Damage/Spoilage", "Return", "Other"]
        )
        self.cmb_reason.setStyleSheet(
            "padding: 5px; color: black; background-color: white;"
        )
        form_layout.addRow("Reason:", self.cmb_reason)

        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(
            "background-color: #FF4136; color: white; padding: 10px;"
        )
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Save Adjustment")
        btn_save.setStyleSheet(
            "background-color: #00BCEB; color: black; font-weight: bold; padding: 10px;"
        )
        btn_save.clicked.connect(self.save_adjustment)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def save_adjustment(self):
        try:
            change = Decimal(self.txt_change.text())
        except Exception:
            QMessageBox.warning(self, "Error", "Invalid amount.")
            return

        reason = self.cmb_reason.currentText()

        if change == 0:
            return

        if InventoryService.adjust_stock(self.product.id, change, reason):
            QMessageBox.information(self, "Success", "Stock adjusted successfully.")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to adjust stock.")
