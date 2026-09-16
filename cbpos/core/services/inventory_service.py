import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from cbpos.core.database import Database
from cbpos.core.models import AuditLog, CompositeItem, InventoryLog, Product

logger = logging.getLogger(__name__)


class InventoryService:
    def __init__(self):
        self.db = Database()

    def create_product(self, data: dict[str, Any]) -> Product:
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

    def update_product(self, product_id: int, data: dict[str, Any]) -> Product | None:
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

            try:
                session.commit()
            except StaleDataError:
                session.rollback()
                raise ValueError("This product was modified by another user. Please reload and try again.")
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

    def get_low_stock_items(self) -> list[Product]:
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
                event_type="INVENTORY",
                details=(
                    f"Product {product.name_en} ({product.barcode}) stock adjusted by {qty_change}. Reason: {reason}"
                ),
            )
            session.add(audit_log)

            try:
                session.commit()
            except StaleDataError:
                session.rollback()
                raise ValueError("This product's stock was modified by another user. Please reload and try again.")
            return True

    def get_composite_items(self, product_id: int) -> list[dict[str, Any]]:
        """Get composite (bundle) child items for a product."""
        with self.db.get_session() as session:
            stmt = select(CompositeItem).where(CompositeItem.parent_product_id == product_id)
            components = session.scalars(stmt).all()
            result = []
            for comp in components:
                child = session.get(Product, comp.child_product_id)
                result.append(
                    {
                        "child_product_id": comp.child_product_id,
                        "child_name": child.name_en if child else "Unknown",
                        "qty": comp.qty,
                    }
                )
            return result

    def get_all_products(self, limit: int = 1000, offset: int = 0) -> list[Product]:
        """Get active products with categories, with pagination support."""
        with self.db.get_session() as session:
            stmt = (
                select(Product).where(Product.is_active.is_(True)).order_by(Product.name_en).limit(limit).offset(offset)
            )
            return list(session.scalars(stmt).all())

    def count_active_products(self) -> int:
        """Get count of active products for pagination."""
        from sqlalchemy import func

        with self.db.get_session() as session:
            stmt = select(func.count()).select_from(Product).where(Product.is_active.is_(True))
            return session.scalar(stmt) or 0

    def get_product_by_barcode(self, barcode: str) -> Product | None:
        """Get a single product by its barcode."""
        with self.db.get_session() as session:
            stmt = select(Product).where(Product.barcode == barcode)
            return session.scalars(stmt).first()
