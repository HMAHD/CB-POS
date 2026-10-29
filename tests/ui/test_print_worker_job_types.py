"""
#625: every PrintWorker job type is either really printed or reported as
an error -- never a silent job_completed.

The worker only handled "print_receipt" and "kick_drawer". A "print_image"
job (old Sinhala/Tamil receipts) or a "print_commands" job (customer
statement, shelf labels, quotation reprint) connected to the printer,
printed nothing, and still emitted job_completed, so the screen said
"sent to printer". The printer here is always a mock.
"""

from unittest.mock import MagicMock

import pytest

from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

COMMANDS = [{"type": "text", "val": "hello"}, {"type": "cut", "partial": True}]


@pytest.fixture
def printer():
    mock = MagicMock()
    mock.connect.return_value = True
    return mock


@pytest.fixture
def worker(printer):
    w = PrintWorker(printer=printer)
    yield w
    w.stop()
    w.wait(5000)


def _run_job(qtbot, worker, job_type, data):
    """Queue one job and return the signals it produced."""
    signals: list = []
    worker.job_completed.connect(lambda: signals.append("completed"))
    worker.error_occurred.connect(lambda msg: signals.append(("error", msg)))
    worker.add_job(job_type, data)
    qtbot.waitUntil(lambda: bool(signals), timeout=5000)
    qtbot.wait(150)  # room for a wrong extra signal to arrive
    return signals


@pytest.mark.parametrize("job_type", ["print_receipt", "print_commands"])
def test_command_list_jobs_really_print(qtbot, worker, printer, job_type):
    signals = _run_job(qtbot, worker, job_type, COMMANDS)

    assert signals == ["completed"]
    printer.print_commands.assert_called_once_with(COMMANDS)
    printer.disconnect.assert_called_once()


@pytest.mark.parametrize("job_type", ["print_image", "print_pdf", "bogus", None])
def test_unknown_job_type_is_an_error_not_a_success(qtbot, worker, printer, job_type):
    signals = _run_job(qtbot, worker, job_type, COMMANDS)

    assert signals == [("error", _t("printer.job_unsupported"))]
    printer.connect.assert_not_called()
    printer.print_commands.assert_not_called()


@pytest.mark.parametrize("data", ["receipt as plain text", None, object()])
def test_print_job_without_a_command_list_is_an_error(qtbot, worker, printer, data):
    signals = _run_job(qtbot, worker, "print_receipt", data)

    assert signals == [("error", _t("printer.job_unsupported"))]
    printer.print_commands.assert_not_called()


def test_unwanted_drawer_kick_never_opens_the_printer(qtbot, worker, printer, monkeypatch):
    """drawer_on_cash_only + card payment: skipped before connecting, so no
    connection is left open (it used to connect, then skip the disconnect)."""
    real_get = ConfigService.get
    monkeypatch.setattr(
        ConfigService, "get", classmethod(lambda cls, k: True if k == "drawer_on_cash_only" else real_get(k))
    )
    worker.add_job("kick_drawer", ["CARD"])
    signals = _run_job(qtbot, worker, "print_receipt", COMMANDS)

    assert signals == ["completed"]
    printer.kick_drawer.assert_not_called()
    assert printer.connect.call_count == 1  # only the receipt job connected
    assert printer.disconnect.call_count == 1


def test_cash_drawer_kick_completes(qtbot, worker, printer):
    signals = _run_job(qtbot, worker, "kick_drawer", ["CASH"])

    assert signals == ["completed"]
    printer.kick_drawer.assert_called_once()
    printer.disconnect.assert_called_once()
