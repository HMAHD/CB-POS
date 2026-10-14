"""
#701: a tax-exempt item must stay exempt even when its product arrives detached
without its category loaded.

``CartService._is_item_tax_exempt`` used to walk ``product.category`` at totals
time, long after the product's session had closed. If the category had never
been loaded into that instance (a product flushed/committed without a refresh,
or one whose attributes were expired), the lazy load raised
``DetachedInstanceError`` -- which a bare ``except Exception`` swallowed, so the
item was silently taxed.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm.exc import DetachedInstanceError

from cbpos.core.models import Category, Product
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService

_counter = 0


def _mock_pricing(product, customer=None):
    return {"final_price": product.price, "original_price": product.price, "applied_rule": "Standard Price"}


def _config(key):
    if key in ("item_tax_exemptions", "vat_registered"):
        return True
    return ConfigService.DEFAULTS.get(key)


@pytest.fixture
def exempt_product(db_session):
    """A product in a tax-exempt category, detached with ``category`` never loaded."""
    global _counter
    _counter += 1
    category = Category(name=f"Exempt701_{_counter}", tax_exempt=True)
    db_session.add(category)
    db_session.flush()
    product = Product(
        name_en=f"Rice701_{_counter}",
        barcode=f"701-{_counter}",
        price=Decimal("118.00"),
        category_id=category.id,
    )
    db_session.add(product)
    db_session.flush()
    db_session.expunge(product)
    assert "category" in sa_inspect(product).unloaded
    with pytest.raises(DetachedInstanceError):
        _ = product.category
    return product


def _config_all():
    # TaxService reads rates via get_all(); pin them so a rate saved by another test can't leak in
    return {**ConfigService.DEFAULTS, "item_tax_exemptions": True, "vat_registered": True, "tax_vat_rate": 18.0}


@patch("cbpos.core.services.config_service.ConfigService.get_all", side_effect=_config_all)
@patch("cbpos.core.services.config_service.ConfigService.get", side_effect=_config)
@patch("cbpos.core.services.cart_service.PricingService.calculate_price", side_effect=_mock_pricing)
class TestDetachedCategoryTaxExempt:
    def test_detached_exempt_item_is_not_taxed(self, _pricing, _cfg, _cfg_all, exempt_product):
        cart = CartService()
        cart.add_item(exempt_product, Decimal("1"))

        totals = cart.get_totals()

        assert totals["exempt_amount"] == Decimal("118.00")
        assert totals["tax"] == Decimal("0.00")

    def test_exempt_flag_is_captured_when_the_item_is_added(self, _pricing, _cfg, _cfg_all, exempt_product):
        cart = CartService()
        cart.add_item(exempt_product, Decimal("1"))

        assert cart.items[0]["tax_exempt"] is True

    def test_loaded_taxable_category_is_taxed(self, _pricing, _cfg, _cfg_all, db_session):
        category = Category(name="Taxable701", tax_exempt=False)
        db_session.add(category)
        db_session.flush()
        product = Product(name_en="Soap701", barcode="701-T", price=Decimal("118.00"), category=category)
        db_session.add(product)
        db_session.flush()
        db_session.expunge(product)

        cart = CartService()
        cart.add_item(product, Decimal("1"))

        assert cart.items[0]["tax_exempt"] is False
        totals = cart.get_totals()
        assert totals["exempt_amount"] == Decimal("0.00")
        assert totals["tax_vat"] == Decimal("18.00")

    def test_product_without_category_is_taxable(self, _pricing, _cfg, _cfg_all, db_session):
        product = Product(name_en="Plain701", barcode="701-N", price=Decimal("50.00"))
        db_session.add(product)
        db_session.flush()
        db_session.expunge(product)

        cart = CartService()
        cart.add_item(product, Decimal("1"))

        assert cart.items[0]["tax_exempt"] is False
