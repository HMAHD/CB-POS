"""Unit tests for DateRangePicker and date preset calculations (#540)."""

from datetime import date, timedelta

import pytest
from PyQt6.QtCore import QDate

from cbpos.i18n import set_language
from cbpos.ui.views.reports.filter_widget import FilterWidget
from cbpos.ui.widgets.date_range_picker import (
    PRESET_CUSTOM,
    PRESET_LAST_7_DAYS,
    PRESET_LAST_30_DAYS,
    PRESET_LAST_MONTH,
    PRESET_LAST_WEEK,
    PRESET_THIS_MONTH,
    PRESET_THIS_WEEK,
    PRESET_TODAY,
    PRESET_YESTERDAY,
    DateRangePicker,
    compute_preset_range,
)

pytestmark = pytest.mark.usefixtures("qapp")


class TestComputePresetRange:
    """Tests the mathematical calculations for each date preset."""

    def test_preset_today(self):
        ref = date(2026, 10, 16)
        start, end = compute_preset_range(PRESET_TODAY, ref)
        assert start == ref
        assert end == ref

    def test_preset_yesterday(self):
        ref = date(2026, 10, 16)
        start, end = compute_preset_range(PRESET_YESTERDAY, ref)
        assert start == date(2026, 10, 15)
        assert end == date(2026, 10, 15)

    def test_preset_this_week_starts_monday(self):
        # 2026-10-16 is a Friday (weekday=4). Monday is 2026-10-12, Sunday is 2026-10-18.
        ref = date(2026, 10, 16)
        start, end = compute_preset_range(PRESET_THIS_WEEK, ref)
        assert start == date(2026, 10, 12)
        assert start.weekday() == 0  # Monday
        assert end == date(2026, 10, 18)
        assert end.weekday() == 6  # Sunday

    def test_preset_last_week(self):
        ref = date(2026, 10, 16)
        start, end = compute_preset_range(PRESET_LAST_WEEK, ref)
        assert start == date(2026, 10, 5)
        assert start.weekday() == 0
        assert end == date(2026, 10, 11)
        assert end.weekday() == 6

    def test_preset_this_month(self):
        ref = date(2026, 10, 16)
        start, end = compute_preset_range(PRESET_THIS_MONTH, ref)
        assert start == date(2026, 10, 1)
        assert end == date(2026, 10, 31)

    def test_preset_last_month_standard(self):
        ref = date(2026, 10, 16)
        start, end = compute_preset_range(PRESET_LAST_MONTH, ref)
        assert start == date(2026, 9, 1)
        assert end == date(2026, 9, 30)

    def test_preset_last_month_year_boundary(self):
        ref = date(2026, 1, 15)
        start, end = compute_preset_range(PRESET_LAST_MONTH, ref)
        assert start == date(2025, 12, 1)
        assert end == date(2025, 12, 31)

    def test_preset_last_7_days(self):
        ref = date(2026, 10, 16)
        start, end = compute_preset_range(PRESET_LAST_7_DAYS, ref)
        assert start == date(2026, 10, 10)
        assert end == date(2026, 10, 16)
        assert (end - start).days == 6  # 7 days inclusive

    def test_preset_last_30_days(self):
        ref = date(2026, 10, 16)
        start, end = compute_preset_range(PRESET_LAST_30_DAYS, ref)
        assert start == date(2026, 9, 17)
        assert end == date(2026, 10, 16)
        assert (end - start).days == 29  # 30 days inclusive


class TestDateRangePickerWidget:
    """Tests DateRangePicker widget behavior, signals, and manual switches."""

    def test_preset_selection_updates_dates_and_emits_signal(self):
        picker = DateRangePicker(default_preset=PRESET_TODAY)
        emitted = []
        picker.range_changed.connect(lambda s, e: emitted.append((s, e)))

        # Select 'this_month'
        idx = picker.preset_combo.findData(PRESET_THIS_MONTH)
        assert idx >= 0
        picker.preset_combo.setCurrentIndex(idx)

        expected_start, expected_end = compute_preset_range(PRESET_THIS_MONTH)
        assert picker.start_date == expected_start
        assert picker.end_date == expected_end
        assert picker.get_preset() == PRESET_THIS_MONTH
        assert len(emitted) == 1
        assert emitted[0] == (expected_start, expected_end)

    def test_manual_date_edit_switches_preset_to_custom(self):
        picker = DateRangePicker(default_preset=PRESET_TODAY)
        assert picker.get_preset() == PRESET_TODAY

        emitted = []
        picker.range_changed.connect(lambda s, e: emitted.append((s, e)))

        # User edits start date manually
        new_start = date.today() - timedelta(days=4)
        picker.start_date_edit.setDate(QDate(new_start.year, new_start.month, new_start.day))

        assert picker.get_preset() == PRESET_CUSTOM
        assert picker.start_date == new_start
        assert picker.end_date == date.today()
        assert len(emitted) >= 1
        assert emitted[-1] == (new_start, date.today())

    def test_set_range_auto_matches_or_sets_custom(self):
        picker = DateRangePicker()
        today = date.today()
        picker.set_range(today, today)
        assert picker.get_preset() == PRESET_TODAY

        custom_start = today - timedelta(days=12)
        custom_end = today - timedelta(days=3)
        picker.set_range(custom_start, custom_end)
        assert picker.get_preset() == PRESET_CUSTOM
        assert picker.start_date == custom_start
        assert picker.end_date == custom_end

    def test_trilingual_translations(self):
        picker = DateRangePicker()

        # English
        set_language("en")
        picker.retranslate_ui()
        today_idx = picker.preset_combo.findData(PRESET_TODAY)
        assert picker.preset_combo.itemText(today_idx) == "Today"
        custom_idx = picker.preset_combo.findData(PRESET_CUSTOM)
        assert picker.preset_combo.itemText(custom_idx) == "Custom"

        # Sinhala
        set_language("si")
        picker.retranslate_ui()
        assert picker.preset_combo.itemText(today_idx) == "අද"
        assert picker.preset_combo.itemText(custom_idx) == "අභිරුචි"

        # Tamil
        set_language("ta")
        picker.retranslate_ui()
        assert picker.preset_combo.itemText(today_idx) == "இன்று"
        assert picker.preset_combo.itemText(custom_idx) == "தனிப்பயன்"

        # Reset to en
        set_language("en")


class TestFilterWidgetIntegration:
    """Tests DateRangePicker integration with reports FilterWidget."""

    def test_filter_widget_builds_picker_and_returns_values(self):
        widget = FilterWidget()
        widget.build_filters([{"type": "date_range", "name": "period", "label": "Period"}])

        input_data = widget.inputs["period"]
        assert "picker" in input_data
        picker = input_data["picker"]
        assert isinstance(picker, DateRangePicker)

        # Select 'yesterday'
        picker.set_preset(PRESET_YESTERDAY)
        values = widget.get_filter_values()
        y = date.today() - timedelta(days=1)
        assert values["period"] == {"start": y, "end": y}
