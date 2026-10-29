"""
Unit tests for PriceListService's update/delete-override gaps (#303, #304).

PriceListService previously had no update_price_list() at all, so a price
list's name and validity dates could only ever be set once, at creation --
fixing a typo'd date or renaming "Happy Hour" to "Weekend Special" meant
deleting and recreating the whole list, losing every product override on
it. Separately, set_item_price() only ever upserted a PriceListItem row;
there was no way to remove a per-product override and fall back to the
product's base price once one had been set.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.models import Product
from cbpos.core.services.price_list_service import PriceListService

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def service():
    return PriceListService()


@pytest.fixture
def test_list(db_session, service):
    return service.create_price_list(f"TestList_{_next_suffix()}")


@pytest.fixture
def test_product(db_session):
    p = Product(
        barcode=f"PL-{_next_suffix()}",
        name_en=f"Product_{_next_suffix()}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
    )
    db_session.add(p)
    db_session.flush()
    return p


class TestUpdatePriceList:
    def test_renames_a_price_list(self, db_session, service, test_list):
        new_name = f"{test_list.name}_Renamed"
        updated = service.update_price_list(test_list.id, name=new_name)

        assert updated.name == new_name

    def test_updates_the_date_range(self, db_session, service, test_list):
        start = datetime(2026, 1, 1)
        end = datetime(2026, 12, 31)

        updated = service.update_price_list(test_list.id, start_date=start, end_date=end)

        assert updated.start_date == start
        assert updated.end_date == end

    def test_can_clear_dates_back_to_none(self, db_session, service, test_list):
        service.update_price_list(test_list.id, start_date=datetime(2026, 1, 1), end_date=datetime(2026, 12, 31))

        updated = service.update_price_list(test_list.id, start_date=None, end_date=None)

        assert updated.start_date is None
        assert updated.end_date is None

    def test_omitting_a_field_leaves_it_unchanged(self, db_session, service, test_list):
        start = datetime(2026, 1, 1)
        service.update_price_list(test_list.id, start_date=start)

        updated = service.update_price_list(test_list.id, name=f"{test_list.name}_X")

        assert updated.start_date == start

    def test_list_not_found_raises(self, db_session, service):
        with pytest.raises(ValueError, match="not found"):
            service.update_price_list(999999, name="Whatever")

    def test_rejects_renaming_to_a_name_used_by_another_list(self, db_session, service, test_list):
        other = service.create_price_list(f"Other_{_next_suffix()}")

        with pytest.raises(ValueError, match="already exists"):
            service.update_price_list(test_list.id, name=other.name)

    def test_renaming_to_its_own_current_name_is_not_a_duplicate(self, db_session, service, test_list):
        updated = service.update_price_list(test_list.id, name=test_list.name)
        assert updated.name == test_list.name


class TestDeleteItemPrice:
    def test_removes_an_existing_override(self, db_session, service, test_list, test_product):
        service.set_item_price(test_list.id, test_product.id, Decimal("75.00"))

        service.delete_item_price(test_list.id, test_product.id)

        assert service.get_items(test_list.id) == []

    def test_no_override_exists_raises(self, db_session, service, test_list, test_product):
        with pytest.raises(ValueError, match="No price override"):
            service.delete_item_price(test_list.id, test_product.id)

    def test_removing_one_override_does_not_touch_another_products(self, db_session, service, test_list, test_product):
        other_product = Product(
            barcode=f"PL-{_next_suffix()}",
            name_en=f"Product_{_next_suffix()}",
            price=Decimal("200.00"),
            cost=Decimal("100.00"),
        )
        db_session.add(other_product)
        db_session.flush()

        service.set_item_price(test_list.id, test_product.id, Decimal("75.00"))
        service.set_item_price(test_list.id, other_product.id, Decimal("150.00"))

        service.delete_item_price(test_list.id, test_product.id)

        remaining = service.get_items(test_list.id)
        assert len(remaining) == 1
        assert remaining[0].product_id == other_product.id
