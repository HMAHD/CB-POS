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
from cbpos.i18n import _t


class CashMovementDialog(QDialog):
    def __init__(self, movement_type="IN", parent=None):
        super().__init__(parent)
        self.movement_type = movement_type
        self.setWindowTitle(_t("cash_movement.title", type=movement_type))
        self.setFixedSize(400, 250)
        self.init_ui()

        self.amount = Decimal("0.00")
        self.reason = ""

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel(_t("cash_movement.record_title", type=self.movement_type))
        title.setProperty("class", "credit" if self.movement_type == "IN" else "debit")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(20)

        # Amount
        lbl_amount = QLabel(_t("cash_movement.amount"))
        self.txt_amount = QLineEdit()
        self.txt_amount.setPlaceholderText("0.00")
        layout.addWidget(lbl_amount)
        layout.addWidget(self.txt_amount)

        # Reason
        lbl_reason = QLabel(_t("cash_movement.reason"))
        self.txt_reason = QLineEdit()
        self.txt_reason.setPlaceholderText(_t("cash_movement.reason_placeholder"))
        layout.addWidget(lbl_reason)
        layout.addWidget(self.txt_reason)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_save = QPushButton(_t("common.save"))
        self.btn_save.clicked.connect(self.validate_and_save)
        self.btn_save.setProperty("class", "accent")
        btn_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton(_t("common.cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def validate_and_save(self):
        amount_text = self.txt_amount.text().strip()
        reason = self.txt_reason.text().strip()

        if not amount_text:
            QMessageBox.warning(self, _t("cash_movement.input_error"), _t("cash_movement.enter_amount"))
            return

        try:
            amount = Decimal(amount_text)
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, _t("cash_movement.input_error"), _t("cash_movement.invalid_amount"))
            return

        if not reason:
            QMessageBox.warning(self, _t("cash_movement.input_error"), _t("cash_movement.enter_reason"))
            return

        self.amount = amount
        self.reason = reason
        self.accept()
