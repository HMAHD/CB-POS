"""
#265: when a cart line had a discount or manual price override, only
the name cell got a background tint -- PRICE, QTY, DISC, and TOTAL
cells on that same row stayed the table's plain background. A single
colored cell in an otherwise plain row read as half-finished rather
than "this whole line is discounted."
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt

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


def _make_product(product_id=1, price="100.00"):
    product = MagicMock()
    product.id = product_id
    product.name_en = f"Test Product {product_id}"
    product.barcode = f"TEST{product_id:03d}"
    product.price = Decimal(price)
    product.stock_qty = Decimal("10")
    product.unit = None
    return product


class TestDiscountedRowTintsAllCells:
    def test_all_five_cells_are_tinted_on_a_discounted_line(self, view):
        # A second, undiscounted item is added afterwards so the
        # discounted row (0) is no longer the "just added" row -- update_cart_display()
        # applies its own transient cyan highlight to whatever row is
        # last, which would otherwise be indistinguishable from the
        # discount tint being tested here.
        view.cart_service.add_item(_make_product(product_id=1))
        view.cart_service.apply_line_discount(0, "PERCENTAGE", Decimal("10"))
        view.cart_service.add_item(_make_product(product_id=2))
        view.update_cart_display()

        for col in (0, 1, 2, 3, 4):
            item = view.cart_table.item(0, col)
            assert item.background().style() != Qt.BrushStyle.NoBrush

    def test_undiscounted_row_has_no_special_background(self, view):
        # Same reasoning: check an older row, not the just-added one,
        # to avoid the unrelated transient "just added" highlight.
        view.cart_service.add_item(_make_product(product_id=1))
        view.cart_service.add_item(_make_product(product_id=2))
        view.update_cart_display()

        for col in (0, 1, 2, 3, 4):
            item = view.cart_table.item(0, col)
            assert item.background().style() == Qt.BrushStyle.NoBrush
