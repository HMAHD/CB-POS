"""
#681: a reprinted receipt shows the sale's own cashier and quantities.

ReceiptBuilder used to print the currently logged-in user as cashier, so a
reprint by cashier B of a sale made by cashier A said "Cashier: B". And a
sale reloaded from the database carries its quantity as ``2.000`` (the
column's scale), so a reprint showed ``2.000`` where the auto-print right
after the sale showed ``2``. Both are fixed in the builder, so the original
print and every reprint share one path.
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cbpos.core.models import Product, Sale, SaleItem, SalePayment, Unit, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_builder import ReceiptBuilder


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture
def config_store(monkeypatch):
    store = _FakeConfigStore(dict(ConfigService.DEFAULTS))
    store.set("receipt_language", "en")
    store.set("show_cashier_on_receipt", True)
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    return store


@pytest.fixture
def logged_in_as_b():
    with patch(
        "cbpos.core.services.auth_service.AuthService.get_current_user",
        return_value=SimpleNamespace(username="cashier_b"),
    ):
        yield


def _sale(qty: str = "2.000", unit: Unit | None = None, user: User | None = None, user_id: int | None = None) -> Sale:
    sale = Sale(
        id=11,
        document_number="INV-2026-00011",
        date=datetime(2026, 10, 7, 9, 30),
        total_amount=Decimal("236.00"),
        tax_vat=Decimal("0"),
        tax_sscl=Decimal("0"),
        net_revenue=Decimal("236.00"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=user_id,
    )
    if user is not None:
        sale.user = user
    sale.items = [
        SaleItem(
            product=Product(name_en="Soap", unit=unit),
            qty=Decimal(qty),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("236.00"),
        )
    ]
    sale.payments = [SalePayment(payment_method="CASH", amount=Decimal("300.00"))]
    return sale


def _texts(commands: list[dict]) -> list[str]:
    return [c.get("val", "") for c in commands if c.get("type") == "text"]


class TestCashierIsTheSalesCashier:
    def test_reprint_shows_original_cashier_not_current_user(self, config_store, logged_in_as_b):
        sale = _sale(user=User(username="cashier_a", pin_hash="x"), user_id=5)

        lines = _texts(ReceiptBuilder.build_receipt(sale, is_reprint=True))

        assert any("cashier_a" in line for line in lines)
        assert not any("cashier_b" in line for line in lines)

    def test_unsaved_preview_sale_falls_back_to_current_user(self, config_store, logged_in_as_b):
        lines = _texts(ReceiptBuilder.build_receipt(_sale()))

        assert any("cashier_b" in line for line in lines)

    def test_saved_sale_without_loaded_user_never_prints_someone_else(self, config_store, logged_in_as_b):
        sale = _sale(user_id=5)  # cashier recorded, but the relationship wasn't loaded

        lines = _texts(ReceiptBuilder.build_receipt(sale, is_reprint=True))

        assert not any("cashier_b" in line for line in lines)


class TestQuantityFormat:
    def test_piece_quantity_from_db_prints_without_decimals(self, config_store, logged_in_as_b):
        lines = _texts(ReceiptBuilder.build_receipt(_sale(qty="2.000", unit=Unit(name="pcs", decimal_places=0))))

        assert any(line.startswith("   2 x ") for line in lines)
        assert not any("2.000 x" in line for line in lines)

    def test_weighed_quantity_keeps_its_three_decimals(self, config_store, logged_in_as_b):
        lines = _texts(ReceiptBuilder.build_receipt(_sale(qty="1.250", unit=Unit(name="kg", decimal_places=3))))

        assert any(line.startswith("   1.250 x ") for line in lines)

    def test_no_unit_prints_whole_number_plainly(self, config_store, logged_in_as_b):
        lines = _texts(ReceiptBuilder.build_receipt(_sale(qty="2.000")))

        assert any(line.startswith("   2 x ") for line in lines)

    def test_no_unit_keeps_fractional_quantity(self, config_store, logged_in_as_b):
        lines = _texts(ReceiptBuilder.build_receipt(_sale(qty="0.500")))

        assert any(line.startswith("   0.500 x ") for line in lines)

    def test_original_and_reloaded_quantity_print_the_same(self, config_store, logged_in_as_b):
        unit = Unit(name="pcs", decimal_places=0)
        fresh = _texts(ReceiptBuilder.build_receipt(_sale(qty="2", unit=unit)))
        reloaded = _texts(ReceiptBuilder.build_receipt(_sale(qty="2.000", unit=unit)))

        assert fresh == reloaded


# ── Database round trip: the sale is reloaded as every reprint path does ──


@pytest.fixture
def two_cashiers(db_session):
    from cbpos.core.models import Role

    role = Role(name="ReprintCashierRole")
    cashier_a = User(username="reprint_cashier_a", pin_hash="x", role=role)
    cashier_b = User(username="reprint_cashier_b", pin_hash="x", role=role)
    pcs = Unit(name="reprint_pcs", abbreviation="pcs", decimal_places=0)
    product = Product(name_en="ReprintSoap", price=Decimal("100"), stock_qty=Decimal("10"), barcode="RPC0001", unit=pcs)
    db_session.add_all([role, cashier_a, cashier_b, pcs, product])
    db_session.flush()
    return cashier_a, cashier_b, product


def test_reprint_of_reloaded_sale_shows_cashier_a_and_plain_quantity(config_store, db_session, two_cashiers):
    from cbpos.core.services.cart_service import CartService
    from cbpos.core.services.sale_query_service import SaleQueryService
    from cbpos.core.services.transaction_service import TransactionService

    cashier_a, cashier_b, product = two_cashiers
    config_store.set("show_receipt_dialog", True)  # no auto-print in this test

    cart = CartService()
    cart.add_item(product, qty=Decimal("2"))
    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=cashier_a),
    ):
        sale = TransactionService.process_sale(cart, [{"method": "CASH", "amount": Decimal("200")}])
    sale_id = sale.id
    # Fresh identity map, so the reload really eager-loads, as in the app.
    db_session.expunge_all()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=cashier_b):
        for reloaded in (
            SaleQueryService.get_sale_details(sale_id),
            SaleQueryService.get_last_sale(),
        ):
            lines = _texts(ReceiptBuilder.build_receipt(reloaded, is_reprint=True))
            assert any("reprint_cashier_a" in line for line in lines)
            assert not any("reprint_cashier_b" in line for line in lines)
            assert any(line.startswith("   2 x ") for line in lines)


@pytest.mark.parametrize("build", ["build_void_receipt", "build_refund_receipt"])
def test_void_and_refund_receipts_format_quantity_by_unit(config_store, logged_in_as_b, build):
    sale = _sale(qty="2.000", unit=Unit(name="pcs", decimal_places=0))

    lines = _texts(getattr(ReceiptBuilder, build)(sale))

    assert any(line.startswith("2 x ") for line in lines)
    assert not any("2.000 x" in line for line in lines)
