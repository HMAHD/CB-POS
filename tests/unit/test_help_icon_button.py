"""
#318: the Shop Info -> Email tab's SMTP help icon (tooltip + a real
4-step setup guide dialog on click) was a genuinely well-built,
task-specific help affordance -- but it existed exactly once, even
though several other unfamiliar fields across the app (Purchasing's
Payment Terms, Price Lists' date ranges, Sales Tax's own VAT/SSCL
fields) could use the same kind of help. HelpIconButton extracts the
reusable icon+tooltip+optional-guide-dialog part.
"""

from unittest.mock import MagicMock

import pytest

from cbpos.ui.widgets.help_icon_button import HelpIconButton
from cbpos.ui.views.settings_pages import SalesTaxPage, ShopInfoPage

pytestmark = pytest.mark.usefixtures("qapp")


class TestHelpIconButtonBasics:
    def test_tooltip_only_usage_sets_no_click_handler(self):
        btn = HelpIconButton(tooltip="Explains the field")
        assert btn.toolTip() == "Explains the field"

    def test_on_click_callback_fires_when_clicked(self):
        callback = MagicMock()
        btn = HelpIconButton(on_click=callback)
        btn.click()
        callback.assert_called_once()


class TestEmailHelpIconStillWorks:
    def test_btn_help_is_a_help_icon_button(self):
        page = ShopInfoPage()
        assert isinstance(page.btn_help, HelpIconButton)

    def test_clicking_it_still_opens_the_smtp_guide(self, monkeypatch):
        guide_shown = MagicMock()
        monkeypatch.setattr(ShopInfoPage, "_show_smtp_guide", guide_shown)
        page = ShopInfoPage()
        page.btn_help.click()
        guide_shown.assert_called_once()


class TestSalesTaxSsclTurnoverHasHelp:
    def test_help_icon_exists(self):
        page = SalesTaxPage()
        assert isinstance(page.btn_sscl_turnover_help, HelpIconButton)

    def test_help_icon_has_a_tooltip_after_retranslation(self):
        page = SalesTaxPage()
        page.retranslate_ui()
        assert page.btn_sscl_turnover_help.toolTip() != ""
