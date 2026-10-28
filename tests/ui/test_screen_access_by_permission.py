"""
#549: the side menu showed Management and Settings to any role *named* admin/manager/owner,
while the screens themselves check permissions. A custom role with full permissions couldn't
see them, a "Manager" with nothing ticked could, and renaming a role changed access. Now the
menu checks permissions, and an upgrade grants the new screen permissions to exactly the roles
the old name check let in.
"""

import sqlite3
from types import SimpleNamespace

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine

from alembic import command
from cbpos.config import Config
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Base
from cbpos.core.services.permission_service import PermissionService
from cbpos.ui.widgets.side_menu import SideMenu

pytestmark = pytest.mark.usefixtures("qapp")

ADMIN_GROUP = Permissions.get_groups()["Admin"]


def _user(role_name: str, codes) -> SimpleNamespace:
    role = SimpleNamespace(name=role_name, permissions=[SimpleNamespace(code=c) for c in codes])
    return SimpleNamespace(id=1, username="someone", role=role)


@pytest.fixture
def menu(qapp):
    widget = SideMenu()
    yield widget
    widget.deleteLater()


def _shown(menu: SideMenu, user) -> tuple[bool, bool]:
    menu.set_user(user)
    return (not menu.btn_management.isHidden(), not menu.btn_settings.isHidden())


class TestSideMenu:
    def test_custom_supervisor_with_admin_permissions_sees_both(self, menu):
        assert _shown(menu, _user("Supervisor", ADMIN_GROUP)) == (True, True)

    def test_screen_permissions_alone_open_the_screens(self, menu):
        assert _shown(menu, _user("Shift Lead", [Permissions.MANAGEMENT_VIEW])) == (True, False)
        assert _shown(menu, _user("Shift Lead", [Permissions.SETTINGS_VIEW])) == (False, True)

    def test_role_named_manager_without_permissions_sees_neither(self, menu):
        assert _shown(menu, _user("Manager", [])) == (False, False)
        assert _shown(menu, _user("owner", [Permissions.SALES_VIEW])) == (False, False)

    def test_renaming_a_role_does_not_change_access(self, menu):
        codes = [Permissions.MANAGEMENT_VIEW, Permissions.SETTINGS_VIEW]
        assert _shown(menu, _user("Manager", codes)) == _shown(menu, _user("Floor Boss", codes)) == (True, True)
        assert _shown(menu, _user("Manager", [])) == _shown(menu, _user("Floor Boss", [])) == (False, False)

    def test_seeded_cashier_sees_neither(self, menu):
        cashier = [
            Permissions.SALES_VIEW,
            Permissions.SALES_ADD_ITEM,
            Permissions.DOCUMENTS_VIEW,
            Permissions.CREDIT_RECEIVE_PAYMENT,
            Permissions.CASH_OPEN_DRAWER,
        ]
        assert _shown(menu, _user("Cashier", cashier)) == (False, False)

    def test_guest_sees_neither(self, menu):
        assert _shown(menu, None) == (False, False)

    def test_no_role_name_check_left_in_the_side_menu(self):
        import inspect

        from cbpos.ui.widgets import side_menu

        source = inspect.getsource(side_menu)
        assert ".role.name.lower()" not in source and '"manager"' not in source


def test_permission_service_handles_missing_permissions():
    user = SimpleNamespace(role=SimpleNamespace(name="Cashier"))
    assert PermissionService.can_open_management(user) is False
    assert PermissionService.can_open_settings(user) is False


# ---------------------------------------------------------------------------
# Upgrade: existing admin/manager/owner roles keep their access
# ---------------------------------------------------------------------------

PREVIOUS_HEAD = "c3f1a9d27e54"
# Upgrade to this migration only, not "head": the schema comes from
# create_all(), so a later migration creating a table would find it there.
SCREEN_PERMISSIONS = "c83b41393b82"


@pytest.fixture
def old_db(tmp_path, monkeypatch):
    """A database at the revision before the screen permissions, with roles named the old way."""
    db_path = tmp_path / "cbpos.db"
    uri = f"sqlite:///{db_path}"
    engine = create_engine(uri)
    Base.metadata.create_all(engine)
    engine.dispose()
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO roles (id, name, access_level, last_modified) VALUES (?, ?, 0, CURRENT_TIMESTAMP)",
            [(1, "Admin"), (2, "manager"), (3, "Owner"), (4, "Cashier"), (5, "Supervisor")],
        )

    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "DB_URI", uri)
    cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.stamp(cfg, PREVIOUS_HEAD)
    return db_path, cfg


def _grants(db_path) -> dict[str, set[str]]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT r.name, p.code FROM role_permissions rp "
            "JOIN roles r ON r.id = rp.role_id JOIN permissions p ON p.id = rp.permission_id"
        ).fetchall()
    grants: dict[str, set[str]] = {}
    for role, code in rows:
        grants.setdefault(role, set()).add(code)
    return grants


def test_upgrade_grants_screens_to_the_roles_the_old_name_check_let_in(old_db):
    db_path, cfg = old_db
    command.upgrade(cfg, SCREEN_PERMISSIONS)

    screens = {Permissions.MANAGEMENT_VIEW, Permissions.SETTINGS_VIEW}
    grants = _grants(db_path)
    for role in ("Admin", "manager", "Owner"):
        assert grants[role] == screens
    assert "Cashier" not in grants and "Supervisor" not in grants
    with sqlite3.connect(db_path) as conn:
        groups = dict(conn.execute('SELECT code, "group" FROM permissions WHERE code IN (?, ?)', tuple(screens)))
    assert groups == dict.fromkeys(screens, "Screens")

    command.downgrade(cfg, PREVIOUS_HEAD)
    assert _grants(db_path) == {}


def test_new_installs_give_managers_the_screen_permissions():
    import inspect

    from cbpos.core.services.database_setup_service import DatabaseSetupService

    assert Permissions.get_groups()["Screens"] == [Permissions.MANAGEMENT_VIEW, Permissions.SETTINGS_VIEW]
    seed = (Config.BASE_DIR / "scripts" / "seed.py").read_text(encoding="utf-8")
    for source in (inspect.getsource(DatabaseSetupService.create_empty_database), seed):
        manager_block = source.split("manager_groups = [", 1)[1].split("]", 1)[0]
        assert '"Screens"' in manager_block
