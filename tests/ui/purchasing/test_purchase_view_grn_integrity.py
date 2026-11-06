from decimal import Decimal

import pytest
from PyQt6.QtCore import Qt

from cbpos.core.models import Permission, Product, Purchase, Role, Supplier, User
from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"grn_integ_perm_{_counter}")
    role = Role(name=f"GRNIntegRole_{_counter}", permissions=[permission])
    user = User(username=f"grn_integ_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"GRN Integ Supplier {_counter}")
    db_session.add(supplier)
    db_session.flush()
    return supplier


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(
        name_en=f"GRNIntegProduct_{_counter}",
        barcode=f"GRNINT{_counter:04d}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("10"),
    )
    db_session.add(product)
    db_session.flush()
    return product


def test_issue_919_invalid_vat_leaves_no_purchase(db_session, test_user, test_supplier, test_product, monkeypatch):
    view = PurchaseView()
    view.set_user(test_user)
    view.supplier_combo.addItem(test_supplier.company_name, test_supplier.id)
    view.supplier_combo.setCurrentIndex(view.supplier_combo.findData(test_supplier.id))
    view.invoice_input.setText("INV-919-TEST")
    view._add_grn_row(test_product, Decimal("5"), Decimal("50.00"))
    view.input_vat_field.setText("invalid_vat")

    monkeypatch.setattr("cbpos.ui.views.purchase_view.QMessageBox.warning", lambda *a, **k: None)

    view.commit_grn()

    db_session.expire_all()
    purchases = db_session.query(Purchase).all()
    assert len(purchases) == 0, (
        f"Expected 0 purchases, but found {len(purchases)} orphan(s): {[p.document_number for p in purchases]}"
    )


def test_issue_902_id_column_not_editable(test_user, test_product):
    view = PurchaseView()
    view.set_user(test_user)
    view._add_grn_row(test_product, Decimal("5"), Decimal("50.00"))

    # Column 0 (ID), Column 1 (Name), Column 4 (Total) must NOT be editable
    assert not bool(view.grn_model.item(0, 0).flags() & Qt.ItemFlag.ItemIsEditable)
    assert not bool(view.grn_model.item(0, 1).flags() & Qt.ItemFlag.ItemIsEditable)
    assert not bool(view.grn_model.item(0, 4).flags() & Qt.ItemFlag.ItemIsEditable)

    # Column 2 (Qty) and Column 3 (Cost) must be editable
    assert bool(view.grn_model.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable)
    assert bool(view.grn_model.item(0, 3).flags() & Qt.ItemFlag.ItemIsEditable)


def test_issue_902_editing_cell_updates_total(test_user, test_product):
    view = PurchaseView()
    view.set_user(test_user)
    view._add_grn_row(test_product, Decimal("2"), Decimal("50.00"))
    view.update_total()
    assert "100.00" in view.total_label.text()

    # Edit Qty cell in model from 2 to 4
    view.grn_model.item(0, 2).setText("4.000")
    # Total label must now reflect 4 * 50 = 200.00
    assert "200.00" in view.total_label.text()
    assert "200.00" in view.grn_model.item(0, 4).text()


def test_issue_902_remove_line_action(test_user, test_product):
    view = PurchaseView()
    view.set_user(test_user)
    view._add_grn_row(test_product, Decimal("2"), Decimal("50.00"))
    assert view.grn_model.rowCount() == 1
    assert "100.00" in view.total_label.text()

    view.grn_table.selectRow(0)
    view.remove_selected_grn_row()
    assert view.grn_model.rowCount() == 0
    assert "0.00" in view.total_label.text()
