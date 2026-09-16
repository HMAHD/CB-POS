from datetime import datetime
from decimal import Decimal

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
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
from cbpos.core.services.promotion_service import PromotionService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.widgets.table_helpers import configure_table_columns

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
    def __init__(self):
        super().__init__()
        self.promotion_service = PromotionService()
        self.init_ui()
        self.load_promotions()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def init_ui(self):
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
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_promotion)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)

    def retranslate_ui(self):
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

    @staticmethod
    def _get_promotion_status(promotion) -> tuple[str, QColor]:
        """Return (label, colour) reflecting whether a promotion is really
        active right now, rather than trusting its stored is_active flag on
        its own -- that flag is only ever set True at creation and otherwise
        only changes when an admin manually toggles it, so a promotion whose
        end_time passed months ago would otherwise show "Active" forever.
        """
        if not promotion.is_active:
            return _t("common.inactive"), QColor("#888888")

        now = datetime.now()
        if promotion.end_time < now:
            return _t("promotion.status_expired"), QColor("#888888")
        if promotion.start_time > now:
            return _t("promotion.status_upcoming"), QColor("#5599FF")
        return _t("common.active"), QColor("#39FF14")

    def load_promotions(self):
        self.promotions = self.promotion_service.get_all_promotions()
        self.table.setRowCount(0)
        for p in self.promotions:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(p.name))
            self.table.setItem(row, 1, QTableWidgetItem(p.type))
            self.table.setItem(row, 2, QTableWidgetItem(f"{p.value:.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(p.start_time.strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 4, QTableWidgetItem(p.end_time.strftime("%Y-%m-%d %H:%M")))

            scope_text = p.category.name if p.category_id and p.category else _t("promotion.scope_all_products")
            self.table.setItem(row, 5, QTableWidgetItem(scope_text))

            status_text, status_colour = self._get_promotion_status(p)
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(status_colour)
            self.table.setItem(row, 6, status_item)

    def add_promotion(self):
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
    def __init__(self, parent=None, promotion=None):
        super().__init__(parent)
        self.promotion = promotion
        self.setWindowTitle(_t("promotion.edit_promotion") if promotion else _t("promotion.new_promotion"))
        self.setMinimumWidth(400)
        self.init_ui()

        if promotion:
            self.name_input.setText(promotion.name)
            index = self.type_combo.findText(promotion.type)
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

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit()

        self.type_combo = QComboBox()
        self.type_combo.addItems(["PERCENTAGE", "FIXED_AMOUNT", "BOGO"])
        self.type_combo.setMaximumWidth(200)

        self.value_input = QDoubleSpinBox()
        self.value_input.setRange(0, 100000)
        self.value_input.setDecimals(2)
        self.value_input.setMaximumWidth(150)

        self.category_combo = QComboBox()
        self.category_combo.setMaximumWidth(250)
        self.category_combo.addItem(_t("promotion.scope_all_products"), None)
        for category in CategoryService.get_all():
            self.category_combo.addItem(category.name, category.id)

        self.start_dt = QDateTimeEdit()
        self.start_dt.setDateTime(QDateTime.currentDateTime())
        self.start_dt.setCalendarPopup(True)
        self.start_dt.setMaximumWidth(220)

        self.end_dt = QDateTimeEdit()
        self.end_dt.setDateTime(QDateTime.currentDateTime().addDays(7))
        self.end_dt.setCalendarPopup(True)
        self.end_dt.setMaximumWidth(220)

        days_row = QHBoxLayout()
        self.day_checkboxes = []
        for key in _DAY_KEYS:
            checkbox = QCheckBox(_t(key))
            checkbox.setChecked(True)
            days_row.addWidget(checkbox)
            self.day_checkboxes.append(checkbox)

        form.addRow(_t("promotion.name_label"), self.name_input)
        form.addRow(_t("promotion.type_label"), self.type_combo)
        form.addRow(_t("promotion.value_label"), self.value_input)
        form.addRow(_t("promotion.scope_label"), self.category_combo)
        form.addRow(_t("promotion.start_time_label"), self.start_dt)
        form.addRow(_t("promotion.end_time_label"), self.end_dt)
        form.addRow(_t("promotion.days_label"), days_row)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate_and_accept(self) -> None:
        """Validate form fields before accepting the dialog."""
        if not self.name_input.text().strip():
            QMessageBox.warning(self, _t("common.validation_error"), _t("promotion.name_required"))
            return

        if self.start_dt.dateTime() >= self.end_dt.dateTime():
            QMessageBox.warning(self, _t("common.validation_error"), _t("promotion.start_before_end"))
            return

        self.accept()

    def get_data(self):
        checked_indices = [str(i) for i, cb in enumerate(self.day_checkboxes) if cb.isChecked()]
        all_checked = len(checked_indices) == len(self.day_checkboxes)

        return {
            "name": self.name_input.text(),
            "type": self.type_combo.currentText(),
            "value": Decimal(str(self.value_input.value())),
            "start_time": self.start_dt.dateTime().toPyDateTime(),
            "end_time": self.end_dt.dateTime().toPyDateTime(),
            "days_of_week": None if all_checked else ",".join(checked_indices),
            "category_id": self.category_combo.currentData(),
        }
