"""Tests for StatementService customer account statements."""

from decimal import Decimal
from datetime import datetime, timedelta
from cbpos.core.services.statement_service import StatementService
from cbpos.core.models import Customer, CustomerLedgerEntry, User, Role, Permission
from unittest.mock import patch


class TestStatementService:
    """Unit tests for StatementService."""

    _phone_counter = 0

    def _create_customer(self, db_session, debt: Decimal = Decimal("0")) -> Customer:
        """Helper to create a test customer."""
        TestStatementService._phone_counter += 1
        customer = Customer(
            name="Test Customer",
            phone=f"077{TestStatementService._phone_counter:07d}",  # noqa: E231
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
