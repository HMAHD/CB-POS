"""
#305: every product row repeated the exact same STATUS value (computed
once for the whole price list, not per-product -- PriceListItem has no
is_active field at all), 80 times identically. A column that repeats
one constant reads as either broken or pointless. The genuinely
list-level status already has a home: the header badge set in
_on_nav_clicked(). Drop the redundant per-row column.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.models import Product
from cbpos.ui.views.pricelist_view import PriceListView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def _make_product(db_session, name):
    p = Product(barcode=f"PLNOSTATUS-{_next_suffix()}", name_en=name, price=Decimal("100.00"), cost=Decimal("50.00"))
    db_session.add(p)
    db_session.flush()
    return p


class TestNoRedundantPerRowStatusColumn:
    def test_table_has_four_columns_not_five(self, db_session):
        view = PriceListView()
        assert view.table.columnCount() == 4

    def test_loading_items_does_not_repeat_a_status_value_per_row(self, db_session):
        _make_product(db_session, "Product A")
        _make_product(db_session, "Product B")

        view = PriceListView()
        price_list = view.price_list_service.create_price_list(
            f"Test List_{_next_suffix()}",
            start_date=datetime(2026, 1, 1),
            end_date=datetime(2026, 12, 31),
        )
        view._on_nav_clicked(price_list)

        assert view.table.rowCount() == 2
        # Only 4 columns of data per row now (id/product/base/list price)
        for row in range(view.table.rowCount()):
            for col in range(4):
                assert view.table.item(row, col) is not None
