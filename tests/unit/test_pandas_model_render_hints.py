"""
#290: every report -- Cash Flow, P&L, Stock Movement Audit, all of them --
rendered through one shared PandasModel with zero report-specific
treatment: no bold/tinted total row, no color-coding for inflow vs.
outflow, and money columns went through raw "{:.2f}" instead of the
app's own currency formatter. Give PandasModel an optional render_hints
dict (currency columns, a total-row marker, a color-coded column) fed by
each report's own BaseReport.get_render_hints(), so the visual treatment
lives with the report definition, not hardcoded per report type in the
view.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import pandas as pd
import pytest

from cbpos.ui.views.reports.pandas_model import PandasModel

pytestmark = pytest.mark.usefixtures("qapp")


class TestBackwardCompatibleWithNoHints:
    def test_plain_dataframe_still_renders_as_before(self):
        df = pd.DataFrame([{"Category": "Sales", "Amount": 500.0}])
        model = PandasModel(df)
        index = model.index(0, 1)
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "500.00"

    def test_no_font_or_background_override_without_hints(self):
        df = pd.DataFrame([{"Category": "Sales", "Amount": 500.0}])
        model = PandasModel(df)
        index = model.index(0, 0)
        assert model.data(index, Qt.ItemDataRole.FontRole) is None
        assert model.data(index, Qt.ItemDataRole.BackgroundRole) is None


class TestCurrencyColumnFormatting:
    def test_currency_column_uses_the_app_currency_formatter(self):
        df = pd.DataFrame([{"Category": "Sales", "Amount": 1234.5}])
        model = PandasModel(df, render_hints={"currency_columns": ["Amount"]})
        index = model.index(0, 1)
        value = model.data(index, Qt.ItemDataRole.DisplayRole)
        assert "1,234.50" in value

    def test_non_currency_column_is_unaffected(self):
        df = pd.DataFrame([{"Category": "Sales", "Amount": 1234.5}])
        model = PandasModel(df, render_hints={"currency_columns": ["Amount"]})
        index = model.index(0, 0)
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "Sales"


class TestTotalRowIsBoldAndTinted:
    def test_total_row_is_bold(self):
        df = pd.DataFrame(
            [
                {"Category": "Sales", "Type": "Inflow", "Amount": 500.0},
                {"Category": "Net Cash Flow", "Type": "Net", "Amount": 500.0},
            ]
        )
        model = PandasModel(df, render_hints={"total_row_column": "Type", "total_row_values": ["Net"]})

        regular_font = model.data(model.index(0, 0), Qt.ItemDataRole.FontRole)
        total_font = model.data(model.index(1, 0), Qt.ItemDataRole.FontRole)

        assert regular_font is None
        assert total_font is not None
        assert total_font.bold()

    def test_total_row_has_a_background_tint(self):
        df = pd.DataFrame(
            [
                {"Category": "Sales", "Type": "Inflow", "Amount": 500.0},
                {"Category": "Net Cash Flow", "Type": "Net", "Amount": 500.0},
            ]
        )
        model = PandasModel(df, render_hints={"total_row_column": "Type", "total_row_values": ["Net"]})

        assert model.data(model.index(0, 0), Qt.ItemDataRole.BackgroundRole) is None
        assert model.data(model.index(1, 0), Qt.ItemDataRole.BackgroundRole) is not None


class TestDirectionalColorCoding:
    def test_inflow_and_outflow_get_different_colors(self):
        df = pd.DataFrame(
            [
                {"Category": "Sales", "Type": "Inflow", "Amount": 500.0},
                {"Category": "Refunds", "Type": "Outflow", "Amount": 50.0},
            ]
        )
        model = PandasModel(
            df,
            render_hints={
                "color_column": "Type",
                "color_map": {"Inflow": "#39FF14", "Outflow": "#FF4136"},
            },
        )

        inflow_colour = model.data(model.index(0, 1), Qt.ItemDataRole.ForegroundRole)
        outflow_colour = model.data(model.index(1, 1), Qt.ItemDataRole.ForegroundRole)

        assert QColor(inflow_colour).name() == "#39ff14"
        assert QColor(outflow_colour).name() == "#ff4136"

    def test_untagged_value_gets_no_colour_override(self):
        df = pd.DataFrame([{"Category": "Sales", "Type": "Net", "Amount": 500.0}])
        model = PandasModel(
            df,
            render_hints={"color_column": "Type", "color_map": {"Inflow": "#39FF14"}},
        )
        assert model.data(model.index(0, 1), Qt.ItemDataRole.ForegroundRole) is None


class TestSetDataAcceptsRenderHints:
    def test_set_data_updates_hints_used_by_subsequent_reads(self):
        model = PandasModel()
        df = pd.DataFrame([{"Amount": 1000.0}])
        model.set_data(df, render_hints={"currency_columns": ["Amount"]})
        value = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
        assert "1,000.00" in value

    def test_set_data_without_hints_clears_previous_hints(self):
        model = PandasModel()
        model.set_data(pd.DataFrame([{"Amount": 1000.0}]), render_hints={"currency_columns": ["Amount"]})
        model.set_data(pd.DataFrame([{"Amount": 1000.0}]))
        value = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
        assert value == "1000.00"
