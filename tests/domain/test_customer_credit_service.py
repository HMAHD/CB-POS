"""
Unit tests for CustomerCreditService — credit payments, adjustments, and ledger.
"""

from decimal import Decimal

import pytest

from cbpos.core.models import Customer, CustomerLedgerEntry, Permission, Role, User
from cbpos.core.services.customer_credit_service import CustomerCreditService

# ── Shared Fixtures ──────────────────────────────────────────────────────

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    suffix = _next_suffix()
    permission = Permission(code=f"credit_test_{suffix}")
    role = Role(name=f"CreditRole_{suffix}", permissions=[permission])
    user = User(username=f"credit_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_customer(db_session):
    """Create a test customer with credit limit and existing debt."""
    suffix = _next_suffix()
    customer = Customer(
        name=f"Test Customer {suffix}",
        credit_limit=Decimal("10000.00"),
        current_debt=Decimal("5000.00"),
        payment_terms=30,
    )
    db_session.add(customer)
    db_session.flush()
    return customer


@pytest.fixture
def zero_debt_customer(db_session):
    """Create a test customer with zero debt."""
    suffix = _next_suffix()
    customer = Customer(
        name=f"Zero Debt Customer {suffix}",
        credit_limit=Decimal("5000.00"),
        current_debt=Decimal("0.00"),
    )
    db_session.add(customer)
    db_session.flush()
    return customer


# ── Test: record_payment ─────────────────────────────────────────────────


def test_record_payment_success(db_session, test_user, test_customer):
    """Payment reduces customer debt and creates ledger entry."""
    payment = CustomerCreditService.record_payment(
        customer_id=test_customer.id,
        amount=Decimal("1000.00"),
        payment_method="Cash",
        user_id=test_user.id,
        note="Monthly payment",
    )

    assert payment is not None
    assert payment.amount == Decimal("1000.00")

    db_session.refresh(test_customer)
    assert test_customer.current_debt == Decimal("4000.00")

    # Verify ledger entry was created
    entries = db_session.query(CustomerLedgerEntry).filter(CustomerLedgerEntry.customer_id == test_customer.id).all()
    assert len(entries) == 1
    assert entries[0].entry_type == "PAYMENT"
    assert entries[0].amount == Decimal("-1000.00")
    assert entries[0].balance_after == Decimal("4000.00")


def test_record_payment_exceeds_debt(db_session, test_user, test_customer):
    """Payment exceeding outstanding debt raises ValueError."""
    with pytest.raises(ValueError, match="exceeds outstanding debt"):
        CustomerCreditService.record_payment(
            customer_id=test_customer.id,
            amount=Decimal("6000.00"),
            payment_method="Cash",
            user_id=test_user.id,
        )


def test_record_payment_zero_amount(db_session, test_user, test_customer):
    """Zero payment amount raises ValueError."""
    with pytest.raises(ValueError, match="greater than zero"):
        CustomerCreditService.record_payment(
            customer_id=test_customer.id,
            amount=Decimal("0.00"),
            payment_method="Cash",
            user_id=test_user.id,
        )


# ── Test: record_credit_sale ─────────────────────────────────────────────


def test_record_credit_sale(db_session, test_user, test_customer):
    """Credit sale increases customer debt and creates SALE ledger entry."""
    CustomerCreditService.record_credit_sale(
        customer_id=test_customer.id,
        sale_id=999,
        amount=Decimal("2500.00"),
        doc_number="REC-TEST-001",
        user_id=test_user.id,
    )

    db_session.refresh(test_customer)
    assert test_customer.current_debt == Decimal("7500.00")

    entries = (
        db_session.query(CustomerLedgerEntry)
        .filter(
            CustomerLedgerEntry.customer_id == test_customer.id,
            CustomerLedgerEntry.entry_type == "SALE",
        )
        .all()
    )
    assert len(entries) == 1
    assert entries[0].amount == Decimal("2500.00")
    assert entries[0].balance_after == Decimal("7500.00")


# ── Test: record_adjustment ──────────────────────────────────────────────


def test_record_adjustment_positive(db_session, test_user, test_customer):
    """Positive adjustment increases debt."""
    result = CustomerCreditService.record_adjustment(
        customer_id=test_customer.id,
        amount=Decimal("500.00"),
        note="Correction: missed invoice",
        user_id=test_user.id,
    )

    assert result is True

    db_session.refresh(test_customer)
    assert test_customer.current_debt == Decimal("5500.00")

    entries = (
        db_session.query(CustomerLedgerEntry)
        .filter(
            CustomerLedgerEntry.customer_id == test_customer.id,
            CustomerLedgerEntry.entry_type == "ADJUSTMENT",
        )
        .all()
    )
    assert len(entries) == 1
    assert entries[0].amount == Decimal("500.00")


def test_record_adjustment_negative(db_session, test_user, test_customer):
    """Negative adjustment decreases debt, floored at zero."""
    # Adjust by more than current debt — should floor at 0
    result = CustomerCreditService.record_adjustment(
        customer_id=test_customer.id,
        amount=Decimal("-9999.00"),
        note="Write-off",
        user_id=test_user.id,
    )

    assert result is True

    db_session.refresh(test_customer)
    assert test_customer.current_debt == Decimal("0.00")


# ── Test: get_ledger ─────────────────────────────────────────────────────


def test_get_ledger(db_session, test_user, test_customer):
    """get_ledger returns entries in chronological order."""
    # Create multiple ledger entries via service calls
    CustomerCreditService.record_credit_sale(
        customer_id=test_customer.id,
        sale_id=100,
        amount=Decimal("1000.00"),
        doc_number="REC-L-001",
        user_id=test_user.id,
    )
    CustomerCreditService.record_payment(
        customer_id=test_customer.id,
        amount=Decimal("500.00"),
        payment_method="Cash",
        user_id=test_user.id,
    )

    entries = CustomerCreditService.get_ledger(test_customer.id)

    assert len(entries) == 2
    assert entries[0].entry_type == "SALE"
    assert entries[1].entry_type == "PAYMENT"
    # Verify chronological order
    assert entries[0].timestamp <= entries[1].timestamp


def test_issue_849_refund_of_overcredited_sale_reverses_at_most_total(db_session, test_user):
    """Refunding an over-credited legacy sale reverses at most the sale's total amount."""
    from cbpos.core.constants.status import PaymentMethodKind
    from cbpos.core.models import Sale, SalePayment

    customer = Customer(
        name="Overcredit Customer",
        credit_limit=Decimal("10000.00"),
        current_debt=Decimal("2000.00"),
    )
    db_session.add(customer)
    db_session.flush()

    # Legacy sale directly inserted: total 1000.00, credit payment 1200.00
    sale = Sale(
        document_number="INV-LEGACY-001",
        total_amount=Decimal("1000.00"),
        payment_method="Credit",
        customer_id=customer.id,
        user_id=test_user.id,
    )
    db_session.add(sale)
    db_session.flush()

    payment = SalePayment(
        sale_id=sale.id,
        payment_method="Credit",
        method_kind=PaymentMethodKind.CREDIT,
        amount=Decimal("1200.00"),
    )
    db_session.add(payment)
    db_session.commit()

    entry = CustomerCreditService.reverse_credit_sale_in_session(
        session=db_session,
        sale=sale,
        entry_type="REFUND",
        user_id=test_user.id,
        reference_doc="REF-LEGACY-001",
    )
    db_session.commit()

    assert entry is not None
    assert entry.amount == Decimal("-1000.00")
    db_session.refresh(customer)
    assert customer.current_debt == Decimal("1000.00")
