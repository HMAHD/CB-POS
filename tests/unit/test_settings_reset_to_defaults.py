"""
#425: no UI path existed to reset settings.json back to defaults -- the
only recovery for a shop owner who misconfigured something was manually
deleting the file from AppData, unrealistic for the target audience
(self-install, no IT department). Adds a per-section "Reset to Defaults"
button to every settings page, scoped to only that page's own keys.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.services.config_service import ConfigService
from cbpos.ui.views.settings_pages import (
    DocumentPage,
    HardwarePage,
    NetworkPage,
    ReceiptPage,
    SalesTaxPage,
    ShopInfoPage,
    SystemPage,
)

pytestmark = pytest.mark.usefixtures("qapp")

ALL_PAGES = [ShopInfoPage, SalesTaxPage, DocumentPage, HardwarePage, ReceiptPage, SystemPage, NetworkPage]


@pytest.mark.parametrize("page_cls", ALL_PAGES, ids=lambda c: c.__name__)
def test_every_page_has_a_translated_reset_button(page_cls, db_session):
    page = page_cls()
    assert hasattr(page, "btn_reset_defaults")
    assert page.btn_reset_defaults.text() != ""


class TestResetToDefaults:
    def test_resets_the_widget_and_persists_the_default_value(self, db_session):
        ConfigService.set("shop_name", "Modified Shop Name")
        page = ShopInfoPage()
        page.load(ConfigService.get_all())
        assert page.input_shop_name.text() == "Modified Shop Name"

        with (
            patch("cbpos.ui.views.settings_pages.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes),
            patch("cbpos.ui.views.settings_pages.QMessageBox.information"),
        ):
            page._reset_to_defaults()

        assert page.input_shop_name.text() == ConfigService.DEFAULTS["shop_name"]
        assert ConfigService.get("shop_name") == ConfigService.DEFAULTS["shop_name"]

    def test_declining_the_confirmation_changes_nothing(self, db_session):
        ConfigService.set("shop_name", "Modified Shop Name")
        page = ShopInfoPage()
        page.load(ConfigService.get_all())

        with patch("cbpos.ui.views.settings_pages.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            page._reset_to_defaults()

        assert page.input_shop_name.text() == "Modified Shop Name"
        assert ConfigService.get("shop_name") == "Modified Shop Name"

    def test_reset_is_scoped_to_this_pages_own_keys_only(self, db_session):
        ConfigService.set("shop_name", "Modified Shop Name")
        ConfigService.set("tax_vat_rate", 25.0)
        page = ShopInfoPage()
        page.load(ConfigService.get_all())

        with (
            patch("cbpos.ui.views.settings_pages.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes),
            patch("cbpos.ui.views.settings_pages.QMessageBox.information"),
        ):
            page._reset_to_defaults()

        assert ConfigService.get("shop_name") == ConfigService.DEFAULTS["shop_name"]
        assert ConfigService.get("tax_vat_rate") == 25.0
