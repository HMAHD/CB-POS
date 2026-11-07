"""Admin lockout guard: saving the Admin role must never drop its critical permissions (#551)."""

from unittest.mock import patch

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME, Permissions
from cbpos.core.models import Permission, Role
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService


def test_saving_admin_with_no_permissions_keeps_critical_ones(db_session):
    codes = [Permissions.ADMIN_MANAGE_USERS, Permissions.ADMIN_MANAGE_ROLES]
    perms = []
    for code in codes:
        perm = db_session.query(Permission).filter_by(code=code).first() or Permission(code=code)
        perms.append(perm)
    role = db_session.query(Role).filter_by(name=ADMIN_ROLE_NAME).first() or Role(name=ADMIN_ROLE_NAME)
    role.permissions = list(perms)
    db_session.add_all([*perms, role])
    db_session.commit()

    # No logged-in user: skip the audit row so a stale user id from another test cannot trip the FK.
    with patch.object(AuthService, "get_current_user", return_value=None):
        assert PermissionService.update_role_permissions(role.id, []) is True

    db_session.expire_all()
    saved = {p.code for p in db_session.get(Role, role.id).permissions}
    assert set(codes) <= saved


def test_issue_858_manager_sees_stock_take_tab(db_session):
    """Manager role has STOCK_TAKE_VIEW so it can access the stock_take tab in MANAGEMENT_TAB_PERMISSIONS."""
    from cbpos.core.constants.permissions import MANAGEMENT_TAB_PERMISSIONS, Permissions

    stock_take_required = MANAGEMENT_TAB_PERMISSIONS["stock_take"]
    assert Permissions.STOCK_TAKE_VIEW in stock_take_required
    assert Permissions.ADMIN_MANAGE_USERS not in stock_take_required

    # Check that Manager groups include Stock Take permissions
    groups = Permissions.get_groups()
    stock_take_codes = groups.get("Stock Take", [])
    assert Permissions.STOCK_TAKE_VIEW in stock_take_codes
    assert any(code in stock_take_codes for code in stock_take_required)


def test_issue_858_manager_sees_pricing_and_promotions_tabs(db_session):
    """Price lists and promotions tabs use PRICING_MANAGE and PROMOTIONS_MANAGE and Manager has access."""
    from cbpos.core.constants.permissions import MANAGEMENT_TAB_PERMISSIONS, Permissions

    assert hasattr(Permissions, "PRICING_MANAGE")
    assert hasattr(Permissions, "PROMOTIONS_MANAGE")
    assert Permissions.PRICING_MANAGE in MANAGEMENT_TAB_PERMISSIONS["pricelists"]
    assert Permissions.PROMOTIONS_MANAGE in MANAGEMENT_TAB_PERMISSIONS["promotions"]

    groups = Permissions.get_groups()
    inventory_codes = groups.get("Inventory", [])
    assert Permissions.PRICING_MANAGE in inventory_codes
    assert Permissions.PROMOTIONS_MANAGE in inventory_codes


def test_issue_858_non_admin_cannot_edit_own_role_permissions(db_session):
    """A non-Admin cannot modify the permissions of their own role (ValueError('cannot_edit_own_role'))."""
    import pytest

    from cbpos.core.models import User

    p1 = Permission(code="sales.view")
    p2 = Permission(code="admin.manage_roles")
    role = Role(name="Supervisor_858", permissions=[p1, p2])
    db_session.add_all([p1, p2, role])
    db_session.flush()

    user = User(username="supervisor_858", pin_hash=AuthService.hash_pin("6666"), role_id=role.id, is_active=True)
    db_session.add(user)
    db_session.commit()

    with pytest.raises(ValueError, match="cannot_edit_own_role"):
        PermissionService.update_role_permissions(role.id, [p1.id], acting_user_id=user.id)


def test_issue_858_non_admin_cannot_grant_unheld_permission(db_session):
    """A non-Admin cannot grant permissions they do not possess themselves (ValueError('cannot_grant_unheld_permission'))."""
    import pytest

    from cbpos.core.models import User

    p_held = Permission(code="sales.view")
    p_unheld = Permission(code="admin.tools")
    actor_role = Role(name="ActorRole_858", permissions=[p_held])
    target_role = Role(name="TargetRole_858", permissions=[])
    db_session.add_all([p_held, p_unheld, actor_role, target_role])
    db_session.flush()

    actor_user = User(
        username="actor_858", pin_hash=AuthService.hash_pin("7777"), role_id=actor_role.id, is_active=True
    )
    db_session.add(actor_user)
    db_session.commit()

    with pytest.raises(ValueError, match="cannot_grant_unheld_permission"):
        PermissionService.update_role_permissions(target_role.id, [p_unheld.id], acting_user_id=actor_user.id)


def test_issue_858_migration_grants_pricing_to_existing_holders(db_session):
    """The migration inserts pricing.manage and promotions.manage and grants to holders of admin.manage_users."""
    import importlib.util
    from unittest.mock import patch

    from alembic import op
    from cbpos.config import Config

    # Setup roles and permissions
    p_admin_users = Permission(code="admin.manage_users", description="Admin Manage Users", group="Admin")
    role_holder = Role(name="CustomSupervisor", permissions=[p_admin_users])
    role_other = Role(name="JuniorStaff", permissions=[])
    db_session.add_all([p_admin_users, role_holder, role_other])
    db_session.commit()

    migration_path = Config.BASE_DIR / "alembic" / "versions" / "7d8e9f0a1b2c_add_pricing_and_promotions_permissions.py"
    spec = importlib.util.spec_from_file_location("migration_858", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with patch.object(op, "get_bind", return_value=db_session.connection()):
        migration.upgrade()

    db_session.expire_all()
    pricing_p = db_session.query(Permission).filter_by(code="pricing.manage").first()
    promotions_p = db_session.query(Permission).filter_by(code="promotions.manage").first()

    assert pricing_p is not None
    assert promotions_p is not None

    holder_codes = {p.code for p in db_session.get(Role, role_holder.id).permissions}
    assert "pricing.manage" in holder_codes
    assert "promotions.manage" in holder_codes

    other_codes = {p.code for p in db_session.get(Role, role_other.id).permissions}
    assert "pricing.manage" not in other_codes
    assert "promotions.manage" not in other_codes

    # Test downgrade
    with patch.object(op, "get_bind", return_value=db_session.connection()):
        migration.downgrade()

    db_session.expire_all()
    assert db_session.query(Permission).filter_by(code="pricing.manage").first() is None
    assert db_session.query(Permission).filter_by(code="promotions.manage").first() is None
