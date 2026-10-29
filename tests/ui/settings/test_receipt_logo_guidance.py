"""
#330: browse_logo() never gave any guidance about what makes a good
thermal logo -- no size guidance, no mention that it will be converted
to black & white dots. A logo that looks fine as a full-color PNG in
the file picker can turn into an unreadable grey blob once converted,
which a shop owner would only discover after wasting real receipt
paper. Add a short hint next to the Logo field.

The hint started as an always-visible 3-line paragraph, which by itself
made the Content tab feel dense next to its handful of actual controls.
Moved to a HelpIconButton tooltip (the same pattern already used
elsewhere on this page) -- same guidance, on hover instead of always on.
The full guidance now lives in the GuideDialog the button opens; the
tooltip is just its short label.
"""

import pytest

from cbpos.i18n import _t
from cbpos.ui.views import settings_pages
from cbpos.ui.views.settings_pages import ReceiptPage

pytestmark = pytest.mark.usefixtures("qapp")


class TestLogoFieldHasGuidance:
    def test_hint_tooltip_exists_and_is_not_empty(self):
        page = ReceiptPage()
        assert page.btn_logo_help.toolTip() != ""

    def test_hint_mentions_black_and_white(self, monkeypatch):
        shown: dict = {}

        class FakeGuide:
            def __init__(self, title_key, steps, note_key, parent=None):
                shown["steps"] = steps

            def exec(self):
                return 0

        monkeypatch.setattr(settings_pages, "GuideDialog", FakeGuide)
        page = ReceiptPage()
        page.btn_logo_help.click()

        details = " ".join(_t(detail) for _, detail in shown["steps"]).lower()
        assert "black" in details
