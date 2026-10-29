"""#559: status/variance/price colours come from one theme-aware palette.

They were dark-theme neon QColors used in both themes (#39FF14 on white
is ~1.4:1), so completed/void, overage/shortage and overdue were
unreadable in Light mode.
"""

import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.resources import status_colors
from cbpos.ui.resources.status_colors import PALETTE, SURFACE, pill_colors, status_color

UI_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui"

# Backgrounds a status colour is drawn on (dark.qss / light.qss tables).
# Dark selected rows are not listed: dark.qss paints selected text white.
BACKGROUNDS = {
    "Dark": ["#252526", "#2D2D30", "#1E1E1E"],
    "Light": ["#FFFFFF", "#F8F9FA", "#E3F2FD"],  # E3F2FD = selected row
}
DARK_NEON = {"#39ff14", "#ff4136", "#ffdc00", "#ffd700", "#5599ff", "#ff851b", "#00ff00"}


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.fixture(params=["Dark", "Light"])
def theme(request, monkeypatch):
    monkeypatch.setattr(ThemeService, "current_theme", request.param)
    return request.param


@pytest.mark.parametrize("meaning", list(PALETTE))
def test_every_colour_meets_aa_on_its_backgrounds(theme, meaning):
    colour = status_color(meaning).name()
    for background in BACKGROUNDS[theme]:
        assert contrast(colour, background) >= 4.5, (theme, meaning, background)


@pytest.mark.parametrize("meaning", list(PALETTE))
def test_pill_text_meets_aa_on_its_own_fill(theme, meaning):
    text, fill = pill_colors(meaning)
    assert contrast(text.name(), fill.name()) >= 4.5, (theme, meaning)


def test_light_theme_never_returns_a_dark_neon_colour(monkeypatch):
    monkeypatch.setattr(ThemeService, "current_theme", "Light")
    assert {status_color(m).name() for m in PALETTE}.isdisjoint(DARK_NEON)


def test_colour_follows_the_theme(monkeypatch):
    monkeypatch.setattr(ThemeService, "current_theme", "Dark")
    dark = status_color(status_colors.SUCCESS).name()
    monkeypatch.setattr(ThemeService, "current_theme", "Light")
    assert status_color(status_colors.SUCCESS).name() != dark
    assert SURFACE["light"] == "#FFFFFF"


def test_no_hardcoded_neon_colours_in_ui_code():
    """No QColor("#39FF14") / Qt.GlobalColor.green (or the other old neon QColors) outside the palette."""
    pattern = re.compile(
        r'QColor\("#(39FF14|FF4136|FFDC00|FFD700|5599FF|FF851B)"\)|GlobalColor\.(green|red|yellow)', re.IGNORECASE
    )
    offenders = [
        f"{path.relative_to(UI_DIR)}:{n}"
        for path in UI_DIR.rglob("*.py")
        if path.name != "status_colors.py"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []


def test_stock_take_variance_has_a_sign_and_a_theme_colour(qapp, monkeypatch):
    from cbpos.core.utils.formatters import MINUS_SIGN
    from cbpos.ui.views.stock_take_view import StockCountItemModel

    monkeypatch.setattr(ThemeService, "current_theme", "Light")
    piece = SimpleNamespace(barcode="B", name_en="P", unit=SimpleNamespace(decimal_places=0), is_weighted=False)

    def item(expected, counted):
        variance = Decimal(counted) - Decimal(expected)
        return SimpleNamespace(
            product=piece,
            expected_qty=Decimal(expected),
            counted_qty=Decimal(counted),
            variance_qty=variance,
            variance_value=variance * 10,
        )

    model = StockCountItemModel([item("10", "13"), item("10", "7"), item("10", "10")])
    display, fg = Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ForegroundRole
    assert model.data(model.index(0, 4), display) == "+3"
    assert model.data(model.index(1, 4), display) == f"{MINUS_SIGN}3"
    assert model.data(model.index(2, 4), display) == "0"
    assert model.data(model.index(0, 5), display).startswith("+")
    assert model.data(model.index(1, 5), display).startswith(MINUS_SIGN)
    assert model.data(model.index(0, 4), fg).name() == status_color(status_colors.SUCCESS).name()
    assert model.data(model.index(1, 4), fg).name() == status_color(status_colors.DANGER).name()


def test_report_colour_map_accepts_meanings(qapp, monkeypatch):
    import pandas as pd

    from cbpos.core.reports.definitions.cash_flow_report import CashFlowReport
    from cbpos.ui.views.reports.pandas_model import PandasModel

    monkeypatch.setattr(ThemeService, "current_theme", "Light")
    frame = pd.DataFrame([{"Category": "Sales", "Amount": 1.0, "Type": "Inflow"}])
    model = PandasModel(frame, render_hints=CashFlowReport().get_render_hints())
    colour = model.data(model.index(0, 2), Qt.ItemDataRole.ForegroundRole)
    assert colour.name() == status_color(status_colors.SUCCESS).name()


def test_admin_tools_colours_only_the_level_cell(qapp, db_session):
    from cbpos.ui.views.admin_tools_view import AdminToolsView

    view = AdminToolsView()
    entry = {"timestamp": "t", "level": "WARNING", "source": "s", "message": "m"}
    view._current_log_entries = [entry]
    view.log_pagination.set_total(1)
    view._populate_log_page()
    row = [view.log_table.item(0, c) for c in range(view.log_table.columnCount())]
    level_col = next(c for c, it in enumerate(row) if it is not None and it.text() == "WARNING")
    assert row[level_col].foreground().color().name() == status_color(status_colors.WARNING).name()
    for col, cell in enumerate(row):
        if cell is None:
            continue
        assert cell.background().style() == Qt.BrushStyle.NoBrush, col
        if col != level_col:
            assert cell.foreground().style() == Qt.BrushStyle.NoBrush, col
    view.deleteLater()
