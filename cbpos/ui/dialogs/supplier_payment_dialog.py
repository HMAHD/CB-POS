"""Dialog to record a payment to a supplier against their outstanding payable."""

from decimal import Decimal, InvalidOperation
from typing import Optional

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
    QFrame,
    QWidget,
)
from PyQt6.QtCore import Qt

from cbpos.core.services.supplier_payable_service import SupplierPayableService
from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.services.auth_service import AuthService
from cbpos.core.utils.formatters import format_currency


class SupplierPaymentDialog(QDialog):
    """Dialog to record a payment made to a supplier."""

    def __init__(self, supplier_id: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.supplier_id = supplier_id
        self.recorded_payment = None

        self.setWindowTitle("Make Payment to Supplier")
        self.setObjectName("SupplierPaymentDialog")
        self.setMinimumSize(450, 380)
        self.resize(500, 420)
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Make Supplier Payment")
        title.setProperty("class", "dialog-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(8)

        # Supplier info
        supplier = SupplierService.get_supplier_by_id(self.supplier_id)
        if supplier:
            name_label = QLabel(f"Supplier: {supplier.company_name}")
            name_label.setProperty("class", "bold")
            layout.addWidget(name_label)

        # Outstanding Balance Display
        self.balance_frame = QFrame()
        self.balance_frame.setObjectName("BalanceFrame")
        balance_layout = QHBoxLayout(self.balance_frame)
        balance_layout.setContentsMargins(12, 8, 12, 8)
        self.lbl_outstanding = QLabel("Outstanding: ---")
        self.lbl_outstanding.setProperty("class", "debit")
        self.lbl_terms = QLabel("Terms: ---")
        self.lbl_terms.setProperty("class", "muted")
        balance_layout.addWidget(self.lbl_outstanding)
        balance_layout.addStretch()
        balance_layout.addWidget(self.lbl_terms)
        layout.addWidget(self.balance_frame)

        # Load supplier summary
        summary = SupplierPayableService.get_supplier_summary(self.supplier_id)
        if summary:
            self.lbl_outstanding.setText(f"Outstanding: {format_currency(summary['current_payable'])}")
            terms = summary["payment_terms"]
            self.lbl_terms.setText(f"Terms: {terms} days" if terms > 0 else "Terms: N/A")
            self._current_payable = summary["current_payable"]
        else:
            self._current_payable = Decimal("0.00")

        # Form Fields
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(0, 4, 0, 4)

        # Amount + Pay Full
        amount_layout = QHBoxLayout()
        self.txt_amount = QLineEdit()
        self.txt_amount.setPlaceholderText("0.00")
        amount_layout.addWidget(self.txt_amount, 1)

        self.btn_pay_full = QPushButton("Pay Full")
        self.btn_pay_full.setProperty("class", "accent")
        self.btn_pay_full.clicked.connect(self.fill_full_amount)
        amount_layout.addWidget(self.btn_pay_full)
        form_layout.addRow("Amount:", amount_layout)

        # Payment Method
        self.cmb_method = QComboBox()
        self.cmb_method.addItems(["Cash", "Card", "Transfer", "Cheque"])
        form_layout.addRow("Method:", self.cmb_method)

        # Reference
        self.txt_reference = QLineEdit()
        self.txt_reference.setPlaceholderText("Cheque #, Transfer ref (optional)")
        form_layout.addRow("Reference:", self.txt_reference)

        # Note
        self.txt_note = QLineEdit()
        self.txt_note.setPlaceholderText("Optional note")
        form_layout.addRow("Note:", self.txt_note)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_record = QPushButton("Record Payment")
        self.btn_record.setProperty("class", "primary")
        self.btn_record.clicked.connect(self.validate_and_record)
        btn_layout.addWidget(self.btn_record)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def fill_full_amount(self) -> None:
        """Fill the amount field with the full outstanding balance."""
        if self._current_payable > 0:
            self.txt_amount.setText(str(self._current_payable))

    def validate_and_record(self) -> None:
        """Validate inputs and record the payment."""
        amount_text = self.txt_amount.text().strip()
        if not amount_text:
            QMessageBox.warning(self, "Input Error", "Please enter an amount.")
            return

        try:
            amount = Decimal(amount_text)
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Input Error", "Invalid amount. Must be a positive number.")
            return

        payment_method = self.cmb_method.currentText()
        reference = self.txt_reference.text().strip() or None
        note = self.txt_note.text().strip() or None

        current_user = AuthService.get_current_user()
        if not current_user:
            QMessageBox.warning(self, "Error", "No user logged in.")
            return

        try:
            payment = SupplierPayableService.record_payment(
                supplier_id=self.supplier_id,
                amount=amount,
                payment_method=payment_method,
                user_id=current_user.id,
                reference=reference,
                note=note,
            )
            self.recorded_payment = payment
            QMessageBox.information(
                self,
                "Payment Recorded",
                f"Payment of {format_currency(amount)} recorded successfully.",
            )
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to record payment: {str(e)}")
