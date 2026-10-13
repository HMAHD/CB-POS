"""Promotion view for listing, creating, and managing discount promotions."""

import weakref
from datetime import datetime
from decimal import Decimal

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.category_service import CategoryService
from cbpos.core.services.promotion_service import SUPPORTED_TYPES, PromotionService
from cbpos.core.utils.formatters import format_discount
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.resources.status_colors import DANGER, INFO, NEUTRAL, SUCCESS
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.status_pill_delegate import StatusPillDelegate, set_status_pill
from cbpos.ui.widgets.table_helpers import NUMERIC_ALIGNMENT, align_numeric_headers, configure_table_columns

_DAY_KEYS = [
    "promotion.day_mon",
    "promotion.day_tue",
    "promotion.day_wed",
    "promotion.day_thu",
    "promotion.day_fri",
    "promotion.day_sat",
    "promotion.day_sun",
]


class PromotionView(QWidget):
    """Promotion list view with add, edit, activate/deactivate, and delete actions."""

    def __init__(self):
        """Initialize the promotion service, build the UI, and load existing promotions."""
        super().__init__()
        self.promotion_service = PromotionService()
        self.init_ui()
        self.load_promotions()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        # weakref avoids a self -> destroyed-connection -> lambda -> self
        # reference cycle that only a full gc.collect() can break, which
        # can segfault mid-teardown (#392).
        self_ref = weakref.ref(self)

        def _unregister():
            view = self_ref()
            if view is not None:
                unregister_language_callback(view.retranslate_ui)

        self.destroyed.connect(_unregister)

    def init_ui(self):
        """Build the header and promotions table layout."""
        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        from cbpos.ui.resources.icons import Icons
        from cbpos.ui.widgets.page_header import PageHeader

        self._page_header = PageHeader(icon_name=Icons.PROMOTION)
        header.addWidget(self._page_header, 1)

        self.btn_add = QPushButton()
        self.btn_add.setProperty("class", "accent")
        self.btn_add.clicked.connect(self.add_promotion)
        header.addWidget(self.btn_add)

        layout.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,  # Name - needs the room
                1: QHeaderView.ResizeMode.ResizeToContents,  # Type
                2: QHeaderView.ResizeMode.ResizeToContents,  # Value
                3: QHeaderView.ResizeMode.ResizeToContents,  # Start
                4: QHeaderView.ResizeMode.ResizeToContents,  # End
                5: QHeaderView.ResizeMode.ResizeToContents,  # Scope
                6: QHeaderView.ResizeMode.ResizeToContents,  # Status
            },
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setItemDelegateForColumn(6, StatusPillDelegate(self.table))  # Status (#560)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_promotion)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)

    def retranslate_ui(self):
        """Update all translatable strings."""
        self._page_header.set_title(_t("promotion.title"))
        self.btn_add.setText(_t("promotion.create_promotion"))
        self.table.setHorizontalHeaderLabels(
            [
                _t("common.name"),
                _t("promotion.type"),
                _t("promotion.value"),
                _t("promotion.start"),
                _t("promotion.end"),
                _t("promotion.scope"),
                _t("common.status"),
            ]
        )
        align_numeric_headers(self.table, (2,))  # Value

    @staticmethod
    def _get_promotion_status(promotion) -> tuple[str, str]:
        """Return (label, palette meaning) reflecting whether a promotion is really
        active right now, rather than trusting its stored is_active flag on
        its own -- that flag is only ever set True at creation and otherwise
        only changes when an admin manually toggles it, so a promotion whose
        end_time passed months ago would otherwise show "Active" forever.
        """
        if not promotion.is_active:
            return _t("common.inactive"), NEUTRAL
        # Checkout has no BOGO branch, so such a promotion never applies (#635).
        if promotion.type not in SUPPORTED_TYPES:
            return _t("promotion.status_not_applied"), DANGER

        now = datetime.now()
        if promotion.end_time < now:
            return _t("promotion.status_expired"), NEUTRAL
        if promotion.start_time > now:
            return _t("promotion.status_upcoming"), INFO
        return _t("common.active"), SUCCESS

    def load_promotions(self):
        """Reload promotions from the service and repopulate the table."""
        self.promotions = self.promotion_service.get_all_promotions()
        self.table.setRowCount(0)
        for p in self.promotions:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(p.name))
            self.table.setItem(row, 1, QTableWidgetItem(p.type))
            value_item = QTableWidgetItem(format_discount(p.type, p.value))
            value_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table.setItem(row, 2, value_item)
            self.table.setItem(row, 3, QTableWidgetItem(p.start_time.strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 4, QTableWidgetItem(p.end_time.strftime("%Y-%m-%d %H:%M")))

            scope_text = p.category.name if p.category_id and p.category else _t("promotion.scope_all_products")
            self.table.setItem(row, 5, QTableWidgetItem(scope_text))

            status_text, meaning = self._get_promotion_status(p)
            self.table.setItem(row, 6, set_status_pill(QTableWidgetItem(), status_text, meaning))

    def add_promotion(self):
        """Open the create dialog and persist a new promotion on accept."""
        dialog = PromotionDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            try:
                self.promotion_service.create_promotion(**data)
                self.load_promotions()
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), str(e))

    def _show_context_menu(self, position) -> None:
        item = self.table.itemAt(position)
        if not item:
            return
        row = item.row()
        promotion = self.promotions[row]

        menu = QMenu(self)
        action_edit = menu.addAction(_t("promotion.context_edit"))
        toggle_label = _t("promotion.context_deactivate") if promotion.is_active else _t("promotion.context_activate")
        action_toggle = menu.addAction(toggle_label)
        action_delete = menu.addAction(_t("promotion.context_delete"))

        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen == action_edit:
            self._edit_promotion_row(row)
        elif chosen == action_toggle:
            self._toggle_promotion_active(row)
        elif chosen == action_delete:
            self._delete_promotion_row(row)

    def edit_promotion(self, index) -> None:
        """Open the edit dialog for the double-clicked table row."""
        self._edit_promotion_row(index.row())

    def _edit_promotion_row(self, row: int) -> None:
        if row < 0 or row >= len(self.promotions):
            return
        promotion = self.promotions[row]

        dialog = PromotionDialog(self, promotion=promotion)
        if dialog.exec():
            data = dialog.get_data()
            try:
                self.promotion_service.update_promotion(promotion.id, **data)
                self.load_promotions()
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), str(e))

    def _toggle_promotion_active(self, row: int) -> None:
        if row < 0 or row >= len(self.promotions):
            return
        promotion = self.promotions[row]

        try:
            self.promotion_service.update_promotion(promotion.id, is_active=not promotion.is_active)
            self.load_promotions()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))

    def _delete_promotion_row(self, row: int) -> None:
        if row < 0 or row >= len(self.promotions):
            return
        promotion = self.promotions[row]

        reply = QMessageBox.question(
            self,
            _t("promotion.confirm_delete_title"),
            _t("promotion.confirm_delete_msg", name=promotion.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.promotion_service.delete_promotion(promotion.id)
            self.load_promotions()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))


class PromotionDialog(QDialog):
    """Dialog for creating or editing a promotion's type, value, scope, and schedule."""

    def __init__(self, parent=None, promotion=None):
        """Build the form and pre-fill fields when editing an existing promotion."""
        super().__init__(parent)
        self.promotion = promotion
        self.setWindowTitle(_t("promotion.edit_promotion") if promotion else _t("promotion.new_promotion"))
        self.setMinimumWidth(480)
        self.init_ui()

        if promotion:
            self.name_input.setText(promotion.name)
            # Keep a legacy BOGO promotion loadable/editable; new ones can't pick it (#635).
            if promotion.type == "BOGO":
                self.type_combo.addItem(_t("promotion.type_bogo"), "BOGO")
            index = self.type_combo.findData(promotion.type)
            if index >= 0:
                self.type_combo.setCurrentIndex(index)
            self.value_input.setValue(float(promotion.value))
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

        self.value_input = QDoubleSpinBox()
        self.value_input.setRange(0, 100000)
        self.value_input.setDecimals(2)

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
            "value": Decimal(str(self.value_input.value())),
            "start_time": self.start_dt.dateTime().toPyDateTime(),
            "end_time": self.end_dt.dateTime().toPyDateTime(),
            "days_of_week": None if all_checked else ",".join(checked_indices),
            "category_id": self.category_combo.currentData(),
        }
