"""Dialog for creating or editing a promotion's type, value, scope, and schedule."""

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.category_service import CategoryService
from cbpos.core.services.promotion_service import PromotionService
from cbpos.i18n import _t
from cbpos.ui.widgets.decimal_line_edit import DecimalLineEdit
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

_DAY_KEYS = [
    "promotion.day_mon",
    "promotion.day_tue",
    "promotion.day_wed",
    "promotion.day_thu",
    "promotion.day_fri",
    "promotion.day_sat",
    "promotion.day_sun",
]


class PromotionDialog(QDialog):
    """Dialog for creating or editing a promotion's type, value, scope, and schedule."""

    def __init__(self, parent=None, promotion=None):
        """Build the form and pre-fill fields when editing an existing promotion."""
        super().__init__(parent)
        self.promotion = promotion
        self.setWindowTitle(_t("promotion.edit_promotion") if promotion else _t("promotion.new_promotion"))
        self.setMinimumWidth(480)
        self.init_ui()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

        if promotion:
            self.name_input.setText(promotion.name)
            # Keep a legacy BOGO promotion loadable/editable; new ones can't pick it (#635).
            if promotion.type == "BOGO":
                self.type_combo.addItem(_t("promotion.type_bogo"), "BOGO")
            index = self.type_combo.findData(promotion.type)
            if index >= 0:
                self.type_combo.setCurrentIndex(index)
            self.value_input.setValue(promotion.value)
            self.start_dt.setDateTime(QDateTime(promotion.start_time))
            self.end_dt.setDateTime(QDateTime(promotion.end_time))

            cat_index = self.category_combo.findData(promotion.category_id)
            if cat_index >= 0:
                self.category_combo.setCurrentIndex(cat_index)

            checked_days = set((promotion.days_of_week or "").split(",")) if promotion.days_of_week else None
            for i, checkbox in enumerate(self.day_checkboxes):
                checkbox.setChecked(checked_days is None or str(i) in checked_days)

    def _set_days_checked(self, indices) -> None:
        """Check or uncheck day checkboxes by day index."""
        target = set(indices)
        for i, checkbox in enumerate(self.day_checkboxes):
            checkbox.setChecked(i in target)

    def init_ui(self):
        """Build the name, type, value, scope, schedule, and days-of-week form."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)

        self.name_input = QLineEdit()

        self.type_combo = QComboBox()
        self.type_combo.addItem(_t("promotion.type_percentage"), "PERCENTAGE")
        self.type_combo.addItem(_t("promotion.type_fixed_amount"), "FIXED_AMOUNT")

        self.value_input = DecimalLineEdit(0.0, 100000.0, 2, self)

        self.category_combo = QComboBox()
        self.category_combo.addItem(_t("promotion.scope_all_products"), None)
        for category in CategoryService.get_all():
            self.category_combo.addItem(category.name, category.id)

        self.start_dt = QDateTimeEdit()
        self.start_dt.setDateTime(QDateTime.currentDateTime())
        self.start_dt.setCalendarPopup(True)

        self.end_dt = QDateTimeEdit()
        self.end_dt.setDateTime(QDateTime.currentDateTime().addDays(7))
        self.end_dt.setCalendarPopup(True)

        days_box = QWidget()
        days_box_layout = QVBoxLayout(days_box)
        days_box_layout.setContentsMargins(0, 0, 0, 0)
        days_box_layout.setSpacing(6)

        # Quick select buttons (All / Weekdays / Weekend)
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(6)

        self.btn_all_days = QPushButton(_t("promotion.quick_all"))
        self.btn_all_days.setProperty("class", "secondary")
        self.btn_all_days.setAutoDefault(False)
        self.btn_all_days.setFixedHeight(26)
        self.btn_all_days.clicked.connect(lambda: self._set_days_checked(range(7)))

        self.btn_weekdays = QPushButton(_t("promotion.quick_weekdays"))
        self.btn_weekdays.setProperty("class", "secondary")
        self.btn_weekdays.setAutoDefault(False)
        self.btn_weekdays.setFixedHeight(26)
        self.btn_weekdays.clicked.connect(lambda: self._set_days_checked(range(5)))

        self.btn_weekend = QPushButton(_t("promotion.quick_weekend"))
        self.btn_weekend.setProperty("class", "secondary")
        self.btn_weekend.setAutoDefault(False)
        self.btn_weekend.setFixedHeight(26)
        self.btn_weekend.clicked.connect(lambda: self._set_days_checked([5, 6]))

        quick_layout.addWidget(self.btn_all_days)
        quick_layout.addWidget(self.btn_weekdays)
        quick_layout.addWidget(self.btn_weekend)
        quick_layout.addStretch()
        days_box_layout.addLayout(quick_layout)

        # 4+3 Grid layout for day checkboxes so they fit comfortably in en/si/ta
        grid_days = QGridLayout()
        grid_days.setHorizontalSpacing(12)
        grid_days.setVerticalSpacing(4)
        self.day_checkboxes = []
        for i, key in enumerate(_DAY_KEYS):
            checkbox = QCheckBox(_t(key))
            checkbox.setChecked(True)
            row = 0 if i < 4 else 1
            col = i if i < 4 else i - 4
            grid_days.addWidget(checkbox, row, col)
            self.day_checkboxes.append(checkbox)

        days_box_layout.addLayout(grid_days)

        form.addRow(_t("promotion.name_label"), self.name_input)
        form.addRow(_t("promotion.type_label"), self.type_combo)
        form.addRow(_t("promotion.value_label"), self.value_input)
        form.addRow(_t("promotion.scope_label"), self.category_combo)
        form.addRow(_t("promotion.start_time_label"), self.start_dt)
        form.addRow(_t("promotion.end_time_label"), self.end_dt)
        form.addRow(_t("promotion.days_label"), days_box)

        layout.addLayout(form)

        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self.validate_and_accept,
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)

    def validate_and_accept(self) -> None:
        """Validate form fields before accepting the dialog."""
        if not self.name_input.text().strip():
            QMessageBox.warning(self, _t("common.validation_error"), _t("promotion.name_required"))
            return

        if self.start_dt.dateTime() >= self.end_dt.dateTime():
            QMessageBox.warning(self, _t("common.validation_error"), _t("promotion.start_before_end"))
            return

        data = self.get_data()
        try:
            PromotionService().validate_promotion(
                data["type"], data["value"], data["days_of_week"], data["category_id"]
            )
        except ValueError as e:
            QMessageBox.warning(self, _t("common.validation_error"), str(e))
            return

        self.accept()

    def get_data(self):
        """Return the form values as a dict of promotion fields for the service layer."""
        checked_indices = [str(i) for i, cb in enumerate(self.day_checkboxes) if cb.isChecked()]
        all_checked = len(checked_indices) == len(self.day_checkboxes)

        return {
            "name": self.name_input.text(),
            "type": self.type_combo.currentData(),
            "value": self.value_input.decimal_value(),
            "start_time": self.start_dt.dateTime().toPyDateTime(),
            "end_time": self.end_dt.dateTime().toPyDateTime(),
            "days_of_week": None if all_checked else ",".join(checked_indices),
            "category_id": self.category_combo.currentData(),
        }
