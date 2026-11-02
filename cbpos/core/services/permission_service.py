from collections.abc import Iterable
from datetime import datetime

from cbpos.core.constants.permissions import (
    ADMIN_ROLE_NAME,
    CRITICAL_ADMIN_PERMISSIONS,
    MANAGEMENT_TAB_PERMISSIONS,
    SETTINGS_PAGE_PERMISSIONS,
)
from cbpos.core.models import User
from cbpos.core.services.auth_service import AuthService


class PermissionService:
    """
    Service to handle permission checks.
    """

    @staticmethod
    def user_has_permission(user: User, permission_code: str) -> bool:
        """
        Check if the user has a specific permission.

        Args:
            user (User): The user to check.
            permission_code (str): The code of the permission (e.g., 'can_void_sale').

        Returns:
            bool: True if authorized, False otherwise.
        """
        if not user or not user.role:
            return False

        # Admin has all permissions
        if user.role.name == ADMIN_ROLE_NAME:
            return True

        return any(perm.code == permission_code for perm in getattr(user.role, "permissions", None) or [])

    @staticmethod
    def user_has_any_permission(user: User, permission_codes: Iterable[str]) -> bool:
        """True if the user has at least one of ``permission_codes`` (see ``user_has_permission``)."""
        return any(PermissionService.user_has_permission(user, code) for code in permission_codes)

    @staticmethod
    def management_tabs(user: User) -> set[str]:
        """Names of the Management tabs this user may see (keys of ``MANAGEMENT_TAB_PERMISSIONS``)."""
        return {
            tab
            for tab, codes in MANAGEMENT_TAB_PERMISSIONS.items()
            if PermissionService.user_has_any_permission(user, codes)
        }

    @staticmethod
    def settings_pages(user: User) -> set[str]:
        """Names of the Settings pages this user may see (keys of ``SETTINGS_PAGE_PERMISSIONS``)."""
        return {
            page
            for page, codes in SETTINGS_PAGE_PERMISSIONS.items()
            if PermissionService.user_has_any_permission(user, codes)
        }

    @staticmethod
    def can_open_management(user: User) -> bool:
        """Whether the side menu offers Management: only if the user would see a tab in it (#549, #728)."""
        return bool(PermissionService.management_tabs(user))

    @staticmethod
    def can_open_settings(user: User) -> bool:
        """Whether the side menu offers Settings: only if the user would see a page in it (#549, #728)."""
        return bool(PermissionService.settings_pages(user))

    @staticmethod
    def get_all_permissions():
        """Get all available permissions."""
        from cbpos.core.database import Database
        from cbpos.core.models import Permission

        db = Database()
        with db.get_session() as session:
            permissions = session.query(Permission).all()
            session.expunge_all()
            return permissions

    @staticmethod
    def update_role_permissions(role_id: int, permission_ids: list[int]):
        """
        Update permissions for a role.

        SAFETY: Prevents revoking critical permissions from Admin.
        """
        from cbpos.core.utils.terminal_guard import require_catalog_writable

        require_catalog_writable()
        from cbpos.core.database import Database
        from cbpos.core.models import AuditLog, Permission, Role

        db = Database()
        with db.get_session() as session:
            role = session.get(Role, role_id)
            if not role:
                return False

            # Fetch new permissions
            new_perms = session.query(Permission).filter(Permission.id.in_(permission_ids)).all()

            # --- SAFETY CHECK: ADMIN LOCKOUT PREVENTION ---
            if role.name == ADMIN_ROLE_NAME:
                critical_codes = CRITICAL_ADMIN_PERMISSIONS

                # Get IDs of critical permissions
                critical_perms = session.query(Permission).filter(Permission.code.in_(critical_codes)).all()

                # Add them to new_perms if not already there
                current_ids = {p.id for p in new_perms}
                for cp in critical_perms:
                    if cp.id not in current_ids:
                        new_perms.append(cp)
            # ----------------------------------------------

            role.permissions = new_perms
            role.last_modified = datetime.now()

            current_user = AuthService.get_current_user()
            if current_user is not None:
                log = AuditLog(
                    user_id=current_user.id,
                    action="UPDATE_PERMISSIONS",
                    event_type="SECURITY",
                    details=f"Updated permissions for role '{role.name}' ({len(new_perms)} permission(s) granted).",
                )
                session.add(log)

            session.commit()
            return True
