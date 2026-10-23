"""
Service for managing product categories.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import Category

logger = logging.getLogger(__name__)


class CategoryService:
    """CRUD operations for product categories."""

    @staticmethod
    def get_all(active_only: bool = True) -> list[Category]:
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
    def get_tree() -> list[Category]:
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
    def get_by_id(category_id: int) -> Category | None:
        """Get a single category by ID.

        Args:
            category_id: ID of the category.

        Returns:
            The Category, or None if not found.
        """
        db = Database()
        with db.get_session() as session:
            category = session.get(Category, category_id)
            if category:
                session.expunge(category)
            return category

    @staticmethod
    def get_top_level_with_subcategories() -> list[Category]:
        """Get root categories with subcategories eagerly loaded, ordered by name.

        Returns:
            List of top-level categories with subcategories loaded.
        """
        db = Database()
        with db.get_session() as session:
            stmt = (
                select(Category)
                .options(joinedload(Category.subcategories))
                .where(Category.parent_id.is_(None))
                .order_by(Category.name)
            )
            results = list(session.execute(stmt).unique().scalars().all())
            for cat in results:
                for sub in cat.subcategories:
                    session.expunge(sub)
                session.expunge(cat)
            return results

    @staticmethod
    def get_top_level_with_subcategories_and_products() -> list[Category]:
        """Get root categories with subcategories and products eagerly loaded.

        Used by CategoryManagerDialog for product counts.

        Returns:
            List of top-level categories with subcategories and products loaded.
        """
        db = Database()
        with db.get_session() as session:
            stmt = (
                select(Category)
                .options(
                    joinedload(Category.subcategories).joinedload(Category.products),
                    joinedload(Category.products),
                )
                .where(Category.parent_id.is_(None))
                .order_by(Category.name)
            )
            results = list(session.execute(stmt).unique().scalars().all())
            for cat in results:
                for sub in cat.subcategories:
                    session.expunge(sub)
                session.expunge(cat)
            return results

    @staticmethod
    def get_descendant_ids(category_id: int) -> set[int]:
        """Get all descendant category IDs (not including the given ID).

        Args:
            category_id: ID of the root category.

        Returns:
            Set of all descendant category IDs.
        """
        db = Database()
        with db.get_session() as session:
            # Build children map
            all_cats = session.execute(select(Category.id, Category.parent_id)).all()
            children_map: dict[int | None, list[int]] = {}
            for cid, pid in all_cats:
                children_map.setdefault(pid, []).append(cid)

            # BFS
            result: set[int] = set()
            queue = list(children_map.get(category_id, []))
            while queue:
                current = queue.pop(0)
                result.add(current)
                queue.extend(children_map.get(current, []))
            return result

    @staticmethod
    def get_product_count_for_ids(category_ids: set[int]) -> int:
        """Count products with category_id in the given set.

        Args:
            category_ids: Set of category IDs to check.

        Returns:
            Number of products in those categories.
        """
        if not category_ids:
            return 0

        from sqlalchemy import func

        from cbpos.core.models import Product

        db = Database()
        with db.get_session() as session:
            count = session.execute(
                select(func.count(Product.id)).where(Product.category_id.in_(category_ids))
            ).scalar()
            return count or 0

    @staticmethod
    def delete_with_descendants(category_id: int) -> None:
        """Delete a category and all its descendants (deepest first).

        Args:
            category_id: ID of the category to delete.

        Raises:
            ValueError: If category not found.
        """
        db = Database()
        with db.get_session() as session:
            category = session.get(Category, category_id)
            if not category:
                raise ValueError(f"Category ID {category_id} not found.")

            # Collect all IDs including self
            all_cats = session.execute(select(Category.id, Category.parent_id)).all()
            children_map: dict[int | None, list[int]] = {}
            for cid, pid in all_cats:
                children_map.setdefault(pid, []).append(cid)

            # BFS to get all descendant IDs
            all_ids = {category_id}
            queue = list(children_map.get(category_id, []))
            while queue:
                current = queue.pop(0)
                all_ids.add(current)
                queue.extend(children_map.get(current, []))

            # Delete deepest first
            cats = list(session.scalars(select(Category).where(Category.id.in_(all_ids))).all())
            cats_by_id = {c.id: c for c in cats}
            for cid in sorted(all_ids, reverse=True):
                cat = cats_by_id.get(cid)
                if cat:
                    session.delete(cat)

    @staticmethod
    def create(name: str, parent_id: int | None = None, color: str | None = None) -> Category:
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
    def update(
        category_id: int,
        name: str | None = None,
        color: str | None = None,
        parent_id: object = ...,
    ) -> Category:
        """Update an existing category.

        Args:
            category_id: ID of the category to update.
            name: New name (if provided).
            color: New color hex string (if provided).
            parent_id: New parent ID. Use None for root, omit (``...``) to leave unchanged.

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

            if parent_id is not ...:
                category.parent_id = parent_id

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
    def reparent(category_id: int, new_parent_id: int | None) -> Category:
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
