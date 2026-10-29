"""Tests for issue #699: split settings_pages god-module into package."""

from unittest.mock import patch

import pytest

import cbpos.core.models  # noqa: F401 - registers ORM models

pytestmark = pytest.mark.usefixtures("qapp", "db_session")


def test_package_exports():
    """Verify all 8 settings page classes and base are exported from package."""
    import cbpos.ui.views.settings_pages as sp

    expected_classes = [
        "SettingsPage",
        "ShopInfoPage",
        "SalesTaxPage",
        "DocumentPage",
        "HardwarePage",
        "ReceiptPage",
        "SystemPage",
        "NetworkPage",
    ]
    for cls_name in expected_classes:
        assert hasattr(sp, cls_name), f"Package missing {cls_name}"
        assert getattr(sp, cls_name) is not None
        assert cls_name in sp.__all__


def test_submodule_direct_imports():
    """Verify each page can be imported directly from its dedicated submodule."""
    import cbpos.ui.views.settings_pages as sp
    from cbpos.ui.views.settings_pages.base import SettingsPage
    from cbpos.ui.views.settings_pages.document import DocumentPage
    from cbpos.ui.views.settings_pages.hardware import HardwarePage
    from cbpos.ui.views.settings_pages.network import NetworkPage
    from cbpos.ui.views.settings_pages.receipt import ReceiptPage
    from cbpos.ui.views.settings_pages.sales_tax import SalesTaxPage
    from cbpos.ui.views.settings_pages.shop_info import ShopInfoPage
    from cbpos.ui.views.settings_pages.system import SystemPage

    assert SettingsPage is sp.SettingsPage
    assert ShopInfoPage is sp.ShopInfoPage
    assert SalesTaxPage is sp.SalesTaxPage
    assert DocumentPage is sp.DocumentPage
    assert HardwarePage is sp.HardwarePage
    assert ReceiptPage is sp.ReceiptPage
    assert SystemPage is sp.SystemPage
    assert NetworkPage is sp.NetworkPage


def test_attribute_synchronization(monkeypatch):
    """Verify monkeypatching package attributes synchronizes down to submodules."""
    from cbpos.ui.views import settings_pages
    from cbpos.ui.views.settings_pages import network

    sentinel = object()
    monkeypatch.setattr(settings_pages, "_t", sentinel)
    assert settings_pages._t is sentinel
    assert network._t is sentinel


def test_instantiate_settings_pages():
    """Verify each settings page can be instantiated with default config."""
    from cbpos.ui.views.settings_pages import (
        DocumentPage,
        HardwarePage,
        NetworkPage,
        ReceiptPage,
        SalesTaxPage,
        SettingsPage,
        ShopInfoPage,
        SystemPage,
    )

    with patch("PyQt6.QtPrintSupport.QPrinterInfo.availablePrinterNames", return_value=[]):
        pages = [
            ShopInfoPage(),
            SalesTaxPage(),
            DocumentPage(),
            HardwarePage(),
            ReceiptPage(),
            SystemPage(),
            NetworkPage(),
        ]

    default_config = {
        "scale_barcode_prefix": "02",
        "scale_barcode_type": "price",
    }
    for page in pages:
        assert isinstance(page, SettingsPage)
        page.load(default_config)
        saved = page.save()
        assert isinstance(saved, dict)
