"""
Tests for Issue #747:
Earn loyalty points at checkout; take them back on refund/void.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.database import Database
from cbpos.core.models import Customer, LoyaltyLedgerEntry, Permission, Product, Role, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.transaction_service import TransactionService

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"loyalty_test_perm_{_counter}")
    role = Role(name=f"LoyaltyRole_{_counter}", permissions=[permission])
    user = User(username=f"loyalty_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def customer(db_session):
    global _counter
    _counter += 1
    c = Customer(name=f"Loyal Customer {_counter}", phone=f"077{_counter:07d}", loyalty_points=0)
    db_session.add(c)
    db_session.flush()
    return c


@pytest.fixture
def product(db_session):
    global _counter
    _counter += 1
    p = Product(
        name_en=f"Item {_counter}",
        price=1250.0,
        stock_qty=100.0,
        barcode=f"LOY{_counter:04d}",
    )
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture(autouse=True)
def enable_loyalty_config():
    ConfigService.set("enable_loyalty", True)
    ConfigService.set("loyalty_points_ratio", 100)
    yield
    ConfigService.set("enable_loyalty", True)
    ConfigService.set("loyalty_points_ratio", 100)


def test_sale_earns_points_at_checkout(db_session, test_user, customer, product):
    """Rs. 1,250 Final Bill, ratio 100, customer attached -> +12 points, one EARN row linked to the sale."""
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(product, qty=Decimal("1.0"))
        payments = [{"method": "CASH", "amount": Decimal("1250.00")}]

        sale = TransactionService.process_sale(cart, payments, customer_id=customer.id)

        assert sale is not None
        assert sale.total_amount == Decimal("1250.00")

        # Customer balance updated
        db_session.refresh(customer)
        assert customer.loyalty_points == 12

        # Exactly one EARN row in LoyaltyLedgerEntry linked to sale
        entries = db_session.query(LoyaltyLedgerEntry).filter_by(customer_id=customer.id, reference_id=sale.id).all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.entry_type == "EARN"
        assert entry.points == 12
        assert entry.balance_after == 12
        assert entry.reference_id == sale.id
        assert entry.synced is False


def test_walk_in_sale_earns_no_points(db_session, test_user, product):
    """Walk-in sale (no customer attached) -> no points, no ledger row."""
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(product, qty=Decimal("1.0"))
        payments = [{"method": "CASH", "amount": Decimal("1250.00")}]

        sale = TransactionService.process_sale(cart, payments, customer_id=None)

        assert sale is not None
        entries = db_session.query(LoyaltyLedgerEntry).filter_by(reference_id=sale.id).all()
        assert len(entries) == 0


def test_loyalty_off_earns_no_points(db_session, test_user, customer, product):
    """Loyalty off -> no points, no ledger row."""
    ConfigService.set("enable_loyalty", False)
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(product, qty=Decimal("1.0"))
        payments = [{"method": "CASH", "amount": Decimal("1250.00")}]

        sale = TransactionService.process_sale(cart, payments, customer_id=customer.id)

        assert sale is not None
        db_session.refresh(customer)
        assert customer.loyalty_points == 0

        entries = db_session.query(LoyaltyLedgerEntry).filter_by(customer_id=customer.id, reference_id=sale.id).all()
        assert len(entries) == 0


def test_credit_book_sale_earns_points(db_session, test_user, customer, product):
    """Credit-book sales earn points too."""
    customer.credit_limit = Decimal("5000.00")
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(product, qty=Decimal("1.0"))
        payments = [{"method": "CREDIT", "amount": Decimal("1250.00")}]

        sale = TransactionService.process_sale(cart, payments, customer_id=customer.id)

        assert sale is not None
        db_session.refresh(customer)
        assert customer.loyalty_points == 12

        entries = db_session.query(LoyaltyLedgerEntry).filter_by(customer_id=customer.id, reference_id=sale.id).all()
        assert len(entries) == 1
        assert entries[0].entry_type == "EARN"
        assert entries[0].points == 12


def test_void_sale_reverses_earned_points(db_session, test_user, customer, product):
    """Void sale -> one REVERSAL row taking back the earned points."""
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(product, qty=Decimal("1.0"))
        payments = [{"method": "CASH", "amount": Decimal("1250.00")}]

        sale = TransactionService.process_sale(cart, payments, customer_id=customer.id)
        assert sale is not None

        db_session.refresh(customer)
        assert customer.loyalty_points == 12

        # Void the sale
        success = TransactionService.void_sale(sale.id, test_user.id, "Mistake at checkout")
        assert success is True

        db_session.refresh(customer)
        assert customer.loyalty_points == 0

        reversals = (
            db_session.query(LoyaltyLedgerEntry)
            .filter_by(customer_id=customer.id, reference_id=sale.id, entry_type="REVERSAL")
            .all()
        )
        assert len(reversals) == 1
        assert reversals[0].points == -12
        assert reversals[0].balance_after == 0


def test_refund_sale_reverses_earned_points(db_session, test_user, customer, product):
    """Refund sale -> one REVERSAL row taking back the earned points."""
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(product, qty=Decimal("1.0"))
        payments = [{"method": "CASH", "amount": Decimal("1250.00")}]

        sale = TransactionService.process_sale(cart, payments, customer_id=customer.id)
        assert sale is not None

        # Process refund
        success = TransactionService.process_refund(sale.id, "Customer returned product", test_user.id)
        assert success is True

        db_session.refresh(customer)
        assert customer.loyalty_points == 0

        reversals = (
            db_session.query(LoyaltyLedgerEntry)
            .filter_by(customer_id=customer.id, reference_id=sale.id, entry_type="REVERSAL")
            .all()
        )
        assert len(reversals) == 1
        assert reversals[0].points == -12
        assert reversals[0].balance_after == 0


def test_refund_then_void_never_reverses_twice(db_session, test_user, customer, product):
    """Refund then void never reverses twice."""
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(product, qty=Decimal("1.0"))
        payments = [{"method": "CASH", "amount": Decimal("1250.00")}]

        sale = TransactionService.process_sale(cart, payments, customer_id=customer.id)
        assert sale is not None

        # 1. Refund takes back the 12 points
        success = TransactionService.process_refund(sale.id, "Returned", test_user.id)
        assert success is True

        db_session.refresh(customer)
        assert customer.loyalty_points == 0

        # 2. Void attempt afterwards must be refused and not reverse again
        with pytest.raises(ValueError, match="sale_has_refund"):
            TransactionService.void_sale(sale.id, test_user.id, "Void after refund")

        db_session.refresh(customer)
        assert customer.loyalty_points == 0

        reversals = (
            db_session.query(LoyaltyLedgerEntry)
            .filter_by(customer_id=customer.id, reference_id=sale.id, entry_type="REVERSAL")
            .all()
        )
        assert len(reversals) == 1


def test_reversal_never_below_zero_silently(db_session, test_user, customer, product, caplog):
    """Reversal never leaves customer points below zero silently (clamps to 0 and logs warning)."""
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.add_item(product, qty=Decimal("1.0"))
        payments = [{"method": "CASH", "amount": Decimal("1250.00")}]

        sale = TransactionService.process_sale(cart, payments, customer_id=customer.id)
        assert sale is not None

        # Artificially set customer points to 5 (e.g. they redeemed 7 points elsewhere)
        with Database().get_session() as session:
            c = session.get(Customer, customer.id)
            c.loyalty_points = 5
            session.commit()

        # Voiding the sale that earned 12 points
        success = TransactionService.void_sale(sale.id, test_user.id, "Mistake")
        assert success is True

        db_session.refresh(customer)
        # Never below zero: clamped at 0
        assert customer.loyalty_points == 0

        # Not silent: logged warning
        assert any("below zero" in record.message.lower() for record in caplog.records)


def test_issue_853_failed_sale_leaves_no_redemption_on_cart(db_session, test_user, customer, product):
    """If a sale with loyalty redemption fails, cart redemption must not be mutated (#853)."""
    db_session.commit()
    with Database().get_session() as session:
        c = session.get(Customer, customer.id)
        c.loyalty_points = 500
        session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart = CartService()
        cart.set_customer(customer)
        # Attempt to sell more quantity than in stock to force stock failure
        cart.add_item(product, qty=Decimal("500.0"))
        payments = [{"method": "CASH", "amount": Decimal("10000.00")}]

        with pytest.raises(ValueError):
            TransactionService.process_sale(cart, payments, customer_id=customer.id, loyalty_points_redeemed=100)

        assert cart.loyalty_points_redeemed == 0


def test_issue_853_walk_in_cart_has_no_loyalty_discount(product):
    """A walk-in cart (customer=None) must never apply loyalty discount in get_totals (#853)."""
    product.price = Decimal("1250.00")
    cart = CartService()
    cart.add_item(product, qty=Decimal("1.0"))
    # Even if loyalty_points_redeemed is set on the cart
    cart.loyalty_points_redeemed = 100
    totals = cart.get_totals()
    assert totals["loyalty_discount"] == Decimal("0.00")
    assert totals["loyalty_points_redeemed"] == 0

    # Also test set_customer(None) resets loyalty_points_redeemed
    cart.loyalty_points_redeemed = 100
    cart.set_customer(None)
    assert cart.loyalty_points_redeemed == 0


def test_issue_913_reversal_below_zero_ledger_matches_balance(db_session, test_user, customer, product):
    """When a reversal would take customer below 0, ledger row matches actual points removed (#913)."""
    from sqlalchemy import func

    db_session.commit()
    # Customer starts with opening 500
    with Database().get_session() as session:
        c = session.get(Customer, customer.id)
        c.loyalty_points = 500
        session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        # Sale A: earn 10 points (1000.00 bill with ratio 100)
        product.price = Decimal("1000.00")
        cart_a = CartService()
        cart_a.add_item(product, qty=Decimal("1.0"))
        sale_a = TransactionService.process_sale(
            cart_a, [{"method": "CASH", "amount": Decimal("1000.00")}], customer_id=customer.id
        )
        assert sale_a.loyalty_points_earned == 10

        db_session.refresh(customer)
        assert customer.loyalty_points == 510

        # Sale B: redeem 510 points
        cart_b = CartService()
        cart_b.set_customer(customer)
        cart_b.add_item(product, qty=Decimal("1.0"))
        sale_b = TransactionService.process_sale(
            cart_b,
            [{"method": "CASH", "amount": Decimal("490.00")}],
            customer_id=customer.id,
            loyalty_points_redeemed=510,
        )
        assert sale_b.loyalty_points_redeemed == 510

        db_session.refresh(customer)
        # Customer has 4 points earned from Sale B (490 / 100 = 4)
        assert customer.loyalty_points == 4

        # Refund Sale A: would reverse 10 points, but customer only has 4 points left
        refund_a = TransactionService.process_refund(sale_a.id, "Refund A", test_user.id)
        assert refund_a is not None

        db_session.refresh(customer)
        assert customer.loyalty_points == 0

        # Invariant: customer.loyalty_points == opening (500) + sum(ledger entries)
        ledger_sum = db_session.query(func.sum(LoyaltyLedgerEntry.points)).filter_by(customer_id=customer.id).scalar()
        assert 500 + ledger_sum == customer.loyalty_points


def test_issue_913_redemption_over_balance_raises(db_session, test_user, customer, product):
    """record_redemption raises ValueError('insufficient_points') if points > customer balance (#913)."""
    from cbpos.core.models import Sale
    from cbpos.core.services.loyalty_service import LoyaltyService

    with Database().get_session() as session:
        c = session.get(Customer, customer.id)
        c.loyalty_points = 50
        session.commit()

    with Database().get_session() as session:
        sale = Sale(
            document_number="INV-TEST-001",
            customer_id=customer.id,
            user_id=test_user.id,
            payment_method="CASH",
            total_amount=Decimal("100.00"),
        )
        session.add(sale)
        session.flush()

        with pytest.raises(ValueError, match="insufficient_points"):
            LoyaltyService.record_redemption(session, sale, 100)
