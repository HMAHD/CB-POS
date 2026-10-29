"""
Tests for PaymentDialog's applied-payments list, specifically the "remove
payment" button (#219 area of payment_dialog.py).

The remove button used to build its icon from a raw SVG file path
(QIcon(str(path))), bypassing the app's centralized qtawesome icon system
(cbpos/ui/resources/icons.py) used by every other icon in the app. Switched
to Icons.get(Icons.CANCEL, ...) so it doesn't depend on Qt's SVG icon
engine plugin being present, and to match the established convention.
"""

from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QPushButton

from cbpos.core.models import PaymentMethod
from cbpos.ui.dialogs.payment_dialog import PaymentDialog


@pytest.fixture
def cash_and_card_methods(db_session):
    """Idempotent: the shared in-memory test engine can carry state across
    tests in the same session despite db_session's per-test rollback, so
    this reuses an existing row rather than assuming a clean table."""
    cash = db_session.query(PaymentMethod).filter_by(name="Cash").first()
    if cash is None:
        cash = PaymentMethod(name="Cash", is_cash=True, is_active=True, shortcut="F12")
        db_session.add(cash)

    card = db_session.query(PaymentMethod).filter_by(name="Card").first()
    if card is None:
        card = PaymentMethod(name="Card", is_cash=False, is_active=True)
        db_session.add(card)

    db_session.commit()
    return cash, card


@pytest.fixture
def dialog(qapp, cash_and_card_methods):
    dlg = PaymentDialog(Decimal("600.00"))
    yield dlg
    dlg.deleteLater()


class TestRemovePaymentButton:
    def test_remove_button_has_a_non_null_icon(self, dialog):
        dialog.select_method(dialog.payment_methods[0], dialog._method_buttons[0][0])
        dialog.txt_amount.setText("500.00")
        dialog.add_payment()

        item = dialog.list_payments.item(0)
        widget = dialog.list_payments.itemWidget(item)
        btn_remove = widget.findChild(QPushButton, "BtnRemovePayment")

        assert btn_remove is not None
        assert not btn_remove.icon().isNull()
        assert not btn_remove.icon().pixmap(18, 18).isNull()

    def test_clicking_remove_deletes_the_row_and_recalculates_balance(self, dialog):
        dialog.select_method(dialog.payment_methods[0], dialog._method_buttons[0][0])
        dialog.txt_amount.setText("500.00")
        dialog.add_payment()

        card_method, card_btn = next((m, b) for b, m in dialog._method_buttons if m.name == "Card")
        dialog.select_method(card_method, card_btn)
        dialog.txt_amount.setText("100.00")
        dialog.add_payment()

        assert len(dialog.payments) == 2
        assert dialog.btn_finish.isEnabled()

        item0 = dialog.list_payments.item(0)
        widget0 = dialog.list_payments.itemWidget(item0)
        widget0.findChild(QPushButton, "BtnRemovePayment").click()

        assert len(dialog.payments) == 1
        assert dialog.payments[0]["method"] == "Card"
        assert dialog.list_payments.count() == 1
        assert not dialog.btn_finish.isEnabled()
        assert dialog.get_remaining_amount() == Decimal("500.00")

    def test_removing_all_payments_resets_to_initial_state(self, dialog):
        dialog.select_method(dialog.payment_methods[0], dialog._method_buttons[0][0])
        dialog.txt_amount.setText("600.00")
        dialog.add_payment()
        assert dialog.btn_finish.isEnabled()

        item0 = dialog.list_payments.item(0)
        widget0 = dialog.list_payments.itemWidget(item0)
        widget0.findChild(QPushButton, "BtnRemovePayment").click()

        assert dialog.payments == []
        assert not dialog.btn_finish.isEnabled()
        assert dialog.get_remaining_amount() == Decimal("600.00")
