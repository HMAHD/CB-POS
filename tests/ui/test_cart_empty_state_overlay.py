"""
The cart wasn't one table that's merely empty -- it was a QStackedWidget
holding two entirely separate widgets: page 0 a plain QLabel, page 1 the
real cart_table (header row included). update_cart_display() flipped
cart_stack.setCurrentIndex(1 if has_items else 0), so the column headers
didn't exist on screen at all until the first item landed; the whole
table was swapped out for the placeholder, not just its rows hidden.

Fixed by keeping cart_table always in the layout and showing the "Scan
or search to add items" hint as an overlay label parented to the table's
own viewport, toggled by visibility rather than swapped in and out --
mirroring the manual-positioning technique this file already uses for
the undo toast.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session):
    v = SalesView()
    yield v
    v.deleteLater()


def _make_product(price="200.00"):
    product = MagicMock()
    product.id = 1
    product.name_en = "Test Product"
    product.barcode = "TEST001"
    product.price = Decimal(price)
    product.stock_qty = Decimal("10")
    product.unit = None
    return product


class TestCartTableIsNeverSwappedOut:
    def test_no_cart_stack_widget_exists_anymore(self, view):
        assert not hasattr(view, "cart_stack")

    def test_empty_cart_label_is_an_overlay_on_the_tables_own_viewport(self, view):
        assert view.empty_cart_label.parent() is view.cart_table.viewport()

    def test_cart_table_header_is_visible_with_an_empty_cart(self, view):
        view.show()
        view.update_cart_display()

        assert view.cart_table.isVisible()
        assert view.cart_table.horizontalHeader().isVisible()


class TestEmptyCartOverlayVisibility:
    def test_overlay_is_shown_when_cart_is_empty(self, view):
        view.show()

        view.update_cart_display()

        assert view.empty_cart_label.isVisible() is True

    def test_overlay_is_hidden_once_an_item_is_added(self, view):
        view.show()
        view.cart_service.add_item(_make_product())

        view.update_cart_display()

        assert view.empty_cart_label.isVisible() is False

    def test_overlay_reappears_after_the_cart_is_cleared_again(self, view):
        view.show()
        view.cart_service.add_item(_make_product())
        view.update_cart_display()

        view.cart_service.items.clear()
        view.update_cart_display()

        assert view.empty_cart_label.isVisible() is True
