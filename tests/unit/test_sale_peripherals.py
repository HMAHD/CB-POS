"""#733: a sale reaches the hardware only through the peripherals port, and only after it is committed."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.interfaces.transaction_peripherals import SaleCompleted
from cbpos.core.models import Permission, Product, Role, Sale, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.transaction_service import TransactionService

_counter = 0


@pytest.fixture
def cashier(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"sp_perm_{_counter}")
    role = Role(name=f"SpRole_{_counter}", permissions=[permission])
    user = User(username=f"sp_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user):
        yield user


@pytest.fixture
def product(db_session):
    global _counter
    _counter += 1
    item = Product(
        name_en=f"SpProduct_{_counter}", price=Decimal("100"), stock_qty=Decimal("10"), barcode=f"SP{_counter:04d}"
    )
    db_session.add(item)
    db_session.commit()
    return item


def _cart(product: Product) -> CartService:
    cart = CartService()
    cart.add_item(product, qty=Decimal("2"))
    return cart


def test_a_sale_emits_one_sale_completed_with_its_payment_methods(cashier, product, peripherals):
    payments = [{"method": "CASH", "amount": Decimal("150")}, {"method": "CARD", "amount": Decimal("50")}]

    sale = TransactionService.process_sale(_cart(product), payments)

    assert peripherals.events == [SaleCompleted(sale=sale, payment_methods=("CASH", "CARD"))]


def test_a_sale_whose_commit_fails_prints_nothing_and_opens_no_drawer(db_session, cashier, product, peripherals):
    """Regression: the receipt and drawer kick used to be queued inside the session, before the commit."""
    cart = _cart(product)
    payments = [{"method": "CASH", "amount": Decimal("200")}]

    with patch.object(db_session, "commit", side_effect=RuntimeError("disk full")):
        sale = TransactionService.process_sale(cart, payments)

    assert sale is None
    assert peripherals.events == []


class _JammedPrinter:
    """Peripherals whose hardware fails on every event."""

    def sale_completed(self, event: SaleCompleted) -> None:
        raise OSError("printer offline")

    def refund_completed(self, event) -> None:
        raise OSError("printer offline")


def test_a_hardware_error_still_returns_the_committed_sale(db_session, cashier, product, caplog):
    payments = [{"method": "CASH", "amount": Decimal("200")}]

    sale = TransactionService.process_sale(_cart(product), payments, peripherals=_JammedPrinter())

    assert sale is not None
    assert db_session.get(Sale, sale.id) is not None
    assert "printer offline" in caplog.text
