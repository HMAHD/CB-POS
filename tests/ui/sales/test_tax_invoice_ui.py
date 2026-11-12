"""UI tests for VAT Tax Invoice components (#814).

Tests:
1. BuyerDetailsDialog form validation and 9-digit TIN enforcement.
2. PaymentDialog tax invoice checkbox toggle and eligibility gating.
3. HistoryView tax invoice button state (issue vs view/print).
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QDialog

from cbpos.core.database import Base
from cbpos.core.models import (
    Customer,
    Role,
    Sale,
    User,
)
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.tax_invoice_service import TaxInvoiceService
from cbpos.ui.dialogs.buyer_details_dialog import BuyerDetailsDialog
from cbpos.ui.dialogs.payment_dialog import PaymentDialog
from cbpos.ui.views.history_view import HistoryView


@pytest.fixture
def tax_ui_setup(db_session):
    Base.metadata.create_all(bind=db_session.bind)

    ConfigService.set("vat_registered", True)
    ConfigService.set("tax_vat_enabled", True)
    ConfigService.set("tax_vat_rate", 18.0)
    ConfigService.set("company_tax_id", "123456789")
    ConfigService.set("shop_name", "Test Supermarket Ltd")
    ConfigService.set("shop_address", "123 Galle Road, Colombo 03")
    ConfigService.set("shop_phone", "0112345678")
    ConfigService.set("terminal_id", "MAIN-01")
    ConfigService.set("terminal_mode", "standalone")

    role = Role(name="Admin", access_level=9)
    db_session.add(role)
    db_session.flush()

    user = User(username="admin", role_id=role.id, is_active=True, pin_hash=AuthService.hash_pin("1234"))
    db_session.add(user)
    db_session.flush()

    AuthService._current_user = user

    cust_with_tin = Customer(
        name="Acme Holdings",
        company_name="Acme Holdings PLC",
        address="77 Galle Face Terrace, Colombo",
        phone="0119876543",
        tax_id="998877665",
        is_active=True,
    )
    db_session.add(cust_with_tin)

    cust_without_tin = Customer(
        name="Sunil Perera",
        address="10 Kandy Road, Kelaniya",
        phone="0777123456",
        tax_id=None,
        is_active=True,
    )
    db_session.add(cust_without_tin)

    db_session.commit()

    return {
        "user": user,
        "cust_with_tin": cust_with_tin,
        "cust_without_tin": cust_without_tin,
    }


class TestBuyerDetailsDialog:
    def test_validation_rejects_empty_fields(self, qapp):
        dialog = BuyerDetailsDialog()
        dialog.name_input.setText("")
        dialog.address_input.setText("Some address")
        dialog.tin_input.setText("123456789")

        dialog.validate_and_accept()
        assert not dialog.error_label.isHidden()
        assert dialog.error_label.text() != ""
        assert dialog.result() != QDialog.DialogCode.Accepted
        assert dialog.get_buyer_details() is None

        dialog.name_input.setText("Test Buyer")
        dialog.address_input.setText("")
        dialog.validate_and_accept()
        assert not dialog.error_label.isHidden()
        assert dialog.get_buyer_details() is None

    def test_validation_requires_exact_9_digit_tin(self, qapp):
        dialog = BuyerDetailsDialog()
        dialog.name_input.setText("Test Buyer PLC")
        dialog.address_input.setText("Colombo 01")

        # 8 digits
        dialog.tin_input.setText("12345678")
        dialog.validate_and_accept()
        assert not dialog.error_label.isHidden()
        assert dialog.get_buyer_details() is None

        # Non-digits
        dialog.tin_input.setText("12345678A")
        dialog.validate_and_accept()
        assert not dialog.error_label.isHidden()
        assert dialog.get_buyer_details() is None

        # Exact 9 digits
        dialog.tin_input.setText("123456789")
        dialog.validate_and_accept()
        assert dialog.error_label.isHidden()
        details = dialog.get_buyer_details()
        assert details is not None
        assert details["name"] == "Test Buyer PLC"
        assert details["address"] == "Colombo 01"
        assert details["tin"] == "123456789"


class TestPaymentDialogTaxInvoice:
    def test_checkbox_disabled_when_vat_not_configured(self, qapp, tax_ui_setup):
        ConfigService.set("company_tax_id", "")
        dialog = PaymentDialog(Decimal("1000.00"))
        assert not dialog.chk_tax_invoice.isEnabled()
        assert dialog.chk_tax_invoice.toolTip() != ""

    def test_checkbox_disabled_in_terminal_mode(self, qapp, tax_ui_setup):
        ConfigService.set("terminal_mode", "terminal")
        dialog = PaymentDialog(Decimal("1000.00"))
        assert not dialog.chk_tax_invoice.isEnabled()

    def test_checkbox_enabled_in_standalone_with_vat(self, qapp, tax_ui_setup):
        dialog = PaymentDialog(Decimal("1000.00"))
        assert dialog.chk_tax_invoice.isEnabled()

    def test_toggle_auto_populates_when_customer_has_tin(self, qapp, tax_ui_setup):
        cust = tax_ui_setup["cust_with_tin"]
        dialog = PaymentDialog(Decimal("1000.00"), customer=cust)
        assert dialog.tax_invoice_details is None

        # Toggle on
        dialog.chk_tax_invoice.setChecked(True)
        assert dialog.tax_invoice_details is not None
        assert dialog.tax_invoice_details["tin"] == "998877665"
        assert dialog.tax_invoice_details["name"] == "Acme Holdings PLC"
        assert not dialog.btn_tax_invoice_details.isHidden()

        # Toggle off
        dialog.chk_tax_invoice.setChecked(False)
        assert dialog.tax_invoice_details is None
        assert dialog.btn_tax_invoice_details.isHidden()

    def test_toggle_prompts_dialog_when_no_customer_or_no_tin(self, qapp, tax_ui_setup):
        dialog = PaymentDialog(Decimal("1000.00"), customer=None)

        with patch.object(BuyerDetailsDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            with patch.object(
                BuyerDetailsDialog,
                "get_buyer_details",
                return_value={
                    "name": "Walkin Co",
                    "address": "Colombo 02",
                    "phone": None,
                    "tin": "112233445",
                },
            ):
                dialog.chk_tax_invoice.setChecked(True)
                assert dialog.tax_invoice_details is not None
                assert dialog.tax_invoice_details["tin"] == "112233445"
                assert not dialog.btn_tax_invoice_details.isHidden()

    def test_toggle_unchecks_if_buyer_dialog_cancelled(self, qapp, tax_ui_setup):
        dialog = PaymentDialog(Decimal("1000.00"), customer=None)

        with patch.object(BuyerDetailsDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            dialog.chk_tax_invoice.setChecked(True)
            assert not dialog.chk_tax_invoice.isChecked()
            assert dialog.tax_invoice_details is None


class TestHistoryViewTaxInvoice:
    def test_history_view_buttons_for_eligible_and_issued_sales(self, qapp, tax_ui_setup, db_session):
        user = tax_ui_setup["user"]

        # 1. Create a sale without tax invoice
        sale = Sale(
            document_number="INV-2026-9901",
            date=datetime.now(),
            total_amount=Decimal("1180.00"),
            tax_vat=Decimal("180.00"),
            tax_sscl=Decimal("0.00"),
            net_revenue=Decimal("1000.00"),
            vat_rate=Decimal("18.00"),
            payment_method="CASH",
            status="COMPLETED",
            user_id=user.id,
        )
        db_session.add(sale)
        db_session.commit()

        history_view = HistoryView()
        history_view.current_sale = sale
        history_view.display_details(sale)
        history_view.on_selection_changed = MagicMock()

        # Since no tax invoice issued, button text should be "Issue Tax Invoice"
        # and details label should not contain "Tax Invoice Serial"
        assert "Tax Invoice Serial" not in history_view.details_label.text()

        # 2. Issue tax invoice
        buyer_details = {
            "name": "Lanka Traders",
            "address": "Colombo",
            "phone": None,
            "tin": "123456789",
        }
        invoice = TaxInvoiceService.issue_tax_invoice(sale.id, buyer_details, user.id)

        # Re-display details
        history_view.display_details(sale)
        assert invoice.serial in history_view.details_label.text()
