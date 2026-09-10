"""
Unit tests for CartService — discount calculations, cart totals, and rounding.

Tests item-level discounts (percentage, fixed), cart-level discounts,
quantity management, price overrides, and total calculations.
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from cbpos.core.services.cart_service import CartService
from cbpos.core.constants.status import Precision


def _make_product(product_id=1, name="Test Product", price="100.00", stock=10.0, barcode="TEST001"):
    """Create a mock Product with minimal attributes."""
    product = MagicMock()
    product.id = product_id
    product.name_en = name
    product.price = Decimal(price)
    product.stock_qty = Decimal(str(stock))
    product.barcode = barcode
    return product


def _mock_pricing(product, customer=None):
    """Default pricing mock — returns standard price, no promotions."""
    return {
        "final_price": product.price,
        "original_price": product.price,
        "applied_rule": "Standard Price",
    }


@patch("cbpos.core.services.cart_service.PricingService.calculate_price", side_effect=_mock_pricing)
class TestCartServiceBasics:
    """Basic cart operations: add, remove, clear."""

    def test_add_item(self, mock_pricing):
        """Adding a product creates a cart item with correct quantity."""
        cart = CartService()
        product = _make_product()
        cart.add_item(product, qty=Decimal("2.000"))

        assert len(cart.items) == 1
        assert cart.items[0]["qty"] == Decimal("2.000")
        assert cart.items[0]["unit_price"] == Decimal("100.00")

    def test_add_same_item_aggregates_quantity(self, mock_pricing):
        """Adding the same product twice increases quantity, not line count."""
        cart = CartService()
        product = _make_product()
        cart.add_item(product, qty=Decimal("2.000"))
        cart.add_item(product, qty=Decimal("3.000"))

        assert len(cart.items) == 1
        assert cart.items[0]["qty"] == Decimal("5.000")

    def test_add_different_items(self, mock_pricing):
        """Adding different products creates separate lines."""
        cart = CartService()
        p1 = _make_product(product_id=1, barcode="A001")
        p2 = _make_product(product_id=2, barcode="A002", price="200.00")
        cart.add_item(p1, qty=Decimal("1.000"))
        cart.add_item(p2, qty=Decimal("1.000"))

        assert len(cart.items) == 2

    def test_add_zero_quantity_raises(self, mock_pricing):
        """Cannot add zero or negative quantity."""
        cart = CartService()
        product = _make_product()
        with pytest.raises(ValueError, match="positive"):
            cart.add_item(product, qty=Decimal("0"))

    def test_add_negative_quantity_raises(self, mock_pricing):
        """Cannot add negative quantity."""
        cart = CartService()
        product = _make_product()
        with pytest.raises(ValueError, match="positive"):
            cart.add_item(product, qty=Decimal("-1"))

    def test_remove_item(self, mock_pricing):
        """Removing an item by index."""
        cart = CartService()
        cart.add_item(_make_product(product_id=1, barcode="A001"), Decimal("1"))
        cart.add_item(_make_product(product_id=2, barcode="A002"), Decimal("1"))

        cart.remove_item(0)
        assert len(cart.items) == 1

    def test_remove_invalid_index(self, mock_pricing):
        """Removing out-of-bounds index does nothing."""
        cart = CartService()
        cart.add_item(_make_product(), Decimal("1"))
        cart.remove_item(99)
        assert len(cart.items) == 1

    def test_clear_cart(self, mock_pricing):
        """Clear empties the cart and resets customer/discounts."""
        cart = CartService()
        cart.add_item(_make_product(), Decimal("1"))
        cart.cart_discount_type = "PERCENTAGE"
        cart.cart_discount_value = Decimal("10")

        cart.clear()
        assert len(cart.items) == 0
        assert cart.cart_discount_type == "NONE"
        assert cart.cart_discount_value == Decimal("0.00")


@patch("cbpos.core.services.cart_service.PricingService.calculate_price", side_effect=_mock_pricing)
class TestCartLineDiscounts:
    """Line-level discount calculations."""

    def test_percentage_discount(self, mock_pricing):
        """10% discount on a Rs.100 x 2 = Rs.200 line → Rs.180."""
        cart = CartService()
        product = _make_product(price="100.00")
        cart.add_item(product, qty=Decimal("2"))
        cart.apply_line_discount(0, "PERCENTAGE", Decimal("10"))

        item = cart.items[0]
        assert item["subtotal"] == Decimal("200.00")  # gross
        assert item["total"] == Decimal("180.00")  # net after 10%

    def test_fixed_discount(self, mock_pricing):
        """Fixed Rs.50 discount on a Rs.200 line → Rs.150."""
        cart = CartService()
        product = _make_product(price="100.00")
        cart.add_item(product, qty=Decimal("2"))
        cart.apply_line_discount(0, "FIXED", Decimal("50"))

        item = cart.items[0]
        assert item["subtotal"] == Decimal("200.00")
        assert item["total"] == Decimal("150.00")

    def test_discount_capped_at_line_total(self, mock_pricing):
        """Discount larger than line total should cap at line total (no negative)."""
        cart = CartService()
        product = _make_product(price="100.00")
        cart.add_item(product, qty=Decimal("1"))
        cart.apply_line_discount(0, "FIXED", Decimal("999"))

        item = cart.items[0]
        assert item["total"] == Decimal("0.00")

    @patch("cbpos.core.services.cart_service.CartService._validate_discount_cap")
    def test_100_percent_discount(self, mock_cap, mock_pricing):
        """100% discount yields zero total (cap bypassed via manager override)."""
        cart = CartService()
        product = _make_product(price="250.00")
        cart.add_item(product, qty=Decimal("1"))
        cart.apply_line_discount(0, "PERCENTAGE", Decimal("100"))

        assert cart.items[0]["total"] == Decimal("0.00")

    def test_no_discount_type_none(self, mock_pricing):
        """Default NONE discount means total equals subtotal."""
        cart = CartService()
        product = _make_product(price="300.00")
        cart.add_item(product, qty=Decimal("3"))

        item = cart.items[0]
        assert item["total"] == Decimal("900.00")
        assert item["subtotal"] == Decimal("900.00")


@patch("cbpos.core.services.cart_service.PricingService.calculate_price", side_effect=_mock_pricing)
class TestUpdateQuantity:
    """update_quantity() must keep a line's discount applied, unlike setting
    qty/total directly -- that silently wiped the discount (money-losing
    bug: the Disc column kept showing e.g. "10%" while the customer was
    actually charged full price)."""

    def test_changing_quantity_keeps_the_line_discount_applied(self, mock_pricing):
        cart = CartService()
        product = _make_product(price="100.00")
        cart.add_item(product, qty=Decimal("2"))
        cart.apply_line_discount(0, "PERCENTAGE", Decimal("10"))
        assert cart.items[0]["total"] == Decimal("180.00")

        cart.update_quantity(0, Decimal("3"))

        item = cart.items[0]
        assert item["qty"] == Decimal("3")
        assert item["subtotal"] == Decimal("300.00")
        assert item["total"] == Decimal("270.00")  # still 10% off, not full price

    def test_changing_quantity_on_a_fixed_discount_line(self, mock_pricing):
        cart = CartService()
        product = _make_product(price="100.00")
        cart.add_item(product, qty=Decimal("2"))
        cart.apply_line_discount(0, "FIXED", Decimal("50"))
        assert cart.items[0]["total"] == Decimal("150.00")

        cart.update_quantity(0, Decimal("4"))

        item = cart.items[0]
        assert item["subtotal"] == Decimal("400.00")
        assert item["total"] == Decimal("350.00")  # same Rs.50 fixed discount

    def test_changing_quantity_on_a_plain_line(self, mock_pricing):
        cart = CartService()
        product = _make_product(price="100.00")
        cart.add_item(product, qty=Decimal("1"))

        cart.update_quantity(0, Decimal("5"))

        item = cart.items[0]
        assert item["qty"] == Decimal("5")
        assert item["total"] == Decimal("500.00")

    def test_invalid_index_does_nothing(self, mock_pricing):
        cart = CartService()
        cart.add_item(_make_product(), Decimal("1"))
        cart.update_quantity(99, Decimal("5"))
        assert cart.items[0]["qty"] == Decimal("1")


@patch("cbpos.core.services.cart_service.PricingService.calculate_price", side_effect=_mock_pricing)
class TestCartLevelDiscounts:
    """Cart-level (whole-cart) discount calculations."""

    def test_cart_percentage_discount(self, mock_pricing):
        """10% cart discount on Rs.500 total → Rs.450 final."""
        cart = CartService()
        cart.add_item(_make_product(price="250.00"), Decimal("2"))
        cart.apply_cart_discount("PERCENTAGE", Decimal("10"))

        totals = cart.get_totals()
        assert totals["subtotal"] == Decimal("500.00")
        assert totals["cart_discount"] == Decimal("50.00")
        assert totals["final_total"] == Decimal("450.00")

    def test_cart_fixed_discount(self, mock_pricing):
        """Fixed Rs.100 cart discount on Rs.500 total → Rs.400 final."""
        cart = CartService()
        cart.add_item(_make_product(price="250.00"), Decimal("2"))
        cart.apply_cart_discount("FIXED", Decimal("100"))

        totals = cart.get_totals()
        assert totals["cart_discount"] == Decimal("100.00")
        assert totals["final_total"] == Decimal("400.00")

    def test_cart_discount_capped(self, mock_pricing):
        """Cart discount exceeding subtotal is capped."""
        cart = CartService()
        cart.add_item(_make_product(price="100.00"), Decimal("1"))
        cart.apply_cart_discount("FIXED", Decimal("999"))

        totals = cart.get_totals()
        assert totals["cart_discount"] == Decimal("100.00")
        assert totals["final_total"] == Decimal("0.00")

    def test_no_cart_discount(self, mock_pricing):
        """No cart discount — final equals subtotal."""
        cart = CartService()
        cart.add_item(_make_product(price="150.00"), Decimal("3"))

        totals = cart.get_totals()
        assert totals["cart_discount"] == Decimal("0.00")
        assert totals["final_total"] == Decimal("450.00")


@patch("cbpos.core.services.cart_service.PricingService.calculate_price", side_effect=_mock_pricing)
class TestCartTotals:
    """Cart total calculations and rounding."""

    def test_totals_with_multiple_items(self, mock_pricing):
        """Total across multiple line items."""
        cart = CartService()
        cart.add_item(_make_product(product_id=1, barcode="A", price="100.00"), Decimal("2"))
        cart.add_item(_make_product(product_id=2, barcode="B", price="50.00"), Decimal("3"))

        totals = cart.get_totals()
        # 100*2 + 50*3 = 200 + 150 = 350
        assert totals["subtotal"] == Decimal("350.00")
        assert totals["final_total"] == Decimal("350.00")
        assert totals["count"] == 2
        assert totals["item_count"] == Decimal("5")

    def test_totals_with_line_and_cart_discounts(self, mock_pricing):
        """Combined line and cart discounts."""
        cart = CartService()
        cart.add_item(_make_product(product_id=1, barcode="A", price="200.00"), Decimal("1"))
        cart.add_item(_make_product(product_id=2, barcode="B", price="100.00"), Decimal("1"))

        # 10% off first item: 200 → 180
        cart.apply_line_discount(0, "PERCENTAGE", Decimal("10"))
        # Fixed Rs.20 off cart: 280 → 260
        cart.apply_cart_discount("FIXED", Decimal("20"))

        totals = cart.get_totals()
        assert totals["subtotal"] == Decimal("280.00")  # 180 + 100
        assert totals["cart_discount"] == Decimal("20.00")
        assert totals["final_total"] == Decimal("260.00")

    def test_totals_quantized_to_2dp(self, mock_pricing):
        """All totals must be quantized to 2 decimal places."""
        cart = CartService()
        # Price that causes repeating decimal with qty
        cart.add_item(_make_product(price="33.33"), Decimal("3"))

        totals = cart.get_totals()
        assert totals["subtotal"] == totals["subtotal"].quantize(Precision.MONEY)
        assert totals["final_total"] == totals["final_total"].quantize(Precision.MONEY)

    def test_empty_cart_totals(self, mock_pricing):
        """Empty cart returns zero totals."""
        cart = CartService()
        totals = cart.get_totals()

        assert totals["subtotal"] == Decimal("0.00")
        assert totals["final_total"] == Decimal("0.00")
        assert totals["count"] == 0
        assert totals["item_count"] == 0


@patch("cbpos.core.services.cart_service.PricingService.calculate_price", side_effect=_mock_pricing)
class TestCartPriceOverride:
    """Manual price override tests."""

    def test_override_price(self, mock_pricing):
        """Override price sets new unit_price and marks as manual."""
        cart = CartService()
        product = _make_product(price="100.00")
        cart.add_item(product, Decimal("1"))

        user = MagicMock()
        user.username = "admin"
        cart.override_price(0, Decimal("80.00"), user)

        assert cart.items[0]["unit_price"] == Decimal("80.00")
        assert cart.items[0]["is_manual_price"] is True
        assert cart.items[0]["total"] == Decimal("80.00")

    def test_override_negative_price_raises(self, mock_pricing):
        """Negative price override raises ValueError."""
        cart = CartService()
        cart.add_item(_make_product(), Decimal("1"))
        with pytest.raises(ValueError, match="negative"):
            cart.override_price(0, Decimal("-10"), MagicMock())

    def test_override_preserves_discount(self, mock_pricing):
        """Price override keeps existing line discount."""
        cart = CartService()
        cart.add_item(_make_product(price="200.00"), Decimal("1"))
        cart.apply_line_discount(0, "PERCENTAGE", Decimal("10"))

        user = MagicMock()
        user.username = "admin"
        cart.override_price(0, Decimal("150.00"), user)

        # 150 with 10% off = 135
        assert cart.items[0]["total"] == Decimal("135.00")
