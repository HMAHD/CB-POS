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

from cbpos.core.models import Permission, Product, PurchaseItem, PurchaseOrder, Role, Supplier, Unit, User
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


def _make_product(db_session, name_en: str, **fields) -> Product:
    """Add a product with a unique barcode, flushed so it has an id."""
    global _counter
    _counter += 1
    product = Product(
        name_en=name_en,
        barcode=f"POX{_counter:04d}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("0"),
        **fields,
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
        assert discrepancies[0]["kind"] == "over"

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
        assert discrepancies[0]["kind"] == "under"

    def test_flags_lines_not_on_the_order(self, db_session, test_supplier, test_product, test_user):
        other_product = Product(
            name_en="Unrelated Product", barcode="POT-UNREL", price=Decimal("10"), cost=Decimal("5")
        )
        db_session.add(other_product)
        db_session.flush()

        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id,
            [
                {"product_id": test_product.id, "qty": Decimal("10")},
                {"product_id": other_product.id, "qty": Decimal("999")},
            ],
        )

        assert len(discrepancies) == 1
        assert discrepancies[0]["kind"] == "not_on_order"
        assert discrepancies[0]["product_id"] == other_product.id
        assert discrepancies[0]["product_name"] == "Unrelated Product"
        assert discrepancies[0]["outstanding"] == Decimal("0")
        assert discrepancies[0]["received"] == Decimal("999")

    def test_flags_outstanding_line_missing_from_the_grn(self, db_session, test_supplier, test_product, test_user):
        second = _make_product(db_session, "Dropped Product")
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id,
            test_user.id,
            [
                {"product_id": test_product.id, "qty_ordered": Decimal("10")},
                {"product_id": second.id, "qty_ordered": Decimal("6")},
            ],
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id, [{"product_id": test_product.id, "qty": Decimal("10")}]
        )

        assert len(discrepancies) == 1
        assert discrepancies[0]["kind"] == "not_received"
        assert discrepancies[0]["product_id"] == second.id
        assert discrepancies[0]["outstanding"] == Decimal("6")
        assert discrepancies[0]["received"] == Decimal("0")

    def test_does_not_flag_a_missing_line_that_is_already_fully_received(
        self, db_session, test_supplier, test_product, test_user
    ):
        second = _make_product(db_session, "Already Received Product")
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id,
            test_user.id,
            [
                {"product_id": test_product.id, "qty_ordered": Decimal("10")},
                {"product_id": second.id, "qty_ordered": Decimal("6")},
            ],
        )
        first_grn = PurchaseService.create_purchase(
            test_supplier.id, "INV-PO-5A", test_user.id, purchase_order_id=order.id
        )
        PurchaseService.commit_purchase(
            first_grn.id, [{"product_id": second.id, "qty": Decimal("6"), "cost": Decimal("50")}]
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id, [{"product_id": test_product.id, "qty": Decimal("10")}]
        )

        assert discrepancies == []

    def test_over_and_under_receipts_carry_their_kind(self, db_session, test_supplier, test_product, test_user):
        second = _make_product(db_session, "Under Product")
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id,
            test_user.id,
            [
                {"product_id": test_product.id, "qty_ordered": Decimal("10")},
                {"product_id": second.id, "qty_ordered": Decimal("10")},
            ],
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id,
            [
                {"product_id": test_product.id, "qty": Decimal("12")},
                {"product_id": second.id, "qty": Decimal("4")},
            ],
        )

        kinds = {d["product_id"]: d["kind"] for d in discrepancies}
        assert kinds == {test_product.id: "over", second.id: "under"}

    def test_reports_every_kind_together(self, db_session, test_supplier, test_product, test_user):
        under = _make_product(db_session, "Combo Under")
        dropped = _make_product(db_session, "Combo Dropped")
        unordered = _make_product(db_session, "Combo Unordered")
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id,
            test_user.id,
            [
                {"product_id": test_product.id, "qty_ordered": Decimal("10")},
                {"product_id": under.id, "qty_ordered": Decimal("10")},
                {"product_id": dropped.id, "qty_ordered": Decimal("3")},
            ],
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id,
            [
                {"product_id": test_product.id, "qty": Decimal("11")},
                {"product_id": under.id, "qty": Decimal("2")},
                {"product_id": unordered.id, "qty": Decimal("5")},
            ],
        )

        assert [(d["product_id"], d["kind"]) for d in discrepancies] == [
            (test_product.id, "over"),
            (under.id, "under"),
            (unordered.id, "not_on_order"),
            (dropped.id, "not_received"),
        ]

    def test_exact_receipt_of_a_multi_line_order_gives_no_discrepancies(
        self, db_session, test_supplier, test_product, test_user
    ):
        second = _make_product(db_session, "Exact Second")
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id,
            test_user.id,
            [
                {"product_id": test_product.id, "qty_ordered": Decimal("10")},
                {"product_id": second.id, "qty_ordered": Decimal("1.250")},
            ],
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id,
            [
                {"product_id": second.id, "qty": Decimal("1.25")},
                {"product_id": test_product.id, "qty": Decimal("10.000")},
            ],
        )

        assert discrepancies == []

    def test_duplicate_grn_lines_for_one_product_are_summed(self, db_session, test_supplier, test_product, test_user):
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id, test_user.id, [{"product_id": test_product.id, "qty_ordered": Decimal("10")}]
        )

        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id,
            [
                {"product_id": test_product.id, "qty": Decimal("6")},
                {"product_id": test_product.id, "qty": Decimal("4")},
            ],
        )

        assert discrepancies == []

    def test_includes_display_name_and_unit_decimal_places(self, db_session, test_supplier, test_user, monkeypatch):
        kg = Unit(name="POTestKg", abbreviation="kg", decimal_places=3)
        db_session.add(kg)
        db_session.flush()
        rice = _make_product(db_session, "Rice", name_si="සහල්", unit_id=kg.id)
        loose = _make_product(db_session, "Loose Item")
        order = PurchaseOrderService.create_purchase_order(
            test_supplier.id,
            test_user.id,
            [
                {"product_id": rice.id, "qty_ordered": Decimal("5")},
                {"product_id": loose.id, "qty_ordered": Decimal("20")},
            ],
        )

        monkeypatch.setattr("cbpos.i18n.get_language", lambda: "si")
        discrepancies = PurchaseOrderService.check_receipt_discrepancies(
            order.id, [{"product_id": rice.id, "qty": Decimal("1.250")}]
        )

        by_product = {d["product_id"]: d for d in discrepancies}
        assert by_product[rice.id]["product_name"] == "සහල්"
        assert by_product[rice.id]["decimal_places"] == 3
        assert by_product[loose.id]["product_name"] == "Loose Item"
        assert by_product[loose.id]["decimal_places"] == 0

    def test_unknown_order_gives_no_discrepancies(self, db_session):
        assert PurchaseOrderService.check_receipt_discrepancies(999_999, [{"product_id": 1, "qty": Decimal("1")}]) == []
