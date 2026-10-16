"""Report filter widget for building dynamic date-range and combo-box filter inputs."""

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

        lbl = QLabel(f"{label}:")
        lbl.setObjectName("ReportFilterLabel")
        combo = QComboBox()
        combo.setObjectName("ReportFilterCombo")

        options = definition.get("options", [])
        for opt in options:
            # Assuming options are dicts {'id': ..., 'label': ...} or tuples
            if isinstance(opt, dict):
                combo.addItem(opt.get("label"), opt.get("id"))
            else:
                combo.addItem(str(opt), opt)

        layout.addWidget(lbl)
        layout.addWidget(combo)

        self.layout.addWidget(container)
        self.inputs[name] = {"type": "combo", "widget": combo}

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
