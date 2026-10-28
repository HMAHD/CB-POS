"""
The Payables detail header shows Supplier.current_payable -- a
denormalized running total with no date filter -- while the ledger table
below queries SupplierLedgerEntry rows within whatever date range is
selected, defaulting to today minus one month. A purchase whose ledger
entry falls outside that default range leaves the table empty and the
footer showing "Closing: Rs. 0.00" while the header above still shows a
real outstanding balance, with nothing on screen explaining why they
disagree.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.models import Supplier, SupplierLedgerEntry, User
from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")


def _make_user(db_session):
    user = User(username=f"payables_test_user_{uuid.uuid4().hex[:8]}", pin_hash="x", is_active=True)
    db_session.add(user)
    db_session.flush()
    return user


def _make_supplier_with_old_purchase(db_session, user):
    supplier = Supplier(
        company_name=f"Old Balance Supplier Co {uuid.uuid4().hex[:8]}", current_payable=Decimal("62000.00")
    )
    db_session.add(supplier)
    db_session.flush()

    entry = SupplierLedgerEntry(
        supplier_id=supplier.id,
        entry_type="PURCHASE",
        amount=Decimal("62000.00"),
        balance_after=Decimal("62000.00"),
        reference_doc="GRN-OLD-1",
        note="Purchase received",
        user_id=user.id,
        timestamp=datetime.now() - timedelta(days=90),
    )
    db_session.add(entry)
    db_session.flush()
    return supplier


def _open_supplier(view, supplier):
    view.tabs.setCurrentWidget(view.payables_tab)
    for row in range(view.payable_supplier_table.rowCount()):
        if view.payable_supplier_table.item(row, 0).text() == str(supplier.id):
            view._open_payable_supplier_row(row)
            return
    raise AssertionError("supplier row not found in payable table")


class TestPayableRangeHint:
    def test_hint_is_shown_when_the_default_range_excludes_old_purchases(self, db_session):
        user = _make_user(db_session)
        supplier = _make_supplier_with_old_purchase(db_session, user)
        view = PurchaseView()
        view.show()

        _open_supplier(view, supplier)

        assert view.payable_ledger_table.rowCount() == 0
        assert view.payable_range_hint.isVisible() is True
        assert "62,000" in view.lbl_payable_range_hint.text() or "62000" in view.lbl_payable_range_hint.text()

    def test_hint_disappears_after_clicking_show_all(self, db_session):
        user = _make_user(db_session)
        supplier = _make_supplier_with_old_purchase(db_session, user)
        view = PurchaseView()
        view.show()
        _open_supplier(view, supplier)

        view.show_all_payable_dates()

        assert view.payable_ledger_table.rowCount() == 1
        assert view.payable_range_hint.isVisible() is False

    def test_no_hint_when_the_visible_range_already_covers_the_full_balance(self, db_session):
        user = _make_user(db_session)
        supplier = Supplier(
            company_name=f"Recent Purchase Supplier Co {uuid.uuid4().hex[:8]}", current_payable=Decimal("500.00")
        )
        db_session.add(supplier)
        db_session.flush()
        entry = SupplierLedgerEntry(
            supplier_id=supplier.id,
            entry_type="PURCHASE",
            amount=Decimal("500.00"),
            balance_after=Decimal("500.00"),
            reference_doc="GRN-RECENT-1",
            note="Purchase received",
            user_id=user.id,
            timestamp=datetime.now(),
        )
        db_session.add(entry)
        db_session.flush()

        view = PurchaseView()
        view.show()
        _open_supplier(view, supplier)

        assert view.payable_ledger_table.rowCount() == 1
        assert view.payable_range_hint.isVisible() is False
