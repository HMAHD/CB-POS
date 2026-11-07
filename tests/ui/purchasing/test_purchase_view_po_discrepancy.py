"""
#486: commit_grn() had no way to know a GRN was receiving against a Purchase
Order, so a cashier could silently over- or under-receive relative to what
was ordered. When the GRN grid was loaded from an open Purchase Order,
committing with a mismatched quantity now asks for confirmation first.
"""

from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Permission, Product, PurchaseOrder, Role, Supplier, Unit, User
from cbpos.core.services.purchase_order_service import PurchaseOrderService
from cbpos.i18n import _t
from cbpos.ui.views.purchase_view import PurchaseView, format_discrepancy_line

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"po_discrepancy_test_{suffix}")
    grn_perm = db_session.query(Permission).filter_by(code=Permissions.PURCHASE_CREATE_GRN).first() or Permission(
        code=Permissions.PURCHASE_CREATE_GRN
    )
    role = Role(name=f"PODiscrepancyRole_{suffix}", permissions=[permission, grn_perm])
    user = User(username=f"po_discrepancy_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, grn_perm, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"PO Discrepancy Supplier {_counter}")
    db_session.add(supplier)
    db_session.flush()
    return supplier


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(
        name_en=f"PODiscrepancyProduct_{_counter}",
        barcode=f"PODIS{_counter:04d}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("0"),
    )
    db_session.add(product)
    db_session.flush()
    return product


def _load_order_into_grn(view, order, test_supplier):
    view.refresh_open_orders()
    index = view.open_po_combo.findData(order.id)
    view.open_po_combo.setCurrentIndex(index)
    view.load_selected_purchase_order()
    view.invoice_input.setText("INV-PO-DISCREPANCY")
    assert view.supplier_combo.currentData() == test_supplier.id


class TestCommitGrnFlagsDiscrepancies:
    def test_declining_the_confirmation_does_not_commit(
        self, db_session, test_supplier, test_product, test_user, monkeypatch
    ):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        view = PurchaseView()
        view.set_user(test_user)
        _load_order_into_grn(view, order, test_supplier)

        # Grid was pre-filled with the outstanding qty (10) -- edit it to
        # over-receive.
        view.grn_model.item(0, 2).setText("15")

        monkeypatch.setattr(
            "cbpos.ui.views.purchase_view.QMessageBox.question",
            lambda *a, **k: QMessageBox.StandardButton.No,
        )

        view.commit_grn()

        db_session.expire_all()
        saved_order = db_session.get(PurchaseOrder, order.id)
        assert saved_order.status == "ORDERED"
        assert saved_order.items[0].qty_received == Decimal("0")

    def test_confirming_the_discrepancy_commits_the_grn(
        self, db_session, test_supplier, test_product, test_user, monkeypatch
    ):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        view = PurchaseView()
        view.set_user(test_user)
        _load_order_into_grn(view, order, test_supplier)

        view.grn_model.item(0, 2).setText("15")

        monkeypatch.setattr(
            "cbpos.ui.views.purchase_view.QMessageBox.question",
            lambda *a, **k: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr("cbpos.ui.views.purchase_view.QMessageBox.information", lambda *a, **k: None)

        view.commit_grn()

        db_session.expire_all()
        saved_order = db_session.get(PurchaseOrder, order.id)
        assert saved_order.status == "RECEIVED"
        assert saved_order.items[0].qty_received == Decimal("15")

    def test_matching_quantity_commits_without_any_confirmation_prompt(
        self, db_session, test_supplier, test_product, test_user, monkeypatch
    ):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        view = PurchaseView()
        view.set_user(test_user)
        _load_order_into_grn(view, order, test_supplier)

        asked = []
        monkeypatch.setattr(
            "cbpos.ui.views.purchase_view.QMessageBox.question",
            lambda *a, **k: asked.append(True),
        )
        monkeypatch.setattr("cbpos.ui.views.purchase_view.QMessageBox.information", lambda *a, **k: None)

        view.commit_grn()

        assert asked == []
        db_session.expire_all()
        saved_order = db_session.get(PurchaseOrder, order.id)
        assert saved_order.status == "RECEIVED"

    def test_confirmation_lists_each_kind_with_formatted_quantities(
        self, db_session, test_supplier, test_product, test_user, monkeypatch
    ):
        global _counter
        _counter += 1
        kg = Unit(name=f"PODiscrepancyKg_{_counter}", abbreviation="kg", decimal_places=3)
        db_session.add(kg)
        db_session.flush()
        dropped = Product(
            name_en=f"PODiscrepancyDropped_{_counter}",
            barcode=f"PODISD{_counter:04d}",
            price=Decimal("100.00"),
            cost=Decimal("50.00"),
            unit_id=kg.id,
        )
        unordered = Product(
            name_en=f"PODiscrepancyUnordered_{_counter}",
            barcode=f"PODISU{_counter:04d}",
            price=Decimal("10.00"),
            cost=Decimal("5.00"),
        )
        db_session.add_all([dropped, unordered])
        db_session.flush()
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id,
            test_user.id,
            [
                {"product_id": test_product.id, "qty_ordered": Decimal("10")},
                {"product_id": dropped.id, "qty_ordered": Decimal("1.25")},
            ],
        )

        view = PurchaseView()
        view.set_user(test_user)
        _load_order_into_grn(view, order, test_supplier)
        assert view.grn_model.item(1, 0).text() == str(dropped.id)
        view.grn_model.removeRow(1)
        view.grn_items.pop(1)
        view.grn_model.item(0, 2).setText("15")
        view._add_grn_row(unordered, Decimal("3"), Decimal("5"))

        messages = []

        def _capture(_parent, _title, text, *_a, **_k):
            messages.append(text)
            return QMessageBox.StandardButton.No

        monkeypatch.setattr("cbpos.ui.views.purchase_view.QMessageBox.question", _capture)

        view.commit_grn()

        assert len(messages) == 1
        text = messages[0]
        over = _t("purchase.discrepancy_line", product=test_product.name_en, outstanding="10", received="15")
        not_on_order = _t(
            "purchase.discrepancy_line_not_on_order", product=unordered.name_en, outstanding="0", received="3"
        )
        not_received = _t(
            "purchase.discrepancy_line_not_received", product=dropped.name_en, outstanding="1.250", received="0.000"
        )
        assert over in text
        assert not_on_order in text
        assert not_received in text


class TestFormatDiscrepancyLine:
    def test_each_kind_uses_its_own_line_and_unit_decimals(self):
        base = {"product_name": "Rice", "decimal_places": 3}

        assert format_discrepancy_line(
            {**base, "kind": "under", "outstanding": Decimal("5"), "received": Decimal("1.25")}
        ) == _t("purchase.discrepancy_line", product="Rice", outstanding="5.000", received="1.250")
        assert format_discrepancy_line(
            {**base, "kind": "not_on_order", "outstanding": Decimal("0"), "received": Decimal("2")}
        ) == _t("purchase.discrepancy_line_not_on_order", product="Rice", outstanding="0.000", received="2.000")
        assert format_discrepancy_line(
            {**base, "kind": "not_received", "outstanding": Decimal("0.5"), "received": Decimal("0")}
        ) == _t("purchase.discrepancy_line_not_received", product="Rice", outstanding="0.500", received="0.000")

    def test_piece_quantities_show_without_decimals(self):
        line = format_discrepancy_line(
            {
                "kind": "over",
                "product_name": "Soap",
                "outstanding": Decimal("20.000"),
                "received": Decimal("24.000"),
                "decimal_places": 0,
            }
        )

        assert line == _t("purchase.discrepancy_line", product="Soap", outstanding="20", received="24")
