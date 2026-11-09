"""Tests for PrintWorker job identity and job_result signal (Phase 7.1 foundation)."""

import uuid
from unittest.mock import MagicMock

import pytest

from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

COMMANDS = [{"type": "text", "val": "receipt line"}, {"type": "cut", "partial": True}]


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


def test_add_job_returns_uuid_hex(worker):
    job_id_1 = worker.add_job("print_receipt", COMMANDS)
    job_id_2 = worker.add_job("print_receipt", COMMANDS)

    assert isinstance(job_id_1, str)
    assert isinstance(job_id_2, str)
    assert len(job_id_1) == 32
    assert len(job_id_2) == 32
    # Verify valid hex
    uuid.UUID(hex=job_id_1)
    uuid.UUID(hex=job_id_2)
    assert job_id_1 != job_id_2


def test_job_result_emitted_on_success(qtbot, worker, printer):
    results = []
    completed = []
    worker.job_result.connect(lambda jid, ok, msg: results.append((jid, ok, msg)))
    worker.job_completed.connect(lambda: completed.append(True))

    job_id = worker.add_job("print_receipt", COMMANDS)
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)

    assert len(completed) == 1
    assert results == [(job_id, True, "")]
    printer.print_commands.assert_called_once_with(COMMANDS)


def test_job_result_emitted_on_error(qtbot, worker, printer):
    results = []
    errors = []
    worker.job_result.connect(lambda jid, ok, msg: results.append((jid, ok, msg)))
    worker.error_occurred.connect(lambda msg: errors.append(msg))

    job_id = worker.add_job("invalid_job_type", COMMANDS)
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)

    expected_msg = _t("printer.job_unsupported")
    assert errors == [expected_msg]
    assert results == [(job_id, False, expected_msg)]


def test_job_result_emitted_when_printer_connect_fails(qtbot, worker, printer):
    printer.connect.return_value = False
    results = []
    errors = []
    worker.job_result.connect(lambda jid, ok, msg: results.append((jid, ok, msg)))
    worker.error_occurred.connect(lambda msg: errors.append(msg))

    job_id = worker.add_job("print_receipt", COMMANDS)
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)

    expected_msg = _t("printer.not_available")
    assert errors == [expected_msg]
    assert results == [(job_id, False, expected_msg)]


def test_job_result_emitted_for_skipped_drawer_kick(qtbot, worker, printer, monkeypatch):
    from cbpos.core.services.config_service import ConfigService

    monkeypatch.setattr(ConfigService, "get", classmethod(lambda cls, k: k == "drawer_on_cash_only"))
    results = []
    worker.job_result.connect(lambda jid, ok, msg: results.append((jid, ok, msg)))

    # Drawer not wanted (card payment)
    job_id = worker.add_job("kick_drawer", ["CARD"])
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)

    assert results == [(job_id, False, "drawer_skipped:not_cash")]


def test_job_result_emitted_for_skipped_drawer_kick_no_printer(qtbot, monkeypatch):
    w = PrintWorker(printer=None)
    monkeypatch.setattr("cbpos.infrastructure.hardware.escpos_driver.receipt_printer_configured", lambda: False)
    results = []
    w.job_result.connect(lambda jid, ok, msg: results.append((jid, ok, msg)))

    job_id = w.add_job("kick_drawer", ["CASH"])
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)

    assert results == [(job_id, False, "drawer_skipped:no_printer")]
    w.stop()
    w.wait(5000)
