"""
#290: Cash Flow, P&L, and Tax Liability are the Financial-category
reports explicitly called out in the issue as looking generic (no
highlighted total, no inflow/outflow color, raw "{:.2f}" instead of
currency formatting). Each now declares its own render_hints so the
shared PandasModel (see test_pandas_model_render_hints.py) can apply
that treatment without the view hardcoding anything per report.
"""

from cbpos.core.reports.base_report import MONEY
from cbpos.core.reports.definitions.cash_flow_report import CashFlowReport
from cbpos.core.reports.definitions.financial_reports import ProfitLossReport, TaxLiabilityReport


def _money_columns(hints) -> set[str]:
    return {name for name, col in hints["columns"].items() if col["type"] == MONEY}


class TestCashFlowReportRenderHints:
    def test_amount_is_a_currency_column(self):
        hints = CashFlowReport().get_render_hints()
        assert "Amount" in _money_columns(hints)

    def test_net_row_is_the_total_row(self):
        hints = CashFlowReport().get_render_hints()
        assert hints["total_row_column"] == "Type"
        assert "Net" in hints["total_row_values"]

    def test_inflow_and_outflow_are_color_tagged(self):
        hints = CashFlowReport().get_render_hints()
        assert hints["color_column"] == "Type"
        assert "Inflow" in hints["color_map"]
        assert "Outflow" in hints["color_map"]
        assert hints["color_map"]["Inflow"] != hints["color_map"]["Outflow"]


class TestProfitLossReportRenderHints:
    def test_money_columns_are_currency_formatted(self):
        hints = ProfitLossReport().get_render_hints()
        for column in ("Revenue", "Cost (COGS)", "Gross Profit"):
            assert column in _money_columns(hints)


class TestTaxLiabilityReportRenderHints:
    def test_money_columns_are_currency_formatted(self):
        hints = TaxLiabilityReport().get_render_hints()
        for column in ("Total Sale", "Net Revenue", "VAT (18%)", "SSCL (2.5%)", "Total Tax"):
            assert column in _money_columns(hints)
