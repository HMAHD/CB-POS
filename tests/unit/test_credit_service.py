"""
Unit tests for CustomerCreditService — credit ledger, payments, limits.

Tests credit ledger entries, payment allocation, credit limit enforcement,
balance adjustments, and ledger querying.
"""

from decimal import Decimal

import pytest

from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.models import Customer, User, Role, Permission, CustomerLedgerEntry


def _setup_user(db_session, suffix="credit"):
    """Create a test user for credit operations."""
    permission = Permission(code=f"credit_{suffix}")
    role = Role(name=f"Cashier_{suffix}", permissions=[permission])
    user = User(username=f"cashier_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


def _setup_customer(db_session, name="Test Customer", credit_limit=5000, current_debt=0, payment_terms=30):
    """Create a test customer with credit settings."""
    customer = Customer(
        name=name,
        credit_limit=Decimal(str(credit_limit)),
        current_debt=Decimal(str(current_debt)),
        payment_terms=payment_terms,
    )
    db_session.add(customer)
    db_session.flush()
    return customer


# ── Record Payment ───────────────────────────────────────────────────────


class TestRecordPayment:
    """Tests for recording customer payments."""

    def test_record_payment_reduces_debt(self, db_session):
        """Payment reduces customer's current_debt."""
        user = _setup_user(db_session, "pay1")
        customer = _setup_customer(db_session, "Pay Customer", current_debt=1000)
        db_session.commit()

        payment = CustomerCreditService.record_payment(
            customer_id=customer.id,
            amount=Decimal("300.00"),
            payment_method="Cash",
            user_id=user.id,
        )

        assert payment is not None
        assert payment.amount == Decimal("300.00")

        db_session.refresh(customer)
        assert customer.current_debt == Decimal("700.00")

    def test_record_payment_creates_ledger_entry(self, db_session):
        """Payment creates a PAYMENT ledger entry with negative amount."""
        user = _setup_user(db_session, "pay2")
        customer = _setup_customer(db_session, "Ledger Customer", current_debt=500)
        db_session.commit()

        CustomerCreditService.record_payment(
            customer_id=customer.id,
            amount=Decimal("200.00"),
            payment_method="Card",
            user_id=user.id,
        )

        entries = (
            db_session.query(CustomerLedgerEntry)
            .filter(
                CustomerLedgerEntry.customer_id == customer.id,
                CustomerLedgerEntry.entry_type == "PAYMENT",
            )
            .all()
        )

        assert len(entries) == 1
        assert entries[0].amount == Decimal("-200.00")
        assert entries[0].balance_after == Decimal("300.00")

    def test_record_payment_zero_amount_raises(self, db_session):
        """Payment with zero amount raises ValueError."""
        user = _setup_user(db_session, "pay3")
        customer = _setup_customer(db_session, "Zero Pay", current_debt=100)
        db_session.commit()

        with pytest.raises(ValueError, match="greater than zero"):
            CustomerCreditService.record_payment(
                customer_id=customer.id,
                amount=Decimal("0"),
                payment_method="Cash",
                user_id=user.id,
            )

    def test_record_payment_exceeds_debt_raises(self, db_session):
        """Payment exceeding current debt raises ValueError."""
        user = _setup_user(db_session, "pay4")
        customer = _setup_customer(db_session, "Over Pay", current_debt=100)
        db_session.commit()

        with pytest.raises(ValueError, match="exceeds outstanding debt"):
            CustomerCreditService.record_payment(
                customer_id=customer.id,
                amount=Decimal("500.00"),
                payment_method="Cash",
                user_id=user.id,
            )

    def test_record_payment_exact_amount_clears_debt(self, db_session):
        """Paying exactly the outstanding debt brings balance to zero."""
        user = _setup_user(db_session, "pay5")
        customer = _setup_customer(db_session, "Full Pay", current_debt=250)
        db_session.commit()

        CustomerCreditService.record_payment(
            customer_id=customer.id,
            amount=Decimal("250.00"),
            payment_method="Transfer",
            user_id=user.id,
        )

        db_session.refresh(customer)
        assert customer.current_debt == Decimal("0.00")

    def test_record_payment_invalid_customer_raises(self, db_session):
        """Payment for non-existent customer raises ValueError."""
        user = _setup_user(db_session, "pay6")
        db_session.commit()

        with pytest.raises(ValueError, match="Customer not found"):
            CustomerCreditService.record_payment(
                customer_id=999999,
                amount=Decimal("100.00"),
                payment_method="Cash",
                user_id=user.id,
            )


# ── Record Credit Sale ───────────────────────────────────────────────────


class TestRecordCreditSale:
    """Tests for recording credit sale ledger entries."""

    def test_record_credit_sale_creates_ledger_entry(self, db_session):
        """Credit sale creates a SALE ledger entry."""
        user = _setup_user(db_session, "cs1")
        customer = _setup_customer(db_session, "Credit Sale Cust", current_debt=0)
        db_session.commit()

        CustomerCreditService.record_credit_sale(
            customer_id=customer.id,
            sale_id=42,
            amount=Decimal("750.00"),
            doc_number="REC-CS-001",
            user_id=user.id,
        )
        db_session.commit()

        entries = (
            db_session.query(CustomerLedgerEntry)
            .filter(
                CustomerLedgerEntry.customer_id == customer.id,
                CustomerLedgerEntry.entry_type == "SALE",
            )
            .all()
        )

        assert len(entries) == 1
        assert entries[0].amount == Decimal("750.00")
        assert entries[0].reference_doc == "REC-CS-001"

    def test_record_credit_sale_nonexistent_customer(self, db_session):
        """Credit sale for non-existent customer logs warning but doesn't crash."""
        user = _setup_user(db_session, "cs2")
        db_session.commit()

        # Should not raise — just logs warning and returns
        CustomerCreditService.record_credit_sale(
            customer_id=999999,
            sale_id=1,
            amount=Decimal("100.00"),
            doc_number="REC-GHOST",
            user_id=user.id,
        )


# ── Record Adjustment ────────────────────────────────────────────────────


class TestRecordAdjustment:
    """Tests for balance adjustments."""

    def test_positive_adjustment_increases_debt(self, db_session):
        """Positive adjustment increases customer debt."""
        user = _setup_user(db_session, "adj1")
        customer = _setup_customer(db_session, "Adj Cust Up", current_debt=500)
        db_session.commit()

        result = CustomerCreditService.record_adjustment(
            customer_id=customer.id,
            amount=Decimal("200.00"),
            note="Correction for missed invoice",
            user_id=user.id,
        )

        assert result is True
        db_session.refresh(customer)
        assert customer.current_debt == Decimal("700.00")

    def test_negative_adjustment_decreases_debt(self, db_session):
        """Negative adjustment decreases customer debt."""
        user = _setup_user(db_session, "adj2")
        customer = _setup_customer(db_session, "Adj Cust Down", current_debt=500)
        db_session.commit()

        result = CustomerCreditService.record_adjustment(
            customer_id=customer.id,
            amount=Decimal("-200.00"),
            note="Goodwill credit",
            user_id=user.id,
        )

        assert result is True
        db_session.refresh(customer)
        assert customer.current_debt == Decimal("300.00")

    def test_adjustment_cannot_go_below_zero(self, db_session):
        """Large negative adjustment caps debt at zero, not negative."""
        user = _setup_user(db_session, "adj3")
        customer = _setup_customer(db_session, "Adj Cust Floor", current_debt=100)
        db_session.commit()

        CustomerCreditService.record_adjustment(
            customer_id=customer.id,
            amount=Decimal("-500.00"),
            note="Big write-off",
            user_id=user.id,
        )

        db_session.refresh(customer)
        assert customer.current_debt == Decimal("0.00")

    def test_adjustment_creates_ledger_entry(self, db_session):
        """Adjustment creates an ADJUSTMENT ledger entry."""
        user = _setup_user(db_session, "adj4")
        customer = _setup_customer(db_session, "Adj Cust Ledger", current_debt=300)
        db_session.commit()

        CustomerCreditService.record_adjustment(
            customer_id=customer.id,
            amount=Decimal("100.00"),
            note="Late fee",
            user_id=user.id,
        )

        entries = (
            db_session.query(CustomerLedgerEntry)
            .filter(
                CustomerLedgerEntry.customer_id == customer.id,
                CustomerLedgerEntry.entry_type == "ADJUSTMENT",
            )
            .all()
        )

        assert len(entries) == 1
        assert entries[0].amount == Decimal("100.00")
        assert entries[0].note == "Late fee"

    def test_adjustment_empty_note_raises(self, db_session):
        """Adjustment without note raises ValueError."""
        user = _setup_user(db_session, "adj5")
        customer = _setup_customer(db_session, "Adj No Note", current_debt=100)
        db_session.commit()

        with pytest.raises(ValueError, match="note is required"):
            CustomerCreditService.record_adjustment(
                customer_id=customer.id,
                amount=Decimal("50.00"),
                note="",
                user_id=user.id,
            )


# ── Get Ledger ───────────────────────────────────────────────────────────


class TestGetLedger:
    """Tests for retrieving customer ledger entries."""

    def test_get_ledger_returns_entries(self, db_session):
        """Get ledger returns all entries for a customer."""
        user = _setup_user(db_session, "led1")
        customer = _setup_customer(db_session, "Ledger Query", current_debt=500)
        db_session.commit()

        # Create two payments
        CustomerCreditService.record_payment(
            customer_id=customer.id,
            amount=Decimal("100.00"),
            payment_method="Cash",
            user_id=user.id,
        )
        CustomerCreditService.record_payment(
            customer_id=customer.id,
            amount=Decimal("50.00"),
            payment_method="Card",
            user_id=user.id,
        )

        entries = CustomerCreditService.get_ledger(customer.id)
        assert len(entries) == 2

    def test_get_ledger_empty_customer(self, db_session):
        """Get ledger for customer with no entries returns empty list."""
        customer = _setup_customer(db_session, "Empty Ledger")
        db_session.commit()

        entries = CustomerCreditService.get_ledger(customer.id)
        assert entries == []

    def test_get_ledger_ordered_by_timestamp(self, db_session):
        """Ledger entries are returned in chronological order."""
        user = _setup_user(db_session, "led2")
        customer = _setup_customer(db_session, "Ordered Ledger", current_debt=1000)
        db_session.commit()

        # Create entries
        CustomerCreditService.record_payment(
            customer_id=customer.id,
            amount=Decimal("100.00"),
            payment_method="Cash",
            user_id=user.id,
        )
        CustomerCreditService.record_payment(
            customer_id=customer.id,
            amount=Decimal("200.00"),
            payment_method="Card",
            user_id=user.id,
        )

        entries = CustomerCreditService.get_ledger(customer.id)
        # Should be chronologically ordered (earliest first)
        assert len(entries) >= 2
        for i in range(len(entries) - 1):
            assert entries[i].timestamp <= entries[i + 1].timestamp


# ── Customer Summary ─────────────────────────────────────────────────────


class TestCustomerSummary:
    """Tests for customer credit summary."""

    def test_summary_returns_expected_keys(self, db_session):
        """Summary dict contains all expected fields."""
        customer = _setup_customer(db_session, "Summary Cust", credit_limit=5000, current_debt=1000)
        db_session.commit()

        summary = CustomerCreditService.get_customer_summary(customer.id)

        assert "current_debt" in summary
        assert "credit_limit" in summary
        assert "available" in summary
        assert "total_purchases" in summary
        assert "total_payments" in summary

    def test_summary_available_credit(self, db_session):
        """Available credit = limit - debt."""
        customer = _setup_customer(db_session, "Available Cust", credit_limit=5000, current_debt=2000)
        db_session.commit()

        summary = CustomerCreditService.get_customer_summary(customer.id)
        assert summary["available"] == Decimal("3000.00")

    def test_summary_nonexistent_customer(self, db_session):
        """Summary for non-existent customer returns empty dict."""
        summary = CustomerCreditService.get_customer_summary(999999)
        assert summary == {}
