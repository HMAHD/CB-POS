from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select
from cbpos.core.database import Database
from cbpos.core.models import Promotion


class PromotionService:
    def __init__(self):
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
        days_of_week: Optional[str] = None,
    ) -> Promotion:
        self._validate_time_range(start_time, end_time)
        with self.db.get_session() as session:
            promotion = Promotion(
                name=name,
                type=type,
                value=value,
                start_time=start_time,
                end_time=end_time,
                days_of_week=days_of_week,
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
        name: Optional[str] = None,
        type: Optional[str] = None,
        value: Optional[Decimal] = None,
        start_time: object = ...,
        end_time: object = ...,
        days_of_week: object = ...,
        is_active: Optional[bool] = None,
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

    def get_active_promotions(self) -> List[Promotion]:
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

    def get_all_promotions(self) -> List[Promotion]:
        with self.db.get_session() as session:
            stmt = select(Promotion).order_by(Promotion.start_time.desc())
            promos = list(session.scalars(stmt).all())
            for promo in promos:
                session.expunge(promo)
            return promos
