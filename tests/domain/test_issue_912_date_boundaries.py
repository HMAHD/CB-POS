"""Regression tests for Issue #912: Date filters drop the last second of the day."""

from datetime import date, datetime
from decimal import Decimal

from cbpos.core.models import Customer, CustomerLedgerEntry, Permission, Role, User
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.statement_service import StatementService


def _create_customer_and_user(db_session):
    customer = Customer(
        name="Issue 912 Customer",
        phone="0779120000",
        current_debt=Decimal("1000.00"),
        credit_limit=Decimal("10000.00"),
    )
    perm = Permission(code="test_perm_912")
    role = Role(name="TestRole_912", permissions=[perm])
    user = User(username="test_user_912", pin_hash="hash", role=role)
    db_session.add_all([customer, perm, role, user])
    db_session.flush()
    return customer, user


def test_issue_912_entry_at_235959_5_in_day_statement(db_session):
    """A ledger entry at 23:59:59.5 appears in that day's statement."""
    customer, user = _create_customer_and_user(db_session)

    # Entry at 23:59:59.500000
    target_dt = datetime(2026, 11, 9, 23, 59, 59, 500000)
    entry = CustomerLedgerEntry(
        customer_id=customer.id,
        entry_type="SALE",
        amount=Decimal("250.00"),
        balance_after=Decimal("250.00"),
        user_id=user.id,
        timestamp=target_dt,
        reference_doc="INV-912-001",
    )
    db_session.add(entry)
    db_session.flush()

    # Generate statement for the day 2026-11-09 using date objects or datetime with 23:59:59
    result_dates = StatementService.generate_statement(
        customer_id=customer.id,
        date_from=date(2026, 11, 9),
        date_to=date(2026, 11, 9),
    )
    assert len(result_dates["entries"]) == 1
    assert result_dates["entries"][0]["description"] == "INV-912-001"
    assert result_dates["closing_balance"] == Decimal("250.00")

    # Also test with datetime ending at 23:59:59 (legacy UI filter)
    result_dt = StatementService.generate_statement(
        customer_id=customer.id,
        date_from=datetime(2026, 11, 9, 0, 0, 0),
        date_to=datetime(2026, 11, 9, 23, 59, 59),
    )
    assert len(result_dt["entries"]) == 1
    assert result_dt["entries"][0]["description"] == "INV-912-001"


def test_issue_912_get_ledger_boundary(db_session):
    """CustomerCreditService.get_ledger cleanly partitions boundaries with half-open range."""
    customer, user = _create_customer_and_user(db_session)

    # Entry A at last moment of Day 1
    dt_day1 = datetime(2026, 11, 9, 23, 59, 59, 500000)
    entry_a = CustomerLedgerEntry(
        customer_id=customer.id,
        entry_type="SALE",
        amount=Decimal("100.00"),
        balance_after=Decimal("100.00"),
        user_id=user.id,
        timestamp=dt_day1,
        reference_doc="ENTRY-A",
    )
    # Entry B at first moment of Day 2
    dt_day2 = datetime(2026, 11, 10, 0, 0, 0, 0)
    entry_b = CustomerLedgerEntry(
        customer_id=customer.id,
        entry_type="SALE",
        amount=Decimal("200.00"),
        balance_after=Decimal("300.00"),
        user_id=user.id,
        timestamp=dt_day2,
        reference_doc="ENTRY-B",
    )
    db_session.add_all([entry_a, entry_b])
    db_session.flush()

    # Query Day 1
    day1_entries = CustomerCreditService.get_ledger(
        customer_id=customer.id,
        date_from=date(2026, 11, 9),
        date_to=date(2026, 11, 9),
    )
    refs_day1 = [e.reference_doc for e in day1_entries]
    assert "ENTRY-A" in refs_day1
    assert "ENTRY-B" not in refs_day1

    # Query Day 2
    day2_entries = CustomerCreditService.get_ledger(
        customer_id=customer.id,
        date_from=date(2026, 11, 10),
        date_to=date(2026, 11, 10),
    )
    refs_day2 = [e.reference_doc for e in day2_entries]
    assert "ENTRY-A" not in refs_day2
    assert "ENTRY-B" in refs_day2
