"""
#623: with no receipt printer set up, the Sales screen shows a small,
non-blocking notice once per app session pointing to Settings -> Hardware,
instead of letting every sale silently print nothing.
"""

from unittest.mock import patch

import pytest

from cbpos.core.services.config_service import ConfigService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker, printer_not_configured_message
from cbpos.ui.views.sales_view import SalesView


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


def _use_printer_type(monkeypatch: pytest.MonkeyPatch, printer_type: str) -> None:
    """Force printer_type in settings without touching the rest of them."""
    real_get_all = ConfigService.get_all
    monkeypatch.setattr(
        ConfigService, "get_all", classmethod(lambda cls: {**real_get_all(), "printer_type": printer_type})
    )


@pytest.fixture
def no_printer(monkeypatch):
    _use_printer_type(monkeypatch, "NONE")


@pytest.fixture
def view(qapp, db_session, monkeypatch):
    monkeypatch.setattr(SalesView, "_printer_notice_shown", False)  # fresh app session
    v = SalesView()
    yield v
    v.hide()
    v.deleteLater()


class TestSalesPrinterNotice:
    def test_notice_shown_once_per_session_when_no_printer(self, no_printer, view):
        view.show()
        assert view.printer_notice.isVisibleTo(view)

        view.printer_notice_close.click()
        assert not view.printer_notice.isVisibleTo(view)

        view.hide()
        view.show()  # coming back to Sales later in the same session
        assert not view.printer_notice.isVisibleTo(view)

        other = SalesView()  # a re-created view in the same app session
        other.show()
        assert not other.printer_notice.isVisibleTo(other)
        other.hide()
        other.deleteLater()

    def test_notice_not_shown_when_printer_configured(self, monkeypatch, view):
        _use_printer_type(monkeypatch, "USB")
        view.show()
        assert not view.printer_notice.isVisibleTo(view)

    def test_setup_button_requests_hardware_settings(self, no_printer, view, qtbot):
        view.show()
        with qtbot.waitSignal(view.printer_setup_requested, timeout=1000):
            view.printer_notice_setup.click()
        assert not view.printer_notice.isVisibleTo(view)

    def test_missing_printer_error_after_sale_is_not_a_modal(self, no_printer, view):
        """Auto-print after a sale with no printer brings the notice back
        instead of blocking the cashier with a modal on every sale."""
        view.show()
        view.printer_notice_close.click()
        with patch("cbpos.ui.views.sales_view.QMessageBox") as mock_box:
            PrintWorker.instance().error_occurred.emit(printer_not_configured_message())
            mock_box.warning.assert_not_called()
        assert view.printer_notice.isVisibleTo(view)

    def test_real_printer_failure_still_shows_a_warning(self, view):
        with patch("cbpos.ui.views.sales_view.QMessageBox") as mock_box:
            PrintWorker.instance().error_occurred.emit("Printer not available.")
            mock_box.warning.assert_called_once()


class TestSetupButtonOpensHardwareSettings:
    @pytest.fixture
    def window(self, qapp, db_session):
        from PyQt6.QtWidgets import QApplication

        from cbpos.ui.main_window import MainWindow

        w = MainWindow()
        yield w
        w.deleteLater()
        QApplication.processEvents()  # see test_main_window_shift_dialog_ordering.py

    def test_main_window_switches_to_settings_hardware_page(self, window):
        from cbpos.ui.views.settings_pages import HardwarePage

        window.sales_view.printer_setup_requested.emit()

        assert window.stack.currentWidget() is window.settings_view
        assert isinstance(window.settings_view.stack.currentWidget(), HardwarePage)


class TestCashSaleWithNoPrinter:
    def test_drawer_kick_does_not_bring_back_dismissed_notice(self, no_printer, view, qtbot):
        """A cash sale queues a drawer kick; with no printer it must stay
        silent so the dismissed notice really appears only once."""
        view.show()
        view.printer_notice_close.click()
        worker = PrintWorker.instance()
        with patch("cbpos.ui.views.sales_view.QMessageBox") as mock_box:
            worker.add_job("kick_drawer", ["CASH"])  # what PrintWorkerPeripherals queues after a sale
            qtbot.waitUntil(worker._queue.empty, timeout=5000)
            qtbot.wait(300)  # let any (wrong) signal reach the UI thread
            mock_box.warning.assert_not_called()
        assert not view.printer_notice.isVisibleTo(view)
