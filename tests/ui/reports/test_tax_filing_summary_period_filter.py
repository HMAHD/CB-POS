from datetime import date

import pytest
from PyQt6.QtCore import QDate

from cbpos.core.reports.definitions.financial_reports import TaxFilingSummaryReport
from cbpos.ui.views.reports.filter_widget import FilterWidget

pytestmark = pytest.mark.usefixtures("qapp")


class TestTaxFilingSummaryPeriodFilterWidget:
    """Test period resolution (Monthly, Quarterly, Custom) in FilterWidget for Issue #796."""

    def test_monthly_period_resolution_updates_date_range(self):
        widget = FilterWidget()
        report = TaxFilingSummaryReport()
        widget.build_filters(report.get_filter_definitions())

        # Select 'month'
        period_data = widget.inputs["period"]
        combo = period_data["widget"]
        idx = combo.findData("month")
        assert idx >= 0
        combo.setCurrentIndex(idx)

        # Set month to February (2) and year to 2026
        period_data["month_combo"].setCurrentIndex(period_data["month_combo"].findData(2))
        period_data["year_combo"].setCurrentIndex(period_data["year_combo"].findData(2026))

        # Check filter values
        values = widget.get_filter_values()
        assert values["period"] == "month"
        date_range = values["date_range"]
        assert date_range["start"] == date(2026, 2, 1)
        assert date_range["end"] == date(2026, 2, 28)

        # Check date edits are read-only when period is month
        date_inputs = widget.inputs["date_range"]
        assert date_inputs["start"].isReadOnly()
        assert date_inputs["end"].isReadOnly()

    def test_quarterly_period_resolution_updates_date_range(self):
        widget = FilterWidget()
        report = TaxFilingSummaryReport()
        widget.build_filters(report.get_filter_definitions())

        period_data = widget.inputs["period"]
        combo = period_data["widget"]
        idx = combo.findData("quarter")
        assert idx >= 0
        combo.setCurrentIndex(idx)

        # Select Q1 and 2026
        period_data["quarter_combo"].setCurrentIndex(period_data["quarter_combo"].findData(1))
        period_data["year_combo"].setCurrentIndex(period_data["year_combo"].findData(2026))

        values = widget.get_filter_values()
        assert values["period"] == "quarter"
        date_range = values["date_range"]
        assert date_range["start"] == date(2026, 1, 1)
        assert date_range["end"] == date(2026, 3, 31)

        date_inputs = widget.inputs["date_range"]
        assert date_inputs["start"].isReadOnly()
        assert date_inputs["end"].isReadOnly()

    def test_custom_period_allows_manual_date_edits(self):
        widget = FilterWidget()
        report = TaxFilingSummaryReport()
        widget.build_filters(report.get_filter_definitions())

        period_data = widget.inputs["period"]
        combo = period_data["widget"]
        idx = combo.findData("custom")
        assert idx >= 0
        combo.setCurrentIndex(idx)

        date_inputs = widget.inputs["date_range"]
        assert not date_inputs["start"].isReadOnly()
        assert not date_inputs["end"].isReadOnly()

        # Manually set dates
        date_inputs["start"].setDate(QDate(2026, 5, 10))
        date_inputs["end"].setDate(QDate(2026, 5, 20))

        values = widget.get_filter_values()
        assert values["period"] == "custom"
        assert values["date_range"]["start"] == date(2026, 5, 10)
        assert values["date_range"]["end"] == date(2026, 5, 20)
