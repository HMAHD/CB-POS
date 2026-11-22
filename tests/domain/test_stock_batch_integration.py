"""Tests for StockService and PurchaseService batch tracking integration (#926)."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.features import Features
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Permission, Product, ProductBatch, PurchaseItem, Role, Supplier, Unit, User
from cbpos.core.services.feature_flags import FeatureFlags
from cbpos.core.services.purchase_service import GrnLine, GrnRequest, PurchaseService
from cbpos.core.services.stock_service import StockService

_counter = 0


@pytest.fixture(autouse=True)
def enable_features_flag():
    FeatureFlags.invalidate_cache()
    with patch.object(
        FeatureFlags,
        "is_on",
        side_effect=lambda name: name in (Features.UNIT_CONVERSION, Features.BATCHES, Features.EXPIRY_DATES),
    ):
        yield
    FeatureFlags.invalidate_cache()


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    perms = []
    for code in (Permissions.PURCHASE_CREATE_GRN, Permissions.INVENTORY_STOCK_ADJUST, Permissions.SALES_ADD_ITEM):
        p = db_session.query(Permission).filter_by(code=code).first()
        if not p:
            p = Permission(code=code, description=code, group="Test")
            db_session.add(p)
        perms.append(p)
    role = Role(name=f"BatchTestRole_{_counter}", permissions=perms)
    user = User(username=f"batch_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"Batch Supplier {_counter}", current_payable=Decimal("0.00"))
    db_session.add(supplier)
    db_session.flush()
    return supplier


def test_issue_926_stock_movement_updates_batch_qty_and_records_batch_id(db_session, test_user):
    """StockService.record_movement with batch_id updates both Product and ProductBatch quantities."""
    prod = Product(
        barcode="STOCK-BATCH-001",
        name_en="Paracetamol 500mg",
        price=Decimal("100.00"),
        cost=Decimal("70.00"),
        stock_qty=Decimal("10.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    batch = ProductBatch(
        product_id=prod.id,
        batch_no="B001",
        expiry_date=date(2027, 5, 31),
        qty_on_hand=Decimal("10.000"),
        cost=Decimal("70.00"),
        mrp=Decimal("100.00"),
    )
    db_session.add(batch)
    db_session.flush()

    # Increase stock
    mov1 = StockService.record_movement(
        product_id=prod.id,
        qty_change=Decimal("5.000"),
        movement_type="PURCHASE",
        user_id=test_user.id,
        batch_id=batch.id,
        session=db_session,
    )
    assert mov1.batch_id == batch.id
    assert prod.stock_qty == Decimal("15.000")
    assert batch.qty_on_hand == Decimal("15.000")

    # Decrease stock
    mov2 = StockService.record_movement(
        product_id=prod.id,
        qty_change=Decimal("-3.000"),
        movement_type="SALE",
        user_id=test_user.id,
        batch_id=batch.id,
        session=db_session,
    )
    assert mov2.batch_id == batch.id
    assert prod.stock_qty == Decimal("12.000")
    assert batch.qty_on_hand == Decimal("12.000")

    # Invariant: sum(batch.qty_on_hand) == prod.stock_qty
    assert batch.qty_on_hand == prod.stock_qty


def test_issue_926_stock_movement_reactivates_inactive_batch(db_session, test_user):
    """Returning or adding stock to an inactive batch reactivates it."""
    prod = Product(
        barcode="STOCK-BATCH-REACTIVATE",
        name_en="Antibiotic Drops",
        price=Decimal("250.00"),
        cost=Decimal("180.00"),
        stock_qty=Decimal("0.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    batch = ProductBatch(
        product_id=prod.id,
        batch_no="INACTIVE-01",
        expiry_date=date(2028, 1, 1),
        qty_on_hand=Decimal("0.000"),
        is_active=False,
    )
    db_session.add(batch)
    db_session.flush()

    # Receiving return stock reactivates batch
    StockService.record_movement(
        product_id=prod.id,
        qty_change=Decimal("2.000"),
        movement_type="RETURN",
        user_id=test_user.id,
        batch_id=batch.id,
        session=db_session,
    )
    assert batch.is_active is True
    assert batch.qty_on_hand == Decimal("2.000")
    assert prod.stock_qty == Decimal("2.000")


def test_issue_926_receive_goods_creates_or_increments_batch_in_base_units(db_session, test_user, test_supplier):
    """GRN captures batch details, converts to base units, and links PurchaseItem to ProductBatch."""
    box_unit = Unit(name="Box", abbreviation="bx")
    piece_unit = Unit(name="Piece", abbreviation="pc")
    db_session.add_all([box_unit, piece_unit])
    db_session.flush()

    prod = Product(
        barcode="GRN-BATCH-CONV",
        name_en="Vitamin C 500mg",
        price=Decimal("20.00"),
        cost=Decimal("12.00"),
        stock_qty=Decimal("0.000"),
        unit_id=piece_unit.id,
        purchase_unit_id=box_unit.id,
        purchase_factor=Decimal("10.000"),  # 10 pieces per box
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    # Receive 3 boxes @ 150.00/box -> 30 pieces @ 15.00/piece
    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-BATCH-001",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=prod.id,
                qty=Decimal("3.000"),
                unit_cost=Decimal("150.00"),
                mode="PURCHASE",
                purchase_unit_id=box_unit.id,
                purchase_factor=Decimal("10.000"),
                batch_no="VITC-B1",
                expiry_date="06/27",
                mrp=Decimal("25.00"),
            )
        ],
        user_id=test_user.id,
    )

    purchase = PurchaseService.receive_goods(req)
    assert purchase.id is not None

    # Verify PurchaseItem links to batch
    item = db_session.query(PurchaseItem).filter_by(purchase_id=purchase.id).first()
    assert item.batch_id is not None
    batch = db_session.get(ProductBatch, item.batch_id)
    assert batch is not None
    assert batch.batch_no == "VITC-B1"
    assert batch.expiry_date == date(2027, 6, 30)
    assert batch.mrp == Decimal("25.00")
    # Base units check: 3 boxes * 10 = 30 pieces
    assert batch.qty_on_hand == Decimal("30.000")
    assert prod.stock_qty == Decimal("30.000")

    # Invariant: sum(batch.qty_on_hand) == prod.stock_qty
    batches = db_session.query(ProductBatch).filter_by(product_id=prod.id).all()
    assert sum(b.qty_on_hand for b in batches) == prod.stock_qty

    # Second GRN with the same lot: merges into existing batch
    req2 = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-BATCH-002",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=prod.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("150.00"),
                mode="PURCHASE",
                purchase_unit_id=box_unit.id,
                purchase_factor=Decimal("10.000"),
                batch_no="VITC-B1",
                expiry_date="06/27",
                mrp=Decimal("25.00"),
            )
        ],
        user_id=test_user.id,
    )
    PurchaseService.receive_goods(req2)

    db_session.refresh(batch)
    db_session.refresh(prod)
    # Total: 30 + 20 = 50 pieces
    assert batch.qty_on_hand == Decimal("50.000")
    assert prod.stock_qty == Decimal("50.000")
    assert len(db_session.query(ProductBatch).filter_by(product_id=prod.id).all()) == 1


def test_issue_926_receive_goods_tracked_product_requires_batch_or_expiry(db_session, test_user, test_supplier):
    """GRN for a batch-tracked product rejects lines missing both batch_no and expiry_date."""
    prod = Product(
        barcode="GRN-MISSING-BATCH",
        name_en="Eye Drops",
        price=Decimal("500.00"),
        cost=Decimal("350.00"),
        stock_qty=Decimal("0.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-BATCH-ERR",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=prod.id,
                qty=Decimal("5.000"),
                unit_cost=Decimal("350.00"),
                batch_no=None,
                expiry_date=None,
            )
        ],
        user_id=test_user.id,
    )

    with pytest.raises(ValueError, match="requires a batch number or expiry date"):
        PurchaseService.receive_goods(req)


def test_issue_926_stock_movement_without_batch_id_on_tracked_product_fails(db_session, test_user):
    """StockService.record_movement on a batch-tracked product requires batch_id to preserve Invariant 1."""
    prod = Product(
        barcode="STOCK-NO-BATCH-001",
        name_en="Tracked Paracetamol",
        price=Decimal("100.00"),
        cost=Decimal("70.00"),
        stock_qty=Decimal("10.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    batch = ProductBatch(
        product_id=prod.id,
        batch_no="B001",
        expiry_date=date(2027, 5, 31),
        qty_on_hand=Decimal("10.000"),
        cost=Decimal("70.00"),
        mrp=Decimal("100.00"),
    )
    db_session.add(batch)
    db_session.flush()

    # Calling record_movement with batch_id=None on a tracked product must raise ValueError
    with pytest.raises(ValueError, match="Batch ID required"):
        StockService.record_movement(
            product_id=prod.id,
            qty_change=Decimal("-2.000"),
            movement_type="ADJUSTMENT",
            user_id=test_user.id,
            session=db_session,
            batch_id=None,
        )

    # Invariant preserved: stock_qty is still 10, batch is still 10
    assert prod.stock_qty == Decimal("10.000")
    assert batch.qty_on_hand == Decimal("10.000")


def test_issue_926_adjust_stock_without_batch_id_on_tracked_product_fails(db_session, test_user):
    """InventoryService.adjust_stock on a batch-tracked product requires batch_id."""
    from cbpos.core.services.inventory_service import InventoryService

    prod = Product(
        barcode="ADJUST-NO-BATCH-001",
        name_en="Tracked Syrup",
        price=Decimal("200.00"),
        cost=Decimal("150.00"),
        stock_qty=Decimal("15.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    batch = ProductBatch(
        product_id=prod.id,
        batch_no="B002",
        expiry_date=date(2027, 8, 31),
        qty_on_hand=Decimal("15.000"),
        cost=Decimal("150.00"),
        mrp=Decimal("200.00"),
    )
    db_session.add(batch)
    db_session.commit()

    inv_service = InventoryService()
    with pytest.raises(ValueError, match="Batch selection required"):
        inv_service.adjust_stock(
            product_id=prod.id,
            qty_change=Decimal("-3.000"),
            reason="DAMAGED",
            user_id=test_user.id,
            batch_id=None,
        )

    # Invariant preserved: stock_qty is still 15
    reloaded_prod = db_session.get(Product, prod.id)
    reloaded_batch = db_session.get(ProductBatch, batch.id)
    assert reloaded_prod.stock_qty == Decimal("15.000")
    assert reloaded_batch.qty_on_hand == Decimal("15.000")
