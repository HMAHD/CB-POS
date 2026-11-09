"""Tests for #803: configured A4 printer passed to printto, falling back to default printer."""

import sys
from unittest.mock import MagicMock

import pytest

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.printer_service import PrinterService


@pytest.fixture
def fake_win32(monkeypatch):
    """Provide mock win32print and win32api modules."""
    mock_print = MagicMock()
    mock_api = MagicMock()

    mock_print.PRINTER_ENUM_LOCAL = 2
    mock_print.PRINTER_ENUM_CONNECTIONS = 4
    mock_print.EnumPrinters.return_value = [
        (2, "Office A4", "Office A4", ""),
    ]
    mock_api.ShellExecute.return_value = 42

    monkeypatch.setitem(sys.modules, "win32print", mock_print)
    monkeypatch.setitem(sys.modules, "win32api", mock_api)
    return mock_print, mock_api


def test_issue_803_configured_printer_passed_to_printto(fake_win32, monkeypatch):
    _, mock_api = fake_win32
    monkeypatch.setattr(ConfigService, "get", lambda k, *_a: "Office A4" if k == "a4_printer_name" else None)

    resolved = PrinterService._resolve_a4_printer()
    assert resolved == "Office A4"

    pdf_path = "C:\\print_spool\\invoice_803.pdf"
    PrinterService._send_pdf_to_printer(pdf_path, resolved)
    mock_api.ShellExecute.assert_called_once_with(0, "printto", pdf_path, '"Office A4"', ".", 0)


def test_issue_803_fallback_to_default_printer_when_no_a4_printer_configured(fake_win32, monkeypatch):
    _, mock_api = fake_win32
    monkeypatch.setattr(ConfigService, "get", lambda k, *_a: None)

    resolved = PrinterService._resolve_a4_printer()
    assert resolved is None

    pdf_path = "C:\\print_spool\\invoice_default.pdf"
    PrinterService._send_pdf_to_printer(pdf_path, resolved)
    mock_api.ShellExecute.assert_called_once_with(0, "print", pdf_path, None, ".", 0)
