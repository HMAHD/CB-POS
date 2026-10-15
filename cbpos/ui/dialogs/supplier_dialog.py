"""Modal dialog for creating or editing a supplier."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.i18n import _t


class SupplierDialog(QDialog):
    """Modal dialog for creating or editing a supplier."""

    def __init__(self, parent=None, supplier=None):
        """Store the supplier being edited (None for a new supplier) and build the form."""
        super().__init__(parent)
        self.supplier = supplier
        self.init_ui()
        self.retranslate_ui()

    def init_ui(self):
        """Build the supplier form fields and Save/Cancel buttons."""
        self.setObjectName("SupplierDialog")
        self.setMinimumSize(420, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.form_layout = QFormLayout()
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form_layout.setSpacing(10)

        self.company_input = QLineEdit()
        self.contact_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.tax_input = QLineEdit()
        self.details_input = QLineEdit()

        # QLineEdit + validator instead of QSpinBox -- native +/- steppers
        # break under QSS (see product_editor.py's Stock group comment).
        self.payment_terms_input = QLineEdit()
        self.payment_terms_input.setPlaceholderText("0")
        self.payment_terms_input.setValidator(QIntValidator(0, 365, self))

        if self.supplier:
            self.company_input.setText(self.supplier.company_name)
            self.contact_input.setText(self.supplier.contact_person or "")
            self.phone_input.setText(self.supplier.phone or "")
            self.tax_input.setText(self.supplier.tax_number or "")
            self.details_input.setText(self.supplier.contact_details or "")
            self.payment_terms_input.setText(str(getattr(self.supplier, "payment_terms", 0)))

        self.lbl_company = QLabel()
        self.lbl_contact = QLabel()
        self.lbl_phone = QLabel()
        self.lbl_tax = QLabel()
        self.lbl_terms = QLabel()
        self.lbl_details = QLabel()

        self.form_layout.addRow(self.lbl_company, self.company_input)
        self.form_layout.addRow(self.lbl_contact, self.contact_input)
        self.form_layout.addRow(self.lbl_phone, self.phone_input)
        self.form_layout.addRow(self.lbl_tax, self.tax_input)
        self.form_layout.addRow(self.lbl_terms, self.payment_terms_input)
        self.form_layout.addRow(self.lbl_details, self.details_input)

        layout.addLayout(self.form_layout)
        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.save_btn = QPushButton()
        self.save_btn.setObjectName("BtnSave")
        self.save_btn.clicked.connect(self.save)
        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("BtnCancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(self.save_btn)
        btn_box.addWidget(self.cancel_btn)
        layout.addLayout(btn_box)

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        if self.supplier:
            self.setWindowTitle(_t("purchase.edit_supplier_title"))
        else:
            self.setWindowTitle(_t("purchase.add_supplier_title"))
        self.lbl_company.setText(_t("purchase.supplier_dialog_company"))
        self.lbl_contact.setText(_t("purchase.supplier_dialog_contact"))
        self.lbl_phone.setText(_t("purchase.supplier_dialog_phone"))
        self.lbl_tax.setText(_t("purchase.supplier_dialog_tax"))
        self.lbl_terms.setText(_t("purchase.supplier_dialog_terms"))
        self.lbl_details.setText(_t("purchase.supplier_dialog_details"))
        self.save_btn.setText(_t("common.save"))
        self.cancel_btn.setText(_t("common.cancel"))

    def save(self) -> None:
        """Validate required fields before accepting -- an empty company name
        would otherwise reach SupplierService and raise there instead of
        giving the cashier immediate, in-dialog feedback (#522)."""
        if not self.company_input.text().strip():
            QMessageBox.warning(self, _t("common.validation_error"), _t("purchase.supplier_name_required"))
            self.company_input.setFocus()
            return
        self.accept()

    def get_data(self):
        """Return the entered supplier field values as a dict."""
        return {
            "company_name": self.company_input.text().strip(),
            "contact_person": self.contact_input.text().strip(),
            "phone": self.phone_input.text().strip(),
            "tax_number": self.tax_input.text().strip(),
            "contact_details": self.details_input.text().strip(),
            "payment_terms": self._parse_payment_terms(self.payment_terms_input.text()),
        }

    @staticmethod
    def _parse_payment_terms(text: str) -> int:
        """Safely parse the Payment Terms QLineEdit value to int."""
        cleaned = text.strip()
        if not cleaned:
            return 0
        try:
            return int(cleaned)
        except ValueError:
            return 0
