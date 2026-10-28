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
