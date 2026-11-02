"""Integration test for promotion sync (#868)."""

from datetime import datetime, time
from decimal import Decimal

import pytest

from cbpos.core.models import Promotion
from tests.helpers.sync_two_machines import Shop, isolated_settings

TILL = "TERM-02"


@pytest.fixture
def shop(tmp_path):
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        s = Shop(str(tmp_path))
        s.add_till(TILL)
        yield s


def test_issue_868_happy_hour_promotion_reaches_till(shop):
    """A promotion with daily_start and daily_end times syncs successfully to the till (#868)."""
    # 1. Create a Happy Hour promotion on Main PC
    with shop.session("main") as s:
        promo = Promotion(
            name="Happy Hour Discount",
            start_time=datetime(2026, 1, 1, 0, 0, 0),
            end_time=datetime(2026, 12, 31, 23, 59, 59),
            type="PERCENTAGE",
            value=Decimal("15.00"),
            daily_start=time(14, 0, 0),
            daily_end=time(18, 0, 0),
            days_of_week="0,1,2,3,4",
            is_active=True,
        )
        s.add(promo)
        s.flush()
        promo_id = promo.id

    # 2. Till pulls catalog
    pulled = shop.pull(TILL, full=True)
    assert pulled > 0

    # 3. Verify promotion on till
    with shop.session(TILL) as s:
        till_promo = s.get(Promotion, promo_id)
        assert till_promo is not None
        assert till_promo.name == "Happy Hour Discount"
        assert till_promo.daily_start == time(14, 0, 0)
        assert till_promo.daily_end == time(18, 0, 0)
        assert till_promo.days_of_week == "0,1,2,3,4"
        assert till_promo.value == Decimal("15.00")
