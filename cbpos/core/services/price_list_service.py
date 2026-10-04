from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, and_, or_, select

from cbpos.core.database import Database
from cbpos.core.models import PriceList, PriceListItem


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


class PriceListService:
    """Manages price lists (e.g. wholesale, promotional) and their per-product price overrides."""

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
        with self.db.get_session() as session:
            price_list = PriceList(name=name, start_date=start_date, end_date=end_date, is_active=is_active)
            session.add(price_list)
            session.commit()
            session.refresh(price_list)
            session.expunge(price_list)
            return price_list

    def update_price_list(
        self,
        list_id: int,
        name: str | None = None,
        start_date: object = ...,
        end_date: object = ...,
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
        with self.db.get_session() as session:
            price_list = session.get(PriceList, list_id)
            if not price_list:
                raise ValueError(f"Price list with ID {list_id} not found.")

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
        with self.db.get_session() as session:
            # Check if exists
            stmt = select(PriceListItem).where(
                PriceListItem.price_list_id == list_id,
                PriceListItem.product_id == product_id,
            )
            item = session.scalar(stmt)

            if item:
                item.price = price
            else:
                item = PriceListItem(price_list_id=list_id, product_id=product_id, price=price)
                session.add(item)

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
        with self.db.get_session() as session:
            stmt = select(PriceListItem).where(
                PriceListItem.price_list_id == list_id,
                PriceListItem.product_id == product_id,
            )
            item = session.scalar(stmt)
            if not item:
                raise ValueError(f"No price override found for product {product_id} on this list.")
            session.delete(item)
            session.commit()

    def delete_price_list(self, list_id: int) -> None:
        """Delete a price list and all its items.

        Args:
            list_id: The ID of the price list to delete.

        Raises:
            ValueError: If the price list does not exist.
        """
        with self.db.get_session() as session:
            price_list = session.get(PriceList, list_id)
            if not price_list:
                raise ValueError(f"Price list with ID {list_id} not found.")
            # Delete associated items first
            session.query(PriceListItem).filter(PriceListItem.price_list_id == list_id).delete()
            session.delete(price_list)
            session.commit()

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
