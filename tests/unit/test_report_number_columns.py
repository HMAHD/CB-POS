"""#556: Reports right-align and format every numeric column.

PandasModel used ``isinstance(v, (int, float))``, which is False for
numpy.int64 (counts) and Decimal (money): those columns were left-aligned
and unformatted, and floats had no thousands separators. Reports now
declare per-column types, and untyped numbers are detected with
``numbers.Number`` (bools excluded).
"""

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import Qt

from cbpos.core.reports import register_all_reports
from cbpos.core.reports.base_report import INT, MONEY, NUMERIC_COLUMN_TYPES, QTY, report_columns
from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport
from cbpos.core.reports.registry import ReportRegistry
from cbpos.core.utils.formatters import get_currency_symbol
from cbpos.ui.views.reports.pandas_model import PandasModel

pytestmark = pytest.mark.usefixtures("qapp")

DISPLAY = Qt.ItemDataRole.DisplayRole
ALIGN = Qt.ItemDataRole.TextAlignmentRole
H = Qt.Orientation.Horizontal


def _is_right(alignment) -> bool:
    return alignment is not None and bool(Qt.AlignmentFlag(alignment) & Qt.AlignmentFlag.AlignRight)


def _cell(model, row, col, role=DISPLAY):
    return model.data(model.index(row, col), role)


class TestUntypedNumbers:
    """No render hints: a number of any kind right-aligns and gets separators."""

    def _model(self):
        frame = pd.DataFrame(
            {
                "Name": ["Rice"],
                "Count": [12345],  # int64 column -> np.int64 cells
                "Revenue": [1650.5],  # float64
                "Amount": [Decimal("1650.00")],  # object column of Decimal
                "Flag": [True],
            }
        )
        assert isinstance(frame.iloc[0, 1], np.int64)
        return PandasModel(frame)

    def test_int64_is_right_aligned_with_separators(self):
        model = self._model()
        assert _cell(model, 0, 1) == "12,345"
        assert _is_right(_cell(model, 0, 1, ALIGN))

    def test_float64_is_right_aligned_with_separators(self):
        model = self._model()
        assert _cell(model, 0, 2) == "1,650.50"
        assert _is_right(_cell(model, 0, 2, ALIGN))

    def test_decimal_is_right_aligned_with_separators(self):
        model = self._model()
        assert _cell(model, 0, 3) == "1,650.00"
        assert _is_right(_cell(model, 0, 3, ALIGN))

    def test_text_and_bool_stay_left(self):
        model = self._model()
        assert not _is_right(_cell(model, 0, 0, ALIGN))
        assert not _is_right(_cell(model, 0, 4, ALIGN))
        assert _cell(model, 0, 4) == "True"

    def test_headers_follow_the_cells(self):
        model = self._model()
        assert [_is_right(model.headerData(c, H, ALIGN)) for c in range(5)] == [False, True, True, True, False]


class TestSalesReport:
    """The Daily Sales Summary report as it comes out of SQL: np.int64 counts, float money."""

    def _model(self):
        frame = pd.DataFrame(
            [
                {"Date": "2026-10-01", "Transactions": 12345, "Total Sales": 1650.0},
                {"Date": "2026-10-02", "Transactions": 7, "Total Sales": 1234567.5},
            ]
        )
        return PandasModel(frame, render_hints=DailySalesSummaryReport().get_render_hints())

    def test_money_and_counts_are_right_aligned_with_separators(self):
        model = self._model()
        assert _cell(model, 0, 1) == "12,345"
        assert _cell(model, 0, 2) == "1,650.00"
        assert _cell(model, 1, 2) == "1,234,567.50"
        for col in (1, 2):
            assert _is_right(_cell(model, 0, col, ALIGN))
            assert _is_right(model.headerData(col, H, ALIGN))
        assert not _is_right(_cell(model, 0, 0, ALIGN))

    def test_money_header_carries_the_currency_symbol(self):
        model = self._model()
        assert model.headerData(2, H, DISPLAY) == f"Total Sales ({get_currency_symbol()})"
        assert model.headerData(1, H, DISPLAY) == "Transactions"


def test_typed_money_column_with_blank_cells_stays_right_aligned():
    """Tax Liability's summary row leaves money cells empty; the column (and header) stays numeric."""
    frame = pd.DataFrame(
        [{"Invoice #": "INV-1", "Total Sale": Decimal("10")}, {"Invoice #": "NET", "Total Sale": None}]
    )
    model = PandasModel(frame, render_hints={"columns": report_columns({"Invoice #": "text", "Total Sale": MONEY})})
    assert _cell(model, 1, 1) == ""
    assert _is_right(_cell(model, 1, 1, ALIGN))
    assert _is_right(model.headerData(1, H, ALIGN))


def test_label_key_is_used_once_translated(monkeypatch):
    from cbpos.ui.views.reports import pandas_model

    monkeypatch.setattr(pandas_model, "_t", lambda key: "Qty (translated)" if key == "reports.col_qty" else key)
    model = PandasModel(pd.DataFrame({"Qty": [1.5]}), render_hints={"columns": report_columns({"Qty": QTY})})
    assert model.headerData(0, H, DISPLAY) == "Qty (translated)"
    assert _cell(model, 0, 0) == "1.500"


def _all_reports():
    register_all_reports()
    registry = ReportRegistry()
    return [r for cat in registry.get_all_categories() for r in registry.get_reports_by_category(cat)]


def test_all_16_reports_declare_column_types_and_label_keys():
    reports = _all_reports()
    assert len(reports) == 16
    for report in reports:
        columns = report.get_render_hints().get("columns")
        assert columns, report.id
        assert any(col["type"] in NUMERIC_COLUMN_TYPES for col in columns.values()), report.id
        for col in columns.values():
            assert col["label_key"].startswith("reports.col_"), report.id


@pytest.mark.parametrize("report", _all_reports(), ids=lambda r: r.id)
def test_every_report_right_aligns_its_numeric_columns(report):
    columns = report.get_render_hints()["columns"]
    sample = {MONEY: 1650.5, INT: np.int64(12345), QTY: 2.5}
    row = {name: sample.get(col["type"], "x") for name, col in columns.items()}
    model = PandasModel(pd.DataFrame([row]), render_hints=report.get_render_hints())
    for col, (_name, definition) in enumerate(columns.items()):
        numeric = definition["type"] in NUMERIC_COLUMN_TYPES
        assert _is_right(_cell(model, 0, col, ALIGN)) == numeric, (report.id, _name)
        assert _is_right(model.headerData(col, H, ALIGN)) == numeric, (report.id, _name)
        if definition["type"] in (MONEY, INT):
            assert "," in _cell(model, 0, col), (report.id, _name)
