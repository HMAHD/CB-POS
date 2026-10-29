from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.models import Customer
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.loyalty_service import LoyaltyService
from cbpos.core.services.statement_service import StatementService

pytestmark = pytest.mark.usefixtures("qapp")


def test_create_customer_with_debt_writes_opening_ledger_entry(db_session):
    service = CustomerService()
    cust = service.create_customer(
        {
            "name": "New Debt Cust",
            "current_debt": Decimal("3000.00"),
            "credit_limit": Decimal("10000.00"),
        }
    )
    entries = CustomerCreditService.get_ledger(cust.id)
    assert len(entries) == 1
    assert entries[0].entry_type == "OPENING"
    assert entries[0].amount == Decimal("3000.00")
    assert entries[0].balance_after == Decimal("3000.00")
    assert entries[0].reference_doc == "INIT-BAL"


def test_create_customer_with_points_writes_opening_loyalty_entry(db_session):
    service = CustomerService()
    cust = service.create_customer(
        {
            "name": "New Points Cust",
            "loyalty_points": 150,
        }
    )
    history = LoyaltyService.get_points_history(cust.id)
    assert len(history) == 1
    assert history[0].entry_type == "OPENING"
    assert history[0].points == 150
    assert history[0].balance_after == 150


def test_backfill_missing_ledger_entries_is_idempotent(db_session):
    # Customer directly inserted without ledger entry
    cust = Customer(
        name="Direct Cust",
        current_debt=Decimal("1500.00"),
        credit_limit=Decimal("5000.00"),
    )
    db_session.add(cust)
    db_session.flush()

    assert len(CustomerCreditService.get_ledger(cust.id)) == 0

    # First backfill run inserts entry
    count1 = CustomerCreditService.backfill_missing_ledger_entries()
    assert count1 >= 1
    entries = CustomerCreditService.get_ledger(cust.id)
    assert len(entries) == 1
    assert entries[0].entry_type == "OPENING"
    assert entries[0].amount == Decimal("1500.00")

    # Second run does not duplicate
    count2 = CustomerCreditService.backfill_missing_ledger_entries()
    assert count2 == 0
    assert len(CustomerCreditService.get_ledger(cust.id)) == 1


def test_backfill_missing_loyalty_entries_is_idempotent(db_session):
    cust = Customer(
        name="Direct Points Cust",
        loyalty_points=250,
    )
    db_session.add(cust)
    db_session.flush()

    assert len(LoyaltyService.get_points_history(cust.id)) == 0

    count1 = LoyaltyService.backfill_missing_loyalty_entries()
    assert count1 >= 1
    history = LoyaltyService.get_points_history(cust.id)
    assert len(history) == 1
    assert history[0].entry_type == "OPENING"
    assert history[0].points == 250

    count2 = LoyaltyService.backfill_missing_loyalty_entries()
    assert count2 == 0
    assert len(LoyaltyService.get_points_history(cust.id)) == 1


def test_historical_statement_before_opening_balance_is_pure_zero(db_session):
    # Customer created with opening balance dated 30 days ago
    past_date = datetime.now() - timedelta(days=30)
    cust = Customer(
        name="Historical Cust",
        current_debt=Decimal("2000.00"),
        credit_limit=Decimal("5000.00"),
        last_modified=past_date,
    )
    db_session.add(cust)
    db_session.flush()

    CustomerCreditService.backfill_missing_ledger_entries()

    # Query for period 90 days ago to 60 days ago (prior to opening date)
    stmt_past = StatementService.generate_statement(
        cust.id,
        datetime.now() - timedelta(days=90),
        datetime.now() - timedelta(days=60),
    )
    assert stmt_past["opening_balance"] == Decimal("0")
    assert stmt_past["closing_balance"] == Decimal("0")
    assert len(stmt_past["entries"]) == 0

    # Query for period covering today (after opening date)
    stmt_current = StatementService.generate_statement(
        cust.id,
        datetime.now() - timedelta(days=40),
        datetime.now() + timedelta(days=1),
    )
    assert stmt_current["closing_balance"] == Decimal("2000.00")
    assert len(stmt_current["entries"]) == 1
