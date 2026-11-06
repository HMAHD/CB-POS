import itertools
from decimal import Decimal

import pytest

from cbpos.core.constants.status import MovementType
from cbpos.core.models import Product, User
from cbpos.core.services.stock_count_service import StockCountService
from cbpos.core.services.stock_service import StockService

_test_counter = itertools.count(1)


def _next_suffix():
    return f"{next(_test_counter):04d}"


@pytest.fixture
def count_setup(db_session):
    suffix = _next_suffix()
    user = User(username=f"user_stk_{suffix}", pin_hash="hash")
    product = Product(
        barcode=f"STK-{suffix}",
        name_en=f"Counted Product {suffix}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("10.000"),
    )
    db_session.add_all([user, product])
    db_session.commit()
    return user, product


class TestStockCountIssue861:
    def test_issue_861_sale_during_count_not_double_counted(self, count_setup, db_session):
        """#861: Load (10), sell 3, count shelf at 7, finalize, approve -> stock is 7."""
        user, product = count_setup
        sc = StockCountService.create_stock_count(user_id=user.id)
        item = StockCountService.add_single_item(sc.id, product.id)
        assert item.expected_qty == Decimal("10.000")

        # Sell 3 during the day
        StockService.record_movement(product.id, Decimal("-3"), MovementType.SALE, user.id)
        db_session.expire_all()
        p = db_session.get(Product, product.id)
        assert p.stock_qty == Decimal("7.000")

        # Count shelf at 7 (first count)
        updated_item = StockCountService.update_count(item.id, Decimal("7.000"))
        assert updated_item.expected_qty == Decimal("7.000")
        assert updated_item.counted_qty == Decimal("7.000")
        assert updated_item.variance_qty == Decimal("0.000")

        StockCountService.finalize_count(sc.id)
        StockCountService.approve_and_apply(sc.id, user.id)

        db_session.expire_all()
        refreshed = db_session.get(Product, product.id)
        assert refreshed.stock_qty == Decimal("7.000")

    def test_issue_861_grn_during_count_not_doubled(self, count_setup, db_session):
        """#861: Load (10), GRN 5, count shelf at 15, finalize, approve -> stock is 15."""
        user, product = count_setup
        sc = StockCountService.create_stock_count(user_id=user.id)
        item = StockCountService.add_single_item(sc.id, product.id)
        assert item.expected_qty == Decimal("10.000")

        # GRN received 5 during the day
        StockService.record_movement(product.id, Decimal("5"), MovementType.PURCHASE, user.id)
        db_session.expire_all()
        p = db_session.get(Product, product.id)
        assert p.stock_qty == Decimal("15.000")

        # Count shelf at 15 (first count)
        updated_item = StockCountService.update_count(item.id, Decimal("15.000"))
        assert updated_item.expected_qty == Decimal("15.000")
        assert updated_item.counted_qty == Decimal("15.000")
        assert updated_item.variance_qty == Decimal("0.000")

        StockCountService.finalize_count(sc.id)
        StockCountService.approve_and_apply(sc.id, user.id)

        db_session.expire_all()
        refreshed = db_session.get(Product, product.id)
        assert refreshed.stock_qty == Decimal("15.000")

    def test_issue_861_sale_after_counting_kept(self, count_setup, db_session):
        """#861: Load 10, count 10, sell 3 after counting, approve -> stock is 7."""
        user, product = count_setup
        sc = StockCountService.create_stock_count(user_id=user.id)
        item = StockCountService.add_single_item(sc.id, product.id)

        # Count shelf at 10
        updated_item = StockCountService.update_count(item.id, Decimal("10.000"))
        assert updated_item.expected_qty == Decimal("10.000")
        assert updated_item.variance_qty == Decimal("0.000")

        # Sell 3 after counting
        StockService.record_movement(product.id, Decimal("-3"), MovementType.SALE, user.id)
        db_session.expire_all()
        p = db_session.get(Product, product.id)
        assert p.stock_qty == Decimal("7.000")

        StockCountService.finalize_count(sc.id)
        StockCountService.approve_and_apply(sc.id, user.id)

        db_session.expire_all()
        refreshed = db_session.get(Product, product.id)
        assert refreshed.stock_qty == Decimal("7.000")

    def test_issue_861_approve_never_fails_insufficient_stock(self, count_setup, db_session):
        """#861: Variance adjustment never fails with Insufficient Stock on approve."""
        user, product = count_setup
        sc = StockCountService.create_stock_count(user_id=user.id)
        item = StockCountService.add_single_item(sc.id, product.id)

        # Count shelf at 2 (variance is -8)
        updated_item = StockCountService.update_count(item.id, Decimal("2.000"))
        assert updated_item.expected_qty == Decimal("10.000")
        assert updated_item.variance_qty == Decimal("-8.000")

        # Sell 5 after count, reducing stock to 5
        StockService.record_movement(product.id, Decimal("-5"), MovementType.SALE, user.id)
        db_session.expire_all()
        p = db_session.get(Product, product.id)
        assert p.stock_qty == Decimal("5.000")

        StockCountService.finalize_count(sc.id)
        # Even though 5 - 8 = -3, approval must succeed without raising Insufficient Stock
        StockCountService.approve_and_apply(sc.id, user.id)

        db_session.expire_all()
        refreshed = db_session.get(Product, product.id)
        assert refreshed.stock_qty == Decimal("-3.000")

    def test_issue_861_increment_count_snapshots_expected_qty_on_first_count(self, count_setup, db_session):
        """#861: increment_count on uncounted item snapshots expected_qty from current product stock."""
        user, product = count_setup
        sc = StockCountService.create_stock_count(user_id=user.id)
        item = StockCountService.add_single_item(sc.id, product.id)

        # Product stock changes before count
        StockService.record_movement(product.id, Decimal("-4"), MovementType.SALE, user.id)

        # First count via increment_count
        updated = StockCountService.increment_count(item.id, Decimal("1.000"))
        assert updated.expected_qty == Decimal("6.000")
        assert updated.counted_qty == Decimal("1.000")
        assert updated.variance_qty == Decimal("-5.000")
