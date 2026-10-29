"""
#552 ([REC-13]): Permissions: parent toggle (tristate) for permission groups.
- Ticking a group under a role ticks all its permissions for that role only.
- Group shows partial state (indeterminate) when some permissions are ticked.
- Admin's protected permissions stay granted even when their group is unticked.
- Saving reads only genuine child permissions.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME, Permissions
from cbpos.core.models import Permission, Role
from cbpos.core.services.auth_service import AuthService
from cbpos.ui.dialogs.permission_dialog import LOCKED_CELL_ROLE, PermissionDialog

NON_CRITICAL_ADMIN_CODE = "admin.audit_logs"
SALES_PERM_1 = "sales.make_sale"
SALES_PERM_2 = "sales.void_item"


def _get_or_create_perm(session, code: str, group: str) -> Permission:
    perm = session.query(Permission).filter_by(code=code).first()
    if perm is None:
        perm = Permission(code=code, description=code, group=group)
        session.add(perm)
    return perm


def _get_or_create_role(session, name: str) -> Role:
    role = session.query(Role).filter_by(name=name).first()
    if role is None:
        role = Role(name=name)
        session.add(role)
    return role


@pytest.fixture
def tristate_matrix(db_session) -> dict:
    admin_perms = [
        _get_or_create_perm(db_session, Permissions.ADMIN_MANAGE_USERS, "Admin"),
        _get_or_create_perm(db_session, Permissions.ADMIN_MANAGE_ROLES, "Admin"),
        _get_or_create_perm(db_session, NON_CRITICAL_ADMIN_CODE, "Admin"),
    ]
    sales_perms = [
        _get_or_create_perm(db_session, SALES_PERM_1, "Sales"),
        _get_or_create_perm(db_session, SALES_PERM_2, "Sales"),
    ]
    all_perms = admin_perms + sales_perms

    admin_role = _get_or_create_role(db_session, ADMIN_ROLE_NAME)
    manager_role = _get_or_create_role(db_session, "Manager")

    # Admin initially has all Admin group perms and one Sales perm
    admin_role.permissions = [admin_perms[0], admin_perms[1], admin_perms[2], sales_perms[0]]
    # Manager initially has one Admin perm and no Sales perms
    manager_role.permissions = [admin_perms[2]]
    db_session.commit()

    perm_rows = {
        p.code: SimpleNamespace(id=p.id, code=p.code, description=p.description, group=p.group) for p in all_perms
    }
    role_rows = [
        SimpleNamespace(id=r.id, name=r.name, permissions=[perm_rows[p.code] for p in r.permissions])
        for r in (admin_role, manager_role)
    ]
    return {
        "admin_id": admin_role.id,
        "manager_id": manager_role.id,
        "perms": perm_rows,
        "role_rows": role_rows,
        "perm_rows": list(perm_rows.values()),
    }


@pytest.fixture
def open_dialog(qtbot, tristate_matrix):
    def _open() -> PermissionDialog:
        with (
            patch(
                "cbpos.ui.dialogs.permission_dialog.UserService.get_all_roles",
                return_value=tristate_matrix["role_rows"],
            ),
            patch(
                "cbpos.ui.dialogs.permission_dialog.PermissionService.get_all_permissions",
                return_value=tristate_matrix["perm_rows"],
            ),
        ):
            dialog = PermissionDialog()
            qtbot.addWidget(dialog)
            dialog.show()
            qtbot.waitExposed(dialog)
            return dialog

    return _open


def _get_group_item(dialog: PermissionDialog, group_label: str):
    root = dialog.tree.invisibleRootItem()
    for g in range(root.childCount()):
        group = root.child(g)
        if group_label.lower() in group.text(0).lower():
            return group
    raise AssertionError(f"group {group_label} not found")


def _get_role_col(dialog: PermissionDialog, role_id: int) -> int:
    return 1 + next(i for i, r in enumerate(dialog.roles) if r.id == role_id)


def _click_cell(dialog: PermissionDialog, item, col: int) -> None:
    index = dialog.tree.indexFromItem(item, col)
    dialog.tree.scrollTo(index)
    rect = dialog.tree.visualRect(index)
    QTest.mouseClick(dialog.tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())


class TestGroupAutoTristateFlagsAndInitialState:
    def test_group_item_has_auto_tristate_flag(self, open_dialog):
        dialog = open_dialog()
        group = _get_group_item(dialog, "Admin")
        assert bool(group.flags() & Qt.ItemFlag.ItemIsAutoTristate)
        assert bool(group.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        assert not bool(group.flags() & Qt.ItemFlag.ItemIsSelectable)

    def test_initial_check_states_reflect_children(self, open_dialog, tristate_matrix):
        dialog = open_dialog()
        admin_col = _get_role_col(dialog, tristate_matrix["admin_id"])
        manager_col = _get_role_col(dialog, tristate_matrix["manager_id"])

        admin_group = _get_group_item(dialog, "Admin")
        sales_group = _get_group_item(dialog, "Sales")

        # Admin holds all 3 Admin permissions -> Checked
        assert admin_group.checkState(admin_col) == Qt.CheckState.Checked

        # Admin holds 1 of 2 Sales permissions -> PartiallyChecked
        assert sales_group.checkState(admin_col) == Qt.CheckState.PartiallyChecked

        # Manager holds 1 of 3 Admin permissions -> PartiallyChecked
        assert admin_group.checkState(manager_col) == Qt.CheckState.PartiallyChecked

        # Manager holds 0 of 2 Sales permissions -> Unchecked
        assert sales_group.checkState(manager_col) == Qt.CheckState.Unchecked


class TestTickingGroupUnderRole:
    def test_ticking_unchecked_group_ticks_all_permissions_for_that_role_only(self, open_dialog, tristate_matrix):
        dialog = open_dialog()
        manager_col = _get_role_col(dialog, tristate_matrix["manager_id"])
        admin_col = _get_role_col(dialog, tristate_matrix["admin_id"])

        sales_group = _get_group_item(dialog, "Sales")
        assert sales_group.checkState(manager_col) == Qt.CheckState.Unchecked
        admin_sales_initial = sales_group.checkState(admin_col)

        # Click Manager's Sales group cell
        _click_cell(dialog, sales_group, manager_col)

        # Manager's Sales group is now Checked, and all its children are Checked
        assert sales_group.checkState(manager_col) == Qt.CheckState.Checked
        for i in range(sales_group.childCount()):
            assert sales_group.child(i).checkState(manager_col) == Qt.CheckState.Checked

        # Admin's column is completely unchanged
        assert sales_group.checkState(admin_col) == admin_sales_initial

    def test_ticking_partially_checked_group_ticks_all_permissions(self, open_dialog, tristate_matrix):
        dialog = open_dialog()
        manager_col = _get_role_col(dialog, tristate_matrix["manager_id"])

        admin_group = _get_group_item(dialog, "Admin")
        assert admin_group.checkState(manager_col) == Qt.CheckState.PartiallyChecked

        # Click partially checked group -> transitions to Checked
        _click_cell(dialog, admin_group, manager_col)

        assert admin_group.checkState(manager_col) == Qt.CheckState.Checked
        for i in range(admin_group.childCount()):
            assert admin_group.child(i).checkState(manager_col) == Qt.CheckState.Checked

    def test_unticking_checked_group_unticks_all_unlocked_permissions(self, open_dialog, tristate_matrix):
        dialog = open_dialog()
        manager_col = _get_role_col(dialog, tristate_matrix["manager_id"])

        # Check Sales group first
        sales_group = _get_group_item(dialog, "Sales")
        _click_cell(dialog, sales_group, manager_col)
        assert sales_group.checkState(manager_col) == Qt.CheckState.Checked

        # Click again to untick
        _click_cell(dialog, sales_group, manager_col)
        assert sales_group.checkState(manager_col) == Qt.CheckState.Unchecked
        for i in range(sales_group.childCount()):
            assert sales_group.child(i).checkState(manager_col) == Qt.CheckState.Unchecked


class TestAdminProtectedPermissionsStayGranted:
    def test_unticking_admin_group_retains_critical_permissions(self, open_dialog, tristate_matrix):
        dialog = open_dialog()
        admin_col = _get_role_col(dialog, tristate_matrix["admin_id"])
        admin_group = _get_group_item(dialog, "Admin")

        assert admin_group.checkState(admin_col) == Qt.CheckState.Checked

        # Untick Admin group
        _click_cell(dialog, admin_group, admin_col)

        # Critical permissions stay checked; non-critical becomes unchecked; group becomes PartiallyChecked
        assert admin_group.checkState(admin_col) == Qt.CheckState.PartiallyChecked

        manage_users_item = next(
            admin_group.child(i)
            for i in range(admin_group.childCount())
            if admin_group.child(i).data(0, Qt.ItemDataRole.UserRole)
            == tristate_matrix["perms"][Permissions.ADMIN_MANAGE_USERS].id
        )
        manage_roles_item = next(
            admin_group.child(i)
            for i in range(admin_group.childCount())
            if admin_group.child(i).data(0, Qt.ItemDataRole.UserRole)
            == tristate_matrix["perms"][Permissions.ADMIN_MANAGE_ROLES].id
        )
        audit_logs_item = next(
            admin_group.child(i)
            for i in range(admin_group.childCount())
            if admin_group.child(i).data(0, Qt.ItemDataRole.UserRole)
            == tristate_matrix["perms"][NON_CRITICAL_ADMIN_CODE].id
        )

        assert manage_users_item.checkState(admin_col) == Qt.CheckState.Checked
        assert manage_roles_item.checkState(admin_col) == Qt.CheckState.Checked
        assert audit_logs_item.checkState(admin_col) == Qt.CheckState.Unchecked
        assert manage_users_item.data(admin_col, LOCKED_CELL_ROLE) is True
        assert manage_roles_item.data(admin_col, LOCKED_CELL_ROLE) is True

    def test_rechecking_admin_group_checks_all_items_again(self, open_dialog, tristate_matrix):
        dialog = open_dialog()
        admin_col = _get_role_col(dialog, tristate_matrix["admin_id"])
        admin_group = _get_group_item(dialog, "Admin")

        # Untick -> becomes PartiallyChecked
        _click_cell(dialog, admin_group, admin_col)
        assert admin_group.checkState(admin_col) == Qt.CheckState.PartiallyChecked

        # Click again -> becomes Checked, all items checked
        _click_cell(dialog, admin_group, admin_col)
        assert admin_group.checkState(admin_col) == Qt.CheckState.Checked
        for i in range(admin_group.childCount()):
            assert admin_group.child(i).checkState(admin_col) == Qt.CheckState.Checked

    def test_space_key_on_admin_group_preserves_locked_cells(self, open_dialog, tristate_matrix):
        dialog = open_dialog()
        admin_col = _get_role_col(dialog, tristate_matrix["admin_id"])
        admin_group = _get_group_item(dialog, "Admin")

        idx = dialog.tree.indexFromItem(admin_group, admin_col)
        dialog.tree.setCurrentIndex(idx)
        dialog.tree.setFocus()

        # Space key toggles Admin group
        QTest.keyClick(dialog.tree, Qt.Key.Key_Space)

        # Critical permissions stay checked; group stays PartiallyChecked
        assert admin_group.checkState(admin_col) == Qt.CheckState.PartiallyChecked


class TestSavingAfterGroupToggle:
    def test_saving_reads_exact_child_permissions_after_toggle(self, open_dialog, tristate_matrix, db_session):
        dialog = open_dialog()
        manager_col = _get_role_col(dialog, tristate_matrix["manager_id"])
        admin_col = _get_role_col(dialog, tristate_matrix["admin_id"])

        sales_group = _get_group_item(dialog, "Sales")
        admin_group = _get_group_item(dialog, "Admin")

        # Manager: grant all Sales permissions via group toggle
        _click_cell(dialog, sales_group, manager_col)

        # Admin: untick Admin group (critical stay granted, audit_logs unchecked)
        _click_cell(dialog, admin_group, admin_col)

        with (
            patch("cbpos.ui.dialogs.permission_dialog.QMessageBox"),
            patch.object(AuthService, "get_current_user", return_value=None),
        ):
            dialog.save_changes()

        db_session.expire_all()

        manager_saved = {p.code for p in db_session.get(Role, tristate_matrix["manager_id"]).permissions}
        admin_saved = {p.code for p in db_session.get(Role, tristate_matrix["admin_id"]).permissions}

        # Manager now has both Sales perms plus their initial audit logs
        assert SALES_PERM_1 in manager_saved
        assert SALES_PERM_2 in manager_saved
        assert NON_CRITICAL_ADMIN_CODE in manager_saved

        # Admin still has both critical permissions
        assert Permissions.ADMIN_MANAGE_USERS in admin_saved
        assert Permissions.ADMIN_MANAGE_ROLES in admin_saved
        # Admin's non-critical admin perm was unticked
        assert NON_CRITICAL_ADMIN_CODE not in admin_saved
