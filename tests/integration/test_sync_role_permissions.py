"""Integration tests for Issue #872: Role permissions sync between Main PC and tills."""

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Permission, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService
from tests.helpers.sync_two_machines import Shop, isolated_settings

TILL = "TERM-02"


@pytest.fixture
def shop(tmp_path):
    with isolated_settings(str(tmp_path), terminal_id="MAIN-01", terminal_mode="main"):
        s = Shop(str(tmp_path))
        s.add_till(TILL)
        yield s


def test_issue_872_custom_role_arrives_with_permissions(shop, tmp_path):
    """Custom roles created on Main PC arrive on till with their permissions (#872)."""
    # 1. Create custom role with permissions on Main PC
    with shop.on("main"), shop.session("main") as s:
        p1 = s.query(Permission).filter_by(code=Permissions.SALES_VIEW).first()
        if not p1:
            p1 = Permission(code=Permissions.SALES_VIEW, description="View sales")
            s.add(p1)
        p2 = s.query(Permission).filter_by(code=Permissions.SALES_VOID).first()
        if not p2:
            p2 = Permission(code=Permissions.SALES_VOID, description="Void item")
            s.add(p2)
        s.flush()

        role = Role(name="Supervisor", access_level=3, permissions=[p1, p2])
        s.add(role)
        s.commit()
        role_id = role.id

    # 2. Till pulls catalog
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        pulled = shop.pull(TILL, full=True)
        assert pulled > 0

        with shop.session(TILL) as s:
            till_role = s.get(Role, role_id)
            assert till_role is not None
            assert till_role.name == "Supervisor"
            till_perm_codes = {p.code for p in till_role.permissions}
            assert Permissions.SALES_VIEW in till_perm_codes
            assert Permissions.SALES_VOID in till_perm_codes


def test_issue_872_revoked_permission_denied_on_till_after_one_cycle(shop, tmp_path):
    """Removing a permission on Main PC takes effect on till for logged-in user (#872)."""
    # 1. Setup Cashier role and user on Main
    with shop.on("main"), shop.session("main") as s:
        p_view = s.query(Permission).filter_by(code=Permissions.SALES_VIEW).first()
        if not p_view:
            p_view = Permission(code=Permissions.SALES_VIEW, description="View sales")
            s.add(p_view)
        p_void = s.query(Permission).filter_by(code=Permissions.SALES_VOID).first()
        if not p_void:
            p_void = Permission(code=Permissions.SALES_VOID, description="Void item")
            s.add(p_void)
        s.flush()

        role = Role(name="CustomCashier", access_level=1, permissions=[p_view, p_void])
        s.add(role)
        s.flush()

        user = User(username="cashier1", pin_hash=AuthService.hash_pin("1234"), role=role)
        s.add(user)
        s.commit()
        role_id = role.id
        p_view_id = p_view.id

    # 2. Sync to till
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        shop.pull(TILL, full=True)

    # 3. Log in cashier on till
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"), shop.on(TILL):
        login_user = AuthService.login("1234")
        assert login_user is not None
        assert PermissionService.user_has_permission(login_user, Permissions.SALES_VOID) is True

    # 4. Revoke SALES_VOID_ITEM on Main PC
    with shop.on("main"):
        # Keep only p_view
        ok = PermissionService.update_role_permissions(role_id, [p_view_id])
        assert ok is True

    # 5. Connect roles_changed signal to AuthService.refresh_current_user on till
    client = shop.client(TILL)
    client.roles_changed.connect(AuthService.refresh_current_user)

    # 6. Till syncs catalog
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"), shop.on(TILL):
        shop.pull(TILL)

        # 7. Check current user on till: SALES_VOID_ITEM must now be denied
        curr = AuthService.get_current_user()
        assert curr is not None
        assert PermissionService.user_has_permission(curr, Permissions.SALES_VOID) is False
        assert PermissionService.user_has_permission(curr, Permissions.SALES_VIEW) is True
