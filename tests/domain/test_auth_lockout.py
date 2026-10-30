"""Domain tests for Issue #856: Terminal-level brute-force lockout."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from cbpos.core.models import AuditLog, Permission, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService


@pytest.fixture
def auth_user_856(db_session):
    """Seed user for lockout tests."""
    perm = Permission(code="sales.create")
    role = Role(name="Cashier_Role_856", permissions=[perm])
    user = User(
        username="cashier_856",
        pin_hash=AuthService.hash_pin("1234"),
        role=role,
        is_active=True,
    )
    db_session.add_all([perm, role, user])
    db_session.commit()

    yield user

    AuthService._current_user = None


def test_issue_856_correct_pin_refused_after_max_failures(db_session, auth_user_856, monkeypatch):
    """After max failed login attempts on a terminal, the correct PIN is refused."""
    monkeypatch.setattr(
        ConfigService,
        "get",
        lambda key: 3 if key == "max_login_attempts" else (300 if key == "lockout_duration_seconds" else "TERM-TEST-1"),
    )

    # 3 failed attempts
    for _ in range(3):
        assert AuthService.login("0000") is None

    # Terminal should now be locked
    lockout_secs = AuthService.get_terminal_lockout_seconds()
    assert lockout_secs > 0

    # Even the correct PIN is now refused
    assert AuthService.login("1234") is None


def test_issue_856_lockout_expires(db_session, auth_user_856, monkeypatch):
    """Once lockout duration expires, login succeeds again."""
    monkeypatch.setattr(
        ConfigService,
        "get",
        lambda key: 2 if key == "max_login_attempts" else (10 if key == "lockout_duration_seconds" else "TERM-TEST-2"),
    )

    # Trigger lockout
    AuthService.login("0000")
    AuthService.login("0000")
    assert AuthService.get_terminal_lockout_seconds() > 0
    assert AuthService.login("1234") is None

    # Simulate time passing past lockout expiration
    future_time = datetime.now() + timedelta(seconds=15)
    with patch("cbpos.core.services.auth_service.datetime") as mock_dt:
        mock_dt.now.return_value = future_time
        assert AuthService.get_terminal_lockout_seconds() == 0
        user = AuthService.login("1234")
        assert user is not None
        assert user.username == auth_user_856.username


def test_issue_856_lockout_persists_across_restart(db_session, auth_user_856, monkeypatch):
    """Lockout persists in database and remains active across simulated process restart."""
    monkeypatch.setattr(
        ConfigService,
        "get",
        lambda key: 2 if key == "max_login_attempts" else (300 if key == "lockout_duration_seconds" else "TERM-TEST-3"),
    )

    # Trigger lockout
    AuthService.login("0000")
    AuthService.login("0000")
    assert AuthService.get_terminal_lockout_seconds() > 0

    # Simulate restart by resetting AuthService in-memory state
    AuthService._current_user = None

    # Terminal must still be locked out from DB state
    assert AuthService.get_terminal_lockout_seconds() > 0
    assert AuthService.login("1234") is None


def test_issue_856_lockout_writes_audit_row(db_session, auth_user_856, monkeypatch):
    """When a terminal is locked out, an AuditLog row with event_type='LOCKOUT' is written."""
    terminal_id = "TERM-TEST-AUDIT"
    monkeypatch.setattr(
        ConfigService,
        "get",
        lambda key: 2 if key == "max_login_attempts" else (300 if key == "lockout_duration_seconds" else terminal_id),
    )

    AuthService.login("0000")
    AuthService.login("0000")

    lockout_logs = (
        db_session.query(AuditLog).filter(AuditLog.event_type == "LOCKOUT", AuditLog.terminal_id == terminal_id).all()
    )
    assert len(lockout_logs) == 1
    assert lockout_logs[0].user_id is None
    assert "wrong PINs" in (lockout_logs[0].details or "")


def test_issue_856_override_attempts_count_toward_lockout(db_session, auth_user_856, monkeypatch):
    """Failed manager override attempts count toward the same terminal lockout."""
    terminal_id = "TERM-TEST-OVERRIDE"
    monkeypatch.setattr(
        ConfigService,
        "get",
        lambda key: 2 if key == "max_login_attempts" else (300 if key == "lockout_duration_seconds" else terminal_id),
    )

    assert AuthService.authenticate_pin("9999") is None
    assert AuthService.authenticate_pin("9999") is None

    assert AuthService.get_terminal_lockout_seconds() > 0
    assert AuthService.authenticate_pin("1234") is None
    assert AuthService.login("1234") is None
