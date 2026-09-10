"""
#330: browse_logo() never gave any guidance about what makes a good
thermal logo -- no size guidance, no mention that it will be converted
to black & white dots. A logo that looks fine as a full-color PNG in
the file picker can turn into an unreadable grey blob once converted,
which a shop owner would only discover after wasting real receipt
paper. Add a short hint next to the Logo field.
"""

import pytest

from cbpos.ui.views.settings_pages import ReceiptPage

pytestmark = pytest.mark.usefixtures("qapp")


class TestLogoFieldHasGuidance:
    def test_hint_label_exists_and_is_not_empty(self):
        page = ReceiptPage()
        assert page._lbl_logo_hint.text() != ""

    def test_hint_mentions_black_and_white(self):
        page = ReceiptPage()
        assert "black" in page._lbl_logo_hint.text().lower()
