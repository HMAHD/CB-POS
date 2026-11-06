from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.models import Permission, Product, Purchase, Role, StockMovement, Supplier, SupplierLedgerEntry, User
from cbpos.core.services.purchase_service import GrnLine, GrnRequest, PurchaseService

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"purch_test_perm_{_counter}")
    role = Role(name=f"PurchTestRole_{_counter}", permissions=[permission])
    user = User(username=f"purch_test_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"Purch Test Supplier {_counter}", current_payable=Decimal("0.00"))
    db_session.add(supplier)
    db_session.flush()
    return supplier


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(
        name_en=f"PurchTestProduct_{_counter}",
        barcode=f"PUR{_counter:04d}",
        price=Decimal("100.00"),
        cost=Decimal("500.00"),
        stock_qty=Decimal("100.000"),
    )
    db_session.add(product)
    db_session.flush()
    return product


def test_purchasing_legacy_flow(db_session, test_user, test_supplier, test_product):
    initial_qty = test_product.stock_qty
    initial_cost = test_product.cost

    # 1. Create GRN (Draft)
    purchase = PurchaseService.create_purchase(
        supplier_id=test_supplier.id,
        reference_external="INV-TEST-001",
        user_id=test_user.id,
    )
    assert purchase.document_number is not None

    # 2. Commit GRN
    new_qty = Decimal("100.000")
    new_cost = Decimal("600.00")
    items_data = [{"product_id": test_product.id, "qty": new_qty, "cost": new_cost}]

    PurchaseService.commit_purchase(purchase.id, items_data)

    db_session.refresh(test_product)
    assert test_product.stock_qty == initial_qty + new_qty

    expected_cost = ((initial_qty * initial_cost) + (new_qty * new_cost)) / (initial_qty + new_qty)
    assert abs(test_product.cost - expected_cost) < Decimal("0.01")

    movement = db_session.query(StockMovement).filter_by(document_id=purchase.id).first()
    assert movement is not None
    assert movement.qty_change == new_qty


def test_issue_919_failure_midway_rolls_back_all(db_session, test_user, test_supplier, test_product, monkeypatch):
    initial_qty = test_product.stock_qty
    initial_cost = test_product.cost
    initial_payable = test_supplier.current_payable

    # Commit setup data so rollback inside receive_goods rolls back only the GRN
    db_session.commit()

    # Patch SupplierPayableService.record_purchase_in_session to simulate an error midway
    def _mock_record_error(*args, **kwargs):
        raise RuntimeError("Injected database failure in ledger recording")

    monkeypatch.setattr(
        "cbpos.core.services.purchase_service.SupplierPayableService.record_purchase_in_session",
        _mock_record_error,
    )

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-FAIL-001",
        input_vat=Decimal("0.00"),
        lines=[GrnLine(product_id=test_product.id, qty=Decimal("5.000"), unit_cost=Decimal("75.00"))],
        user_id=test_user.id,
    )

    with pytest.raises(RuntimeError, match="Injected database failure"):
        PurchaseService.receive_goods(req)

    db_session.expire_all()
    assert db_session.query(Purchase).count() == 0
    assert db_session.query(StockMovement).count() == 0
    assert db_session.query(SupplierLedgerEntry).count() == 0

    reloaded_product = db_session.get(Product, test_product.id)
    assert reloaded_product.stock_qty == initial_qty
    assert reloaded_product.cost == initial_cost

    reloaded_supplier = db_session.get(Supplier, test_supplier.id)
    assert reloaded_supplier.current_payable == initial_payable


def test_issue_919_receive_goods_invalid_vat(db_session, test_user, test_supplier, test_product):
    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-BAD-VAT",
        input_vat=Decimal("-15.00"),
        lines=[GrnLine(product_id=test_product.id, qty=Decimal("5.000"), unit_cost=Decimal("50.00"))],
        user_id=test_user.id,
    )

    with pytest.raises(ValueError, match="grn_invalid_vat"):
        PurchaseService.receive_goods(req)

    db_session.expire_all()
    assert db_session.query(Purchase).count() == 0


def test_issue_902_service_rejects_nonpositive_qty_negative_cost(db_session, test_user, test_supplier, test_product):
    purchase = PurchaseService.create_purchase(test_supplier.id, "INV-902-1", test_user.id)

    # Qty = 0 rejected
    with pytest.raises(ValueError):
        PurchaseService.commit_purchase(
            purchase.id, [{"product_id": test_product.id, "qty": Decimal("0"), "cost": Decimal("10.00")}]
        )

    # Qty < 0 rejected
    with pytest.raises(ValueError):
        PurchaseService.commit_purchase(
            purchase.id, [{"product_id": test_product.id, "qty": Decimal("-5.000"), "cost": Decimal("10.00")}]
        )

    # Cost < 0 rejected
    with pytest.raises(ValueError):
        PurchaseService.commit_purchase(
            purchase.id, [{"product_id": test_product.id, "qty": Decimal("5.000"), "cost": Decimal("-10.00")}]
        )


def test_issue_919_receive_goods_success(db_session, test_user, test_supplier, test_product):
    initial_qty = test_product.stock_qty

    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no="INV-OK-001",
        input_vat=Decimal("25.00"),
        lines=[GrnLine(product_id=test_product.id, qty=Decimal("10.000"), unit_cost=Decimal("600.00"))],
        user_id=test_user.id,
    )

    purchase = PurchaseService.receive_goods(req)
    assert purchase.status == "COMPLETED"
    assert purchase.document_number.startswith("GRN-")
    assert purchase.total_cost == Decimal("6000.00")
    assert purchase.input_vat == Decimal("25.00")

    db_session.expire_all()
    reloaded_prod = db_session.get(Product, test_product.id)
    assert reloaded_prod.stock_qty == initial_qty + Decimal("10.000")

    movement = db_session.query(StockMovement).filter_by(document_id=purchase.id).first()
    assert movement is not None
    assert movement.qty_change == Decimal("10.000")

    reloaded_sup = db_session.get(Supplier, test_supplier.id)
    assert reloaded_sup.current_payable == Decimal("6000.00")

    ledger = db_session.query(SupplierLedgerEntry).filter_by(reference_id=purchase.id).first()
    assert ledger is not None
    assert ledger.amount == Decimal("6000.00")
    assert ledger.entry_type == "PURCHASE"


def test_issue_895_receive_goods_back_dated(db_session, test_user, test_supplier, test_product):
    past_datetime = datetime.now() - timedelta(days=7)
    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=past_datetime,
        supplier_invoice_no="INV-895-DOMAIN",
        input_vat=Decimal("0.00"),
        lines=[GrnLine(product_id=test_product.id, qty=Decimal("10.000"), unit_cost=Decimal("50.00"))],
        user_id=test_user.id,
    )
    purchase = PurchaseService.receive_goods(req)
    assert purchase.date == past_datetime

    movement = db_session.query(StockMovement).filter_by(document_id=purchase.id).first()
    assert movement is not None
    assert movement.timestamp.date() == datetime.now().date()


def test_issue_895_future_date_rejected(db_session, test_user, test_supplier, test_product):
    future_datetime = datetime.now() + timedelta(days=2)
    req = GrnRequest(
        supplier_id=test_supplier.id,
        date_received=future_datetime,
        supplier_invoice_no="INV-895-FUTURE",
        input_vat=Decimal("0.00"),
        lines=[GrnLine(product_id=test_product.id, qty=Decimal("10.000"), unit_cost=Decimal("50.00"))],
        user_id=test_user.id,
    )
    with pytest.raises(ValueError, match="grn_future_date"):
        PurchaseService.receive_goods(req)
