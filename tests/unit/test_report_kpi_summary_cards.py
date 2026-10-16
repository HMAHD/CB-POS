"""Unit tests for report KPI summary cards contract and computation (#543)."""

import pandas as pd
import pytest

from cbpos.core.reports.base_report import BaseReport
from cbpos.core.reports.definitions.inventory_reports import InventoryValuationReport
from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport
from cbpos.i18n import get_language, set_language, translate_in


@pytest.fixture
def language():
    original = get_language()
    yield set_language
    set_language(original)


def test_base_report_default_summary_is_empty():
    class DummyReport(BaseReport):
        @property
        def id(self) -> str:
            return "dummy"

        @property
        def name(self) -> str:
            return "Dummy"

        @property
        def category(self) -> str:
            return "sales"

        def get_filter_definitions(self):
            return []

        def generate(self, filters):
            return pd.DataFrame()

    dummy = DummyReport()
    assert dummy.get_summary(pd.DataFrame()) == []
    assert dummy.get_summary(pd.DataFrame({"x": [1, 2, 3]})) == []


def test_daily_sales_summary_computation():
    report = DailySalesSummaryReport()
    df = pd.DataFrame(
        {
            "Date": ["2026-10-01", "2026-10-02"],
            "Total Invoices": [10, 20],
            "Total Sales": [15000.0, 35000.0],
            "Total Discounts": [500.0, 1000.0],
            "Net Sales": [14500.0, 34000.0],
        }
    )

    summary = report.get_summary(df)
    assert len(summary) == 3

    # Total Sales card
    sales_card = summary[0]
    assert sales_card["key"] == "total_sales"
    assert "50,000.00" in sales_card["value"] or "50000.00" in sales_card["value"]

    # Invoices count card (sum of total invoices)
    invoices_card = summary[1]
    assert invoices_card["key"] == "invoices"
    assert invoices_card["value"] == "30"

    # Avg ticket card (50,000 / 30 = 1666.67)
    avg_card = summary[2]
    assert avg_card["key"] == "avg_ticket"
    assert "1,666.67" in avg_card["value"] or "1666.67" in avg_card["value"]


def test_daily_sales_summary_empty_df():
    report = DailySalesSummaryReport()
    summary = report.get_summary(pd.DataFrame())
    assert len(summary) == 3
    assert "0.00" in summary[0]["value"]
    assert summary[1]["value"] == "0"
    assert "0.00" in summary[2]["value"]


def test_inventory_valuation_summary_computation():
    report = InventoryValuationReport()
    df = pd.DataFrame(
        {
            "SKU": ["SKU1", "SKU2"],
            "Product Name": ["Item 1", "Item 2"],
            "Quantity": [10.0, 5.0],
            "Cost Price": [100.0, 200.0],
            "Selling Price": [150.0, 300.0],
            "Total Cost Value": [1000.0, 1000.0],
            "Total Retail Value": [1500.0, 1500.0],
        }
    )

    summary = report.get_summary(df)
    assert len(summary) == 3

    # Total Items
    items_card = summary[0]
    assert items_card["key"] == "total_items"
    assert items_card["value"] == "2"

    # Total Cost Value
    cost_card = summary[1]
    assert cost_card["key"] == "cost_value"
    assert "2,000.00" in cost_card["value"] or "2000.00" in cost_card["value"]

    # Total Retail Value
    retail_card = summary[2]
    assert retail_card["key"] == "retail_value"
    assert "3,000.00" in retail_card["value"] or "3000.00" in retail_card["value"]


def test_inventory_valuation_empty_df():
    report = InventoryValuationReport()
    summary = report.get_summary(pd.DataFrame())
    assert len(summary) == 3
    assert summary[0]["value"] == "0"
    assert "0.00" in summary[1]["value"]
    assert "0.00" in summary[2]["value"]


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_summary_card_i18n_keys_exist(language, lang):
    keys = [
        "reports.summary_total_sales",
        "reports.summary_invoices",
        "reports.summary_avg_ticket",
        "reports.summary_total_items",
        "reports.summary_cost_value",
        "reports.summary_retail_value",
    ]
    for key in keys:
        translated = translate_in(lang, key)
        assert translated != key, f"Missing translation for {key} in {lang}"
