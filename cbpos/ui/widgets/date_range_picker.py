"""Shared Date Range Picker widget with quick presets and manual date inputs.

Supports quick presets:
- Today
- Yesterday
- This Week (Monday - Sunday)
- Last Week (Monday - Sunday)
- This Month (1st - last day)
- Last Month (1st - last day)
- Last 7 Days
- Last 30 Days
- Custom

Manual date edits automatically switch the preset combo to 'Custom'.
Fully localized in English, Sinhala, and Tamil.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from PyQt6.QtCore import QDate, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from cbpos.i18n import _t, register_language_callback

PRESET_TODAY = "today"
PRESET_YESTERDAY = "yesterday"
PRESET_THIS_WEEK = "this_week"
PRESET_LAST_WEEK = "last_week"
PRESET_THIS_MONTH = "this_month"
PRESET_LAST_MONTH = "last_month"
PRESET_LAST_7_DAYS = "last_7_days"
PRESET_LAST_30_DAYS = "last_30_days"
PRESET_CUSTOM = "custom"

ALL_PRESETS = [
    PRESET_TODAY,
    PRESET_YESTERDAY,
    PRESET_THIS_WEEK,
    PRESET_LAST_WEEK,
    PRESET_THIS_MONTH,
    PRESET_LAST_MONTH,
    PRESET_LAST_7_DAYS,
    PRESET_LAST_30_DAYS,
    PRESET_CUSTOM,
]


def compute_preset_range(preset: str, ref_date: date | None = None) -> tuple[date, date]:
    """Calculates start and end dates for a given preset key.

    Week starts on Monday (ISO-8601).
    """
    today = ref_date or date.today()
    if preset == PRESET_TODAY:
        return today, today
    elif preset == PRESET_YESTERDAY:
        y = today - timedelta(days=1)
        return y, y
    elif preset == PRESET_THIS_WEEK:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end
    elif preset == PRESET_LAST_WEEK:
        this_mon = today - timedelta(days=today.weekday())
        start = this_mon - timedelta(days=7)
        end = start + timedelta(days=6)
        return start, end
    elif preset == PRESET_THIS_MONTH:
        start = today.replace(day=1)
        _, last_day = calendar.monthrange(today.year, today.month)
        end = today.replace(day=last_day)
        return start, end
    elif preset == PRESET_LAST_MONTH:
        if today.month == 1:
            py, pm = today.year - 1, 12
        else:
            py, pm = today.year, today.month - 1
        _, last_day = calendar.monthrange(py, pm)
        return date(py, pm, 1), date(py, pm, last_day)
    elif preset == PRESET_LAST_7_DAYS:
        return today - timedelta(days=6), today
    elif preset == PRESET_LAST_30_DAYS:
        return today - timedelta(days=29), today
    return today, today


class DateRangePicker(QWidget):
    """Composite date range selector combining quick preset shortcuts with manual QDateEdit inputs.

    Signals:
        range_changed(date, date): Emitted when either the preset changes or dates are manually edited.
    """

    range_changed = pyqtSignal(object, object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        default_start: date | None = None,
        default_end: date | None = None,
        default_preset: str | None = None,
        presets: list[str] | None = None,
    ):
        super().__init__(parent)
        self._presets = list(presets) if presets else list(ALL_PRESETS)
        self._is_updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.preset_combo = QComboBox(self)
        self.preset_combo.setObjectName("DateRangePresetCombo")

        self.start_date_edit = QDateEdit(self)
        self.start_date_edit.setObjectName("DateRangeStartEdit")
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")

        self.separator_label = QLabel("-", self)
        self.separator_label.setObjectName("DateRangeSeparator")

        self.end_date_edit = QDateEdit(self)
        self.end_date_edit.setObjectName("DateRangeEndEdit")
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")

        layout.addWidget(self.preset_combo)
        layout.addWidget(self.start_date_edit)
        layout.addWidget(self.separator_label)
        layout.addWidget(self.end_date_edit)

        self.retranslate_ui()

        # Connect signals
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.start_date_edit.dateChanged.connect(self._on_date_manually_edited)
        self.end_date_edit.dateChanged.connect(self._on_date_manually_edited)

        # Wire language switching
        register_language_callback(self.retranslate_ui, owner=self)

        # Initialize dates and selected preset
        if default_start is not None and default_end is not None:
            self.set_range(default_start, default_end, preset=default_preset)
        elif default_preset is not None:
            self.set_preset(default_preset)
        else:
            self.set_preset(PRESET_TODAY)

    def retranslate_ui(self):
        """Populate preset combo items with current language translations."""
        current_key = self.preset_combo.currentData() or PRESET_CUSTOM
        self._is_updating = True
        try:
            self.preset_combo.clear()
            for key in self._presets:
                label = _t(f"date_presets.{key}")
                if label.startswith("date_presets."):
                    label = key.replace("_", " ").title()
                self.preset_combo.addItem(label, key)

            idx = self.preset_combo.findData(current_key)
            if idx >= 0:
                self.preset_combo.setCurrentIndex(idx)
        finally:
            self._is_updating = False

    @property
    def start_date(self) -> date:
        """Returns the currently selected start date."""
        return self.start_date_edit.date().toPyDate()

    @property
    def end_date(self) -> date:
        """Returns the currently selected end date."""
        return self.end_date_edit.date().toPyDate()

    def get_range(self) -> tuple[date, date]:
        """Returns the (start_date, end_date) tuple."""
        return self.start_date, self.end_date

    def get_preset(self) -> str:
        """Returns the active preset key, or 'custom'."""
        return self.preset_combo.currentData() or PRESET_CUSTOM

    def set_range(self, start: date, end: date, preset: str | None = None):
        """Sets both date inputs and updates the preset selection."""
        self._is_updating = True
        try:
            self.start_date_edit.setDate(QDate(start.year, start.month, start.day))
            self.end_date_edit.setDate(QDate(end.year, end.month, end.day))

            if preset:
                idx = self.preset_combo.findData(preset)
                if idx >= 0:
                    self.preset_combo.setCurrentIndex(idx)
            else:
                matched = self._find_matching_preset(start, end)
                idx = self.preset_combo.findData(matched or PRESET_CUSTOM)
                if idx >= 0:
                    self.preset_combo.setCurrentIndex(idx)
        finally:
            self._is_updating = False

    def set_preset(self, preset_key: str):
        """Selects a preset by key and updates date inputs."""
        idx = self.preset_combo.findData(preset_key)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        if preset_key != PRESET_CUSTOM:
            start, end = compute_preset_range(preset_key)
            self._is_updating = True
            try:
                self.start_date_edit.setDate(QDate(start.year, start.month, start.day))
                self.end_date_edit.setDate(QDate(end.year, end.month, end.day))
            finally:
                self._is_updating = False

    def _find_matching_preset(self, start: date, end: date) -> str | None:
        """Finds if given (start, end) matches any known non-custom preset."""
        for p in self._presets:
            if p == PRESET_CUSTOM:
                continue
            if compute_preset_range(p) == (start, end):
                return p
        return None

    def _on_preset_changed(self, index: int):
        if self._is_updating or index < 0:
            return
        preset_key = self.preset_combo.itemData(index)
        if preset_key == PRESET_CUSTOM:
            return
        start, end = compute_preset_range(preset_key)
        self._is_updating = True
        try:
            self.start_date_edit.setDate(QDate(start.year, start.month, start.day))
            self.end_date_edit.setDate(QDate(end.year, end.month, end.day))
        finally:
            self._is_updating = False
        self.range_changed.emit(self.start_date, self.end_date)

    def _on_date_manually_edited(self, _qdate: QDate):
        if self._is_updating:
            return
        self._is_updating = True
        try:
            idx = self.preset_combo.findData(PRESET_CUSTOM)
            if idx >= 0 and self.preset_combo.currentIndex() != idx:
                self.preset_combo.setCurrentIndex(idx)
        finally:
            self._is_updating = False
        self.range_changed.emit(self.start_date, self.end_date)
