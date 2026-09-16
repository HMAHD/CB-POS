"""
#318: the Shop Info -> Email tab's SMTP help icon (tooltip + a real
4-step setup guide dialog on click) was a genuinely well-built,
task-specific help affordance -- but it existed exactly once, even
though several other unfamiliar fields across the app (Purchasing's
Payment Terms, Price Lists' date ranges, Sales Tax's own VAT/SSCL
fields) could use the same kind of help. HelpIconButton extracts the
reusable icon+tooltip+optional-guide-dialog part.

A tooltip-only button appeared to do nothing when tapped, since Qt only
shows a hover tooltip on mouse-over -- which never happens on a
touchscreen POS terminal (tapping is the only gesture available there).
Clicking a tooltip-only HelpIconButton now shows the same tooltip text
via QToolTip directly.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QToolTip

from cbpos.ui.views.settings_pages import SalesTaxPage, ShopInfoPage
from cbpos.ui.widgets.help_icon_button import HelpIconButton

pytestmark = pytest.mark.usefixtures("qapp")


class TestHelpIconButtonBasics:
    def test_tooltip_only_usage_has_no_extra_click_side_effect(self):
        btn = HelpIconButton(tooltip="Explains the field")
        assert btn.toolTip() == "Explains the field"

    def test_clicking_a_tooltip_only_button_shows_the_tooltip(self):
        btn = HelpIconButton(tooltip="Explains the field")
        btn.show()

        btn.click()

        assert QToolTip.isVisible()
        assert QToolTip.text() == "Explains the field"

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
