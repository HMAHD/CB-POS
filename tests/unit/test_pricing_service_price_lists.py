"""
#633 (UI-061): checkout applied a customer's price list whenever its
is_active flag was True and ignored start_date/end_date entirely, so expired
special prices kept applying and upcoming ones applied early. A list must
apply only when it is switched on AND today is inside its date range -- the
same rule the Price Lists screen uses for its status badge.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.models import Customer, PriceList, PriceListItem, Product
from cbpos.core.services.price_list_service import PriceListService
from cbpos.core.services.pricing_service import PricingService


def _sfx() -> str:
    return uuid.uuid4().hex[:12]


def _customer_on_list(db_session, *, is_active=True, start=None, end=None):
    product = Product(barcode=f"PLDATE-{_sfx()}", name_en=f"P {_sfx()}", price=Decimal("100.00"))
    price_list = PriceList(name=f"List {_sfx()}", is_active=is_active, start_date=start, end_date=end)
    db_session.add_all([product, price_list])
    db_session.flush()
    db_session.add(PriceListItem(price_list_id=price_list.id, product_id=product.id, price=Decimal("80.00")))
    customer = Customer(name=f"C {_sfx()}", price_list_id=price_list.id)
    db_session.add(customer)
    db_session.flush()
    return product, customer, price_list


_DAY = timedelta(days=1)


@pytest.mark.parametrize(
    ("is_active", "start_offset", "end_offset", "expected", "status"),
    [
        (True, -_DAY, -_DAY / 2, "100.00", "expired"),
        (True, _DAY, 2 * _DAY, "100.00", "upcoming"),
        (True, -_DAY, _DAY, "80.00", "active"),
        (True, None, None, "80.00", "active"),
        (False, -_DAY, _DAY, "100.00", "disabled"),
    ],
    ids=["expired", "upcoming", "live", "open-ended", "switched-off"],
)
def test_price_list_applies_only_when_live(db_session, is_active, start_offset, end_offset, expected, status):
    now = datetime.now()
    start = now + start_offset if start_offset is not None else None
    end = now + end_offset if end_offset is not None else None
    product, customer, price_list = _customer_on_list(db_session, is_active=is_active, start=start, end=end)

    result = PricingService.calculate_price(product, customer)

    assert result["final_price"] == Decimal(expected)
    # The screen's status must agree with what checkout does.
    assert PriceListService.get_status(price_list) == status


def test_update_price_list_can_switch_a_list_off_and_on(db_session):
    service = PriceListService()
    price_list = service.create_price_list(f"Toggle {_sfx()}")

    assert service.update_price_list(price_list.id, is_active=False).is_active is False
    assert service.update_price_list(price_list.id, name=f"Renamed {_sfx()}").is_active is False
    assert service.update_price_list(price_list.id, is_active=True).is_active is True
