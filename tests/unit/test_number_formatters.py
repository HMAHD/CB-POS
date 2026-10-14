"""#555: one set of number helpers for every table, and the configured currency symbol everywhere.

Screens used to format with ``:.2f``/``str()`` and a few hardcoded "Rs.",
so the Currency Symbol setting was ignored in places.
"""

import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import cbpos.core.models  # noqa: F401 -- registers tables before db_session creates them
from cbpos.core.services.config_service import ConfigService
from cbpos.core.utils.formatters import (
    MINUS_SIGN,
    NO_VALUE,
    format_currency,
    format_discount,
    format_number,
    format_quantity,
    format_signed,
    money_header,
)


@pytest.fixture
def currency(monkeypatch):
    """Set the configured currency symbol for one test."""
    ConfigService.get("currency_symbol")  # make sure settings are loaded

    def _set(symbol: str) -> None:
        monkeypatch.setitem(ConfigService._settings, "currency_symbol", symbol)

    return _set


@pytest.mark.parametrize(
    ("value", "decimals", "expected"),
    [
        (1650, 2, "1,650.00"),
        (12345, 0, "12,345"),
        (Decimal("1650.5"), 2, "1,650.50"),
        (Decimal("1234567.891"), 3, "1,234,567.891"),
        (np.int64(12345), 0, "12,345"),
        (np.int64(7), 2, "7.00"),
        (np.float64(1650.5), 2, "1,650.50"),
        (1650.505, 2, "1,650.51"),  # half-up, like money
        (-1234.5, 2, "-1,234.50"),
        (Decimal("-0.001"), 2, "0.00"),  # never "-0.00"
        (0, 2, "0.00"),
        (0, 0, "0"),
        ("2500", 2, "2,500.00"),
    ],
)
def test_format_number(value, decimals, expected):
    assert format_number(value, decimals) == expected


@pytest.mark.parametrize("value", [None, float("nan"), np.float64("nan"), True])
def test_format_number_blank_for_missing_values(value):
    assert format_number(value) == ""


def test_format_number_leaves_text_untouched():
    assert format_number("N/A") == "N/A"


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (Decimal("12.000"), SimpleNamespace(decimal_places=0), "12"),
        (Decimal("1.25"), SimpleNamespace(decimal_places=3), "1.250"),
        (Decimal("1250"), SimpleNamespace(decimal_places=0), "1,250"),
        (Decimal("2.5"), 1, "2.5"),
        (Decimal("2.5"), None, "2.500"),  # unknown unit: full precision
        (Decimal("12.5"), SimpleNamespace(decimal_places=0), "12.500"),  # bad data is not rounded away
        (np.int64(4), SimpleNamespace(decimal_places=0), "4"),
    ],
)
def test_format_quantity_uses_unit_decimal_places(value, unit, expected):
    assert format_quantity(value, unit) == expected


def test_format_signed_shows_plus_and_minus():
    piece = SimpleNamespace(decimal_places=0)
    assert format_signed(Decimal("3"), lambda v: format_quantity(v, piece)) == "+3"
    assert format_signed(Decimal("-3"), lambda v: format_quantity(v, piece)) == f"{MINUS_SIGN}3"
    assert format_signed(Decimal("0"), lambda v: format_quantity(v, piece)) == "0"


def test_format_currency_and_header_use_the_configured_symbol(currency):
    currency("$")
    assert format_currency(Decimal("1650")) == "$ 1,650.00"
    assert money_header("Price") == "Price ($)"
    assert format_signed(Decimal("-50"), format_currency) == f"{MINUS_SIGN}$ 50.00"


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [
        ("PERCENTAGE", Decimal("10.00"), "10%"),
        ("PERCENT", Decimal("12.5"), "12.50%"),
        ("FIXED", Decimal("50"), "Rs. 50.00"),
        ("FIXED_AMOUNT", Decimal("1500"), "Rs. 1,500.00"),
        ("BOGO", Decimal("0"), NO_VALUE),
        ("NONE", Decimal("0"), ""),
        (None, None, ""),
    ],
)
def test_format_discount(currency, kind, value, expected):
    currency("Rs.")
    assert format_discount(kind, value) == expected


def test_settings_money_spin_boxes_follow_the_currency_symbol(qapp, db_session, currency):
    from cbpos.ui.views.settings_view import SettingsView

    currency("LKR")
    view = SettingsView()
    view.load_settings()
    shop, sales = view.pages[0], view.pages[1]
    assert sales.spin_loyalty_ratio.prefix() == "LKR "
    assert sales.spin_default_credit.prefix() == "LKR "

    # Typing a new symbol on Shop Info updates the prefixes before saving.
    shop.input_currency.setText("$")
    assert sales.spin_loyalty_ratio.prefix() == "$ "
    assert sales.spin_default_credit.prefix() == "$ "
    view.deleteLater()


def test_stock_take_stats_bar_uses_the_currency_symbol(qapp, db_session, currency):
    from cbpos.ui.views.stock_take_view import StockTakeView

    currency("$")
    view = StockTakeView()
    assert "$ 0.00" in view.lbl_net_variance.text()
    assert "$ 0.00" in view.lbl_discrepancy.text()
    assert "Rs." not in view.lbl_net_variance.text() + view.lbl_discrepancy.text()
    view.deleteLater()


def test_no_hardcoded_rupee_symbol_in_ui_code():
    """No '"Rs.' string literal in cbpos/ui Python (i18n JSON/receipt templates excluded)."""
    ui_dir = Path(__file__).resolve().parents[2] / "cbpos" / "ui"
    offenders = [
        f"{path.relative_to(ui_dir)}:{n}"
        for path in ui_dir.rglob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"[\"']Rs\.", line)
    ]
    assert offenders == []
