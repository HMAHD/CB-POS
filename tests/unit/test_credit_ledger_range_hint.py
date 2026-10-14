"""
Same header-vs-filtered-ledger split already fixed for Payables (#282),
confirmed on Credit Book's customer detail page too: the header's "Debt"
value reads Customer.current_debt (a running total with no date filter),
while the ledger table filters CustomerLedgerEntry rows by whatever
range is selected, defaulting to today minus one month. A sale whose
ledger entry falls outside that range leaves the table and footer
showing "Closing: Rs. 0.00" while the header above still shows the real
debt.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from PyQt6.QtCore import Qt

from cbpos.core.models import Customer, CustomerLedgerEntry, User
from cbpos.i18n import _t
from cbpos.ui.views.credit_book_view import CreditBookView

pytestmark = pytest.mark.usefixtures("qapp")


def _make_user(db_session):
    user = User(username=f"credit_test_user_{uuid.uuid4().hex[:8]}", pin_hash="x", is_active=True)
    db_session.add(user)
    db_session.flush()
    return user


def _make_customer_with_old_sale(db_session, user):
    customer = Customer(name=f"Old Balance Customer {uuid.uuid4().hex[:8]}", current_debt=Decimal("7200.00"))
    db_session.add(customer)
    db_session.flush()

    entry = CustomerLedgerEntry(
        customer_id=customer.id,
        entry_type="SALE",
        amount=Decimal("7200.00"),
        balance_after=Decimal("7200.00"),
        reference_doc="SALE-OLD-1",
        note="Credit sale",
        user_id=user.id,
        timestamp=datetime.now() - timedelta(days=90),
    )
    db_session.add(entry)
    db_session.flush()
    return customer


def _open_customer(view, customer):
    view.load_customers()
    for row in range(view.customer_table.rowCount()):
        item = view.customer_table.item(row, 0)
        if item and item.text() == str(customer.id):
            view._open_customer_row(row)
            return
    raise AssertionError("customer row not found in customer table")


class TestCreditRangeHint:
    def test_hint_is_shown_when_the_default_range_excludes_old_sales(self, db_session):
        user = _make_user(db_session)
        customer = _make_customer_with_old_sale(db_session, user)
        view = CreditBookView()
        view.show()

        _open_customer(view, customer)

        # #596: an empty range shows one non-selectable placeholder row, not real entries
        assert view.ledger_table.rowCount() == 1
        placeholder = view.ledger_table.item(0, 0)
        assert placeholder.flags() == Qt.ItemFlag.NoItemFlags
        assert placeholder.text() == _t("credit_book.ledger_empty_range")
        assert view.credit_range_hint.isVisible() is True
        assert "7,200" in view.lbl_credit_range_hint.text() or "7200" in view.lbl_credit_range_hint.text()

    def test_hint_disappears_after_clicking_show_all(self, db_session):
        user = _make_user(db_session)
        customer = _make_customer_with_old_sale(db_session, user)
        view = CreditBookView()
        view.show()
        _open_customer(view, customer)

        view.show_all_dates()

        assert view.ledger_table.rowCount() == 1
        assert view.credit_range_hint.isVisible() is False

    def test_no_hint_when_the_visible_range_already_covers_the_full_balance(self, db_session):
        user = _make_user(db_session)
        customer = Customer(name=f"Recent Sale Customer {uuid.uuid4().hex[:8]}", current_debt=Decimal("500.00"))
        db_session.add(customer)
        db_session.flush()
        entry = CustomerLedgerEntry(
            customer_id=customer.id,
            entry_type="SALE",
            amount=Decimal("500.00"),
            balance_after=Decimal("500.00"),
            reference_doc="SALE-RECENT-1",
            note="Credit sale",
            user_id=user.id,
            timestamp=datetime.now(),
        )
        db_session.add(entry)
        db_session.flush()

        view = CreditBookView()
        view.show()
        _open_customer(view, customer)

        assert view.ledger_table.rowCount() == 1
        assert view.credit_range_hint.isVisible() is False
