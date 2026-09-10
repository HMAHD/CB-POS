"""
The cart's right-click context menu had no keyboard mnemonics at all --
once open, there was no way to invoke an action by typing a letter, unlike
a well-behaved desktop menu. Only "Change Quantity" showed a (purely
textual, non-functional as a mnemonic) "\tF4" hint. Give every action a
distinct "&X" mnemonic so the menu can be driven from the keyboard once
it's open.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QMenu

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


def _captured_menu(view, monkeypatch, position):
    captured = {}

    def _fake_exec(self, *args, **kwargs):
        captured["menu"] = self

    monkeypatch.setattr(QMenu, "exec", _fake_exec)
    view.show_cart_context_menu(position)
    return captured["menu"]


class TestCartContextMenuMnemonics:
    def test_every_action_has_a_mnemonic_and_they_are_all_distinct(self, view, monkeypatch):
        view.cart_service.add_item(_make_product())
        view.update_cart_display()
        position = view.cart_table.visualRect(view.cart_table.model().index(0, 0)).center()

        menu = _captured_menu(view, monkeypatch, position)
        actions = menu.actions()

        assert len(actions) == 5
        mnemonics = []
        for action in actions:
            assert "&" in action.text()
            letter_index = action.text().index("&") + 1
            mnemonics.append(action.text()[letter_index].lower())

        assert len(set(mnemonics)) == len(mnemonics)

    def test_change_quantity_keeps_its_f4_hint_alongside_the_mnemonic(self, view, monkeypatch):
        view.cart_service.add_item(_make_product())
        view.update_cart_display()
        position = view.cart_table.visualRect(view.cart_table.model().index(0, 0)).center()

        menu = _captured_menu(view, monkeypatch, position)
        qty_action = next(a for a in menu.actions() if "F4" in a.text())

        assert "&" in qty_action.text()
