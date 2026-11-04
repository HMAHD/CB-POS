"""
Phase 3A Exit Gate: Money Invariants Integration Test.

Runs a day's lifecycle:
- Shift start with starting float
- Sale with change given (cash over-tender)
- Credit sale
- Split payment (Cash + Card)
- Quick Pay (F12 cash)
- Customer debt adjustment
- Partial refund
- Full refund
Then validates Invariants 1-7 from Phase 3A brief.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import PaymentMethodKind
from cbpos.core.models import (
    Customer,
    CustomerLedgerEntry,
    PaymentMethod,
    Permission,
    Product,
    Role,
    Sale,
    User,
)
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.payment_service import PaymentService
from cbpos.core.services.refund_service import RefundLineRequest, RefundService
from cbpos.core.services.shift_service import ShiftService
from cbpos.core.services.transaction_service import TransactionService

_seq = 0


@pytest.fixture
def inv_user(db_session):
    global _seq
    _seq += 1
    role = Role(name=f"InvRole_{_seq}")
    db_session.add(role)
    db_session.flush()

    for code in (Permissions.SALES_REFUND, Permissions.SALES_VOID):
        perm = db_session.query(Permission).filter_by(code=code).first()
        if not perm:
            perm = Permission(code=code, description=code)
            db_session.add(perm)
        role.permissions.append(perm)

    user = User(username=f"inv_user_{_seq}", pin_hash="hash", role=role)
    db_session.add(user)
    db_session.flush()
    return user


def test_money_invariants_full_day_lifecycle(db_session, inv_user):
    """Integration test executing a complete daily shop lifecycle and asserting Invariants 1-7."""
    global _seq
    _seq += 1

    # 0. Setup active payment methods
    cash_pm = db_session.query(PaymentMethod).filter_by(kind=PaymentMethodKind.CASH).first()
    if not cash_pm:
        cash_pm = PaymentMethod(name="Cash", kind=PaymentMethodKind.CASH, is_cash=True, is_active=True)
        db_session.add(cash_pm)
    card_pm = db_session.query(PaymentMethod).filter_by(kind=PaymentMethodKind.CARD).first()
    if not card_pm:
        card_pm = PaymentMethod(name="Card", kind=PaymentMethodKind.CARD, is_cash=False, is_active=True)
        db_session.add(card_pm)
    credit_pm = db_session.query(PaymentMethod).filter_by(kind=PaymentMethodKind.CREDIT).first()
    if not credit_pm:
        credit_pm = PaymentMethod(name="Credit", kind=PaymentMethodKind.CREDIT, is_cash=False, is_active=True)
        db_session.add(credit_pm)
    db_session.commit()

    # Products & Customer
    p1 = Product(name_en=f"Item A {_seq}", barcode=f"INV-A-{_seq}", price=Decimal("100.00"), stock_qty=Decimal("100"))
    p2 = Product(
        name_en=f"Item B {_seq}",
        barcode=f"INV-B-{_seq}",
        price=Decimal("150.00"),
        stock_qty=Decimal("100"),
        is_weighted=True,
    )
    cust = Customer(name=f"Customer {_seq}", credit_limit=Decimal("10000.00"), current_debt=Decimal("0.00"))
    db_session.add_all([p1, p2, cust])
    db_session.commit()

    shift_service = ShiftService()
    start_float = Decimal("5000.00")
    shift = shift_service.start_shift(inv_user.id, start_float)

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=inv_user):
        # 1. Sale with change given (Rs 200 bill, Rs 1000 cash tendered, Rs 800 change)
        cart1 = CartService()
        cart1.add_item(p1, qty=Decimal("2.000"))  # 200.00
        sale1 = TransactionService.process_sale(
            cart1,
            [{"method": "Cash", "amount": Decimal("1000.00")}],  # overtender
        )
        assert sale1 is not None

        # 2. Credit sale (Rs 300 bill charged to customer credit)
        cart2 = CartService()
        cart2.add_item(p1, qty=Decimal("3.000"))  # 300.00
        sale2 = TransactionService.process_sale(
            cart2,
            [{"method": "Credit", "amount": Decimal("300.00")}],
            customer_id=cust.id,
        )
        assert sale2 is not None

        # 3. Split payment (Rs 450: Rs 150 Cash + Rs 300 Card)
        cart3 = CartService()
        cart3.add_item(p2, qty=Decimal("3.000"))  # 450.00
        sale3 = TransactionService.process_sale(
            cart3,
            [
                {"method": "Cash", "amount": Decimal("150.00")},
                {"method": "Card", "amount": Decimal("300.00")},
            ],
        )
        assert sale3 is not None

        # 4. F12 Quick Pay (Rs 100 Cash)
        default_cash = PaymentService.get_default_cash_method()
        assert default_cash is not None
        cart4 = CartService()
        cart4.add_item(p1, qty=Decimal("1.000"))  # 100.00
        sale4 = TransactionService.process_sale(
            cart4,
            [{"method": default_cash.name, "amount": Decimal("100.00")}],
        )
        assert sale4 is not None

        # 5. Customer debt adjustment (+50.00 adjustment)
        CustomerCreditService.record_adjustment(
            cust.id,
            Decimal("50.00"),
            "Correction note",
            inv_user.id,
        )

        # 6. Partial refund on sale1 (1 item of p1 = Rs 100.00 refunded)
        item_to_refund = sale1.items[0]
        res_partial = RefundService.refund(
            sale1.id,
            [RefundLineRequest(sale_item_id=item_to_refund.id, qty=Decimal("1.000"))],
            reason="Partial customer return",
            user_id=inv_user.id,
        )
        assert res_partial is not None
        assert res_partial.total_refund_amount == Decimal("100.00")

        # 7. Full refund on sale3 (split payment: Rs 150 cash + Rs 300 card refunded)
        res_full = TransactionService.process_refund(sale3.id, "Full return split sale", inv_user.id)
        assert res_full is True

    # ── VALIDATE INVARIANTS 1-7 ──────────────────────────────────────────

    # Invariant 1: For every sale, sum(SalePayment.amount) == Sale.total_amount
    all_sales = db_session.query(Sale).all()
    for s in all_sales:
        if s.payment_method == "REFUND":
            # Refund doc has negative amounts
            expected = -abs(s.total_amount)
            actual = sum(p.amount for p in s.payments)
            assert actual == expected, f"Sale {s.document_number}: payment sum {actual} != total {expected}"
        else:
            actual = sum(p.amount for p in s.payments)
            assert actual == s.total_amount, f"Sale {s.document_number}: payment sum {actual} != total {s.total_amount}"

    # Invariant 2: Non-cash payments never exceed amount due
    for s in all_sales:
        for p in s.payments:
            if p.method_kind != PaymentMethodKind.CASH:
                assert p.tendered_amount is None or p.tendered_amount == p.amount

    # Invariant 3: expected_cash = starting_cash + sum(CASH-kind SalePayment.amount)
    summary = shift_service.get_shift_summary(shift.id)
    # Expected cash:
    # Starting: 5000.00
    # Sale 1 cash: +200.00
    # Sale 3 cash: +150.00
    # Sale 4 cash: +100.00
    # Refund 1 cash: -100.00
    # Refund on Sale 3 cash: -150.00
    # Net cash delta = 200 + 150 + 100 - 100 - 150 = 200.00
    # Expected drawer cash = 5200.00
    assert summary["expected_cash"] == Decimal("5200.00")
    assert summary["cash_sales"] == Decimal("200.00")

    # Invariant 4: current_debt == sum(CustomerLedgerEntry.amount)
    db_session.refresh(cust)
    ledger_entries = db_session.query(CustomerLedgerEntry).filter_by(customer_id=cust.id).all()
    ledger_sum = sum(e.amount for e in ledger_entries)
    assert cust.current_debt == ledger_sum
    # Sale 2 (+300) + Adjustment (+50) = 350.00
    assert cust.current_debt == Decimal("350.00")

    # Invariant 5: For every sale line, refunded_qty <= qty, and sum(refund totals) <= total_amount
    for s in all_sales:
        if s.payment_method != "REFUND":
            for item in s.items:
                assert item.refunded_qty <= item.qty
            refund_states = RefundService.refund_state(s.id)
            if s.id == sale1.id:
                assert refund_states == "PARTIAL"
            elif s.id == sale3.id:
                assert refund_states == "FULL"

    # Invariant 6: A sale with any refund cannot be voided; a refund document cannot be voided
    with pytest.raises(ValueError, match="sale_has_refund"):
        TransactionService.void_sale(sale1.id, inv_user.id, "Try void partial")

    with pytest.raises(ValueError, match="sale_has_refund"):
        TransactionService.void_sale(sale3.id, inv_user.id, "Try void full")

    refund_sales = db_session.query(Sale).filter(Sale.payment_method == "REFUND").all()
    assert len(refund_sales) >= 2
    for r_sale in refund_sales:
        with pytest.raises(ValueError, match="cannot_void_refund"):
            TransactionService.void_sale(r_sale.id, inv_user.id, "Try void refund doc")

    # Invariant 7: Credit reversed on a sale never exceeds credit charged on that sale
    credit_reversed_sale2 = CustomerCreditService.credit_already_reversed(sale2.id)
    assert credit_reversed_sale2 <= Decimal("300.00")
