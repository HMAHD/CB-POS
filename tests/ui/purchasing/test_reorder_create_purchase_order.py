"""
#486: ReorderView's "Create Purchase Order" button only emitted an ephemeral
signal -- nothing was ever persisted, so there was no PO to compare a later
receipt against. Now it persists a real PurchaseOrder (and blocks mixed-
supplier selections, since a Purchase Order is placed with one supplier).
"""

from decimal import Decimal

import pytest

from cbpos.core.models import Permission, Product, PurchaseOrder, Role, Supplier, User
from cbpos.ui.views.reorder_view import ReorderView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"reorder_po_test_{suffix}")
    role = Role(name=f"ReorderPORole_{suffix}", permissions=[permission])
    user = User(username=f"reorder_po_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


def _low_stock_product(db_session, supplier: Supplier | None, suffix: str):
    product = Product(
        name_en=f"Reorder PO Product {suffix}",
        barcode=f"RPO{suffix}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("2.000"),
        reorder_point=Decimal("5.000"),
        preferred_qty=Decimal("20.000"),
    )
    if supplier:
        product.suppliers.append(supplier)
    db_session.add(product)
    db_session.commit()
    return product


class TestCreatePurchaseOrderPersistsARealOrder:
    def test_single_supplier_selection_persists_a_purchase_order(self, db_session, test_user, monkeypatch):
        global _counter
        _counter += 1
        supplier = Supplier(company_name=f"Reorder Supplier {_counter}")
        db_session.add(supplier)
        db_session.flush()
        _low_stock_product(db_session, supplier, str(_counter))

        view = ReorderView()
        view.set_user(test_user)
        view.load_reorder_items()
        view.table.selectRow(0)

        monkeypatch.setattr("cbpos.ui.views.reorder_view.QMessageBox.information", lambda *a, **k: None)

        received = []
        view.navigate_to_purchase.connect(lambda items, order_id: received.append((items, order_id)))
        view.create_purchase_order()

        assert len(received) == 1
        items, order_id = received[0]
        assert len(items) == 1

        db_session.expire_all()
        order = db_session.get(PurchaseOrder, order_id)
        assert order is not None
        assert order.status == "ORDERED"
        assert order.supplier_id == supplier.id

    def test_mixed_supplier_selection_is_blocked_and_nothing_is_persisted(self, db_session, test_user, monkeypatch):
        global _counter
        _counter += 1
        supplier_a = Supplier(company_name=f"Reorder Supplier A{_counter}")
        supplier_b = Supplier(company_name=f"Reorder Supplier B{_counter}")
        db_session.add_all([supplier_a, supplier_b])
        db_session.flush()
        _low_stock_product(db_session, supplier_a, f"A{_counter}")
        _low_stock_product(db_session, supplier_b, f"B{_counter}")

        view = ReorderView()
        view.set_user(test_user)
        view.load_reorder_items()
        for row in (0, 1):
            for col in range(view.table.columnCount()):
                item = view.table.item(row, col)
                if item is not None:
                    item.setSelected(True)

        warned = []
        monkeypatch.setattr(
            "cbpos.ui.views.reorder_view.QMessageBox.warning",
            lambda *a, **k: warned.append(True),
        )

        order_count_before = db_session.query(PurchaseOrder).count()
        view.create_purchase_order()

        assert warned == [True]
        assert db_session.query(PurchaseOrder).count() == order_count_before
