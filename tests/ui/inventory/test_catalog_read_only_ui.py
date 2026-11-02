"""UI tests for catalog read-only behavior on till terminals (#869)."""

import pytest

from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t
from cbpos.ui.views.inventory_view import InventoryView
from cbpos.ui.views.payment_methods_view import PaymentMethodsView
from cbpos.ui.views.pricelist_view import PriceListView
from cbpos.ui.views.promotion_view import PromotionView
from cbpos.ui.views.purchase_view import PurchaseView
from cbpos.ui.views.user_view import UserView

pytestmark = pytest.mark.usefixtures("qapp")


def test_inventory_view_read_only_in_terminal_mode(db_session, monkeypatch):
    """InventoryView shows read-only banner and disables mutating buttons on a till."""
    ConfigService.set("terminal_mode", "terminal")
    view = InventoryView()
    view.show()
    try:
        assert view.read_only_banner.isHidden() is False
        assert view.read_only_banner.isVisible() is True
        assert view.add_btn.isEnabled() is False
        assert view.import_btn.isEnabled() is False
        assert view.cat_btn.isEnabled() is False
        assert view.unit_btn.isEnabled() is False
        assert view.add_btn.toolTip() == _t("catalog.read_only_tooltip")

        # Switch to standalone
        ConfigService.set("terminal_mode", "standalone")
        view.on_activated()
        assert view.read_only_banner.isHidden() is True
        assert view.add_btn.isEnabled() is True
        assert view.import_btn.isEnabled() is True
        assert view.cat_btn.isEnabled() is True
        assert view.unit_btn.isEnabled() is True
    finally:
        ConfigService.set("terminal_mode", "standalone")
        view.close()
        view.deleteLater()


def test_user_view_read_only_in_terminal_mode(db_session, monkeypatch):
    """UserView shows read-only banner and disables add/permissions/roles on a till."""
    ConfigService.set("terminal_mode", "terminal")
    view = UserView()
    view.show()
    try:
        assert view.read_only_banner.isHidden() is False
        assert view.btn_add.isEnabled() is False
        assert view.btn_perms.isEnabled() is False
        assert view.btn_roles.isEnabled() is False
        assert view.btn_add.toolTip() == _t("catalog.read_only_tooltip")

        # Switch to standalone
        ConfigService.set("terminal_mode", "standalone")
        view.on_activated()
        assert view.read_only_banner.isHidden() is True
        assert view.btn_add.isEnabled() is True
        assert view.btn_perms.isEnabled() is True
        assert view.btn_roles.isEnabled() is True
    finally:
        ConfigService.set("terminal_mode", "standalone")
        view.close()
        view.deleteLater()


def test_promotion_view_read_only_in_terminal_mode(db_session, monkeypatch):
    """PromotionView shows read-only banner and disables add on a till."""
    ConfigService.set("terminal_mode", "terminal")
    view = PromotionView()
    view.show()
    try:
        assert view.read_only_banner.isHidden() is False
        assert view.btn_add.isEnabled() is False
        assert view.btn_add.toolTip() == _t("catalog.read_only_tooltip")

        # Switch to standalone
        ConfigService.set("terminal_mode", "standalone")
        view.on_activated()
        assert view.read_only_banner.isHidden() is True
        assert view.btn_add.isEnabled() is True
    finally:
        ConfigService.set("terminal_mode", "standalone")
        view.close()
        view.deleteLater()


def test_pricelist_view_read_only_in_terminal_mode(db_session, monkeypatch):
    """PriceListView shows read-only banner and disables list and item edits on a till."""
    ConfigService.set("terminal_mode", "terminal")
    view = PriceListView()
    view.show()
    try:
        assert view.read_only_banner.isHidden() is False
        assert view.btn_add.isEnabled() is False
        assert view.btn_edit.isEnabled() is False
        assert view.btn_delete.isEnabled() is False
        assert view.btn_bulk_adjust.isEnabled() is False
        assert view.btn_set_item_price.isEnabled() is False
        assert view.btn_remove_override.isEnabled() is False
        assert view.btn_add.toolTip() == _t("catalog.read_only_tooltip")

        # Switch to standalone
        ConfigService.set("terminal_mode", "standalone")
        view.on_activated()
        assert view.read_only_banner.isHidden() is True
        assert view.btn_add.isEnabled() is True
        assert view.btn_edit.isEnabled() is True
        assert view.btn_delete.isEnabled() is True
        assert view.btn_bulk_adjust.isEnabled() is True
        assert view.btn_set_item_price.isEnabled() is True
    finally:
        ConfigService.set("terminal_mode", "standalone")
        view.close()
        view.deleteLater()


def test_payment_methods_view_read_only_in_terminal_mode(db_session, monkeypatch):
    """PaymentMethodsView shows read-only banner and disables add on a till."""
    ConfigService.set("terminal_mode", "terminal")
    view = PaymentMethodsView()
    view.show()
    try:
        assert view.read_only_banner.isHidden() is False
        assert view.btn_add.isEnabled() is False
        assert view.btn_add.toolTip() == _t("catalog.read_only_tooltip")

        # Switch to standalone
        ConfigService.set("terminal_mode", "standalone")
        view.showEvent(None)
        assert view.read_only_banner.isHidden() is True
        assert view.btn_add.isEnabled() is True
    finally:
        ConfigService.set("terminal_mode", "standalone")
        view.close()
        view.deleteLater()


def test_purchase_view_supplier_tab_read_only_in_terminal_mode(db_session, monkeypatch):
    """PurchaseView supplier tab shows read-only banner and disables supplier edits on a till."""
    ConfigService.set("terminal_mode", "terminal")
    view = PurchaseView()
    view.show()
    try:
        assert view.supplier_read_only_banner.isHidden() is False
        assert view.btn_add_supplier.isEnabled() is False
        assert view.btn_edit_supplier.isEnabled() is False
        assert view.btn_deactivate_supplier.isEnabled() is False
        assert view.btn_add_supplier.toolTip() == _t("catalog.read_only_tooltip")

        # Switch to standalone
        ConfigService.set("terminal_mode", "standalone")
        view.on_activated()
        assert view.supplier_read_only_banner.isHidden() is True
        assert view.btn_add_supplier.isEnabled() is True
        assert view.btn_edit_supplier.isEnabled() is True
        assert view.btn_deactivate_supplier.isEnabled() is True
    finally:
        ConfigService.set("terminal_mode", "standalone")
        view.close()
        view.deleteLater()
