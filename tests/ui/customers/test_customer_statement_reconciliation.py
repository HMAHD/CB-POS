from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.models import Customer
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.statement_service import StatementService
from cbpos.ui.dialogs.customer_statement_dialog import CustomerStatementDialog

pytestmark = pytest.mark.usefixtures("qapp")


def test_statement_reconciles_sales_payments_and_adjustments(db_session):
    customer = Customer(
        name="Reconcile Cust",
        phone="0779998888",
        credit_limit=Decimal("15000.00"),
        current_debt=Decimal("2500.00"),
    )
    db_session.add(customer)
    db_session.flush()

    CustomerCreditService.backfill_missing_ledger_entries(db_session)

    # Record adjustment: -200 discount
    CustomerCreditService.record_adjustment(
        customer_id=customer.id,
        amount=Decimal("-200.00"),
        note="Goodwill discount",
        user_id=1,
    )

    stmt = StatementService.generate_statement(
        customer.id,
        datetime.now() - timedelta(days=60),
        datetime.now() + timedelta(days=1),
    )

    assert "total_sales" in stmt
    assert "total_payments" in stmt
    assert "net_adjustments" in stmt
    assert stmt["net_adjustments"] == Decimal("-200.00")

    # 5-Way Reconciliation: Opening + Sales - Payments + Net Adjustments == Closing
    reconciled = stmt["opening_balance"] + stmt["total_sales"] - stmt["total_payments"] + stmt["net_adjustments"]
    assert reconciled == stmt["closing_balance"]


def test_customer_statement_dialog_shows_phone_number(db_session):
    customer = Customer(
        name="Phone Test Customer",
        phone="0771234567",
        credit_limit=Decimal("5000.00"),
        current_debt=Decimal("0.00"),
    )
    db_session.add(customer)
    db_session.flush()

    dialog = CustomerStatementDialog(customer)
    try:
        assert hasattr(dialog, "lbl_phone")
        assert "0771234567" in dialog.lbl_phone.text()
    finally:
        dialog.deleteLater()
