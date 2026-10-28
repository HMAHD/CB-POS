"""#734: the refund handed to the peripherals prints with no database session.

The port is called after the refund's session has committed and closed, so
the production adapter gets a *detached* refund document. The voucher is
built inside the session (``_build_refund_receipt``); this checks that
nothing the hardware path reads afterwards needs the session.

As in ``test_sale_receipt_after_detach.py``, the shared ``db_session`` is
made to behave like the app's sessions (no expiry on commit, starts empty,
emptied where the app's session closes), and the production adapter runs on
the detached event. Only the print queue is stubbed.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from cbpos.core.interfaces.transaction_peripherals import RefundCompleted
from cbpos.core.models import Customer, Permission, Product, Role, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import translate_in
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.infrastructure.hardware.print_worker_peripherals import PrintWorkerPeripherals

_counter = 0


def _next() -> int:
    global _counter
    _counter += 1
    return _counter


def _list_price(product, customer=None):
    return {"final_price": product.price, "original_price": product.price, "applied_rule": "Standard Price"}


@pytest.fixture
def settings(monkeypatch):
    values = dict(ConfigService.DEFAULTS)
    values.update(receipt_language="en", auto_print_receipt=True, receipt_copies=1, terminal_id="TERM-01")
    monkeypatch.setattr(ConfigService, "get", lambda key, *_a: values.get(key))
    monkeypatch.setattr(ConfigService, "get_all", lambda: dict(values))
    return values


@pytest.fixture
def print_queue():
    """The shared PrintWorker's queue -- the one stubbed step for the voucher."""
    worker = MagicMock()
    with patch.object(PrintWorker, "instance", return_value=worker):
        yield worker


@pytest.fixture
def cashier(db_session):
    n = _next()
    permission = Permission(code=f"detach734_{n}")
    role = Role(name=f"Detach734Role_{n}", permissions=[permission])
    user = User(username=f"cashier734_{n}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@contextmanager
def _sessions_like_the_app(db_session: Session) -> Iterator[None]:
    """Keep loaded state across commits, as the app's ``expire_on_commit=False`` sessions do."""
    with patch.object(db_session, "expire_on_commit", False), patch.object(db_session, "expire_all"):
        yield


class _DetachOnClose:
    """Peripherals that empty the session first -- what closing the app's refund session does."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.events: list[RefundCompleted] = []

    def sale_completed(self, event) -> None:
        raise AssertionError("not a sale")

    def refund_completed(self, event: RefundCompleted) -> None:
        self._session.expunge_all()
        self.events.append(event)


def _sell(
    db_session: Session, cashier: User, product: Product, payments: list[tuple[str, str]], customer=None
) -> tuple[int, str]:
    """Ring up two of ``product``; return the sale's (id, document number), read while it is loaded."""
    db_session.commit()
    with (
        patch("cbpos.core.services.cart_service.PricingService.calculate_price", side_effect=_list_price),
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=cashier),
    ):
        cart = CartService()
        cart.add_item(product, qty=Decimal("2"))
        sale = TransactionService.process_sale(
            cart, [{"method": m, "amount": Decimal(a)} for m, a in payments], customer.id if customer else None
        )
    assert sale is not None
    return sale.id, sale.document_number


def _refund_detached(db_session: Session, sale_id: int, cashier_id: int) -> RefundCompleted:
    """Refund the sale through the real path and return the event the hardware gets, detached."""
    db_session.commit()
    detach = _DetachOnClose(db_session)
    with _sessions_like_the_app(db_session):
        db_session.expunge_all()  # the app's refund session starts empty
        assert TransactionService.process_refund(sale_id, "Damaged", cashier_id, peripherals=detach) is True

    (event,) = detach.events
    assert inspect(event.refund_sale).detached
    return event


def _printed_lines(print_queue: MagicMock, event: RefundCompleted) -> list[str]:
    """Run the production adapter on the detached refund; return the queued voucher's text lines."""
    PrintWorkerPeripherals().refund_completed(event)
    ((job_type, commands),) = [c.args for c in print_queue.add_job.call_args_list]
    assert job_type == "print_receipt"
    return [c.get("val", "") for c in commands if c.get("type") == "text"]


def _mentions(lines: list[str], text: str) -> bool:
    return any(text in line for line in lines)


@pytest.mark.usefixtures("settings")
class TestDetachedRefundPrints:
    def test_cash_sale_refund(self, db_session, cashier, print_queue):
        rice = Product(name_en="Samba Rice 5kg", price=Decimal("1250.00"), stock_qty=Decimal("20"), barcode="734-1")
        db_session.add(rice)
        db_session.flush()
        cashier_id, cashier_name = cashier.id, cashier.username
        sale_id, sale_no = _sell(db_session, cashier, rice, [("CASH", "2500.00")])

        event = _refund_detached(db_session, sale_id, cashier_id)

        assert event.refund_sale.document_number.startswith("CN-")
        assert event.refund_sale.total_amount == Decimal("-2500.00")
        lines = _printed_lines(print_queue, event)
        assert _mentions(lines, sale_no)
        assert _mentions(lines, "Samba Rice 5kg")
        assert _mentions(lines, cashier_name)
        assert not _mentions(lines, translate_in("en", "receipt_strings.refund_off_credit", amount=""))

    def test_credit_sale_refund_shows_the_credit_given_back(self, db_session, cashier, print_queue):
        dhal = Product(name_en="Mysore Dhal 1kg", price=Decimal("400.00"), stock_qty=Decimal("20"), barcode="734-2")
        customer = Customer(name=f"Kamala Stores {_next()}", credit_limit=Decimal("5000.00"))
        db_session.add_all([dhal, customer])
        db_session.flush()
        cashier_id, customer_id = cashier.id, customer.id
        sale_id, sale_no = _sell(db_session, cashier, dhal, [("CASH", "300.00"), ("CREDIT", "500.00")], customer)

        event = _refund_detached(db_session, sale_id, cashier_id)

        assert event.refund_sale.customer_id == customer_id
        lines = _printed_lines(print_queue, event)
        assert _mentions(lines, sale_no)
        assert _mentions(lines, "Mysore Dhal 1kg")
        assert _mentions(lines, translate_in("en", "receipt_strings.refund_off_credit", amount=format_currency("500")))
        assert _mentions(lines, translate_in("en", "receipt_strings.refund_given_back", amount=format_currency("300")))
