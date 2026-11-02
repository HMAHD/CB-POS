"""Price list management service.

Handles price list entities, custom item prices, bulk price adjustment calculations,
rounding rules, and price modification auditing (#544, #642).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from types import EllipsisType

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session, selectinload

from cbpos.core.constants.audit import PRICE_LIST_BULK_ADJUST, PRICING_EVENT
from cbpos.core.database import Database
from cbpos.core.models import PriceList, PriceListItem, Product
from cbpos.core.services.logging_service import LoggingService, diff_changes, snapshot_changes
from cbpos.core.utils.terminal_guard import require_catalog_writable


@dataclass(slots=True)
class BulkAdjustmentRule:
    """Parameters for a bulk price adjustment operation (#544)."""

    rule_type: str  # "PERCENTAGE_OFF", "FIXED_OFF", "FIXED_MARKUP", "MARGIN_OVER_COST"
    value: Decimal  # Discount/markup percentage or rupee amount
    rounding: str = "EXACT"  # "EXACT", "NEAREST_1", "NEAREST_5", "CHARM_99"
    scope: str = "ALL"  # "SELECTED", "CATEGORY", "ALL"
    category_id: int | None = None
    product_ids: list[int] | None = None


@dataclass(slots=True)
class BulkPreviewItem:
    """One candidate product row in the bulk adjustment preview table (#544)."""

    product_id: int
    product_name: str
    category_name: str
    cost: Decimal
    base_price: Decimal
    old_list_price: Decimal | None
    new_list_price: Decimal
    margin_percent: Decimal | None
    is_below_cost: bool
    loss_amount: Decimal


def round_price(val: Decimal, mode: str) -> Decimal:
    """Round a calculated price according to the specified rounding rule (#544)."""
    val = max(Decimal("0.00"), val)
    if mode == "NEAREST_1":
        return val.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(Decimal("0.01"))
    elif mode == "NEAREST_5":
        divided = (val / Decimal("5")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return (divided * Decimal("5")).quantize(Decimal("0.01"))
    elif mode == "CHARM_99":
        int_part = int(val)
        return (Decimal(int_part) + Decimal("0.99")).quantize(Decimal("0.01"))
    else:  # "EXACT"
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def live_price_list_condition(now: datetime) -> ColumnElement[bool]:
    """SQL condition for a price list that is switched on and inside its date range at ``now``.

    Shared by checkout pricing and :meth:`PriceListService.get_active_lists` so both agree;
    :meth:`PriceListService.get_status` is the in-memory mirror of the same rule.
    """
    return and_(
        PriceList.is_active.is_(True),
        or_(PriceList.start_date.is_(None), PriceList.start_date <= now),
        or_(PriceList.end_date.is_(None), PriceList.end_date >= now),
    )


def _list_fields(price_list: PriceList) -> dict:
    """The audited fields of a price list."""
    return {
        "name": price_list.name,
        "start_date": price_list.start_date,
        "end_date": price_list.end_date,
        "is_active": price_list.is_active,
    }


class PriceListService:
    """Manages price lists (e.g. wholesale, promotional) and their per-product price overrides.

    Every create, update, on/off switch and delete of a list or a list price is written to the
    Activity Log in the same transaction (#642).
    """

    def __init__(self):
        """Bind this service instance to the database singleton."""
        self.db = Database()

    def create_price_list(
        self,
        name: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        is_active: bool = True,
    ) -> PriceList:
        """Create a new price list, optionally date-scoped; pass is_active=False to create it switched off."""
        require_catalog_writable()
        with self.db.get_session() as session:
            price_list = PriceList(name=name, start_date=start_date, end_date=end_date, is_active=is_active)
            session.add(price_list)
            # No dates means "no limit" and lists usually start on: only note what was actually set
            created = {k: v for k, v in _list_fields(price_list).items() if v is not None and v is not True}
            LoggingService.add_change(session, "PRICE_LIST_CREATE", PRICING_EVENT, name, snapshot_changes(created))
            session.commit()
            session.refresh(price_list)
            session.expunge(price_list)
            return price_list

    def update_price_list(
        self,
        list_id: int,
        name: str | None = None,
        start_date: datetime | EllipsisType | None = ...,
        end_date: datetime | EllipsisType | None = ...,
        is_active: bool | None = None,
    ) -> PriceList:
        """Update a price list's name, validity dates and/or on/off switch.

        Args:
            list_id: ID of the price list to update.
            name: New name (if provided).
            start_date: New start date, or None to clear. Omit (``...``) to leave unchanged.
            end_date: New end date, or None to clear. Omit (``...``) to leave unchanged.
            is_active: Switch the list on/off for checkout (if provided).

        Returns:
            The updated PriceList.

        Raises:
            ValueError: If the price list isn't found, the name is empty,
                or another price list already has that name.
        """
        require_catalog_writable()
        with self.db.get_session() as session:
            price_list = session.get(PriceList, list_id)
            if not price_list:
                raise ValueError(f"Price list with ID {list_id} not found.")
            before = _list_fields(price_list)

            if name is not None:
                name = name.strip()
                if not name:
                    raise ValueError("Price list name is required.")
                if name != price_list.name:
                    dup = session.query(PriceList).filter(PriceList.name == name, PriceList.id != list_id).first()
                    if dup:
                        raise ValueError(f"Price list '{name}' already exists.")
                    price_list.name = name

            if start_date is not ...:
                price_list.start_date = start_date
            if end_date is not ...:
                price_list.end_date = end_date
            if is_active is not None:
                price_list.is_active = is_active

            changes = diff_changes(before, _list_fields(price_list))
            action = "PRICE_LIST_TOGGLE" if changes.keys() == {"is_active"} else "PRICE_LIST_UPDATE"
            LoggingService.add_change(session, action, PRICING_EVENT, before["name"], changes)

            session.commit()
            session.refresh(price_list)
            session.expunge(price_list)
            return price_list

    def get_all_lists(self) -> list[PriceList]:
        """Return every price list, active or not, ordered by id."""
        with self.db.get_session() as session:
            stmt = select(PriceList).order_by(PriceList.id)
            lists = list(session.scalars(stmt).all())
            for pl in lists:
                session.expunge(pl)
            return lists

    def get_active_lists(self) -> list[PriceList]:
        """Return price lists that are active and currently within their validity window."""
        now = datetime.now()
        with self.db.get_session() as session:
            stmt = select(PriceList).where(live_price_list_condition(now))
            lists = list(session.scalars(stmt).all())
            for pl in lists:
                session.expunge(pl)
            return lists

    @staticmethod
    def get_status(price_list: PriceList, now: datetime | None = None) -> str:
        """Classify a price list the same way checkout does (see ``live_price_list_condition``).

        Args:
            price_list: The price list to classify.
            now: Moment to evaluate at; defaults to the current time.

        Returns:
            One of ``"disabled"``, ``"expired"``, ``"upcoming"`` or ``"active"``.
        """
        now = now or datetime.now()
        if not price_list.is_active:
            return "disabled"
        if price_list.end_date and price_list.end_date < now:
            return "expired"
        if price_list.start_date and price_list.start_date > now:
            return "upcoming"
        return "active"

    def set_item_price(self, list_id: int, product_id: int, price: Decimal) -> PriceListItem:
        """Create or update a product's price override on a price list (upsert)."""
        require_catalog_writable()
        with self.db.get_session() as session:
            # Check if exists
            stmt = select(PriceListItem).where(
                PriceListItem.price_list_id == list_id,
                PriceListItem.product_id == product_id,
            )
            item = session.scalar(stmt)
            old_price = item.price if item else None

            if item:
                item.price = price
            else:
                item = PriceListItem(price_list_id=list_id, product_id=product_id, price=price)
                session.add(item)

            self._log_item_price(session, "PRICE_LIST_PRICE_SET", list_id, product_id, old_price, price)
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def delete_item_price(self, list_id: int, product_id: int) -> None:
        """Remove a product's price override from a price list.

        Args:
            list_id: ID of the price list.
            product_id: ID of the product whose override should be removed.

        Raises:
            ValueError: If no override exists for this product on this list.
        """
        require_catalog_writable()
        with self.db.get_session() as session:
            stmt = select(PriceListItem).where(
                PriceListItem.price_list_id == list_id,
                PriceListItem.product_id == product_id,
            )
            item = session.scalar(stmt)
            if not item:
                raise ValueError(f"No price override found for product {product_id} on this list.")
            self._log_item_price(session, "PRICE_LIST_PRICE_REMOVE", list_id, product_id, item.price, None)
            session.delete(item)
            session.commit()

    def delete_price_list(self, list_id: int) -> None:
        """Delete a price list and all its items.

        Args:
            list_id: The ID of the price list to delete.

        Raises:
            ValueError: If the price list does not exist.
        """
        require_catalog_writable()
        with self.db.get_session() as session:
            price_list = session.get(PriceList, list_id)
            if not price_list:
                raise ValueError(f"Price list with ID {list_id} not found.")
            # Delete associated items first
            item_count = session.query(PriceListItem).filter(PriceListItem.price_list_id == list_id).delete()
            gone = {k: v for k, v in _list_fields(price_list).items() if v is not None and k != "is_active"}
            gone["item_count"] = item_count
            LoggingService.add_change(
                session, "PRICE_LIST_DELETE", PRICING_EVENT, price_list.name, snapshot_changes(gone, deleted=True)
            )
            session.delete(price_list)
            session.commit()

    @staticmethod
    def _log_item_price(
        session: Session, action: str, list_id: int, product_id: int, old: Decimal | None, new: Decimal | None
    ) -> None:
        """Activity Log row for one list price: "<list> / <product>: price old -> new".

        Writes nothing when the price didn't really change.

        Args:
            session: Open DB session; the row commits with the caller's change.
            action: Audit action, e.g. "PRICE_LIST_PRICE_SET".
            list_id: ID of the price list.
            product_id: ID of the product whose list price changed.
            old: Price before the change (None when newly added).
            new: Price after the change (None when removed).

        Returns:
            None.
        """
        changes = diff_changes({"price": old}, {"price": new})
        if not changes:
            return
        price_list = session.get(PriceList, list_id)
        product = session.get(Product, product_id)
        LoggingService.add_change(
            session,
            action,
            PRICING_EVENT,
            price_list.name if price_list else f"#{list_id}",
            changes,
            item=product.name_en if product else f"#{product_id}",
        )

    def get_items(self, list_id: int) -> list[PriceListItem]:
        """Return a price list's product overrides, with each item's product eager-loaded."""
        with self.db.get_session() as session:
            stmt = (
                select(PriceListItem).where(PriceListItem.price_list_id == list_id).join(PriceListItem.product)
            )  # Ensure product is loaded if needed, though scalars might not load rels by default without options

            # We might want to eager load product to show names
            from sqlalchemy.orm import selectinload

            stmt = stmt.options(selectinload(PriceListItem.product))

            items = list(session.scalars(stmt).all())
            for item in items:
                session.expunge(item)
            return items

    def calculate_preview(self, list_id: int, rule: BulkAdjustmentRule) -> list[BulkPreviewItem]:
        """Compute candidate bulk-adjusted prices without modifying database records (#544).

        Args:
            list_id: Target price list ID.
            rule: Parameters specifying rule type, value, rounding, and scope.

        Returns:
            A list of BulkPreviewItem detailing old vs new prices, margins, and below-cost flags.
        """
        with self.db.get_session() as session:
            # 1. Fetch existing list items for this list
            existing_overrides = {
                item.product_id: item.price
                for item in session.scalars(select(PriceListItem).where(PriceListItem.price_list_id == list_id)).all()
            }

            # 2. Select target products based on scope
            stmt = select(Product).where(Product.is_active.is_(True))
            if rule.scope == "SELECTED" and rule.product_ids:
                stmt = stmt.where(Product.id.in_(rule.product_ids))
            elif rule.scope == "CATEGORY" and rule.category_id:
                stmt = stmt.where(Product.category_id == rule.category_id)

            stmt = stmt.options(selectinload(Product.category)).order_by(Product.name_en)
            products = session.scalars(stmt).all()

            preview_items: list[BulkPreviewItem] = []
            for product in products:
                base_price = Decimal(str(product.price or 0))
                cost = Decimal(str(product.cost or 0))

                # Compute unrounded new price
                if rule.rule_type == "PERCENTAGE_OFF":
                    discount_factor = Decimal("1") - (rule.value / Decimal("100"))
                    raw_new_price = base_price * discount_factor
                elif rule.rule_type == "FIXED_OFF":
                    raw_new_price = base_price - rule.value
                elif rule.rule_type == "FIXED_MARKUP":
                    raw_new_price = base_price + rule.value
                elif rule.rule_type == "MARGIN_OVER_COST":
                    if cost > Decimal("0.00"):
                        raw_new_price = cost * (Decimal("1") + (rule.value / Decimal("100")))
                    else:
                        raw_new_price = base_price
                else:
                    raw_new_price = base_price

                # Round and clamp
                new_price = round_price(raw_new_price, rule.rounding)

                # Margin and below-cost calculations
                if cost > Decimal("0.00"):
                    margin_pct = ((new_price - cost) / cost * Decimal("100")).quantize(
                        Decimal("0.1"), rounding=ROUND_HALF_UP
                    )
                    is_below_cost = new_price < cost
                    loss_amount = max(Decimal("0.00"), cost - new_price) if is_below_cost else Decimal("0.00")
                else:
                    margin_pct = None
                    is_below_cost = False
                    loss_amount = Decimal("0.00")

                cat_name = product.category.name if product.category else ""
                old_override = existing_overrides.get(product.id)

                preview_items.append(
                    BulkPreviewItem(
                        product_id=product.id,
                        product_name=product.name_en,
                        category_name=cat_name,
                        cost=cost,
                        base_price=base_price,
                        old_list_price=old_override,
                        new_list_price=new_price,
                        margin_percent=margin_pct,
                        is_below_cost=is_below_cost,
                        loss_amount=loss_amount,
                    )
                )

            return preview_items

    def apply_bulk_adjust(self, list_id: int, items: list[BulkPreviewItem], rule_summary: str) -> int:
        """Apply candidate bulk-adjusted prices in a single atomic transaction (#544).

        Updates existing overrides or creates new ones. Writes exactly one
        consolidated entry to the Activity Log and updates the list's last_modified.

        Args:
            list_id: Target price list ID.
            items: The candidate items to save (as returned by calculate_preview).
            rule_summary: Human-readable summary of the rule applied (for audit details).

        Returns:
            The number of items updated.

        Raises:
            ValueError: If the price list is not found.
        """
        require_catalog_writable()
        if not items:
            return 0

        with self.db.get_session() as session:
            price_list = session.get(PriceList, list_id)
            if not price_list:
                raise ValueError(f"Price list with ID {list_id} not found.")

            # Load all existing PriceListItem rows for this list
            existing_items_map = {
                item.product_id: item
                for item in session.scalars(select(PriceListItem).where(PriceListItem.price_list_id == list_id)).all()
            }

            below_cost_count = 0
            for preview_item in items:
                if preview_item.is_below_cost:
                    below_cost_count += 1

                existing = existing_items_map.get(preview_item.product_id)
                if existing:
                    existing.price = preview_item.new_list_price
                else:
                    new_item = PriceListItem(
                        price_list_id=list_id,
                        product_id=preview_item.product_id,
                        price=preview_item.new_list_price,
                    )
                    session.add(new_item)

            price_list.last_modified = datetime.now()

            # Record single consolidated Activity Log entry (#544)
            log_details = snapshot_changes(
                {
                    "items_updated": len(items),
                    "rule": rule_summary,
                    "below_cost_count": below_cost_count,
                }
            )
            LoggingService.add_change(
                session,
                PRICE_LIST_BULK_ADJUST,
                PRICING_EVENT,
                price_list.name,
                log_details,
            )

            session.commit()
            return len(items)
