"""
PricingService.calculate_price() already implements promotion matching
(active window, day-of-week, PERCENTAGE/FIXED_AMOUNT) and CartService.add_item()
already calls it for every item added to the cart -- but this path has zero
test coverage anywhere (test_cart_service.py mocks PricingService entirely,
"no promotions"), so nothing has ever verified it actually works end to end.
These tests exist to settle that empirically rather than by reading code.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.database import Database
from cbpos.core.models import Product, Promotion
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.pricing_service import PricingService

_BARCODE_PREFIX = "PROMOTEST-"


def _next_suffix() -> str:
    """A fresh, globally-unique suffix per call -- not a simple counter. A known
    cross-test data leak (Database.get_session()'s internal commit escapes
    conftest's per-test savepoint rollback) means a plain incrementing counter
    can collide with another test file's rows that were supposed to have been
    rolled back -- confirmed: this file's first product, "BC1", collided with
    test_inventory_service.py's identically-named first product. See the filed
    cross-test-isolation issue."""
    return uuid.uuid4().hex[:12]


@pytest.fixture(autouse=True)
def _no_leftover_promotion_or_product_rows(db_session):
    """
    Clean up this file's own Promotion and Product rows both before AND after
    every test, so it can never leave residue behind for another test in this
    file -- or, worse, an unrelated test in another file that runs after this
    one and happens to add an item to a cart (confirmed: leftover Promotion
    rows broke test_transaction_service.py::test_process_sale_atomic when
    this file's tests ran first). See the filed cross-test-isolation issue.
    """

    def _clean():
        # Goes through Database().get_session() -- the same commit path that
        # lets PricingService's changes escape the per-test rollback boundary
        # in the first place -- so this cleanup is guaranteed to stick the
        # same way, regardless of the exact isolation mechanics at play.
        with Database().get_session() as session:
            session.query(Promotion).delete()
            session.query(Product).filter(Product.barcode.like(f"{_BARCODE_PREFIX}%")).delete(synchronize_session=False)

    _clean()
    yield
    _clean()


def _make_product(db_session, price="100.00", category_id=None):
    suffix = _next_suffix()
    p = Product(
        barcode=f"{_BARCODE_PREFIX}{suffix}",
        name_en=f"Product {suffix}",
        price=Decimal(price),
        category_id=category_id,
    )
    db_session.add(p)
    db_session.flush()
    return p


def _make_promotion(db_session, promo_type, value, active=True, days_of_week=None, category_id=None):
    now = datetime.now()
    start = now - timedelta(hours=1) if active else now + timedelta(days=1)
    end = now + timedelta(hours=1) if active else now + timedelta(days=2)
    suffix = _next_suffix()
    promo = Promotion(
        name=f"Promo {suffix}",
        type=promo_type,
        value=Decimal(str(value)),
        start_time=start,
        end_time=end,
        days_of_week=days_of_week,
        category_id=category_id,
        is_active=True,
    )
    db_session.add(promo)
    db_session.flush()
    return promo


class TestPricingServiceAppliesActivePromotions:
    def test_percentage_promotion_discounts_the_price(self, db_session):
        product = _make_product(db_session, price="100.00")
        _make_promotion(db_session, "PERCENTAGE", "10")

        result = PricingService.calculate_price(product)

        assert result["final_price"] == Decimal("90.00")
        assert result["original_price"] == Decimal("100.00")
        assert "Promo" in result["applied_rule"]

    def test_fixed_amount_promotion_discounts_the_price(self, db_session):
        product = _make_product(db_session, price="100.00")
        _make_promotion(db_session, "FIXED_AMOUNT", "15")

        result = PricingService.calculate_price(product)

        assert result["final_price"] == Decimal("85.00")

    def test_inactive_promotion_outside_its_window_does_not_apply(self, db_session):
        product = _make_product(db_session, price="100.00")
        _make_promotion(db_session, "PERCENTAGE", "50", active=False)

        result = PricingService.calculate_price(product)

        assert result["final_price"] == Decimal("100.00")
        assert result["applied_rule"] == "Standard Price"

    def test_promotion_for_a_different_day_of_week_does_not_apply(self, db_session):
        product = _make_product(db_session, price="100.00")
        # Pick a weekday number that is NOT today, so this promo must not match.
        other_day = str((datetime.now().weekday() + 1) % 7)
        _make_promotion(db_session, "PERCENTAGE", "50", days_of_week=other_day)

        result = PricingService.calculate_price(product)

        assert result["final_price"] == Decimal("100.00")

    def test_best_of_multiple_active_promotions_is_applied(self, db_session):
        product = _make_product(db_session, price="100.00")
        _make_promotion(db_session, "PERCENTAGE", "10")  # -> 90.00
        _make_promotion(db_session, "FIXED_AMOUNT", "30")  # -> 70.00, better for the customer

        result = PricingService.calculate_price(product)

        assert result["final_price"] == Decimal("70.00")

    def test_discount_cannot_take_price_below_zero(self, db_session):
        product = _make_product(db_session, price="10.00")
        _make_promotion(db_session, "FIXED_AMOUNT", "999")

        result = PricingService.calculate_price(product)

        assert result["final_price"] == Decimal("0.00")


class TestPricingServiceRespectsCategoryScope:
    def test_category_scoped_promotion_applies_to_a_product_in_that_category(self, db_session):
        from cbpos.core.models import Category

        category = Category(name=f"Cat_{_next_suffix()}", color="#00FF00")
        db_session.add(category)
        db_session.flush()

        product = _make_product(db_session, price="100.00", category_id=category.id)
        _make_promotion(db_session, "PERCENTAGE", "10", category_id=category.id)

        result = PricingService.calculate_price(product)

        assert result["final_price"] == Decimal("90.00")

    def test_category_scoped_promotion_does_not_apply_to_a_product_in_another_category(self, db_session):
        from cbpos.core.models import Category

        promo_category = Category(name=f"Cat_{_next_suffix()}", color="#00FF00")
        other_category = Category(name=f"Cat_{_next_suffix()}", color="#0000FF")
        db_session.add(promo_category)
        db_session.add(other_category)
        db_session.flush()

        product = _make_product(db_session, price="100.00", category_id=other_category.id)
        _make_promotion(db_session, "PERCENTAGE", "10", category_id=promo_category.id)

        result = PricingService.calculate_price(product)

        assert result["final_price"] == Decimal("100.00")
        assert result["applied_rule"] == "Standard Price"

    def test_category_scoped_promotion_does_not_apply_to_an_uncategorized_product(self, db_session):
        from cbpos.core.models import Category

        category = Category(name=f"Cat_{_next_suffix()}", color="#00FF00")
        db_session.add(category)
        db_session.flush()

        product = _make_product(db_session, price="100.00", category_id=None)
        _make_promotion(db_session, "PERCENTAGE", "10", category_id=category.id)

        result = PricingService.calculate_price(product)

        assert result["final_price"] == Decimal("100.00")

    def test_store_wide_promotion_still_applies_regardless_of_category(self, db_session):
        from cbpos.core.models import Category

        category = Category(name=f"Cat_{_next_suffix()}", color="#00FF00")
        db_session.add(category)
        db_session.flush()

        product = _make_product(db_session, price="100.00", category_id=category.id)
        _make_promotion(db_session, "PERCENTAGE", "10", category_id=None)

        result = PricingService.calculate_price(product)

        assert result["final_price"] == Decimal("90.00")


class TestCartServiceAppliesPromotionsWhenAddingItems:
    def test_active_promotion_price_flows_into_the_cart_line(self, db_session):
        product = _make_product(db_session, price="200.00")
        _make_promotion(db_session, "PERCENTAGE", "25")

        cart = CartService()
        cart.add_item(product, qty=Decimal("1"))

        assert cart.items[0]["unit_price"] == Decimal("150.00")
        assert cart.items[0]["original_price"] == Decimal("200.00")
