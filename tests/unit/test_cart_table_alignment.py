"""
The cart table's PRICE/QTY/DISC/TOTAL columns read as "not lined up":
alignment flipped between left and right depending on whether a line item
was discounted (a plain, unaligned QTableWidgetItem for a normal price vs.
a right-aligned QLabel for a discounted one), QTY/DISC/TOTAL never set
alignment at all, and the discounted-price label skipped format_currency()
entirely, showing "110.00 60.00" with no "Rs." prefix while every other
price in the same table had one.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QTableWidgetItem

from cbpos.core.utils.formatters import format_currency
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView

_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session):
    v = SalesView()
    yield v
    v.deleteLater()


def _make_product(price="200.00", unit=None):
    product = MagicMock()
    product.id = 1
    product.name_en = "Test Product"
    product.barcode = "TEST001"
    product.price = Decimal(price)
    product.stock_qty = Decimal("10")
    product.unit = unit
    return product


class TestCartColumnAlignment:
    def test_qty_disc_total_columns_are_right_aligned(self, view):
        view.cart_service.add_item(_make_product())
        view.update_cart_display()

        for col in (2, 3, 4):
            item = view.cart_table.item(0, col)
            assert item.textAlignment() & _RIGHT == _RIGHT

    def test_plain_price_item_is_right_aligned_same_as_discounted(self, view):
        view.cart_service.add_item(_make_product())
        view.update_cart_display()

        price_item = view.cart_table.item(0, 1)
        assert isinstance(price_item, QTableWidgetItem)
        assert price_item.textAlignment() & _RIGHT == _RIGHT

    def test_header_columns_1_to_4_are_right_aligned_item_stays_left(self, view):
        for col in (1, 2, 3, 4):
            header_item = view.cart_table.horizontalHeaderItem(col)
            assert header_item.textAlignment() & _RIGHT == _RIGHT

        item_header = view.cart_table.horizontalHeaderItem(0)
        assert not (item_header.textAlignment() & Qt.AlignmentFlag.AlignRight)


class TestDiscountedPriceFormatting:
    def test_discounted_price_label_uses_currency_formatting_for_both_prices(self, view):
        # A cart-line discount (apply_line_discount) only affects the line
        # TOTAL, not unit_price -- the strikethrough display path is driven
        # by PricingService (a promotion or price-list discount setting
        # unit_price below original_price directly), so that's what needs
        # mocking here to reach it deterministically.
        discounted_pricing = {
            "final_price": Decimal("60.00"),
            "original_price": Decimal("110.00"),
            "applied_rule": "Promo: Test",
        }
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "cbpos.core.services.cart_service.PricingService.calculate_price", lambda *a, **k: discounted_pricing
            )
            view.cart_service.add_item(_make_product(price="110.00"))
        view.update_cart_display()

        widget = view.cart_table.cellWidget(0, 1)
        assert isinstance(widget, QLabel)
        text = widget.text()
        # The old bug rendered a bare "110.00"/"60.00" with no currency
        # symbol at all -- asserting the fully-formatted string is present
        # (not just the raw number) is what actually catches that.
        assert format_currency(Decimal("110.00")) in text
        assert format_currency(Decimal("60.00")) in text


class TestDiscColumnLabeling:
    """The Disc column always appended "%" regardless of discount type,
    so a FIXED-amount discount (e.g. Rs. 50 off) displayed as "50.00%" --
    misrepresenting a currency amount as a percentage."""

    def test_percentage_discount_shows_a_percent_sign(self, view):
        view.cart_service.add_item(_make_product(price="100.00"), qty=Decimal("2"))
        view.cart_service.apply_line_discount(0, "PERCENTAGE", Decimal("10"))
        view.update_cart_display()

        assert view.cart_table.item(0, 3).text() == "10%"

    def test_fixed_discount_shows_a_currency_amount_not_a_percent_sign(self, view):
        view.cart_service.add_item(_make_product(price="100.00"), qty=Decimal("2"))
        view.cart_service.apply_line_discount(0, "FIXED", Decimal("50"))
        view.update_cart_display()

        disc_text = view.cart_table.item(0, 3).text()
        assert "%" not in disc_text
        assert format_currency(Decimal("50")) in disc_text

    def test_no_discount_shows_a_dash(self, view):
        view.cart_service.add_item(_make_product(price="100.00"))
        view.update_cart_display()

        assert view.cart_table.item(0, 3).text() == "-"


class TestChangeQuantityPreservesDiscount:
    """Changing a discounted line's quantity must keep the discount applied
    -- it previously set qty/total directly, silently dropping the
    discount from the charged total while the Disc column kept showing it."""

    def test_changing_quantity_keeps_the_percentage_discount_applied(self, view):
        view.cart_service.add_item(_make_product(price="100.00"), qty=Decimal("2"))
        view.cart_service.apply_line_discount(0, "PERCENTAGE", Decimal("10"))
        view.update_cart_display()
        view.cart_table.setCurrentCell(0, 0)

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 1
        fake_dialog.get_quantity.return_value = Decimal("3")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("cbpos.ui.views.sales_view.QuantityDialog", MagicMock(return_value=fake_dialog))
            view.change_line_quantity()

        item = view.cart_service.items[0]
        assert item["subtotal"] == Decimal("300.00")
        assert item["total"] == Decimal("270.00")  # still 10% off, not full price
