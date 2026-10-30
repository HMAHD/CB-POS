"""Tests that user.role.permissions is safe to access on the detached User
returned by AuthService -- both login() and verify_pin()
expunge the user (and its role) from their session, so any relationship
not eager-loaded raises DetachedInstanceError the moment something reads
it. PermissionService.user_has_permission() reads user.role.permissions
for every non-admin user on every permission check -- a guaranteed crash
that was reported/confirmed before the fix.
"""

from unittest.mock import patch

import pytest

from cbpos.core.models import Permission, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService

_counter = 0


@pytest.fixture
def cashier_role_with_permission(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    perm = Permission(code=f"sales.void_{suffix}")
    role = Role(name=f"Cashier_{suffix}", permissions=[perm])
    user = User(username=f"cashier_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([perm, role, user])
    db_session.commit()
    return user, perm


@pytest.fixture(autouse=True)
def _bypass_pin_hash():
    with patch.object(AuthService, "_verify_against_hash", return_value=True):
        yield


class TestVerifyPinPermissionsAreEagerLoaded:
    def test_role_permissions_accessible_after_session_closes(self, db_session, cashier_role_with_permission):
        _, perm = cashier_role_with_permission
        user = AuthService.verify_pin("0000")

        assert user is not None
        assert PermissionService.user_has_permission(user, perm.code) is True
        assert PermissionService.user_has_permission(user, "nonexistent.permission") is False


class TestLoginPermissionsAreEagerLoaded:
    def test_role_permissions_accessible_after_session_closes(self, db_session, cashier_role_with_permission):
        _, perm = cashier_role_with_permission
        user = AuthService.login("0000")

        assert user is not None
        assert PermissionService.user_has_permission(user, perm.code) is True
        assert PermissionService.user_has_permission(user, "nonexistent.permission") is False
