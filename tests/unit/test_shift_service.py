"""
Unit tests for ShiftService — shift lifecycle (start, get, close).
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.status import ShiftStatus
from cbpos.core.models import Permission, Role, Shift, User
from cbpos.core.services.shift_service import ShiftService

# ── Shared Fixtures ──────────────────────────────────────────────────────

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_user(db_session):
    """Create a test user for shift tests."""
    suffix = _next_suffix()
    permission = Permission(code=f"shift_test_{suffix}")
    role = Role(name=f"ShiftRole_{suffix}", permissions=[permission])
    user = User(username=f"shift_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def shift_service():
    """Create a ShiftService instance."""
    return ShiftService()


# ── Test: start_shift ────────────────────────────────────────────────────


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_start_shift(mock_config, db_session, test_user, shift_service):
    """Starting a shift creates a new open shift with the float amount."""
    shift = shift_service.start_shift(test_user.id, Decimal("5000.00"))

    assert shift is not None
    assert shift.user_id == test_user.id
    assert shift.starting_cash == Decimal("5000.00")
    assert shift.status == ShiftStatus.OPEN
    assert shift.terminal_id == "TERM-01"


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_start_shift_duplicate(mock_config, db_session, test_user, shift_service):
    """Starting a shift when one is already open raises ValueError."""
    shift_service.start_shift(test_user.id, Decimal("5000.00"))

    with pytest.raises(ValueError, match="already has an open shift"):
        shift_service.start_shift(test_user.id, Decimal("3000.00"))


# ── Test: get_current_shift ──────────────────────────────────────────────


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_get_current_shift(mock_config, db_session, test_user, shift_service):
    """get_current_shift returns the open shift for the user."""
    shift_service.start_shift(test_user.id, Decimal("5000.00"))

    current = shift_service.get_current_shift(test_user.id)

    assert current is not None
    assert current.user_id == test_user.id
    assert current.status == ShiftStatus.OPEN


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_get_current_shift_none(mock_config, db_session, test_user, shift_service):
    """get_current_shift returns None when no shift is open."""
    current = shift_service.get_current_shift(test_user.id)
    assert current is None


# ── Test: close_shift ────────────────────────────────────────────────────


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_close_shift(mock_config, db_session, test_user, shift_service):
    """Closing a shift sets status to CLOSED and returns summary with variance."""
    shift = shift_service.start_shift(test_user.id, Decimal("5000.00"))

    summary = shift_service.close_shift(shift.id, counted_cash=Decimal("5200.00"), notes="All good")

    assert summary is not None
    assert summary["starting_cash"] == Decimal("5000.00")
    assert summary["actual_cash"] == Decimal("5200.00")
    assert summary["variance"] == Decimal("200.00")
    assert summary["notes"] == "All good"
    assert summary["end_time"] is not None

    # Verify shift is now closed in DB
    db_session.expire_all()
    closed_shift = db_session.get(Shift, shift.id)
    assert closed_shift.status == ShiftStatus.CLOSED
