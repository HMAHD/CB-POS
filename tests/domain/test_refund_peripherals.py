"""#734: a refund reaches the hardware only through the peripherals port, and only after it is committed."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.interfaces.transaction_peripherals import RefundCompleted
from cbpos.core.models import Permission, Product, Role, Sale, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.transaction_service import TransactionService
from tests.fakes import RecordingPeripherals

_counter = 0


@pytest.fixture
def settings(monkeypatch):
    values = dict(ConfigService.DEFAULTS)
    values.update(receipt_language="en", terminal_id="TERM-01")
    monkeypatch.setattr(ConfigService, "get", lambda key, *_a: values.get(key))
    monkeypatch.setattr(ConfigService, "get_all", lambda: dict(values))
    return values


@pytest.fixture
def cashier(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"rp_perm_{_counter}")
    role = Role(name=f"RpRole_{_counter}", permissions=[permission])
    user = User(username=f"rp_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user):
        yield user


@pytest.fixture
def sale(db_session, settings, cashier, peripherals) -> Sale:
    global _counter
    _counter += 1
    product = Product(
        name_en=f"RpProduct_{_counter}", price=Decimal("100"), stock_qty=Decimal("10"), barcode=f"RP{_counter:04d}"
    )
    db_session.add(product)
    db_session.commit()
    cart = CartService()
    cart.add_item(product, qty=Decimal("2"))
    sold = TransactionService.process_sale(cart, [{"method": "CASH", "amount": Decimal("200")}])
    assert sold is not None
    peripherals.events.clear()
    return sold


def _texts(commands: list[dict]) -> list[str]:
    return [c.get("val", "") for c in commands if c.get("type") == "text"]


def test_a_refund_emits_one_refund_completed_with_its_voucher(db_session, cashier, sale, peripherals):
    assert TransactionService.process_refund(sale.id, "Damaged", cashier.id) is True

    (event,) = peripherals.events
    assert isinstance(event, RefundCompleted)
    refund = db_session.query(Sale).filter_by(refund_of_sale_id=sale.id).one()
    assert event.refund_sale.id == refund.id
    assert event.refund_sale.document_number == refund.document_number
    lines = _texts(event.voucher)
    assert any(sale.document_number in line for line in lines)
    assert any(cashier.username in line for line in lines)


def test_a_refund_whose_commit_fails_prints_no_voucher(db_session, cashier, sale, peripherals):
    """Regression: the voucher must never reach the printer for a refund that didn't save."""
    with patch.object(db_session, "commit", side_effect=RuntimeError("disk full")):
        assert TransactionService.process_refund(sale.id, "Damaged", cashier.id) is False

    assert peripherals.events == []


def test_a_rejected_refund_prints_no_voucher(db_session, cashier, sale, peripherals):
    assert TransactionService.process_refund(sale.id, "Damaged", cashier.id) is True
    peripherals.events.clear()

    assert TransactionService.process_refund(sale.id, "Again", cashier.id) is False

    assert peripherals.events == []


def test_peripherals_passed_per_call_get_the_refund_instead(cashier, sale, peripherals):
    own = RecordingPeripherals()

    assert TransactionService.process_refund(sale.id, "Damaged", cashier.id, peripherals=own) is True

    assert [type(e) for e in own.events] == [RefundCompleted]
    assert peripherals.events == []


class _JammedPrinter:
    """Peripherals whose hardware fails on every event."""

    def sale_completed(self, event) -> None:
        raise OSError("printer offline")

    def refund_completed(self, event: RefundCompleted) -> None:
        raise OSError("printer offline")


def test_a_hardware_error_still_reports_the_committed_refund(db_session, cashier, sale, caplog):
    assert TransactionService.process_refund(sale.id, "Damaged", cashier.id, peripherals=_JammedPrinter()) is True

    assert db_session.query(Sale).filter_by(refund_of_sale_id=sale.id).count() == 1
    assert "printer offline" in caplog.text


def test_a_void_touches_no_hardware(cashier, sale, peripherals):
    assert TransactionService.void_sale(sale.id, cashier.id, "Wrong item") is True

    assert peripherals.events == []
