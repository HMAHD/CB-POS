"""
#486: Roadmap 22.1 claimed "Verify quantities against PO" in the GRN flow,
but there was no persisted Purchase Order at all -- Reorder's "Create
Purchase Order" button just emitted an ephemeral list that pre-filled the
GRN grid, with nothing to compare a later receipt against. Adds a real
PurchaseOrder/PurchaseOrderItem model pair, tracked independently of the
Purchase (GRN) row(s) that receive it so a single order can be received in
full or partially across multiple separate GRNs.
"""

from decimal import Decimal

import pytest

from cbpos.core.models import Permission, Product, PurchaseItem, PurchaseOrder, Role, Supplier, User
from cbpos.core.services.purchase_order_service import PurchaseOrderService
from cbpos.core.services.purchase_service import PurchaseService

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"po_test_{suffix}")
    role = Role(name=f"POTestRole_{suffix}", permissions=[permission])
    user = User(username=f"po_test_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"PO Test Supplier {_counter}")
    db_session.add(supplier)
    db_session.flush()
    return supplier


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(
        name_en=f"POTestProduct_{_counter}",
        barcode=f"POT{_counter:04d}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("0"),
    )
    db_session.add(product)
    db_session.flush()
    return product


class TestCreatePurchaseOrder:
    def test_persists_order_and_items_in_ordered_status(self, db_session, test_supplier, test_product, test_user):
        order = PurchaseOrderService.create_purchase_order(
            supplier_id=test_supplier.id,
            user_id=test_user.id,
            items=[{"product_id": test_product.id, "qty_ordered": Decimal("20.000")}],
        )

        db_session.expire_all()
        saved = db_session.get(PurchaseOrder, order.id)
        assert saved.status == "ORDERED"
        assert saved.supplier_id == test_supplier.id
        assert len(saved.items) == 1
        assert saved.items[0].qty_ordered == Decimal("20.000")
        assert saved.items[0].qty_received == Decimal("0")

    def test_appears_in_open_orders(self, db_session, test_supplier, test_product, test_user):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("5")}]
        )

        open_orders = PurchaseOrderService.get_open_orders()

        assert order.id in [o.id for o in open_orders]


class TestCommitPurchaseAgainstAnOrder:
    def test_full_receipt_marks_the_order_received_and_links_the_purchase_item(
        self, db_session, test_supplier, test_product, test_user
    ):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        purchase = PurchaseService.create_purchase(
            test_supplier.id, "INV-PO-1", test_user.id, purchase_order_id=order.id
        )
        PurchaseService.commit_purchase(
            purchase.id, [{"product_id": test_product.id, "qty": Decimal("10"), "cost": Decimal("50")}]
        )

        db_session.expire_all()
        saved_order = db_session.get(PurchaseOrder, order.id)
        assert saved_order.status == "RECEIVED"
        assert saved_order.items[0].qty_received == Decimal("10")

        purchase_item = db_session.query(PurchaseItem).filter_by(purchase_id=purchase.id).one()
        assert purchase_item.purchase_order_item_id == saved_order.items[0].id

    def test_partial_receipt_marks_the_order_partially_received(
        self, db_session, test_supplier, test_product, test_user
    ):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        purchase = PurchaseService.create_purchase(
            test_supplier.id, "INV-PO-2", test_user.id, purchase_order_id=order.id
        )
        PurchaseService.commit_purchase(
            purchase.id, [{"product_id": test_product.id, "qty": Decimal("4"), "cost": Decimal("50")}]
        )

        db_session.expire_all()
        saved_order = db_session.get(PurchaseOrder, order.id)
        assert saved_order.status == "PARTIALLY_RECEIVED"
        assert saved_order.items[0].qty_received == Decimal("4")

    def test_order_can_be_received_across_two_separate_grns(self, db_session, test_supplier, test_product, test_user):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        first_grn = PurchaseService.create_purchase(
            test_supplier.id, "INV-PO-3A", test_user.id, purchase_order_id=order.id
        )
        PurchaseService.commit_purchase(
            first_grn.id, [{"product_id": test_product.id, "qty": Decimal("6"), "cost": Decimal("50")}]
        )

        second_grn = PurchaseService.create_purchase(
            test_supplier.id, "INV-PO-3B", test_user.id, purchase_order_id=order.id
        )
        PurchaseService.commit_purchase(
            second_grn.id, [{"product_id": test_product.id, "qty": Decimal("4"), "cost": Decimal("50")}]
        )

        db_session.expire_all()
        saved_order = db_session.get(PurchaseOrder, order.id)
        assert saved_order.status == "RECEIVED"
        assert saved_order.items[0].qty_received == Decimal("10")

    def test_order_no_longer_open_once_fully_received(self, db_session, test_supplier, test_product, test_user):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )
        purchase = PurchaseService.create_purchase(
            test_supplier.id, "INV-PO-4", test_user.id, purchase_order_id=order.id
        )
        PurchaseService.commit_purchase(
            purchase.id, [{"product_id": test_product.id, "qty": Decimal("10"), "cost": Decimal("50")}]
        )

        open_orders = PurchaseOrderService.get_open_orders()

        assert order.id not in [o.id for o in open_orders]


class TestCheckReceiptDiscrepancies:
    def test_no_discrepancy_when_receiving_exactly_what_is_outstanding(
        self, db_session, test_supplier, test_product, test_user
    ):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id, [{"product_id": test_product.id, "qty": Decimal("10")}]
        )

        assert discrepancies == []

    def test_flags_over_receipt(self, db_session, test_supplier, test_product, test_user):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id, [{"product_id": test_product.id, "qty": Decimal("15")}]
        )

        assert len(discrepancies) == 1
        assert discrepancies[0]["outstanding"] == Decimal("10")
        assert discrepancies[0]["received"] == Decimal("15")

    def test_flags_under_receipt(self, db_session, test_supplier, test_product, test_user):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id, [{"product_id": test_product.id, "qty": Decimal("3")}]
        )

        assert len(discrepancies) == 1
        assert discrepancies[0]["outstanding"] == Decimal("10")
        assert discrepancies[0]["received"] == Decimal("3")

    def test_ignores_lines_not_on_the_order(self, db_session, test_supplier, test_product, test_user):
        other_product = Product(
            name_en="Unrelated Product", barcode="POT-UNREL", price=Decimal("10"), cost=Decimal("5")
        )
        db_session.add(other_product)
        db_session.flush()

        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id, [{"product_id": other_product.id, "qty": Decimal("999")}]
        )

        assert discrepancies == []
