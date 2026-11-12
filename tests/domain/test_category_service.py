"""
Unit tests for CategoryService — CRUD operations and hierarchy.
"""

import json

import pytest

from cbpos.core.constants.audit import WARRANTY_EVENT
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import AuditLog, Category, Permission, Product, Role, User, WarrantyPolicy
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.category_service import CategoryService

# ── Shared Fixtures ──────────────────────────────────────────────────────

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_category(db_session):
    """Create a test category."""
    suffix = _next_suffix()
    cat = Category(name=f"TestCat_{suffix}", color="#FF0000")
    db_session.add(cat)
    db_session.flush()
    return cat


# ── Test: create ─────────────────────────────────────────────────────────


def test_create_category(db_session):
    """Creating a category sets name and color."""
    suffix = _next_suffix()
    cat = CategoryService.create(name=f"Groceries_{suffix}", color="#00FF00")

    assert cat is not None
    assert cat.name == f"Groceries_{suffix}"
    assert cat.color == "#00FF00"


def test_create_duplicate_name(db_session, test_category):
    """Creating a category with an existing name raises ValueError."""
    with pytest.raises(ValueError, match="already exists"):
        CategoryService.create(name=test_category.name)


# ── Test: update ─────────────────────────────────────────────────────────


def test_update_category(db_session, test_category):
    """Updating a category changes name and color."""
    suffix = _next_suffix()
    new_name = f"UpdatedCat_{suffix}"
    updated = CategoryService.update(test_category.id, name=new_name, color="#0000FF")

    assert updated.name == new_name
    assert updated.color == "#0000FF"


# ── Test: delete ─────────────────────────────────────────────────────────


def test_delete_category(db_session, test_category):
    """Deleting a category with no products succeeds."""
    cat_id = test_category.id
    CategoryService.delete(cat_id)

    # Verify it is gone
    result = db_session.get(Category, cat_id)
    assert result is None


def test_delete_category_with_products(db_session, test_category):
    """Deleting a category that has products raises ValueError."""
    suffix = _next_suffix()
    product = Product(
        name_en=f"Product_{suffix}",
        barcode=f"DEL{suffix:0>4}",
        price=100.0,
        stock_qty=5.0,
        category_id=test_category.id,
    )
    db_session.add(product)
    db_session.flush()

    with pytest.raises(ValueError, match="product"):
        CategoryService.delete(test_category.id)


# ── Test: get_descendant_ids ─────────────────────────────────────────────


def test_get_descendant_ids(db_session):
    """get_descendant_ids returns all descendant category IDs."""
    suffix = _next_suffix()

    # Create a tree: root -> child1, child2; child1 -> grandchild
    root = Category(name=f"Root_{suffix}", color="#FFFFFF")
    db_session.add(root)
    db_session.flush()

    child1 = Category(name=f"Child1_{suffix}", color="#AAAAAA", parent_id=root.id)
    child2 = Category(name=f"Child2_{suffix}", color="#BBBBBB", parent_id=root.id)
    db_session.add_all([child1, child2])
    db_session.flush()

    grandchild = Category(name=f"GrandChild_{suffix}", color="#CCCCCC", parent_id=child1.id)
    db_session.add(grandchild)
    db_session.flush()

    descendants = CategoryService.get_descendant_ids(root.id)

    assert child1.id in descendants
    assert child2.id in descendants
    assert grandchild.id in descendants
    assert root.id not in descendants
    assert len(descendants) == 3


# ── Test: Issue #797 Category tax exemptions and audit ───────────────────


def test_issue_797_category_flag_settable_and_audited(db_session):
    """Category tax exemption flags can be set, audited, and inherit down the tree."""
    from cbpos.core.constants.permissions import Permissions
    from cbpos.core.models import AuditLog, Permission, Role, User
    from cbpos.core.services.auth_service import AuthService

    # Setup roles and users
    role_admin = Role(name=f"AdminRole_{_next_suffix()}")
    db_session.add(role_admin)
    db_session.flush()
    for code in [Permissions.INVENTORY_EDIT, Permissions.ADMIN_SETTINGS]:
        perm = db_session.query(Permission).filter(Permission.code == code).first()
        if not perm:
            perm = Permission(code=code)
            db_session.add(perm)
            db_session.flush()
        role_admin.permissions.append(perm)

    admin_user = User(
        username=f"admin_{_next_suffix()}",
        pin_hash=AuthService.hash_pin("1234"),
        role_id=role_admin.id,
        is_active=True,
    )
    db_session.add(admin_user)

    role_cashier = Role(name=f"CashierRole_{_next_suffix()}")
    db_session.add(role_cashier)
    db_session.flush()
    perm_inv = db_session.query(Permission).filter(Permission.code == Permissions.INVENTORY_EDIT).first()
    role_cashier.permissions.append(perm_inv)

    cashier_user = User(
        username=f"cashier_{_next_suffix()}",
        pin_hash=AuthService.hash_pin("5678"),
        role_id=role_cashier.id,
        is_active=True,
    )
    db_session.add(cashier_user)
    db_session.commit()

    # Cashier cannot set exemption flags (missing admin.settings)
    with pytest.raises(PermissionError, match=r"admin\.settings required"):
        CategoryService.create(
            name=f"ExemptFail_{_next_suffix()}",
            tax_exempt=True,
            acting_user_id=cashier_user.id,
        )

    # Admin CAN set exemption flags
    cat_exempt = CategoryService.create(
        name=f"ExemptCat_{_next_suffix()}",
        tax_exempt=True,
        sscl_exempt=True,
        acting_user_id=admin_user.id,
    )
    assert cat_exempt.tax_exempt is True
    assert cat_exempt.sscl_exempt is True

    # Audit log was written
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "CATEGORY_TAX_FLAG_CHANGED")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.user_id == admin_user.id
    details = json.loads(audit.details)
    assert details["category_id"] == cat_exempt.id

    # Test inheritance: child inherits parent flags when child has None / default
    subcat = CategoryService.create(
        name=f"SubExempt_{_next_suffix()}",
        parent_id=cat_exempt.id,
        acting_user_id=admin_user.id,
    )
    flags = CategoryService.effective_flags(subcat.id)
    assert flags["vat_exempt"] is True
    assert flags["sscl_exempt"] is True


def test_issue_821_category_warranty_permission_and_audit(db_session):
    """Setting default_warranty_policy_id enforces warranty.edit, validates active policy, and audits."""
    policy = WarrantyPolicy(
        name="Cat Policy Active",
        warranty_type="SHOP",
        duration=1,
        duration_unit="YEARS",
        remedy="REPAIR_OR_REPLACE",
        is_active=True,
    )
    inactive_policy = WarrantyPolicy(
        name="Cat Policy Inactive",
        warranty_type="SHOP",
        duration=6,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        is_active=False,
    )
    db_session.add_all([policy, inactive_policy])
    db_session.flush()

    role_no_warranty = Role(name=f"NoWarrantyRole_{_next_suffix()}")
    db_session.add(role_no_warranty)
    db_session.flush()
    perm_inv = db_session.query(Permission).filter(Permission.code == Permissions.INVENTORY_EDIT).first()
    if not perm_inv:
        perm_inv = Permission(code=Permissions.INVENTORY_EDIT, description="Inventory Edit", group="Inventory")
        db_session.add(perm_inv)
        db_session.flush()
    role_no_warranty.permissions.append(perm_inv)

    user_no_warranty = User(
        username=f"nowarr_{_next_suffix()}",
        pin_hash=AuthService.hash_pin("1111"),
        role_id=role_no_warranty.id,
        is_active=True,
    )
    db_session.add(user_no_warranty)

    role_warranty = Role(name=f"WarrantyRole_{_next_suffix()}")
    db_session.add(role_warranty)
    db_session.flush()
    perm_warr = db_session.query(Permission).filter(Permission.code == Permissions.WARRANTY_EDIT).first()
    if not perm_warr:
        perm_warr = Permission(code=Permissions.WARRANTY_EDIT, description="Warranty Edit", group="Warranty")
        db_session.add(perm_warr)
        db_session.flush()
    if perm_inv:
        role_warranty.permissions.append(perm_inv)
    role_warranty.permissions.append(perm_warr)

    user_warranty = User(
        username=f"warr_{_next_suffix()}",
        pin_hash=AuthService.hash_pin("2222"),
        role_id=role_warranty.id,
        is_active=True,
    )
    db_session.add(user_warranty)
    db_session.commit()

    # 1. Unauthenticated or user without warranty.edit cannot set default_warranty_policy_id on create
    with pytest.raises(PermissionError, match=r"warranty\.edit required"):
        CategoryService.create(
            name=f"CatWarrFail_{_next_suffix()}",
            default_warranty_policy_id=policy.id,
            acting_user_id=user_no_warranty.id,
        )

    # 2. Cannot assign inactive policy on create
    with pytest.raises(ValueError, match="Cannot assign inactive warranty policy"):
        CategoryService.create(
            name=f"CatInactFail_{_next_suffix()}",
            default_warranty_policy_id=inactive_policy.id,
            acting_user_id=user_warranty.id,
        )

    # 3. User with warranty.edit succeeds on create and writes AuditLog
    cat = CategoryService.create(
        name=f"CatWarrSuccess_{_next_suffix()}",
        default_warranty_policy_id=policy.id,
        acting_user_id=user_warranty.id,
    )
    assert cat.default_warranty_policy_id == policy.id

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == WARRANTY_EVENT, AuditLog.action == "CATEGORY_DEFAULT_WARRANTY")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.user_id == user_warranty.id
    details = json.loads(audit.details)
    assert details["category_id"] == cat.id
    assert details["policy_id"] == policy.id

    # 4. Update default_warranty_policy_id requires warranty.edit
    with pytest.raises(PermissionError, match=r"warranty\.edit required"):
        CategoryService.update(
            cat.id,
            default_warranty_policy_id=None,
            acting_user_id=user_no_warranty.id,
        )

    # 5. Update without changing warranty (default_warranty_policy_id=...) succeeds for inventory editor
    cat_updated = CategoryService.update(
        cat.id,
        name=f"RenamedCat_{_next_suffix()}",
        acting_user_id=user_no_warranty.id,
    )
    assert cat_updated.default_warranty_policy_id == policy.id
