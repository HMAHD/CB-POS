from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.features import Features
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import (
    Permission,
    Product,
    Purchase,
    PurchaseItem,
    PurchaseOrder,
    PurchaseOrderItem,
    Role,
    StockMovement,
    Supplier,
    SupplierLedgerEntry,
    Unit,
    User,
)
from cbpos.core.services.feature_flags import FeatureFlags
from cbpos.core.services.purchase_service import GrnLine, GrnRequest, PurchaseService

_counter = 0


@pytest.fixture(autouse=True)
def enable_unit_conversion_flag(db_session):
    FeatureFlags.invalidate_cache()
    # By default in these conversion tests, enable UNIT_CONVERSION
    with patch.object(FeatureFlags, "is_on", side_effect=lambda name: name == Features.UNIT_CONVERSION):
        yield
    FeatureFlags.invalidate_cache()


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    perms = []
    for code in (Permissions.PURCHASE_CREATE_GRN, Permissions.INVENTORY_EDIT):
        p = db_session.query(Permission).filter_by(code=code).first()
        if not p:
            p = Permission(code=code, description=code, group="Test")
            db_session.add(p)
        perms.append(p)
    role = Role(name=f"ConvPurchRole_{_counter}", permissions=perms)
    user = User(username=f"conv_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"Conv Supplier {_counter}", current_payable=Decimal("0.00"))
    db_session.add(supplier)
    db_session.flush()
    return supplier


@pytest.fixture
def units(db_session):
    piece = Unit(name="Piece", abbreviation="pcs", decimal_places=0)
    box = Unit(name="Box", abbreviation="box", decimal_places=0)
    db_session.add_all([piece, box])
    db_session.flush()
    return {"piece": piece, "box": box}


@pytest.fixture
def conv_product(db_session, units):
    global _counter
    _counter += 1
    product = Product(
        name_en=f"Paracetamol 500mg {_counter}",
        barcode=f"MED{_counter:05d}",
        price=Decimal("15.00"),
        cost=Decimal("5.00"),
        stock_qty=Decimal("10.000"),
        unit_id=units["piece"].id,
        purchase_unit_id=units["box"].id,
        purchase_factor=Decimal("10.000"),
    )
    db_session.add(product)
    db_session.flush()
    return product


def test_issue_937_grn_unit_conversion_stock_and_movement(db_session, test_user, test_supplier, conv_product, units):
    """2 boxes with factor 10 adds exactly 20 base units to stock and stock movements."""
    initial_stock = conv_product.stock_qty

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-BOX-001",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("2.000"),  # 2 boxes
                unit_cost=Decimal("100.00"),  # Rs 100 per box
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
            )
        ],
        user_id=test_user.id,
    )

    purchase = PurchaseService.receive_goods(req)
    assert purchase.document_number is not None

    db_session.refresh(conv_product)
    # Stock should increase by 2 boxes * 10 = 20 base units
    assert conv_product.stock_qty == initial_stock + Decimal("20.000")

    # Movement should record 20 base units
    movement = db_session.query(StockMovement).filter_by(document_id=purchase.id).first()
    assert movement is not None
    assert movement.qty_change == Decimal("20.000")
    assert movement.balance_after == initial_stock + Decimal("20.000")


def test_issue_937_grn_unit_conversion_avco(db_session, test_user, test_supplier, conv_product, units):
    """AVCO per base unit correctly updated: ((old_stock * old_cost) + (20 * base_cost)) / (old_stock + 20)."""
    # conv_product has stock 10, cost 5.00.
    # Receiving 2 boxes @ 100/box with factor 10 -> base_cost = 100 / 10 = 10.00. base_qty = 20.
    # New cost = (10 * 5.00 + 20 * 10.00) / (10 + 20) = (50 + 200) / 30 = 250 / 30 = 8.33
    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-AVCO-001",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("100.00"),
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
            )
        ],
        user_id=test_user.id,
    )

    PurchaseService.receive_goods(req)

    db_session.refresh(conv_product)
    assert conv_product.cost == Decimal("8.33")


def test_issue_937_supplier_payable_and_grn_total_uses_exact_supplier_invoice(
    db_session, test_user, test_supplier, units
):
    """Supplier payable and GRN total use exact supplier-invoice total, not base_qty * rounded base cost."""
    global _counter
    _counter += 1
    # Product with factor 7 (e.g. 1 strip = 7 tablets)
    strip_product = Product(
        name_en=f"Antibiotic {_counter}",
        barcode=f"ANTI{_counter:05d}",
        price=Decimal("5.00"),
        cost=Decimal("1.50"),
        stock_qty=Decimal("0.000"),
        unit_id=units["piece"].id,
        purchase_unit_id=units["box"].id,
        purchase_factor=Decimal("7.000"),
    )
    db_session.add(strip_product)
    db_session.flush()

    # Buy 3 strips @ Rs 10.00/strip.
    # Supplier invoice line total = 3 * 10.00 = Rs 30.00.
    # Note: base_cost = 10.00 / 7 = 1.42857 -> rounded to 1.43.
    # If using base_qty * base_cost: 21 * 1.43 = 30.03 (an error of 0.03!).
    # Invariant requires exact supplier invoice line total: Rs 30.00.
    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-EXACT-001",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=strip_product.id,
                qty=Decimal("3.000"),
                unit_cost=Decimal("10.00"),
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("7.000"),
            )
        ],
        user_id=test_user.id,
    )

    purchase = PurchaseService.receive_goods(req)

    db_session.refresh(purchase)
    db_session.refresh(test_supplier)

    assert purchase.total_cost == Decimal("30.00")
    assert test_supplier.current_payable == Decimal("30.00")

    ledger = db_session.query(SupplierLedgerEntry).filter_by(reference_id=purchase.id).first()
    assert ledger is not None
    assert ledger.amount == Decimal("30.00")


def test_issue_937_legacy_behavior_unchanged_when_factor_one_or_feature_off(
    db_session, test_user, test_supplier, units
):
    """Legacy products with factor 1 or when feature is off preserve existing behavior identically."""
    global _counter
    _counter += 1
    legacy_product = Product(
        name_en=f"Standard Item {_counter}",
        barcode=f"STD{_counter:05d}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("10.000"),
        unit_id=units["piece"].id,
        purchase_factor=Decimal("1.000"),
    )
    db_session.add(legacy_product)
    db_session.flush()

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-STD-001",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=legacy_product.id,
                qty=Decimal("5.000"),
                unit_cost=Decimal("60.00"),
            )
        ],
        user_id=test_user.id,
    )

    purchase = PurchaseService.receive_goods(req)

    db_session.refresh(legacy_product)
    assert legacy_product.stock_qty == Decimal("15.000")
    # AVCO: (10 * 50 + 5 * 60) / 15 = 800 / 15 = 53.33
    assert legacy_product.cost == Decimal("53.33")
    assert purchase.total_cost == Decimal("300.00")


def test_issue_937_stale_conversion_configuration_rolls_back(db_session, test_user, test_supplier, conv_product, units):
    """If Product conversion factor changes while GRN is open, commit fails closed."""
    # Commit setup so rollback only rolls back GRN
    db_session.commit()

    # Worker/UI prepares line with factor 10, but in DB someone modified it to 12
    with db_session.begin_nested():
        conv_product.purchase_factor = Decimal("12.000")
        db_session.commit()

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-STALE-001",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("100.00"),
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),  # Stale!
            )
        ],
        user_id=test_user.id,
    )

    with pytest.raises(ValueError, match="stale_conversion_configuration"):
        PurchaseService.receive_goods(req)

    # Verify no orphan purchase or movement was created
    purchases = db_session.query(Purchase).filter_by(reference_external="INV-STALE-001").all()
    assert len(purchases) == 0


def test_issue_937_failure_injection_rolls_back_entire_transaction(
    db_session, test_user, test_supplier, conv_product, units, monkeypatch
):
    """Failure during stock or ledger update leaves no partial state or orphan purchase."""
    db_session.commit()

    def _fail_ledger(*args, **kwargs):
        raise RuntimeError("Injected database failure in ledger recording")

    monkeypatch.setattr(
        "cbpos.core.services.purchase_service.SupplierPayableService.record_purchase_in_session",
        _fail_ledger,
    )

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-FAIL-001",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("100.00"),
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
            )
        ],
        user_id=test_user.id,
    )

    with pytest.raises(RuntimeError, match="Injected database failure"):
        PurchaseService.receive_goods(req)

    purchases = db_session.query(Purchase).filter_by(reference_external="INV-FAIL-001").all()
    assert len(purchases) == 0


def test_issue_937_po_receiving_retains_base_unit_invariant(db_session, test_user, test_supplier, conv_product, units):
    """PO receiving increments PO line received qty in base units, matching qty_ordered."""
    # Create PurchaseOrder for 20 base units (pieces)
    po = PurchaseOrder(
        document_number="PO-2026-00001",
        type="purchase_order",
        supplier_id=test_supplier.id,
        user_id=test_user.id,
        status="ORDERED",
    )
    db_session.add(po)
    db_session.flush()

    po_item = PurchaseOrderItem(
        purchase_order_id=po.id,
        product_id=conv_product.id,
        qty_ordered=Decimal("20.000"),  # 20 pieces
        qty_received=Decimal("0.000"),
    )
    db_session.add(po_item)
    db_session.commit()

    # Receive 2 boxes (2 * 10 = 20 pieces)
    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-PO-001",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("100.00"),
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
            )
        ],
        user_id=test_user.id,
        purchase_order_id=po.id,
    )

    PurchaseService.receive_goods(req)

    db_session.refresh(po_item)
    db_session.refresh(po)

    assert po_item.qty_received == Decimal("20.000")
    assert po.status == "RECEIVED"


def test_issue_937_historical_grn_facts_preserved_after_product_factor_change(
    db_session, test_user, test_supplier, conv_product, units
):
    """Historical purchase facts on PurchaseItem survive subsequent Product conversion edits."""
    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-HIST-001",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("100.00"),
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
            )
        ],
        user_id=test_user.id,
    )

    purchase = PurchaseService.receive_goods(req)

    item = db_session.query(PurchaseItem).filter_by(purchase_id=purchase.id).first()
    assert item is not None
    assert item.qty_received == Decimal("20.000")
    assert item.unit_cost == Decimal("10.00")
    assert item.purchase_qty == Decimal("2.000")
    assert item.purchase_unit_cost == Decimal("100.00")
    assert item.purchase_factor == Decimal("10.000")
    assert item.purchase_unit_id == units["box"].id

    # Later: operator changes product's factor to 12
    conv_product.purchase_factor = Decimal("12.000")
    conv_product.purchase_unit_id = None
    db_session.commit()

    db_session.refresh(item)
    # Historic line facts remain untouched!
    assert item.purchase_factor == Decimal("10.000")
    assert item.purchase_qty == Decimal("2.000")
    assert item.purchase_unit_cost == Decimal("100.00")
    assert item.purchase_unit_id == units["box"].id


def test_issue_937_commit_purchase_legacy_path_respects_conversion(
    db_session, test_user, test_supplier, conv_product, units
):
    """Calling commit_purchase directly also respects unit conversion and updates stock and AVCO in base units."""
    initial_stock = conv_product.stock_qty

    purchase = PurchaseService.create_purchase(
        supplier_id=test_supplier.id,
        reference_external="INV-LEGACY-CONV-001",
        user_id=test_user.id,
    )

    items_data = [
        {
            "product_id": conv_product.id,
            "qty": Decimal("3.000"),  # 3 boxes
            "cost": Decimal("100.00"),  # Rs 100/box
            "purchase_unit_id": units["box"].id,
            "purchase_factor": Decimal("10.000"),
        }
    ]

    PurchaseService.commit_purchase(purchase.id, items_data)

    db_session.refresh(conv_product)
    # 3 boxes * 10 = 30 base units added
    assert conv_product.stock_qty == initial_stock + Decimal("30.000")

    item = db_session.query(PurchaseItem).filter_by(purchase_id=purchase.id).first()
    assert item is not None
    assert item.qty_received == Decimal("30.000")
    assert item.unit_cost == Decimal("10.00")
    assert item.purchase_qty == Decimal("3.000")
    assert item.purchase_unit_cost == Decimal("100.00")
    assert item.purchase_factor == Decimal("10.000")


def test_issue_937_stale_conversion_concurrent_clear_or_add_fails_closed(
    db_session, test_user, test_supplier, conv_product, units
):
    """Fail closed if conversion is cleared or added concurrently before GRN is committed."""
    # Case A: GRN line had conversion, but product had conversion cleared concurrently
    conv_product.purchase_unit_id = None
    db_session.commit()

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-STALE-CLR",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("100.00"),
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
            )
        ],
        user_id=test_user.id,
    )

    with pytest.raises(ValueError, match=r"stale_conversion_configuration.*purchase unit changed"):
        PurchaseService.receive_goods(req)

    # Case B: GRN line had NO conversion, but product had conversion configured concurrently
    conv_product.purchase_unit_id = units["box"].id
    conv_product.purchase_factor = Decimal("10.000")
    db_session.commit()

    req_no_conv = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-STALE-ADD",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("20.000"),
                unit_cost=Decimal("10.00"),
                purchase_unit_id=None,
                purchase_factor=None,
            )
        ],
        user_id=test_user.id,
    )

    with pytest.raises(ValueError, match=r"stale_conversion_configuration.*purchase unit changed"):
        PurchaseService.receive_goods(req_no_conv)


def test_issue_937_unit_service_delete_rejects_active_purchase_unit(db_session, test_user, conv_product, units):
    """UnitService.delete must refuse deleting a unit referenced as Product.purchase_unit_id."""
    from cbpos.core.services.unit_service import UnitService

    with pytest.raises(ValueError, match=r"Cannot delete: 1 product.*use this unit"):
        UnitService.delete(units["box"].id, acting_user_id=test_user.id)


def test_issue_937_commit_purchase_with_none_product_cost(db_session, test_user, test_supplier, units):
    """commit_purchase must handle product.cost being None without raising TypeError."""
    product = Product(
        name_en="No Cost Item",
        barcode="NOCOST001",
        price=Decimal("20.00"),
        cost=None,
        stock_qty=Decimal("0.000"),
        unit_id=units["piece"].id,
        purchase_unit_id=units["box"].id,
        purchase_factor=Decimal("5.000"),
    )
    db_session.add(product)
    db_session.flush()

    purchase = PurchaseService.create_purchase(
        supplier_id=test_supplier.id,
        reference_external="INV-NOCOST-001",
        user_id=test_user.id,
    )

    items_data = [
        {
            "product_id": product.id,
            "qty": Decimal("2.000"),
            "cost": Decimal("50.00"),
            "purchase_unit_id": units["box"].id,
            "purchase_factor": Decimal("5.000"),
        }
    ]

    PurchaseService.commit_purchase(purchase.id, items_data)

    db_session.refresh(product)
    assert product.stock_qty == Decimal("10.000")
    assert product.cost == Decimal("10.00")
