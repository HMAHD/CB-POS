from decimal import Decimal, InvalidOperation
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)
from PyQt6.QtCore import Qt


class CashMovementDialog(QDialog):
    def __init__(self, movement_type="IN", parent=None):
        super().__init__(parent)
        self.movement_type = movement_type
        self.setWindowTitle(f"Cash {movement_type}")
        self.setFixedSize(400, 250)
        self.init_ui()

        self.amount = Decimal("0.00")
        self.reason = ""

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel(f"Record Cash {self.movement_type}")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {'#39FF14' if self.movement_type == 'IN' else '#FF4136'};"  # noqa: E231, E501, E702
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(20)

        # Amount
        lbl_amount = QLabel("Amount:")
        self.txt_amount = QLineEdit()
        self.txt_amount.setPlaceholderText("0.00")
        self.txt_amount.setStyleSheet("font-size: 16px; padding: 5px;")
        layout.addWidget(lbl_amount)
        layout.addWidget(self.txt_amount)

        # Reason
        lbl_reason = QLabel("Reason:")
        self.txt_reason = QLineEdit()
        self.txt_reason.setPlaceholderText("e.g. Petty Cash, Float")
        self.txt_reason.setStyleSheet("font-size: 16px; padding: 5px;")
        layout.addWidget(lbl_reason)
        layout.addWidget(self.txt_reason)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.validate_and_save)
        self.btn_save.setStyleSheet(
            "background-color: #0074D9; color: white; font-weight: bold;"
        )
        btn_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setStyleSheet("background-color: #555555; color: white;")
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def validate_and_save(self):
        amount_text = self.txt_amount.text().strip()
        reason = self.txt_reason.text().strip()

        if not amount_text:
            QMessageBox.warning(self, "Input Error", "Please enter an amount.")
            return

        try:
            amount = Decimal(amount_text)
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Input Error", "Invalid amount.")
            return

        if not reason:
            QMessageBox.warning(self, "Input Error", "Please enter a reason.")
            return

        self.amount = amount
        self.reason = reason
        self.accept()
