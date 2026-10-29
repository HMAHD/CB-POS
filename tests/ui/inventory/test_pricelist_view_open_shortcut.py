"""
The Price List item table only opened the price editor via a raw
doubleClicked signal -- no visible button and no keyboard way to edit the
selected row's price (Enter did nothing).
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cbpos.core.models import Product
from cbpos.ui.views import pricelist_view as pricelist_view_module
from cbpos.ui.views.pricelist_view import PriceListView

pytestmark = pytest.mark.usefixtures("qapp")


def _make_product(db_session, name, barcode, price="100.00"):
    p = Product(barcode=barcode, name_en=name, price=Decimal(price), cost=Decimal("50.00"))
    db_session.add(p)
    db_session.flush()
    return p


class TestPriceListViewOpenShortcut:
    def test_open_button_exists_alongside_double_click(self, db_session):
        view = PriceListView()

        assert hasattr(view, "btn_set_item_price")
        assert view.btn_set_item_price.isVisible() or not view.isVisible()

    def test_no_selection_or_no_list_does_not_crash(self, db_session):
        view = PriceListView()
        view.table.clearSelection()
        view.table.setCurrentCell(-1, -1)

        view.edit_selected_item_price()

    def test_selecting_a_row_and_opening_it_sets_that_products_price(self, db_session):
        product = _make_product(db_session, "Keyboard Product", "PL-KB-1")
        price_list = view = None
        view = PriceListView()
        price_list = view.price_list_service.create_price_list("Test List")
        view.current_list = price_list
        view.load_items()

        row = None
        for r in range(view.table.rowCount()):
            if view.table.item(r, 0).text() == str(product.id):
                row = r
                break
        assert row is not None
        view.table.setCurrentCell(row, 1)

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 1
        fake_dialog.get_price.return_value = Decimal("175.00")
        fake_dialog_cls = MagicMock(return_value=fake_dialog)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(pricelist_view_module, "SetItemPriceDialog", fake_dialog_cls)
            view.edit_selected_item_price()

        fake_dialog_cls.assert_called_once()
        args, _ = fake_dialog_cls.call_args
        assert args[0] == "Keyboard Product"

        items = view.price_list_service.get_items(price_list.id)
        assert len(items) == 1
        assert items[0].product_id == product.id
        assert items[0].price == Decimal("175.00")
