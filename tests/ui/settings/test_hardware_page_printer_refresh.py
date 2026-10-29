"""
#323: printer detection ran exactly once, inside HardwarePage.__init__(),
and HardwarePage itself is constructed exactly once per app session and
kept alive for the rest of it. A shop owner who plugs in a receipt
printer after opening the app had no way to make it appear in the list
short of a full app restart -- there was no "Refresh" action anywhere
on this tab.
"""

from unittest.mock import patch

import pytest

from cbpos.ui.views.settings_pages import HardwarePage

pytestmark = pytest.mark.usefixtures("qapp")


class TestPrinterListCanBeRescanned:
    def test_refresh_button_exists(self):
        page = HardwarePage()
        assert page.btn_refresh_printers is not None

    def test_clicking_refresh_repopulates_both_printer_combos(self):
        with patch(
            "cbpos.ui.views.settings_pages.QPrinterInfo.availablePrinterNames",
            return_value=["Old Printer"],
        ):
            page = HardwarePage()

        assert page.combo_receipt_printer.findText("Old Printer") != -1

        with patch(
            "cbpos.ui.views.settings_pages.QPrinterInfo.availablePrinterNames",
            return_value=["New Receipt Printer", "New A4 Printer"],
        ):
            page.btn_refresh_printers.click()

        assert page.combo_receipt_printer.findText("New Receipt Printer") != -1
        assert page.combo_a4_printer.findText("New A4 Printer") != -1
        assert page.combo_receipt_printer.findText("Old Printer") == -1

    def test_refresh_preserves_the_current_selection_when_still_available(self):
        with patch(
            "cbpos.ui.views.settings_pages.QPrinterInfo.availablePrinterNames",
            return_value=["Printer A", "Printer B"],
        ):
            page = HardwarePage()

        page.combo_receipt_printer.setCurrentText("Printer B")

        with patch(
            "cbpos.ui.views.settings_pages.QPrinterInfo.availablePrinterNames",
            return_value=["Printer A", "Printer B", "Printer C"],
        ):
            page.btn_refresh_printers.click()

        assert page.combo_receipt_printer.currentText() == "Printer B"
