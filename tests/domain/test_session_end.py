"""Domain tests for session end and logout / timeout behaviour (#860)."""

from types import SimpleNamespace

import pytest

from cbpos.core.models import AuditLog, Role, SuspendedTransaction, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.suspended_transaction_service import SuspendedTransactionService
from cbpos.infrastructure.session_watchdog import SessionWatchdog


@pytest.fixture
def auth_user(db_session):
    """Seed an active user for session testing."""
    role = Role(name="Cashier_Role_860")
    db_session.add(role)
    db_session.flush()

    user = User(
        username="cashier_860",
        pin_hash=AuthService.hash_pin("1234"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_issue_860_logout_clears_auth_and_writes_audit(db_session, auth_user, monkeypatch):
    """AuthService.logout('LOGOUT') clears _current_user and writes LOGOUT audit with terminal_id."""
    monkeypatch.setattr(ConfigService, "get", lambda key: "TILL-7" if key == "terminal_id" else None)

    AuthService._current_user = auth_user

    AuthService.logout("LOGOUT")

    assert AuthService.get_current_user() is None

    log = (
        db_session.query(AuditLog)
        .filter(AuditLog.user_id == auth_user.id, AuditLog.event_type == "LOGOUT")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.action == "User Logout"
    assert log.terminal_id == "TILL-7"


def test_issue_860_timeout_writes_audit_with_configured_terminal(db_session, auth_user, monkeypatch):
    """AuthService.logout('TIMEOUT') clears _current_user and writes TIMEOUT audit with terminal_id."""
    monkeypatch.setattr(ConfigService, "get", lambda key: "TILL-9" if key == "terminal_id" else None)

    AuthService._current_user = auth_user

    AuthService.logout("TIMEOUT")

    assert AuthService.get_current_user() is None

    log = (
        db_session.query(AuditLog)
        .filter(AuditLog.user_id == auth_user.id, AuditLog.event_type == "TIMEOUT")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.action == "Session Timeout"
    assert log.terminal_id == "TILL-9"


def test_issue_860_session_watchdog_does_not_write_db(db_session, auth_user):
    """SessionWatchdog.on_timeout only stops monitoring and emits session_expired, without DB writes."""
    AuthService._current_user = auth_user

    initial_log_count = db_session.query(AuditLog).count()

    watchdog = SessionWatchdog(timeout_minutes=1)
    expired_called = []
    watchdog.session_expired.connect(lambda: expired_called.append(True))

    watchdog.on_timeout()

    assert expired_called == [True]
    # No AuditLog rows written by watchdog itself
    assert db_session.query(AuditLog).count() == initial_log_count

    AuthService._current_user = None


def test_issue_860_end_session_auto_holds_cart_with_note(db_session, auth_user):
    """Ending a session with cart items auto-holds the bill with user note and clears the cart."""
    AuthService._current_user = auth_user

    from decimal import Decimal

    cart = CartService()
    product = SimpleNamespace(id=1, barcode="1234567890123", name_en="Test Item", price=Decimal("100.00"))
    cart.add_item(product, qty=2)
    assert len(cart.items) == 1

    held_id = SuspendedTransactionService.hold_bill(
        cart,
        note=f"Auto-held at sign-out ({auth_user.username})",
    )
    assert held_id is not None

    held = db_session.get(SuspendedTransaction, held_id)
    assert held is not None
    assert held.note == f"Auto-held at sign-out ({auth_user.username})"

    AuthService._current_user = None
