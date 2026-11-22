from datetime import date, timedelta
from decimal import Decimal

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import (
    Permission,
    Product,
    ProductBatch,
    Role,
    StockMovement,
    User,
)
from cbpos.core.services.batch_service import BatchService
from cbpos.core.services.stock_count_service import StockCountService

_counter = 0


@pytest.fixture
def inv_user(db_session):
    global _counter
    _counter += 1
    p = db_session.query(Permission).filter_by(code=Permissions.STOCK_TAKE_CREATE).first()
    if not p:
        p = Permission(code=Permissions.STOCK_TAKE_CREATE, description="Create stock count", group="Inventory")
        db_session.add(p)
    role = Role(name=f"StockTakeAdmin_{_counter}", permissions=[p])
    user = User(username=f"st_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


def test_issue_926_stock_take_add_all_products_tracked(db_session, inv_user):
    """StockCountService.add_all_products creates distinct lines per active batch for tracked products."""
    prod = Product(
        name_en="Tracked Syrup",
        barcode="BAR-SYR-001",
        price=Decimal("150.00"),
        cost=Decimal("100.00"),
        stock_qty=Decimal("25.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    b1 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-A",
        expiry_date=date(2027, 4, 30),
        mrp=Decimal("150.00"),
        cost=Decimal("100.00"),
        qty_on_hand=Decimal("10.000"),
        is_active=True,
    )
    b2 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-B",
        expiry_date=date(2027, 8, 31),
        mrp=Decimal("155.00"),
        cost=Decimal("105.00"),
        qty_on_hand=Decimal("15.000"),
        is_active=True,
    )
    db_session.add_all([b1, b2])
    db_session.commit()

    sc = StockCountService.create_stock_count(user_id=inv_user.id)
    count = StockCountService.add_all_products(sc.id)
    assert count == 2

    reloaded = StockCountService.get_stock_count(sc.id)
    items = reloaded.items
    assert len(items) == 2
    batch_ids = {item.batch_id for item in items}
    assert batch_ids == {b1.id, b2.id}

    items_by_batch = {item.batch_id: item for item in items}
    assert items_by_batch[b1.id].expected_qty == Decimal("10.000")
    assert items_by_batch[b2.id].expected_qty == Decimal("15.000")


def test_issue_926_stock_take_per_batch_reconciliation(db_session, inv_user):
    """Counting specific batches adjusts individual batch quantities and preserves the batch-stock invariant."""
    prod = Product(
        name_en="Counted Pills",
        barcode="BAR-PILLS-001",
        price=Decimal("50.00"),
        cost=Decimal("30.00"),
        stock_qty=Decimal("20.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    b1 = ProductBatch(
        product_id=prod.id,
        batch_no="P-01",
        expiry_date=date(2027, 3, 31),
        mrp=Decimal("50.00"),
        cost=Decimal("30.00"),
        qty_on_hand=Decimal("10.000"),
        is_active=True,
    )
    b2 = ProductBatch(
        product_id=prod.id,
        batch_no="P-02",
        expiry_date=date(2027, 9, 30),
        mrp=Decimal("50.00"),
        cost=Decimal("30.00"),
        qty_on_hand=Decimal("10.000"),
        is_active=True,
    )
    db_session.add_all([b1, b2])
    db_session.commit()

    sc = StockCountService.create_stock_count(user_id=inv_user.id)
    it1 = StockCountService.add_single_item(sc.id, prod.id, batch_id=b1.id)
    it2 = StockCountService.add_single_item(sc.id, prod.id, batch_id=b2.id)

    # Physical count: LOT 1 is missing 2 units (count 8), LOT 2 has 1 surplus (count 11)
    StockCountService.update_count(it1.id, Decimal("8.000"))
    StockCountService.update_count(it2.id, Decimal("11.000"))

    StockCountService.finalize_count(sc.id)
    StockCountService.approve_and_apply(sc.id, inv_user.id)

    db_session.expire_all()
    b1_reloaded = db_session.get(ProductBatch, b1.id)
    b2_reloaded = db_session.get(ProductBatch, b2.id)
    prod_reloaded = db_session.get(Product, prod.id)

    assert b1_reloaded.qty_on_hand == Decimal("8.000")
    assert b2_reloaded.qty_on_hand == Decimal("11.000")
    assert prod_reloaded.stock_qty == Decimal("19.000")
    # Mathematical invariant holds
    assert b1_reloaded.qty_on_hand + b2_reloaded.qty_on_hand == prod_reloaded.stock_qty

    # StockMovements generated with batch_id
    movements = (
        db_session.query(StockMovement)
        .filter_by(product_id=prod.id, type="ADJUSTMENT")
        .order_by(StockMovement.id.asc())
        .all()
    )
    assert len(movements) == 2
    assert movements[0].batch_id == b1.id
    assert movements[0].qty_change == Decimal("-2.000")
    assert movements[1].batch_id == b2.id
    assert movements[1].qty_change == Decimal("1.000")


def test_issue_926_batch_service_expiring_summary_and_filter(db_session):
    """BatchService correctly aggregates expiring/expired summary and filters by horizon."""
    prod = Product(
        name_en="Expiring Items",
        barcode="BAR-EXP-001",
        price=Decimal("100.00"),
        cost=Decimal("70.00"),
        stock_qty=Decimal("40.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    today = date.today()
    # 1. Expired batch (10 days ago)
    b_expired = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-EXPIRED",
        expiry_date=today - timedelta(days=10),
        mrp=Decimal("100.00"),
        cost=Decimal("70.00"),
        qty_on_hand=Decimal("5.000"),
        is_active=True,
    )
    # 2. Expiring in 15 days
    b_15 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-15",
        expiry_date=today + timedelta(days=15),
        mrp=Decimal("100.00"),
        cost=Decimal("70.00"),
        qty_on_hand=Decimal("10.000"),
        is_active=True,
    )
    # 3. Expiring in 45 days
    b_45 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-45",
        expiry_date=today + timedelta(days=45),
        mrp=Decimal("100.00"),
        cost=Decimal("70.00"),
        qty_on_hand=Decimal("10.000"),
        is_active=True,
    )
    # 4. Expiring in 75 days
    b_75 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-75",
        expiry_date=today + timedelta(days=75),
        mrp=Decimal("100.00"),
        cost=Decimal("70.00"),
        qty_on_hand=Decimal("15.000"),
        is_active=True,
    )
    db_session.add_all([b_expired, b_15, b_45, b_75])
    db_session.commit()

    summary = BatchService.get_expiring_batches_summary()
    assert summary["expired"] == 1
    assert summary["expiring_30"] == 1
    assert summary["expiring_60"] == 2
    assert summary["expiring_90"] == 3

    # Filter 'expired'
    exp_batches = BatchService.get_expiring_batches_by_filter("expired")
    assert len(exp_batches) == 1
    assert exp_batches[0].batch_no == "LOT-EXPIRED"

    # Filter '30'
    in_30 = BatchService.get_expiring_batches_by_filter("30")
    assert len(in_30) == 1
    assert in_30[0].batch_no == "LOT-15"

    # Filter '60'
    in_60 = BatchService.get_expiring_batches_by_filter("60")
    assert len(in_60) == 2
    assert {b.batch_no for b in in_60} == {"LOT-15", "LOT-45"}

    # Filter '90'
    in_90 = BatchService.get_expiring_batches_by_filter("90")
    assert len(in_90) == 3
    assert {b.batch_no for b in in_90} == {"LOT-15", "LOT-45", "LOT-75"}
