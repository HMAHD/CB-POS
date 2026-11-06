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
    QWidget,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.supplier_payable_service import SupplierPayableService
from cbpos.core.services.supplier_service import SupplierService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


class SupplierPaymentDialog(QDialog):
    """Dialog to record a payment made to a supplier."""

    def __init__(self, supplier_id: int, parent: QWidget | None = None):
        """Build the dialog for recording a payment to the supplier identified by `supplier_id`."""
        super().__init__(parent)
        self.supplier_id = supplier_id
        self.recorded_payment = None

        self.setWindowTitle(_t("supplier_payment.title"))
        self.setObjectName("SupplierPaymentDialog")
        self.setMinimumSize(450, 380)
        self.resize(500, 420)
        self.init_ui()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def init_ui(self) -> None:
        """Build the title, supplier info, payment form, and action buttons."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel(_t("supplier_payment.title"))
        title.setProperty("class", "dialog-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(8)

        # Supplier info
        supplier = SupplierService.get_supplier_by_id(self.supplier_id)
        if supplier:
            name_label = QLabel(_t("supplier_payment.supplier_label", name=supplier.company_name))
            name_label.setProperty("class", "bold")
            layout.addWidget(name_label)

        # Outstanding Balance Display
        self.balance_frame = QFrame()
        self.balance_frame.setObjectName("BalanceFrame")
        balance_layout = QHBoxLayout(self.balance_frame)
        balance_layout.setContentsMargins(12, 8, 12, 8)
        self.lbl_outstanding = QLabel(_t("supplier_payment.outstanding", amount="---"))
        self.lbl_outstanding.setProperty("class", "debit")
        self.lbl_terms = QLabel(_t("supplier_payment.terms", days="---"))
        self.lbl_terms.setProperty("class", "muted")
        balance_layout.addWidget(self.lbl_outstanding)
        balance_layout.addStretch()
        balance_layout.addWidget(self.lbl_terms)
        layout.addWidget(self.balance_frame)

        # Load supplier summary
        summary = SupplierPayableService.get_supplier_summary(self.supplier_id)
        if summary:
            bal = summary["current_payable"]
            if bal < 0:
                self.lbl_outstanding.setText(_t("supplier.credit_balance", amount=format_currency(abs(bal))))
            else:
                self.lbl_outstanding.setText(_t("supplier_payment.outstanding", amount=format_currency(bal)))
            terms = summary["payment_terms"]
            self.lbl_terms.setText(
                _t("supplier_payment.terms", days=str(terms)) if terms > 0 else _t("supplier_payment.terms_na")
            )
            self._current_payable = bal
        else:
            self._current_payable = Decimal("0.00")

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

        self.btn_pay_full = QPushButton(_t("supplier_payment.pay_full"))
        self.btn_pay_full.setProperty("class", "accent")
        self.btn_pay_full.clicked.connect(self.fill_full_amount)
        amount_layout.addWidget(self.btn_pay_full)
        form_layout.addRow(_t("supplier_payment.amount_label"), amount_layout)

        # Payment Method (loaded from DB, excluding Credit)
        self.cmb_method = QComboBox()
        from cbpos.core.constants.status import PaymentMethodType
        from cbpos.core.services.payment_service import PaymentService

        for m in PaymentService.get_active_methods():
            if m.name.upper() != PaymentMethodType.CREDIT.upper():
                self.cmb_method.addItem(m.name)
        form_layout.addRow(_t("supplier_payment.method_label"), self.cmb_method)

        # Reference
        self.txt_reference = QLineEdit()
        self.txt_reference.setPlaceholderText(_t("supplier_payment.reference_placeholder"))
        form_layout.addRow(_t("supplier_payment.reference_label"), self.txt_reference)

        # Note
        self.txt_note = QLineEdit()
        self.txt_note.setPlaceholderText(_t("supplier_payment.note_placeholder"))
        form_layout.addRow(_t("supplier_payment.note_label"), self.txt_note)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_record = QPushButton(_t("supplier_payment.record"))
        self.btn_record.setProperty("class", "primary")
        self.btn_record.clicked.connect(self.validate_and_record)
        btn_layout.addWidget(self.btn_record)

        self.btn_cancel = QPushButton(_t("common.cancel"))
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.setProperty("class", "secondary")
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
            QMessageBox.warning(self, _t("common.error"), _t("supplier_payment.enter_amount"))
            return

        try:
            amount = Decimal(str(amount_text).strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, _t("common.error"), _t("supplier_payment.invalid_amount"))
            return

        payment_method = self.cmb_method.currentText()
        reference = self.txt_reference.text().strip() or None
        note = self.txt_note.text().strip() or None

        current_user = AuthService.get_current_user()
        if not current_user:
            QMessageBox.warning(self, _t("common.error"), _t("supplier_payment.no_user"))
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
                _t("common.success"),
                _t("supplier_payment.recorded_success", amount=format_currency(amount)),
            )
            self.accept()
        except ValueError as e:
            logger.warning("Supplier payment validation error: %s", e)
            QMessageBox.warning(self, _t("common.warning"), translate_error(str(e)))
        except Exception as e:
            logger.exception("Supplier payment record failed: %s", e)
            QMessageBox.critical(
                self, _t("common.error"), _t("supplier_payment.record_failed", error=translate_error(str(e)))
            )
