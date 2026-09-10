"""
The Credit Book customer list only opened a customer's ledger via a raw
doubleClicked signal -- no visible button and no keyboard way to open the
selected row (Enter did nothing), so a keyboard-only or touch user had no
way to drill into a customer's ledger at all.
"""

import pytest

from cbpos.core.models import Customer
from cbpos.ui.views.credit_book_view import CreditBookView

pytestmark = pytest.mark.usefixtures("qapp")


def _make_customer(db_session, name, suffix):
    customer = Customer(name=name, phone=f"07{suffix}")
    db_session.add(customer)
    db_session.flush()
    return customer


class TestCreditBookCustomerOpenShortcut:
    def test_open_button_exists_alongside_double_click(self, db_session):
        view = CreditBookView()

        assert hasattr(view, "btn_open_customer_ledger")
        assert view.btn_open_customer_ledger.isVisible() or not view.isVisible()

    def test_selecting_a_row_and_opening_it_drills_into_that_customers_ledger(self, db_session):
        customer = _make_customer(db_session, "Keyboard Customer", "222")
        view = CreditBookView()

        row = None
        for r in range(view.customer_table.rowCount()):
            item = view.customer_table.item(r, 0)
            if item and item.text() == str(customer.id):
                row = r
                break
        assert row is not None

        view.customer_table.setCurrentCell(row, 1)
        view._open_selected_customer()

        assert view.selected_customer is not None
        assert view.selected_customer.id == customer.id
        assert view.stack.currentIndex() == 1

    def test_no_selection_does_not_crash_or_navigate(self, db_session):
        view = CreditBookView()
        view.customer_table.clearSelection()
        view.customer_table.setCurrentCell(-1, -1)

        view._open_selected_customer()

        assert view.stack.currentIndex() == 0
