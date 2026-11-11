"""
Enhanced Product Search Service with Multiple Search Modes.
Provides ALL, BARCODE, CODE, and NAME search capabilities.
"""

import logging
from typing import Any, overload

from sqlalchemy import and_, func, or_, select

from cbpos.core.database import Database
from cbpos.core.models import Product
from cbpos.core.utils.formatters import escape_like

logger = logging.getLogger(__name__)


def build_product_search_filter(query: str):
    """Build the shared WHERE clause matching barcode, English, Sinhala, and Tamil names (#863)."""
    pattern = f"%{escape_like(query.strip())}%"
    return or_(
        Product.barcode.like(pattern),
        func.lower(Product.name_en).like(func.lower(pattern)),
        func.lower(Product.name_si).like(func.lower(pattern)),
        func.lower(Product.name_ta).like(func.lower(pattern)),
    )


class ProductService:
    """Enhanced product search with multiple search modes."""

    SEARCH_MODE_ALL = "ALL"
    SEARCH_MODE_BARCODE = "BARCODE"
    SEARCH_MODE_CODE = "CODE"
    SEARCH_MODE_NAME = "NAME"

    @staticmethod
    def is_stock_tracked(product: Product) -> bool:
        """Check if a specific product instance is stock-tracked (not a service or bundle)."""
        return not bool(product.is_service) and not bool(product.is_composite)

    @overload
    @staticmethod
    def stock_tracked(product: None = None) -> Any: ...

    @overload
    @staticmethod
    def stock_tracked(product: Product) -> bool: ...

    @staticmethod
    def stock_tracked(product: Product | None = None) -> Any:
        """SQLAlchemy criteria or boolean check matching stock-tracked products (#909).

        Excludes service items (is_service=True) and composite bundles (is_composite=True).
        """
        if product is not None:
            return ProductService.is_stock_tracked(product)
        return and_(
            or_(Product.is_service.is_(False), Product.is_service.is_(None)),
            or_(Product.is_composite.is_(False), Product.is_composite.is_(None)),
        )

    @staticmethod
    def display_name(product: Any, lang: str | None = None) -> str:
        """Return the localized product name according to the specified language (#805).

        Picks name_si for 'si', name_ta for 'ta', falling back to name_en when
        empty or when lang is 'en' (or unsupported). If product is None, returns "".
        """
        if product is None:
            return ""
        if hasattr(product, "get_display_name"):
            return product.get_display_name(lang)
        lang = (lang or "en").lower()
        if lang == "si":
            name = (getattr(product, "name_si", None) or "").strip()
            if name:
                return name
        elif lang == "ta":
            name = (getattr(product, "name_ta", None) or "").strip()
            if name:
                return name
        name_en = (getattr(product, "name_en", None) or "").strip()
        if name_en:
            return name_en
        return (
            (getattr(product, "name_si", None) or "").strip()
            or (getattr(product, "name_ta", None) or "").strip()
            or getattr(product, "name", "")
            or ""
        )

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
                stmt = (
                    select(Product)
                    .where(
                        build_product_search_filter(query),
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
