"""
Unit tests for TransactionService — atomic commits, void, and refund workflows.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import Customer, Permission, Product, Role, Sale, SaleItem, StockMovement, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.tax_service import TaxService
from cbpos.core.services.transaction_service import TransactionService

# ── Shared Fixtures ──────────────────────────────────────────────────────

_counter = 0


@pytest.fixture
def test_user(db_session):
    """Create a test user with a unique role and permission."""
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"txn_test_{suffix}")
    role = Role(name=f"TxnRole_{suffix}", permissions=[permission])
    user = User(username=f"txn_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    """Create a test product with stock."""
    global _counter
    _counter += 1
    product = Product(
        name_en=f"Product_{_counter}",
        price=100.0,
        stock_qty=10.0,
        barcode=f"TST{_counter:04d}",
    )
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def completed_sale(db_session, test_user, test_product):
    """Create a completed sale with one item (qty=2, price=100, total=200)."""
    sale = Sale(
        document_number=f"REC-FIX-{_counter}",
        date=datetime.now(),
        total_amount=200.0,
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=200,
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.flush()

    sale_item = SaleItem(
        sale_id=sale.id,
        product_id=test_product.id,
        qty=2.0,
        unit_price=100.0,
        original_price=100.0,
        subtotal=200.0,
    )
    db_session.add(sale_item)
    db_session.commit()
    return sale


# ── Test Case A: Atomic Commit (Sale + Stock) ───────────────────────────


def test_process_sale_atomic(db_session, test_user, test_product):
    """Sale processing is atomic: stock deducted, sale saved."""
    db_session.commit()

    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user),
    ):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))
        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        result = TransactionService.process_sale(cart_service, payments)

        assert result is not None

        db_session.refresh(test_product)
        assert test_product.stock_qty == 8.0

        sale = db_session.query(Sale).order_by(Sale.id.desc()).first()
        assert sale is not None
        assert sale.total_amount == 200.0
        assert sale.items[0].qty == 2.0


def test_process_sale_persists_the_cart_line_note(db_session, test_user, test_product):
    """#481: the cart already captured a per-line note (add_line_note in
    sales_view.py) but SaleItem had no column for it -- the note was
    silently discarded the instant the sale completed."""
    db_session.commit()

    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user),
    ):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("1.0"))
        cart_service.items[0]["note"] = "Gift wrap please"
        payments = [{"method": "CASH", "amount": Decimal("100.0")}]

        TransactionService.process_sale(cart_service, payments)

        sale = db_session.query(Sale).order_by(Sale.id.desc()).first()
        assert sale.items[0].notes == "Gift wrap please"


def test_process_sale_rollback_on_error(db_session, test_user, test_product):
    """Transaction rolls back on error — stock unchanged."""
    db_session.commit()

    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user),
    ):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))
        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        with patch(
            "cbpos.core.services.transaction_service.SaleItem",
            side_effect=Exception("DB Error"),
        ):
            result = TransactionService.process_sale(cart_service, payments)

            assert result is None

            db_session.refresh(test_product)
            assert test_product.stock_qty == 10.0


# ── Test Case B: Backward Tax Verification ───────────────────────────────


def test_calculate_taxes():
    """TaxService backward calculation returns expected keys and types."""
    amount = Decimal("1000.00")
    taxes = TaxService.calculate_taxes(amount)

    assert "vat" in taxes
    assert "sscl" in taxes
    assert "net" in taxes
    assert isinstance(taxes["vat"], Decimal)


# ── Test Case C: Void Sale ───────────────────────────────────────────────


def test_void_sale(db_session, test_user, test_product, completed_sale):
    """Void sale sets status to VOID and restores stock."""
    result = TransactionService.void_sale(completed_sale.id, test_user.id, "Wrong Entry")

    assert result is True

    db_session.refresh(completed_sale)
    assert completed_sale.status == "VOID"

    db_session.refresh(test_product)
    assert test_product.stock_qty == 12.0  # 10 + 2 restored


# ── Test Case D: Double Void Prevention ──────────────────────────────────


def test_void_sale_already_voided(db_session, test_user, test_product):
    """Voiding an already-voided sale returns False."""
    sale = Sale(
        document_number=f"REC-VD-{_counter}",
        date=datetime.now(),
        total_amount=50.0,
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=50,
        payment_method="CASH",
        status="VOID",
    )
    db_session.add(sale)
    db_session.flush()

    sale_item = SaleItem(
        sale_id=sale.id,
        product_id=test_product.id,
        qty=1.0,
        unit_price=50.0,
        original_price=50.0,
        subtotal=50.0,
    )
    db_session.add(sale_item)
    db_session.commit()

    result = TransactionService.void_sale(sale.id, test_user.id, "Accidental double void")
    assert result is False

    db_session.refresh(test_product)
    assert test_product.stock_qty == 10.0


# ── Test Case E: Void Non-existent Sale ──────────────────────────────────


def test_void_nonexistent_sale(db_session):
    """Voiding a non-existent sale ID returns False."""
    result = TransactionService.void_sale(999999, 1, "Does not exist")
    assert result is False


# ── Test Case F: Void Stock Restoration Audit Trail ──────────────────────


def test_void_creates_stock_movements(db_session, test_user, test_product, completed_sale):
    """Voiding a sale creates VOID stock movements to restore inventory."""
    result = TransactionService.void_sale(completed_sale.id, test_user.id, "Customer changed mind")
    assert result is True

    void_movements = (
        db_session.query(StockMovement)
        .filter(StockMovement.product_id == test_product.id, StockMovement.type == "VOID")
        .all()
    )
    assert len(void_movements) >= 1
    last_void = void_movements[-1]
    assert last_void.qty_change == Decimal("2")

    db_session.refresh(test_product)
    assert test_product.stock_qty == 12.0  # 10 + 2


# ── Test Case G: Refund Full Workflow ────────────────────────────────────


def test_process_refund(db_session, test_user, test_product, completed_sale, peripherals):
    """Full refund creates a negative sale, restores stock, links to original, and reports it to the hardware."""
    with patch("cbpos.core.services.transaction_service.ConfigService.get_all", return_value={"language": "en"}):
        result = TransactionService.process_refund(completed_sale.id, "Defective item", test_user.id)

    assert result is True

    refund_sale = db_session.query(Sale).filter(Sale.refund_of_sale_id == completed_sale.id).first()
    (event,) = peripherals.events
    assert event.refund_sale.id == refund_sale.id
    assert event.voucher
    assert refund_sale is not None
    assert refund_sale.total_amount == Decimal("-200")
    assert refund_sale.payment_method == "REFUND"
    assert refund_sale.document_number.startswith("CN-")  # #637: sequential, was REF-<uuid>

    refund_items = db_session.query(SaleItem).filter(SaleItem.sale_id == refund_sale.id).all()
    assert len(refund_items) == 1
    assert refund_items[0].qty == Decimal("-2")

    db_session.refresh(test_product)
    assert test_product.stock_qty == 12.0  # 10 + 2


# ── Test Case H: Cannot Refund Voided Sale ───────────────────────────────


def test_refund_voided_sale_fails(db_session, test_user):
    """Cannot refund a sale that has been voided."""
    sale = Sale(
        document_number=f"REC-RV-{_counter}",
        date=datetime.now(),
        total_amount=100.0,
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=100,
        payment_method="CASH",
        status="VOID",
    )
    db_session.add(sale)
    db_session.commit()

    result = TransactionService.process_refund(sale.id, "Should fail", test_user.id)

    assert result is False


# ── Test Case I: Cannot Double-Refund ────────────────────────────────────


def test_double_refund_fails(db_session, test_user, test_product, completed_sale):
    """Cannot refund a sale that has already been refunded."""
    # Create existing refund
    existing_refund = Sale(
        document_number=f"REF-DR-{_counter}",
        date=datetime.now(),
        total_amount=-200.0,
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=-200,
        payment_method="REFUND",
        refund_of_sale_id=completed_sale.id,
    )
    db_session.add(existing_refund)
    db_session.commit()

    result = TransactionService.process_refund(completed_sale.id, "Second refund attempt", test_user.id)

    assert result is False


# ── Test Case J: Cannot Refund a Refund ──────────────────────────────────


def test_refund_of_refund_fails(db_session, test_user):
    """Cannot refund a transaction that is itself a refund."""
    refund_sale = Sale(
        document_number=f"REF-REFREF-{_counter}",
        date=datetime.now(),
        total_amount=-100.0,
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=-100,
        payment_method="REFUND",
    )
    db_session.add(refund_sale)
    db_session.commit()

    result = TransactionService.process_refund(refund_sale.id, "Meta refund", test_user.id)

    assert result is False


# ── Test Case K: Refund Non-existent Sale ────────────────────────────────


def test_refund_nonexistent_sale(db_session):
    """Refunding a non-existent sale returns False."""
    result = TransactionService.process_refund(999999, "Ghost sale", 1)
    assert result is False


# ── Test Case L: B2B customers additionally get an A4 Tax Invoice ───────


def test_b2b_sale_hands_the_receipt_its_vat_customer(db_session, test_user, test_product, peripherals):
    """A VAT-registered customer's sale reaches the peripherals with the customer loaded,
    so the receipt and the A4 Tax Invoice can be printed after the session has closed."""
    customer = Customer(name="Registered Co", vat_number="VAT-12345")
    db_session.add(customer)
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))
        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        result = TransactionService.process_sale(cart_service, payments, customer_id=customer.id)

    (event,) = peripherals.events
    assert event.sale is result
    assert event.sale.customer.vat_number == "VAT-12345"


def test_walkin_sale_reaches_the_peripherals_without_a_customer(db_session, test_user, test_product, peripherals):
    """A walk-in (no customer) sale goes through the same single sale event."""
    db_session.commit()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_user):
        cart_service = CartService()
        cart_service.add_item(test_product, qty=Decimal("2.0"))
        payments = [{"method": "CASH", "amount": Decimal("200.0")}]

        result = TransactionService.process_sale(cart_service, payments)

    (event,) = peripherals.events
    assert event.sale is result
    assert event.sale.customer is None
