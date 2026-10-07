"""
UI-047 (#615): adding a product that is already in the stock count raised
"Product already in this stock count." instead of counting it again.
StockCountService.increment_count adds to the counted quantity (and
recomputes variance) in one transaction so re-add/scan can count up.
"""

from decimal import Decimal

import pytest

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Product, StockCount, StockCountItem, User
from cbpos.core.services.stock_count_service import StockCountService


@pytest.fixture
def count_item(db_session):
    user = User(username="stk_increment_user", pin_hash="hash")
    product = Product(
        barcode="STK-INC-0001",
        name_en="Increment Soap",
        price=Decimal("100.00"),
        cost=Decimal("60.00"),
        stock_qty=Decimal("5.000"),
    )
    db_session.add_all([user, product])
    db_session.flush()
    stock_count = StockCountService.create_stock_count(user_id=user.id)
    item = StockCountService.add_single_item(stock_count.id, product.id)
    return stock_count, item


class TestIncrementCount:
    def test_increment_from_uncounted_starts_at_the_step(self, count_item):
        _sc, item = count_item

        updated = StockCountService.increment_count(item.id, Decimal("1"))

        assert updated.counted_qty == Decimal("1.000")
        assert updated.variance_qty == Decimal("-4.000")
        assert updated.variance_value == Decimal("-240.00")

    def test_increment_adds_to_existing_count(self, count_item):
        _sc, item = count_item
        StockCountService.update_count(item.id, Decimal("2"))

        updated = StockCountService.increment_count(item.id, Decimal("1.5"))

        assert updated.counted_qty == Decimal("3.500")
        assert updated.variance_qty == Decimal("-1.500")

    def test_increment_refuses_a_non_draft_count(self, count_item, db_session):
        stock_count, item = count_item
        StockCountService.void_stock_count(stock_count.id)

        with pytest.raises(ValueError):
            StockCountService.increment_count(item.id, Decimal("1"))

        assert db_session.get(StockCount, stock_count.id).status == DocumentStatus.VOID
        assert db_session.get(StockCountItem, item.id).counted_qty is None
