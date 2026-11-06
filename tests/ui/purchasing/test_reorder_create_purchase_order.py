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
        monkeypatch.setattr("cbpos.ui.views.reorder_view.QMessageBox.warning", lambda *a, **k: None)

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

    def test_mixed_supplier_selection_declined_nothing_persisted(self, db_session, test_user, monkeypatch):
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

        from PyQt6.QtWidgets import QMessageBox

        monkeypatch.setattr(
            "cbpos.ui.views.reorder_view.QMessageBox.question",
            lambda *a, **k: QMessageBox.StandardButton.No,
        )
        monkeypatch.setattr("cbpos.ui.views.reorder_view.QMessageBox.warning", lambda *a, **k: None)

        order_count_before = db_session.query(PurchaseOrder).count()
        view.create_purchase_order()

        assert db_session.query(PurchaseOrder).count() == order_count_before

    def test_issue_864_po_created_for_default_supplier(self, db_session, test_user, monkeypatch):
        global _counter
        _counter += 1
        counter_val = _counter
        supplier = Supplier(company_name=f"Default Supplier PO {counter_val}")
        db_session.add(supplier)
        db_session.flush()

        product = Product(
            name_en=f"Reorder Default Prod {counter_val}",
            barcode=f"RDP{counter_val}",
            price=Decimal("150.00"),
            cost=Decimal("75.00"),
            stock_qty=Decimal("1.000"),
            reorder_point=Decimal("10.000"),
            preferred_qty=Decimal("25.000"),
            default_supplier_id=supplier.id,
        )
        db_session.add(product)
        db_session.commit()

        view = ReorderView()
        view.set_user(test_user)
        view.load_reorder_items()

        # Find row for this product
        target_row = None
        for r in range(view.table.rowCount()):
            if view.table.item(r, 0).data(0x0100) == product.id:
                target_row = r
                break
        assert target_row is not None
        # Supplier column should display supplier.company_name
        assert view.table.item(target_row, 5).text() == supplier.company_name

        view.table.selectRow(target_row)

        monkeypatch.setattr("cbpos.ui.views.reorder_view.QMessageBox.information", lambda *a, **k: None)
        monkeypatch.setattr("cbpos.ui.views.reorder_view.QMessageBox.warning", lambda *a, **k: None)

        received = []
        view.navigate_to_purchase.connect(lambda items, order_id: received.append((items, order_id)))
        view.create_purchase_order()

        assert len(received) == 1
        _, order_id = received[0]

        db_session.expire_all()
        order = db_session.get(PurchaseOrder, order_id)
        assert order is not None
        assert order.status == "ORDERED"
        assert order.supplier_id == supplier.id

    def test_issue_864_mixed_suppliers_split_into_pos(self, db_session, test_user, monkeypatch):
        global _counter
        _counter += 1
        supplier_a = Supplier(company_name=f"Split Supplier A{_counter}")
        supplier_b = Supplier(company_name=f"Split Supplier B{_counter}")
        db_session.add_all([supplier_a, supplier_b])
        db_session.flush()

        # Product A with default supplier A
        product_a = Product(
            name_en=f"Split Prod A{_counter}",
            barcode=f"SPA{_counter}",
            price=Decimal("100.00"),
            cost=Decimal("50.00"),
            stock_qty=Decimal("1.000"),
            reorder_point=Decimal("5.000"),
            preferred_qty=Decimal("10.000"),
            default_supplier_id=supplier_a.id,
        )
        # Product B with M2M supplier B
        product_b = Product(
            name_en=f"Split Prod B{_counter}",
            barcode=f"SPB{_counter}",
            price=Decimal("200.00"),
            cost=Decimal("80.00"),
            stock_qty=Decimal("2.000"),
            reorder_point=Decimal("8.000"),
            preferred_qty=Decimal("15.000"),
            suppliers=[supplier_b],
        )
        db_session.add_all([product_a, product_b])
        db_session.commit()

        view = ReorderView()
        view.set_user(test_user)
        view.load_reorder_items()

        # Select both rows
        for r in range(view.table.rowCount()):
            p_id = view.table.item(r, 0).data(0x0100)
            if p_id in (product_a.id, product_b.id):
                for c in range(view.table.columnCount()):
                    item = view.table.item(r, c)
                    if item:
                        item.setSelected(True)

        from PyQt6.QtWidgets import QMessageBox

        questions = []

        def fake_question(parent, title, text, buttons, default):
            questions.append(text)
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr("cbpos.ui.views.reorder_view.QMessageBox.question", fake_question)
        monkeypatch.setattr("cbpos.ui.views.reorder_view.QMessageBox.information", lambda *a, **k: None)
        monkeypatch.setattr("cbpos.ui.views.reorder_view.QMessageBox.warning", lambda *a, **k: None)

        received = []
        view.navigate_to_purchase.connect(lambda items, order_id: received.append((items, order_id)))
        view.create_purchase_order()

        assert len(questions) == 1
        # split_confirm asked for 2 suppliers
        assert "2" in questions[0]

        # Verify 2 PurchaseOrders were created in DB
        db_session.expire_all()
        order_a = db_session.query(PurchaseOrder).filter_by(supplier_id=supplier_a.id).first()
        order_b = db_session.query(PurchaseOrder).filter_by(supplier_id=supplier_b.id).first()
        assert order_a is not None
        assert order_b is not None
        assert order_a.status == "ORDERED"
        assert order_b.status == "ORDERED"

    def test_issue_864_no_supplier_items_show_hint_and_no_po(self, db_session, test_user, monkeypatch):
        global _counter
        _counter += 1
        product = Product(
            name_en=f"No Supplier Prod {_counter}",
            barcode=f"NSP{_counter}",
            price=Decimal("50.00"),
            cost=Decimal("25.00"),
            stock_qty=Decimal("0.000"),
            reorder_point=Decimal("5.000"),
            preferred_qty=Decimal("10.000"),
        )
        db_session.add(product)
        db_session.commit()

        view = ReorderView()
        view.set_user(test_user)
        view.load_reorder_items()

        # Select the row
        target_row = None
        for r in range(view.table.rowCount()):
            if view.table.item(r, 0).data(0x0100) == product.id:
                target_row = r
                break
        assert target_row is not None
        view.table.selectRow(target_row)

        warned = []
        monkeypatch.setattr(
            "cbpos.ui.views.reorder_view.QMessageBox.warning",
            lambda parent, title, text: warned.append(text),
        )

        order_count_before = db_session.query(PurchaseOrder).count()
        view.create_purchase_order()

        assert len(warned) == 1
        assert "Inventory" in warned[0] or "Edit product" in warned[0]
        assert product.name_en in warned[0]
        assert db_session.query(PurchaseOrder).count() == order_count_before
