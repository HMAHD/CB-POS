"""Tests for StatementService customer account statements."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from cbpos.core.models import Customer, CustomerLedgerEntry, Permission, Role, User
from cbpos.core.services.statement_service import StatementService


class TestStatementService:
    """Unit tests for StatementService."""

    _phone_counter = 0

    def _create_customer(self, db_session, debt: Decimal = Decimal("0")) -> Customer:
        """Helper to create a test customer."""
        TestStatementService._phone_counter += 1
        customer = Customer(
            name="Test Customer",
            phone=f"077{TestStatementService._phone_counter:07d}",
            current_debt=debt,
            credit_limit=Decimal("10000"),
        )
        db_session.add(customer)
        db_session.flush()
        return customer

    _user_counter = 0

    def _create_user(self, db_session) -> User:
        """Helper to create a test user."""
        TestStatementService._user_counter += 1
        n = TestStatementService._user_counter
        perm = Permission(code=f"test_stmt_{n}")
        role = Role(name=f"TestRole_Stmt_{n}", permissions=[perm])
        user = User(username=f"test_stmt_user_{n}", pin_hash="hash", role=role)
        db_session.add_all([perm, role, user])
        db_session.flush()
        return user

    def test_generate_statement_with_entries(self, db_session):
        """Test statement with ledger entries in range."""
        customer = self._create_customer(db_session, debt=Decimal("500"))
        user = self._create_user(db_session)

        now = datetime.now()
        # Create ledger entries
        e1 = CustomerLedgerEntry(
            customer_id=customer.id,
            entry_type="SALE",
            amount=Decimal("300"),
            balance_after=Decimal("300"),
            user_id=user.id,
            timestamp=now - timedelta(days=5),
            reference_doc="SALE-001",
        )
        e2 = CustomerLedgerEntry(
            customer_id=customer.id,
            entry_type="PAYMENT",
            amount=Decimal("-100"),
            balance_after=Decimal("200"),
            user_id=user.id,
            timestamp=now - timedelta(days=3),
            reference_doc="PAY-001",
        )
        e3 = CustomerLedgerEntry(
            customer_id=customer.id,
            entry_type="SALE",
            amount=Decimal("300"),
            balance_after=Decimal("500"),
            user_id=user.id,
            timestamp=now - timedelta(days=1),
            reference_doc="SALE-002",
        )
        db_session.add_all([e1, e2, e3])
        db_session.flush()

        with patch("cbpos.core.services.statement_service.ConfigService") as mock_config:
            mock_config.get.return_value = "Test Shop"
            result = StatementService.generate_statement(
                customer_id=customer.id,
                date_from=now - timedelta(days=10),
                date_to=now,
            )

        assert result["customer"]["name"] == "Test Customer"
        assert len(result["entries"]) == 3
        assert result["opening_balance"] == Decimal("0")  # 300 - 300
        assert result["closing_balance"] == Decimal("500")
        assert result["total_debit"] == Decimal("600")  # 300 + 300
        assert result["total_credit"] == Decimal("100")

    def test_generate_statement_empty_period_no_prior(self, db_session):
        """Test statement with no entries and no prior history gives zero balance."""
        customer = self._create_customer(db_session, debt=Decimal("500"))

        now = datetime.now()

        with patch("cbpos.core.services.statement_service.ConfigService") as mock_config:
            mock_config.get.return_value = "Test Shop"
            result = StatementService.generate_statement(
                customer_id=customer.id,
                date_from=now - timedelta(days=10),
                date_to=now,
            )

        assert len(result["entries"]) == 0
        # No prior entries, so opening and closing should be 0
        assert result["opening_balance"] == Decimal("0")
        assert result["closing_balance"] == Decimal("0")

    def test_generate_statement_empty_period_with_prior(self, db_session):
        """Test statement with no entries in range but prior history uses last known balance."""
        customer = self._create_customer(db_session, debt=Decimal("500"))
        user = self._create_user(db_session)

        now = datetime.now()

        # Entry BEFORE the statement period
        e_prior = CustomerLedgerEntry(
            customer_id=customer.id,
            entry_type="SALE",
            amount=Decimal("250"),
            balance_after=Decimal("250"),
            user_id=user.id,
            timestamp=now - timedelta(days=30),
            reference_doc="SALE-OLD",
        )
        db_session.add(e_prior)
        db_session.flush()

        with patch("cbpos.core.services.statement_service.ConfigService") as mock_config:
            mock_config.get.return_value = "Test Shop"
            result = StatementService.generate_statement(
                customer_id=customer.id,
                date_from=now - timedelta(days=5),
                date_to=now,
            )

        assert len(result["entries"]) == 0
        # Should use last known balance before period
        assert result["opening_balance"] == Decimal("250")
        assert result["closing_balance"] == Decimal("250")

    def test_generate_statement_invalid_customer(self, db_session):
        """Test that invalid customer ID raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="not found"):
            StatementService.generate_statement(
                customer_id=99999,
                date_from=datetime.now() - timedelta(days=10),
                date_to=datetime.now(),
            )

    def test_issue_907_past_period_without_entries_uses_balance_before_period(self, db_session):
        """With an entry after period_to and none inside, opening and closing come from before period (#907)."""
        from cbpos.core.services.customer_credit_service import CustomerCreditService
        from cbpos.core.services.statement_receipt_builder import StatementReceiptBuilder

        customer = self._create_customer(db_session, debt=Decimal("750.00"))
        user = self._create_user(db_session)
        now = datetime.now()

        # Prior entry: 40 days ago (+250)
        e_prior = CustomerLedgerEntry(
            customer_id=customer.id,
            entry_type="SALE",
            amount=Decimal("250.00"),
            balance_after=Decimal("250.00"),
            user_id=user.id,
            timestamp=now - timedelta(days=40),
            reference_doc="SALE-OLD",
        )
        # Future entry: today (+500, making total current debt 750)
        e_future = CustomerLedgerEntry(
            customer_id=customer.id,
            entry_type="SALE",
            amount=Decimal("500.00"),
            balance_after=Decimal("750.00"),
            user_id=user.id,
            timestamp=now,
            reference_doc="SALE-NEW",
        )
        db_session.add_all([e_prior, e_future])
        db_session.flush()

        period_from = now - timedelta(days=30)
        period_to = now - timedelta(days=10)

        # 1. CustomerCreditService.balance_at
        assert CustomerCreditService.balance_at(customer.id, period_from) == Decimal("250.00")
        assert CustomerCreditService.balance_at(customer.id, period_to) == Decimal("250.00")
        assert CustomerCreditService.balance_at(customer.id, now + timedelta(days=1)) == Decimal("750.00")

        # 2. Thermal statement builder
        commands = StatementReceiptBuilder.build_customer_statement(
            customer=customer,
            entries=[],
            period_from=period_from,
            period_to=period_to,
        )
        texts = [c["val"] for c in commands if c.get("type") == "text"]
        full_text = "\n".join(texts)

        # Must show 250.00, NOT today's 750.00
        assert "750" not in full_text
        assert "250.00" in full_text
