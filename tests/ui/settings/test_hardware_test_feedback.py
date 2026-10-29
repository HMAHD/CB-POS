"""
#624: hardware tests returned one hardcoded English sentence ("No printer
configured...") whatever went wrong, always tested the *saved* printer
rather than what is on screen, kicked the drawer on pin 2 only, and showed
the outcome in an unstyled, top-aligned label.

Now the service returns codes, the UI translates them, tests use the
unsaved on-screen values, and the drawer pin (2/5) is passed through.
python-escpos printer classes are always mocked -- never real hardware.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from escpos.exceptions import DeviceNotFoundError
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from cbpos.core.constants.hardware import HardwareTestOutcome, PrinterError
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.hardware_test_service import HardwareTestResult, HardwareTestService
from cbpos.i18n import get_language, set_language
from cbpos.ui.hardware_test_feedback import hardware_test_message, show_hardware_test_result
from cbpos.ui.views.admin_tools_view import AdminToolsView
from cbpos.ui.views.settings_pages import HardwarePage

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def saved_no_printer(monkeypatch):
    """Saved settings say there is no printer -- tests must not depend on them."""
    real_get_all = ConfigService.get_all
    monkeypatch.setattr(
        ConfigService,
        "get_all",
        classmethod(lambda cls: {**real_get_all(), "printer_type": "NONE", "printer_path": ""}),
    )


class TestServiceTestsTheGivenValues:
    def test_unsaved_windows_printer_is_tested(self, saved_no_printer):
        with patch("escpos.printer.Win32Raw") as win32raw:
            win32raw.is_usable.return_value = True
            result = HardwareTestService.test_receipt_printer("WIN32", "XP-80C")
        win32raw.assert_called_once_with("XP-80C")
        assert result.success is True
        assert result.code == HardwareTestOutcome.PRINT_SENT_WIN32
        printed = [c.args[0] for c in win32raw.return_value.text.call_args_list]
        assert any("TEST PRINT" in t for t in printed)

    def test_unsaved_network_printer_is_tested(self, saved_no_printer):
        with patch("escpos.printer.Network") as network:
            result = HardwareTestService.test_receipt_printer("NETWORK", "192.168.1.50")
        assert network.call_args.args == ("192.168.1.50",)
        assert result.code == HardwareTestOutcome.PRINT_SENT

    def test_saved_values_used_when_none_given(self, saved_no_printer):
        result = HardwareTestService.test_receipt_printer()
        assert result.success is False
        assert result.code == PrinterError.NOT_CONFIGURED


class TestServiceErrorCodes:
    def test_missing_windows_printer(self):
        with patch("escpos.printer.Win32Raw") as win32raw:
            win32raw.is_usable.return_value = True
            win32raw.return_value.open.side_effect = DeviceNotFoundError("Incorrect printer name")
            result = HardwareTestService.test_receipt_printer("WIN32", "Gone")
        assert (result.success, result.code, result.printer_path) == (False, PrinterError.WIN32_NOT_FOUND, "Gone")

    def test_network_timeout(self):
        with patch("escpos.printer.Network") as network:
            network.return_value.open.side_effect = DeviceNotFoundError("Could not open socket: timed out")
            result = HardwareTestService.test_receipt_printer("NETWORK", "10.0.0.9")
        assert result.code == PrinterError.NETWORK_NO_ANSWER

    def test_usb_access_denied_while_writing(self):
        import usb.core

        with patch("escpos.printer.Usb") as usb_printer:
            usb_printer.return_value.text.side_effect = usb.core.USBError("Access denied (insufficient permissions)")
            result = HardwareTestService.test_receipt_printer("USB", "0x04b8:0x0202")
        assert result.code == PrinterError.USB_ACCESS_DENIED

    def test_usb_unplugged(self):
        with patch("escpos.printer.Usb") as usb_printer:
            usb_printer.return_value.open.side_effect = DeviceNotFoundError(
                "Unable to open USB printer on (1208, 514):\nDevice not found or cable not plugged in."
            )
            result = HardwareTestService.test_receipt_printer("USB", "0x04b8:0x0202")
        assert result.code == PrinterError.USB_NOT_FOUND

    def test_not_configured(self):
        result = HardwareTestService.test_receipt_printer("NONE", "")
        assert result.code == PrinterError.NOT_CONFIGURED


class TestDrawerPin:
    @pytest.mark.parametrize("pin", [2, 5])
    def test_pin_is_passed_to_cashdraw(self, pin):
        with patch("escpos.printer.Network") as network:
            result = HardwareTestService.test_cash_drawer("NETWORK", "192.168.1.50", pin=pin)
        network.return_value.cashdraw.assert_called_once_with(pin)
        assert result.code == HardwareTestOutcome.DRAWER_SENT

    def test_sale_drawer_kick_uses_saved_pin(self, monkeypatch):
        from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver

        real_get = ConfigService.get
        monkeypatch.setattr(
            ConfigService, "get", classmethod(lambda cls, key: 5 if key == "drawer_pin" else real_get(key))
        )
        driver = ESCPOSDriver()
        driver.printer = MagicMock()
        driver.kick_drawer()
        driver.printer.cashdraw.assert_called_once_with(5)


CODES = [
    HardwareTestOutcome.PRINT_SENT,
    HardwareTestOutcome.PRINT_SENT_WIN32,
    HardwareTestOutcome.DRAWER_SENT,
    HardwareTestOutcome.DRAWER_SENT_WIN32,
    PrinterError.NOT_CONFIGURED,
    PrinterError.WIN32_NOT_FOUND,
    PrinterError.WIN32_UNAVAILABLE,
    PrinterError.NETWORK_NO_ADDRESS,
    PrinterError.NETWORK_NO_ANSWER,
    PrinterError.USB_INVALID_ID,
    PrinterError.USB_NOT_FOUND,
    PrinterError.USB_ACCESS_DENIED,
    PrinterError.FAILED,
]


class TestCodesBecomeTranslatedMessages:
    def test_each_code_has_its_own_message(self):
        messages = [hardware_test_message(HardwareTestResult(False, code, "WIN32", "X")) for code in CODES]
        assert len(set(messages)) == len(CODES)
        assert not any(m.startswith("printer.test.") for m in messages)

    def test_messages_name_the_printer(self):
        assert "XP-80C" in hardware_test_message(
            HardwareTestResult(False, PrinterError.WIN32_NOT_FOUND, "WIN32", "XP-80C")
        )
        assert "10.0.0.9" in hardware_test_message(
            HardwareTestResult(False, PrinterError.NETWORK_NO_ANSWER, "NETWORK", "10.0.0.9")
        )

    def test_win32_success_is_worded_honestly(self):
        text = hardware_test_message(HardwareTestResult(True, HardwareTestOutcome.PRINT_SENT_WIN32, "WIN32", "X"))
        assert text == "Sent to Windows — check that the test slip printed."

    @pytest.mark.parametrize("lang", ["si", "ta"])
    def test_messages_are_translated(self, lang):
        english = {code: hardware_test_message(HardwareTestResult(False, code, "WIN32", "X")) for code in CODES}
        previous = get_language()
        set_language(lang)
        try:
            for code in CODES:
                assert hardware_test_message(HardwareTestResult(False, code, "WIN32", "X")) != english[code], code
        finally:
            set_language(previous)

    def test_unknown_code_reads_as_generic_failure(self):
        assert hardware_test_message(HardwareTestResult(False, "???")) == hardware_test_message(
            HardwareTestResult(False, PrinterError.FAILED)
        )


class TestResultLabelStyling:
    def test_success_and_failure_classes(self):
        label = QLabel()
        show_hardware_test_result(label, HardwareTestResult(True, HardwareTestOutcome.PRINT_SENT))
        assert label.property("class") == "success-hint"
        show_hardware_test_result(label, HardwareTestResult(False, PrinterError.FAILED, detail="boom"))
        assert label.property("class") == "warning-hint"
        assert label.toolTip() == "boom"
        assert label.alignment() & Qt.AlignmentFlag.AlignVCenter

    def test_admin_tools_result_slot_uses_translated_styled_text(self):
        view = SimpleNamespace(btn_test_printer=MagicMock(), lbl_printer_status=QLabel())
        AdminToolsView._on_printer_test_done(
            view, HardwareTestResult(False, PrinterError.NETWORK_NO_ANSWER, "NETWORK", "10.0.0.9")
        )
        assert "10.0.0.9" in view.lbl_printer_status.text()
        assert view.lbl_printer_status.property("class") == "warning-hint"
        view.btn_test_printer.setEnabled.assert_called_once_with(True)


class _FakeWorker:
    """Records how a test worker was built instead of starting a thread."""

    instances: list["_FakeWorker"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.result = MagicMock()
        self.started = False
        _FakeWorker.instances.append(self)

    def start(self) -> None:
        self.started = True


@pytest.fixture
def page():
    with patch("cbpos.ui.views.settings_pages.QPrinterInfo.availablePrinterNames", return_value=["XP-80C"]):
        p = HardwarePage()
    p.load({"printer_type": "WIN32", "printer_path": "XP-80C", "drawer_pin": 2})
    _FakeWorker.instances = []
    yield p


class TestSettingsPageTestsUnsavedValues:
    def test_test_print_uses_on_screen_network_ip(self, page):
        page.combo_printer_type.setCurrentIndex(page.combo_printer_type.findData("NETWORK"))
        page.input_printer_ip.setText("192.168.1.77")
        with patch("cbpos.ui.workers.PrinterTestWorker", _FakeWorker):
            page.btn_test_print.click()
        worker = _FakeWorker.instances[-1]
        assert worker.args == ("NETWORK", "192.168.1.77")
        assert worker.started
        assert not page.btn_test_print.isEnabled()

    def test_open_drawer_uses_on_screen_printer_and_pin(self, page):
        page.combo_drawer_pin.setCurrentIndex(page.combo_drawer_pin.findData(5))
        with patch("cbpos.ui.workers.DrawerTestWorker", _FakeWorker):
            page.btn_open_drawer.click()
        assert _FakeWorker.instances[-1].args == ("WIN32", "XP-80C", 5)

    def test_result_reenables_buttons_and_styles_label(self, page):
        page._on_hardware_test_done(HardwareTestResult(True, HardwareTestOutcome.PRINT_SENT_WIN32, "WIN32", "XP-80C"))
        assert page.btn_test_print.isEnabled()
        assert page.lbl_test_result.property("class") == "success-hint"
        assert "Windows" in page.lbl_test_result.text()

    def test_drawer_pin_is_saved_and_loaded(self, page):
        page.combo_drawer_pin.setCurrentIndex(page.combo_drawer_pin.findData(5))
        assert page.save()["drawer_pin"] == 5
        page.load({"drawer_pin": 2})
        assert page.combo_drawer_pin.currentData() == 2
