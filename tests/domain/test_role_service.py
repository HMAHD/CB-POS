"""
Unit tests for RoleService — the CRUD layer added for #296.

The Role table and User.role_id foreign key already existed and were
fully wired (UserDialog's role picker, PermissionDialog's permission
grid), but nothing anywhere could create, rename, or delete a role --
UserService.get_all_roles() was the only role-related method that
existed. RoleService adds that missing CRUD, with guards against
renaming/deleting the built-in Admin role (PermissionService hardcodes
role.name == "Admin" for its permission bypass, so renaming it would
silently strip every admin of elevated access) and against deleting a
role that users are still assigned to.
"""

import pytest

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.models import Role, User
from cbpos.core.services.role_service import RoleService

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_role(db_session):
    suffix = _next_suffix()
    role = Role(name=f"TestRole_{suffix}", access_level=0)
    db_session.add(role)
    db_session.flush()
    return role


@pytest.fixture
def admin_role(db_session):
    role = Role(name=ADMIN_ROLE_NAME, access_level=100)
    db_session.add(role)
    db_session.flush()
    return role


class TestCreate:
    def test_creates_a_role_with_the_given_name(self, db_session):
        suffix = _next_suffix()
        role = RoleService.create(name=f"Supervisor_{suffix}")

        assert role is not None
        assert role.name == f"Supervisor_{suffix}"

    def test_rejects_an_empty_name(self, db_session):
        with pytest.raises(ValueError, match="required"):
            RoleService.create(name="   ")

    def test_rejects_a_duplicate_name(self, db_session, test_role):
        with pytest.raises(ValueError, match="already exists"):
            RoleService.create(name=test_role.name)


class TestUpdate:
    def test_renames_a_role(self, db_session, test_role):
        new_name = f"{test_role.name}_Renamed"
        updated = RoleService.update(test_role.id, name=new_name)

        assert updated.name == new_name

    def test_role_not_found_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            RoleService.update(999999, name="Whatever")

    def test_rejects_renaming_to_a_name_already_used_by_another_role(self, db_session, test_role):
        suffix = _next_suffix()
        other = Role(name=f"Other_{suffix}", access_level=0)
        db_session.add(other)
        db_session.flush()

        with pytest.raises(ValueError, match="already exists"):
            RoleService.update(test_role.id, name=other.name)

    def test_renaming_a_role_to_its_own_current_name_is_not_a_duplicate(self, db_session, test_role):
        updated = RoleService.update(test_role.id, name=test_role.name)
        assert updated.name == test_role.name

    def test_rejects_renaming_the_admin_role(self, db_session, admin_role):
        with pytest.raises(ValueError, match="Admin"):
            RoleService.update(admin_role.id, name="Superadmin")


class TestGetUserCountForRole:
    def test_counts_users_assigned_to_the_role(self, db_session, test_role):
        from cbpos.core.services.auth_service import AuthService

        user = User(
            username=f"user_{_next_suffix()}",
            pin_hash=AuthService.hash_pin("1234"),
            role_id=test_role.id,
            is_active=True,
        )
        db_session.add(user)
        db_session.flush()

        assert RoleService.get_user_count_for_role(test_role.id) == 1

    def test_zero_for_a_role_nobody_is_assigned_to(self, db_session, test_role):
        assert RoleService.get_user_count_for_role(test_role.id) == 0


class TestDelete:
    def test_deletes_an_unused_role(self, db_session, test_role):
        role_id = test_role.id
        RoleService.delete(role_id)

        assert db_session.get(Role, role_id) is None

    def test_role_not_found_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            RoleService.delete(999999)

    def test_rejects_deleting_the_admin_role(self, db_session, admin_role):
        with pytest.raises(ValueError, match="Admin"):
            RoleService.delete(admin_role.id)

    def test_rejects_deleting_a_role_still_assigned_to_users(self, db_session, test_role):
        from cbpos.core.services.auth_service import AuthService

        user = User(
            username=f"user_{_next_suffix()}",
            pin_hash=AuthService.hash_pin("1234"),
            role_id=test_role.id,
            is_active=True,
        )
        db_session.add(user)
        db_session.flush()

        with pytest.raises(ValueError, match="Cannot delete"):
            RoleService.delete(test_role.id)
