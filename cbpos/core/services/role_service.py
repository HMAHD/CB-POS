"""
Service for managing user roles (CRUD).

Reading roles (``UserService.get_all_roles``) and assigning them to users
already existed; this adds the missing create/rename/delete operations
themselves, with guards protecting the built-in Admin role and any role
still assigned to a user.
"""

import logging

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.database import Database
from cbpos.core.models import Role, User
from cbpos.core.utils.terminal_guard import require_catalog_writable

logger = logging.getLogger(__name__)


class RoleService:
    """CRUD operations for roles."""

    @staticmethod
    def create(name: str) -> Role:
        """Create a new role.

        Args:
            name: Role name.

        Returns:
            The newly created Role.

        Raises:
            ValueError: If the name is empty or a role with that name already exists.
        """
        require_catalog_writable()
        name = (name or "").strip()
        if not name:
            raise ValueError("Role name is required.")

        db = Database()
        with db.get_session() as session:
            existing = session.query(Role).filter(Role.name == name).first()
            if existing:
                raise ValueError(f"Role '{name}' already exists.")

            role = Role(name=name, access_level=0)
            session.add(role)
            session.flush()
            session.expunge(role)
            return role

    @staticmethod
    def update(role_id: int, name: str) -> Role:
        """Rename an existing role.

        Args:
            role_id: ID of the role to rename.
            name: New name.

        Returns:
            The updated Role.

        Raises:
            ValueError: If the role isn't found, the name is empty, the
                role is the built-in Admin role, or another role already
                has that name.
        """
        require_catalog_writable()
        name = (name or "").strip()
        if not name:
            raise ValueError("Role name is required.")

        db = Database()
        with db.get_session() as session:
            role = session.get(Role, role_id)
            if not role:
                raise ValueError(f"Role ID {role_id} not found.")

            if role.name == ADMIN_ROLE_NAME and name != ADMIN_ROLE_NAME:
                raise ValueError("The built-in Admin role cannot be renamed.")

            if name != role.name:
                dup = session.query(Role).filter(Role.name == name, Role.id != role_id).first()
                if dup:
                    raise ValueError(f"Role '{name}' already exists.")
                role.name = name

            session.flush()
            session.expunge(role)
            return role

    @staticmethod
    def get_user_count_for_role(role_id: int) -> int:
        """Count users currently assigned to a role.

        Args:
            role_id: ID of the role to check.

        Returns:
            Number of users with this role.
        """
        db = Database()
        with db.get_session() as session:
            return session.query(User).filter(User.role_id == role_id).count()

    @staticmethod
    def delete(role_id: int) -> None:
        """Delete a role.

        Args:
            role_id: ID of the role to delete.

        Raises:
            ValueError: If the role isn't found, is the built-in Admin
                role, or is still assigned to at least one user.
        """
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            role = session.get(Role, role_id)
            if not role:
                raise ValueError(f"Role ID {role_id} not found.")

            if role.name == ADMIN_ROLE_NAME:
                raise ValueError("The built-in Admin role cannot be deleted.")

            user_count = session.query(User).filter(User.role_id == role_id).count()
            if user_count > 0:
                raise ValueError(f"Cannot delete: {user_count} user(s) have this role.")

            session.delete(role)
