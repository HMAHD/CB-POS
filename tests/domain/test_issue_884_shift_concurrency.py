"""Regression tests for Issue #884:
Same cashier on two terminals: shifts count each other's sales.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import DocumentStatus, PaymentMethodType, ShiftStatus
from cbpos.core.models import AuditLog, Permission, Role, Sale, SalePayment, User
from cbpos.core.services.shift_service import ShiftService


@pytest.fixture
def test_user(db_session):
    role = Role(name="CashierRole")
    db_session.add(role)
    db_session.flush()
    user = User(username="cashier_dual", pin_hash="hash", role_id=role.id, is_active=True)
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def manager_user(db_session):
    perm = Permission(code=Permissions.SHIFT_FORCE_CLOSE, description="Force Close", group="Cash")
    db_session.add(perm)
    db_session.flush()
    role = Role(name="ManagerRole", permissions=[perm])
    db_session.add(role)
    db_session.flush()
    user = User(username="manager_dual", pin_hash="hash", role_id=role.id, is_active=True)
    db_session.add(user)
    db_session.flush()
    return user


def test_issue_884_two_open_shifts_same_user(db_session, test_user):
    """Starting a shift on terminal B while one is open on terminal A is allowed; they are independent."""
    service = ShiftService()

    shift1 = service.start_shift(test_user.id, Decimal("1000.00"), terminal_id="TERM-01")
    assert shift1 is not None
    assert shift1.terminal_id == "TERM-01"
    assert shift1.status == ShiftStatus.OPEN

    shift2 = service.start_shift(test_user.id, Decimal("2000.00"), terminal_id="TERM-02")
    assert shift2 is not None
    assert shift2.terminal_id == "TERM-02"
    assert shift2.status == ShiftStatus.OPEN

    # Fetching per-terminal returns the right shift
    assert service.get_open_shift(test_user.id, terminal_id="TERM-01").id == shift1.id
    assert service.get_open_shift(test_user.id, terminal_id="TERM-02").id == shift2.id

    # Starting a duplicate on TERM-01 fails
    with pytest.raises(ValueError, match="already has an open shift"):
        service.start_shift(test_user.id, Decimal("500.00"), terminal_id="TERM-01")


def test_issue_884_term02_sale_not_in_term01_summary(db_session, test_user):
    """A sale on TERM-02 is NOT counted in TERM-01 shift summary, even for the same user and overlapping time."""
    service = ShiftService()

    shift1 = service.start_shift(test_user.id, Decimal("1000.00"), terminal_id="TERM-01")
    shift2 = service.start_shift(test_user.id, Decimal("2000.00"), terminal_id="TERM-02")

    # Sale on TERM-01 stamped with shift1.id
    sale1 = Sale(
        document_number="INV-TERM01-001",
        date=datetime.now(),
        total_amount=Decimal("500.00"),
        status=DocumentStatus.COMPLETED,
        payment_method="CASH",
        user_id=test_user.id,
        terminal_id="TERM-01",
        shift_id=shift1.id,
    )
    db_session.add(sale1)
    db_session.flush()
    db_session.add(SalePayment(sale_id=sale1.id, payment_method=PaymentMethodType.CASH, amount=Decimal("500.00")))

    # Sale on TERM-02 stamped with shift2.id
    sale2 = Sale(
        document_number="INV-TERM02-001",
        date=datetime.now(),
        total_amount=Decimal("800.00"),
        status=DocumentStatus.COMPLETED,
        payment_method="CASH",
        user_id=test_user.id,
        terminal_id="TERM-02",
        shift_id=shift2.id,
    )
    db_session.add(sale2)
    db_session.flush()
    db_session.add(SalePayment(sale_id=sale2.id, payment_method=PaymentMethodType.CASH, amount=Decimal("800.00")))

    # Legacy sales without shift_id
    legacy_sale1 = Sale(
        document_number="INV-LEGACY-001",
        date=datetime.now(),
        total_amount=Decimal("150.00"),
        status=DocumentStatus.COMPLETED,
        payment_method="CASH",
        user_id=test_user.id,
        terminal_id="TERM-01",
        shift_id=None,
    )
    db_session.add(legacy_sale1)
    db_session.flush()
    db_session.add(
        SalePayment(sale_id=legacy_sale1.id, payment_method=PaymentMethodType.CASH, amount=Decimal("150.00"))
    )

    legacy_sale2 = Sale(
        document_number="INV-LEGACY-002",
        date=datetime.now(),
        total_amount=Decimal("350.00"),
        status=DocumentStatus.COMPLETED,
        payment_method="CASH",
        user_id=test_user.id,
        terminal_id="TERM-02",
        shift_id=None,
    )
    db_session.add(legacy_sale2)
    db_session.flush()
    db_session.add(
        SalePayment(sale_id=legacy_sale2.id, payment_method=PaymentMethodType.CASH, amount=Decimal("350.00"))
    )

    db_session.commit()

    # Verify shift 1 summary
    summary1 = service.get_shift_summary(shift1.id)
    # Expected cash: float (1000) + sale1 (500) + legacy_sale1 (150) = 1650
    assert summary1["cash_sales"] == Decimal("650.00")
    assert summary1["expected_cash"] == Decimal("1650.00")
    assert summary1["txn_count"] == 2

    # Verify shift 2 summary
    summary2 = service.get_shift_summary(shift2.id)
    # Expected cash: float (2000) + sale2 (800) + legacy_sale2 (350) = 3150
    assert summary2["cash_sales"] == Decimal("1150.00")
    assert summary2["expected_cash"] == Decimal("3150.00")
    assert summary2["txn_count"] == 2


def test_issue_884_force_close_requires_permission_and_audits(db_session, test_user, manager_user):
    """Force close requires shift.force_close permission, sets status to CLOSED, and audits."""
    service = ShiftService()

    shift = service.start_shift(test_user.id, Decimal("1000.00"), terminal_id="TERM-01")

    # Regular cashier without permission cannot force close
    with pytest.raises(ValueError, match="Permission denied"):
        service.force_close_shift(
            shift.id, counted_cash=Decimal("1000.00"), reason="Forgot to close", closed_by_user_id=test_user.id
        )

    # Manager with shift.force_close can force close
    closed = service.force_close_shift(
        shift.id,
        counted_cash=Decimal("950.00"),
        reason="Cashier went home sick",
        closed_by_user_id=manager_user.id,
    )
    assert closed.status == ShiftStatus.CLOSED
    assert closed.actual_cash == Decimal("950.00")
    assert "Cashier went home sick" in (closed.notes or "")

    # Verify AuditLog written
    audit = db_session.query(AuditLog).filter_by(event_type="SHIFT_FORCE_CLOSED").first()
    assert audit is not None
    assert audit.user_id == manager_user.id
    assert "Cashier went home sick" in audit.details


def test_issue_884_is_shift_stale(db_session, test_user):
    """is_shift_stale checks age > 24 hours or terminal ID mismatch."""
    service = ShiftService()

    # Shift opened on TERM-01
    shift = service.start_shift(test_user.id, Decimal("1000.00"), terminal_id="TERM-01")
    assert not service.is_shift_stale(shift, current_terminal_id="TERM-01")

    # Terminal mismatch is stale
    assert service.is_shift_stale(shift, current_terminal_id="TERM-02")

    # Over 24 hours old is stale even on same terminal
    shift.start_time = datetime.now() - timedelta(hours=25)
    db_session.commit()
    assert service.is_shift_stale(shift, current_terminal_id="TERM-01")
