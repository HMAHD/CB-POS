import logging
from typing import List, Optional, Dict, Any
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from cbpos.core.database import Database
from cbpos.core.models import Product, InventoryLog, AuditLog, CompositeItem

logger = logging.getLogger(__name__)


class InventoryService:
    def __init__(self):
        self.db = Database()

    def create_product(self, data: Dict[str, Any]) -> Product:
        """Create a new product with optional composite items."""
        with self.db.get_session() as session:
            # Extract composite items data if present
            components_data = data.pop("components", [])

            product = Product(**data)
            session.add(product)
            session.flush()  # Generate ID

            # Handle composite items
            for comp_data in components_data:
                child_id = comp_data.get("child_product_id")
                qty = comp_data.get("qty")
                if child_id and qty:
                    composite = CompositeItem(parent_product_id=product.id, child_product_id=child_id, qty=qty)
                    session.add(composite)

            session.commit()
            session.refresh(product)
            return product

    def update_product(self, product_id: int, data: Dict[str, Any]) -> Optional[Product]:
        """Update an existing product."""
        with self.db.get_session() as session:
            product = session.get(Product, product_id)
            if not product:
                return None

            # Extract composite items data if present
            components_data = data.pop("components", None)

            for key, value in data.items():
                if hasattr(product, key):
                    setattr(product, key, value)

            if components_data is not None:
                # Clear existing components
                session.query(CompositeItem).filter(CompositeItem.parent_product_id == product.id).delete()
                # Add new components
                for comp_data in components_data:
                    child_id = comp_data.get("child_product_id")
                    qty = comp_data.get("qty")
                    if child_id and qty:
                        composite = CompositeItem(
                            parent_product_id=product.id,
                            child_product_id=child_id,
                            qty=qty,
                        )
                        session.add(composite)

            session.commit()
            session.refresh(product)
            return product

    def delete_product(self, product_id: int) -> bool:
        """Soft-delete a product by marking it inactive."""
        with self.db.get_session() as session:
            product = session.get(Product, product_id)
            if not product:
                return False

            product.is_active = False
            session.commit()
            return True

    def get_low_stock_items(self) -> List[Product]:
        """Get products where stock is at or below reorder level."""
        with self.db.get_session() as session:
            stmt = select(Product).where(Product.is_active.is_(True), Product.stock_qty <= Product.reorder_level)
            return list(session.scalars(stmt).all())

    def adjust_stock(self, product_id: int, qty_change: Decimal, reason: str, user_id: int) -> bool:
        """Adjust stock quantity and record in audit log."""
        with self.db.get_session() as session:
            product = session.get(Product, product_id)
            if not product:
                return False

            old_qty = product.stock_qty
            new_qty = old_qty + qty_change
            product.stock_qty = new_qty

            # Log to InventoryLog
            inv_log = InventoryLog(
                product_id=product.id,
                qty_change=qty_change,
                new_qty=new_qty,
                reason=reason,
                user_id=user_id,
            )
            session.add(inv_log)

            # Log to AuditLog (as requested)
            audit_log = AuditLog(
                user_id=user_id,
                action="STOCK_ADJUSTMENT",
                details=(
                    f"Product {product.name_en} ({product.barcode}) "
                    f"stock adjusted by {qty_change}. Reason: {reason}"
                ),
            )
            session.add(audit_log)

            session.commit()
            return True

    def get_all_products(self) -> List[Product]:
        """Get all active products with categories."""
        with self.db.get_session() as session:
            stmt = select(Product).options(joinedload(Product.category)).where(Product.is_active.is_(True))
            return list(session.scalars(stmt).all())

    def get_product_by_barcode(self, barcode: str) -> Optional[Product]:
        """Get a single product by its barcode."""
        with self.db.get_session() as session:
            stmt = select(Product).options(joinedload(Product.category)).where(Product.barcode == barcode)
            return session.scalars(stmt).first()
