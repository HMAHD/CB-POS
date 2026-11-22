"""Tests for BatchService, FEFO allocation engine, and synthetic opening batches (#926)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from cbpos.core.models import Product, ProductBatch
from cbpos.core.services.batch_service import (
    BatchService,
    ExpiredBatchError,
    InsufficientStockError,
)


def test_issue_926_parse_mmyy_to_month_end():
    """MM/YY expiry strings parse to the exact month-end date with leap year support."""
    # Standard 31-day month
    assert BatchService.parse_mmyy_to_month_end("12/26") == date(2026, 12, 31)
    assert BatchService.parse_mmyy_to_month_end("1226") == date(2026, 12, 31)
    assert BatchService.parse_mmyy_to_month_end("12-2026") == date(2026, 12, 31)
    assert BatchService.parse_mmyy_to_month_end("01/25") == date(2025, 1, 31)

    # 30-day month
    assert BatchService.parse_mmyy_to_month_end("04/25") == date(2025, 4, 30)

    # Leap year February
    assert BatchService.parse_mmyy_to_month_end("02/24") == date(2024, 2, 29)
    assert BatchService.parse_mmyy_to_month_end("02/28") == date(2028, 2, 29)

    # Non-leap year February
    assert BatchService.parse_mmyy_to_month_end("02/25") == date(2025, 2, 28)

    # Invalid values raise ValueError
    with pytest.raises(ValueError):
        BatchService.parse_mmyy_to_month_end("13/25")
    with pytest.raises(ValueError):
        BatchService.parse_mmyy_to_month_end("00/25")
    with pytest.raises(ValueError):
        BatchService.parse_mmyy_to_month_end("invalid")


def test_issue_926_get_batches_for_product_fefo_order(db_session):
    """Batches are returned in strict FEFO order: expiry_date ASC NULLS LAST, received_at ASC, id ASC."""
    prod = Product(
        barcode="PANADOL-FEFO",
        name_en="Panadol Actifast",
        price=Decimal("120.00"),
        cost=Decimal("90.00"),
        stock_qty=Decimal("30.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    today = date.today()
    b_later = ProductBatch(
        product_id=prod.id,
        batch_no="B-LATER",
        expiry_date=today + timedelta(days=90),
        qty_on_hand=Decimal("10.000"),
    )
    b_earlier = ProductBatch(
        product_id=prod.id,
        batch_no="B-EARLIER",
        expiry_date=today + timedelta(days=30),
        qty_on_hand=Decimal("10.000"),
    )
    b_no_expiry = ProductBatch(
        product_id=prod.id,
        batch_no="B-NO-EXP",
        expiry_date=None,
        qty_on_hand=Decimal("10.000"),
    )
    db_session.add_all([b_later, b_earlier, b_no_expiry])
    db_session.flush()

    batches = BatchService.get_batches_for_product(prod.id, session=db_session)
    assert len(batches) == 3
    assert batches[0].batch_no == "B-EARLIER"
    assert batches[1].batch_no == "B-LATER"
    assert batches[2].batch_no == "B-NO-EXP"


def test_issue_926_differing_mrps_triggers_batch_picker(db_session):
    """Batch picker is required only when tracked active batches carry differing MRPs."""
    prod = Product(
        barcode="MRP-TEST",
        name_en="Differing MRP Biscuit",
        price=Decimal("200.00"),
        cost=Decimal("150.00"),
        stock_qty=Decimal("20.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    # Case 1: All batches have identical MRP -> picker NOT required
    b1 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-1",
        expiry_date=date(2027, 1, 1),
        mrp=Decimal("200.00"),
        qty_on_hand=Decimal("10.000"),
    )
    b2 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-2",
        expiry_date=date(2027, 6, 1),
        mrp=Decimal("200.00"),
        qty_on_hand=Decimal("10.000"),
    )
    db_session.add_all([b1, b2])
    db_session.flush()

    assert not BatchService.requires_batch_picker(prod.id, session=db_session)
    assert BatchService.get_active_differing_mrps(prod.id, session=db_session) == [Decimal("200.00")]

    # Case 2: New batch arrives with higher MRP -> picker IS required
    b3 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-3",
        expiry_date=date(2027, 9, 1),
        mrp=Decimal("220.00"),
        qty_on_hand=Decimal("5.000"),
    )
    db_session.add(b3)
    db_session.flush()

    assert BatchService.requires_batch_picker(prod.id, session=db_session)
    mrps = BatchService.get_active_differing_mrps(prod.id, session=db_session)
    assert set(mrps) == {Decimal("200.00"), Decimal("220.00")}


def test_issue_926_allocate_fefo_stock_splits_and_skips_expired(db_session):
    """FEFO allocation automatically splits requested qty across lots and skips expired batches."""
    prod = Product(
        barcode="FEFO-SPLIT",
        name_en="Siddhalepa Balm 50g",
        price=Decimal("450.00"),
        cost=Decimal("350.00"),
        stock_qty=Decimal("25.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    today = date.today()
    # Expired batch: should NOT be allocated
    b_expired = ProductBatch(
        product_id=prod.id,
        batch_no="EXP-LOT",
        expiry_date=today - timedelta(days=5),
        qty_on_hand=Decimal("10.000"),
    )
    # Valid batch 1: 5 units
    b_valid1 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-EARLY",
        expiry_date=today + timedelta(days=20),
        qty_on_hand=Decimal("5.000"),
    )
    # Valid batch 2: 10 units
    b_valid2 = ProductBatch(
        product_id=prod.id,
        batch_no="LOT-LATE",
        expiry_date=today + timedelta(days=60),
        qty_on_hand=Decimal("10.000"),
    )
    db_session.add_all([b_expired, b_valid1, b_valid2])
    db_session.flush()

    # Request 8 units: should skip b_expired, take 5 from b_valid1 and 3 from b_valid2
    allocations = BatchService.allocate_fefo_stock(prod.id, Decimal("8.000"), session=db_session)
    assert len(allocations) == 2
    assert allocations[0][0].id == b_valid1.id
    assert allocations[0][1] == Decimal("5.000")
    assert allocations[1][0].id == b_valid2.id
    assert allocations[1][1] == Decimal("3.000")

    # Request 20 units: only 15 valid available -> InsufficientStockError when allow_negative_stock is False
    with pytest.raises(InsufficientStockError):
        BatchService.allocate_fefo_stock(prod.id, Decimal("20.000"), allow_negative_stock=False, session=db_session)

    # When allow_negative_stock is True: allocates all 15 valid, then newest absorbs the remaining 5
    alloc_neg = BatchService.allocate_fefo_stock(
        prod.id, Decimal("20.000"), allow_negative_stock=True, session=db_session
    )
    total_allocated = sum(qty for _, qty in alloc_neg)
    assert total_allocated == Decimal("20.000")


def test_issue_926_create_synthetic_opening_batch(db_session):
    """Enabling tracks_batches on an existing product creates a synthetic opening batch."""
    prod = Product(
        barcode="SYNTH-TEST",
        name_en="Highland Butter 200g",
        price=Decimal("850.00"),
        cost=Decimal("700.00"),
        stock_qty=Decimal("42.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    opening = BatchService.create_synthetic_opening_batch(prod, session=db_session)
    assert opening is not None
    assert opening.batch_no == "OPENING"
    assert opening.expiry_date is None
    assert opening.qty_on_hand == Decimal("42.000")
    assert opening.cost == Decimal("700.00")
    assert opening.mrp == Decimal("850.00")
    assert opening.is_active is True

    # Invariant check: sum(b.qty_on_hand) == product.stock_qty
    batches = BatchService.get_batches_for_product(prod.id, include_zero_stock=True, session=db_session)
    total_batch_qty = sum(b.qty_on_hand for b in batches)
    assert total_batch_qty == prod.stock_qty


def test_issue_926_validate_batch_allocation_blocks_expired_without_override(db_session):
    """Explicit batch selection rejects expired batches unless allow_expired=True."""
    prod = Product(
        barcode="EXP-VALIDATE",
        name_en="Expiring Milk",
        price=Decimal("350.00"),
        cost=Decimal("280.00"),
        stock_qty=Decimal("10.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    b_expired = ProductBatch(
        product_id=prod.id,
        batch_no="MILK-OLD",
        expiry_date=date.today() - timedelta(days=1),
        qty_on_hand=Decimal("10.000"),
    )
    db_session.add(b_expired)
    db_session.flush()

    # Blocked by default
    with pytest.raises(ExpiredBatchError) as exc_info:
        BatchService.validate_batch_allocation(
            prod.id, b_expired.id, Decimal("1.000"), allow_expired=False, session=db_session
        )
    assert exc_info.value.batch.id == b_expired.id

    # Allowed with override
    batch = BatchService.validate_batch_allocation(
        prod.id, b_expired.id, Decimal("1.000"), allow_expired=True, session=db_session
    )
    assert batch.id == b_expired.id


def test_issue_926_validate_batch_allocation_rejects_inactive_batch(db_session):
    """Explicit batch selection rejects deactivated/recalled batches."""
    prod = Product(
        barcode="INACTIVE-VALIDATE",
        name_en="Recalled Medicine",
        price=Decimal("150.00"),
        cost=Decimal("100.00"),
        stock_qty=Decimal("10.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    b_inactive = ProductBatch(
        product_id=prod.id,
        batch_no="RECALL-01",
        expiry_date=date.today() + timedelta(days=60),
        qty_on_hand=Decimal("10.000"),
        is_active=False,
    )
    db_session.add(b_inactive)
    db_session.flush()

    with pytest.raises(ValueError, match="inactive and cannot be sold"):
        BatchService.validate_batch_allocation(
            prod.id, b_inactive.id, Decimal("1.000"), allow_expired=True, session=db_session
        )


def test_issue_926_reconcile_batches_when_toggling_tracking_restores_invariant(db_session):
    """Toggling tracks_batches off, moving stock, and toggling back on reconciles batch quantities."""
    from cbpos.core.models import Role, User
    from cbpos.core.services.inventory_service import InventoryService
    from cbpos.core.services.stock_service import StockService

    role = Role(name="ReconcileTestRole")
    user = User(username="reconcile_user", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()

    prod = Product(
        barcode="TOGGLE-RECON-01",
        name_en="Toggle Reconcile Item",
        price=Decimal("500.00"),
        cost=Decimal("350.00"),
        stock_qty=Decimal("10.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    # Initial opening batch
    b_opening = BatchService.create_synthetic_opening_batch(prod, session=db_session)
    assert b_opening.qty_on_hand == Decimal("10.000")

    # 1. Toggle tracking off
    inv_service = InventoryService()
    inv_service.update_product(prod.id, {"tracks_batches": False})
    db_session.refresh(prod)
    assert prod.tracks_batches is False

    # 2. Stock moves while tracking is off (e.g. sale of 4 units)
    StockService.record_movement(
        product_id=prod.id,
        qty_change=Decimal("-4.000"),
        movement_type="SALE",
        user_id=user.id,
        session=db_session,
        batch_id=None,
    )
    db_session.refresh(prod)
    assert prod.stock_qty == Decimal("6.000")

    # 3. Toggle tracking back on
    inv_service.update_product(prod.id, {"tracks_batches": True})
    db_session.refresh(prod)
    assert prod.tracks_batches is True

    # 4. Invariant must hold: sum of batches == product.stock_qty
    all_batches = db_session.query(ProductBatch).filter_by(product_id=prod.id).all()
    total_batch_qty = sum(b.qty_on_hand for b in all_batches)
    assert total_batch_qty == prod.stock_qty == Decimal("6.000")
