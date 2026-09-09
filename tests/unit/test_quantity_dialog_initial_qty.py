"""
QuantityDialog always started its input at "1" -- fine for adding a new
product to the cart, but "Change Quantity" on an existing cart line needs
to open pre-filled with that line's current quantity, not reset it to 1.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cbpos.ui.dialogs.quantity_dialog import QuantityDialog

pytestmark = pytest.mark.usefixtures("qapp")


def _make_product():
    product = MagicMock()
    product.name_en = "Test Product"
    product.unit = None
    return product


class TestQuantityDialogInitialQty:
    def test_defaults_to_one_when_no_initial_qty_given(self):
        dialog = QuantityDialog(_make_product())
        assert dialog.qty_input.text() == "1"

    def test_prefills_with_the_given_initial_qty(self):
        dialog = QuantityDialog(_make_product(), initial_qty=Decimal("2.5"))
        assert dialog.qty_input.text() == "2.500"
        assert dialog.get_quantity() == Decimal("2.5")
