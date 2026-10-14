"""
#682: the shift Z-Report (and the mid-shift X-Read) is actually printed.

Closing a shift used to build the Z-Report text and drop it -- nothing went
to the printer. Now the report is built as receipt commands (so Sinhala/Tamil
labels print as images like every other receipt) and queued on the shared
PrintWorker through PrinterService. The closing dialog waits for the real
outcome: "printed" only on job_completed, and a no-printer / failed job
shows the worker's translated message -- never a false success (#669).
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.printer_service import PrinterService
from cbpos.core.services.shift_report_builder import ShiftReportBuilder
from cbpos.infrastructure.hardware.escpos_driver import printer_not_configured_message


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture
def config_store(monkeypatch):
    store = _FakeConfigStore(dict(ConfigService.DEFAULTS))
    store.set("receipt_language", "en")
    store.set("shop_name", "Perera Stores")
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    return store


class _FakeWorker(QObject):
    """Stands in for the shared PrintWorker: records jobs, signals emitted by the test."""

    error_occurred = pyqtSignal(str)
    job_completed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[tuple] = []

    def add_job(self, job_type, data=None) -> None:
        self.jobs.append((job_type, data))


@pytest.fixture
def worker():
    fake = _FakeWorker()
    with (
        patch("cbpos.core.services.printer_service.PrintWorker") as svc_cls,
        patch("cbpos.ui.dialogs.shift_closing_dialog.PrintWorker") as dlg_cls,
        patch("cbpos.ui.dialogs.shift_management_dialog.PrintWorker") as mgmt_cls,
    ):
        for cls in (svc_cls, dlg_cls, mgmt_cls):
            cls.instance.return_value = fake
        yield fake


def _summary(**overrides) -> dict:
    summary = {
        "shift_id": 3,
        "user_name": "nimal",
        "start_time": datetime(2026, 10, 14, 8, 0),
        "end_time": datetime(2026, 10, 14, 17, 0),
        "sales_by_method": {"CASH": Decimal("1500.00"), "CARD": Decimal("750.00")},
        "total_sales": Decimal("2250.00"),
        "starting_cash": Decimal("1000.00"),
        "cash_sales": Decimal("1500.00"),
        "cash_in": Decimal("200.00"),
        "cash_out": Decimal("100.00"),
        "expected_cash": Decimal("2600.00"),
        "actual_cash": Decimal("2550.00"),
        "variance": Decimal("-50.00"),
        "notes": "Short by 50",
        "txn_count": 12,
        "void_count": 1,
        "void_value": Decimal("118.00"),
    }
    summary.update(overrides)
    return summary


def _texts(commands: list[dict]) -> list[str]:
    return [c.get("val", "") for c in commands if c.get("type") == "text"]


# ── Builder ──────────────────────────────────────────────────────────────


class TestShiftReportBuilder:
    def test_z_report_has_title_figures_and_ends_with_cut(self, config_store):
        commands = ShiftReportBuilder.build_shift_report(_summary())
        joined = "\n".join(_texts(commands))

        assert "Z-REPORT" in joined
        assert "Perera Stores" in joined
        assert "nimal" in joined
        assert "1,500.00" in joined and "2,250.00" in joined
        assert "2,550.00" in joined and "-50.00" in joined
        assert "Short by 50" in joined
        assert "Powered by CB POS" in joined
        assert commands[-1]["type"] == "cut"

    def test_x_read_is_titled_differently_and_has_no_count_or_variance(self, config_store):
        summary = _summary()
        for key in ("end_time", "actual_cash", "variance", "notes"):
            summary.pop(key)

        joined = "\n".join(_texts(ShiftReportBuilder.build_shift_report(summary, x_read=True)))

        assert "X-READ" in joined and "Z-REPORT" not in joined
        assert "Variance" not in joined

    def test_receipt_language_is_used(self, config_store):
        config_store.set("receipt_language", "si")

        joined = "\n".join(_texts(ShiftReportBuilder.build_shift_report(_summary())))

        assert "මුළු විකුණුම්" in joined  # "Total Sales" in Sinhala

    def test_58mm_paper_rows_fit_the_line(self, config_store):
        config_store.set("paper_width", "58mm")

        for line in _texts(ShiftReportBuilder.build_shift_report(_summary())):
            assert len(line) <= 32, line


# ── PrinterService ──────────────────────────────────────────────────────


def test_print_shift_report_queues_one_job_with_built_commands(config_store, worker):
    summary = _summary()

    PrinterService.print_shift_report(summary)

    assert worker.jobs == [("print_receipt", ShiftReportBuilder.build_shift_report(summary))]


def test_print_shift_report_ignores_receipt_copies(config_store, worker):
    config_store.set("receipt_copies", 3)

    PrinterService.print_shift_report(_summary())

    ((_, commands),) = worker.jobs
    assert sum(1 for c in commands if c["type"] == "cut") == 1


# ── Shift closing dialog ─────────────────────────────────────────────────


@pytest.fixture
def closing_dialog(qapp, config_store, worker):
    from cbpos.ui.dialogs.shift_closing_dialog import ShiftClosingDialog

    with patch("cbpos.ui.dialogs.shift_closing_dialog.ShiftService") as svc_cls:
        service = svc_cls.return_value
        service.get_shift_summary.return_value = _summary(variance=Decimal("0"))
        service.close_shift.return_value = _summary(variance=Decimal("0"))
        dlg = ShiftClosingDialog(3)
        dlg.counted_cash = Decimal("2600.00")
        dlg.summary = {"expected_cash": Decimal("2600.00")}
        yield dlg
    dlg.deleteLater()


def test_closing_shift_queues_exactly_one_z_report(closing_dialog, worker):
    with patch("cbpos.ui.dialogs.shift_closing_dialog.QMessageBox"):
        closing_dialog._close_shift()

    assert worker.jobs == [("print_receipt", ShiftReportBuilder.build_shift_report(_summary(variance=Decimal("0"))))]


def test_success_is_reported_only_after_the_printer_finishes(closing_dialog, worker):
    with (
        patch("cbpos.ui.dialogs.shift_closing_dialog.QMessageBox") as box,
        patch.object(closing_dialog, "_offer_backup", return_value=False),
        patch.object(closing_dialog, "accept") as accept,
    ):
        closing_dialog._close_shift()
        box.information.assert_not_called()
        accept.assert_not_called()

        worker.job_completed.emit()

    box.information.assert_called_once()
    assert box.information.call_args.args[2] == _t_en("shift_closing.closed_success")
    accept.assert_called_once()


def test_no_printer_shows_translated_message_and_still_finishes(closing_dialog, worker):
    with (
        patch("cbpos.ui.dialogs.shift_closing_dialog.QMessageBox") as box,
        patch.object(closing_dialog, "_offer_backup", return_value=False),
        patch.object(closing_dialog, "accept") as accept,
    ):
        closing_dialog._close_shift()
        worker.error_occurred.emit(printer_not_configured_message())

    box.information.assert_not_called()
    shown = box.return_value.setText.call_args.args[0]
    assert printer_not_configured_message() in shown
    accept.assert_called_once()  # the shift IS closed -- skip printing and move on


def test_failure_then_retry_queues_a_second_job(closing_dialog, worker):
    with (
        patch("cbpos.ui.dialogs.shift_closing_dialog.QMessageBox") as box,
        patch.object(closing_dialog, "_offer_backup", return_value=False),
        patch.object(closing_dialog, "accept"),
    ):
        box.return_value.clickedButton.side_effect = lambda: box.return_value.addButton.return_value
        closing_dialog._close_shift()
        box.return_value.clickedButton.side_effect = None
        worker.error_occurred.emit("Paper out")

    assert len(worker.jobs) == 2


def test_closed_dialog_cannot_be_cancelled_while_printing(closing_dialog, worker):
    with patch("cbpos.ui.dialogs.shift_closing_dialog.QMessageBox"):
        closing_dialog._close_shift()
    with patch("PyQt6.QtWidgets.QDialog.reject") as base_reject:
        closing_dialog.reject()
    base_reject.assert_not_called()


# ── X-Read from the Shift dialog ─────────────────────────────────────────


@pytest.fixture
def management_dialog(qapp, config_store, worker):
    from cbpos.ui.dialogs.shift_management_dialog import ShiftManagementDialog

    summary = _summary()
    for key in ("end_time", "actual_cash", "variance", "notes"):
        summary.pop(key)
    with patch("cbpos.ui.dialogs.shift_management_dialog.ShiftService") as svc_cls:
        svc_cls.return_value.get_shift_summary.return_value = summary
        dlg = ShiftManagementDialog(3, user_id=1)
        yield dlg, summary
    dlg.deleteLater()


def test_print_x_read_queues_the_x_read(management_dialog, worker):
    dlg, summary = management_dialog

    with patch("cbpos.ui.dialogs.shift_management_dialog.QMessageBox") as box:
        dlg._print_x_read()
        worker.job_completed.emit()

    assert worker.jobs == [("print_receipt", ShiftReportBuilder.build_shift_report(summary, x_read=True))]
    box.information.assert_called_once()


def test_print_x_read_without_printer_reports_it(management_dialog, worker):
    dlg, _ = management_dialog

    with patch("cbpos.ui.dialogs.shift_management_dialog.QMessageBox") as box:
        dlg._print_x_read()
        worker.error_occurred.emit(printer_not_configured_message())

    box.information.assert_not_called()
    box.warning.assert_called_once()
    assert printer_not_configured_message() in box.warning.call_args.args[2]


def _t_en(key: str) -> str:
    from cbpos.i18n import _t

    return _t(key)


def test_shift_report_builder_does_not_touch_current_user(config_store):
    with patch(
        "cbpos.core.services.auth_service.AuthService.get_current_user",
        return_value=SimpleNamespace(username="someone_else"),
    ):
        joined = "\n".join(_texts(ShiftReportBuilder.build_shift_report(_summary())))
    assert "someone_else" not in joined


def test_old_text_z_report_is_gone():
    import importlib.util

    assert importlib.util.find_spec("cbpos.core.services.receipt_service") is None
