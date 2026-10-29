"""Unit tests for loyalty points display on receipt (#756).

Covers:
- Points earned, redeemed (when any > 0), and balance displayed on receipt.
- Shown only when customer is attached and show_loyalty_on_receipt is on.
- Nothing printed for walk-in sales.
- Correct formatting in en, si, ta on 58mm and 80mm paper.
- Reprints show the sale's own historical loyalty figures.
- Works on detached sales without DetachedInstanceError.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.models import Customer, Product, Sale, SaleItem, SalePayment
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_builder import ReceiptBuilder


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture
def config_store(monkeypatch):
    store = _FakeConfigStore(dict(ConfigService.DEFAULTS))
    store.set("receipt_language", "en")
    store.set("show_loyalty_on_receipt", True)
    store.set("enable_loyalty", True)
    store.set("paper_width", "80mm")
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    monkeypatch.setattr(ConfigService, "set", store.set)
    return store


def make_sale(
    customer: Customer | None = None,
    earned: int = 0,
    redeemed: int = 0,
    balance: int | None = None,
    total: str = "500.00",
) -> Sale:
    sale = Sale(
        id=42,
        document_number="INV-2026-00042",
        date=datetime(2026, 10, 15, 14, 30),
        total_amount=Decimal(total),
        tax_vat=Decimal("0"),
        tax_sscl=Decimal("0"),
        net_revenue=Decimal(total),
        payment_method="CASH",
        status="COMPLETED",
        customer_id=customer.id if customer else None,
        loyalty_points_redeemed=redeemed,
        loyalty_points_value=Decimal(str(redeemed)),
    )
    # New columns for #756
    sale.loyalty_points_earned = earned
    sale.loyalty_points_balance = balance

    sale.customer = customer
    sale.items = [
        SaleItem(
            product=Product(name_en="Rice 5kg"),
            qty=Decimal("1"),
            unit_price=Decimal(total),
            original_price=Decimal(total),
            subtotal=Decimal(total),
        )
    ]
    sale.payments = [SalePayment(payment_method="CASH", amount=Decimal(total))]
    return sale


def _text_commands(commands: list[dict]) -> list[dict]:
    return [c for c in commands if c.get("type") == "text"]


def _find_cmd_with_text(commands: list[dict], needle: str) -> dict | None:
    for c in commands:
        if needle in (c.get("val") or "") or needle in (c.get("left_val") or ""):
            return c
    return None


class TestReceiptLoyaltyPoints:
    def test_walk_in_sale_prints_no_loyalty_lines(self, config_store):
        sale = make_sale(customer=None, earned=0, redeemed=0, balance=None)

        commands = ReceiptBuilder.build_receipt(sale)

        assert _find_cmd_with_text(commands, "Points Earned:") is None
        assert _find_cmd_with_text(commands, "Points Redeemed:") is None
        assert _find_cmd_with_text(commands, "Points Balance:") is None

    def test_customer_sale_with_setting_off_prints_no_loyalty_lines(self, config_store):
        config_store.set("show_loyalty_on_receipt", False)
        customer = Customer(id=1, name="Sunil Perera", loyalty_points=120)
        sale = make_sale(customer=customer, earned=15, redeemed=0, balance=120)

        commands = ReceiptBuilder.build_receipt(sale)

        assert _find_cmd_with_text(commands, "Points Earned:") is None
        assert _find_cmd_with_text(commands, "Points Balance:") is None

    def test_customer_sale_with_loyalty_disabled_prints_no_loyalty_lines(self, config_store):
        config_store.set("enable_loyalty", False)
        customer = Customer(id=1, name="Sunil Perera", loyalty_points=120)
        sale = make_sale(customer=customer, earned=15, redeemed=0, balance=120)

        commands = ReceiptBuilder.build_receipt(sale)

        assert _find_cmd_with_text(commands, "Points Earned:") is None
        assert _find_cmd_with_text(commands, "Points Balance:") is None

    def test_customer_sale_earned_and_balance_80mm_en(self, config_store):
        customer = Customer(id=1, name="Sunil Perera", loyalty_points=115)
        sale = make_sale(customer=customer, earned=15, redeemed=0, balance=115)

        commands = ReceiptBuilder.build_receipt(sale)

        earned_cmd = _find_cmd_with_text(commands, "Points Earned:")
        assert earned_cmd is not None
        assert earned_cmd.get("right_val") == "15"
        assert len(earned_cmd.get("val")) == 42  # 80mm width

        balance_cmd = _find_cmd_with_text(commands, "Points Balance:")
        assert balance_cmd is not None
        assert balance_cmd.get("right_val") == "115"
        assert len(balance_cmd.get("val")) == 42

        # No redeemed points -> no redeemed line
        assert _find_cmd_with_text(commands, "Points Redeemed:") is None

    def test_customer_sale_with_redemption_58mm_en(self, config_store):
        config_store.set("paper_width", "58mm")
        customer = Customer(id=1, name="Sunil Perera", loyalty_points=60)
        sale = make_sale(customer=customer, earned=10, redeemed=50, balance=60)

        commands = ReceiptBuilder.build_receipt(sale)

        earned_cmd = _find_cmd_with_text(commands, "Points Earned:")
        assert earned_cmd is not None
        assert earned_cmd.get("right_val") == "10"
        assert len(earned_cmd.get("val")) == 32  # 58mm width

        redeemed_cmd = _find_cmd_with_text(commands, "Points Redeemed:")
        assert redeemed_cmd is not None
        assert redeemed_cmd.get("right_val") == "50"
        assert len(redeemed_cmd.get("val")) == 32

        balance_cmd = _find_cmd_with_text(commands, "Points Balance:")
        assert balance_cmd is not None
        assert balance_cmd.get("right_val") == "60"
        assert len(balance_cmd.get("val")) == 32

    def test_customer_sale_loyalty_si(self, config_store):
        config_store.set("receipt_language", "si")
        customer = Customer(id=1, name="Sunil Perera", loyalty_points=60)
        sale = make_sale(customer=customer, earned=10, redeemed=50, balance=60)

        commands = ReceiptBuilder.build_receipt(sale)

        earned_cmd = _find_cmd_with_text(commands, "ලබාගත් ලකුණු:")
        assert earned_cmd is not None
        assert earned_cmd.get("right_val") == "10"

        redeemed_cmd = _find_cmd_with_text(commands, "භාවිත කළ ලකුණු:")
        assert redeemed_cmd is not None
        assert redeemed_cmd.get("right_val") == "50"

        balance_cmd = _find_cmd_with_text(commands, "ලකුණු ශේෂය:")
        assert balance_cmd is not None
        assert balance_cmd.get("right_val") == "60"

    def test_customer_sale_loyalty_ta(self, config_store):
        config_store.set("receipt_language", "ta")
        customer = Customer(id=1, name="Sunil Perera", loyalty_points=60)
        sale = make_sale(customer=customer, earned=10, redeemed=50, balance=60)

        commands = ReceiptBuilder.build_receipt(sale)

        earned_cmd = _find_cmd_with_text(commands, "பெற்ற புள்ளிகள்:")
        assert earned_cmd is not None
        assert earned_cmd.get("right_val") == "10"

        redeemed_cmd = _find_cmd_with_text(commands, "பயன்படுத்திய புள்ளிகள்:")
        assert redeemed_cmd is not None
        assert redeemed_cmd.get("right_val") == "50"

        balance_cmd = _find_cmd_with_text(commands, "புள்ளி நிலுவை:")
        assert balance_cmd is not None
        assert balance_cmd.get("right_val") == "60"

    def test_reprint_shows_sale_historical_loyalty_figures(self, config_store):
        # Customer currently has 250 points, but at the time of this sale had 60
        customer = Customer(id=1, name="Sunil Perera", loyalty_points=250)
        sale = make_sale(customer=customer, earned=10, redeemed=50, balance=60)

        commands = ReceiptBuilder.build_receipt(sale, is_reprint=True)

        # Must show 60 from sale.loyalty_points_balance, NOT 250 from customer.loyalty_points
        balance_cmd = _find_cmd_with_text(commands, "Points Balance:")
        assert balance_cmd is not None
        assert balance_cmd.get("right_val") == "60"

        earned_cmd = _find_cmd_with_text(commands, "Points Earned:")
        assert earned_cmd is not None
        assert earned_cmd.get("right_val") == "10"

        redeemed_cmd = _find_cmd_with_text(commands, "Points Redeemed:")
        assert redeemed_cmd is not None
        assert redeemed_cmd.get("right_val") == "50"

        # Reprint markings
        duplicate_cmds = [c for c in commands if "*** DUPLICATE ***" in (c.get("val") or "")]
        assert len(duplicate_cmds) >= 1

    def test_loyalty_sinhala_and_tamil_raster(self, config_store, qapp):
        from cbpos.infrastructure.hardware.text_raster import needs_raster, render_text_line

        # Sinhala
        config_store.set("receipt_language", "si")
        customer = Customer(id=1, name="Sunil Perera", loyalty_points=60)
        sale = make_sale(customer=customer, earned=10, redeemed=50, balance=60)
        commands_si = ReceiptBuilder.build_receipt(sale)
        earned_si = _find_cmd_with_text(commands_si, "ලබාගත් ලකුණු:")
        assert earned_si is not None
        assert needs_raster(earned_si["val"])
        img_80 = render_text_line(earned_si, "80mm")
        assert img_80.width == 576
        img_58 = render_text_line(earned_si, "58mm")
        assert img_58.width == 384

        # Tamil
        config_store.set("receipt_language", "ta")
        commands_ta = ReceiptBuilder.build_receipt(sale)
        earned_ta = _find_cmd_with_text(commands_ta, "பெற்ற புள்ளிகள்:")
        assert earned_ta is not None
        assert needs_raster(earned_ta["val"])
        img_ta_80 = render_text_line(earned_ta, "80mm")
        assert img_ta_80.width == 576
        img_ta_58 = render_text_line(earned_ta, "58mm")
        assert img_ta_58.width == 384

    def test_legacy_sale_fallback_to_customer_points(self, config_store):
        # When loyalty_points_balance is None (e.g. legacy sale before column existed)
        customer = Customer(id=1, name="Sunil Perera", loyalty_points=120)
        sale = make_sale(customer=customer, earned=15, redeemed=0, balance=None)

        commands = ReceiptBuilder.build_receipt(sale)

        balance_cmd = _find_cmd_with_text(commands, "Points Balance:")
        assert balance_cmd is not None
        assert balance_cmd.get("right_val") == "120"
