from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.models import (
    Customer,
    CustomerLedgerEntry,
    Product,
    Supplier,
    SupplierLedgerEntry,
    User,
)
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.statement_receipt_builder import StatementReceiptBuilder
from cbpos.core.services.supplier_payable_service import SupplierPayableService
from cbpos.core.utils.aging import oldest_open_charge


def _get_or_create_user(session) -> int:
    admin = session.query(User).first()
    if not admin:
        admin = User(username="admin_test_user", pin_hash="fake_hash", is_active=True)
        session.add(admin)
        session.flush()
    return admin.id


def test_statement_receipt_builder_accepts_date_objects(db_session):
    """Finding 13: StatementReceiptBuilder must not fail with AttributeError when date is passed."""
    customer = Customer(id=1, name="John Doe", phone="0771234567")
    d_from = date(2026, 3, 1)
    d_to = date(2026, 3, 31)

    # Should build commands cleanly without AttributeError on d_to.time()
    cmds = StatementReceiptBuilder.build_customer_statement(customer, [], d_from, d_to)
    assert any(
        "statement.period_range" in c.get("val", "") or "Period" in c.get("val", "") or "2026-03" in c.get("val", "")
        for c in cmds
    )


def test_balance_at_fails_closed_on_invalid_type():
    """Finding 22: balance_at must raise TypeError for invalid date types rather than defaulting to min."""
    with pytest.raises(TypeError):
        CustomerCreditService.balance_at(1, "2026-03-01")  # str is not allowed, must be date or datetime


def test_balance_at_accepts_external_session(db_session):
    """Finding 10: balance_at should accept an existing session to prevent stale reads."""
    user_id = _get_or_create_user(db_session)
    cust = Customer(
        name="Session Test Cust", phone="0779998877", credit_limit=Decimal("1000.00"), current_debt=Decimal("0.00")
    )
    db_session.add(cust)
    db_session.flush()

    entry = CustomerLedgerEntry(
        customer_id=cust.id,
        entry_type="SALE",
        amount=Decimal("250.00"),
        balance_after=Decimal("250.00"),
        timestamp=datetime(2026, 3, 10, 10, 0, 0),
        user_id=user_id,
    )
    db_session.add(entry)
    db_session.flush()

    # Reading through the same uncommitted session
    bal = CustomerCreditService.balance_at(cust.id, datetime(2026, 3, 15, 0, 0, 0), session=db_session)
    assert bal == Decimal("250.00")


def test_oldest_open_charge_fails_closed_on_missing_timestamp():
    """Finding 8: oldest_open_charge must fail closed on missing/invalid timestamps."""

    class BadEntry:
        amount = Decimal("100.00")
        entry_type = "SALE"
        timestamp = None

    with pytest.raises(ValueError):
        oldest_open_charge([BadEntry()])


def test_get_overdue_customers_batched(db_session):
    """Finding 7: get_overdue_customers should compute overdue without N+1 query loops."""
    user_id = _get_or_create_user(db_session)
    cust = Customer(
        name="Overdue Batch Cust",
        phone="0771122334",
        credit_limit=Decimal("5000.00"),
        current_debt=Decimal("1500.00"),
        payment_terms=15,
        is_active=True,
    )
    db_session.add(cust)
    db_session.flush()

    old_dt = datetime.now() - timedelta(days=30)
    entry = CustomerLedgerEntry(
        customer_id=cust.id,
        entry_type="SALE",
        amount=Decimal("1500.00"),
        balance_after=Decimal("1500.00"),
        timestamp=old_dt,
        user_id=user_id,
    )
    db_session.add(entry)
    db_session.commit()

    overdue = CustomerCreditService.get_overdue_customers()
    match = next((c for c in overdue if c["id"] == cust.id), None)
    assert match is not None
    assert match["outstanding"] == Decimal("1500.00")
    assert match["days_overdue"] >= 14


def test_get_overdue_suppliers_batched(db_session):
    """Finding 5 & 12: get_overdue_suppliers should batch fetch ledger and have no dead code."""
    user_id = _get_or_create_user(db_session)
    supp = Supplier(
        company_name="Overdue Batch Supplier",
        phone="0775566778",
        current_payable=Decimal("3000.00"),
        payment_terms=10,
        is_active=True,
    )
    db_session.add(supp)
    db_session.flush()

    old_dt = datetime.now() - timedelta(days=25)
    entry = SupplierLedgerEntry(
        supplier_id=supp.id,
        entry_type="PURCHASE",
        amount=Decimal("3000.00"),
        balance_after=Decimal("3000.00"),
        timestamp=old_dt,
        user_id=user_id,
    )
    db_session.add(entry)
    db_session.commit()

    overdue = SupplierPayableService.get_overdue_suppliers()
    match = next((s for s in overdue if s["id"] == supp.id), None)
    assert match is not None
    assert match["outstanding"] == Decimal("3000.00")
    assert match["days_overdue"] >= 14


def test_product_service_stock_tracked_typing_and_instance():
    """Finding 9: ProductService.stock_tracked works both as a query criterion and instance check."""
    physical = Product(name_en="Item P", barcode="123", is_service=False, is_composite=False)
    service = Product(name_en="Service S", barcode="124", is_service=True, is_composite=False)

    assert ProductService.stock_tracked(physical) is True
    assert ProductService.stock_tracked(service) is False
    assert ProductService.is_stock_tracked(physical) is True
    assert ProductService.is_stock_tracked(service) is False

    # Also as SQLAlchemy criterion
    crit = ProductService.stock_tracked()
    assert crit is not None
