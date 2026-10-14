"""
#715: voiding or refunding a credit sale must give the credit back.

Neither path wrote a CustomerLedgerEntry, so ``Customer.current_debt`` kept
the voided/refunded amount -- and since LAN Sync (#678) moves balances only
through ledger rows, the Main PC and other tills kept it too.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import AuditLog, Customer, CustomerLedgerEntry, Permission, Product, Role, Sale, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.transaction_service import TransactionService

_counter = 0


@pytest.fixture
def user(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"credit715_{_counter}")
    role = Role(name=f"Credit715Role_{_counter}", permissions=[permission])
    u = User(username=f"credit715_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, u])
    db_session.flush()
    return u


@pytest.fixture
def product(db_session):
    global _counter
    _counter += 1
    p = Product(
        name_en=f"Credit715_{_counter}", price=Decimal("100.00"), stock_qty=Decimal("50"), barcode=f"715-{_counter}"
    )
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture
def customer(db_session):
    c = Customer(name="Credit 715", credit_limit=Decimal("10000.00"), current_debt=Decimal("50.00"))
    db_session.add(c)
    db_session.flush()
    return c


def _sell(db_session, user, product, customer, payments: list[tuple[str, str]], qty: str = "2") -> Sale:
    """Ring up ``qty`` x 100.00 through TransactionService with the given (method, amount) payments."""
    db_session.commit()
    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
        patch("cbpos.core.services.transaction_service.PrintWorker"),
    ):
        cart = CartService()
        cart.add_item(product, qty=Decimal(qty))
        sale = TransactionService.process_sale(
            cart, [{"method": m, "amount": Decimal(a)} for m, a in payments], customer_id=customer.id
        )
    assert sale is not None
    return sale


def _debt(db_session, customer) -> Decimal:
    db_session.expire_all()
    return db_session.get(Customer, customer.id).current_debt


def _reversals(db_session, customer) -> list[CustomerLedgerEntry]:
    db_session.expire_all()
    return (
        db_session.query(CustomerLedgerEntry)
        .filter(
            CustomerLedgerEntry.customer_id == customer.id,
            CustomerLedgerEntry.entry_type.in_(("VOID", "REFUND")),
        )
        .order_by(CustomerLedgerEntry.id)
        .all()
    )


class TestVoidCreditSale:
    def test_void_returns_debt_to_previous_value(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])
        assert _debt(db_session, customer) == Decimal("250.00")

        assert TransactionService.void_sale(sale.id, user.id, "Wrong customer") is True

        assert _debt(db_session, customer) == Decimal("50.00")
        [entry] = _reversals(db_session, customer)
        assert entry.entry_type == "VOID"
        assert entry.amount == Decimal("-200.00")
        assert entry.balance_after == Decimal("50.00")
        assert entry.reference_id == sale.id
        assert entry.reference_doc == sale.document_number
        assert entry.synced is False  # queued for LAN Sync like any other ledger row

    def test_void_of_mixed_payment_reverses_only_the_credit_part(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        assert _debt(db_session, customer) == Decimal("130.00")

        TransactionService.void_sale(sale.id, user.id, "Mistake")

        assert _debt(db_session, customer) == Decimal("50.00")
        [entry] = _reversals(db_session, customer)
        assert entry.amount == Decimal("-80.00")

    def test_void_of_cash_sale_writes_no_ledger_row(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "200.00")])

        TransactionService.void_sale(sale.id, user.id, "Mistake")

        assert _reversals(db_session, customer) == []
        assert _debt(db_session, customer) == Decimal("50.00")

    def test_void_is_audited(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])

        TransactionService.void_sale(sale.id, user.id, "Mistake")

        db_session.expire_all()
        log = db_session.query(AuditLog).filter(AuditLog.action == "CREDIT_REVERSAL").one()
        assert sale.document_number in log.details
        assert "200.00" in log.details


class TestRefundCreditSale:
    def test_refund_returns_debt_to_previous_value(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])

        assert TransactionService.process_refund(sale.id, "Returned", user.id) is True

        assert _debt(db_session, customer) == Decimal("50.00")
        [entry] = _reversals(db_session, customer)
        refund = db_session.query(Sale).filter(Sale.refund_of_sale_id == sale.id).one()
        assert entry.entry_type == "REFUND"
        assert entry.amount == Decimal("-200.00")
        assert entry.balance_after == Decimal("50.00")
        assert entry.reference_id == sale.id
        assert entry.reference_doc == refund.document_number

    def test_refund_of_mixed_payment_reverses_only_the_credit_part(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "150.00"), ("Credit", "50.00")])

        TransactionService.process_refund(sale.id, "Returned", user.id)

        assert _debt(db_session, customer) == Decimal("50.00")
        assert [e.amount for e in _reversals(db_session, customer)] == [Decimal("-50.00")]

    def test_voiding_a_refunded_sale_does_not_reverse_the_credit_twice(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])
        TransactionService.process_refund(sale.id, "Returned", user.id)

        TransactionService.void_sale(sale.id, user.id, "Oops")

        assert _debt(db_session, customer) == Decimal("50.00")
        assert len(_reversals(db_session, customer)) == 1


class TestPartialRefundRule:
    """No partial-refund screen exists yet; the rule lives in the service."""

    def test_partial_refund_reverses_its_credit_share(self, db_session, user, product, customer):
        # 200.00 sale: 120 cash + 80 credit. Refunding 100.00 (half) gives back 40.00 of credit.
        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        sale_row = db_session.get(Sale, sale.id)
        entry = CustomerCreditService.reverse_credit_sale_in_session(
            db_session, sale_row, "REFUND", user.id, "RET-PART-1", refund_amount=Decimal("100.00")
        )
        db_session.flush()

        assert entry.amount == Decimal("-40.00")
        assert _debt(db_session, customer) == Decimal("90.00")

    def test_repeated_partial_refunds_never_exceed_the_credit(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        sale_row = db_session.get(Sale, sale.id)
        for doc in ("RET-1", "RET-2", "RET-3"):
            CustomerCreditService.reverse_credit_sale_in_session(
                db_session, sale_row, "REFUND", user.id, doc, refund_amount=Decimal("150.00")
            )
        db_session.flush()

        assert sum(e.amount for e in _reversals(db_session, customer)) == Decimal("-80.00")
        assert _debt(db_session, customer) == Decimal("50.00")
