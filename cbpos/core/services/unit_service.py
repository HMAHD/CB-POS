"""
Service for managing units of measurement.
"""

import logging
from typing import List, Optional
from sqlalchemy import select
from cbpos.core.database import Database
from cbpos.core.models import Unit

logger = logging.getLogger(__name__)


class UnitService:
    """CRUD operations for units of measurement."""

    @staticmethod
    def get_all(active_only: bool = True) -> List[Unit]:
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
    def get_by_id(unit_id: int) -> Optional[Unit]:
        """Get a single unit by ID."""
        db = Database()
        with db.get_session() as session:
            unit = session.query(Unit).get(unit_id)
            if unit:
                session.expunge(unit)
            return unit

    @staticmethod
    def create(name: str, abbreviation: str, decimal_places: int = 0) -> Unit:
        """Create a new unit."""
        db = Database()
        with db.get_session() as session:
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
    def update(unit_id: int, name: str, abbreviation: str, decimal_places: int) -> Unit:
        """Update an existing unit."""
        db = Database()
        with db.get_session() as session:
            unit = session.query(Unit).get(unit_id)
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
    def delete(unit_id: int) -> None:
        """Deactivate a unit (soft delete). Prevents deletion if products use it."""
        db = Database()
        with db.get_session() as session:
            unit = session.query(Unit).get(unit_id)
            if not unit:
                raise ValueError(f"Unit ID {unit_id} not found.")

            # Check if any products use this unit
            from cbpos.core.models import Product

            product_count = session.query(Product).filter(Product.unit_id == unit_id).count()
            if product_count > 0:
                raise ValueError(f"Cannot delete: {product_count} product(s) use this unit.")

            unit.is_active = False
