import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


class ReceivePaymentDialog(QDialog):
    """Dialog to record a customer payment against their outstanding credit debt."""

    def __init__(self, customer_id: int | None = None, parent: object | None = None):
        """Build the dialog, optionally pre-selecting a customer to receive payment from."""
        super().__init__(parent)
        self.customer_service = CustomerService()
        self.selected_customer_id = customer_id
        self.recorded_payment = None

        self.setWindowTitle(_t("receive_payment.title"))
        self.setObjectName("ReceivePaymentDialog")
        self.setMinimumSize(450, 420)
        self.resize(500, 480)
        self.init_ui()

        if customer_id:
            self.load_customer(customer_id)
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def init_ui(self) -> None:
        """Build the customer selector, balance display, payment form, and action buttons."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        self.title_label = QLabel("")
        self.title_label.setProperty("class", "dialog-title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        layout.addSpacing(8)

        # Customer Selector
        customer_layout = QHBoxLayout()
        customer_layout.setSpacing(10)
        self.lbl_customer = QLabel("")
        self.lbl_customer.setProperty("class", "bold")
        self.cmb_customer = QComboBox()
        self.cmb_customer.setMinimumWidth(250)
        customer_layout.addWidget(self.lbl_customer)
        customer_layout.addWidget(self.cmb_customer, 1)
        layout.addLayout(customer_layout)

        # Outstanding Balance Display
        self.balance_frame = QFrame()
        self.balance_frame.setObjectName("BalanceFrame")
        balance_layout = QHBoxLayout(self.balance_frame)
        balance_layout.setContentsMargins(12, 8, 12, 8)
        self.lbl_outstanding = QLabel("")
        self.lbl_outstanding.setProperty("class", "debit")
        self.lbl_limit = QLabel("")
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
        self.txt_amount.setPlaceholderText(_t("receive_payment.amount_placeholder"))
        amount_layout.addWidget(self.txt_amount, 1)

        self.btn_pay_full = QPushButton("")
        self.btn_pay_full.setProperty("class", "accent")
        self.btn_pay_full.clicked.connect(self.fill_full_amount)
        amount_layout.addWidget(self.btn_pay_full)

        form_layout.addRow(_t("receive_payment.amount_label"), amount_layout)

        # Payment Method (loaded from DB, excluding Credit)
        self.cmb_method = QComboBox()
        from cbpos.core.constants.status import PaymentMethodType
        from cbpos.core.services.payment_service import PaymentService

        for m in PaymentService.get_active_methods():
            if m.name.upper() != PaymentMethodType.CREDIT.upper():
                self.cmb_method.addItem(m.name)
        form_layout.addRow(_t("receive_payment.method_label"), self.cmb_method)

        # Reference
        self.txt_reference = QLineEdit()
        self.txt_reference.setPlaceholderText(_t("receive_payment.reference_placeholder"))
        form_layout.addRow(_t("receive_payment.reference_label"), self.txt_reference)

        # Note
        self.txt_note = QLineEdit()
        self.txt_note.setPlaceholderText(_t("receive_payment.note_placeholder"))
        form_layout.addRow(_t("receive_payment.note_label"), self.txt_note)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_record = QPushButton("")
        self.btn_record.setProperty("class", "primary")
        self.btn_record.clicked.connect(self.validate_and_record)
        btn_layout.addWidget(self.btn_record)

        self.btn_cancel = QPushButton("")
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

        # Connect signal and load data AFTER all widgets exist
        self.cmb_customer.currentIndexChanged.connect(self.on_customer_changed)
        self.load_customers_with_debt()

        # Apply translations
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("receive_payment.title"))
        self.title_label.setText(_t("receive_payment.title_alt"))
        self.lbl_customer.setText(_t("receive_payment.customer_label"))
        self.lbl_outstanding.setText(_t("receive_payment.outstanding_default"))
        self.lbl_limit.setText(_t("receive_payment.limit_default"))
        self.btn_pay_full.setText(_t("receive_payment.btn_pay_full"))
        self.btn_record.setText(_t("receive_payment.btn_record"))
        self.btn_cancel.setText(_t("receive_payment.btn_cancel"))

    def load_customers_with_debt(self) -> None:
        """Load all active customers into the combo box."""
        customers = self.customer_service.get_all_customers()
        self.cmb_customer.clear()
        self.cmb_customer.addItem(_t("receive_payment.select_customer"), None)

        for customer in customers:
            debt_str = (
                f" ({_t('receive_payment.debt_label')} {format_currency(customer.current_debt)})"
                if customer.current_debt > 0
                else ""
            )
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
            self.lbl_outstanding.setText(_t("receive_payment.outstanding_default"))
            self.lbl_limit.setText(_t("receive_payment.limit_default"))
            self.selected_customer_id = None
            return

        self.selected_customer_id = customer_id
        summary = CustomerCreditService.get_customer_summary(customer_id)
        if summary:
            self.lbl_outstanding.setText(
                f"{_t('receive_payment.outstanding_label')} {format_currency(summary['current_debt'])}"
            )
            self.lbl_limit.setText(f"{_t('receive_payment.limit_label')} {format_currency(summary['credit_limit'])}")
        else:
            self.lbl_outstanding.setText(_t("receive_payment.outstanding_default"))
            self.lbl_limit.setText(_t("receive_payment.limit_default"))

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
            QMessageBox.warning(
                self, _t("receive_payment.input_error_title"), _t("receive_payment.select_customer_error")
            )
            return

        amount_text = self.txt_amount.text().strip()
        if not amount_text:
            QMessageBox.warning(self, _t("receive_payment.input_error_title"), _t("receive_payment.enter_amount_error"))
            return

        try:
            amount = Decimal(str(amount_text).strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            QMessageBox.warning(
                self, _t("receive_payment.input_error_title"), _t("receive_payment.invalid_amount_error")
            )
            return

        payment_method = self.cmb_method.currentText()
        reference = self.txt_reference.text().strip() or None
        note = self.txt_note.text().strip() or None

        current_user = AuthService.get_current_user()
        if not current_user:
            QMessageBox.warning(self, _t("common.error"), _t("receive_payment.no_user_error"))
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
                _t("receive_payment.success_title"),
                _t(
                    "receive_payment.success_message",
                    amount=format_currency(amount),
                    customer=self.cmb_customer.currentText().split(" (")[0],
                ),
            )
            self.accept()
        except ValueError as e:
            logger.warning("Receive payment validation error: %s", e)
            QMessageBox.warning(self, _t("common.validation_error"), translate_error(str(e)))
        except Exception as e:
            logger.exception("Receive payment record failed: %s", e)
            QMessageBox.critical(
                self, _t("common.error"), _t("receive_payment.record_failed", error=translate_error(str(e)))
            )
