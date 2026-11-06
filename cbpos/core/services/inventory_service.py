import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import StaleDataError

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import MovementType
from cbpos.core.database import Database
from cbpos.core.models import AuditLog, CompositeItem, InventoryLog, Product, Role, StockMovement, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.logging_service import LoggingService, diff_changes
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.stock_service import StockService
from cbpos.core.utils.terminal_guard import require_catalog_writable

logger = logging.getLogger(__name__)


class InventoryService:
    """Manages product records, composite (bundle) items, and stock-level adjustments."""

    # GS1 keeps EAN-13 prefixes 20-29 for in-store numbers, so a generated
    # barcode can never clash with a manufacturer's. 29 stays clear of the
    # usual weighing-scale prefixes (20-28).
    IN_STORE_BARCODE_PREFIX = "29"

    def __init__(self):
        """Bind this service instance to the database singleton."""
        self.db = Database()

    @staticmethod
    def _ean13(body: str) -> str:
        """Return the 12-digit ``body`` with its EAN-13 check digit appended."""
        odd = sum(int(d) for d in body[0::2])
        even = sum(int(d) for d in body[1::2])
        return body + str((10 - (odd + even * 3) % 10) % 10)

    def _in_store_barcode(self, session, product_id: int) -> str:
        """Return an unused in-store EAN-13 for a product, numbered from its id."""
        n = product_id
        while True:
            candidate = self._ean13(f"{self.IN_STORE_BARCODE_PREFIX}{n:010d}")
            if session.scalar(select(Product.id).where(Product.barcode == candidate)) is None:
                return candidate
            n += 1

    def create_product(self, data: dict[str, Any]) -> Product:
        """Create a new product with optional composite items."""
        require_catalog_writable()
        with self.db.get_session() as session:
            # Extract composite items data if present
            components_data = data.pop("components", [])

            # "Auto-Generate Barcodes" (Settings -> System, #641): a new
            # product saved without a barcode gets one. The real number is
            # built from the id, so hold a unique placeholder until flush.
            generate_barcode = not data.get("barcode") and ConfigService.get("auto_generate_barcodes")
            if generate_barcode:
                data["barcode"] = f"PENDING-{uuid.uuid4().hex}"

            product = Product(**data)
            session.add(product)
            session.flush()  # Generate ID

            if generate_barcode:
                product.barcode = self._in_store_barcode(session, product.id)
                session.flush()

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
        """Update an existing product; a selling price change goes to the Activity Log (#642)."""
        require_catalog_writable()
        with self.db.get_session() as session:
            product = session.get(Product, product_id)
            if not product:
                return None

            if data.get("price") is not None:
                price_change = diff_changes({"price": product.price}, {"price": Decimal(str(data["price"]))})
                LoggingService.add_change(session, "PRODUCT_PRICE_CHANGE", "INVENTORY", product.name_en, price_change)

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
        require_catalog_writable()
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

    def adjust_stock(
        self,
        product_id: int,
        qty_change: Decimal,
        reason: str,
        user_id: int,
        note: str | None = None,
    ) -> StockMovement:
        """Adjust stock quantity via StockService and record in InventoryLog & AuditLog (#794).

        Args:
            product_id: The product to adjust.
            qty_change: Signed quantity delta (+/-). Must not be zero.
            reason: Reason code (DAMAGED, EXPIRED, THEFT, FOUND, CORRECTION, OTHER).
            user_id: ID of the user performing the adjustment.
            note: Optional note (mandatory when reason is OTHER).

        Returns:
            The created StockMovement.

        Raises:
            PermissionError: If user lacks inventory.stock_adjust permission.
            ValueError: On invalid quantity, service item, or missing note for OTHER.
        """
        if isinstance(user_id, str) and (note is None or isinstance(note, int)):
            note, user_id = user_id, note

        if qty_change == 0 or qty_change == Decimal("0"):
            raise ValueError("Quantity change cannot be zero")

        clean_reason = str(reason).strip()
        clean_note = (note or "").strip()
        if clean_reason.upper() == "OTHER" and not clean_note:
            raise ValueError("A note is required when reason is 'OTHER'")

        with self.db.get_session() as session:
            # 1. Check user permission
            user = session.get(User, user_id, options=[joinedload(User.role).joinedload(Role.permissions)])
            if not user or not PermissionService.user_has_permission(user, Permissions.INVENTORY_STOCK_ADJUST):
                raise PermissionError("Permission denied: inventory.stock_adjust required")

            # 2. Check product
            product = session.get(Product, product_id)
            if not product:
                raise ValueError(f"Product {product_id} not found")

            if product.is_service:
                raise ValueError("Cannot adjust stock for service products")

            # 3. Record movement via StockService (updates product.stock_qty and enforces negative stock)
            movement = StockService.record_movement(
                product_id=product.id,
                qty_change=qty_change,
                movement_type=MovementType.ADJUSTMENT,
                user_id=user_id,
                session=session,
            )

            # 4. Record InventoryLog
            log_reason = f"{clean_reason}: {clean_note}" if clean_note else clean_reason
            inv_log = InventoryLog(
                product_id=product.id,
                qty_change=qty_change,
                new_qty=product.stock_qty,
                reason=log_reason,
                user_id=user_id,
            )
            session.add(inv_log)

            # 5. Record AuditLog
            audit_details = (
                f"Product {product.name_en} ({product.barcode}) stock adjusted by {qty_change}. "
                f"Reason: {clean_reason}{f' - {clean_note}' if clean_note else ''}. "
                f"New stock: {product.stock_qty}"
            )
            audit_log = AuditLog(
                user_id=user_id,
                action="STOCK_ADJUSTMENT",
                event_type="INVENTORY",
                details=audit_details,
            )
            session.add(audit_log)

            try:
                session.commit()
            except StaleDataError:
                session.rollback()
                raise ValueError("This product's stock was modified by another user. Please reload and try again.")

            return movement

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
