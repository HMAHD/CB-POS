"""Buyer Details Dialog for issuing official VAT Tax Invoices (#814).

Captures and validates statutory buyer particulars:
- Registered Name (Required)
- Business Address (Required)
- Contact Phone (Optional)
- Taxpayer Identification Number / TIN (Required, validated 9 digits)
"""

import re
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer

_TIN_RE = re.compile(r"^\d{9}$")


class BuyerDetailsDialog(QDialog):
    """Dialog for gathering and validating statutory buyer particulars for a Tax Invoice."""

    def __init__(self, parent=None, initial_data: dict[str, Any] | None = None):
        super().__init__(parent)
        self.buyer_details: dict[str, Any] | None = None
        self._initial_data = initial_data or {}

        self.setWindowTitle(_t("tax_invoice.buyer_details_title"))
        self.setMinimumWidth(440)
        self.setObjectName("BuyerDetailsDialog")
        self.setup_ui()

    def setup_ui(self) -> None:
        """Build form inputs, labels, error banner, and action footer."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header description
        desc_label = QLabel(_t("tax_invoice.buyer_details_desc"))
        desc_label.setWordWrap(True)
        desc_label.setObjectName("dialogHelperText")
        layout.addWidget(desc_label)

        # Form fields
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setText(str(self._initial_data.get("name") or ""))

        self.address_input = QLineEdit()
        self.address_input.setText(str(self._initial_data.get("address") or ""))

        self.phone_input = QLineEdit()
        self.phone_input.setText(str(self._initial_data.get("phone") or ""))

        self.tin_input = QLineEdit()
        self.tin_input.setMaxLength(9)
        self.tin_input.setPlaceholderText("123456789")
        self.tin_input.setText(str(self._initial_data.get("tin") or ""))

        form.addRow(_t("tax_invoice.buyer_name_label") + " *", self.name_input)
        form.addRow(_t("tax_invoice.buyer_address_label") + " *", self.address_input)
        form.addRow(_t("tax_invoice.buyer_phone_label"), self.phone_input)
        form.addRow(_t("tax_invoice.buyer_tin_label") + " *", self.tin_input)

        layout.addLayout(form)

        # Inline error display
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #DC3545; font-size: 11px;")
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        # Footer
        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.confirm",
            on_primary=self.validate_and_accept,
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)

        # Set focus
        if not self.name_input.text():
            self.name_input.setFocus()
        elif not self.tin_input.text():
            self.tin_input.setFocus()
        else:
            self.btn_save.setFocus()

    def validate_and_accept(self) -> None:
        """Validate input fields and accept dialog if valid."""
        name = self.name_input.text().strip()
        address = self.address_input.text().strip()
        phone = self.phone_input.text().strip()
        tin = self.tin_input.text().strip()

        if not name:
            self._show_error(_t("tax_invoice.buyer_name_required"))
            self.name_input.setFocus()
            return

        if not address:
            self._show_error(_t("tax_invoice.buyer_address_required"))
            self.address_input.setFocus()
            return

        if not tin:
            self._show_error(_t("tax_invoice.tin_required"))
            self.tin_input.setFocus()
            return

        if not _TIN_RE.match(tin):
            self._show_error(_t("tax_invoice.tin_required_9_digits"))
            self.tin_input.setFocus()
            return

        self.error_label.setVisible(False)
        self.buyer_details = {
            "name": name,
            "address": address,
            "phone": phone or None,
            "tin": tin,
        }
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)

    def get_buyer_details(self) -> dict[str, Any] | None:
        """Return statutory buyer particulars captured by the dialog, or None if rejected."""
        return self.buyer_details
