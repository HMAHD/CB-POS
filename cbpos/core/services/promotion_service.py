from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select
from cbpos.core.database import Database
from cbpos.core.models import Promotion


class PromotionService:
    def __init__(self):
        self.db = Database()

    def create_promotion(
        self,
        name: str,
        type: str,
        value: Decimal,
        start_time: datetime,
        end_time: datetime,
        days_of_week: Optional[str] = None,
    ) -> Promotion:
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
