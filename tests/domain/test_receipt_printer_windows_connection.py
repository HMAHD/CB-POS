"""
#622: the receipt printer could only be set by hand-editing settings.json --
the Hardware page and Setup Wizard saved ``receipt_printer_name``, which
nothing read. The driver now understands a WIN32 connection (raw ESC/POS
through the Windows spooler via python-escpos' Win32Raw).

Win32Raw is always mocked here -- never real hardware, and never pywin32
(not installed off Windows).
"""

from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.constants.hardware import PrinterError
from cbpos.core.services.config_service import ConfigService
from cbpos.infrastructure.hardware.escpos_driver import (
    ESCPOSDriver,
    PrintWorker,
    parse_usb_id,
    receipt_printer_configured,
)


class TestWindowsPrinterIsARealPrinter:
    def test_win32_counts_as_configured(self, monkeypatch):
        monkeypatch.setattr(ConfigService, "get_all", classmethod(lambda cls: {"printer_type": "WIN32"}))
        assert receipt_printer_configured() is True

    def test_resolve_printer_returns_win32raw_backed_driver(self, monkeypatch):
        monkeypatch.setattr(
            ConfigService,
            "get_all",
            classmethod(lambda cls: {"printer_type": "WIN32", "printer_path": "XP-80C"}),
        )
        worker = PrintWorker()
        driver = worker._resolve_printer()
        assert isinstance(driver, ESCPOSDriver)

        fake = MagicMock()
        with patch("escpos.printer.Win32Raw") as win32raw:
            win32raw.is_usable.return_value = True
            win32raw.return_value = fake
            assert driver.connect() is True

        win32raw.assert_called_once_with("XP-80C")
        fake.open.assert_called_once()
        assert driver.printer is fake


class TestDriverConnect:
    def test_missing_windows_printer_reports_not_found(self):
        from escpos.exceptions import DeviceNotFoundError

        driver = ESCPOSDriver(printer_type="WIN32", printer_path="Gone")
        with patch("escpos.printer.Win32Raw") as win32raw:
            win32raw.is_usable.return_value = True
            win32raw.return_value.open.side_effect = DeviceNotFoundError("Incorrect printer name")
            assert driver.connect() is False
        assert driver.last_error == PrinterError.WIN32_NOT_FOUND

    def test_win32_without_pywin32_reports_unavailable(self):
        driver = ESCPOSDriver(printer_type="WIN32", printer_path="XP-80C")
        with patch("escpos.printer.Win32Raw") as win32raw:
            win32raw.is_usable.return_value = False
            assert driver.connect() is False
        win32raw.assert_not_called()
        assert driver.last_error == PrinterError.WIN32_UNAVAILABLE

    def test_network_uses_ip_and_short_timeout(self):
        driver = ESCPOSDriver(printer_type="NETWORK", printer_path="192.168.1.50")
        with patch("escpos.printer.Network") as network:
            assert driver.connect() is True
        args, kwargs = network.call_args
        assert args == ("192.168.1.50",)
        assert kwargs["port"] == 9100
        assert kwargs["timeout"] <= 10

    def test_network_timeout_reports_no_answer(self):
        driver = ESCPOSDriver(printer_type="NETWORK", printer_path="10.0.0.9")
        with patch("escpos.printer.Network") as network:
            network.return_value.open.side_effect = TimeoutError("timed out")
            assert driver.connect() is False
        assert driver.last_error == PrinterError.NETWORK_NO_ANSWER

    def test_usb_uses_parsed_ids(self):
        driver = ESCPOSDriver(printer_type="USB", printer_path="0x04b8:0x0202")
        with patch("escpos.printer.Usb") as usb:
            assert driver.connect() is True
        usb.assert_called_once_with(0x04B8, 0x0202)

    def test_bad_usb_id_reports_invalid(self):
        driver = ESCPOSDriver(printer_type="USB", printer_path="epson")
        assert driver.connect() is False
        assert driver.last_error == PrinterError.USB_INVALID_ID

    def test_lost_connection_while_printing_is_raised(self):
        """A dead printer must fail the job, not be logged and skipped as a bad command."""
        driver = ESCPOSDriver()
        driver.printer = MagicMock()
        driver.printer.text.side_effect = OSError("broken pipe")
        with pytest.raises(OSError):
            driver.print_commands([{"type": "text", "val": "x"}])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0x04b8:0x0202", (0x04B8, 0x0202)),
        ("04b8:0202", (0x04B8, 0x0202)),
        ("04b8", None),
        ("zz:0202", None),
        ("", None),
    ],
)
def test_parse_usb_id(text, expected):
    assert parse_usb_id(text) == expected
