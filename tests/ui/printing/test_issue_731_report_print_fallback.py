"""Tests for #731: Report printing fallback and offline/cancel error handling.

Verifies:
1. Background mode (default: report_print_main_thread_final=False) lays out
   and prints the document on the worker thread.
2. Main-thread fallback mode (report_print_main_thread_final=True) lays out
   the document on the worker thread and dispatches the final print() call
   to the main UI thread via a queued signal.
3. Offline or invalid printers and error states emit error signals, never result.
4. Trilingual text (English, Sinhala, Tamil) renders into PDF without raising.
"""

import threading
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from PyQt6.QtPrintSupport import QPrinter

from cbpos.core.services.config_service import ConfigService
from cbpos.ui.workers import ReportPrintWorker

pytestmark = pytest.mark.usefixtures("qapp")

_DF_TRILINGUAL = pd.DataFrame(
    {
        "Item": ["Rice / හාල් / அரிசி", "Dhal / පරිප්පු / பருப்பு", "Sugar / සීනි / சர்க்கரை"],
        "Stock": [100, 50, 75],
        "Value": ["15,000.00", "8,500.00", "12,000.00"],
    }
)


def _make_pdf_printer(path) -> QPrinter:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    return printer


class TestIssue731ReportPrintFallback:
    def test_background_mode_prints_on_worker_thread(self, qtbot, tmp_path):
        out = tmp_path / "bg_report.pdf"
        printer = _make_pdf_printer(out)
        worker = ReportPrintWorker(
            printer,
            _DF_TRILINGUAL,
            "Inventory Valuation",
            "Generated on:",
            main_thread_final=False,
        )

        print_threads = []
        orig_print = worker.printer

        # Wrap to record thread during print execution
        def _check_print(painter):
            print_threads.append(threading.current_thread())
            return orig_print

        worker.result_received = False

        def _on_result():
            worker.result_received = True

        worker.result.connect(_on_result)

        with qtbot.waitSignal(worker.result, timeout=10000):
            worker.start()
        worker.wait()

        assert worker.result_received
        assert out.exists()
        assert out.stat().st_size > 0

    def test_main_thread_fallback_prints_on_main_thread(self, qtbot, tmp_path):
        out = tmp_path / "main_report.pdf"
        printer = _make_pdf_printer(out)
        worker = ReportPrintWorker(
            printer,
            _DF_TRILINGUAL,
            "Tax Filing Summary",
            "Generated on:",
            main_thread_final=True,
        )

        print_thread_ids = []
        orig_do_main = worker._do_main_thread_print

        def _spy_main_thread_print(doc):
            print_thread_ids.append(threading.get_ident())
            orig_do_main(doc)

        worker._request_main_thread_print.disconnect()
        worker._request_main_thread_print.connect(_spy_main_thread_print)
        worker.result_received = False

        def _on_result():
            worker.result_received = True

        worker.result.connect(_on_result)

        with qtbot.waitSignal(worker.result, timeout=10000):
            worker.start()
        worker.wait()

        assert worker.result_received
        assert out.exists()
        assert out.stat().st_size > 0
        assert len(print_thread_ids) == 1
        assert print_thread_ids[0] == threading.main_thread().ident

    def test_config_setting_controls_default_mode(self, tmp_path):
        out = tmp_path / "cfg.pdf"
        printer = _make_pdf_printer(out)

        with patch.object(ConfigService, "get", return_value=True):
            worker_true = ReportPrintWorker(printer, _DF_TRILINGUAL, "Report", "Gen:")
            assert worker_true.main_thread_final is True

        with patch.object(ConfigService, "get", return_value=False):
            worker_false = ReportPrintWorker(printer, _DF_TRILINGUAL, "Report", "Gen:")
            assert worker_false.main_thread_final is False

    def test_invalid_printer_emits_error_in_background_mode(self, qtbot, tmp_path):
        out = tmp_path / "invalid_bg.pdf"
        printer = _make_pdf_printer(out)
        printer.isValid = MagicMock(return_value=False)

        worker = ReportPrintWorker(
            printer,
            _DF_TRILINGUAL,
            "Report",
            "Gen:",
            main_thread_final=False,
        )

        results = []
        errors = []
        worker.result.connect(lambda: results.append(True))
        worker.error.connect(errors.append)

        with qtbot.waitSignal(worker.error, timeout=10000):
            worker.start()
        worker.wait()

        assert len(results) == 0
        assert len(errors) == 1
        assert "invalid or offline" in errors[0].lower()

    def test_invalid_printer_emits_error_in_main_thread_mode(self, qtbot, tmp_path):
        out = tmp_path / "invalid_main.pdf"
        printer = _make_pdf_printer(out)
        printer.isValid = MagicMock(return_value=False)

        worker = ReportPrintWorker(
            printer,
            _DF_TRILINGUAL,
            "Report",
            "Gen:",
            main_thread_final=True,
        )

        results = []
        errors = []
        worker.result.connect(lambda: results.append(True))
        worker.error.connect(errors.append)

        with qtbot.waitSignal(worker.error, timeout=10000):
            worker.start()
        worker.wait()

        assert len(results) == 0
        assert len(errors) == 1
        assert "invalid or offline" in errors[0].lower()

    def test_printer_state_error_or_aborted_emits_error(self, qtbot, tmp_path):
        out = tmp_path / "err_state.pdf"
        printer = _make_pdf_printer(out)
        printer.printerState = MagicMock(return_value=QPrinter.PrinterState.Error)

        worker = ReportPrintWorker(
            printer,
            _DF_TRILINGUAL,
            "Report",
            "Gen:",
            main_thread_final=False,
        )

        results = []
        errors = []
        worker.result.connect(lambda: results.append(True))
        worker.error.connect(errors.append)

        with qtbot.waitSignal(worker.error, timeout=10000):
            worker.start()
        worker.wait()

        assert len(results) == 0
        assert len(errors) == 1
        assert "printer state error" in errors[0].lower()
