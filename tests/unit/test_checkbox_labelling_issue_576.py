"""
Tests for Issue #576 [UI-018-B]:
Adopt one checkbox labelling rule (remove title + description double labels)
and keep checkboxes aligned in the field column.
"""

import pytest
from PyQt6.QtWidgets import QFormLayout

from cbpos.ui.views.payment_methods_view import PaymentMethodDialog
from cbpos.ui.views.settings_pages import HardwarePage, ReceiptPage, SystemPage

pytestmark = pytest.mark.usefixtures("qapp")


def _get_form_label_text(widget) -> str | None:
    """Helper to inspect the left label text for a given field widget in a QFormLayout."""
    parent = widget.parentWidget()
    if not parent:
        return None
    for form in parent.findChildren(QFormLayout):
        label_item = form.labelForField(widget)
        if label_item is not None:
            label_widget = label_item.widget()
            return label_widget.text() if label_widget else None
    return None


class TestPaymentMethodDialogCheckboxes:
    def test_payment_method_checkboxes_have_no_double_labels(self, db_session):
        dialog = PaymentMethodDialog()
        # Label in the left column must be empty string / None
        assert _get_form_label_text(dialog.chk_cash) in ("", None)
        assert _get_form_label_text(dialog.chk_drawer) in ("", None)

        # Checkbox widgets themselves hold the descriptive text
        assert len(dialog.chk_cash.text()) > 0
        assert len(dialog.chk_drawer.text()) > 0


class TestHardwarePageCheckboxes:
    def test_hardware_page_checkboxes_have_no_double_labels(self, db_session):
        page = HardwarePage()
        assert _get_form_label_text(page.chk_auto_print) in ("", None)
        assert len(page.chk_auto_print.text()) > 0

        assert _get_form_label_text(page.chk_auto_cut) in ("", None)
        assert len(page.chk_auto_cut.text()) > 0

        assert _get_form_label_text(page.chk_drawer_cash_only) in ("", None)
        assert len(page.chk_drawer_cash_only.text()) > 0


class TestSystemPageCheckboxes:
    def test_system_page_checkboxes_have_single_labels(self, db_session):
        page = SystemPage()
        for chk in (
            page.chk_void_reason,
            page.chk_quick_pay,
            page.chk_show_receipt_dialog,
            page.chk_auto_barcode_select,
            page.chk_enable_sounds,
            page.chk_negative_stock,
            page.chk_auto_barcodes,
            page.chk_loyalty,
            page.chk_auto_backup,
        ):
            assert _get_form_label_text(chk) in ("", None)
            assert len(chk.text()) > 0


class TestReceiptPageCheckboxes:
    def test_receipt_display_checkboxes_have_no_double_labels(self, db_session):
        page = ReceiptPage()
        for chk in (
            page.chk_show_barcode,
            page.chk_merge_items,
            page.chk_show_tax,
            page.chk_show_qr,
            page.chk_show_cashier,
            page.chk_show_terminal,
        ):
            assert _get_form_label_text(chk) in ("", None)
            assert len(chk.text()) > 0
