"""
#622: Settings -> Hardware only saved ``receipt_printer_name``, which nothing
read, so the receipt printer could not be set from the app. The page now
has a connection selector (Windows printer / Network / USB direct), shows
only the matching field, and saves ``printer_type`` + ``printer_path`` --
the keys the print driver reads.
"""

from unittest.mock import patch

import pytest

from cbpos.ui.views.settings_pages import HardwarePage

pytestmark = pytest.mark.usefixtures("qapp")

PRINTERS = ["XP-80C", "Microsoft Print to PDF"]


@pytest.fixture
def page():
    with patch("cbpos.ui.views.settings_pages.QPrinterInfo.availablePrinterNames", return_value=PRINTERS):
        p = HardwarePage()
    p.load({})  # fill the other fields with their defaults so save() is valid
    yield p


def _choose(page: HardwarePage, printer_type: str) -> None:
    page.combo_printer_type.setCurrentIndex(page.combo_printer_type.findData(printer_type))


def _row_visible(page: HardwarePage, widget) -> bool:
    return page._sel_form.isRowVisible(widget)


class TestDefaultsToWindowsPrinter:
    def test_unconfigured_install_shows_windows_printer_with_nothing_chosen(self, page):
        page.load({"printer_type": "NONE", "printer_path": ""})
        assert page.combo_printer_type.currentData() == "WIN32"
        assert page.combo_receipt_printer.currentData() == ""

    def test_nothing_chosen_saves_no_printer(self, page):
        page.load({"printer_type": "NONE"})
        saved = page.save()
        assert saved["printer_type"] == "NONE"
        assert saved["printer_path"] == ""


class TestSavesPrinterTypeAndValue:
    def test_windows_printer(self, page):
        _choose(page, "WIN32")
        page.combo_receipt_printer.setCurrentIndex(page.combo_receipt_printer.findData("XP-80C"))
        saved = page.save()
        assert saved["printer_type"] == "WIN32"
        assert saved["printer_path"] == "XP-80C"
        assert saved["receipt_printer_name"] == "XP-80C"

    def test_network_printer(self, page):
        _choose(page, "NETWORK")
        page.input_printer_ip.setText(" 192.168.1.50 ")
        saved = page.save()
        assert saved["printer_type"] == "NETWORK"
        assert saved["printer_path"] == "192.168.1.50"

    def test_usb_printer(self, page):
        _choose(page, "USB")
        page.input_usb_id.setText("0x04b8:0x0202")
        saved = page.save()
        assert saved["printer_type"] == "USB"
        assert saved["printer_path"] == "0x04b8:0x0202"


class TestLoadsSavedPrinter:
    @pytest.mark.parametrize(
        ("printer_type", "path", "attr"),
        [("NETWORK", "10.0.0.7", "input_printer_ip"), ("USB", "04b8:0202", "input_usb_id")],
    )
    def test_value_lands_in_matching_field(self, page, printer_type, path, attr):
        page.load({"printer_type": printer_type, "printer_path": path})
        assert page.combo_printer_type.currentData() == printer_type
        assert getattr(page, attr).text() == path

    def test_saved_windows_printer_that_is_offline_is_kept(self, page):
        page.load({"printer_type": "WIN32", "printer_path": "Kitchen Printer"})
        assert page.combo_receipt_printer.currentData() == "Kitchen Printer"
        assert page.save()["printer_path"] == "Kitchen Printer"


class TestOnlyTheChosenFieldIsShown:
    @pytest.mark.parametrize(
        ("printer_type", "visible"),
        [
            ("WIN32", "combo_receipt_printer"),
            ("NETWORK", "input_printer_ip"),
            ("USB", "input_usb_id"),
        ],
    )
    def test_field_visibility(self, page, printer_type, visible):
        _choose(page, printer_type)
        for attr in ("combo_receipt_printer", "input_printer_ip", "input_usb_id"):
            assert _row_visible(page, getattr(page, attr)) is (attr == visible), attr


class TestValidation:
    def test_network_needs_an_ip(self, page):
        _choose(page, "NETWORK")
        with pytest.raises(ValueError):
            page.validate()

    def test_usb_needs_vid_pid(self, page):
        _choose(page, "USB")
        page.input_usb_id.setText("epson")
        with pytest.raises(ValueError):
            page.validate()

    def test_windows_printer_is_valid(self, page):
        _choose(page, "WIN32")
        page.validate()
