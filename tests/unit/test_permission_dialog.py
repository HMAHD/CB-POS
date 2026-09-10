"""
PermissionDialog.save_changes() called PermissionService.update_role_permission()
(singular) -- a method that has never existed. PermissionService only defines
update_role_permissions() (plural, takes a full permission-id list per role).
Every click of "Save Changes" in the Manage Permissions dialog raised
AttributeError, so no permission change made through this dialog has ever
been persisted.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem

from cbpos.ui.dialogs.permission_dialog import PermissionDialog

pytestmark = pytest.mark.usefixtures("qapp")


def _build_tree(roles, checked_by_role):
    """A 1-group, 2-permission tree with columns Permission | role1 | role2 | ..."""
    tree = QTreeWidget()
    tree.setColumnCount(1 + len(roles))
    group = QTreeWidgetItem(tree)
    group.setText(0, "Test Group")

    for perm_id in (1, 2):
        item = QTreeWidgetItem(group)
        item.setData(0, Qt.ItemDataRole.UserRole, perm_id)
        for col, role in enumerate(roles, start=1):
            state = Qt.CheckState.Checked if perm_id in checked_by_role.get(role.id, []) else Qt.CheckState.Unchecked
            item.setCheckState(col, state)
    return tree


class TestCollectRolePermissionMap:
    def test_maps_each_role_to_only_its_checked_permissions(self):
        roles = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        tree = _build_tree(roles, checked_by_role={1: [1], 2: [2]})

        result = PermissionDialog.collect_role_permission_map(tree, roles)

        assert result == {1: [1], 2: [2]}

    def test_role_with_nothing_checked_maps_to_empty_list(self):
        roles = [SimpleNamespace(id=1)]
        tree = _build_tree(roles, checked_by_role={})

        result = PermissionDialog.collect_role_permission_map(tree, roles)

        assert result == {1: []}


class TestSaveChanges:
    def test_calls_update_role_permissions_once_per_role_with_its_checked_ids(self):
        roles = [SimpleNamespace(id=10), SimpleNamespace(id=20)]
        dialog = PermissionDialog.__new__(PermissionDialog)
        dialog.roles = roles
        dialog.tree = _build_tree(roles, checked_by_role={10: [1, 2], 20: []})

        with (
            patch("cbpos.ui.dialogs.permission_dialog.PermissionService") as mock_service,
            patch("cbpos.ui.dialogs.permission_dialog.QMessageBox"),
            patch.object(PermissionDialog, "accept"),
        ):
            dialog.save_changes()

        mock_service.update_role_permissions.assert_any_call(10, [1, 2])
        mock_service.update_role_permissions.assert_any_call(20, [])
        assert mock_service.update_role_permissions.call_count == 2

    def test_a_role_with_no_checked_permissions_still_gets_its_list_cleared(self):
        """Regression guard: the old buggy version silently dropped roles with 0
        checked permissions from the update entirely, because the loop only ever
        called `update_role_permission` per-checked-item, never per-role."""
        roles = [SimpleNamespace(id=5)]
        dialog = PermissionDialog.__new__(PermissionDialog)
        dialog.roles = roles
        dialog.tree = _build_tree(roles, checked_by_role={})

        with (
            patch("cbpos.ui.dialogs.permission_dialog.PermissionService") as mock_service,
            patch("cbpos.ui.dialogs.permission_dialog.QMessageBox"),
            patch.object(PermissionDialog, "accept"),
        ):
            dialog.save_changes()

        mock_service.update_role_permissions.assert_called_once_with(5, [])
