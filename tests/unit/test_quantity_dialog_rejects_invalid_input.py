"""
get_quantity() silently fell back to Decimal("1") for anything that didn't
parse as a positive number, and accept() never checked the input before
closing the dialog. A cashier who clears the field to retype it and hits
Enter (or the validator's "Intermediate" state lets an empty/partial value
through) would have the quantity silently reset to 1 with no warning --
DiscountDialog already guards this exact class of mistake in its own
accept(), so QuantityDialog should too.
"""

from unittest.mock import MagicMock, patch

import pytest

from cbpos.ui.dialogs.quantity_dialog import QuantityDialog

pytestmark = pytest.mark.usefixtures("qapp")


def _make_product():
    product = MagicMock()
    product.name_en = "Test Product"
    product.unit = None
    return product


class TestQuantityDialogRejectsInvalidInput:
    def test_accept_is_blocked_when_the_field_is_empty(self):
        dialog = QuantityDialog(_make_product())
        dialog.qty_input.setText("")

        with patch("cbpos.ui.dialogs.quantity_dialog.QMessageBox.warning") as mock_warning:
            dialog.accept()

        mock_warning.assert_called_once()
        assert dialog.result() == 0

    def test_accept_is_blocked_for_zero(self):
        dialog = QuantityDialog(_make_product())
        dialog.qty_input.setText("0")

        with patch("cbpos.ui.dialogs.quantity_dialog.QMessageBox.warning") as mock_warning:
            dialog.accept()

        mock_warning.assert_called_once()
        assert dialog.result() == 0

    def test_accept_succeeds_for_a_valid_quantity(self):
        dialog = QuantityDialog(_make_product())
        dialog.qty_input.setText("3")

        with patch("cbpos.ui.dialogs.quantity_dialog.QMessageBox.warning") as mock_warning:
            dialog.accept()

        mock_warning.assert_not_called()
        assert dialog.result() == 1
