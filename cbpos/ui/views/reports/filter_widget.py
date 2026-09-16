from datetime import date
from typing import Any

from PyQt6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QLabel, QWidget


class FilterWidget(QWidget):
    """
    Widget that dynamically generates filter inputs based on definitions.
    """

    def __init__(self):
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

        self.layout.addStretch()

    def _add_date_range(self, name: str, label: str, definition: dict):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(f"{label}:")
        lbl.setObjectName("ReportFilterLabel")
        start_edit = QDateEdit()
        start_edit.setObjectName("ReportDateEdit")
        start_edit.setCalendarPopup(True)
        start_edit.setDisplayFormat("yyyy-MM-dd")
        end_edit = QDateEdit()
        end_edit.setObjectName("ReportDateEdit")
        end_edit.setCalendarPopup(True)
        end_edit.setDisplayFormat("yyyy-MM-dd")

        default_start = definition.get("default_start", date.today())
        default_end = definition.get("default_end", date.today())

        start_edit.setDate(default_start)
        end_edit.setDate(default_end)

        layout.addWidget(lbl)
        layout.addWidget(start_edit)
        layout.addWidget(QLabel("-"))
        layout.addWidget(end_edit)

        self.layout.addWidget(container)
        self.inputs[name] = {"type": "date_range", "start": start_edit, "end": end_edit}

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
