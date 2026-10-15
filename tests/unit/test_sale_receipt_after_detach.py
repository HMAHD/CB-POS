"""#733: the sale handed to the peripherals prints with no database session.

The port is called after the sale's session has committed and closed, so the
receipt (and the A4 Tax Invoice) is built from a *detached* sale. Anything
the builders read that wasn't loaded inside the session raises
``DetachedInstanceError`` -- in the shop, a sale that saved but never printed.

The shared ``db_session`` fixture normally hides that: it expires everything
on every commit and never really closes, so a later access just reloads.
Here it is made to behave like the app's sessions instead (no expiry on
commit, starts empty, and is emptied where the app's session closes), and
the production builders run on the detached sale. Only the print queue and
the A4 printer hand-off are stubbed.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfReader
from sqlalchemy.orm import Session

from cbpos.core.interfaces.transaction_peripherals import SaleCompleted
from cbpos.core.models import CompositeItem, Customer, Permission, Product, Role, Unit, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.printer_service import PrinterService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

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
    values.update(
        receipt_language="en",
        auto_print_receipt=True,
        show_receipt_dialog=False,
        receipt_copies=1,
        show_cashier_on_receipt=True,
        a4_printer_name=None,
    )
    monkeypatch.setattr(ConfigService, "get", lambda key, *_a: values.get(key))
    monkeypatch.setattr(ConfigService, "get_all", lambda: dict(values))
    return values


@pytest.fixture
def print_queue():
    """The shared PrintWorker's queue -- the one stubbed step for the receipt."""
    worker = MagicMock()
    with patch.object(PrintWorker, "instance", return_value=worker):
        yield worker


@pytest.fixture
def cashier(db_session):
    n = _next()
    permission = Permission(code=f"detach733_{n}")
    role = Role(name=f"Detach733Role_{n}", permissions=[permission])
    user = User(username=f"cashier733_{n}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


def _product(db_session: Session, name: str, price: str, stock: str, **extra: Any) -> Product:
    product = Product(name_en=name, price=Decimal(price), stock_qty=Decimal(stock), barcode=f"733-{_next()}", **extra)
    db_session.add(product)
    db_session.flush()
    return product


@contextmanager
def _sessions_like_the_app(db_session: Session) -> Iterator[None]:
    """Keep loaded state across commits, as the app's ``expire_on_commit=False`` sessions do."""
    with patch.object(db_session, "expire_on_commit", False), patch.object(db_session, "expire_all"):
        yield


class _DetachOnClose:
    """Peripherals that empty the session first -- what closing the app's sale session does."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.events: list[SaleCompleted] = []

    def sale_completed(self, event: SaleCompleted) -> None:
        self._session.expunge_all()
        self.events.append(event)

    def refund_completed(self, event) -> None:
        raise AssertionError("not a refund")


def _ring_up(
    db_session: Session,
    cashier: User,
    lines: list[tuple[Product, str]],
    payments: list[tuple[str, str]],
    customer: Customer | None = None,
) -> SaleCompleted:
    """Sell ``lines`` through the real sale path and return the event the hardware gets, detached."""
    db_session.commit()
    detach = _DetachOnClose(db_session)
    with (
        _sessions_like_the_app(db_session),
        patch("cbpos.core.services.cart_service.PricingService.calculate_price", side_effect=_list_price),
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=cashier),
    ):
        for obj in list(db_session.identity_map.values()):
            db_session.refresh(obj)
        cart = CartService()
        for product, qty in lines:
            cart.add_item(product, qty=Decimal(qty))
        customer_id = customer.id if customer else None
        db_session.expunge_all()  # the app's sale session starts empty; cart products come in detached
        sale = TransactionService.process_sale(
            cart, [{"method": m, "amount": Decimal(a)} for m, a in payments], customer_id, peripherals=detach
        )

    assert sale is not None
    (event,) = detach.events
    assert event.sale is sale
    assert sale not in db_session
    return event


def _printed_lines(print_queue: MagicMock, event: SaleCompleted) -> list[str]:
    """Run the production auto-print on the detached sale; return the queued receipt's text lines."""
    assert PrinterService.print_transaction(event.sale) is True
    ((job_type, commands),) = [c.args for c in print_queue.add_job.call_args_list]
    assert job_type == "print_receipt"
    return [c.get("val", "") for c in commands if c.get("type") == "text"]


def _mentions(lines: list[str], text: str) -> bool:
    return any(text in line for line in lines)


@pytest.mark.usefixtures("settings")
class TestDetachedSalePrints:
    def test_walk_in_cash_sale(self, db_session, cashier, print_queue):
        rice = _product(db_session, "Samba Rice 5kg", "1250.00", "20")

        event = _ring_up(db_session, cashier, [(rice, "2")], [("CASH", "2500.00")])

        lines = _printed_lines(print_queue, event)
        assert _mentions(lines, "Samba Rice 5kg")
        assert _mentions(lines, cashier.username)

    def test_customer_sale_split_cash_and_credit(self, db_session, cashier, print_queue):
        dhal = _product(db_session, "Mysore Dhal 1kg", "400.00", "20")
        customer = Customer(name=f"Kamala Stores {_next()}", credit_limit=Decimal("5000.00"))
        db_session.add(customer)
        db_session.flush()

        event = _ring_up(
            db_session, cashier, [(dhal, "3")], [("CASH", "500.00"), ("CREDIT", "700.00")], customer=customer
        )

        assert event.payment_methods == ("CASH", "CREDIT")
        lines = _printed_lines(print_queue, event)
        assert _mentions(lines, customer.name)
        assert _mentions(lines, "Mysore Dhal 1kg")
        assert _mentions(lines, cashier.username)

    def test_vat_registered_customer_sale_receipt(self, db_session, cashier, print_queue):
        cement = _product(db_session, "Cement 50kg", "2360.00", "40")
        customer = Customer(name=f"Lanka Builders {_next()}", vat_number="114567890-7000")
        db_session.add(customer)
        db_session.flush()

        event = _ring_up(db_session, cashier, [(cement, "1")], [("CASH", "2360.00")], customer=customer)

        assert event.sale.customer.vat_number == "114567890-7000"
        lines = _printed_lines(print_queue, event)
        assert _mentions(lines, customer.name)
        assert _mentions(lines, "Cement 50kg")

    def test_vat_registered_customer_sale_a4_invoice(self, db_session, cashier, tmp_path):
        cement = _product(db_session, "Cement 50kg", "2360.00", "40")
        customer = Customer(name=f"Lanka Builders {_next()}", vat_number="114567890-7000", address="Galle Road")
        db_session.add(customer)
        db_session.flush()

        event = _ring_up(db_session, cashier, [(cement, "1")], [("CASH", "2360.00")], customer=customer)

        pdf = tmp_path / "invoice.pdf"
        InvoiceService.generate_pdf(event.sale, str(pdf))
        text = "".join(page.extract_text() for page in PdfReader(pdf).pages)
        assert "Cement 50kg" in text
        assert customer.name in text
        assert "114567890-7000" in text

    def test_weighted_item_keeps_its_unit_decimals(self, db_session, cashier, print_queue):
        kg = Unit(name=f"Kilogram {_next()}", abbreviation="kg", decimal_places=3)
        db_session.add(kg)
        db_session.flush()
        sugar = _product(db_session, "Sugar (loose)", "240.00", "50", is_weighted=True, unit_id=kg.id)

        event = _ring_up(db_session, cashier, [(sugar, "1.250")], [("CASH", "300.00")])

        lines = _printed_lines(print_queue, event)
        assert _mentions(lines, "Sugar (loose)")
        assert _mentions(lines, "1.250")  # read from the product's unit -- "1" if the unit weren't loaded

    def test_composite_product(self, db_session, cashier, print_queue):
        tea = _product(db_session, "Tea 100g", "300.00", "10")
        biscuits = _product(db_session, "Biscuits", "150.00", "5")
        pack = _product(db_session, "Gift Pack", "700.00", "0", is_composite=True)
        db_session.add_all(
            [
                CompositeItem(parent_product_id=pack.id, child_product_id=tea.id, qty=Decimal("2")),
                CompositeItem(parent_product_id=pack.id, child_product_id=biscuits.id, qty=Decimal("1")),
            ]
        )
        db_session.flush()

        event = _ring_up(db_session, cashier, [(pack, "1")], [("CASH", "700.00")])

        lines = _printed_lines(print_queue, event)
        assert _mentions(lines, "Gift Pack")


def test_the_detach_harness_catches_a_relation_loaded_too_late(db_session, cashier, settings, print_queue):
    """Guard on the harness itself: with the receipt eager-load switched off, the build must fail here."""
    rice = _product(db_session, "Samba Rice 5kg", "1250.00", "20")

    with patch.object(TransactionService, "_load_receipt_relations", lambda sale: None):
        event = _ring_up(db_session, cashier, [(rice, "1")], [("CASH", "1250.00")])

    from sqlalchemy.orm.exc import DetachedInstanceError

    with pytest.raises(DetachedInstanceError):
        PrinterService.print_transaction(event.sale)
