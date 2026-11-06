"""Phase 4 Exit Gate: Stock Invariants Integration Test.

Validates:
- Invariant 1: For every product, product.stock_qty == sum(StockMovement.qty_change).
- Invariant 2: When a GRN arrives against negative or zero stock,
  new product.cost == unit_cost (no distorted weighted average).

Covers the full inventory lifecycle:
- CSV import with opening stock (recording OPENING movements)
- Stock sales via StockService
- Customer refunds via StockService
- Inventory adjustment via InventoryService
- Stock take during trading with physical count application via StockCountService
- GRN receipt onto negative stock via PurchaseService.receive_goods
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from cbpos.core.models import (
    Permission,
    Product,
    Role,
    StockMovement,
    Supplier,
    User,
)
from cbpos.core.services.import_service import ImportService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.services.purchase_service import GrnLine, GrnRequest, PurchaseService
from cbpos.core.services.stock_count_service import StockCountService
from cbpos.core.services.stock_service import StockService

_counter = 0


def _uid() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def inv_admin(db_session):
    uid = _uid()
    perm_codes = [
        "inventory.stock_adjust",
        "inventory.manage",
        "purchase.create_grn",
        "stock_count.manage",
    ]
    perms = []
    for code in perm_codes:
        p = db_session.query(Permission).filter_by(code=code).first()
        if not p:
            p = Permission(code=code, description=code, group="Inventory")
            db_session.add(p)
        perms.append(p)

    role = Role(name=f"StockAdmin_{uid}", access_level=9, permissions=perms)
    user = User(username=f"admin_{uid}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.commit()
    return user


def test_stock_invariants_lifecycle(db_session, inv_admin, tmp_path: Path):
    """Run full inventory operations and assert Invariant 1 and Invariant 2."""
    uid = _uid()

    # 1. CSV import with opening stock
    csv_file = tmp_path / f"import_{uid}.csv"
    csv_file.write_text(
        f"Barcode,Name,Selling Price,Cost Price,Stock\nINV{uid}01,Import Item A,150.00,100.00,20\nINV{uid}02,Import Item B,250.00,180.00,15\n",
        encoding="utf-8",
    )
    import_service = ImportService()
    res = import_service.import_products_from_csv(str(csv_file))
    assert res["success"] == 2

    p_a = db_session.query(Product).filter_by(barcode=f"INV{uid}01").one()
    p_b = db_session.query(Product).filter_by(barcode=f"INV{uid}02").one()

    # 2. Sales: Sell 5 of A, 3 of B
    StockService.record_movement(
        product_id=p_a.id,
        qty_change=Decimal("-5.000"),
        movement_type="SALE",
        user_id=inv_admin.id,
        session=db_session,
    )
    StockService.record_movement(
        product_id=p_b.id,
        qty_change=Decimal("-3.000"),
        movement_type="SALE",
        user_id=inv_admin.id,
        session=db_session,
    )
    db_session.commit()

    # 3. Refund: Return 2 of A
    StockService.record_movement(
        product_id=p_a.id,
        qty_change=Decimal("2.000"),
        movement_type="RETURN",
        user_id=inv_admin.id,
        session=db_session,
    )
    db_session.commit()

    # 4. Inventory adjustment: Adjust B by -2 (Damaged)
    inv_service = InventoryService()
    inv_service.adjust_stock(
        product_id=p_b.id,
        qty_change=Decimal("-2.000"),
        reason="DAMAGED",
        user_id=inv_admin.id,
        note="Water damage in warehouse",
    )
    db_session.commit()

    # 5. Stock take during trading on A:
    # Physical count counts 19 items (expected is 17: 20 opening - 5 sold + 2 returned)
    count = StockCountService.create_stock_count(user_id=inv_admin.id, note="Midday count")
    item_a = StockCountService.add_single_item(count.id, p_a.id)
    StockCountService.update_count(item_a.id, Decimal("19.000"))
    StockCountService.finalize_count(count.id)
    StockCountService.approve_and_apply(count.id, user_id=inv_admin.id)
    db_session.commit()

    # 6. GRN onto negative stock:
    # Create product C with 0 stock, sell 4 without non-negative enforcement to put stock at -4
    p_c = Product(
        name_en=f"Negative Item C_{uid}",
        barcode=f"INV{uid}03",
        price=200.0,
        cost=Decimal("80.00"),
        stock_qty=Decimal("0.000"),
    )
    supplier = Supplier(company_name=f"Invariant Supplier_{uid}", current_payable=Decimal("0.00"))
    db_session.add_all([p_c, supplier])
    db_session.commit()

    StockService.record_movement(
        product_id=p_c.id,
        qty_change=Decimal("-4.000"),
        movement_type="SALE",
        user_id=inv_admin.id,
        enforce_non_negative=False,
        session=db_session,
    )
    db_session.commit()

    # Receive GRN for 10 units of C @ 120.00
    grn_req = GrnRequest(
        supplier_id=supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no=f"INV-GRN-{uid}",
        input_vat=Decimal("0.00"),
        lines=[GrnLine(product_id=p_c.id, qty=Decimal("10.000"), unit_cost=Decimal("120.00"))],
        user_id=inv_admin.id,
    )
    PurchaseService.receive_goods(grn_req)
    db_session.commit()

    # ── VALIDATE INVARIANTS ──

    # Invariant 2 (GRN onto negative stock):
    # Because old_qty was <= 0 (-4), new cost MUST be exactly unit_cost (120.00), not distorted AVCO
    db_session.refresh(p_c)
    assert p_c.cost == Decimal("120.00"), f"Expected Invariant 2 cost 120.00, got {p_c.cost}"
    assert p_c.stock_qty == Decimal("6.000")

    # Invariant 1 (stock_qty == sum(StockMovement.qty_change)):
    # Verify for every single product involved
    for product in [p_a, p_b, p_c]:
        db_session.refresh(product)
        movements = db_session.query(StockMovement).filter(StockMovement.product_id == product.id).all()
        movement_sum = sum(m.qty_change for m in movements)
        assert product.stock_qty == movement_sum, (
            f"Invariant 1 violated for product {product.name_en} ({product.barcode}): "
            f"stock_qty={product.stock_qty} != sum(movements)={movement_sum}"
        )
