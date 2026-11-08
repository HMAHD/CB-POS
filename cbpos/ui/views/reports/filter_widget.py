"""Report filter widget for building dynamic date-range and combo-box filter inputs."""

import calendar
from datetime import date
from typing import Any

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget


class FilterWidget(QWidget):
    """
    Widget that dynamically generates filter inputs based on definitions.
    """

    def __init__(self):
        """Initialize the widget with an empty horizontal filter layout."""
        super().__init__()
        self.setObjectName("ReportFilterWidget")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.inputs = {}

    def clear_filters(self):
        """Removes all current filter widgets."""
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.inputs = {}

    def build_filters(self, definitions: list[dict[str, Any]]):
        """
        Builds filter widgets based on the provided definitions.
        """
        self.clear_filters()

        for filter_def in definitions:
            f_type = filter_def.get("type")
            f_name = filter_def.get("name")
            f_label = filter_def.get("label", f_name)

            if f_type == "date_range":
                self._add_date_range(f_name, f_label, filter_def)
            elif f_type == "combo":
                self._add_combo(f_name, f_label, filter_def)

            # Add spacing
            self.layout.addSpacing(10)

        # Initialize linked period preset if present (#796)
        if "period" in self.inputs:
            self._on_period_changed("period")

        # No trailing stretch: the filter bar puts Run Report right after
        # these filters and stretches *after* it (#611).

    def _add_date_range(self, name: str, label: str, definition: dict):
        from cbpos.ui.widgets.date_range_picker import DateRangePicker

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = QLabel(f"{label}:")
        lbl.setObjectName("ReportFilterLabel")

        default_start = definition.get("default_start", date.today())
        default_end = definition.get("default_end", date.today())
        default_preset = definition.get("default_preset")

        picker = DateRangePicker(
            parent=container,
            default_start=default_start,
            default_end=default_end,
            default_preset=default_preset,
        )
        picker.setObjectName("ReportDateRangePicker")
        picker.preset_combo.setObjectName("ReportFilterCombo")
        picker.start_date_edit.setObjectName("ReportDateEdit")
        picker.end_date_edit.setObjectName("ReportDateEdit")

        layout.addWidget(lbl)
        layout.addWidget(picker)

        self.layout.addWidget(container)
        self.inputs[name] = {
            "type": "date_range",
            "start": picker.start_date_edit,
            "end": picker.end_date_edit,
            "picker": picker,
        }

    def _add_combo(self, name: str, label: str, definition: dict):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = QLabel(f"{label}:")
        lbl.setObjectName("ReportFilterLabel")
        combo = QComboBox()
        combo.setObjectName("ReportFilterCombo")

        options = definition.get("options", [])
        for opt in options:
            if isinstance(opt, dict):
                combo.addItem(opt.get("label"), opt.get("id"))
            else:
                combo.addItem(str(opt), opt)

        layout.addWidget(lbl)
        layout.addWidget(combo)

        if name == "period":
            month_combo = QComboBox()
            month_combo.setObjectName("ReportMonthCombo")
            month_names = [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ]
            for m in range(1, 13):
                month_combo.addItem(month_names[m - 1], m)
            month_combo.setCurrentIndex(date.today().month - 1)

            quarter_combo = QComboBox()
            quarter_combo.setObjectName("ReportQuarterCombo")
            quarters = [
                (1, "Q1 (Jan - Mar)"),
                (2, "Q2 (Apr - Jun)"),
                (3, "Q3 (Jul - Sep)"),
                (4, "Q4 (Oct - Dec)"),
            ]
            for q_id, q_label in quarters:
                quarter_combo.addItem(q_label, q_id)
            cur_quarter = (date.today().month - 1) // 3 + 1
            quarter_combo.setCurrentIndex(cur_quarter - 1)

            year_combo = QComboBox()
            year_combo.setObjectName("ReportYearCombo")
            cur_year = date.today().year
            for y in range(cur_year - 5, cur_year + 2):
                year_combo.addItem(str(y), y)
            year_combo.setCurrentIndex(year_combo.findData(cur_year))

            layout.addWidget(month_combo)
            layout.addWidget(quarter_combo)
            layout.addWidget(year_combo)

            self.inputs[name] = {
                "type": "combo",
                "widget": combo,
                "month_combo": month_combo,
                "quarter_combo": quarter_combo,
                "year_combo": year_combo,
            }

            combo.currentIndexChanged.connect(lambda: self._on_period_changed(name))
            month_combo.currentIndexChanged.connect(lambda: self._on_period_changed(name))
            quarter_combo.currentIndexChanged.connect(lambda: self._on_period_changed(name))
            year_combo.currentIndexChanged.connect(lambda: self._on_period_changed(name))
        else:
            self.inputs[name] = {"type": "combo", "widget": combo}

        self.layout.addWidget(container)

    def _on_period_changed(self, name: str):
        period_data = self.inputs.get(name)
        if not period_data or "month_combo" not in period_data:
            return

        date_input = self.inputs.get("date_range")
        if not date_input:
            for inp in self.inputs.values():
                if inp.get("type") == "date_range":
                    date_input = inp
                    break

        period_type = period_data["widget"].currentData()
        month_combo = period_data["month_combo"]
        quarter_combo = period_data["quarter_combo"]
        year_combo = period_data["year_combo"]

        if period_type == "month":
            month_combo.setVisible(True)
            quarter_combo.setVisible(False)
            year_combo.setVisible(True)

            month = month_combo.currentData() or date.today().month
            year = year_combo.currentData() or date.today().year
            _, last_day = calendar.monthrange(year, month)
            start_d = date(year, month, 1)
            end_d = date(year, month, last_day)

            if date_input:
                picker = date_input.get("picker")
                if picker and hasattr(picker, "set_range"):
                    picker.set_range(start_d, end_d)
                if "start" in date_input:
                    date_input["start"].setReadOnly(True)
                if "end" in date_input:
                    date_input["end"].setReadOnly(True)
                if picker and hasattr(picker, "preset_combo"):
                    picker.preset_combo.setEnabled(False)

        elif period_type == "quarter":
            month_combo.setVisible(False)
            quarter_combo.setVisible(True)
            year_combo.setVisible(True)

            q = quarter_combo.currentData() or 1
            year = year_combo.currentData() or date.today().year

            if q == 1:
                start_d = date(year, 1, 1)
                end_d = date(year, 3, 31)
            elif q == 2:
                start_d = date(year, 4, 1)
                end_d = date(year, 6, 30)
            elif q == 3:
                start_d = date(year, 7, 1)
                end_d = date(year, 9, 30)
            else:
                start_d = date(year, 10, 1)
                end_d = date(year, 12, 31)

            if date_input:
                picker = date_input.get("picker")
                if picker and hasattr(picker, "set_range"):
                    picker.set_range(start_d, end_d)
                if "start" in date_input:
                    date_input["start"].setReadOnly(True)
                if "end" in date_input:
                    date_input["end"].setReadOnly(True)
                if picker and hasattr(picker, "preset_combo"):
                    picker.preset_combo.setEnabled(False)

        else:  # custom
            month_combo.setVisible(False)
            quarter_combo.setVisible(False)
            year_combo.setVisible(False)

            if date_input:
                picker = date_input.get("picker")
                if "start" in date_input:
                    date_input["start"].setReadOnly(False)
                if "end" in date_input:
                    date_input["end"].setReadOnly(False)
                if picker and hasattr(picker, "preset_combo"):
                    picker.preset_combo.setEnabled(True)

    def get_filter_values(self) -> dict[str, Any]:
        """
        Returns a dictionary of current filter values.
        """
        values = {}
        for name, input_data in self.inputs.items():
            if input_data["type"] == "date_range":
                start_date = input_data["start"].date().toPyDate()
                end_date = input_data["end"].date().toPyDate()
                values[name] = {"start": start_date, "end": end_date}
            elif input_data["type"] == "combo":
                values[name] = input_data["widget"].currentData()
        return values
