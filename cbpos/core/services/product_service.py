"""
Enhanced Product Search Service with Multiple Search Modes.
Provides ALL, BARCODE, CODE, and NAME search capabilities.
"""

import logging

from sqlalchemy import func, or_, select

from cbpos.core.database import Database
from cbpos.core.models import Product
from cbpos.core.utils.formatters import escape_like

logger = logging.getLogger(__name__)


class ProductService:
    """Enhanced product search with multiple search modes."""

    SEARCH_MODE_ALL = "ALL"
    SEARCH_MODE_BARCODE = "BARCODE"
    SEARCH_MODE_CODE = "CODE"
    SEARCH_MODE_NAME = "NAME"

    def __init__(self):
        """Bind this service instance to the database singleton."""
        self.db = Database()

    def search_products(self, query: str, mode: str = "ALL", limit: int = 50) -> list[Product]:
        """
        Multi-mode product search.

        Args:
            query: Search term
            mode: Search mode (ALL, BARCODE, CODE, NAME)
            limit: Maximum results

        Returns:
            List of matching products
        """
        if not query.strip():
            return []

        query = query.strip()

        with self.db.get_session() as session:
            if mode == self.SEARCH_MODE_BARCODE:
                stmt = select(Product).where(Product.barcode == query, Product.is_active)

            elif mode == self.SEARCH_MODE_CODE:
                if query.isdigit():
                    stmt = select(Product).where(Product.id == int(query), Product.is_active)
                else:
                    return []

            elif mode == self.SEARCH_MODE_NAME:
                pattern = f"%{escape_like(query)}%"
                stmt = (
                    select(Product)
                    .where(
                        or_(
                            func.lower(Product.name_en).like(func.lower(pattern)),
                            func.lower(Product.name_si).like(func.lower(pattern)),
                            func.lower(Product.name_ta).like(func.lower(pattern)),
                        ),
                        Product.is_active,
                    )
                    .limit(limit)
                )

            else:  # SEARCH_MODE_ALL (default)
                pattern = f"%{escape_like(query)}%"
                stmt = (
                    select(Product)
                    .where(
                        or_(
                            Product.barcode.like(pattern),
                            func.lower(Product.name_en).like(func.lower(pattern)),
                            func.lower(Product.name_si).like(func.lower(pattern)),
                            func.lower(Product.name_ta).like(func.lower(pattern)),
                        ),
                        Product.is_active,
                    )
                    .limit(limit)
                )

            results = list(session.scalars(stmt).all())
            for p in results:
                session.expunge(p)
            return results

    def get_all_products(self) -> list[Product]:
        """Get all active products."""
        with self.db.get_session() as session:
            stmt = select(Product).where(Product.is_active).order_by(Product.name_en)
            results = list(session.scalars(stmt).unique().all())
            for p in results:
                session.expunge(p)
            return results

    def get_top_products(self, limit: int = 100) -> list[str]:
        """Get top N product names for autocomplete."""
        with self.db.get_session() as session:
            stmt = select(Product.name_en).where(Product.is_active).limit(limit)
            return list(session.scalars(stmt).all())

    @staticmethod
    def get_all_categories():
        """Get all categories for visual POS view."""
        from cbpos.core.models import Category

        db = Database()
        with db.get_session() as session:
            stmt = select(Category).order_by(Category.name)
            results = list(session.scalars(stmt).all())
            for c in results:
                session.expunge(c)
            return results

    @staticmethod
    def get_by_category(category_id: int) -> list[Product]:
        """Get all active products in a category."""
        db = Database()
        with db.get_session() as session:
            stmt = (
                select(Product).where(Product.category_id == category_id, Product.is_active).order_by(Product.name_en)
            )
            results = list(session.scalars(stmt).all())
            for p in results:
                session.expunge(p)
            return results

    @staticmethod
    def get_by_barcode(barcode: str):
        """Get product by exact barcode match."""
        db = Database()
        with db.get_session() as session:
            stmt = select(Product).where(Product.barcode == barcode, Product.is_active)
            product = session.scalar(stmt)
            if product:
                session.expunge(product)
            return product

    @staticmethod
    def search(query: str, limit: int = 50) -> list[Product]:
        """Legacy search method for backward compatibility."""
        db = Database()
        with db.get_session() as session:
            pattern = f"%{query}%"
            stmt = (
                select(Product)
                .where(
                    or_(
                        Product.barcode.like(pattern),
                        func.lower(Product.name_en).like(func.lower(pattern)),
                        func.lower(Product.name_si).like(func.lower(pattern)),
                        func.lower(Product.name_ta).like(func.lower(pattern)),
                    ),
                    Product.is_active,
                )
                .limit(limit)
            )
            results = list(session.scalars(stmt).all())
            for p in results:
                session.expunge(p)
            return results

    @staticmethod
    def get_products_by_category(category_id: int) -> list[Product]:
        """Alias for get_by_category for backward compatibility."""
        return ProductService.get_by_category(category_id)
