"""
Enhanced Product Search Service with Multiple Search Modes.
Provides ALL, BARCODE, CODE, and NAME search capabilities.
"""

from typing import List
from sqlalchemy import select, or_, func
from cbpos.core.models import Product
from cbpos.core.database import Database


class ProductService:
    """Enhanced product search with multiple search modes."""

    SEARCH_MODE_ALL = "ALL"
    SEARCH_MODE_BARCODE = "BARCODE"
    SEARCH_MODE_CODE = "CODE"
    SEARCH_MODE_NAME = "NAME"

    def __init__(self):
        self.db = Database()

    def search_products(
        self, query: str, mode: str = "ALL", limit: int = 50
    ) -> List[Product]:
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
            # Add joinedload to eager load category
            from sqlalchemy.orm import joinedload

            if mode == self.SEARCH_MODE_BARCODE:
                # Exact barcode match
                stmt = (
                    select(Product)
                    .options(joinedload(Product.category))
                    .where(Product.barcode == query, Product.is_active)
                )

            elif mode == self.SEARCH_MODE_CODE:
                # Match on product ID or internal reference
                if query.isdigit():
                    stmt = (
                        select(Product)
                        .options(joinedload(Product.category))
                        .where(Product.id == int(query), Product.is_active)
                    )
                else:
                    return []

            elif mode == self.SEARCH_MODE_NAME:
                # Fuzzy name search (EN, SI, TA)
                pattern = f"%{query}%"
                stmt = (
                    select(Product)
                    .options(joinedload(Product.category))
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
                # Search barcode OR any name field
                pattern = f"%{query}%"
                stmt = (
                    select(Product)
                    .options(joinedload(Product.category))
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

            return list(session.scalars(stmt).all())

    def get_all_products(self) -> List[Product]:
        """Get all active products."""
        with self.db.get_session() as session:
            stmt = select(Product).where(Product.is_active).order_by(Product.name_en)
            return list(session.scalars(stmt).all())

    def get_top_products(self, limit: int = 100) -> List[str]:
        """Get top N product names for autocomplete."""
        with self.db.get_session() as session:
            stmt = select(Product.name_en).where(Product.is_active).limit(limit)
            return [name for name in session.scalars(stmt).all()]

    @staticmethod
    def get_all_categories():
        """Get all categories for visual POS view."""
        from cbpos.core.models import Category

        db = Database()
        with db.get_session() as session:
            stmt = select(Category).order_by(Category.name)
            return list(session.scalars(stmt).all())

    @staticmethod
    def get_by_category(category_id: int) -> List[Product]:
        """Get all active products in a category."""
        db = Database()
        with db.get_session() as session:
            stmt = (
                select(Product)
                .where(Product.category_id == category_id, Product.is_active)
                .order_by(Product.name_en)
            )
            return list(session.scalars(stmt).all())

    @staticmethod
    def get_by_barcode(barcode: str):
        """Get product by exact barcode match."""
        db = Database()
        with db.get_session() as session:
            stmt = select(Product).where(Product.barcode == barcode, Product.is_active)
            return session.scalar(stmt)

    @staticmethod
    def search(query: str, limit: int = 50) -> List[Product]:
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
            return list(session.scalars(stmt).all())

    @staticmethod
    def get_products_by_category(category_id: int) -> List[Product]:
        """Alias for get_by_category for backward compatibility."""
        return ProductService.get_by_category(category_id)
