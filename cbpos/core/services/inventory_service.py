import json
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from cbpos.core.constants.audit import WARRANTY_EVENT
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


class StaleProductError(ValueError):
    """Raised when an update is attempted against a stale product snapshot (#862)."""


@dataclass
class ProductFilter:
    """Filter criteria for product catalog listing (#863)."""

    category_id: int | None = None
    is_active: bool | None = True
    low_stock: bool | None = None


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

    def get_product(self, product_id: int) -> Product | None:
        """Get product by ID from fresh database session (#862)."""
        with self.db.get_session() as session:
            product = session.get(Product, product_id)
            if product:
                session.expunge(product)
            return product

    def create_product(
        self,
        data: dict[str, Any],
        user_id: int | None = None,
        session: Session | None = None,
    ) -> Product:
        """Create a new product with optional composite items and opening stock (#862)."""
        require_catalog_writable()
        if session is not None:
            return self._create_product_in_session(session, data, user_id, auto_commit=False)
        with self.db.get_session() as s:
            return self._create_product_in_session(s, data, user_id, auto_commit=True)

    def _create_product_in_session(
        self,
        session: Session,
        data: dict[str, Any],
        user_id: int | None,
        auto_commit: bool,
    ) -> Product:
        # Extract composite items data if present
        components_data = data.pop("components", [])

        # Extract opening stock if present (#862)
        opening_stock = Decimal(str(data.pop("stock_qty", 0) or 0))

        # "Auto-Generate Barcodes" (Settings -> System, #641): a new
        # product saved without a barcode gets one. The real number is
        # built from the id, so hold a unique placeholder until flush.
        generate_barcode = not data.get("barcode") and ConfigService.get("auto_generate_barcodes")
        if generate_barcode:
            data["barcode"] = f"PENDING-{uuid.uuid4().hex}"

        # Opening stock is initialized to 0 on model, then recorded via StockService
        data["stock_qty"] = Decimal("0")

        # Validate warranty assignment and enforce warranty.edit if specified
        warr_actor_id = None
        override = data.get("warranty_override")
        policy_id = data.get("warranty_policy_id")
        if (override is not None and override != "INHERIT") or policy_id is not None:
            from cbpos.core.services.warranty_service import WarrantyService

            warr_actor_id = WarrantyService._resolve_actor(user_id, Permissions.WARRANTY_EDIT)
            WarrantyService.validate_warranty_assignment(
                override=override or "INHERIT",
                policy_id=policy_id,
                is_weighted=bool(data.get("is_weighted")),
                session=session,
            )

        product = Product(**data)
        session.add(product)
        session.flush()  # Generate ID

        if warr_actor_id is not None:
            audit = AuditLog(
                user_id=warr_actor_id,
                action="PRODUCT_WARRANTY_ASSIGNMENT",
                event_type=WARRANTY_EVENT,
                details=json.dumps(
                    {
                        "product_id": product.id,
                        "override": product.warranty_override,
                        "policy_id": product.warranty_policy_id,
                    }
                ),
            )
            session.add(audit)
            session.flush()

        if generate_barcode:
            product.barcode = self._in_store_barcode(session, product.id)
            session.flush()

        # Record opening stock movement if provided on non-service item
        if opening_stock > 0 and not product.is_service:
            uid = user_id
            if uid is None:
                from cbpos.core.services.auth_service import AuthService

                curr = AuthService.get_current_user()
                uid = curr.id if curr else 1

            StockService.record_movement(
                product_id=product.id,
                qty_change=opening_stock,
                movement_type=MovementType.OPENING,
                user_id=uid,
                session=session,
            )

        # Handle composite items
        for comp_data in components_data:
            child_id = comp_data.get("child_product_id")
            qty = comp_data.get("qty")
            if child_id and qty:
                composite = CompositeItem(parent_product_id=product.id, child_product_id=child_id, qty=qty)
                session.add(composite)

        if auto_commit:
            session.commit()
            session.refresh(product)
        else:
            session.flush()
        return product

    def update_product(
        self,
        product_id: int,
        data: dict[str, Any],
        expected_version: int | None = None,
        user_id: int | None = None,
    ) -> Product | None:
        """Update an existing product; rejects stale updates and ignores stock/cost (#862)."""
        require_catalog_writable()

        # #862: Stock and cost must never be overwritten via product editor
        data.pop("stock_qty", None)
        data.pop("cost", None)

        with self.db.get_session() as session:
            product = session.get(Product, product_id)
            if not product:
                return None

            if expected_version is not None and product.version_id != expected_version:
                raise StaleProductError("This product was modified by another user. Please reload and try again.")

            warr_actor_id = None
            override_in_data = "warranty_override" in data
            policy_in_data = "warranty_policy_id" in data
            new_override = data.get("warranty_override") if override_in_data else product.warranty_override
            new_policy_id = data.get("warranty_policy_id") if policy_in_data else product.warranty_policy_id

            override_changed = override_in_data and new_override != product.warranty_override
            policy_changed = policy_in_data and new_policy_id != product.warranty_policy_id

            if override_changed or policy_changed:
                effective_override = new_override or "INHERIT"
                effective_policy_id = new_policy_id
                effective_weighted = data.get("is_weighted", product.is_weighted)

                from cbpos.core.services.warranty_service import WarrantyService

                warr_actor_id = WarrantyService._resolve_actor(user_id, Permissions.WARRANTY_EDIT)
                WarrantyService.validate_warranty_assignment(
                    override=effective_override,
                    policy_id=effective_policy_id,
                    is_weighted=bool(effective_weighted),
                    existing_policy_id=product.warranty_policy_id,
                    session=session,
                )

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

            if warr_actor_id is not None:
                audit = AuditLog(
                    user_id=warr_actor_id,
                    action="PRODUCT_WARRANTY_ASSIGNMENT",
                    event_type=WARRANTY_EVENT,
                    details=json.dumps(
                        {
                            "product_id": product.id,
                            "override": product.warranty_override,
                            "policy_id": product.warranty_policy_id,
                        }
                    ),
                )
                session.add(audit)

            try:
                session.commit()
            except StaleDataError:
                session.rollback()
                raise StaleProductError("This product was modified by another user. Please reload and try again.")
            session.refresh(product)
            return product

    def set_cost(self, product_id: int, new_cost: Decimal, user_id: int) -> Product:
        """Manually override a product's cost (requires inventory.set_cost permission) (#862)."""
        require_catalog_writable()
        if new_cost < Decimal("0"):
            raise ValueError("Cost cannot be negative")

        with self.db.get_session() as session:
            user = session.get(User, user_id, options=[joinedload(User.role).joinedload(Role.permissions)])
            if not user or not PermissionService.user_has_permission(user, Permissions.INVENTORY_SET_COST):
                raise PermissionError("Permission denied: inventory.set_cost required")

            product = session.get(Product, product_id)
            if not product:
                raise ValueError(f"Product {product_id} not found")

            old_cost = product.cost
            product.cost = new_cost

            audit_log = AuditLog(
                user_id=user_id,
                action="COST_OVERRIDE",
                event_type="INVENTORY",
                details=f"Product {product.name_en} ({product.barcode}) cost overridden from {old_cost} to {new_cost}",
            )
            session.add(audit_log)
            session.commit()
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
        """Get products where stock is at or below reorder level (excluding services & bundles #909)."""
        from cbpos.core.services.product_service import ProductService

        with self.db.get_session() as session:
            stmt = select(Product).where(
                Product.is_active.is_(True),
                ProductService.stock_tracked(),
                Product.stock_qty <= Product.reorder_point,
            )
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

    def list_products(
        self,
        query: str | None = None,
        filters: ProductFilter | dict | None = None,
        page: int = 0,
        page_size: int = 100,
    ) -> tuple[list[Product], int]:
        """List products with server-side search, filtering, and pagination (#863).

        Args:
            query: Optional search term matching barcode, English, Sinhala, or Tamil name.
            filters: Optional ProductFilter or dict (category_id, is_active, low_stock).
            page: 0-based page number.
            page_size: Number of items per page.

        Returns:
            tuple[list[Product], int]: (page of detached products, total matching count).
        """
        from sqlalchemy import and_, func

        from cbpos.core.services.product_service import build_product_search_filter

        conditions = []
        if query and query.strip():
            conditions.append(build_product_search_filter(query.strip()))

        if isinstance(filters, dict):
            category_id = filters.get("category_id")
            is_active = filters.get("is_active", True)
            low_stock = filters.get("low_stock")
        elif isinstance(filters, ProductFilter):
            category_id = filters.category_id
            is_active = filters.is_active
            low_stock = filters.low_stock
        else:
            category_id = None
            is_active = True
            low_stock = None

        if is_active is not None:
            conditions.append(Product.is_active.is_(is_active))
        if category_id is not None:
            conditions.append(Product.category_id == category_id)
        if low_stock:
            from cbpos.core.services.product_service import ProductService

            conditions.append(Product.stock_qty <= Product.reorder_point)
            conditions.append(ProductService.stock_tracked())

        page_num = max(0, page)
        offset = page_num * page_size

        with self.db.get_session() as session:
            count_stmt = select(func.count()).select_from(Product)
            if conditions:
                count_stmt = count_stmt.where(and_(*conditions))
            total_count = session.scalar(count_stmt) or 0

            data_stmt = select(Product).options(joinedload(Product.category), joinedload(Product.unit))
            if conditions:
                data_stmt = data_stmt.where(and_(*conditions))
            data_stmt = data_stmt.order_by(Product.name_en, Product.id).offset(offset).limit(page_size)
            items = list(session.scalars(data_stmt).unique().all())
            for item in items:
                session.expunge(item)
            return items, total_count
