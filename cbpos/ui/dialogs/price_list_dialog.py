"""Dialog for creating or editing a price list's name and validity dates."""

from datetime import datetime

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class PriceListDialog(QDialog):
    """Dialog for creating or editing a price list's name and validity dates."""

    def __init__(self, parent=None, price_list=None):
        """Build the form and pre-fill fields when editing an existing price list."""
        super().__init__(parent)
        self.price_list = price_list
        self.init_ui()
        self.retranslate_ui()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

        if price_list:
            self.name_input.setText(price_list.name)
            if price_list.start_date:
                self.start_date.setDate(
                    QDate(price_list.start_date.year, price_list.start_date.month, price_list.start_date.day)
                )
            if price_list.end_date:
                self.end_date.setDate(
                    QDate(price_list.end_date.year, price_list.end_date.month, price_list.end_date.day)
                )
            self.active_check.setChecked(bool(price_list.is_active))

    def init_ui(self):
        """Build the name and date-range form with Save/Cancel buttons."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        self.name_input = QLineEdit()
        self.start_date = QDateEdit()
        self.start_date.setDate(QDate.currentDate())
        self.start_date.setCalendarPopup(True)

        self.end_date = QDateEdit()
        self.end_date.setDate(QDate.currentDate().addYears(1))
        self.end_date.setCalendarPopup(True)

        self.active_check = QCheckBox()
        self.active_check.setChecked(True)

        self.lbl_name = QLabel()
        self.lbl_start = QLabel()
        self.lbl_end = QLabel()
        self.lbl_active = QLabel()

        form.addRow(self.lbl_name, self.name_input)
        form.addRow(self.lbl_start, self.start_date)
        form.addRow(self.lbl_end, self.end_date)
        form.addRow(self.lbl_active, self.active_check)

        layout.addLayout(form)

        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self.validate_and_accept,
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        title_key = "pricelist.dialog_edit_title" if self.price_list else "pricelist.dialog_title"
        self.setWindowTitle(_t(title_key))
        self.lbl_name.setText(_t("pricelist.form_name"))
        self.lbl_start.setText(_t("pricelist.form_start_date"))
        self.lbl_end.setText(_t("pricelist.form_end_date"))
        self.lbl_active.setText(_t("pricelist.form_active"))
        self.active_check.setText(_t("pricelist.form_active_hint"))
        self.btn_save.setText(_t("common.save"))
        self.btn_cancel.setText(_t("common.cancel"))

    def validate_and_accept(self) -> None:
        """Validate form fields before accepting the dialog."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                _t("common.validation_error"),
                _t("pricelist.name_required"),
            )
            return

        start = self.start_date.date()
        end = self.end_date.date()
        if start > end:
            QMessageBox.warning(
                self,
                _t("common.validation_error"),
                _t("pricelist.start_before_end"),
            )
            return

        self.accept()

    def get_data(self):
        """Return the entered (name, start, end, is_active)."""
        start = datetime.combine(self.start_date.date().toPyDate(), datetime.min.time())
        end = datetime.combine(self.end_date.date().toPyDate(), datetime.max.time())
        return self.name_input.text().strip(), start, end, self.active_check.isChecked()
