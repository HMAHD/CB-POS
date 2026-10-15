"""Package containing individual settings tab page modules."""

import sys
import types

from PyQt6.QtPrintSupport import QPrinterInfo
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from cbpos.i18n import _t
from cbpos.ui.dialogs.guide_dialog import GuideDialog
from cbpos.ui.views.settings_pages import (
    base,
    document,
    hardware,
    network,
    receipt,
    sales_tax,
    shop_info,
    system,
)
from cbpos.ui.views.settings_pages.base import _SECTION_TITLE_KEY, SettingsPage
from cbpos.ui.views.settings_pages.document import DocumentPage
from cbpos.ui.views.settings_pages.hardware import HardwarePage
from cbpos.ui.views.settings_pages.network import NetworkPage
from cbpos.ui.views.settings_pages.receipt import ReceiptPage
from cbpos.ui.views.settings_pages.sales_tax import SalesTaxPage
from cbpos.ui.views.settings_pages.shop_info import ShopInfoPage
from cbpos.ui.views.settings_pages.system import SystemPage

_SUBMODULES = (base, document, hardware, network, receipt, sales_tax, shop_info, system)


class _SettingsPagesPackage(types.ModuleType):
    """Package wrapper that synchronizes patched/monkeypatched attributes down to submodules."""

    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        for mod in _SUBMODULES:
            if hasattr(mod, name):
                setattr(mod, name, value)


sys.modules[__name__].__class__ = _SettingsPagesPackage

__all__ = [
    "_SECTION_TITLE_KEY",
    "DocumentPage",
    "GuideDialog",
    "HardwarePage",
    "NetworkPage",
    "QFileDialog",
    "QMessageBox",
    "QPrinterInfo",
    "ReceiptPage",
    "SalesTaxPage",
    "SettingsPage",
    "ShopInfoPage",
    "SystemPage",
    "_t",
]
