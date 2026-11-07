"""
#614: the Admin-lockout guard removed ItemIsUserCheckable from the WHOLE
permission row, so "Manage Users"/"Manage Roles" could never be granted
to a Manager or Cashier. Only Admin's own critical cells should be locked,
and the checkboxes should sit centered in their role column.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME, CRITICAL_ADMIN_PERMISSIONS, Permissions
from cbpos.core.models import Permission, Role
from cbpos.core.services.auth_service import AuthService
from cbpos.ui.dialogs.permission_dialog import PermissionDialog

EXTRA_CODE = "test.x614_non_critical"


def _get_or_create_perm(session, code: str) -> Permission:
    perm = session.query(Permission).filter_by(code=code).first()
    if perm is None:
        perm = Permission(code=code, description=code, group="Admin")
        session.add(perm)
    return perm


def _get_or_create_role(session, name: str) -> Role:
    role = session.query(Role).filter_by(name=name).first()
    if role is None:
        role = Role(name=name)
        session.add(role)
    return role


@pytest.fixture
def matrix(db_session) -> dict:
    """Admin holds both critical permissions; Manager holds none. Returns plain ids, because the
    dialog's service calls expunge ORM objects from the shared test session."""
    perms = {code: _get_or_create_perm(db_session, code) for code in [*CRITICAL_ADMIN_PERMISSIONS, EXTRA_CODE]}
    admin = _get_or_create_role(db_session, ADMIN_ROLE_NAME)
    manager = _get_or_create_role(db_session, "Manager")
    admin.permissions = [perms[code] for code in CRITICAL_ADMIN_PERMISSIONS]
    manager.permissions = []
    db_session.commit()

    # The shared test session expires on commit and the loaders expunge it, so hand the dialog
    # plain snapshots to read; saving still goes through the real PermissionService.
    perm_rows = {
        code: SimpleNamespace(id=p.id, code=p.code, description=p.description, group=p.group)
        for code, p in perms.items()
    }
    role_rows = [
        SimpleNamespace(id=r.id, name=r.name, permissions=[perm_rows[p.code] for p in r.permissions])
        for r in (admin, manager)
    ]
    return {
        "admin": admin.id,
        "manager": manager.id,
        "perms": {code: p.id for code, p in perm_rows.items()},
        "role_rows": role_rows,
        "perm_rows": list(perm_rows.values()),
    }


@pytest.fixture
def open_dialog(qtbot, matrix):
    def _open() -> PermissionDialog:
        with (
            patch("cbpos.ui.dialogs.permission_dialog.UserService.get_all_roles", return_value=matrix["role_rows"]),
            patch(
                "cbpos.ui.dialogs.permission_dialog.PermissionService.get_all_permissions",
                return_value=matrix["perm_rows"],
            ),
        ):
            return _open_dialog(qtbot)

    return _open


def _open_dialog(qtbot) -> PermissionDialog:
    dialog = PermissionDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog


def _cell(dialog: PermissionDialog, perm_id: int, role_id: int):
    col = 1 + next(i for i, r in enumerate(dialog.roles) if r.id == role_id)
    root = dialog.tree.invisibleRootItem()
    for g in range(root.childCount()):
        group = root.child(g)
        for p in range(group.childCount()):
            item = group.child(p)
            if item.data(0, Qt.ItemDataRole.UserRole) == perm_id:
                return item, col
    raise AssertionError(f"permission {perm_id} not in tree")


def _click_cell_center(dialog: PermissionDialog, item, col: int) -> None:
    index = dialog.tree.indexFromItem(item, col)
    dialog.tree.scrollTo(index)
    rect = dialog.tree.visualRect(index)
    QTest.mouseClick(dialog.tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())


class TestManagerCanBeGrantedCriticalPermissions:
    def test_clicking_managers_manage_users_cell_ticks_it(self, open_dialog, matrix):
        dialog = open_dialog()
        item, col = _cell(dialog, matrix["perms"][Permissions.ADMIN_MANAGE_USERS], matrix["manager"])
        assert item.checkState(col) == Qt.CheckState.Unchecked

        _click_cell_center(dialog, item, col)

        assert item.checkState(col) == Qt.CheckState.Checked

    def test_space_key_ticks_managers_manage_users_cell(self, open_dialog, matrix):
        dialog = open_dialog()
        item, col = _cell(dialog, matrix["perms"][Permissions.ADMIN_MANAGE_USERS], matrix["manager"])
        dialog.tree.setCurrentIndex(dialog.tree.indexFromItem(item, col))
        dialog.tree.setFocus()

        QTest.keyClick(dialog.tree, Qt.Key.Key_Space)

        assert item.checkState(col) == Qt.CheckState.Checked

    def test_granting_manage_users_to_manager_is_saved(self, open_dialog, matrix, db_session):
        dialog = open_dialog()
        item, col = _cell(dialog, matrix["perms"][Permissions.ADMIN_MANAGE_USERS], matrix["manager"])
        _click_cell_center(dialog, item, col)

        with (
            patch("cbpos.ui.dialogs.permission_dialog.QMessageBox"),
            patch.object(AuthService, "get_current_user", return_value=None),
        ):
            dialog.save_changes()

        db_session.expire_all()
        saved = {p.code for p in db_session.get(Role, matrix["manager"]).permissions}
        assert Permissions.ADMIN_MANAGE_USERS in saved


class TestAdminCriticalCellsAreLocked:
    @pytest.mark.parametrize("code", CRITICAL_ADMIN_PERMISSIONS)
    def test_clicking_admins_critical_cell_does_not_untick_it(self, open_dialog, matrix, code):
        dialog = open_dialog()
        item, col = _cell(dialog, matrix["perms"][code], matrix["admin"])
        assert item.checkState(col) == Qt.CheckState.Checked

        _click_cell_center(dialog, item, col)

        assert item.checkState(col) == Qt.CheckState.Checked

    def test_space_key_does_not_untick_admins_critical_cell(self, open_dialog, matrix):
        dialog = open_dialog()
        item, col = _cell(dialog, matrix["perms"][Permissions.ADMIN_MANAGE_ROLES], matrix["admin"])
        dialog.tree.setCurrentIndex(dialog.tree.indexFromItem(item, col))
        dialog.tree.setFocus()

        QTest.keyClick(dialog.tree, Qt.Key.Key_Space)

        assert item.checkState(col) == Qt.CheckState.Checked

    def test_admins_non_critical_cell_stays_editable(self, open_dialog, matrix):
        dialog = open_dialog()
        item, col = _cell(dialog, matrix["perms"][EXTRA_CODE], matrix["admin"])
        assert item.checkState(col) == Qt.CheckState.Unchecked

        _click_cell_center(dialog, item, col)

        assert item.checkState(col) == Qt.CheckState.Checked


class TestNonAdminActorPermissionDialog:
    def test_non_admin_cannot_edit_admin_or_own_role(self, open_dialog, matrix, monkeypatch):
        from cbpos.ui.dialogs.permission_dialog import LOCKED_CELL_ROLE

        manager_role = SimpleNamespace(
            id=matrix["manager"],
            name="Manager",
            permissions=[
                SimpleNamespace(id=matrix["perms"][Permissions.ADMIN_MANAGE_ROLES], code=Permissions.ADMIN_MANAGE_ROLES)
            ],
        )
        current_user = SimpleNamespace(id=10, username="manager_user", role=manager_role, role_id=matrix["manager"])
        monkeypatch.setattr(AuthService, "get_current_user", lambda: current_user)

        dialog = open_dialog()

        # Admin column is locked
        item_admin, col_admin = _cell(dialog, matrix["perms"][EXTRA_CODE], matrix["admin"])
        assert item_admin.data(col_admin, LOCKED_CELL_ROLE) is True

        # Manager column (actor's own role) is locked
        item_mgr, col_mgr = _cell(dialog, matrix["perms"][Permissions.ADMIN_MANAGE_ROLES], matrix["manager"])
        assert item_mgr.data(col_mgr, LOCKED_CELL_ROLE) is True

        # Unheld permission is locked
        item_unheld, col_mgr2 = _cell(dialog, matrix["perms"][EXTRA_CODE], matrix["manager"])
        assert item_unheld.data(col_mgr2, LOCKED_CELL_ROLE) is True
