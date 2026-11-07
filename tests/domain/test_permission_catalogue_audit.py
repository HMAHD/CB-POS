"""Tests for Issue #894: Permission catalogue audit, enforcement, and cleanup."""

from pathlib import Path

import pytest
from sqlalchemy import select

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Permission, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.category_service import CategoryService
from cbpos.core.services.import_service import ImportService
from cbpos.core.services.unit_service import UnitService


def _create_user_with_permissions(db_session, username: str, perms: list[str]) -> User:
    role = Role(name=f"Role_{username}")
    db_session.add(role)
    db_session.flush()

    for code in perms:
        perm = db_session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if not perm:
            perm = Permission(code=code)
            db_session.add(perm)
            db_session.flush()
        role.permissions.append(perm)

    user = User(username=username, pin_hash=AuthService.hash_pin("1234"), role_id=role.id, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def test_issue_894_csv_import_requires_inventory_edit(db_session, tmp_path: Path):
    """ImportService._import_csv requires inventory.edit permission for the acting user."""
    cashier = _create_user_with_permissions(db_session, "cashier_894", [Permissions.MANAGEMENT_VIEW])
    manager = _create_user_with_permissions(
        db_session, "manager_894", [Permissions.MANAGEMENT_VIEW, Permissions.INVENTORY_EDIT]
    )

    csv_file = tmp_path / "test_import.csv"
    csv_file.write_text(
        "Barcode,Name,Selling Price,Cost Price,Stock\n8909999,Test Item,100.00,80.00,5\n", encoding="utf-8"
    )

    service = ImportService()

    # Cashier lacking inventory.edit must be rejected
    with pytest.raises(PermissionError, match=r"inventory\.edit"):
        service.import_products_from_csv(str(csv_file), acting_user_id=cashier.id)

    # Manager with inventory.edit must succeed
    result = service.import_products_from_csv(str(csv_file), acting_user_id=manager.id)
    assert result["success"] == 1


def test_issue_894_category_create_requires_inventory_edit(db_session):
    """CategoryService.create and UnitService.create require inventory.edit permission."""
    cashier = _create_user_with_permissions(db_session, "cashier_cat_894", [Permissions.MANAGEMENT_VIEW])
    manager = _create_user_with_permissions(
        db_session, "manager_cat_894", [Permissions.MANAGEMENT_VIEW, Permissions.INVENTORY_EDIT]
    )

    # Cashier cannot create category
    with pytest.raises(PermissionError, match=r"inventory\.edit"):
        CategoryService.create(name="Restricted Category", acting_user_id=cashier.id)

    # Cashier cannot create unit
    with pytest.raises(PermissionError, match=r"inventory\.edit"):
        UnitService.create(name="Restricted Unit", abbreviation="ru", acting_user_id=cashier.id)

    # Manager can create category and unit
    cat = CategoryService.create(name="Allowed Category", acting_user_id=manager.id)
    assert cat is not None
    assert cat.name == "Allowed Category"

    unit = UnitService.create(name="Allowed Unit", abbreviation="au", acting_user_id=manager.id)
    assert unit is not None
    assert unit.name == "Allowed Unit"


def test_issue_894_inventory_delete_code_removed_by_migration(db_session):
    """inventory.delete must not exist in Permissions constant, and migration cleans up the DB table."""
    import importlib.util
    from unittest.mock import patch

    from alembic import op
    from cbpos.config import Config

    assert not hasattr(Permissions, "INVENTORY_DELETE"), "INVENTORY_DELETE constant must be removed from Permissions"

    # Setup permissions and roles for migration test
    p_delete = Permission(code="inventory.delete", description="Delete products", group="Inventory")
    p_mgmt = Permission(code="management.view", description="Management View", group="Screens")
    p_inv_view = Permission(code="inventory.view", description="Inventory View", group="Inventory")
    p_purch_view = Permission(code="purchase.view", description="Purchase View", group="Purchase")
    role_mgmt = Role(name="MgmtRole894", permissions=[p_delete, p_mgmt])
    admin_role = Role(name="Admin", permissions=[p_delete])
    db_session.add_all([p_delete, p_mgmt, p_inv_view, p_purch_view, role_mgmt, admin_role])
    db_session.commit()

    migration_path = Config.BASE_DIR / "alembic" / "versions" / "8e9f0a1b2c3d_permission_catalogue_audit.py"
    spec = importlib.util.spec_from_file_location("migration_894", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with patch.object(op, "get_bind", return_value=db_session.connection()):
        migration.upgrade()

    db_session.expire_all()
    assert db_session.query(Permission).filter_by(code="inventory.delete").first() is None
    role_perms = {p.code for p in db_session.get(Role, role_mgmt.id).permissions}
    assert "inventory.delete" not in role_perms
    assert "inventory.view" in role_perms
    assert "purchase.view" in role_perms

    # Downgrade restores inventory.delete
    with patch.object(op, "get_bind", return_value=db_session.connection()):
        migration.downgrade()

    db_session.expire_all()
    restored_perm = db_session.query(Permission).filter_by(code="inventory.delete").first()
    assert restored_perm is not None
