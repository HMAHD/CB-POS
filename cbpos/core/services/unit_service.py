"""
Service for managing units of measurement.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import Role, Unit, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.utils.terminal_guard import require_catalog_writable

logger = logging.getLogger(__name__)


def _require_inventory_edit(session, acting_user_id: int | None) -> None:
    effective_actor_id = acting_user_id
    if effective_actor_id is None:
        curr = AuthService.get_current_user()
        if curr:
            effective_actor_id = curr.id

    if effective_actor_id is not None:
        user = session.get(User, effective_actor_id, options=[joinedload(User.role).joinedload(Role.permissions)])
        if not user or not PermissionService.user_has_permission(user, Permissions.INVENTORY_EDIT):
            raise PermissionError("Permission denied: inventory.edit required")


class UnitService:
    """CRUD operations for units of measurement."""

    @staticmethod
    def get_all(active_only: bool = True) -> list[Unit]:
        """Get all units, optionally filtering active only."""
        db = Database()
        with db.get_session() as session:
            stmt = select(Unit).order_by(Unit.name)
            if active_only:
                stmt = stmt.where(Unit.is_active.is_(True))
            results = list(session.scalars(stmt).all())
            for u in results:
                session.expunge(u)
            return results

    @staticmethod
    def get_by_id(unit_id: int) -> Unit | None:
        """Get a single unit by ID."""
        db = Database()
        with db.get_session() as session:
            unit = session.get(Unit, unit_id)
            if unit:
                session.expunge(unit)
            return unit

    @staticmethod
    def create(name: str, abbreviation: str, decimal_places: int = 0, acting_user_id: int | None = None) -> Unit:
        """Create a new unit."""
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            _require_inventory_edit(session, acting_user_id)
            existing = session.query(Unit).filter(Unit.name == name).first()
            if existing:
                raise ValueError(f"Unit '{name}' already exists.")

            unit = Unit(
                name=name,
                abbreviation=abbreviation,
                decimal_places=decimal_places,
            )
            session.add(unit)
            session.flush()
            session.expunge(unit)
            return unit

    @staticmethod
    def update(
        unit_id: int,
        name: str,
        abbreviation: str,
        decimal_places: int,
        acting_user_id: int | None = None,
    ) -> Unit:
        """Update an existing unit."""
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            _require_inventory_edit(session, acting_user_id)
            unit = session.get(Unit, unit_id)
            if not unit:
                raise ValueError(f"Unit ID {unit_id} not found.")

            # Check name uniqueness (excluding self)
            dup = session.query(Unit).filter(Unit.name == name, Unit.id != unit_id).first()
            if dup:
                raise ValueError(f"Unit '{name}' already exists.")

            unit.name = name
            unit.abbreviation = abbreviation
            unit.decimal_places = decimal_places
            session.flush()
            session.expunge(unit)
            return unit

    @staticmethod
    def delete(unit_id: int, acting_user_id: int | None = None) -> None:
        """Deactivate a unit (soft delete). Prevents deletion if products use it."""
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            _require_inventory_edit(session, acting_user_id)
            unit = session.get(Unit, unit_id)
            if not unit:
                raise ValueError(f"Unit ID {unit_id} not found.")

            # Check if any products use this unit
            from cbpos.core.models import Product

            product_count = session.query(Product).filter(Product.unit_id == unit_id).count()
            if product_count > 0:
                raise ValueError(f"Cannot delete: {product_count} product(s) use this unit.")

            unit.is_active = False
