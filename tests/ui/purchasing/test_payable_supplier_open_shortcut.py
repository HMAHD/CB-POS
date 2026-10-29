"""
The Payables supplier list only opened a supplier's ledger via a raw
doubleClicked signal -- no visible button and no keyboard way to open the
selected row (Enter did nothing), so a keyboard-only or touch user had no
way to drill into a supplier's ledger at all.
"""

import pytest

from cbpos.core.models import Supplier
from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")


def _make_supplier(db_session, name, suffix):
    supplier = Supplier(company_name=name, phone=f"07{suffix}")
    db_session.add(supplier)
    db_session.flush()
    return supplier


class TestPayableSupplierOpenShortcut:
    def test_open_button_exists_alongside_double_click(self, db_session):
        view = PurchaseView()

        assert hasattr(view, "btn_open_payable_supplier")
        assert view.btn_open_payable_supplier.isVisible() or not view.isVisible()

    def test_selecting_a_row_and_opening_it_drills_into_that_suppliers_ledger(self, db_session):
        supplier = _make_supplier(db_session, "Keyboard Supplier Co", "111")
        view = PurchaseView()

        row = None
        for r in range(view.payable_supplier_table.rowCount()):
            if view.payable_supplier_table.item(r, 0).text() == str(supplier.id):
                row = r
                break
        assert row is not None

        view.payable_supplier_table.setCurrentCell(row, 1)
        view._open_selected_payable_supplier()

        assert view.selected_payable_supplier is not None
        assert view.selected_payable_supplier.id == supplier.id
        assert view.payable_stack.currentIndex() == 1

    def test_no_selection_does_not_crash_or_navigate(self, db_session):
        view = PurchaseView()
        view.payable_supplier_table.clearSelection()
        view.payable_supplier_table.setCurrentCell(-1, -1)

        view._open_selected_payable_supplier()

        assert view.payable_stack.currentIndex() == 0
