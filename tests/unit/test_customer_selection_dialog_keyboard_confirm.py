"""
Select Customer dialog only had a Cancel button -- no Select/OK button at
all, and no Key_Return/Key_Enter binding anywhere in the file. The only
way to confirm a selection was self.table.doubleClicked, a mouse-only
interaction, which breaks this app's own keyboard-first design principle
(a cashier could arrow-key to the right row but had nothing to press).
"""

import pytest

from cbpos.core.models import Customer
from cbpos.ui.dialogs.customer_selection_dialog import CustomerSelectionDialog

pytestmark = pytest.mark.usefixtures("qapp")


def _make_customer(db_session, name, suffix):
    customer = Customer(name=name, phone=f"07{suffix}")
    db_session.add(customer)
    db_session.flush()
    return customer


class TestCustomerSelectionKeyboardConfirm:
    def test_select_button_exists(self, db_session):
        dialog = CustomerSelectionDialog()
        assert hasattr(dialog, "btn_select")

    def test_selecting_a_row_and_clicking_select_confirms_that_customer(self, db_session):
        customer = _make_customer(db_session, "Keyboard Select Customer", "333")
        dialog = CustomerSelectionDialog()

        row = None
        for r in range(dialog.table.rowCount()):
            if dialog.table.item(r, 0).text() == str(customer.id):
                row = r
                break
        assert row is not None

        dialog.table.setCurrentCell(row, 1)
        dialog.btn_select.click()

        assert dialog.selected_customer is not None
        assert dialog.selected_customer.id == customer.id
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_select_with_no_row_selected_does_not_close_the_dialog(self, db_session):
        dialog = CustomerSelectionDialog()
        dialog.table.clearSelection()
        dialog.table.setCurrentCell(-1, -1)

        dialog.select_customer()

        assert dialog.selected_customer is None
        assert dialog.result() == 0
