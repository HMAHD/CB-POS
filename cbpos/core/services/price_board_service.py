"""Price Board service for fast daily price updates (#931)."""

import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import AuditLog, Product, Role, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.inventory_service import StaleProductError
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.utils.money import round_money
from cbpos.core.utils.terminal_guard import require_catalog_writable

logger = logging.getLogger(__name__)


class PriceBoardItem:
    """Detached data representation of a price board product row."""

    def __init__(
        self,
        id: int,
        barcode: str,
        name_en: str,
        name_si: str | None,
        name_ta: str | None,
        current_price: Decimal,
        version_id: int,
    ):
        self.id = id
        self.barcode = barcode
        self.name_en = name_en
        self.name_si = name_si
        self.name_ta = name_ta
        self.current_price = current_price
        self.version_id = version_id

    def get_display_name(self, lang: str | None = None) -> str:
        """Return localized product name with English fallback."""
        if lang is None:
            try:
                from cbpos.i18n import get_language

                lang = get_language()
            except Exception:
                lang = "en"
        if lang == "si" and self.name_si:
            return self.name_si
        if lang == "ta" and self.name_ta:
            return self.name_ta
        return self.name_en or ""

    def to_dict(self) -> dict[str, Any]:
        """Convert item attributes to dictionary."""
        return {
            "id": self.id,
            "barcode": self.barcode,
            "name_en": self.name_en,
            "name_si": self.name_si,
            "name_ta": self.name_ta,
            "current_price": self.current_price,
            "version_id": self.version_id,
        }


class PriceBoardService:
    """Service providing catalog queries and atomic batch updates for daily price board."""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def get_price_board_items(self) -> list[PriceBoardItem]:
        """Fetch all active products flagged with price_changes_often=True.

        Returns detached PriceBoardItem instances safe for crossing Qt thread boundaries.
        """
        with self.db.get_session() as session:
            stmt = (
                select(Product)
                .where(
                    Product.is_active.is_(True),
                    Product.price_changes_often.is_(True),
                )
                .order_by(Product.name_en)
            )
            products = session.scalars(stmt).all()
            return [
                PriceBoardItem(
                    id=p.id,
                    barcode=p.barcode,
                    name_en=p.name_en,
                    name_si=p.name_si,
                    name_ta=p.name_ta,
                    current_price=p.price,
                    version_id=p.version_id,
                )
                for p in products
            ]

    def batch_update_prices(
        self,
        updates: list[dict[str, Any]],
        acting_user_id: int,
        terminal_id: str | None = None,
    ) -> list[int]:
        """Atomically update product prices for a batch of products.

        Requirements:
        - require_catalog_writable(): fails closed on till terminals.
        - Permission check: acting_user_id must have Permissions.PRICING_MANAGE.
        - Validation: prices must be non-negative Decimal rounded to 2 places.
        - Optimistic locking: all expected_version_id values must match current database state.
          If ANY product is stale, raises StaleProductError and rolls back the entire batch.
        - Audit: creates one PRICE_CHANGE audit log per actual price change.
        - Atomicity: commits once in a single transaction; rolls back completely on any failure.
        - Returns list of product IDs whose prices were actually changed.
        """
        require_catalog_writable()

        if not updates:
            return []

        # Validate format & parse prices before opening transaction
        parsed_updates: list[tuple[int, int, Decimal]] = []
        seen_ids: set[int] = set()
        for item in updates:
            prod_id = item.get("product_id")
            if not isinstance(prod_id, int):
                raise ValueError(f"Invalid product_id: {prod_id}")
            if prod_id in seen_ids:
                raise ValueError(f"Duplicate product_id in batch update: {prod_id}")
            seen_ids.add(prod_id)

            expected_version = item.get("expected_version_id")
            if not isinstance(expected_version, int):
                raise ValueError(f"Invalid expected_version_id: {expected_version}")

            raw_price = item.get("new_price")
            try:
                new_price = round_money(Decimal(str(raw_price)))
            except (InvalidOperation, TypeError, ValueError) as e:
                raise ValueError(f"Invalid price value for product {prod_id}: {raw_price}") from e

            if new_price < Decimal("0"):
                raise ValueError(f"Price cannot be negative for product {prod_id}: {new_price}")

            parsed_updates.append((prod_id, expected_version, new_price))

        effective_terminal_id = terminal_id or ConfigService.get("terminal_id") or "TERM-01"

        with self.db.get_session() as session:
            # 1. Check user permission
            user = session.get(
                User,
                acting_user_id,
                options=[joinedload(User.role).joinedload(Role.permissions)],
            )
            if not user or not PermissionService.user_has_permission(user, Permissions.PRICING_MANAGE):
                raise PermissionError(f"Permission denied: {Permissions.PRICING_MANAGE} required")

            # 2. Fetch all products and validate optimistic lock BEFORE applying any change
            product_ids = [p_id for p_id, _, _ in parsed_updates]
            stmt = select(Product).where(Product.id.in_(product_ids))
            products_by_id = {p.id: p for p in session.scalars(stmt).all()}

            for prod_id, expected_version, _ in parsed_updates:
                product = products_by_id.get(prod_id)
                if not product or not product.is_active:
                    raise ValueError(f"Product {prod_id} not found or inactive")
                if product.version_id != expected_version:
                    raise StaleProductError(
                        f"Product '{product.name_en}' was modified by another user. Please reload and try again."
                    )

            # 3. Apply changes and record audit logs
            changed_product_ids: list[int] = []
            now = datetime.now()

            for prod_id, _, new_price in parsed_updates:
                product = products_by_id[prod_id]
                old_price = product.price

                if old_price == new_price:
                    continue  # No actual change, skip mutation & audit

                product.price = new_price
                product.last_modified = now

                audit_details = {
                    "subject": product.name_en,
                    "product_id": product.id,
                    "barcode": product.barcode,
                    "changes": {
                        "price": {
                            "old": str(old_price),
                            "new": str(new_price),
                        }
                    },
                }

                audit = AuditLog(
                    user_id=acting_user_id,
                    action="PRICE_CHANGE",
                    event_type="INVENTORY",
                    terminal_id=effective_terminal_id,
                    details=json.dumps(audit_details, ensure_ascii=False),
                )
                session.add(audit)
                changed_product_ids.append(product.id)

            # 4. Commit transaction
            session.commit()
            return changed_product_ids
