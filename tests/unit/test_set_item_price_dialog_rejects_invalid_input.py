"""
get_price() silently fell back to Decimal("0.01") for anything that didn't
parse as a positive number, and accept() never checked the input before
closing the dialog -- a manager who clears the field to retype a price and
hits Enter before finishing would silently set the line to 1 cent with no
warning. DiscountDialog and QuantityDialog both guard this exact mistake
in their own accept(); SetItemPriceDialog should too, since this directly
changes what the customer is charged.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.ui.dialogs.set_item_price_dialog import SetItemPriceDialog

pytestmark = pytest.mark.usefixtures("qapp")


class TestSetItemPriceDialogRejectsInvalidInput:
    def test_accept_is_blocked_when_the_field_is_empty(self):
        dialog = SetItemPriceDialog("Rice 5kg", Decimal("450.00"))
        dialog.price_input.setText("")

        with patch("cbpos.ui.dialogs.set_item_price_dialog.QMessageBox.warning") as mock_warning:
            dialog.accept()

        mock_warning.assert_called_once()
        assert dialog.result() == 0

    def test_accept_is_blocked_for_zero(self):
        dialog = SetItemPriceDialog("Rice 5kg", Decimal("450.00"))
        dialog.price_input.setText("0")

        with patch("cbpos.ui.dialogs.set_item_price_dialog.QMessageBox.warning") as mock_warning:
            dialog.accept()

        mock_warning.assert_called_once()
        assert dialog.result() == 0

    def test_accept_succeeds_for_a_valid_price(self):
        dialog = SetItemPriceDialog("Rice 5kg", Decimal("450.00"))
        dialog.price_input.setText("399.50")

        with patch("cbpos.ui.dialogs.set_item_price_dialog.QMessageBox.warning") as mock_warning:
            dialog.accept()

        mock_warning.assert_not_called()
        assert dialog.result() == 1
