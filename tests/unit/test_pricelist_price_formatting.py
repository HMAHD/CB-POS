"""#557: Price Lists show formatted prices without breaking price editing.

The edit and context-menu handlers parsed the *displayed* text back with
``Decimal(...)``, so formatting the cells ("1,650.00") would have raised
InvalidOperation. They now read the raw Decimal stored in UserRole.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.models import Product
from cbpos.core.utils.formatters import get_currency_symbol
from cbpos.ui.views import pricelist_view as pricelist_view_module
from cbpos.ui.views.pricelist_view import PRICE_ROLE, PriceListView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def setup(db_session):
    """A view showing a list with one overridden and one plain product, both priced 1,650."""
    plain = Product(barcode=f"PF-{_suffix()}", name_en="Plain", price=Decimal("1650.00"), cost=Decimal("1"))
    over = Product(barcode=f"PF-{_suffix()}", name_en="Over", price=Decimal("1650.00"), cost=Decimal("1"))
    db_session.add_all([plain, over])
    db_session.flush()
    view = PriceListView()
    price_list = view.price_list_service.create_price_list(f"Fmt_{_suffix()}")
    view.price_list_service.set_item_price(price_list.id, over.id, Decimal("1234.50"))
    view.current_list = price_list
    view.load_items()
    rows = {view.table.item(r, 0).text(): r for r in range(view.table.rowCount())}
    yield view, rows[str(plain.id)], rows[str(over.id)]
    view.deleteLater()


def _edit(view, row):
    dialog = MagicMock()
    dialog.exec.return_value = 0
    with patch.object(pricelist_view_module, "SetItemPriceDialog", return_value=dialog) as dialog_cls:
        view._edit_item_price_row(row)
    return dialog_cls.call_args.args[1]


def test_prices_keep_their_raw_decimal_in_user_role(setup):
    view, plain, over = setup
    assert view.table.item(plain, 2).data(PRICE_ROLE) == Decimal("1650.00")
    assert view.table.item(plain, 3).data(PRICE_ROLE) is None
    assert view.table.item(over, 3).data(PRICE_ROLE) == Decimal("1234.50")


def test_editing_ignores_display_text(setup):
    """Whatever the cells *show*, editing opens with the real price -- no InvalidOperation."""
    view, plain, over = setup
    for row in (plain, over):
        for col in (2, 3):
            view.table.item(row, col).setText("Rs. 1,650.00 (display only)")

    assert _edit(view, plain) == Decimal("1650.00")  # base price row
    assert _edit(view, over) == Decimal("1234.50")  # overridden row


def test_prices_display_with_separators_and_symbol_in_header(setup):
    view, plain, over = setup
    assert view.table.item(plain, 2).text() == "1,650.00"
    assert view.table.item(over, 3).text() == "1,234.50"
    symbol = get_currency_symbol()
    assert view.table.horizontalHeaderItem(2).text().endswith(f"({symbol})")
    assert view.table.horizontalHeaderItem(3).text().endswith(f"({symbol})")


def test_no_override_shows_a_right_aligned_dash_and_no_context_menu(setup):
    view, plain, _over = setup
    cell = view.table.item(plain, 3)
    assert cell.text() == "—"
    assert cell.textAlignment() == pricelist_view_module.NUMERIC_ALIGNMENT
    position = view.table.visualItemRect(view.table.item(plain, 1)).center()
    with patch.object(pricelist_view_module, "QMenu") as menu_cls:
        view._show_item_context_menu(position)
    menu_cls.assert_not_called()


def test_editing_after_formatting_round_trips_to_the_service(setup):
    view, plain, _over = setup
    dialog = MagicMock()
    dialog.exec.return_value = 1
    dialog.get_price.return_value = Decimal("1999.99")
    with patch.object(pricelist_view_module, "SetItemPriceDialog", return_value=dialog):
        view._edit_item_price_row(plain)
    assert view.table.item(plain, 3).data(PRICE_ROLE) == Decimal("1999.99")
    assert view.table.item(plain, 3).text() == "1,999.99"
