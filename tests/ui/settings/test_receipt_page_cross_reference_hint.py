"""
#331: copies/auto-print live on the Hardware tab and receipt numbering
format lives on the Documents tab, with no link back from the Receipt
page -- someone tuning header/footer/logo would feel done and never
realize the rest of "receipt customization" is configured elsewhere.
Add a persistent cross-reference note at the top of the Receipt page
(visible regardless of which Content/Display tab is active).
"""

import pytest

from cbpos.ui.views.settings_pages import ReceiptPage

pytestmark = pytest.mark.usefixtures("qapp")


class TestReceiptPageCrossReferencesOtherSettingsPages:
    def test_hint_label_is_not_empty(self):
        page = ReceiptPage()
        assert page._lbl_receipt_cross_ref.text() != ""

    def test_hint_mentions_hardware_for_copies(self):
        page = ReceiptPage()
        assert "Hardware" in page._lbl_receipt_cross_ref.text()

    def test_hint_mentions_documents_for_numbering(self):
        page = ReceiptPage()
        assert "Documents" in page._lbl_receipt_cross_ref.text()

    def test_hint_is_visible_outside_the_tab_widget_so_it_survives_tab_switches(self):
        page = ReceiptPage()
        assert page._lbl_receipt_cross_ref.parent() is not page.tabs
