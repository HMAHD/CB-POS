"""
Service for managing product categories.
"""

import logging
from typing import List, Optional

from sqlalchemy import select

from cbpos.core.database import Database
from cbpos.core.models import Category

logger = logging.getLogger(__name__)


class CategoryService:
    """CRUD operations for product categories."""

    @staticmethod
    def get_all(active_only: bool = True) -> List[Category]:
        """Get all categories, ordered by name.

        Args:
            active_only: Currently unused (categories have no is_active flag),
                         kept for API consistency.

        Returns:
            List of all categories.
        """
        db = Database()
        with db.get_session() as session:
            stmt = select(Category).order_by(Category.name)
            results = list(session.scalars(stmt).all())
            for cat in results:
                session.expunge(cat)
            return results

    @staticmethod
    def get_tree() -> List[Category]:
        """Get all categories for tree building (includes parent_id info).

        Returns:
            List of all categories with id, name, parent_id, color loaded.
        """
        db = Database()
        with db.get_session() as session:
            stmt = select(Category).order_by(Category.parent_id.nulls_first(), Category.name)
            results = list(session.scalars(stmt).all())
            for cat in results:
                session.expunge(cat)
            return results

    @staticmethod
    def create(name: str, parent_id: Optional[int] = None, color: Optional[str] = None) -> Category:
        """Create a new category.

        Args:
            name: Category name.
            parent_id: Optional parent category ID for subcategories.
            color: Optional hex color string (e.g. '#FF0000').

        Returns:
            The newly created Category.

        Raises:
            ValueError: If a category with the same name already exists.
        """
        db = Database()
        with db.get_session() as session:
            existing = session.query(Category).filter(Category.name == name).first()
            if existing:
                raise ValueError(f"Category '{name}' already exists.")

            category = Category(
                name=name,
                parent_id=parent_id,
                color=color or "#FFFFFF",
            )
            session.add(category)
            session.flush()
            session.expunge(category)
            return category

    @staticmethod
    def update(category_id: int, name: Optional[str] = None, color: Optional[str] = None) -> Category:
        """Update an existing category.

        Args:
            category_id: ID of the category to update.
            name: New name (if provided).
            color: New color hex string (if provided).

        Returns:
            The updated Category.

        Raises:
            ValueError: If category not found or duplicate name.
        """
        db = Database()
        with db.get_session() as session:
            category = session.get(Category, category_id)
            if not category:
                raise ValueError(f"Category ID {category_id} not found.")

            if name is not None:
                # Check uniqueness excluding self
                dup = session.query(Category).filter(Category.name == name, Category.id != category_id).first()
                if dup:
                    raise ValueError(f"Category '{name}' already exists.")
                category.name = name

            if color is not None:
                category.color = color

            session.flush()
            session.expunge(category)
            return category

    @staticmethod
    def delete(category_id: int) -> None:
        """Delete a category. Checks for products first.

        Args:
            category_id: ID of the category to delete.

        Raises:
            ValueError: If category not found or has products assigned.
        """
        db = Database()
        with db.get_session() as session:
            category = session.get(Category, category_id)
            if not category:
                raise ValueError(f"Category ID {category_id} not found.")

            from cbpos.core.models import Product

            product_count = session.query(Product).filter(Product.category_id == category_id).count()
            if product_count > 0:
                raise ValueError(f"Cannot delete: {product_count} product(s) use this category.")

            session.delete(category)

    @staticmethod
    def reparent(category_id: int, new_parent_id: Optional[int]) -> Category:
        """Move a category under a new parent.

        Args:
            category_id: ID of the category to move.
            new_parent_id: ID of the new parent, or None for root.

        Returns:
            The updated Category.

        Raises:
            ValueError: If category or parent not found, or circular reference.
        """
        db = Database()
        with db.get_session() as session:
            category = session.get(Category, category_id)
            if not category:
                raise ValueError(f"Category ID {category_id} not found.")

            if new_parent_id is not None:
                parent = session.get(Category, new_parent_id)
                if not parent:
                    raise ValueError(f"Parent category ID {new_parent_id} not found.")

                # Prevent circular reference
                if new_parent_id == category_id:
                    raise ValueError("A category cannot be its own parent.")

            category.parent_id = new_parent_id
            session.flush()
            session.expunge(category)
            return category
