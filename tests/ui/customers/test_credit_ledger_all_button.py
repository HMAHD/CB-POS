import uuid
from decimal import Decimal

import pytest

from cbpos.core.models import Customer, User
from cbpos.ui.views.credit_book_view import CreditBookView

pytestmark = pytest.mark.usefixtures("qapp")


def _make_user(db_session):
    user = User(username=f"credit_user_{uuid.uuid4().hex[:8]}", pin_hash="x", is_active=True)
    db_session.add(user)
    db_session.flush()
    return user


def _make_customer_with_unrecorded_debt(db_session):
    """Customer with opening debt but no ledger entry (e.g. Chaminda Bandara in seed data)."""
    customer = Customer(
        name=f"Chaminda Bandara {uuid.uuid4().hex[:8]}",
        phone="0751234567",
        current_debt=Decimal("4800.00"),
        credit_limit=Decimal("5000.00"),
    )
    db_session.add(customer)
    db_session.flush()
    return customer


def _open_customer(view, customer):
    view.load_customers()
    for row in range(view.customer_table.rowCount()):
        item = view.customer_table.item(row, 0)
        if item and item.text() == str(customer.id):
            view._open_customer_row(row)
            return
    raise AssertionError("Customer row not found in customer table")


class TestCreditLedgerAllButtonBug:
    def test_all_button_clears_warning_and_updates_preset_state(self, db_session):
        _make_user(db_session)
        customer = _make_customer_with_unrecorded_debt(db_session)

        view = CreditBookView()
        view.show()
        _open_customer(view, customer)

        # Initially, warning hint is visible prompting to click All
        assert view.credit_range_hint.isVisible() is True
        assert "4,800" in view.lbl_credit_range_hint.text()
        assert view.btn_preset_30d.property("presetActive") is True
        assert view.btn_all_dates.property("presetActive") is False

        # User clicks "All"
        view.btn_all_dates.click()

        # Warning banner must be hidden because All Time is active
        assert view.credit_range_hint.isVisible() is False
        assert view.btn_all_dates.property("presetActive") is True
        assert view.btn_preset_30d.property("presetActive") is False

        # User clicks "Last 30 Days" preset
        view.btn_preset_30d.click()
        assert view.btn_preset_30d.property("presetActive") is True
        assert view.btn_all_dates.property("presetActive") is False
        # Discrepancy returns because customer debt is not in the 30d range
        assert view.credit_range_hint.isVisible() is True

        # Clicking the banner's "All" button also activates all dates and hides the banner
        view.btn_credit_range_hint_show_all.click()
        assert view.credit_range_hint.isVisible() is False
        assert view.btn_all_dates.property("presetActive") is True
