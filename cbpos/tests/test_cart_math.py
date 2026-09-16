from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.models import Product
from cbpos.core.services.cart_service import CartService


@pytest.fixture
def cart_service():
    return CartService()


@pytest.fixture
def mock_product():
    product = MagicMock(spec=Product)
    product.id = 1
    product.name_en = "Test Product"
    product.price = Decimal("100.00")
    return product


@patch("cbpos.core.services.pricing_service.PricingService.calculate_price")
def test_add_item_defaults(mock_calc_price, cart_service, mock_product):
    mock_calc_price.return_value = {
        "final_price": Decimal("100.00"),
        "original_price": Decimal("100.00"),
        "applied_rule": None,
    }

    cart_service.add_item(mock_product)

    assert len(cart_service.items) == 1
    item = cart_service.items[0]
    assert item["unit_price"] == Decimal("100.00")
    assert item["subtotal"] == Decimal("100.00")
    assert item["total"] == Decimal("100.00")
    assert item["discount_type"] == "NONE"


@patch("cbpos.core.services.pricing_service.PricingService.calculate_price")
def test_apply_line_discount_percentage(mock_calc_price, cart_service, mock_product):
    mock_calc_price.return_value = {
        "final_price": Decimal("100.00"),
        "original_price": Decimal("100.00"),
        "applied_rule": None,
    }

    cart_service.add_item(mock_product)
    cart_service.apply_line_discount(0, "PERCENTAGE", 10.0)  # 10% off

    item = cart_service.items[0]
    assert item["subtotal"] == Decimal("100.00")
    # 10% of 100 is 10. Net = 90.
    assert item["total"] == Decimal("90.00")

    totals = cart_service.get_totals()
    assert totals["subtotal"] == Decimal("90.00")
    assert totals["final_total"] == Decimal("90.00")


@patch("cbpos.core.services.pricing_service.PricingService.calculate_price")
def test_apply_line_discount_fixed(mock_calc_price, cart_service, mock_product):
    mock_calc_price.return_value = {
        "final_price": Decimal("100.00"),
        "original_price": Decimal("100.00"),
        "applied_rule": None,
    }

    cart_service.add_item(mock_product)
    cart_service.apply_line_discount(0, "FIXED", 15.00)  # 15 Rs off

    item = cart_service.items[0]
    assert item["total"] == Decimal("85.00")


@patch("cbpos.core.services.pricing_service.PricingService.calculate_price")
def test_override_price(mock_calc_price, cart_service, mock_product):
    mock_calc_price.return_value = {
        "final_price": Decimal("100.00"),
        "original_price": Decimal("100.00"),
        "applied_rule": None,
    }

    cart_service.add_item(mock_product)

    user = MagicMock()
    user.username = "manager"

    cart_service.override_price(0, 50.00, user)

    item = cart_service.items[0]
    assert item["unit_price"] == Decimal("50.00")
    assert item["is_manual_price"] is True
    assert item["total"] == Decimal("50.00")


@patch("cbpos.core.services.pricing_service.PricingService.calculate_price")
def test_cart_discount(mock_calc_price, cart_service, mock_product):
    mock_calc_price.return_value = {
        "final_price": Decimal("100.00"),
        "original_price": Decimal("100.00"),
        "applied_rule": None,
    }

    cart_service.add_item(mock_product)  # 100
    cart_service.add_item(mock_product)  # 100 -> Total 200

    cart_service.apply_cart_discount("PERCENTAGE", 10.0)  # 10% off cart

    totals = cart_service.get_totals()
    assert totals["subtotal"] == Decimal("200.00")
    # 10% of 200 is 20
    assert totals["cart_discount"] == Decimal("20.00")
    assert totals["final_total"] == Decimal("180.00")


@patch("cbpos.core.services.pricing_service.PricingService.calculate_price")
def test_retail_math_chain(mock_calc_price, cart_service, mock_product):
    # Test the full chain: Gross -> Line Disc -> Net -> Cart Disc -> Final
    mock_calc_price.return_value = {
        "final_price": Decimal("100.00"),
        "original_price": Decimal("100.00"),
        "applied_rule": None,
    }

    cart_service.add_item(mock_product)

    # 1. Line Discount: 10% -> 90
    cart_service.apply_line_discount(0, "PERCENTAGE", 10.0)

    # 2. Cart Discount: 10% off Net (90) -> 9
    cart_service.apply_cart_discount("PERCENTAGE", 10.0)

    totals = cart_service.get_totals()

    assert totals["subtotal"] == Decimal("90.00")  # Sum of line totals
    assert totals["cart_discount"] == Decimal("9.00")  # 10% of 90
    assert totals["final_total"] == Decimal("81.00")  # 90 - 9
