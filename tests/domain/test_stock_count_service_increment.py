"""
UI-047 (#615): adding a product that is already in the stock count raised
"Product already in this stock count." instead of counting it again.
StockCountService.increment_count adds to the counted quantity (and
recomputes variance) in one transaction so re-add/scan can count up.
"""

from decimal import Decimal

import pytest
from sqlalchemy import update

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

    def test_increment_adds_to_the_stored_count_not_a_stale_copy(self, count_item, db_session):
        """#548: the add happens in SQL, so a scan can't overwrite a count saved
        meanwhile (another scan, another terminal) with a stale value plus one."""
        _sc, item = count_item
        db_session.get(StockCountItem, item.id)  # identity map now holds counted_qty=None
        db_session.execute(
            update(StockCountItem)
            .where(StockCountItem.id == item.id)
            .values(counted_qty=Decimal("3"))
            .execution_options(synchronize_session=False)
        )

        updated = StockCountService.increment_count(item.id, Decimal("1"))

        assert updated.counted_qty == Decimal("4.000")
        assert updated.variance_qty == Decimal("-1.000")
        assert updated.variance_value == Decimal("-60.00")

    def test_fractional_increment_stays_exact(self, count_item):
        _sc, item = count_item
        for _ in range(3):
            updated = StockCountService.increment_count(item.id, Decimal("0.1"))

        assert updated.counted_qty == Decimal("0.300")


class TestAddSingleItemScope:
    def test_service_products_are_not_stock_counted(self, count_item, db_session):
        """add_all_products leaves services out; a scan or typed add must too (#548)."""
        stock_count, _item = count_item
        service = Product(barcode="STK-INC-SVC", name_en="Delivery", price=Decimal("200"), is_service=True)
        db_session.add(service)
        db_session.flush()

        with pytest.raises(ValueError, match="Service items"):
            StockCountService.add_single_item(stock_count.id, service.id)
