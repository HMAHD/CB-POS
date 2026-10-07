"""
#622: the Setup Wizard's printer step saved only ``receipt_printer_name``,
which nothing read. It now offers the same connection choice as
Settings -> Hardware and writes the same ``printer_type`` /
``printer_path`` keys.
"""

from unittest.mock import patch

import pytest

from cbpos.ui.dialogs.setup_wizard import SetupWizard

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def wizard():
    with patch("cbpos.ui.dialogs.setup_wizard.QPrinterInfo.availablePrinterNames", return_value=["XP-80C"]):
        w = SetupWizard()
    w.input_shop_name.setText("Test Shop")
    w.input_pin.setText("4321")
    yield w
    w.deleteLater()


def _finish(wizard: SetupWizard) -> dict:
    """Run finish_wizard() and return what it saved."""
    with (
        patch("cbpos.core.services.config_service.ConfigService.update_all") as update_all,
        patch("cbpos.core.services.user_service.UserService.update_admin_pin"),
    ):
        wizard.finish_wizard()
    return update_all.call_args[0][0]


def _choose(wizard: SetupWizard, printer_type: str) -> None:
    wizard.combo_printer_type.setCurrentIndex(wizard.combo_printer_type.findData(printer_type))


class TestWizardWritesPrinterKeys:
    def test_defaults_to_windows_printer(self, wizard):
        assert wizard.combo_printer_type.currentData() == "WIN32"

    def test_windows_printer(self, wizard):
        _choose(wizard, "WIN32")
        wizard.combo_receipt_printer.setCurrentIndex(wizard.combo_receipt_printer.findData("XP-80C"))
        saved = _finish(wizard)
        assert saved["printer_type"] == "WIN32"
        assert saved["printer_path"] == "XP-80C"

    def test_no_printer_chosen(self, wizard):
        saved = _finish(wizard)
        assert saved["printer_type"] == "NONE"
        assert saved["printer_path"] == ""

    def test_network_printer(self, wizard):
        _choose(wizard, "NETWORK")
        wizard.input_printer_ip.setText("192.168.1.50")
        saved = _finish(wizard)
        assert saved["printer_type"] == "NETWORK"
        assert saved["printer_path"] == "192.168.1.50"

    def test_usb_printer(self, wizard):
        _choose(wizard, "USB")
        wizard.input_usb_id.setText("0x04b8:0x0202")
        saved = _finish(wizard)
        assert saved["printer_type"] == "USB"
        assert saved["printer_path"] == "0x04b8:0x0202"

    def test_network_without_ip_blocks_next(self, wizard):
        wizard.stack.setCurrentIndex(1)
        _choose(wizard, "NETWORK")
        with patch("cbpos.ui.dialogs.setup_wizard.QMessageBox.warning") as warn:
            wizard.go_next()
        warn.assert_called_once()
        assert wizard.stack.currentIndex() == 1

    def test_only_the_chosen_field_is_shown(self, wizard):
        _choose(wizard, "NETWORK")
        assert wizard.hw_form.isRowVisible(wizard.input_printer_ip)
        assert not wizard.hw_form.isRowVisible(wizard.combo_receipt_printer)
        assert not wizard.hw_form.isRowVisible(wizard.input_usb_id)
