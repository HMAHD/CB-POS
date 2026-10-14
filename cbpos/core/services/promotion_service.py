from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from cbpos.core.database import Database
from cbpos.core.models import Category, Product, Promotion
from cbpos.core.services.logging_service import LoggingService, diff_changes, snapshot_changes
from cbpos.core.services.price_list_service import PRICING_EVENT
from cbpos.i18n import _t

# Types pricing_service.calculate_price() actually applies. BOGO has no branch
# there, so it can't be created (#635); legacy BOGO rows stay editable.
SUPPORTED_TYPES = ("PERCENTAGE", "FIXED_AMOUNT")


def _promotion_fields(session: Session, promotion: Promotion) -> dict:
    """The audited fields of a promotion; the category is kept by name so the log stays readable."""
    category = session.get(Category, promotion.category_id) if promotion.category_id is not None else None
    return {
        "name": promotion.name,
        "type": promotion.type,
        "value": promotion.value,
        "start_time": promotion.start_time,
        "end_time": promotion.end_time,
        "days_of_week": promotion.days_of_week,
        "category": category.name if category else None,
        "is_active": promotion.is_active,
    }


class PromotionService:
    """Manages time-boxed promotions (e.g. happy-hour or category discounts).

    Every create, update, on/off switch and delete is written to the Activity Log in the same
    transaction (#642).
    """

    def __init__(self):
        """Bind this service instance to the database singleton."""
        self.db = Database()

    @staticmethod
    def _validate_time_range(start_time: datetime, end_time: datetime) -> None:
        if end_time <= start_time:
            raise ValueError("End time must be after the start time.")

    @staticmethod
    def _check_rules(
        session: Session, type: str, value: Decimal, days_of_week: str | None, category_id: int | None
    ) -> None:
        """Reject values/schedules that would give goods away at checkout (#634).

        Args:
            session: Open session used to look up the top price in scope.
            type: Promotion type.
            value: Percentage or fixed amount.
            days_of_week: Comma-separated weekday indices, or None for every day.
            category_id: Category scope, or None for store-wide.

        Raises:
            ValueError: With a translated message describing the broken rule.
        """
        if type == "PERCENTAGE" and not (0 < value <= 100):
            raise ValueError(_t("promotion.percentage_out_of_range"))
        if type == "FIXED_AMOUNT":
            if value <= 0:
                raise ValueError(_t("promotion.amount_must_be_positive"))
            stmt = select(func.max(Product.price)).where(Product.is_active.is_(True))
            if category_id is not None:
                stmt = stmt.where(Product.category_id == category_id)
            top_price = session.scalar(stmt)
            if top_price is not None and value >= top_price:
                raise ValueError(_t("promotion.amount_exceeds_prices", price=f"{top_price:,.2f}"))
        if days_of_week is not None and not days_of_week.strip():
            raise ValueError(_t("promotion.days_required"))

    def validate_promotion(
        self, type: str, value: Decimal, days_of_week: str | None = None, category_id: int | None = None
    ) -> None:
        """Check a promotion's type, value and days without saving it.

        Raises:
            ValueError: With a translated message describing the broken rule.
        """
        with self.db.get_session() as session:
            self._check_rules(session, type, value, days_of_week, category_id)

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
            ValueError: If end_time is not after start_time, the type is unsupported
                (e.g. BOGO), or the value/days break a rule in ``_check_rules``.
        """
        self._validate_time_range(start_time, end_time)
        if type not in SUPPORTED_TYPES:
            raise ValueError(_t("promotion.type_not_supported"))
        with self.db.get_session() as session:
            self._check_rules(session, type, value, days_of_week, category_id)
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
            with session.no_autoflush:
                created = _promotion_fields(session, promotion)
            del created["is_active"]  # promotions always start switched on
            LoggingService.add_change(
                session, "PROMOTION_CREATE", PRICING_EVENT, name, snapshot_changes(created), value_type=type
            )
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
                the resulting date range has the end at or before the start,
                the type is switched to an unsupported one, or a changed
                type/value/days/scope breaks a rule in ``_check_rules``.
        """
        with self.db.get_session() as session:
            promotion = session.get(Promotion, promotion_id)
            if not promotion:
                raise ValueError(f"Promotion with ID {promotion_id} not found.")
            before = _promotion_fields(session, promotion)

            if name is not None:
                name = name.strip()
                if not name:
                    raise ValueError("Promotion name is required.")
                promotion.name = name

            if type is not None:
                if type not in SUPPORTED_TYPES and type != promotion.type:
                    raise ValueError(_t("promotion.type_not_supported"))
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

            # Only re-check when a rule field changed, so a legacy bad promotion can still be switched off.
            if type is not None or value is not None or days_of_week is not ... or category_id is not ...:
                with session.no_autoflush:
                    self._check_rules(
                        session, promotion.type, promotion.value, promotion.days_of_week, promotion.category_id
                    )

            with session.no_autoflush:
                changes = diff_changes(before, _promotion_fields(session, promotion))
            action = "PROMOTION_TOGGLE" if changes.keys() == {"is_active"} else "PROMOTION_UPDATE"
            LoggingService.add_change(
                session, action, PRICING_EVENT, before["name"], changes, value_type=promotion.type
            )

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
            gone = _promotion_fields(session, promotion)
            del gone["is_active"]
            LoggingService.add_change(
                session,
                "PROMOTION_DELETE",
                PRICING_EVENT,
                promotion.name,
                snapshot_changes(gone, deleted=True),
                value_type=promotion.type,
            )
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
