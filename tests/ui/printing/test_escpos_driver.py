"""
Tests for ESCPOSDriver and cash drawer kick rules (#793).
"""

from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.database import Database
from cbpos.core.models import AuditLog, Permission, Role, User
from cbpos.core.services.config_service import ConfigService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


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
    qtbot.wait(150)
    return signals


def test_issue_793_manual_kick_ignores_cash_only(qtbot, worker, printer, monkeypatch):
    """Manual drawer kick opens the drawer even when drawer_on_cash_only is True (#793)."""
    monkeypatch.setattr(
        ConfigService,
        "get",
        classmethod(lambda cls, k, d=None: True if k == "drawer_on_cash_only" else ConfigService.DEFAULTS.get(k, d)),
    )

    signals = _run_job(qtbot, worker, "kick_drawer", {"manual": True})

    assert signals == ["completed"]
    printer.kick_drawer.assert_called_once()
    printer.disconnect.assert_called_once()


def test_issue_793_auto_kick_card_only_skipped(qtbot, worker, printer, monkeypatch):
    """Automatic kick for card-only sale is skipped when drawer_on_cash_only is True (#793)."""
    monkeypatch.setattr(
        ConfigService,
        "get",
        classmethod(lambda cls, k, d=None: True if k == "drawer_on_cash_only" else ConfigService.DEFAULTS.get(k, d)),
    )

    # Queue an automatic card-only kick followed by a dummy receipt to verify drawer was skipped
    worker.add_job("kick_drawer", {"manual": False, "method_kinds": ["CARD"]})
    commands = [{"type": "text", "val": "receipt"}]
    signals = _run_job(qtbot, worker, "print_receipt", commands)

    assert signals == ["completed"]
    printer.kick_drawer.assert_not_called()


def test_issue_793_manual_open_requires_permission_and_audits(qapp, db_session):
    """Cashier without permission is denied with no job queued; override creates audit row and queues job (#793)."""
    perm = Permission(code="cash.open_drawer")
    manager_role = Role(name="Manager793", permissions=[perm])
    cashier_role = Role(name="Cashier793", permissions=[])
    manager = User(username="manager793", pin_hash="hash", role=manager_role)
    cashier = User(username="cashier793", pin_hash="hash", role=cashier_role)
    db_session.add_all([perm, manager_role, cashier_role, manager, cashier])
    db_session.commit()

    view = SalesView()
    try:
        mock_worker = MagicMock()
        with (
            patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=cashier),
            patch("cbpos.infrastructure.hardware.escpos_driver.PrintWorker.instance", return_value=mock_worker),
        ):
            # 1. Cashier denied (check_permission_with_override returns None)
            with patch("cbpos.core.utils.permission_helper.check_permission_with_override", return_value=None):
                view.open_cash_drawer()
                mock_worker.add_job.assert_not_called()

                with Database().get_session() as session:
                    logs = session.query(AuditLog).filter(AuditLog.action == "NO_SALE_DRAWER_OPEN").all()
                    assert len(logs) == 0

            # 2. Manager override granted (returns manager)
            with patch("cbpos.core.utils.permission_helper.check_permission_with_override", return_value=manager):
                view.open_cash_drawer()
                mock_worker.add_job.assert_called_once_with("kick_drawer", {"manual": True})

                with Database().get_session() as session:
                    logs = session.query(AuditLog).filter(AuditLog.action == "NO_SALE_DRAWER_OPEN").all()
                    assert len(logs) == 1
                    assert logs[0].user_id == cashier.id
                    assert logs[0].event_type == "SECURITY"
                    assert "manager793" in str(logs[0].details) or str(manager.id) in str(logs[0].details)
    finally:
        view.deleteLater()


def test_issue_840_choose_barcode_ean13_code128c_b():
    """choose_barcode selects EAN13 for valid 13-digit EANs, CODE128 {C for even digits, {B otherwise (#840)."""
    from cbpos.infrastructure.hardware.escpos_driver import choose_barcode

    # Valid EAN-13 -> EAN13
    assert choose_barcode("4006381333931") == ("EAN13", "4006381333931")
    assert choose_barcode("4791234567891") == ("EAN13", "4791234567891")

    # Even-length all-digit non-EAN -> CODE128 with {C
    assert choose_barcode("123456") == ("CODE128", "{C123456")
    assert choose_barcode("12") == ("CODE128", "{C12")

    # Odd-length all-digit non-EAN -> CODE128 with {B
    assert choose_barcode("4791234567890") == ("CODE128", "{B4791234567890")
    assert choose_barcode("12345") == ("CODE128", "{B12345")

    # Alphanumeric -> CODE128 with {B
    assert choose_barcode("INV-2026-0001") == ("CODE128", "{BINV-2026-0001")
    assert choose_barcode("ABC") == ("CODE128", "{BABC")

    # Already prefixed -> preserved
    assert choose_barcode("{C123456") == ("CODE128", "{C123456")
    assert choose_barcode("{BABC") == ("CODE128", "{BABC")


def test_issue_840_label_sends_gs_k_to_dummy():
    """A product label print sends real ESC/POS barcode bytes (GS k) to the printer (#840)."""
    from decimal import Decimal

    import escpos.printer

    from cbpos.core.models import Product
    from cbpos.core.services.label_service import LabelService
    from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver

    dummy = escpos.printer.Dummy()
    driver = ESCPOSDriver()
    driver.printer = dummy

    product = Product(
        name_en="Ceylon Tea 100g",
        barcode="4791234567890",
        price=Decimal("450.00"),
    )
    commands = LabelService._build_single_label(product)
    driver.print_commands(commands)

    assert b"\x1dk" in dummy.output, "Dummy printer output should contain ESC/POS GS k (barcode) command"
    assert b"4791234567890" in dummy.output, "Dummy printer output should contain encoded barcode data"


def test_issue_840_unrelated_runtime_error_does_not_abort_print_job(monkeypatch):
    """An unrelated RuntimeError on another command logs the error and does not abort the print job."""
    import escpos.printer

    from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver

    dummy = escpos.printer.Dummy()
    driver = ESCPOSDriver()
    driver.printer = dummy

    def bad_text(txt):
        raise RuntimeError("simulated unexpected text renderer error")

    monkeypatch.setattr(dummy, "text", bad_text)

    commands = [
        {"type": "text", "val": "hello"},
        {"type": "cut", "partial": True},
    ]
    # Text error should be logged; job must not abort before executing cut
    driver.print_commands(commands)
    assert b"\x1dV" in dummy.output  # GS V / cut command executed


def test_issue_840_unencodable_barcode_fails_job(qtbot):
    """An unencodable barcode fails the job, emitting job_result(..., False, ...) and error_occurred (#840)."""
    import escpos.printer

    from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver

    dummy = escpos.printer.Dummy()
    driver = ESCPOSDriver()
    driver.printer = dummy
    driver.connect = lambda: True
    driver.disconnect = lambda: None
    worker = PrintWorker(printer=driver)
    job_results = []
    errors = []
    completed = []

    worker.job_result.connect(lambda jid, ok, msg: job_results.append((jid, ok, msg)))
    worker.error_occurred.connect(lambda msg: errors.append(msg))
    worker.job_completed.connect(lambda: completed.append(True))

    try:
        commands = [{"type": "barcode", "val": "\u0d85\u0d9a", "code": "CODE128"}]
        job_id = worker.add_job("print_receipt", commands)

        qtbot.waitUntil(lambda: len(job_results) == 1, timeout=5000)
        qtbot.waitUntil(lambda: worker._queue.empty(), timeout=2000)

        assert len(job_results) == 1, "Exactly one job_result must be emitted"
        jid, ok, msg = job_results[0]
        assert jid == job_id
        assert ok is False
        assert "අක" in msg
        assert errors == [msg]
        assert len(completed) == 0, "A failed barcode job must not emit job_completed"
    finally:
        worker.stop()
        worker.wait(5000)
