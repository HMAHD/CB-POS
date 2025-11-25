from typing import Optional, List, Dict, Any
from sqlalchemy.orm import joinedload
from cbpos.core.database import Database
from cbpos.core.models import Product


class ProductService:
    """
    Service to handle product lookups and inventory queries.
    """

    @staticmethod
    def get_by_barcode(barcode: str) -> Optional[Product]:
        """
        Retrieve a product by its exact barcode.
        """
        db = Database()
        with db.get_session() as session:
            product = session.query(Product).filter(Product.barcode == barcode).first()
            if product:
                session.expunge(product)  # Detach from session
                return product
        return None

    @staticmethod
    def search_products(query: str) -> List[Product]:
        """
        Search for products by name or barcode (alias for search, but can be expanded).
        """
        if not query:
            # Return all (or top 100)
            db = Database()
            with db.get_session() as session:
                products = (
                    session.query(Product)
                    .options(joinedload(Product.category))
                    .limit(100)
                    .all()
                )
                session.expunge_all()
                return products

        db = Database()
        with db.get_session() as session:
            products = (
                session.query(Product)
                .options(joinedload(Product.category))
                .filter(
                    (Product.name_en.ilike(f"%{query}%"))
                    | (Product.barcode.ilike(f"%{query}%"))
                )
                .limit(50)
                .all()
            )

            session.expunge_all()
            return products

    @staticmethod
    def search(query: str) -> List[Product]:
        """
        Search for products by name (case-insensitive partial match).
        """
        return ProductService.search_products(query)

    @staticmethod
    def get_components(product_id: int) -> List[Dict[str, Any]]:
        """Get components for a composite product."""
        from cbpos.core.models import CompositeItem

        db = Database()
        with db.get_session() as session:
            components = (
                session.query(CompositeItem)
                .filter(CompositeItem.parent_product_id == product_id)
                .all()
            )
            result = []
            for comp in components:
                result.append({"product": comp.child, "qty": comp.qty})
            return result
