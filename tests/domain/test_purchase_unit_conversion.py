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
from cbpos.core.utils.money import round_quantity

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


def test_issue_937_feature_toggle_while_grn_in_flight_fails_closed(
    db_session, test_user, test_supplier, conv_product, units
):
    """If UNIT_CONVERSION is toggled while a GRN is in-flight, commit must fail closed."""
    db_session.commit()
    initial_stock = conv_product.stock_qty

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-TOGGLE-001",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("100.00"),
                mode="PURCHASE",
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
        expected_unit_conversion_on=True,
    )

    # Feature is toggled OFF right before commit
    with patch.object(FeatureFlags, "is_on", return_value=False):
        with pytest.raises(ValueError, match=r"stale_conversion_configuration.*feature"):
            PurchaseService.receive_goods(req)

    db_session.refresh(conv_product)
    assert conv_product.stock_qty == initial_stock

    # Test same protection on commit_purchase
    purchase = PurchaseService.create_purchase(
        supplier_id=test_supplier.id,
        reference_external="INV-TOGGLE-LEGACY",
        user_id=test_user.id,
    )
    items_data = [
        {
            "product_id": conv_product.id,
            "qty": Decimal("2.000"),
            "cost": Decimal("100.00"),
            "mode": "PURCHASE",
            "purchase_unit_id": units["box"].id,
            "purchase_factor": Decimal("10.000"),
            "expected_unit_conversion_on": True,
        }
    ]
    with patch.object(FeatureFlags, "is_on", return_value=False):
        with pytest.raises(ValueError, match=r"stale_conversion_configuration.*feature"):
            PurchaseService.commit_purchase(purchase.id, items_data)

    db_session.refresh(conv_product)
    assert conv_product.stock_qty == initial_stock
    db_session.refresh(purchase)
    assert purchase.status == "DRAFT"


def test_issue_937_commit_purchase_fails_on_missing_product_rolls_back(
    db_session, test_user, test_supplier, conv_product, units
):
    """commit_purchase must fail on missing products, rolling back without creating partial state."""
    db_session.commit()
    initial_stock = conv_product.stock_qty
    initial_payable = test_supplier.current_payable

    purchase = PurchaseService.create_purchase(
        supplier_id=test_supplier.id,
        reference_external="INV-MISSING-PROD",
        user_id=test_user.id,
    )

    missing_pid = 999999
    items_data = [
        {
            "product_id": conv_product.id,
            "qty": Decimal("1.000"),
            "cost": Decimal("50.00"),
        },
        {
            "product_id": missing_pid,
            "qty": Decimal("2.000"),
            "cost": Decimal("20.00"),
        },
    ]

    with pytest.raises(ValueError, match=rf"Product {missing_pid} not found"):
        PurchaseService.commit_purchase(purchase.id, items_data)

    # Verify atomic rollback
    db_session.refresh(conv_product)
    assert conv_product.stock_qty == initial_stock
    db_session.refresh(test_supplier)
    assert test_supplier.current_payable == initial_payable

    db_session.refresh(purchase)
    assert purchase.status == "DRAFT"
    items_count = db_session.query(PurchaseItem).filter_by(purchase_id=purchase.id).count()
    assert items_count == 0

    # All-missing batch also rolls back
    items_all_missing = [{"product_id": 888888, "qty": Decimal("1.000"), "cost": Decimal("10.00")}]
    with pytest.raises(ValueError, match=r"Product 888888 not found"):
        PurchaseService.commit_purchase(purchase.id, items_all_missing)
    db_session.refresh(purchase)
    assert purchase.status == "DRAFT"


def test_issue_937_historical_unit_labels_immutable(qapp, db_session, test_user, test_supplier, conv_product, units):
    """Historical unit labels on PurchaseItem survive Unit renaming, deactivation, and Product unit replacement."""
    db_session.commit()
    from cbpos.ui.dialogs.grn_detail_dialog import GRNDetailDialog

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-IMMUT-LABELS",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("100.00"),
                mode="PURCHASE",
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
            )
        ],
        user_id=test_user.id,
    )

    purchase = PurchaseService.receive_goods(req)

    item = db_session.query(PurchaseItem).filter_by(purchase_id=purchase.id).first()
    assert item is not None
    assert item.purchase_unit_name == "Box"
    assert item.base_unit_name == "Piece"

    # Now mutate the catalog:
    # 1. Rename "Box" to "SuperBox"
    units["box"].name = "SuperBox"
    # 2. Deactivate "Box"
    units["box"].is_active = False
    # 3. Create a new unit and assign as product's base unit
    tablet = Unit(name="Tablet", abbreviation="tab", decimal_places=0)
    db_session.add(tablet)
    db_session.flush()
    conv_product.unit_id = tablet.id
    db_session.commit()

    # Verify PurchaseItem snapshots remain unchanged
    db_session.refresh(item)
    assert item.purchase_unit_name == "Box"
    assert item.base_unit_name == "Piece"

    # Verify dialog displays snapshot labels, not renamed/replaced units
    dialog = GRNDetailDialog(purchase.id)
    qty_text = dialog.table.item(0, 2).text()
    assert "2" in qty_text
    assert "Box" in qty_text
    assert "SuperBox" not in qty_text
    assert "Piece" in qty_text
    assert "Tablet" not in qty_text


def test_issue_937_po_partial_receipt_exact_conversion_and_base_fallback(db_session, test_user, test_supplier, units):
    """PO partial receipts reach RECEIVED with zero remainder, falling back to BASE mode when not exact."""
    from cbpos.core.models import PurchaseOrder, PurchaseOrderItem

    # Product with purchase factor = 3 (Pack of 3)
    pack3 = Unit(name="Pack3", abbreviation="pk3", decimal_places=0)
    db_session.add(pack3)
    db_session.flush()

    prod = Product(
        barcode="B_TRIPACK",
        name_en="Tri-Pack Battery",
        cost=Decimal("30.00"),
        price=Decimal("45.00"),
        stock_qty=Decimal("0.000"),
        unit_id=units["piece"].id,
        purchase_unit_id=pack3.id,
        purchase_factor=Decimal("3.000"),
        default_supplier_id=test_supplier.id,
    )
    db_session.add(prod)
    db_session.commit()

    # Create PO for 10 base units (pieces)
    po = PurchaseOrder(
        document_number="PO-PARTIAL-001",
        supplier_id=test_supplier.id,
        user_id=test_user.id,
        status="ORDERED",
        date=datetime.now(),
    )
    db_session.add(po)
    db_session.flush()

    po_item = PurchaseOrderItem(
        purchase_order_id=po.id,
        product_id=prod.id,
        qty_ordered=Decimal("10.000"),
        qty_received=Decimal("0.000"),
    )
    db_session.add(po_item)
    db_session.commit()

    # 1. First receipt: 2 packs (= 6 pieces) via PURCHASE mode
    req1 = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-PARTIAL-1",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=prod.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("90.00"),  # 90 per pack of 3 -> 30 per piece
                mode="PURCHASE",
                purchase_unit_id=pack3.id,
                purchase_factor=Decimal("3.000"),
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
        purchase_order_id=po.id,
        expected_unit_conversion_on=True,
    )
    PurchaseService.receive_goods(req1)

    db_session.refresh(po)
    db_session.refresh(po_item)
    db_session.refresh(prod)
    assert po.status == "PARTIALLY_RECEIVED"
    assert po_item.qty_received == Decimal("6.000")
    assert prod.stock_qty == Decimal("6.000")

    # Remaining outstanding = 4 pieces
    outstanding = po_item.qty_ordered - po_item.qty_received
    assert outstanding == Decimal("4.000")

    # Prove exactness check fails for 4 pieces / factor 3:
    candidate_p_qty = round_quantity(outstanding / prod.purchase_factor)
    assert round_quantity(candidate_p_qty * prod.purchase_factor) != outstanding

    # 2. Second receipt: uses BASE mode fallback for the remaining 4 pieces
    req2 = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-PARTIAL-2",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=prod.id,
                qty=outstanding,
                unit_cost=Decimal("30.00"),
                mode="BASE",
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
        purchase_order_id=po.id,
        expected_unit_conversion_on=True,
    )
    PurchaseService.receive_goods(req2)

    db_session.refresh(po)
    db_session.refresh(po_item)
    db_session.refresh(prod)
    assert po.status == "RECEIVED"
    assert po_item.qty_received == Decimal("10.000")
    assert po_item.qty_ordered - po_item.qty_received == Decimal("0.000")
    assert prod.stock_qty == Decimal("10.000")  # exactly equals ordered base quantity


def test_issue_937_exact_reorder_and_po_prefill_in_purchase_view(
    qapp, db_session, test_user, test_supplier, conv_product, units
):
    """PurchaseView prefill_grn_items and load_selected_purchase_order use exact conversion and fallback."""
    db_session.commit()
    from cbpos.core.models import PurchaseOrder, PurchaseOrderItem
    from cbpos.ui.views.purchase_view import PurchaseView

    # conv_product has purchase_factor = 10, Box
    view = PurchaseView()
    view.set_user(test_user)

    # 1. Exact quantity: 20 pieces -> converts to 2 boxes (mode=PURCHASE)
    view.prefill_grn_items([{"barcode": conv_product.barcode, "order_qty": Decimal("20.000")}])
    assert view.grn_model.rowCount() == 1
    assert view.grn_items[0]["mode"] == "PURCHASE"
    assert view.grn_model.item(0, 2).text() == "2.000"
    assert view.grn_model.item(0, 3).text() == "Box"
    assert "20.000 Piece" in view.grn_model.item(0, 4).text()

    # Product with non-exact division: factor 3 (Pack of 3)
    pack3 = Unit(name="Pack3B", abbreviation="pk3b", decimal_places=0)
    db_session.add(pack3)
    db_session.flush()
    p_third = Product(
        barcode="B_THIRD",
        name_en="Third Product",
        cost=Decimal("10.00"),
        price=Decimal("15.00"),
        stock_qty=Decimal("0.000"),
        unit_id=units["piece"].id,
        purchase_unit_id=pack3.id,
        purchase_factor=Decimal("3.000"),
        default_supplier_id=test_supplier.id,
    )
    db_session.add(p_third)
    db_session.commit()

    # 2. Inexact quantity: 10 pieces with factor 3 -> cannot be represented as whole/exact boxes -> falls back to mode=BASE
    view.prefill_grn_items([{"barcode": p_third.barcode, "order_qty": Decimal("10.000")}])
    assert view.grn_model.rowCount() == 1
    assert view.grn_items[0]["mode"] == "BASE"
    assert view.grn_model.item(0, 2).text() == "10.000"
    assert view.grn_model.item(0, 3).text() == "Piece"
    assert "10.000 Piece" in view.grn_model.item(0, 4).text()

    # 3. PO loading with exact outstanding quantity (15 pieces / 10 = 1.500 boxes)
    po = PurchaseOrder(
        document_number="PO-PREFILL-EXACT",
        supplier_id=test_supplier.id,
        user_id=test_user.id,
        status="ORDERED",
        date=datetime.now(),
    )
    db_session.add(po)
    db_session.flush()

    po_item = PurchaseOrderItem(
        purchase_order_id=po.id,
        product_id=conv_product.id,
        qty_ordered=Decimal("15.000"),
        qty_received=Decimal("0.000"),
    )
    db_session.add(po_item)
    db_session.commit()

    view.refresh_open_orders()
    idx = view.open_po_combo.findData(po.id)
    assert idx >= 0
    view.open_po_combo.setCurrentIndex(idx)
    view.load_selected_purchase_order()

    assert view.grn_model.rowCount() == 1
    assert view.grn_items[0]["mode"] == "PURCHASE"
    assert view.grn_model.item(0, 2).text() == "1.500"

    # 4. PO loading with non-exact outstanding quantity (10 pieces / 3)
    po3 = PurchaseOrder(
        document_number="PO-PREFILL-THIRD",
        supplier_id=test_supplier.id,
        user_id=test_user.id,
        status="ORDERED",
        date=datetime.now(),
    )
    db_session.add(po3)
    db_session.flush()
    po3_item = PurchaseOrderItem(
        purchase_order_id=po3.id,
        product_id=p_third.id,
        qty_ordered=Decimal("10.000"),
        qty_received=Decimal("0.000"),
    )
    db_session.add(po3_item)
    db_session.commit()

    view.refresh_open_orders()
    idx3 = view.open_po_combo.findData(po3.id)
    assert idx3 >= 0
    view.open_po_combo.setCurrentIndex(idx3)
    view.load_selected_purchase_order()

    assert view.grn_model.rowCount() == 1
    # 10 / 3 = 3.333 -> 3.333 * 3 = 9.999 != 10.000 -> mode must fall back to BASE!
    assert view.grn_items[0]["mode"] == "BASE"
    assert view.grn_model.item(0, 2).text() == "10.000"
    assert view.grn_model.item(0, 3).text() == "Piece"
    assert "10.000 Piece" in view.grn_model.item(0, 4).text()


def test_issue_937_configuration_snapshot_validation_base_and_purchase_modes(
    db_session, test_user, test_supplier, conv_product, units
):
    """Configuration snapshots must be validated for both BASE and PURCHASE modes in receive_goods and commit_purchase (#937)."""
    db_session.commit()

    other_piece = Unit(name="Gram", abbreviation="g", decimal_places=3)
    carton = Unit(name="Carton", abbreviation="ctn", decimal_places=0)
    db_session.add_all([other_piece, carton])
    db_session.commit()

    # 1. Base unit replacement in BASE mode
    conv_product.unit_id = other_piece.id
    db_session.commit()

    req_base_unit_changed = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-BASE-UNIT-STALE",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("5.000"),
                unit_cost=Decimal("10.00"),
                mode="BASE",
                expected_base_unit_id=units["piece"].id,  # Stale: was piece, now gram
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
    )
    with pytest.raises(ValueError, match=r"stale_conversion_configuration.*base unit changed"):
        PurchaseService.receive_goods(req_base_unit_changed)

    # 2. Base unit replacement in PURCHASE mode
    req_purchase_unit_changed = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-PURCH-UNIT-STALE",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("2.000"),
                unit_cost=Decimal("100.00"),
                mode="PURCHASE",
                expected_base_unit_id=units["piece"].id,  # Stale
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
    )
    with pytest.raises(ValueError, match=r"stale_conversion_configuration.*base unit changed"):
        PurchaseService.receive_goods(req_purchase_unit_changed)

    # Restore base unit
    conv_product.unit_id = units["piece"].id
    db_session.commit()

    # 3. Conversion removal in BASE mode (expected box, DB cleared to None)
    conv_product.purchase_unit_id = None
    db_session.commit()

    req_conv_removed_base = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-CONV-REM-BASE",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("5.000"),
                unit_cost=Decimal("10.00"),
                mode="BASE",
                expected_base_unit_id=units["piece"].id,
                purchase_unit_id=units["box"].id,  # Stale: product now has None
                purchase_factor=Decimal("10.000"),
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
    )
    with pytest.raises(ValueError, match=r"stale_conversion_configuration.*purchase unit changed"):
        PurchaseService.receive_goods(req_conv_removed_base)

    # 4. Conversion addition in BASE mode (expected None, DB added box)
    conv_product.purchase_unit_id = units["box"].id
    conv_product.purchase_factor = Decimal("10.000")
    db_session.commit()

    req_conv_added_base = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-CONV-ADD-BASE",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("5.000"),
                unit_cost=Decimal("10.00"),
                mode="BASE",
                expected_base_unit_id=units["piece"].id,
                purchase_unit_id=None,  # Stale: expected None, but product now has box
                purchase_factor=Decimal("1.000"),
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
    )
    with pytest.raises(ValueError, match=r"stale_conversion_configuration.*purchase unit changed"):
        PurchaseService.receive_goods(req_conv_added_base)

    # 5. Factor change in BASE mode (expected 10, DB changed to 12)
    conv_product.purchase_factor = Decimal("12.000")
    db_session.commit()

    req_factor_changed_base = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-FACTOR-CHG-BASE",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("5.000"),
                unit_cost=Decimal("10.00"),
                mode="BASE",
                expected_base_unit_id=units["piece"].id,
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),  # Stale: was 10, now 12
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
    )
    with pytest.raises(ValueError, match=r"stale_conversion_configuration.*factor changed"):
        PurchaseService.receive_goods(req_factor_changed_base)

    # 6. Purchase-unit change in BASE mode (expected box, DB changed to carton)
    conv_product.purchase_unit_id = carton.id
    conv_product.purchase_factor = Decimal("10.000")
    db_session.commit()

    req_punit_changed_base = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-PUNIT-CHG-BASE",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("5.000"),
                unit_cost=Decimal("10.00"),
                mode="BASE",
                expected_base_unit_id=units["piece"].id,
                purchase_unit_id=units["box"].id,  # Stale: was box, now carton
                purchase_factor=Decimal("10.000"),
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
    )
    with pytest.raises(ValueError, match=r"stale_conversion_configuration.*purchase unit changed"):
        PurchaseService.receive_goods(req_punit_changed_base)

    # 7. Same contract applied to commit_purchase
    p_commit = PurchaseService.create_purchase(test_supplier.id, "INV-COMMIT-STALE", test_user.id)
    items_stale = [
        {
            "product_id": conv_product.id,
            "qty": Decimal("5.000"),
            "cost": Decimal("10.00"),
            "mode": "BASE",
            "expected_base_unit_id": units["piece"].id,
            "purchase_unit_id": units["box"].id,  # Stale: product now has carton
            "purchase_factor": Decimal("10.000"),
            "expected_unit_conversion_on": True,
        }
    ]
    with pytest.raises(ValueError, match=r"stale_conversion_configuration.*purchase unit changed"):
        PurchaseService.commit_purchase(p_commit.id, items_stale)

    # 8. Unrelated stock change does NOT cause false stale failure
    conv_product.purchase_unit_id = units["box"].id
    conv_product.purchase_factor = Decimal("10.000")
    conv_product.stock_qty += Decimal("50.000")  # Stock moved, version updated
    db_session.commit()

    req_valid = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-VALID-AFTER-STOCK-MOVE",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("5.000"),
                unit_cost=Decimal("10.00"),
                mode="BASE",
                expected_base_unit_id=units["piece"].id,
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("10.000"),
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
    )
    res = PurchaseService.receive_goods(req_valid)
    assert res.status == "COMPLETED"


def test_issue_937_reject_quantities_that_persist_as_zero(db_session, test_user, test_supplier, conv_product, units):
    """Any quantity that persists as zero base units must be rejected before any mutations (#937)."""
    db_session.commit()

    # 1. Tiny positive quantity in BASE mode (0.0001 -> rounds to 0.000)
    req_tiny_base = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-TINY-BASE",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("0.0001"),
                unit_cost=Decimal("10.00"),
                mode="BASE",
            )
        ],
        user_id=test_user.id,
    )
    with pytest.raises(ValueError, match=r"grn_invalid_qty.*zero base quantity"):
        PurchaseService.receive_goods(req_tiny_base)

    assert db_session.query(Purchase).filter_by(reference_external="INV-TINY-BASE").count() == 0

    # 2. In PURCHASE mode, tiny input that converts to zero base units
    # e.g., purchase qty 0.001 with factor 0.010 = 0.00001 -> rounds to 0.000
    conv_product.purchase_factor = Decimal("0.010")
    db_session.commit()

    req_tiny_purch = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-TINY-PURCH",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=conv_product.id,
                qty=Decimal("0.001"),
                unit_cost=Decimal("10.00"),
                mode="PURCHASE",
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("0.010"),
            )
        ],
        user_id=test_user.id,
    )
    with pytest.raises(ValueError, match=r"grn_invalid_qty.*zero base quantity"):
        PurchaseService.receive_goods(req_tiny_purch)

    assert db_session.query(Purchase).filter_by(reference_external="INV-TINY-PURCH").count() == 0

    # 3. Same rule applied in commit_purchase
    p = PurchaseService.create_purchase(test_supplier.id, "INV-TINY-COMMIT", test_user.id)
    with pytest.raises(ValueError, match=r"grn_invalid_qty.*zero base quantity"):
        PurchaseService.commit_purchase(
            p.id,
            [{"product_id": conv_product.id, "qty": Decimal("0.0001"), "cost": Decimal("10.00"), "mode": "BASE"}],
        )

    # Verify no partial purchase rows, no stock movement, no payable update
    db_session.refresh(p)
    assert p.status == "DRAFT"
    assert len(p.items) == 0
    assert db_session.query(StockMovement).filter_by(document_id=p.id).count() == 0


def test_issue_937_authoritative_supplier_line_total_rounding_reconciliation(
    db_session, test_user, test_supplier, units
):
    """PurchaseItem.line_total reconciles displayed lines with Purchase.total_cost exactly (#937)."""
    db_session.commit()
    from cbpos.core.services.document_browser_service import DocumentBrowserService

    # Product A: 1 Box = 3 pieces, cost per box Rs 10.00
    # Base unit cost = 10.00 / 3 = 3.33. Base qty = 1 * 3 = 3. 3 * 3.33 = 9.99 != 10.00!
    p_third = Product(
        name_en="Third Item",
        barcode="THIRD001",
        price=Decimal("20.00"),
        cost=Decimal("3.33"),
        stock_qty=Decimal("0.000"),
        unit_id=units["piece"].id,
        purchase_unit_id=units["box"].id,
        purchase_factor=Decimal("3.000"),
    )
    db_session.add(p_third)
    db_session.commit()

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-ROUNDING-RECONCILE",
        input_vat=Decimal("0.00"),
        lines=[
            GrnLine(
                product_id=p_third.id,
                qty=Decimal("1.000"),
                unit_cost=Decimal("10.00"),
                mode="PURCHASE",
                purchase_unit_id=units["box"].id,
                purchase_factor=Decimal("3.000"),
                expected_unit_conversion_on=True,
            )
        ],
        user_id=test_user.id,
    )
    purchase = PurchaseService.receive_goods(req)

    # Authoritative total cost on Purchase is Rs 10.00
    assert purchase.total_cost == Decimal("10.00")

    item = purchase.items[0]
    # line_total must be Rs 10.00, NOT 3 * 3.33 = 9.99
    assert item.line_total == Decimal("10.00")
    assert sum(it.line_total for it in purchase.items) == purchase.total_cost

    # DocumentBrowserService must also report line_total == Rs 10.00
    doc = DocumentBrowserService.get_document_details(purchase.id, "purchase")
    assert doc is not None
    assert doc["items"][0]["line_total"] == Decimal("10.00")
    assert sum(it["line_total"] for it in doc["items"]) == doc["total_amount"]
