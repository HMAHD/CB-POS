"""Tests for printer name validation, ShellExecute printing, spool directory, and A4 routing (#876, #803)."""

import sys
import time
from unittest.mock import MagicMock

import pytest

from cbpos.config import Config
from cbpos.core.services.printer_service import PrinterService, cleanup_print_spool
from cbpos.i18n import _t


@pytest.fixture
def fake_win32(monkeypatch):
    """Provide mock win32print and win32api modules on all platforms."""
    mock_print = MagicMock()
    mock_api = MagicMock()

    mock_print.PRINTER_ENUM_LOCAL = 2
    mock_print.PRINTER_ENUM_CONNECTIONS = 4
    mock_print.EnumPrinters.return_value = [
        (2, "HP LaserJet Pro M404-M405 (PCL 6)", "HP LaserJet Pro M404-M405 (PCL 6)", ""),
        (2, "EPSON L3150 Series (Copy 1)", "EPSON L3150 Series (Copy 1)", ""),
        (2, "Office A4", "Office A4", ""),
    ]
    mock_api.ShellExecute.return_value = 42

    monkeypatch.setitem(sys.modules, "win32print", mock_print)
    monkeypatch.setitem(sys.modules, "win32api", mock_api)
    return mock_print, mock_api


def test_issue_876_names_with_parentheses_accepted_when_installed(fake_win32):
    _mock_print, _ = fake_win32
    name = "HP LaserJet Pro M404-M405 (PCL 6)"
    # Should not raise
    PrinterService._validate_printer_name(name)


def test_issue_876_name_not_installed_rejected(fake_win32):
    with pytest.raises(ValueError, match="isn't installed"):
        PrinterService._validate_printer_name("Nonexistent Printer (PCL 6)")


def test_issue_876_control_chars_rejected():
    for bad in ["Printer\nName", "Printer\rName", "Printer\x00Name", "Printer\x1fName"]:
        with pytest.raises(ValueError, match="control characters"):
            PrinterService._validate_printer_name(bad)
        with pytest.raises(ValueError, match="control characters"):
            PrinterService._validate_pdf_path(bad)


def test_issue_876_tilde_path_accepted():
    path = "C:\\Users\\ADMINI~1\\AppData\\Local\\Temp\\invoice_5.pdf"
    # Should not raise
    PrinterService._validate_pdf_path(path)
    assert PrinterService._validate_name(path, "PDF path") == path


def test_issue_876_shellexecute_called_with_printto_and_quotes(fake_win32):
    _, mock_api = fake_win32
    pdf_path = "C:\\print_spool\\invoice_1.pdf"
    printer_name = "HP LaserJet Pro M404-M405 (PCL 6)"

    PrinterService._send_pdf_to_printer(pdf_path, printer_name)

    mock_api.ShellExecute.assert_called_once_with(0, "printto", pdf_path, f'"{printer_name}"', ".", 0)


def test_issue_876_shellexecute_no_pdf_handler_translated(fake_win32):
    _, mock_api = fake_win32

    class PyWinError(Exception):
        def __init__(self):
            super().__init__("No application is associated with the specified file for this operation")
            self.winerror = 31

    mock_api.ShellExecute.side_effect = PyWinError()

    with pytest.raises(RuntimeError) as exc_info:
        PrinterService._send_pdf_to_printer("C:\\test.pdf", "Office A4")

    assert str(exc_info.value) == _t("printer.no_pdf_handler")


def test_issue_876_spool_folder_and_startup_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)

    spool_path = PrinterService.get_spool_path("REC/2026/001")
    assert spool_path.parent == tmp_path / "print_spool"
    assert spool_path.name.startswith("invoice_REC_2026_001_")
    assert spool_path.name.endswith(".pdf")

    # Create an old spool file (2 days old) and a recent one
    old_file = tmp_path / "print_spool" / "invoice_old_12345678.pdf"
    new_file = tmp_path / "print_spool" / "invoice_new_87654321.pdf"
    old_file.write_text("old")
    new_file.write_text("new")

    two_days_ago = time.time() - (2 * 86400)
    import os

    os.utime(old_file, (two_days_ago, two_days_ago))

    deleted = cleanup_print_spool(max_age_seconds=86400)
    assert deleted == 1
    assert not old_file.exists()
    assert new_file.exists()
