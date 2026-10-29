"""
CustomerView (deleted as dead code -- superseded by this screen, #506)
showed each customer's loyalty points as a table column. CreditBookView's
customer list covers everything else CustomerView did (list all, search,
add, edit -- confirmed via CustomerService.get_all_customers()/
search_customers(), the same methods CustomerView called) but dropped the
Points column. Restores it so browsing points at a glance isn't lost.
"""

import pytest

from cbpos.core.models import Customer
from cbpos.ui.views.credit_book_view import CreditBookView

pytestmark = pytest.mark.usefixtures("qapp")


def test_customer_table_has_a_points_column_with_the_right_value(db_session):
    customer = Customer(name="Points Customer", phone="0771234567", loyalty_points=42)
    db_session.add(customer)
    db_session.commit()

    view = CreditBookView()

    assert view.customer_table.columnCount() == 6

    row = None
    for r in range(view.customer_table.rowCount()):
        item = view.customer_table.item(r, 0)
        if item and item.text() == str(customer.id):
            row = r
            break
    assert row is not None

    assert view.customer_table.item(row, 5).text() == "42"
