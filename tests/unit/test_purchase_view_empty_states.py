"""
#258: the Payables supplier table and GRN History both rendered a
completely blank table body when there were zero rows -- just headers,
no message. This app already has an established convention for this
(customer_view.py, pricelist_view.py, inventory_view.py,
report_viewer.py all insert a single spanning, centered, gray
placeholder row). Payables is a plain QTableWidget, so it gets that
exact pattern; GRN History is a QTableView backed by a real model, so
it gets an overlay label instead (the same technique already proven
for the Sales screen's empty cart, sales_view.py's empty_cart_label).
"""

import pytest

from cbpos.i18n import _t
from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")


class TestPayablesTableEmptyState:
    def test_shows_a_spanning_placeholder_row_when_no_suppliers(self, db_session):
        view = PurchaseView()
        view._populate_payable_table([])

        assert view.payable_supplier_table.rowCount() == 1
        item = view.payable_supplier_table.item(0, 0)
        assert item.text() == _t("purchase.payables_empty_state")
        assert view.payable_supplier_table.columnSpan(0, 0) == view.payable_supplier_table.columnCount()

    def test_placeholder_disappears_once_a_supplier_is_added(self, db_session):
        from cbpos.core.models import Supplier

        supplier = Supplier(company_name="Test Supplier Co")
        db_session.add(supplier)
        db_session.flush()

        view = PurchaseView()
        view._populate_payable_table([supplier])

        assert view.payable_supplier_table.rowCount() == 1
        assert view.payable_supplier_table.item(0, 1).text() == "Test Supplier Co"


class TestGrnHistoryEmptyState:
    def test_overlay_label_shown_when_no_purchases(self, db_session):
        view = PurchaseView()
        view.refresh_history()

        assert view.empty_history_label.isVisibleTo(view.history_table)
        assert view.empty_history_label.text() == _t("purchase.grn_history_empty_state")

    def test_overlay_label_hidden_when_purchases_exist(self, db_session):
        from cbpos.core.models import Supplier, User
        from cbpos.core.services.purchase_service import PurchaseService

        supplier = Supplier(company_name="Test Supplier Co")
        user = User(username="grn_empty_state_test_user", pin_hash="hash")
        db_session.add_all([supplier, user])
        db_session.flush()
        PurchaseService.create_purchase(supplier_id=supplier.id, reference_external="INV-1", user_id=user.id)

        view = PurchaseView()
        view.refresh_history()

        assert view.empty_history_label.isVisibleTo(view.history_table) is False
