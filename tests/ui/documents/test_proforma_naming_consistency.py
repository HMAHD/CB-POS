"""
One feature had four different names: a "+ New Quotation" button opened a
dialog titled "Proforma Invoice", with a "Create Proforma" confirm button,
that on success reported "Quotation <doc_number> created successfully."
in a raw hardcoded English string. The data layer (ProformaService, the
"PROFORMA" document-number prefix) already committed to "Proforma"
throughout, so the trigger button and success message were the stray
inconsistencies -- both are now "Proforma" everywhere, and the success
message goes through the i18n system instead of being hardcoded.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.i18n import _t
from cbpos.ui.dialogs.proforma_dialog import ProformaDialog
from cbpos.ui.views.document_view import DocumentBrowserView

pytestmark = pytest.mark.usefixtures("qapp")


class TestTriggerButtonSaysProforma:
    def test_new_proforma_button_text_says_proforma_not_quotation(self, db_session):
        view = DocumentBrowserView()
        text = view.new_proforma_btn.text()
        assert "proforma" in text.lower()
        assert "quotation" not in text.lower()

    def test_btn_new_proforma_i18n_key_resolves_to_real_text_not_the_raw_key(self):
        # _t() falls back to returning the raw key string when a key is
        # missing -- resolving to something else is what proves the key
        # actually exists, rather than this assertion passing by accident.
        resolved = _t("document_browser.btn_new_proforma")
        assert resolved != "document_browser.btn_new_proforma"
        assert "quotation" not in resolved.lower()


class TestSuccessMessageSaysProforma:
    def test_success_message_names_proforma_not_quotation(self, db_session):
        dialog = ProformaDialog()
        dialog.items = [
            {
                "product_id": 1,
                "name": "Test Product",
                "quantity": Decimal("1"),
                "unit_price": Decimal("100.00"),
                "line_total": Decimal("100.00"),
            }
        ]

        fake_proforma = MagicMock()
        fake_proforma.document_number = "PROFORMA-0001"

        with patch("cbpos.ui.dialogs.proforma_dialog.ProformaService.create_proforma", return_value=fake_proforma):
            with patch("cbpos.ui.dialogs.proforma_dialog.QMessageBox.information") as mock_info:
                dialog.create_proforma()

        mock_info.assert_called_once()
        _self, _title, message = mock_info.call_args[0]
        assert "proforma" in message.lower()
        assert "quotation" not in message.lower()
        assert "PROFORMA-0001" in message
