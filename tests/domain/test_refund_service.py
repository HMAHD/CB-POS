"""
Domain tests for RefundService (#812).

Partial / item-level refunds and returns, proportional tax & tender allocation,
remainder rule over a series of partial refunds, permissions and audit trail.
"""

import sqlite3
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text

from alembic import command
from cbpos.config import Config
from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import DocumentStatus, PaymentMethodKind
from cbpos.core.database import Base
from cbpos.core.models import (
    AuditLog,
    Customer,
    Permission,
    Product,
    Role,
    Sale,
    SaleItem,
    SalePayment,
    StockMovement,
    User,
)
from cbpos.core.services.refund_service import (
    RefundLineRequest,
    RefundService,
)

_counter = 0


def _get_or_create_permission(db_session, code, group="Sales"):
    p = db_session.query(Permission).filter_by(code=code).first()
    if not p:
        p = Permission(code=code, group=group)
        db_session.add(p)
        db_session.flush()
    return p


@pytest.fixture
def refund_user(db_session):
    """User with sales.refund and sales.refund_override_tender permissions."""
    global _counter
    _counter += 1
    p1 = _get_or_create_permission(db_session, Permissions.SALES_REFUND, group="Sales")
    p2 = _get_or_create_permission(db_session, Permissions.SALES_REFUND_OVERRIDE_TENDER, group="Sales")
    role = Role(name=f"RefundRole_{_counter}", permissions=[p1, p2])
    user = User(username=f"refund_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def non_manager_user(db_session):
    """User with only sales.refund (no override)."""
    global _counter
    _counter += 1
    p1 = _get_or_create_permission(db_session, Permissions.SALES_REFUND, group="Sales")
    role = Role(name=f"CashierRole_{_counter}", permissions=[p1])
    user = User(username=f"cashier_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


def _create_product(db_session, name="Item", price=100.0, stock=10.0, is_weighted=False, is_service=False):
    global _counter
    _counter += 1
    p = Product(
        name_en=f"{name}_{_counter}",
        price=price,
        stock_qty=stock,
        barcode=f"BC{_counter:05d}",
        is_weighted=is_weighted,
        is_service=is_service,
    )
    db_session.add(p)
    db_session.flush()
    return p


def _create_sale_item(
    sale_id, product_id, qty, unit_price, subtotal, refunded_qty=Decimal("0.000"), original_price=None
):
    return SaleItem(
        sale_id=sale_id,
        product_id=product_id,
        qty=qty,
        unit_price=unit_price,
        original_price=original_price or unit_price,
        subtotal=subtotal,
        refunded_qty=refunded_qty,
    )


def test_issue_812_partial_refund_one_line(db_session, refund_user):
    """Sale of A*2 (100 each) and B*1 (50), total 250.
    Refund A*1 -> Value 100.00, stock A +1, VAT proportional, refund_state == "PARTIAL".
    """
    prod_a = _create_product(db_session, "A", price=100.0, stock=10.0)
    prod_b = _create_product(db_session, "B", price=50.0, stock=5.0)

    sale = Sale(
        document_number="INV-812-01",
        date=datetime.now(),
        total_amount=Decimal("250.00"),
        tax_vat=Decimal("25.00"),
        tax_sscl=Decimal("6.25"),
        net_revenue=Decimal("218.75"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=refund_user.id,
    )
    db_session.add(sale)
    db_session.flush()

    item_a = _create_sale_item(sale.id, prod_a.id, Decimal("2"), Decimal("100.00"), Decimal("200.00"))
    item_b = _create_sale_item(sale.id, prod_b.id, Decimal("1"), Decimal("50.00"), Decimal("50.00"))
    payment = SalePayment(
        sale_id=sale.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("250.00")
    )
    db_session.add_all([item_a, item_b, payment])
    db_session.commit()

    # Initial stock before refund
    assert prod_a.stock_qty == Decimal("10.0")

    refundable = RefundService.refundable_lines(sale.id)
    assert len(refundable) == 2
    assert refundable[0].remaining_qty == Decimal("2")
    assert refundable[1].remaining_qty == Decimal("1")

    # Preview refunding A*1
    preview = RefundService.preview(
        sale.id,
        [RefundLineRequest(sale_item_id=item_a.id, qty=Decimal("1"))],
    )
    assert preview.total_refund_amount == Decimal("100.00")
    # Proportional VAT: 25.00 * (100 / 250) = 10.00
    assert preview.refund_vat == Decimal("10.00")
    # Proportional SSCL: 6.25 * (100 / 250) = 2.50
    assert preview.refund_sscl == Decimal("2.50")
    assert preview.refund_net == Decimal("87.50")

    # Execute refund
    res = RefundService.refund(
        sale.id,
        [RefundLineRequest(sale_item_id=item_a.id, qty=Decimal("1"), reason="Damaged")],
        reason="Customer returned 1 item A",
        user_id=refund_user.id,
    )
    assert res.total_refund_amount == Decimal("100.00")

    # Verify database state
    db_session.refresh(prod_a)
    assert prod_a.stock_qty == Decimal("11.0")  # +1 restored

    db_session.refresh(item_a)
    assert item_a.refunded_qty == Decimal("1.000")

    # State should now be PARTIAL
    assert RefundService.refund_state(sale.id) == "PARTIAL"


def test_issue_812_cannot_refund_more_than_sold(db_session, refund_user):
    """Refund A*2, then attempting to refund A*1 raises qty_exceeds_remaining."""
    prod = _create_product(db_session, "A", price=100.0, stock=10.0)

    sale = Sale(
        document_number="INV-812-02",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("200.00"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=refund_user.id,
    )
    db_session.add(sale)
    db_session.flush()

    item = _create_sale_item(sale.id, prod.id, Decimal("2"), Decimal("100.00"), Decimal("200.00"))
    payment = SalePayment(
        sale_id=sale.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("200.00")
    )
    db_session.add_all([item, payment])
    db_session.commit()

    # Refund A*2
    RefundService.refund(
        sale.id,
        [RefundLineRequest(sale_item_id=item.id, qty=Decimal("2"))],
        reason="Full return of line A",
        user_id=refund_user.id,
    )
    assert RefundService.refund_state(sale.id) == "FULL"

    # Attempting to refund A*1 must fail
    with pytest.raises(ValueError, match="qty_exceeds_remaining"):
        RefundService.refund(
            sale.id,
            [RefundLineRequest(sale_item_id=item.id, qty=Decimal("1"))],
            reason="Over refund attempt",
            user_id=refund_user.id,
        )


def test_issue_812_series_of_partials_reverses_sale_exactly(db_session, refund_user):
    """Sale with awkward total (e.g. 333.33) and taxes refunded line by line.
    The remainder rule guarantees Σ refund totals == total_amount, VAT, SSCL and net to the cent.
    """
    p1 = _create_product(db_session, "P1", price=100.0)
    p2 = _create_product(db_session, "P2", price=100.0)
    p3 = _create_product(db_session, "P3", price=200.0)

    # Awkward numbers
    sale = Sale(
        document_number="INV-812-03",
        date=datetime.now(),
        total_amount=Decimal("333.33"),
        tax_vat=Decimal("33.33"),
        tax_sscl=Decimal("8.88"),
        net_revenue=Decimal("291.12"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=refund_user.id,
    )
    db_session.add(sale)
    db_session.flush()

    # Subtotals sum to 400.00, bill discount scaled it to 333.33
    i1 = _create_sale_item(sale.id, p1.id, Decimal("1"), Decimal("100.00"), Decimal("100.00"))
    i2 = _create_sale_item(sale.id, p2.id, Decimal("1"), Decimal("100.00"), Decimal("100.00"))
    i3 = _create_sale_item(sale.id, p3.id, Decimal("1"), Decimal("200.00"), Decimal("200.00"))
    pay = SalePayment(
        sale_id=sale.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("333.33")
    )
    db_session.add_all([i1, i2, i3, pay])
    db_session.commit()

    # 1. Refund i1
    RefundService.refund(
        sale.id, [RefundLineRequest(sale_item_id=i1.id, qty=Decimal("1"))], reason="R1", user_id=refund_user.id
    )
    # 2. Refund i2
    RefundService.refund(
        sale.id, [RefundLineRequest(sale_item_id=i2.id, qty=Decimal("1"))], reason="R2", user_id=refund_user.id
    )
    # 3. Refund i3 (final refund!)
    RefundService.refund(
        sale.id, [RefundLineRequest(sale_item_id=i3.id, qty=Decimal("1"))], reason="R3", user_id=refund_user.id
    )

    assert RefundService.refund_state(sale.id) == "FULL"

    # Query all refund sales
    refunds = db_session.query(Sale).filter(Sale.refund_of_sale_id == sale.id).all()
    assert len(refunds) == 3

    total_refunded = sum(abs(r.total_amount) for r in refunds)
    total_vat = sum(abs(r.tax_vat) for r in refunds)
    total_sscl = sum(abs(r.tax_sscl) for r in refunds)
    total_net = sum(abs(r.net_revenue) for r in refunds)

    assert total_refunded == Decimal("333.33")
    assert total_vat == Decimal("33.33")
    assert total_sscl == Decimal("8.88")
    assert total_net == Decimal("291.12")


def test_issue_812_tender_allocation_proportional(db_session, refund_user):
    """Cash 600 + Credit 400 on 1000 sale.
    Refund 300 -> CASH 180, CREDIT 120, customer debt falls by 120.
    """
    cust = Customer(name="Perera", phone="0771234567", current_debt=Decimal("400.00"))
    db_session.add(cust)
    db_session.flush()

    prod = _create_product(db_session, "P", price=100.0, stock=20.0)

    sale = Sale(
        document_number="INV-812-04",
        date=datetime.now(),
        total_amount=Decimal("1000.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("1000.00"),
        payment_method="SPLIT",
        status="COMPLETED",
        user_id=refund_user.id,
        customer_id=cust.id,
    )
    db_session.add(sale)
    db_session.flush()

    item = _create_sale_item(sale.id, prod.id, Decimal("10"), Decimal("100.00"), Decimal("1000.00"))
    pay_cash = SalePayment(
        sale_id=sale.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("600.00")
    )
    pay_credit = SalePayment(
        sale_id=sale.id, payment_method="Credit", method_kind=PaymentMethodKind.CREDIT, amount=Decimal("400.00")
    )
    db_session.add_all([item, pay_cash, pay_credit])
    db_session.commit()

    # Refund 3 units (value 300)
    preview = RefundService.preview(
        sale.id,
        [RefundLineRequest(sale_item_id=item.id, qty=Decimal("3"))],
    )
    assert preview.total_refund_amount == Decimal("300.00")
    tender_map = {t.kind: t.amount for t in preview.tenders}
    assert tender_map["CASH"] == Decimal("180.00")
    assert tender_map["CREDIT"] == Decimal("120.00")

    res = RefundService.refund(
        sale.id,
        [RefundLineRequest(sale_item_id=item.id, qty=Decimal("3"))],
        reason="Partial return",
        user_id=refund_user.id,
    )

    db_session.refresh(cust)
    # Debt was 400.00, reversed 120.00 -> 280.00
    assert cust.current_debt == Decimal("280.00")

    # Check refund sale payments
    refund_sale = db_session.get(Sale, res.refund_sale_id)
    rf_tenders = {p.method_kind: p.amount for p in refund_sale.payments}
    assert rf_tenders[PaymentMethodKind.CASH] == Decimal("-180.00")
    assert rf_tenders[PaymentMethodKind.CREDIT] == Decimal("-120.00")


def test_issue_812_override_to_cash_requires_reason_and_audits(db_session, refund_user, non_manager_user):
    """Override tender to CASH sends full value to cash, requires reason, and writes AuditLog."""
    cust = Customer(name="Kamal", phone="0779998888", current_debt=Decimal("500.00"))
    prod = _create_product(db_session, "Item", price=500.0)
    db_session.add(cust)
    db_session.flush()

    sale = Sale(
        document_number="INV-812-05",
        date=datetime.now(),
        total_amount=Decimal("500.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("500.00"),
        payment_method="Credit",
        status="COMPLETED",
        user_id=refund_user.id,
        customer_id=cust.id,
    )
    db_session.add(sale)
    db_session.flush()

    item = _create_sale_item(sale.id, prod.id, Decimal("1"), Decimal("500.00"), Decimal("500.00"))
    pay = SalePayment(
        sale_id=sale.id, payment_method="Credit", method_kind=PaymentMethodKind.CREDIT, amount=Decimal("500.00")
    )
    db_session.add_all([item, pay])
    db_session.commit()

    # 1. Missing reason raises ValueError("override_needs_reason")
    with pytest.raises(ValueError, match="override_needs_reason"):
        RefundService.refund(
            sale.id,
            [RefundLineRequest(sale_item_id=item.id, qty=Decimal("1"))],
            reason="Refund",
            user_id=refund_user.id,
            tender_override="CASH",
            override_reason="",
        )

    # 2. User without permission raises ValueError("permission_denied")
    with pytest.raises(ValueError, match="permission_denied"):
        RefundService.refund(
            sale.id,
            [RefundLineRequest(sale_item_id=item.id, qty=Decimal("1"))],
            reason="Refund",
            user_id=non_manager_user.id,
            tender_override="CASH",
            override_reason="Manager authorized cash refund",
        )

    # 3. Valid override succeeds and writes AuditLog
    res = RefundService.refund(
        sale.id,
        [RefundLineRequest(sale_item_id=item.id, qty=Decimal("1"))],
        reason="Refund",
        user_id=refund_user.id,
        tender_override="CASH",
        override_reason="Customer insisted on cash return",
    )
    assert res.total_refund_amount == Decimal("500.00")
    refund_sale = db_session.get(Sale, res.refund_sale_id)
    assert refund_sale.refund_tender_override == "CASH"

    # Customer debt unchanged since all was given back in CASH
    db_session.refresh(cust)
    assert cust.current_debt == Decimal("500.00")

    # Check AuditLog
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "REFUND_TENDER_OVERRIDE")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert "Customer insisted on cash return" in audit.details


def test_issue_812_weighed_item_partial_qty(db_session, refund_user):
    """Weighed item with 3-decimal quantity: 1.250 kg sold, 0.500 refunded."""
    prod = _create_product(db_session, "Sugar", price=200.0, stock=50.0, is_weighted=True)

    sale = Sale(
        document_number="INV-812-06",
        date=datetime.now(),
        total_amount=Decimal("250.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("250.00"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=refund_user.id,
    )
    db_session.add(sale)
    db_session.flush()

    item = _create_sale_item(sale.id, prod.id, Decimal("1.250"), Decimal("200.00"), Decimal("250.00"))
    pay = SalePayment(
        sale_id=sale.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("250.00")
    )
    db_session.add_all([item, pay])
    db_session.commit()

    res = RefundService.refund(
        sale.id,
        [RefundLineRequest(sale_item_id=item.id, qty=Decimal("0.500"))],
        reason="Weighed partial return",
        user_id=refund_user.id,
    )
    # 0.500 kg @ 200 = 100.00
    assert res.total_refund_amount == Decimal("100.00")

    db_session.refresh(prod)
    assert prod.stock_qty == Decimal("50.500")

    db_session.refresh(item)
    assert item.refunded_qty == Decimal("0.500")
    assert RefundService.refund_state(sale.id) == "PARTIAL"


def test_issue_812_service_item_no_stock_movement(db_session, refund_user):
    """Service items (is_service=True) record no stock movements on refund."""
    prod = _create_product(db_session, "Delivery Fee", price=300.0, stock=0.0, is_service=True)

    sale = Sale(
        document_number="INV-812-07",
        date=datetime.now(),
        total_amount=Decimal("300.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("300.00"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=refund_user.id,
    )
    db_session.add(sale)
    db_session.flush()

    item = _create_sale_item(sale.id, prod.id, Decimal("1"), Decimal("300.00"), Decimal("300.00"))
    pay = SalePayment(
        sale_id=sale.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("300.00")
    )
    db_session.add_all([item, pay])
    db_session.commit()

    movements_before = db_session.query(StockMovement).filter(StockMovement.product_id == prod.id).count()

    RefundService.refund(
        sale.id,
        [RefundLineRequest(sale_item_id=item.id, qty=Decimal("1"))],
        reason="Service not delivered",
        user_id=refund_user.id,
    )

    movements_after = db_session.query(StockMovement).filter(StockMovement.product_id == prod.id).count()
    assert movements_after == movements_before == 0


def test_issue_812_legacy_full_refund_counts_as_full(db_session, refund_user):
    """A historical sale that has a legacy full refund counts as FULL."""
    prod = _create_product(db_session, "Legacy Item", price=150.0)

    sale = Sale(
        document_number="INV-812-08",
        date=datetime.now(),
        total_amount=Decimal("150.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("150.00"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=refund_user.id,
    )
    db_session.add(sale)
    db_session.flush()

    # Line has refunded_qty=1 (set by backfill migration)
    item = _create_sale_item(
        sale.id,
        prod.id,
        Decimal("1"),
        Decimal("150.00"),
        Decimal("150.00"),
        refunded_qty=Decimal("1.000"),
    )
    db_session.add(item)

    legacy_refund = Sale(
        document_number="CN-812-LEGACY",
        date=datetime.now(),
        total_amount=Decimal("-150.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("-150.00"),
        payment_method="REFUND",
        status="COMPLETED",
        refund_of_sale_id=sale.id,
        user_id=refund_user.id,
    )
    db_session.add(legacy_refund)
    db_session.commit()

    assert RefundService.refund_state(sale.id) == "FULL"
    refundable = RefundService.refundable_lines(sale.id)
    assert len(refundable) == 1
    assert refundable[0].remaining_qty == Decimal("0.000")


def test_issue_812_failure_midway_leaves_nothing(db_session, refund_user):
    """Monkeypatch loyalty reversal to raise. Failure midway rolls back transaction cleanly:
    no refund Sale, no stock movement, no ledger row.
    """
    cust = Customer(name="Saman", phone="0770001111", current_debt=Decimal("0.00"))
    prod = _create_product(db_session, "FailItem", price=200.0, stock=10.0)
    db_session.add(cust)
    db_session.flush()

    sale = Sale(
        document_number="INV-812-09",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("200.00"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=refund_user.id,
        customer_id=cust.id,
        loyalty_points_earned=20,
    )
    db_session.add(sale)
    db_session.flush()

    item = _create_sale_item(sale.id, prod.id, Decimal("1"), Decimal("200.00"), Decimal("200.00"))
    pay = SalePayment(
        sale_id=sale.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("200.00")
    )
    db_session.add_all([item, pay])
    db_session.commit()

    with patch(
        "cbpos.core.services.loyalty_service.LoyaltyService.reverse_sale_points",
        side_effect=RuntimeError("Loyalty failure"),
    ):
        with pytest.raises(RuntimeError, match="Loyalty failure"):
            RefundService.refund(
                sale.id,
                [RefundLineRequest(sale_item_id=item.id, qty=Decimal("1"))],
                reason="Midway fail",
                user_id=refund_user.id,
            )

    # Verify no refund sale created
    refunds = db_session.query(Sale).filter(Sale.refund_of_sale_id == sale.id).all()
    assert len(refunds) == 0

    # Stock unchanged
    db_session.refresh(prod)
    assert prod.stock_qty == Decimal("10.0")

    # Item refunded_qty unchanged
    db_session.refresh(item)
    assert item.refunded_qty == Decimal("0.000")


def test_issue_915_refund_states_batched(db_session, refund_user):
    """RefundService.refund_states correctly classifies sales in a single batch query (#915)."""
    p = _create_product(db_session, "BatchItem", price=100.0, stock=20.0)

    # Sale 1: no refund
    s1 = Sale(
        document_number="INV-915-01",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=refund_user.id,
    )
    db_session.add(s1)
    db_session.flush()
    i1 = _create_sale_item(s1.id, p.id, Decimal("2"), Decimal("100.00"), Decimal("200.00"))
    pay1 = SalePayment(
        sale_id=s1.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("200.00")
    )
    db_session.add_all([i1, pay1])

    # Sale 2: partial refund
    s2 = Sale(
        document_number="INV-915-02",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=refund_user.id,
    )
    db_session.add(s2)
    db_session.flush()
    i2 = _create_sale_item(s2.id, p.id, Decimal("2"), Decimal("100.00"), Decimal("200.00"))
    pay2 = SalePayment(
        sale_id=s2.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("200.00")
    )
    db_session.add_all([i2, pay2])

    # Sale 3: full refund
    s3 = Sale(
        document_number="INV-915-03",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=refund_user.id,
    )
    db_session.add(s3)
    db_session.flush()
    i3 = _create_sale_item(s3.id, p.id, Decimal("1"), Decimal("100.00"), Decimal("100.00"))
    pay3 = SalePayment(
        sale_id=s3.id, payment_method="Cash", method_kind=PaymentMethodKind.CASH, amount=Decimal("100.00")
    )
    db_session.add_all([i3, pay3])
    db_session.commit()

    # Refund 1 qty on s2 (partial)
    RefundService.refund(
        s2.id,
        [RefundLineRequest(sale_item_id=i2.id, qty=Decimal("1"))],
        reason="Partial return",
        user_id=refund_user.id,
    )

    # Refund 1 qty on s3 (full)
    RefundService.refund(
        s3.id,
        [RefundLineRequest(sale_item_id=i3.id, qty=Decimal("1"))],
        reason="Full return",
        user_id=refund_user.id,
    )

    states = RefundService.refund_states([s1.id, s2.id, s3.id])
    assert states[s1.id] == "NONE"
    assert states[s2.id] == "PARTIAL"
    assert states[s3.id] == "FULL"


def test_refund_service_itemless_sale(db_session, refund_user):
    """Itemless sales (e.g. synthetic sync test sales or legacy entries) can be refunded fully."""
    sale = Sale(
        document_number="TEST-ITEMLESS-001",
        date=datetime.now(),
        user_id=refund_user.id,
        terminal_id="TERM-01",
        origin_terminal_id="TERM-01",
        total_amount=Decimal("300.00"),
        net_revenue=Decimal("300.00"),
        payment_method="CASH",
        status=DocumentStatus.COMPLETED,
    )
    db_session.add(sale)
    db_session.commit()

    preview = RefundService.preview(sale.id, [])
    assert preview.total_refund_amount == Decimal("300.00")
    assert preview.is_full_refund is True

    res = RefundService.refund(sale.id, [], "Customer refund", refund_user.id)
    assert res.total_refund_amount == Decimal("300.00")
    assert res.refund_sale.refund_of_sale_id == sale.id

    # Trying to refund again fails
    with pytest.raises(ValueError, match="qty_exceeds_remaining"):
        RefundService.refund(sale.id, [], "Customer refund again", refund_user.id)


@pytest.mark.domain
def test_migration_refund_lines(tmp_path, monkeypatch):
    """Alembic upgrade adds refund columns, check constraints, backfills legacy rows, and downgrades cleanly."""
    db_path = tmp_path / "cbpos.db"
    uri = f"sqlite:///{db_path}"
    engine = create_engine(uri)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "DB_URI", uri)

    cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False

    # 1. Stamp head and downgrade to 4a5b6c7d8e9f
    command.stamp(cfg, "head")
    command.downgrade(cfg, "4a5b6c7d8e9f")

    # 2. Insert older rows before the migration
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        # Roles and admin user
        conn.execute("INSERT OR IGNORE INTO roles (id, name) VALUES (1, 'Admin')")
        conn.execute("INSERT OR IGNORE INTO roles (id, name) VALUES (2, 'Manager')")
        conn.execute("INSERT OR IGNORE INTO users (id, username, role_id) VALUES (1, 'admin', 1)")

        # Product
        conn.execute(
            "INSERT INTO products (id, name_en, barcode, price, cost, stock_qty, is_weighted, is_composite, is_service, price_change_allowed, is_age_restricted, reorder_point, preferred_qty, is_active, version_id, last_modified) "
            "VALUES (1, 'Test Product', 'BAR-MIG-1', 100.0, 50.0, 10.0, 0, 0, 0, 1, 0, 0.0, 0.0, 1, 1, '2026-01-01 00:00:00')"
        )

        # Original sale & items (without refunded_qty / refund_of_item_id / refund_tender_override)
        conn.execute(
            "INSERT INTO documents (id, document_number, type, date, user_id, status, synced) "
            "VALUES (101, 'INV-MIG-1', 'SALE', '2026-01-01 10:00:00', 1, 'COMPLETED', 0)"
        )
        conn.execute(
            "INSERT INTO sales (id, total_amount, tax_vat, tax_sscl, net_revenue, "
            "additional_discount_type, additional_discount_value, loyalty_points_redeemed, loyalty_points_value, loyalty_points_earned, payment_method) "
            "VALUES (101, 200.0, 0.0, 0.0, 200.0, 'NONE', 0.0, 0, 0.0, 0, 'CASH')"
        )
        conn.execute(
            "INSERT INTO sale_items (id, sale_id, product_id, qty, unit_price, original_price, discount_type, discount_value, is_manual_price, subtotal) "
            "VALUES (201, 101, 1, 2.0, 100.0, 100.0, 'NONE', 0.0, 0, 200.0)"
        )

        # Legacy full refund sale referencing original sale 101
        conn.execute(
            "INSERT INTO documents (id, document_number, type, date, user_id, status, synced) "
            "VALUES (102, 'RET-MIG-1', 'SALE', '2026-01-01 11:00:00', 1, 'COMPLETED', 0)"
        )
        conn.execute(
            "INSERT INTO sales (id, total_amount, tax_vat, tax_sscl, net_revenue, "
            "additional_discount_type, additional_discount_value, loyalty_points_redeemed, loyalty_points_value, loyalty_points_earned, payment_method, refund_of_sale_id) "
            "VALUES (102, -200.0, 0.0, 0.0, -200.0, 'NONE', 0.0, 0, 0.0, 0, 'REFUND', 101)"
        )
        conn.commit()

    # 3. Upgrade to head
    command.upgrade(cfg, "head")

    # 4. Verify columns, backfill, and permissions
    engine = create_engine(uri)
    with engine.connect() as conn:
        # Check sales table has refund_tender_override
        sales_cols = [c[1] for c in conn.execute(text("PRAGMA table_info(sales)")).fetchall()]
        assert "refund_tender_override" in sales_cols

        # Check sale_items table has refund columns
        items_cols = [c[1] for c in conn.execute(text("PRAGMA table_info(sale_items)")).fetchall()]
        assert "refund_of_item_id" in items_cols
        assert "refund_reason" in items_cols
        assert "refunded_qty" in items_cols

        # Check backfill: original line 201 must have refunded_qty == 2.0
        row = conn.execute(text("SELECT refunded_qty FROM sale_items WHERE id = 201")).fetchone()
        assert row is not None and float(row[0]) == 2.0

        # Check permission sales.refund_override_tender is seeded
        perm = conn.execute(text("SELECT id FROM permissions WHERE code = 'sales.refund_override_tender'")).fetchone()
        assert perm is not None

    engine.dispose()

    # 5. Verify downgrade cleans up columns without error
    command.downgrade(cfg, "4a5b6c7d8e9f")
    engine = create_engine(uri)
    with engine.connect() as conn:
        sales_cols = [c[1] for c in conn.execute(text("PRAGMA table_info(sales)")).fetchall()]
        assert "refund_tender_override" not in sales_cols
        items_cols = [c[1] for c in conn.execute(text("PRAGMA table_info(sale_items)")).fetchall()]
        assert "refund_of_item_id" not in items_cols
    engine.dispose()
