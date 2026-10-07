"""
RoleManagerDialog is the UI half of #296: RoleService already had the
CRUD guards (see test_role_service.py), but nothing wired them into a
dialog an admin could actually use. These tests exercise the dialog's
list-loading, add/rename/delete flows, and its guards against modifying
the built-in Admin role or deleting a role still assigned to a user.
"""

from unittest.mock import patch

import pytest

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.models import Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.ui.dialogs.role_manager import RoleManagerDialog

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_role(db_session):
    role = Role(name=f"TestRole_{_next_suffix()}", access_level=0)
    db_session.add(role)
    db_session.flush()
    return role


@pytest.fixture
def admin_role(db_session):
    role = Role(name=ADMIN_ROLE_NAME, access_level=100)
    db_session.add(role)
    db_session.flush()
    return role


def _select_role(dialog, role_id):
    from PyQt6.QtCore import Qt

    for i in range(dialog.tree.topLevelItemCount()):
        item = dialog.tree.topLevelItem(i)
        if item.data(0, Qt.ItemDataRole.UserRole) == role_id:
            dialog.tree.setCurrentItem(item)
            return item
    raise AssertionError(f"Role {role_id} not found in tree")


class TestListLoading:
    def test_loads_existing_roles_with_their_user_counts(self, db_session, test_role):
        user = User(
            username=f"user_{_next_suffix()}",
            pin_hash=AuthService.hash_pin("1234"),
            role_id=test_role.id,
            is_active=True,
        )
        db_session.add(user)
        db_session.flush()

        dialog = RoleManagerDialog()

        item = _select_role(dialog, test_role.id)
        assert item.text(0) == test_role.name
        assert item.text(1) == "1"

    def test_admin_role_is_marked_as_built_in(self, db_session, admin_role):
        dialog = RoleManagerDialog()
        item = _select_role(dialog, admin_role.id)
        assert "Built-in" in item.text(0)


class TestCreate:
    def test_saving_a_new_name_creates_a_role(self, db_session):
        dialog = RoleManagerDialog()
        name = f"Supervisor_{_next_suffix()}"
        dialog.txt_name.setText(name)

        dialog._save_role()

        assert any(r.name == name for r in dialog.roles)

    def test_empty_name_shows_a_warning_and_does_not_create(self, db_session):
        dialog = RoleManagerDialog()
        dialog.txt_name.setText("   ")

        with patch("cbpos.ui.dialogs.role_manager.QMessageBox") as mock_box:
            dialog._save_role()

        mock_box.warning.assert_called_once()
        assert dialog.roles == []


class TestRename:
    def test_selecting_a_role_and_saving_a_new_name_renames_it(self, db_session, test_role):
        dialog = RoleManagerDialog()
        _select_role(dialog, test_role.id)

        new_name = f"{test_role.name}_Renamed"
        dialog.txt_name.setText(new_name)
        dialog._save_role()

        assert any(r.name == new_name for r in dialog.roles)

    def test_renaming_the_admin_role_is_blocked_with_a_warning(self, db_session, admin_role):
        dialog = RoleManagerDialog()
        _select_role(dialog, admin_role.id)

        dialog.txt_name.setText("Superadmin")

        with patch("cbpos.ui.dialogs.role_manager.QMessageBox") as mock_box:
            dialog._save_role()

        mock_box.warning.assert_called_once()
        assert any(r.name == ADMIN_ROLE_NAME for r in dialog.roles)


class TestDelete:
    def test_confirmed_delete_of_an_unused_role_removes_it(self, db_session, test_role):
        dialog = RoleManagerDialog()
        _select_role(dialog, test_role.id)

        with patch("cbpos.ui.dialogs.role_manager.QMessageBox") as mock_box:
            mock_box.StandardButton.Yes = 1
            mock_box.question.return_value = 1
            dialog._delete_role()

        assert not any(r.id == test_role.id for r in dialog.roles)

    def test_declining_the_confirmation_keeps_the_role(self, db_session, test_role):
        dialog = RoleManagerDialog()
        _select_role(dialog, test_role.id)

        with patch("cbpos.ui.dialogs.role_manager.QMessageBox") as mock_box:
            mock_box.StandardButton.Yes = 1
            mock_box.StandardButton.No = 0
            mock_box.question.return_value = 0
            dialog._delete_role()

        assert any(r.id == test_role.id for r in dialog.roles)

    def test_deleting_a_role_still_assigned_to_a_user_is_blocked(self, db_session, test_role):
        user = User(
            username=f"user_{_next_suffix()}",
            pin_hash=AuthService.hash_pin("1234"),
            role_id=test_role.id,
            is_active=True,
        )
        db_session.add(user)
        db_session.flush()

        dialog = RoleManagerDialog()
        _select_role(dialog, test_role.id)

        with patch("cbpos.ui.dialogs.role_manager.QMessageBox") as mock_box:
            dialog._delete_role()

        mock_box.warning.assert_called_once()
        mock_box.question.assert_not_called()
        assert any(r.id == test_role.id for r in dialog.roles)

    def test_deleting_the_admin_role_is_blocked_without_prompting(self, db_session, admin_role):
        dialog = RoleManagerDialog()
        _select_role(dialog, admin_role.id)

        with patch("cbpos.ui.dialogs.role_manager.QMessageBox") as mock_box:
            dialog._delete_role()

        mock_box.warning.assert_called_once()
        mock_box.question.assert_not_called()
        assert any(r.id == admin_role.id for r in dialog.roles)


class TestAdminGuardsShownUpfront:
    """#614: Admin's rules should be visible before acting, not only as an error popup."""

    def test_selecting_admin_disables_delete(self, db_session, admin_role):
        dialog = RoleManagerDialog()
        _select_role(dialog, admin_role.id)

        assert not dialog.btn_delete.isEnabled()
        assert dialog.btn_delete.toolTip()

    def test_selecting_admin_makes_the_name_read_only(self, db_session, admin_role):
        dialog = RoleManagerDialog()
        _select_role(dialog, admin_role.id)

        assert dialog.txt_name.isReadOnly()
        assert dialog.txt_name.toolTip()

    def test_selecting_another_role_after_admin_re_enables_editing(self, db_session, admin_role, test_role):
        dialog = RoleManagerDialog()
        _select_role(dialog, admin_role.id)
        _select_role(dialog, test_role.id)

        assert dialog.btn_delete.isEnabled()
        assert not dialog.txt_name.isReadOnly()
        assert not dialog.btn_delete.toolTip()

    def test_clearing_the_form_after_admin_re_enables_the_name(self, db_session, admin_role):
        dialog = RoleManagerDialog()
        _select_role(dialog, admin_role.id)
        dialog._clear_form()

        assert not dialog.txt_name.isReadOnly()
