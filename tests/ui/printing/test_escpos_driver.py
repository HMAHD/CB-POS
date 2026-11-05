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
