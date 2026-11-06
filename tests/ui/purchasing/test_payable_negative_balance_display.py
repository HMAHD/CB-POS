from decimal import Decimal

import pytest

from cbpos.core.models import Supplier
from cbpos.ui.dialogs.supplier_payment_dialog import SupplierPaymentDialog
from cbpos.ui.views.purchase_view import PurchaseView


@pytest.fixture
def test_supplier_negative_payable(db_session):
    supplier = Supplier(
        company_name="Overcredited Supplier Ltd",
        phone="0771234567",
        current_payable=Decimal("-1280.00"),
        payment_terms=30,
        is_active=True,
    )
    db_session.add(supplier)
    db_session.commit()
    return supplier


def test_issue_920_purchase_view_table_shows_credit_balance(qapp, db_session, test_supplier_negative_payable):
    """Supplier list table displays negative payable as supplier.credit_balance."""
    view = PurchaseView()
    try:
        view.load_payable_suppliers()
        # Find row for our supplier
        table = view.payable_supplier_table
        found_row = -1
        for row in range(table.rowCount()):
            if table.item(row, 0) and table.item(row, 0).text() == str(test_supplier_negative_payable.id):
                found_row = row
                break

        assert found_row != -1, "Supplier not found in table"
        payable_item = table.item(found_row, 3)
        assert payable_item is not None
        assert "Supplier owes you" in payable_item.text()
        assert "1,280.00" in payable_item.text()
    finally:
        view.deleteLater()


def test_issue_920_purchase_view_header_shows_credit_balance(qapp, db_session, test_supplier_negative_payable):
    """Payable detail header card displays negative payable as supplier.credit_balance."""
    view = PurchaseView()
    try:
        view._update_payable_header(test_supplier_negative_payable)
        assert "Supplier owes you" in view.lbl_pay_balance.text()
        assert "1,280.00" in view.lbl_pay_balance.text()
    finally:
        view.deleteLater()


def test_issue_920_supplier_payment_dialog_shows_credit_balance(qapp, db_session, test_supplier_negative_payable):
    """SupplierPaymentDialog displays negative payable as supplier.credit_balance."""
    dlg = SupplierPaymentDialog(test_supplier_negative_payable.id)
    try:
        assert "Supplier owes you" in dlg.lbl_outstanding.text()
        assert "1,280.00" in dlg.lbl_outstanding.text()
    finally:
        dlg.deleteLater()
