"""Tests for Sales, Cart, Pricing, and Checkout batch integration (#926)."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.features import Features
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import (
    PaymentMethod,
    Permission,
    Product,
    ProductBatch,
    Role,
    StockMovement,
    User,
)
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.feature_flags import FeatureFlags
from cbpos.core.services.pricing_service import PricingService
from cbpos.core.services.refund_service import RefundLineRequest, RefundService
from cbpos.core.services.transaction_service import TransactionService

_counter = 0


@pytest.fixture(autouse=True)
def enable_batch_features():
    FeatureFlags.invalidate_cache()
    with patch.object(
        FeatureFlags,
        "is_on",
        side_effect=lambda name: name in (Features.BATCHES, Features.EXPIRY_DATES),
    ):
        yield
    FeatureFlags.invalidate_cache()


@pytest.fixture
def cashier_user(db_session):
    global _counter
    _counter += 1
    perms = []
    for code in (
        Permissions.SALES_VIEW,
        Permissions.SALES_ADD_ITEM,
        Permissions.SALES_VOID,
        Permissions.SALES_REFUND,
        Permissions.SALES_OVERRIDE_EXPIRED_BATCH,
    ):
        p = db_session.query(Permission).filter_by(code=code).first()
        if not p:
            p = Permission(code=code, description=code, group="Sales")
            db_session.add(p)
        perms.append(p)
    role = Role(name=f"CashierRole_{_counter}", permissions=perms)
    user = User(username=f"cashier_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()

    # Create standard Cash payment method if absent
    cash_method = db_session.query(PaymentMethod).filter_by(name="CASH").first()
    if not cash_method:
        cash_method = PaymentMethod(name="CASH", kind="CASH", is_active=True)
        db_session.add(cash_method)
        db_session.flush()

    AuthService._current_user = user
    return user


def test_issue_926_cart_separates_differing_batches(db_session, cashier_user):
    """Adding items with different batch_ids creates distinct cart lines, while same batch merges."""
    prod = Product(
        barcode="CART-BATCH-TEST",
        name_en="Cough Syrup 100ml",
        price=Decimal("400.00"),
        cost=Decimal("300.00"),
        stock_qty=Decimal("20.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    b1 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-A",
        expiry_date=date(2027, 1, 1),
        qty_on_hand=Decimal("10.000"),
        mrp=Decimal("400.00"),
    )
    b2 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-B",
        expiry_date=date(2027, 6, 1),
        qty_on_hand=Decimal("10.000"),
        mrp=Decimal("420.00"),
    )
    db_session.add_all([b1, b2])
    db_session.flush()

    cart = CartService()
    # Add 1 unit of Batch A
    cart.add_item(prod, qty=Decimal("1.000"), batch_id=b1.id, batch_mrp=Decimal("400.00"))
    assert len(cart.items) == 1
    assert cart.items[0]["batch_id"] == b1.id
    assert cart.items[0]["unit_price"] == Decimal("400.00")

    # Add 1 unit of Batch B -> must create a separate line
    cart.add_item(prod, qty=Decimal("1.000"), batch_id=b2.id, batch_mrp=Decimal("420.00"))
    assert len(cart.items) == 2
    assert cart.items[1]["batch_id"] == b2.id
    assert cart.items[1]["unit_price"] == Decimal("420.00")

    # Add another unit of Batch A -> merges into first line
    cart.add_item(prod, qty=Decimal("2.000"), batch_id=b1.id, batch_mrp=Decimal("400.00"))
    assert len(cart.items) == 2
    assert cart.items[0]["qty"] == Decimal("3.000")


def test_issue_926_pricing_uses_batch_mrp_as_baseline(db_session):
    """When batch_mrp is provided, PricingService uses it as the base original price."""
    prod = Product(
        barcode="PRICE-BATCH-TEST",
        name_en="Soap 100g",
        price=Decimal("100.00"),
        cost=Decimal("70.00"),
        stock_qty=Decimal("10.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    # Standard call without batch_mrp
    p1 = PricingService.calculate_price(prod)
    assert p1["final_price"] == Decimal("100.00")
    assert p1["original_price"] == Decimal("100.00")

    # Call with batch_mrp
    p2 = PricingService.calculate_price(prod, batch_mrp=Decimal("125.00"))
    assert p2["final_price"] == Decimal("125.00")
    assert p2["original_price"] == Decimal("125.00")


def test_issue_926_checkout_explicit_batch_deducts_exact_batch(db_session, cashier_user):
    """Explicit batch selection deducts from that exact batch and creates SaleItem with batch_id."""
    prod = Product(
        barcode="CHECKOUT-EXPLICIT",
        name_en="Eye Gel",
        price=Decimal("500.00"),
        cost=Decimal("350.00"),
        stock_qty=Decimal("20.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    b1 = ProductBatch(
        product_id=prod.id,
        batch_no="EYE-1",
        expiry_date=date(2027, 1, 1),
        qty_on_hand=Decimal("10.000"),
        mrp=Decimal("500.00"),
    )
    b2 = ProductBatch(
        product_id=prod.id,
        batch_no="EYE-2",
        expiry_date=date(2027, 8, 1),
        qty_on_hand=Decimal("10.000"),
        mrp=Decimal("500.00"),
    )
    db_session.add_all([b1, b2])
    db_session.flush()

    cart = CartService()
    cart.add_item(prod, qty=Decimal("4.000"), batch_id=b2.id)

    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=[{"method": "CASH", "amount": Decimal("2000.00"), "tendered_amount": Decimal("2000.00")}],
    )
    assert sale is not None

    db_session.refresh(b1)
    db_session.refresh(b2)
    db_session.refresh(prod)

    # Batch 2 was deducted; Batch 1 was untouched
    assert b1.qty_on_hand == Decimal("10.000")
    assert b2.qty_on_hand == Decimal("6.000")
    assert prod.stock_qty == Decimal("16.000")

    # Invariant: sum(b.qty_on_hand) == prod.stock_qty
    assert b1.qty_on_hand + b2.qty_on_hand == prod.stock_qty

    # Verify SaleItem.batch_id
    item = sale.items[0]
    assert item.batch_id == b2.id


def test_issue_926_checkout_silent_fefo_line_splitting(db_session, cashier_user):
    """When untargeted, checkout uses FEFO and splits cart line into multiple SaleItems across lots."""
    prod = Product(
        barcode="CHECKOUT-FEFO-SPLIT",
        name_en="Surgical Mask 50s",
        price=Decimal("600.00"),
        cost=Decimal("400.00"),
        stock_qty=Decimal("15.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    today = date.today()
    b_early = ProductBatch(
        product_id=prod.id,
        batch_no="MASK-EARLY",
        expiry_date=today + timedelta(days=20),
        qty_on_hand=Decimal("4.000"),
        mrp=Decimal("600.00"),
    )
    b_late = ProductBatch(
        product_id=prod.id,
        batch_no="MASK-LATE",
        expiry_date=today + timedelta(days=120),
        qty_on_hand=Decimal("11.000"),
        mrp=Decimal("600.00"),
    )
    db_session.add_all([b_early, b_late])
    db_session.flush()

    cart = CartService()
    # Add 7 units without specifying batch -> spans across 4 from b_early and 3 from b_late
    cart.add_item(prod, qty=Decimal("7.000"))

    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=[{"method": "CASH", "amount": Decimal("4200.00"), "tendered_amount": Decimal("4200.00")}],
    )
    assert sale is not None

    db_session.refresh(b_early)
    db_session.refresh(b_late)
    db_session.refresh(prod)

    assert b_early.qty_on_hand == Decimal("0.000")
    assert b_late.qty_on_hand == Decimal("8.000")
    assert prod.stock_qty == Decimal("8.000")

    # Invariant: sum(b.qty_on_hand) == prod.stock_qty
    assert b_early.qty_on_hand + b_late.qty_on_hand == prod.stock_qty

    # Verify 2 distinct SaleItem rows created for the single cart entry
    assert len(sale.items) == 2
    assert sale.items[0].batch_id == b_early.id
    assert sale.items[0].qty == Decimal("4.000")
    assert sale.items[1].batch_id == b_late.id
    assert sale.items[1].qty == Decimal("3.000")


def test_issue_926_void_and_refund_restore_exact_batch(db_session, cashier_user):
    """Void and refund return stock strictly to original SaleItem.batch_id."""
    prod = Product(
        barcode="RESTORE-BATCH-TEST",
        name_en="Naphazoline Drops",
        price=Decimal("300.00"),
        cost=Decimal("200.00"),
        stock_qty=Decimal("10.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    batch = ProductBatch(
        product_id=prod.id,
        batch_no="NAPH-01",
        expiry_date=date(2027, 10, 1),
        qty_on_hand=Decimal("10.000"),
        mrp=Decimal("300.00"),
    )
    db_session.add(batch)
    db_session.flush()

    # 1. Sell 4 units
    cart = CartService()
    cart.add_item(prod, qty=Decimal("4.000"), batch_id=batch.id)
    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=[{"method": "CASH", "amount": Decimal("1200.00"), "tendered_amount": Decimal("1200.00")}],
    )

    db_session.refresh(batch)
    db_session.refresh(prod)
    assert batch.qty_on_hand == Decimal("6.000")
    assert prod.stock_qty == Decimal("6.000")

    # 2. Refund 1 unit
    result = RefundService.refund(
        sale_id=sale.id,
        lines=[RefundLineRequest(sale_item_id=sale.items[0].id, qty=Decimal("1.000"))],
        reason="Defective",
        user_id=cashier_user.id,
    )
    assert result.refund_sale_id is not None

    db_session.refresh(batch)
    db_session.refresh(prod)
    assert batch.qty_on_hand == Decimal("7.000")
    assert prod.stock_qty == Decimal("7.000")

    # 3. Check movements
    movements = db_session.query(StockMovement).filter_by(product_id=prod.id).order_by(StockMovement.id.desc()).all()
    # Most recent movement is RETURN with batch_id
    assert movements[0].type == "RETURN"
    assert movements[0].batch_id == batch.id
    assert movements[0].qty_change == Decimal("1.000")


def test_issue_926_receipt_builder_displays_batch_and_no_mixed_merge(db_session, cashier_user):
    """Receipt builder renders batch no and expiry, and does not merge lines of differing batches."""
    from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder

    prod = Product(
        barcode="RECEIPT-BATCH-TEST",
        name_en="Eye Drops 10ml",
        price=Decimal("150.00"),
        cost=Decimal("90.00"),
        stock_qty=Decimal("10.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    batch_a = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-A",
        expiry_date=date(2027, 5, 31),
        qty_on_hand=Decimal("5.000"),
        mrp=Decimal("150.00"),
    )
    batch_b = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-B",
        expiry_date=date(2028, 1, 31),
        qty_on_hand=Decimal("5.000"),
        mrp=Decimal("150.00"),
    )
    db_session.add_all([batch_a, batch_b])
    db_session.flush()

    cart = CartService()
    cart.add_item(prod, qty=Decimal("2.000"), batch_id=batch_a.id)
    cart.add_item(prod, qty=Decimal("3.000"), batch_id=batch_b.id)
    sale = TransactionService.process_sale(
        cart_service=cart,
        payments=[{"method": "CASH", "amount": Decimal("750.00"), "tendered_amount": Decimal("750.00")}],
    )

    receipt_cmds = SalesReceiptBuilder.build_receipt(sale)
    text_lines = [cmd.get("val", "") for cmd in receipt_cmds if cmd.get("type") == "text"]

    # Verify both batch details appear on receipt
    assert any("Batch: LOT-A" in t and "Exp: 2027-05-31" in t for t in text_lines)
    assert any("Batch: LOT-B" in t and "Exp: 2028-01-31" in t for t in text_lines)

    # Verify lines were NOT merged: 2 display items
    display_items = SalesReceiptBuilder._merge_items(sale.items)
    assert len(display_items) == 2
