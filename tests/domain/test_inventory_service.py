"""
InventoryService.adjust_stock() built an AuditLog row without event_type,
a non-nullable column -- session.commit() raised IntegrityError, which the
surrounding try/except only catches for StaleDataError, so it propagated
out uncaught. A stock adjustment could fail outright rather than merely
fail to log.
"""

import json
from decimal import Decimal

import pytest

from cbpos.core.constants.audit import WARRANTY_EVENT
from cbpos.core.constants.permissions import ADMIN_ROLE_NAME, Permissions
from cbpos.core.constants.status import MovementType
from cbpos.core.models import (
    AuditLog,
    Category,
    InventoryLog,
    Permission,
    Product,
    Role,
    StockMovement,
    User,
    WarrantyPolicy,
)
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.inventory_service import InventoryService

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_product(db_session):
    suffix = _next_suffix()
    product = Product(
        barcode=f"BC{suffix}",
        name_en=f"Test Product {suffix}",
        price=Decimal("100.00"),
        stock_qty=Decimal("10"),
    )
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def test_user(db_session):
    suffix = _next_suffix()
    admin_role = db_session.query(Role).filter_by(name=ADMIN_ROLE_NAME).first()
    if not admin_role:
        admin_role = Role(name=ADMIN_ROLE_NAME, access_level=9)
        db_session.add(admin_role)
        db_session.flush()
    user = User(username=f"user_{suffix}", pin_hash="hash", role_id=admin_role.id)
    db_session.add(user)
    db_session.flush()
    return user


class TestAdjustStock:
    def test_commits_successfully_and_records_both_logs(self, db_session, test_product, test_user):
        service = InventoryService()

        result = service.adjust_stock(
            product_id=test_product.id,
            qty_change=Decimal("5"),
            reason="Stock take correction",
            user_id=test_user.id,
        )

        assert bool(result) is True

        db_session.expire_all()
        refreshed = db_session.get(Product, test_product.id)
        assert refreshed.stock_qty == Decimal("15")

        inv_log = db_session.query(InventoryLog).filter_by(product_id=test_product.id).one()
        assert inv_log.qty_change == Decimal("5")

        audit_log = db_session.query(AuditLog).filter_by(action="STOCK_ADJUSTMENT").one()
        assert audit_log.event_type == "INVENTORY"
        assert audit_log.user_id == test_user.id

    def test_issue_794_adjust_stock_writes_movement_and_audit(self, db_session, test_product, test_user):
        """#794: adjust_stock writes a StockMovement(type=ADJUSTMENT) and updates stock atomically."""
        service = InventoryService()

        movement = service.adjust_stock(
            product_id=test_product.id,
            qty_change=Decimal("-2"),
            reason="DAMAGED",
            user_id=test_user.id,
            note="Broken bottle on shelf",
        )

        assert isinstance(movement, StockMovement)
        assert movement.type == MovementType.ADJUSTMENT
        assert movement.qty_change == Decimal("-2")
        assert movement.balance_after == Decimal("8")
        assert movement.product_id == test_product.id
        assert movement.user_id == test_user.id

        db_session.expire_all()
        refreshed = db_session.get(Product, test_product.id)
        assert refreshed.stock_qty == Decimal("8")

        # InventoryLog and AuditLog recorded
        inv_log = db_session.query(InventoryLog).filter_by(product_id=test_product.id).one()
        assert inv_log.qty_change == Decimal("-2")
        assert "DAMAGED" in inv_log.reason

        audit_log = db_session.query(AuditLog).filter_by(action="STOCK_ADJUSTMENT").one()
        assert audit_log.event_type == "INVENTORY"
        assert audit_log.user_id == test_user.id
        assert "DAMAGED" in audit_log.details
        assert "Broken bottle" in audit_log.details

    def test_issue_794_adjust_requires_permission(self, db_session, test_product):
        """#794: adjust_stock requires inventory.stock_adjust permission."""
        service = InventoryService()
        suffix = _next_suffix()
        cashier_role = Role(name=f"Cashier_{suffix}", access_level=1)
        db_session.add(cashier_role)
        db_session.flush()

        cashier = User(username=f"cashier_{suffix}", pin_hash="hash", role_id=cashier_role.id)
        db_session.add(cashier)
        db_session.flush()

        with pytest.raises(PermissionError, match=r"inventory\.stock_adjust"):
            service.adjust_stock(
                product_id=test_product.id,
                qty_change=Decimal("1"),
                reason="FOUND",
                user_id=cashier.id,
            )

    def test_issue_794_adjust_rejects_zero_and_service(self, db_session, test_user):
        """#794: adjust_stock rejects zero quantity change and service products."""
        service = InventoryService()
        suffix = _next_suffix()
        service_prod = Product(
            barcode=f"SRV{suffix}",
            name_en=f"Labor Service {suffix}",
            price=Decimal("500.00"),
            stock_qty=Decimal("0"),
            is_service=True,
        )
        norm_prod = Product(
            barcode=f"NRM{suffix}",
            name_en=f"Normal Item {suffix}",
            price=Decimal("100.00"),
            stock_qty=Decimal("10"),
        )
        db_session.add_all([service_prod, norm_prod])
        db_session.flush()

        # Reject qty_change == 0
        with pytest.raises(ValueError, match="zero"):
            service.adjust_stock(
                product_id=norm_prod.id,
                qty_change=Decimal("0"),
                reason="CORRECTION",
                user_id=test_user.id,
            )

        # Reject service product
        with pytest.raises(ValueError, match="service"):
            service.adjust_stock(
                product_id=service_prod.id,
                qty_change=Decimal("1"),
                reason="FOUND",
                user_id=test_user.id,
            )

        # Reject OTHER reason without note
        with pytest.raises(ValueError, match="note"):
            service.adjust_stock(
                product_id=norm_prod.id,
                qty_change=Decimal("1"),
                reason="OTHER",
                user_id=test_user.id,
                note="",
            )


class TestProductEditorConcurrencyAndCost:
    def test_issue_862_stale_snapshot_does_not_overwrite_stock_cost(self, db_session):
        """#862: update_product with stale version raises StaleProductError without overwriting stock/cost."""
        from cbpos.core.services.inventory_service import StaleProductError

        service = InventoryService()
        suffix = _next_suffix()
        product = Product(
            barcode=f"STALE_{suffix}",
            name_en="Original Name",
            price=Decimal("100.00"),
            cost=Decimal("40.00"),
            stock_qty=Decimal("50"),
        )
        db_session.add(product)
        db_session.commit()

        initial_version = product.version_id

        # In another session, simulate sales/GRN updating stock, cost and version_id
        with service.db.get_session() as s2:
            p2 = s2.get(Product, product.id)
            p2.stock_qty = Decimal("40")
            p2.cost = Decimal("70")
            p2.price = Decimal("120.00")
            s2.commit()

        # Stale update with initial_version must raise StaleProductError
        with pytest.raises(StaleProductError):
            service.update_product(
                product_id=product.id,
                data={"name_en": "Stale Attempted Name", "stock_qty": Decimal("999"), "cost": Decimal("999")},
                expected_version=initial_version,
            )

        # Verify stock, cost, and name were not overwritten
        db_session.expire_all()
        refreshed = db_session.get(Product, product.id)
        assert refreshed.name_en == "Original Name"
        assert refreshed.stock_qty == Decimal("40")
        assert refreshed.cost == Decimal("70")

    def test_issue_862_update_ignores_stock_and_cost_keys(self, db_session):
        """#862: update_product ignores stock_qty and cost keys even when version matches."""
        service = InventoryService()
        suffix = _next_suffix()
        product = Product(
            barcode=f"IGN_{suffix}",
            name_en="Untouched Item",
            price=Decimal("50.00"),
            cost=Decimal("30.00"),
            stock_qty=Decimal("25"),
        )
        db_session.add(product)
        db_session.commit()

        current_version = product.version_id

        service.update_product(
            product_id=product.id,
            data={
                "name_en": "Updated Name",
                "stock_qty": Decimal("999"),
                "cost": Decimal("888"),
            },
            expected_version=current_version,
        )

        db_session.expire_all()
        refreshed = db_session.get(Product, product.id)
        assert refreshed.name_en == "Updated Name"
        assert refreshed.stock_qty == Decimal("25")
        assert refreshed.cost == Decimal("30.00")

    def test_issue_862_new_product_opening_stock_writes_movement(self, db_session, test_user):
        """#862: create_product with opening stock records StockMovement(type=OPENING)."""
        service = InventoryService()
        suffix = _next_suffix()

        prod = service.create_product(
            {
                "barcode": f"NEW_OP_{suffix}",
                "name_en": f"New Product {suffix}",
                "price": Decimal("200.00"),
                "cost": Decimal("120.00"),
                "stock_qty": Decimal("15"),
            },
            user_id=test_user.id,
        )

        assert prod.stock_qty == Decimal("15")

        movement = (
            db_session.query(StockMovement).filter_by(product_id=prod.id, type=MovementType.OPENING).one_or_none()
        )
        assert movement is not None
        assert movement.qty_change == Decimal("15")
        assert movement.balance_after == Decimal("15")
        assert movement.user_id == test_user.id

    def test_issue_862_set_cost_requires_permission_and_audits(self, db_session, test_user):
        """#862: set_cost updates cost, checks inventory.set_cost permission, and writes AuditLog."""
        service = InventoryService()
        suffix = _next_suffix()

        product = Product(
            barcode=f"COST_{suffix}",
            name_en="Cost Override Item",
            price=Decimal("100.00"),
            cost=Decimal("40.00"),
            stock_qty=Decimal("10"),
        )
        db_session.add(product)
        db_session.commit()

        # Admin user has permission and successfully updates cost
        updated = service.set_cost(product.id, Decimal("55.00"), user_id=test_user.id)
        assert updated.cost == Decimal("55.00")

        audit_log = db_session.query(AuditLog).filter_by(action="COST_OVERRIDE").order_by(AuditLog.id.desc()).first()
        assert audit_log is not None
        assert audit_log.user_id == test_user.id
        assert "40" in audit_log.details
        assert "55" in audit_log.details

        # Cashier user without permission is rejected
        cashier_role = Role(name=f"Cashier_{suffix}", access_level=1)
        db_session.add(cashier_role)
        db_session.flush()
        cashier = User(username=f"cashier_{suffix}", pin_hash="hash", role_id=cashier_role.id)
        db_session.add(cashier)
        db_session.flush()

        with pytest.raises(PermissionError, match=r"inventory\.set_cost"):
            service.set_cost(product.id, Decimal("60.00"), user_id=cashier.id)


class TestInventoryServiceListProductsIssue863:
    def test_issue_863_product_1400_reachable_by_page_and_search(self, db_session):
        """#863: 1,500 products seeded via bulk insert; product #1,400 reachable by page and search."""
        service = InventoryService()
        suffix = _next_suffix()

        # Bulk insert 1,500 products
        products_data = [
            {
                "barcode": f"BLK-{suffix}-{i:04d}",
                "name_en": f"Bulk Item {suffix} {i:04d}",
                "price": Decimal("100.00"),
                "cost": Decimal("50.00"),
                "stock_qty": Decimal("10.000"),
                "is_active": True,
                "is_service": False,
            }
            for i in range(1, 1501)
        ]
        db_session.bulk_insert_mappings(Product, products_data)
        db_session.commit()

        # Check total count and page 13 (indices 1300..1399 contains product #1400)
        items, total_count = service.list_products(page=13, page_size=100)
        assert total_count >= 1500
        assert len(items) == 100
        barcodes = [p.barcode for p in items]
        assert f"BLK-{suffix}-1400" in barcodes

        # Search directly for product #1400
        search_items, search_count = service.list_products(query=f"BLK-{suffix}-1400")
        assert search_count == 1
        assert len(search_items) == 1
        assert search_items[0].barcode == f"BLK-{suffix}-1400"

    def test_issue_863_search_matches_sinhala_name(self, db_session):
        """#863: list_products matches Sinhala and Tamil names in addition to English and barcode."""
        service = InventoryService()
        suffix = _next_suffix()

        product = Product(
            barcode=f"TRI-{suffix}",
            name_en=f"Red Rice {suffix}",
            name_si="රතු කැකුළු සහල්",
            name_ta="சிவப்பு அரிசி",
            price=Decimal("220.00"),
            cost=Decimal("180.00"),
            stock_qty=Decimal("50.000"),
            is_active=True,
        )
        db_session.add(product)
        db_session.commit()

        # Match Sinhala
        items_si, count_si = service.list_products(query="කැකුළු")
        assert count_si >= 1
        assert any(p.barcode == f"TRI-{suffix}" for p in items_si)

        # Match Tamil
        items_ta, count_ta = service.list_products(query="சிவப்பு")
        assert count_ta >= 1
        assert any(p.barcode == f"TRI-{suffix}" for p in items_ta)

    def test_issue_863_count_matches_filter(self, db_session):
        """#863: list_products total_count accurately reflects active, category, and low stock filters."""

        service = InventoryService()
        suffix = _next_suffix()

        cat = Category(name=f"Cat863_{suffix}")
        db_session.add(cat)
        db_session.flush()

        p_low = Product(
            barcode=f"LOW-{suffix}",
            name_en=f"Low Stock {suffix}",
            price=Decimal("50.00"),
            cost=Decimal("20.00"),
            stock_qty=Decimal("2.000"),
            reorder_point=Decimal("5.000"),
            category_id=cat.id,
            is_active=True,
        )
        p_norm = Product(
            barcode=f"NORM-{suffix}",
            name_en=f"Normal Stock {suffix}",
            price=Decimal("50.00"),
            cost=Decimal("20.00"),
            stock_qty=Decimal("20.000"),
            reorder_point=Decimal("5.000"),
            category_id=cat.id,
            is_active=True,
        )
        p_inactive = Product(
            barcode=f"INACT-{suffix}",
            name_en=f"Inactive Item {suffix}",
            price=Decimal("50.00"),
            cost=Decimal("20.00"),
            stock_qty=Decimal("0.000"),
            category_id=cat.id,
            is_active=False,
        )
        db_session.add_all([p_low, p_norm, p_inactive])
        db_session.commit()

        # Category filter for active products
        items_cat, count_cat = service.list_products(filters={"category_id": cat.id, "is_active": True})
        assert count_cat == 2
        assert len(items_cat) == 2

        # Low stock filter within this category
        items_low, count_low = service.list_products(
            filters={"category_id": cat.id, "is_active": True, "low_stock": True}
        )
        assert count_low == 1
        assert items_low[0].barcode == f"LOW-{suffix}"


def test_issue_821_inventory_service_warranty_permission_and_audit(db_session):
    """Product create and update with warranty settings enforces warranty.edit and writes WARRANTY audit."""
    service = InventoryService()
    policy = WarrantyPolicy(
        name="Prod Policy Active",
        warranty_type="SHOP",
        duration=1,
        duration_unit="YEARS",
        remedy="REPAIR_OR_REPLACE",
        is_active=True,
    )
    inactive_policy = WarrantyPolicy(
        name="Prod Policy Inactive",
        warranty_type="SHOP",
        duration=6,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        is_active=False,
    )
    db_session.add_all([policy, inactive_policy])
    db_session.flush()

    role_no_warr = Role(name=f"InvOnlyRole_{_next_suffix()}")
    db_session.add(role_no_warr)
    db_session.flush()
    perm_inv = db_session.query(Permission).filter(Permission.code == Permissions.INVENTORY_EDIT).first()
    if not perm_inv:
        perm_inv = Permission(code=Permissions.INVENTORY_EDIT, description="Inventory Edit", group="Inventory")
        db_session.add(perm_inv)
        db_session.flush()
    role_no_warr.permissions.append(perm_inv)

    user_no_warr = User(
        username=f"nowarr_{_next_suffix()}",
        pin_hash=AuthService.hash_pin("3333"),
        role_id=role_no_warr.id,
        is_active=True,
    )
    db_session.add(user_no_warr)

    role_warr = Role(name=f"WarrRole_{_next_suffix()}")
    db_session.add(role_warr)
    db_session.flush()
    perm_warr = db_session.query(Permission).filter(Permission.code == Permissions.WARRANTY_EDIT).first()
    if not perm_warr:
        perm_warr = Permission(code=Permissions.WARRANTY_EDIT, description="Warranty Edit", group="Warranty")
        db_session.add(perm_warr)
        db_session.flush()
    role_warr.permissions.extend([perm_inv, perm_warr])

    user_warr = User(
        username=f"warr_{_next_suffix()}",
        pin_hash=AuthService.hash_pin("4444"),
        role_id=role_warr.id,
        is_active=True,
    )
    db_session.add(user_warr)
    db_session.commit()

    # 1. User without warranty.edit cannot set specific warranty policy on create
    with pytest.raises(PermissionError, match=r"warranty\.edit required"):
        service.create_product(
            {
                "barcode": f"WARR-FAIL-{_next_suffix()}",
                "name_en": "Warranty Create Fail",
                "price": Decimal("150.00"),
                "warranty_override": "POLICY",
                "warranty_policy_id": policy.id,
            },
            user_id=user_no_warr.id,
        )

    # 2. Cannot assign inactive policy on create
    with pytest.raises(ValueError, match="Cannot assign inactive warranty policy"):
        service.create_product(
            {
                "barcode": f"WARR-INACT-{_next_suffix()}",
                "name_en": "Warranty Inactive Fail",
                "price": Decimal("150.00"),
                "warranty_override": "POLICY",
                "warranty_policy_id": inactive_policy.id,
            },
            user_id=user_warr.id,
        )

    # 3. Weighted product cannot have warranty policy
    with pytest.raises(ValueError, match="Weighted products cannot have warranty policies"):
        service.create_product(
            {
                "barcode": f"WARR-WEIGHT-{_next_suffix()}",
                "name_en": "Warranty Weighted Fail",
                "price": Decimal("150.00"),
                "is_weighted": True,
                "warranty_override": "POLICY",
                "warranty_policy_id": policy.id,
            },
            user_id=user_warr.id,
        )

    # 4. User with warranty.edit succeeds on create and writes AuditLog
    prod = service.create_product(
        {
            "barcode": f"WARR-OK-{_next_suffix()}",
            "name_en": "Warranty Success",
            "price": Decimal("250.00"),
            "warranty_override": "POLICY",
            "warranty_policy_id": policy.id,
        },
        user_id=user_warr.id,
    )
    assert prod.warranty_override == "POLICY"
    assert prod.warranty_policy_id == policy.id

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == WARRANTY_EVENT, AuditLog.action == "PRODUCT_WARRANTY_ASSIGNMENT")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.user_id == user_warr.id
    details = json.loads(audit.details)
    assert details["product_id"] == prod.id
    assert details["override"] == "POLICY"
    assert details["policy_id"] == policy.id

    # 5. User without warranty.edit cannot change warranty settings on update
    with pytest.raises(PermissionError, match=r"warranty\.edit required"):
        service.update_product(
            prod.id,
            {"warranty_override": "NONE", "warranty_policy_id": None},
            user_id=user_no_warr.id,
        )

    # 6. User without warranty.edit CAN update price or name without changing warranty
    updated = service.update_product(
        prod.id,
        {"price": Decimal("300.00")},
        user_id=user_no_warr.id,
    )
    assert updated.price == Decimal("300.00")
    assert updated.warranty_policy_id == policy.id


def test_issue_821_inventory_service_preserves_inactive_warranty(db_session):
    """Updating a product that already has an inactive warranty preserves the assignment."""
    service = InventoryService()
    inactive_policy = WarrantyPolicy(
        name="Existing Inactive Policy",
        warranty_type="SHOP",
        duration=6,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        is_active=False,
    )
    db_session.add(inactive_policy)
    db_session.flush()

    prod = Product(
        barcode=f"EXIST-INACT-{_next_suffix()}",
        name_en="Existing Product With Inactive Policy",
        price=Decimal("500.00"),
        stock_qty=Decimal("10"),
        warranty_override="POLICY",
        warranty_policy_id=inactive_policy.id,
    )
    db_session.add(prod)
    db_session.commit()

    # Updating name should succeed and preserve the inactive policy
    updated = service.update_product(prod.id, {"name_en": "Updated Name Keeping Inactive"})
    assert updated.name_en == "Updated Name Keeping Inactive"
    assert updated.warranty_policy_id == inactive_policy.id
