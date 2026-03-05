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
)
from PyQt6.QtCore import Qt
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.auth_service import AuthService
from cbpos.core.utils.formatters import format_currency


class ReceivePaymentDialog(QDialog):
    """Dialog to record a customer payment against their outstanding credit debt."""

    def __init__(self, customer_id: Optional[int] = None, parent: Optional[object] = None):
        super().__init__(parent)
        self.customer_service = CustomerService()
        self.selected_customer_id = customer_id
        self.recorded_payment = None

        self.setWindowTitle("Receive Payment")
        self.setObjectName("ReceivePaymentDialog")
        self.setMinimumSize(450, 420)
        self.resize(500, 480)
        self.init_ui()

        if customer_id:
            self.load_customer(customer_id)

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Receive Customer Payment")
        title.setProperty("class", "dialog-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(8)

        # Customer Selector
        customer_layout = QHBoxLayout()
        customer_layout.setSpacing(10)
        lbl_customer = QLabel("Customer:")
        lbl_customer.setProperty("class", "bold")
        self.cmb_customer = QComboBox()
        self.cmb_customer.setMinimumWidth(250)
        customer_layout.addWidget(lbl_customer)
        customer_layout.addWidget(self.cmb_customer, 1)
        layout.addLayout(customer_layout)

        # Outstanding Balance Display
        self.balance_frame = QFrame()
        self.balance_frame.setObjectName("BalanceFrame")
        balance_layout = QHBoxLayout(self.balance_frame)
        balance_layout.setContentsMargins(12, 8, 12, 8)
        self.lbl_outstanding = QLabel("Outstanding: ---")
        self.lbl_outstanding.setProperty("class", "debit")
        self.lbl_limit = QLabel("Limit: ---")
        self.lbl_limit.setProperty("class", "muted")
        balance_layout.addWidget(self.lbl_outstanding)
        balance_layout.addStretch()
        balance_layout.addWidget(self.lbl_limit)
        layout.addWidget(self.balance_frame)

        # Form Fields
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
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

        # Payment Method (loaded from DB, excluding Credit)
        self.cmb_method = QComboBox()
        from cbpos.core.services.payment_service import PaymentService
        from cbpos.core.constants.status import PaymentMethodType

        for m in PaymentService.get_active_methods():
            if m.name.upper() != PaymentMethodType.CREDIT.upper():
                self.cmb_method.addItem(m.name)
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

        # Connect signal and load data AFTER all widgets exist
        self.cmb_customer.currentIndexChanged.connect(self.on_customer_changed)
        self.load_customers_with_debt()

    def load_customers_with_debt(self) -> None:
        """Load all active customers into the combo box."""
        customers = self.customer_service.get_all_customers()
        self.cmb_customer.clear()
        self.cmb_customer.addItem("-- Select Customer --", None)

        for customer in customers:
            debt_str = f" (Debt: {format_currency(customer.current_debt)})" if customer.current_debt > 0 else ""
            self.cmb_customer.addItem(f"{customer.name}{debt_str}", customer.id)

    def load_customer(self, customer_id: int) -> None:
        """Pre-select a customer in the combo box."""
        for i in range(self.cmb_customer.count()):
            if self.cmb_customer.itemData(i) == customer_id:
                self.cmb_customer.setCurrentIndex(i)
                break

    def on_customer_changed(self, index: int) -> None:
        """Update balance display when customer selection changes."""
        customer_id = self.cmb_customer.currentData()
        if not customer_id:
            self.lbl_outstanding.setText("Outstanding: ---")
            self.lbl_limit.setText("Limit: ---")
            self.selected_customer_id = None
            return

        self.selected_customer_id = customer_id
        summary = CustomerCreditService.get_customer_summary(customer_id)
        if summary:
            self.lbl_outstanding.setText(f"Outstanding: {format_currency(summary['current_debt'])}")
            self.lbl_limit.setText(f"Limit: {format_currency(summary['credit_limit'])}")
        else:
            self.lbl_outstanding.setText("Outstanding: ---")
            self.lbl_limit.setText("Limit: ---")

    def fill_full_amount(self) -> None:
        """Fill the amount field with the full outstanding balance."""
        if not self.selected_customer_id:
            return
        summary = CustomerCreditService.get_customer_summary(self.selected_customer_id)
        if summary and summary["current_debt"] > 0:
            self.txt_amount.setText(str(summary["current_debt"]))

    def validate_and_record(self) -> None:
        """Validate inputs and record the payment."""
        if not self.selected_customer_id:
            QMessageBox.warning(self, "Input Error", "Please select a customer.")
            return

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
            payment = CustomerCreditService.record_payment(
                customer_id=self.selected_customer_id,
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
