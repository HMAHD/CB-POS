import logging
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select

from cbpos.core.constants.permissions import (
    ADMIN_ROLE_NAME,
    CRITICAL_ADMIN_PERMISSIONS,
    MANAGEMENT_TAB_PERMISSIONS,
    SETTINGS_PAGE_PERMISSIONS,
)
from cbpos.core.models import User
from cbpos.core.services.auth_service import AuthService

logger = logging.getLogger(__name__)


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
        if not user:
            return False

        try:
            role = getattr(user, "role", None)
            if not role:
                return False

            # Admin has all permissions
            if getattr(role, "name", None) == ADMIN_ROLE_NAME:
                return True

            return any(perm.code == permission_code for perm in getattr(role, "permissions", None) or [])
        except Exception:
            # Handle detached user instances gracefully
            user_id = getattr(user, "__dict__", {}).get("id")
            if not user_id:
                try:
                    from sqlalchemy import inspect

                    insp = inspect(user)
                    if insp and insp.identity:
                        user_id = insp.identity[0]
                except Exception:
                    pass
            if user_id:
                try:
                    from sqlalchemy.orm import joinedload

                    from cbpos.core.database import Database
                    from cbpos.core.models import Role

                    db = Database()
                    with db.get_session() as session:
                        fresh_user = (
                            session.query(User)
                            .options(joinedload(User.role).joinedload(Role.permissions))
                            .filter(User.id == user_id)
                            .first()
                        )
                        if fresh_user and fresh_user.role:
                            if fresh_user.role.name == ADMIN_ROLE_NAME:
                                return True
                            return any(perm.code == permission_code for perm in fresh_user.role.permissions or [])
                except Exception as inner_exc:
                    logger.debug("Failed to reload detached user %s: %s", user_id, inner_exc)
            return False

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
    def update_role_permissions(
        role_id: int,
        permission_ids: list[int],
        acting_user_id: int | None = None,
    ) -> bool:
        """Update permissions for a role.

        SAFETY:
        - Prevents revoking critical permissions from Admin.
        - Non-Admin cannot edit the Admin role.
        - Non-Admin cannot edit their own role.
        - Non-Admin cannot grant permissions they do not possess themselves.
        """
        from cbpos.core.utils.terminal_guard import require_catalog_writable

        require_catalog_writable()
        from cbpos.core.database import Database
        from cbpos.core.models import AuditLog, Permission, Role, User

        db = Database()
        with db.get_session() as session:
            role = session.get(Role, role_id)
            if not role:
                return False

            # Non-Admin restrictions apply when an acting user is provided
            if acting_user_id is not None:
                admin_role = session.execute(select(Role).where(Role.name == ADMIN_ROLE_NAME)).scalar_one_or_none()
                actor = session.get(User, acting_user_id)
                actor_is_admin = bool(actor and admin_role and actor.role_id == admin_role.id)
                if not actor_is_admin:
                    if role.name == ADMIN_ROLE_NAME:
                        raise ValueError("only_admin_can_modify_admin_role")
                    if actor and role.id == actor.role_id:
                        raise ValueError("cannot_edit_own_role")

                    actor_perm_ids = {p.id for p in actor.role.permissions} if (actor and actor.role) else set()
                    for pid in permission_ids:
                        if pid not in actor_perm_ids:
                            raise ValueError("cannot_grant_unheld_permission")

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

            logger_id = acting_user_id
            if logger_id is None:
                curr = AuthService.get_current_user()
                if curr:
                    logger_id = curr.id
            if logger_id is not None:
                log = AuditLog(
                    user_id=logger_id,
                    action="UPDATE_PERMISSIONS",
                    event_type="SECURITY",
                    details=f"Updated permissions for role '{role.name}' ({len(new_perms)} permission(s) granted).",
                )
                session.add(log)

            session.commit()
            return True
