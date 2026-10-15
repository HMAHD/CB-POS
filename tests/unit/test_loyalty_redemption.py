"""Tests for loyalty points redemption rules, ledger entries, and reversal on refund/void."""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from cbpos.core.models import Customer, LoyaltyLedgerEntry, Sale, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.loyalty_service import LoyaltyService

_counter = 0


@pytest.fixture
def loyalty_customer(db_session: Session) -> Customer:
    global _counter
    _counter += 1
    customer = Customer(
        name=f"Loyal Customer {_counter}",
        phone=f"077{_counter:07d}",
        loyalty_points=500,
    )
    db_session.add(customer)
    db_session.flush()
    return customer


@pytest.fixture
def sample_cashier(db_session: Session) -> User:
    global _counter
    _counter += 1
    user = User(
        username=f"cashier_test_{_counter}",
        pin_hash="test_hash",
    )
    db_session.add(user)
    db_session.flush()
    return user


class TestLoyaltyRedeemCalculation:
    """Test calculate_redeem_value and can_redeem_points domain logic."""

    def test_calculate_redeem_value_default(self, monkeypatch):
        monkeypatch.setattr(ConfigService, "get", lambda key: "1.00" if key == "loyalty_point_value" else None)
        assert LoyaltyService.calculate_redeem_value(100) == Decimal("100.00")

    def test_calculate_redeem_value_custom_ratio(self, monkeypatch):
        monkeypatch.setattr(ConfigService, "get", lambda key: "2.50" if key == "loyalty_point_value" else None)
        assert LoyaltyService.calculate_redeem_value(100) == Decimal("250.00")

    def test_can_redeem_disabled_loyalty(self, monkeypatch, loyalty_customer):
        monkeypatch.setattr(ConfigService, "get", lambda key: False if key == "enable_loyalty" else "1.00")
        can_redeem, reason = LoyaltyService.can_redeem_points(loyalty_customer, 100, Decimal("500.00"))
        assert can_redeem is False
        assert reason == "loyalty_disabled"

    def test_can_redeem_no_customer(self, monkeypatch):
        monkeypatch.setattr(ConfigService, "get", lambda key: True if key == "enable_loyalty" else "1.00")
        can_redeem, reason = LoyaltyService.can_redeem_points(None, 100, Decimal("500.00"))
        assert can_redeem is False
        assert reason == "no_customer"

    def test_can_redeem_invalid_points(self, monkeypatch, loyalty_customer):
        monkeypatch.setattr(ConfigService, "get", lambda key: True if key == "enable_loyalty" else "1.00")
        can_redeem, reason = LoyaltyService.can_redeem_points(loyalty_customer, 0, Decimal("500.00"))
        assert can_redeem is False
        assert reason == "invalid_points"

        can_redeem, reason = LoyaltyService.can_redeem_points(loyalty_customer, -10, Decimal("500.00"))
        assert can_redeem is False
        assert reason == "invalid_points"

    def test_can_redeem_insufficient_points(self, monkeypatch, loyalty_customer):
        monkeypatch.setattr(ConfigService, "get", lambda key: True if key == "enable_loyalty" else "1.00")
        # Customer has 500 points
        can_redeem, reason = LoyaltyService.can_redeem_points(loyalty_customer, 600, Decimal("1000.00"))
        assert can_redeem is False
        assert reason == "insufficient_points"

    def test_can_redeem_below_minimum_redeem(self, monkeypatch, loyalty_customer):
        def _mock_get(key):
            if key == "enable_loyalty":
                return True
            if key == "loyalty_minimum_redeem":
                return 200
            if key == "loyalty_point_value":
                return "1.00"
            return None

        monkeypatch.setattr(ConfigService, "get", _mock_get)
        can_redeem, reason = LoyaltyService.can_redeem_points(loyalty_customer, 100, Decimal("500.00"))
        assert can_redeem is False
        assert reason == "below_minimum"

    def test_can_redeem_exceeds_bill_total(self, monkeypatch, loyalty_customer):
        def _mock_get(key):
            if key == "enable_loyalty":
                return True
            if key == "loyalty_point_value":
                return "1.00"
            if key == "loyalty_minimum_redeem":
                return 50
            return None

        monkeypatch.setattr(ConfigService, "get", _mock_get)
        # 300 points = Rs 300, but bill is only Rs 250
        can_redeem, reason = LoyaltyService.can_redeem_points(loyalty_customer, 300, Decimal("250.00"))
        assert can_redeem is False
        assert reason == "exceeds_bill"

    def test_can_redeem_valid(self, monkeypatch, loyalty_customer):
        def _mock_get(key):
            if key == "enable_loyalty":
                return True
            if key == "loyalty_point_value":
                return "1.00"
            if key == "loyalty_minimum_redeem":
                return 50
            return None

        monkeypatch.setattr(ConfigService, "get", _mock_get)
        can_redeem, reason = LoyaltyService.can_redeem_points(loyalty_customer, 150, Decimal("500.00"))
        assert can_redeem is True
        assert reason == ""


class TestLoyaltyRedemptionLedger:
    """Test record_redemption and return_redeemed_points ledger entries."""

    def test_record_redemption_creates_negative_ledger_entry(
        self, db_session: Session, loyalty_customer: Customer, sample_cashier: User
    ):
        sale = Sale(
            document_number="SAL-TEST-001",
            type="sale",
            total_amount=Decimal("350.00"),
            tax_vat=Decimal("0.00"),
            tax_sscl=Decimal("0.00"),
            net_revenue=Decimal("350.00"),
            payment_method="CASH",
            user_id=sample_cashier.id,
            customer_id=loyalty_customer.id,
            loyalty_points_redeemed=150,
            loyalty_points_value=Decimal("150.00"),
        )
        db_session.add(sale)
        db_session.flush()

        entry = LoyaltyService.record_redemption(db_session, sale, 150)
        assert entry is not None
        assert entry.entry_type == "REDEEM"
        assert entry.points == -150
        assert entry.balance_after == 350
        assert entry.reference_id == sale.id

        # Customer balance updated
        cust = db_session.get(Customer, loyalty_customer.id)
        assert cust.loyalty_points == 350

    def test_return_redeemed_points_on_void_or_refund(
        self, db_session: Session, loyalty_customer: Customer, sample_cashier: User
    ):
        sale = Sale(
            document_number="SAL-TEST-002",
            type="sale",
            total_amount=Decimal("350.00"),
            tax_vat=Decimal("0.00"),
            tax_sscl=Decimal("0.00"),
            net_revenue=Decimal("350.00"),
            payment_method="CASH",
            user_id=sample_cashier.id,
            customer_id=loyalty_customer.id,
            loyalty_points_redeemed=100,
            loyalty_points_value=Decimal("100.00"),
        )
        db_session.add(sale)
        db_session.flush()

        LoyaltyService.record_redemption(db_session, sale, 100)
        assert loyalty_customer.loyalty_points == 400

        # Return redeemed points on void
        reversal_entry = LoyaltyService.return_redeemed_points(db_session, sale, reason="VOID")
        assert reversal_entry is not None
        assert reversal_entry.entry_type == "REVERSAL"
        assert reversal_entry.points == 100
        assert reversal_entry.balance_after == 500
        assert reversal_entry.reference_id == sale.id

        assert loyalty_customer.loyalty_points == 500

        # Second return call returns None and does not add points again
        second_entry = LoyaltyService.return_redeemed_points(db_session, sale, reason="VOID")
        assert second_entry is None
        assert loyalty_customer.loyalty_points == 500


class TestCartServiceLoyaltyDiscount:
    """Test CartService integration with loyalty redemption discount."""

    def test_cart_loyalty_redemption_reduces_final_total(self, db_session: Session):
        from cbpos.core.models import Product
        from cbpos.core.services.cart_service import CartService

        product = Product(name_en="Test Item", price=Decimal("1000.00"), stock_qty=50.0, barcode="TEST001")
        db_session.add(product)
        db_session.flush()

        cart = CartService()
        cart.add_item(product, Decimal("1"))
        cart.set_loyalty_redemption(200)

        totals = cart.get_totals()
        assert totals["subtotal"] == Decimal("1000.00")
        assert totals["loyalty_discount"] == Decimal("200.00")
        assert totals["loyalty_points_redeemed"] == 200
        assert totals["final_total"] == Decimal("800.00")

    def test_cart_loyalty_discount_combined_with_cart_discount(self, db_session: Session):
        from cbpos.core.models import Product
        from cbpos.core.services.cart_service import CartService

        product = Product(name_en="Test Item 2", price=Decimal("1000.00"), stock_qty=50.0, barcode="TEST002")
        db_session.add(product)
        db_session.flush()

        cart = CartService()
        cart.add_item(product, Decimal("1"))
        cart.apply_cart_discount("FIXED", Decimal("100.00"))
        cart.set_loyalty_redemption(200)

        totals = cart.get_totals()
        assert totals["subtotal"] == Decimal("1000.00")
        assert totals["cart_discount"] == Decimal("100.00")
        assert totals["loyalty_discount"] == Decimal("200.00")
        assert totals["final_total"] == Decimal("700.00")

    def test_cart_clear_resets_loyalty_redemption(self, db_session: Session):
        from cbpos.core.models import Product
        from cbpos.core.services.cart_service import CartService

        product = Product(name_en="Test Item 3", price=Decimal("500.00"), stock_qty=50.0, barcode="TEST003")
        db_session.add(product)
        db_session.flush()

        cart = CartService()
        cart.add_item(product, Decimal("1"))
        cart.set_loyalty_redemption(100)
        assert cart.loyalty_points_redeemed == 100

        cart.clear()
        assert cart.loyalty_points_redeemed == 0
        totals = cart.get_totals()
        assert totals["loyalty_discount"] == Decimal("0.00")


class TestTransactionServiceLoyaltyRedemption:
    """Test TransactionService processing sales, voids, and refunds with loyalty redemption."""

    def test_process_sale_with_redemption(self, db_session: Session, loyalty_customer: Customer, sample_cashier: User):
        from unittest.mock import patch

        from cbpos.core.models import Product
        from cbpos.core.services.cart_service import CartService
        from cbpos.core.services.transaction_service import TransactionService

        loyalty_customer.loyalty_points = 300
        product = Product(name_en="Rice 5kg", price=Decimal("1000.00"), stock_qty=50.0, barcode="RICE5K")
        db_session.add(product)
        db_session.commit()

        ConfigService.set("enable_loyalty", True)
        ConfigService.set("loyalty_points_ratio", 100)
        ConfigService.set("loyalty_point_value", "1.00")
        ConfigService.set("loyalty_minimum_redeem", 50)

        with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=sample_cashier):
            cart = CartService()
            cart.add_item(product, Decimal("1.0"))

            # Redeem 100 points -> Rs. 100 discount, net bill = 900.00
            payments = [{"method": "CASH", "amount": Decimal("900.00")}]
            sale = TransactionService.process_sale(
                cart, payments, customer_id=loyalty_customer.id, loyalty_points_redeemed=100
            )

            assert sale is not None
            assert sale.total_amount == Decimal("900.00")
            assert sale.loyalty_points_redeemed == 100
            assert sale.loyalty_points_value == Decimal("100.00")
            assert sale.loyalty_points_earned == 9
            assert sale.loyalty_points_balance == 209

            # Check customer balance: started 300, redeemed -100, earned on 900.00 (+9 pts) -> 209
            db_session.refresh(loyalty_customer)
            assert loyalty_customer.loyalty_points == 209

            # Ledger rows: one REDEEM (-100) and one EARN (+9)
            entries = (
                db_session.query(LoyaltyLedgerEntry)
                .filter_by(customer_id=loyalty_customer.id, reference_id=sale.id)
                .order_by(LoyaltyLedgerEntry.id.asc())
                .all()
            )
            assert len(entries) == 2
            redeem_entry = entries[0]
            assert redeem_entry.entry_type == "REDEEM"
            assert redeem_entry.points == -100

            earn_entry = entries[1]
            assert earn_entry.entry_type == "EARN"
            assert earn_entry.points == 9

    def test_process_sale_redemption_validation_error(
        self, db_session: Session, loyalty_customer: Customer, sample_cashier: User
    ):
        from unittest.mock import patch

        from cbpos.core.models import Product
        from cbpos.core.services.cart_service import CartService
        from cbpos.core.services.transaction_service import TransactionService

        loyalty_customer.loyalty_points = 50
        product = Product(name_en="Biscuit", price=Decimal("1000.00"), stock_qty=50.0, barcode="BISC01")
        db_session.add(product)
        db_session.commit()

        ConfigService.set("enable_loyalty", True)
        ConfigService.set("loyalty_points_ratio", 100)
        ConfigService.set("loyalty_point_value", "1.00")
        ConfigService.set("loyalty_minimum_redeem", 100)

        with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=sample_cashier):
            cart = CartService()
            cart.add_item(product, Decimal("1.0"))
            payments = [{"method": "CASH", "amount": Decimal("1000.00")}]

            # Try to redeem 100 points when customer only has 50 (also below min 100)
            with pytest.raises(ValueError):
                TransactionService.process_sale(
                    cart, payments, customer_id=loyalty_customer.id, loyalty_points_redeemed=100
                )

    def test_void_sale_returns_redeemed_points_alongside_earned_reversal(
        self, db_session: Session, loyalty_customer: Customer, sample_cashier: User
    ):
        from unittest.mock import patch

        from cbpos.core.models import Product
        from cbpos.core.services.cart_service import CartService
        from cbpos.core.services.transaction_service import TransactionService

        loyalty_customer.loyalty_points = 300
        product = Product(name_en="Tea 1kg", price=Decimal("1000.00"), stock_qty=50.0, barcode="TEA1K")
        db_session.add(product)
        db_session.commit()

        ConfigService.set("enable_loyalty", True)
        ConfigService.set("loyalty_points_ratio", 100)
        ConfigService.set("loyalty_point_value", "1.00")
        ConfigService.set("loyalty_minimum_redeem", 50)

        with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=sample_cashier):
            cart = CartService()
            cart.add_item(product, Decimal("1.0"))
            payments = [{"method": "CASH", "amount": Decimal("900.00")}]
            sale = TransactionService.process_sale(
                cart, payments, customer_id=loyalty_customer.id, loyalty_points_redeemed=100
            )

            db_session.refresh(loyalty_customer)
            assert loyalty_customer.loyalty_points == 209

            # Void the sale
            ok = TransactionService.void_sale(sale.id, sample_cashier.id, reason="Customer cancelled")
            assert ok is True

            db_session.refresh(loyalty_customer)
            # Reversal of 9 earned points (-9) and return of 100 redeemed points (+100) -> 300
            assert loyalty_customer.loyalty_points == 300

            # Ledger checks: should have REVERSAL row with +100 points
            reversal_entries = (
                db_session.query(LoyaltyLedgerEntry)
                .filter_by(customer_id=loyalty_customer.id, reference_id=sale.id, entry_type="REVERSAL")
                .all()
            )
            assert len(reversal_entries) == 2
            returned_entry = next((e for e in reversal_entries if e.points > 0), None)
            earned_reversed_entry = next((e for e in reversal_entries if e.points < 0), None)

            assert returned_entry is not None
            assert returned_entry.points == 100

            assert earned_reversed_entry is not None
            assert earned_reversed_entry.points == -9

    def test_refund_sale_returns_redeemed_points_alongside_earned_reversal(
        self, db_session: Session, loyalty_customer: Customer, sample_cashier: User
    ):
        from unittest.mock import patch

        from cbpos.core.models import Product
        from cbpos.core.services.cart_service import CartService
        from cbpos.core.services.transaction_service import TransactionService

        loyalty_customer.loyalty_points = 300
        product = Product(name_en="Coffee 500g", price=Decimal("1000.00"), stock_qty=50.0, barcode="COF500")
        db_session.add(product)
        db_session.commit()

        ConfigService.set("enable_loyalty", True)
        ConfigService.set("loyalty_points_ratio", 100)
        ConfigService.set("loyalty_point_value", "1.00")
        ConfigService.set("loyalty_minimum_redeem", 50)

        with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=sample_cashier):
            cart = CartService()
            cart.add_item(product, Decimal("1.0"))
            payments = [{"method": "CASH", "amount": Decimal("900.00")}]
            sale = TransactionService.process_sale(
                cart, payments, customer_id=loyalty_customer.id, loyalty_points_redeemed=100
            )

            db_session.refresh(loyalty_customer)
            assert loyalty_customer.loyalty_points == 209

            # Refund the sale
            refund_sale = TransactionService.process_refund(
                original_sale_id=sale.id,
                refund_reason="Damaged item",
                user_id=sample_cashier.id,
            )
            assert refund_sale is not None

            db_session.refresh(loyalty_customer)
            # Reversal of 9 earned points (-9) and return of 100 redeemed points (+100) -> 300
            assert loyalty_customer.loyalty_points == 300
