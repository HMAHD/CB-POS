"""
#336: Cash is the only payment method with no Delete button (correctly
-- it can't be deleted), but the button group had no fixed width or
reserved slot for the missing third button, and the row is right-
anchored via a stretch factor on the info column. So Cash's narrower
2-button group shifted left, landing its Edit button in a different
horizontal position than every other row's Edit button -- 5 rows lined
up, 1 didn't.
"""

from unittest.mock import MagicMock

import pytest

from cbpos.core.models import PaymentMethod
from cbpos.ui.views.payment_methods_view import _MethodCard

pytestmark = pytest.mark.usefixtures("qapp")


def _make_method(is_cash=False):
    method = MagicMock(spec=PaymentMethod)
    method.name = "Cash" if is_cash else "Card"
    method.is_cash = is_cash
    method.is_active = True
    method.open_drawer = is_cash
    method.shortcut = "F12" if is_cash else None
    return method


class TestCashCardReservesTheDeleteButtonSlot:
    def test_cash_card_still_adds_a_delete_button_to_the_layout(self):
        card = _MethodCard(_make_method(is_cash=True), MagicMock())
        assert card.btn_delete is not None
        assert card.btn_delete.parent() is not None

    def test_cash_delete_button_is_invisible_but_space_is_retained(self):
        card = _MethodCard(_make_method(is_cash=True), MagicMock())
        assert card.btn_delete.isVisibleTo(card) is False
        assert card.btn_delete.sizePolicy().retainSizeWhenHidden() is True

    def test_non_cash_card_shows_a_real_clickable_delete_button(self):
        card = _MethodCard(_make_method(is_cash=False), MagicMock())
        assert card.btn_delete.isVisibleTo(card) is True

    def test_cash_and_non_cash_button_groups_are_the_same_width(self):
        cash_card = _MethodCard(_make_method(is_cash=True), MagicMock())
        card_card = _MethodCard(_make_method(is_cash=False), MagicMock())
        cash_card.adjustSize()
        card_card.adjustSize()
        assert cash_card.btn_layout.sizeHint().width() == card_card.btn_layout.sizeHint().width()
