from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import Promotion


class PromotionService:
    """Manages time-boxed promotions (e.g. happy-hour or category discounts)."""

    def __init__(self):
        """Bind this service instance to the database singleton."""
        self.db = Database()

    @staticmethod
    def _validate_time_range(start_time: datetime, end_time: datetime) -> None:
        if end_time <= start_time:
            raise ValueError("End time must be after the start time.")

    def create_promotion(
        self,
        name: str,
        type: str,
        value: Decimal,
        start_time: datetime,
        end_time: datetime,
        days_of_week: str | None = None,
        category_id: int | None = None,
    ) -> Promotion:
        """Create a new active promotion, scoped to a category if given, else store-wide.

        Raises:
            ValueError: If end_time is not after start_time.
        """
        self._validate_time_range(start_time, end_time)
        with self.db.get_session() as session:
            promotion = Promotion(
                name=name,
                type=type,
                value=value,
                start_time=start_time,
                end_time=end_time,
                days_of_week=days_of_week,
                category_id=category_id,
                is_active=True,
            )
            session.add(promotion)
            session.commit()
            session.refresh(promotion)
            session.expunge(promotion)
            return promotion

    def update_promotion(
        self,
        promotion_id: int,
        name: str | None = None,
        type: str | None = None,
        value: Decimal | None = None,
        start_time: object = ...,
        end_time: object = ...,
        days_of_week: object = ...,
        is_active: bool | None = None,
        category_id: object = ...,
    ) -> Promotion:
        """Update a promotion's fields.

        Args:
            promotion_id: ID of the promotion to update.
            name: New name (if provided).
            type: New promotion type (if provided).
            value: New value (if provided).
            start_time: New start time. Omit (``...``) to leave unchanged.
            end_time: New end time. Omit (``...``) to leave unchanged.
            days_of_week: New days-of-week string, or None to clear. Omit (``...``) to leave unchanged.
            is_active: New active flag (if provided) -- a manual on/off switch,
                independent of whether the promotion's dates currently apply.
            category_id: New category scope, or None for store-wide. Omit (``...``) to leave unchanged.

        Returns:
            The updated Promotion.

        Raises:
            ValueError: If the promotion isn't found, the name is empty,
                or the resulting date range has the end at or before the start.
        """
        with self.db.get_session() as session:
            promotion = session.get(Promotion, promotion_id)
            if not promotion:
                raise ValueError(f"Promotion with ID {promotion_id} not found.")

            if name is not None:
                name = name.strip()
                if not name:
                    raise ValueError("Promotion name is required.")
                promotion.name = name

            if type is not None:
                promotion.type = type

            if value is not None:
                promotion.value = value

            if start_time is not ...:
                promotion.start_time = start_time
            if end_time is not ...:
                promotion.end_time = end_time

            self._validate_time_range(promotion.start_time, promotion.end_time)

            if days_of_week is not ...:
                promotion.days_of_week = days_of_week

            if is_active is not None:
                promotion.is_active = is_active

            if category_id is not ...:
                promotion.category_id = category_id

            session.commit()
            session.refresh(promotion)
            session.expunge(promotion)
            return promotion

    def delete_promotion(self, promotion_id: int) -> None:
        """Delete a promotion.

        Args:
            promotion_id: ID of the promotion to delete.

        Raises:
            ValueError: If the promotion isn't found.
        """
        with self.db.get_session() as session:
            promotion = session.get(Promotion, promotion_id)
            if not promotion:
                raise ValueError(f"Promotion with ID {promotion_id} not found.")
            session.delete(promotion)
            session.commit()

    def get_active_promotions(self) -> list[Promotion]:
        """Return promotions that are active and whose start/end window covers now."""
        now = datetime.now()
        with self.db.get_session() as session:
            stmt = select(Promotion).where(
                Promotion.is_active.is_(True),
                Promotion.start_time <= now,
                Promotion.end_time >= now,
            )
            promos = list(session.scalars(stmt).all())
            for promo in promos:
                session.expunge(promo)
            return promos

    def get_all_promotions(self) -> list[Promotion]:
        """Return every promotion, with its category eager-loaded, newest start first."""
        with self.db.get_session() as session:
            stmt = select(Promotion).options(joinedload(Promotion.category)).order_by(Promotion.start_time.desc())
            promos = list(session.scalars(stmt).all())
            for promo in promos:
                session.expunge(promo)
            return promos
