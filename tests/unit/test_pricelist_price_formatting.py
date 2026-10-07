"""#557: Price Lists show formatted prices without breaking price editing.

The edit and context-menu handlers parsed the *displayed* text back with
``Decimal(...)``, so formatting the cells ("1,650.00") would have raised
InvalidOperation. They now read the raw Decimal stored in UserRole.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.models import Product
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
