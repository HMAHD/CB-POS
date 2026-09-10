"""
Unit tests for PromotionService's CRUD gap (#308) and date validation
(part of #310's compounding issues).

PromotionService previously had only create_promotion, get_active_promotions,
and get_all_promotions -- no update or delete method existed anywhere, so a
promotion with a typo'd name or a wrong date range could only ever be left
wrong forever or replaced by creating a second, separate one.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.services.promotion_service import PromotionService

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def service():
    return PromotionService()


@pytest.fixture
def test_promotion(db_session, service):
    now = datetime.now()
    return service.create_promotion(
        name=f"TestPromo_{_next_suffix()}",
        type="PERCENTAGE",
        value=Decimal("10.00"),
        start_time=now,
        end_time=now + timedelta(days=7),
    )


class TestCreatePromotionValidation:
    def test_rejects_end_time_before_start_time(self, db_session, service):
        now = datetime.now()
        with pytest.raises(ValueError, match="start"):
            service.create_promotion(
                name=f"Bad_{_next_suffix()}",
                type="PERCENTAGE",
                value=Decimal("10.00"),
                start_time=now,
                end_time=now - timedelta(days=1),
            )

    def test_rejects_end_time_equal_to_start_time(self, db_session, service):
        now = datetime.now()
        with pytest.raises(ValueError, match="start"):
            service.create_promotion(
                name=f"Bad_{_next_suffix()}",
                type="PERCENTAGE",
                value=Decimal("10.00"),
                start_time=now,
                end_time=now,
            )


class TestUpdatePromotion:
    def test_renames_a_promotion(self, db_session, service, test_promotion):
        new_name = f"{test_promotion.name}_Renamed"
        updated = service.update_promotion(test_promotion.id, name=new_name)
        assert updated.name == new_name

    def test_updates_value_and_type(self, db_session, service, test_promotion):
        updated = service.update_promotion(test_promotion.id, type="FIXED_AMOUNT", value=Decimal("50.00"))
        assert updated.type == "FIXED_AMOUNT"
        assert updated.value == Decimal("50.00")

    def test_updates_the_date_range(self, db_session, service, test_promotion):
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 31)
        updated = service.update_promotion(test_promotion.id, start_time=start, end_time=end)
        assert updated.start_time == start
        assert updated.end_time == end

    def test_rejects_an_updated_range_where_end_precedes_start(self, db_session, service, test_promotion):
        with pytest.raises(ValueError, match="start"):
            service.update_promotion(
                test_promotion.id,
                start_time=datetime(2026, 6, 1),
                end_time=datetime(2026, 1, 1),
            )

    def test_can_toggle_is_active_off_and_on(self, db_session, service, test_promotion):
        deactivated = service.update_promotion(test_promotion.id, is_active=False)
        assert deactivated.is_active is False

        reactivated = service.update_promotion(test_promotion.id, is_active=True)
        assert reactivated.is_active is True

    def test_omitting_a_field_leaves_it_unchanged(self, db_session, service, test_promotion):
        original_value = test_promotion.value
        updated = service.update_promotion(test_promotion.id, name=f"{test_promotion.name}_X")
        assert updated.value == original_value

    def test_promotion_not_found_raises(self, db_session, service):
        with pytest.raises(ValueError, match="not found"):
            service.update_promotion(999999, name="Whatever")


class TestDeletePromotion:
    def test_deletes_an_existing_promotion(self, db_session, service, test_promotion):
        promo_id = test_promotion.id
        service.delete_promotion(promo_id)

        remaining = [p.id for p in service.get_all_promotions()]
        assert promo_id not in remaining

    def test_promotion_not_found_raises(self, db_session, service):
        with pytest.raises(ValueError, match="not found"):
            service.delete_promotion(999999)
