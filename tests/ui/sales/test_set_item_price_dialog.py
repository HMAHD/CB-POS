"""
Price List's "set item price" prompt used QInputDialog.getDouble(), which
renders a native spin-box stepper whose up/down arrows don't pick up the
app's QSS theme (part of the spinbox-widget pattern, issue #263). This
replaces it with the same QLineEdit + QDoubleValidator pattern already
proven correct by QuantityDialog.
"""

from decimal import Decimal

import pytest

from cbpos.ui.dialogs.set_item_price_dialog import SetItemPriceDialog

pytestmark = pytest.mark.usefixtures("qapp")


class TestSetItemPriceDialog:
    def test_prefills_current_price(self):
        dialog = SetItemPriceDialog("Rice 5kg", Decimal("450.00"))
        assert dialog.price_input.text() == "450.00"

    def test_get_price_returns_entered_value(self):
        dialog = SetItemPriceDialog("Rice 5kg", Decimal("450.00"))
        dialog.price_input.setText("399.50")
        assert dialog.get_price() == Decimal("399.50")

    def test_get_price_falls_back_to_minimum_on_invalid_text(self):
        dialog = SetItemPriceDialog("Rice 5kg", Decimal("450.00"))
        dialog.price_input.setText("")
        assert dialog.get_price() == Decimal("0.01")

    def test_uses_line_edit_not_native_spinbox(self):
        # The old QInputDialog.getDouble() rendered a QDoubleSpinBox with
        # broken stepper arrows -- asserting a QLineEdit is what actually
        # catches a regression back to that widget.
        from PyQt6.QtWidgets import QLineEdit

        dialog = SetItemPriceDialog("Rice 5kg", Decimal("450.00"))
        assert isinstance(dialog.price_input, QLineEdit)
