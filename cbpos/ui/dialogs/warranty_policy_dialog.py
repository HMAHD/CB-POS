"""Dialog for creating or editing a warranty policy (#821)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.models import WarrantyPolicy
from cbpos.core.services.warranty_service import WarrantyService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class WarrantyPolicyDialog(QDialog):
    """Dialog for creating or editing a warranty policy."""

    def __init__(self, parent=None, policy: WarrantyPolicy | None = None):
        super().__init__(parent)
        self.policy = policy
        self.setWindowTitle(_t("warranty.policy.title_edit") if policy else _t("warranty.policy.title_add"))
        self.setMinimumWidth(560)
        self.resize(580, 520)

        self.init_ui()
        if policy:
            self.load_policy_data(policy)
        install_wheel_guard(self)

    def init_ui(self) -> None:
        """Initialize form inputs, tab widget, and action buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.tabs = QTabWidget()

        # Tab 1: Basic Details
        tab_basic = QWidget()
        form_basic = QFormLayout(tab_basic)
        form_basic.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_basic.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_basic.setContentsMargins(12, 12, 12, 12)
        form_basic.setSpacing(10)

        self.name_en_input = QLineEdit()
        self.name_en_input.setPlaceholderText(_t("warranty.policy.name_en_placeholder"))
        form_basic.addRow(_t("warranty.policy.name_en"), self.name_en_input)

        self.name_si_input = QLineEdit()
        self.name_si_input.setPlaceholderText(_t("warranty.policy.name_si_placeholder"))
        form_basic.addRow(_t("warranty.policy.name_si"), self.name_si_input)

        self.name_ta_input = QLineEdit()
        self.name_ta_input.setPlaceholderText(_t("warranty.policy.name_ta_placeholder"))
        form_basic.addRow(_t("warranty.policy.name_ta"), self.name_ta_input)

        self.type_combo = QComboBox()
        self.type_combo.addItem(_t("warranty.types.shop"), "SHOP")
        self.type_combo.addItem(_t("warranty.types.manufacturer"), "MANUFACTURER")
        self.type_combo.addItem(_t("warranty.types.extended"), "EXTENDED")
        form_basic.addRow(_t("warranty.policy.type"), self.type_combo)

        duration_layout = QHBoxLayout()
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 999)
        self.duration_spin.setValue(1)
        self.duration_spin.setFixedWidth(100)

        self.unit_combo = QComboBox()
        self.unit_combo.addItem(_t("warranty.units.days"), "DAYS")
        self.unit_combo.addItem(_t("warranty.units.months"), "MONTHS")
        self.unit_combo.addItem(_t("warranty.units.years"), "YEARS")
        self.unit_combo.setCurrentIndex(1)  # Default: MONTHS

        duration_layout.addWidget(self.duration_spin)
        duration_layout.addWidget(self.unit_combo)
        duration_layout.addStretch()
        form_basic.addRow(_t("warranty.policy.duration"), duration_layout)

        self.remedy_combo = QComboBox()
        self.remedy_combo.addItem(_t("warranty.remedies.repair_or_replace"), "REPAIR_OR_REPLACE")
        self.remedy_combo.addItem(_t("warranty.remedies.repair_only"), "REPAIR_ONLY")
        self.remedy_combo.addItem(_t("warranty.remedies.replace_only"), "REPLACE_ONLY")
        self.remedy_combo.addItem(_t("warranty.remedies.refund"), "REFUND")
        form_basic.addRow(_t("warranty.policy.remedy"), self.remedy_combo)

        self.provider_input = QLineEdit()
        self.provider_input.setPlaceholderText(_t("warranty.policy.provider_placeholder"))
        form_basic.addRow(_t("warranty.policy.provider"), self.provider_input)

        self.supplier_cover_spin = QSpinBox()
        self.supplier_cover_spin.setRange(0, 120)
        self.supplier_cover_spin.setValue(0)
        self.supplier_cover_spin.setFixedWidth(100)
        form_basic.addRow(_t("warranty.policy.supplier_cover"), self.supplier_cover_spin)

        self.active_check = QCheckBox(_t("warranty.policy.active"))
        self.active_check.setChecked(True)
        form_basic.addRow("", self.active_check)

        self.tabs.addTab(tab_basic, _t("warranty.policy.tab_basic"))

        # Tab 2: Terms & Exclusions
        tab_terms = QWidget()
        form_terms = QFormLayout(tab_terms)
        form_terms.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_terms.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_terms.setContentsMargins(12, 12, 12, 12)
        form_terms.setSpacing(10)

        self.terms_en_edit = QTextEdit()
        self.terms_en_edit.setMaximumHeight(70)
        form_terms.addRow(_t("warranty.policy.terms_en"), self.terms_en_edit)

        self.terms_si_edit = QTextEdit()
        self.terms_si_edit.setMaximumHeight(70)
        form_terms.addRow(_t("warranty.policy.terms_si"), self.terms_si_edit)

        self.terms_ta_edit = QTextEdit()
        self.terms_ta_edit.setMaximumHeight(70)
        form_terms.addRow(_t("warranty.policy.terms_ta"), self.terms_ta_edit)

        self.excl_en_edit = QTextEdit()
        self.excl_en_edit.setMaximumHeight(70)
        form_terms.addRow(_t("warranty.policy.exclusions_en"), self.excl_en_edit)

        self.excl_si_edit = QTextEdit()
        self.excl_si_edit.setMaximumHeight(70)
        form_terms.addRow(_t("warranty.policy.exclusions_si"), self.excl_si_edit)

        self.excl_ta_edit = QTextEdit()
        self.excl_ta_edit.setMaximumHeight(70)
        form_terms.addRow(_t("warranty.policy.exclusions_ta"), self.excl_ta_edit)

        self.tabs.addTab(tab_terms, _t("warranty.policy.tab_terms"))
        layout.addWidget(self.tabs)

        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self.save,
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)

    def load_policy_data(self, policy: WarrantyPolicy) -> None:
        """Populate inputs from an existing WarrantyPolicy instance."""
        self.name_en_input.setText(policy.name)
        self.name_si_input.setText(policy.name_si or "")
        self.name_ta_input.setText(policy.name_ta or "")

        idx = self.type_combo.findData(policy.warranty_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)

        self.duration_spin.setValue(policy.duration)

        idx = self.unit_combo.findData(policy.duration_unit)
        if idx >= 0:
            self.unit_combo.setCurrentIndex(idx)

        idx = self.remedy_combo.findData(policy.remedy)
        if idx >= 0:
            self.remedy_combo.setCurrentIndex(idx)

        self.provider_input.setText(policy.provider_name or "")
        self.supplier_cover_spin.setValue(policy.supplier_cover_months)
        self.active_check.setChecked(bool(policy.is_active))

        self.terms_en_edit.setPlainText(policy.terms_text or "")
        self.terms_si_edit.setPlainText(policy.terms_text_si or "")
        self.terms_ta_edit.setPlainText(policy.terms_text_ta or "")

        self.excl_en_edit.setPlainText(policy.exclusions_text or "")
        self.excl_si_edit.setPlainText(policy.exclusions_text_si or "")
        self.excl_ta_edit.setPlainText(policy.exclusions_text_ta or "")

    def save(self) -> None:
        """Validate input and create or update warranty policy."""
        name_en = self.name_en_input.text().strip()
        if not name_en:
            QMessageBox.warning(self, _t("common.validation_error"), _t("warranty.policy.name_required"))
            self.tabs.setCurrentIndex(0)
            self.name_en_input.setFocus()
            return

        duration = self.duration_spin.value()
        if duration <= 0:
            QMessageBox.warning(self, _t("common.validation_error"), _t("warranty.policy.duration_required"))
            self.tabs.setCurrentIndex(0)
            self.duration_spin.setFocus()
            return

        terms_en = self.terms_en_edit.toPlainText().strip()
        terms_si = self.terms_si_edit.toPlainText().strip()
        terms_ta = self.terms_ta_edit.toPlainText().strip()
        if (terms_si or terms_ta) and not terms_en:
            QMessageBox.warning(
                self, _t("common.validation_error"), _t("warranty.policy.terms_translation_requires_en")
            )
            self.tabs.setCurrentIndex(1)
            self.terms_en_edit.setFocus()
            return

        excl_en = self.excl_en_edit.toPlainText().strip()
        excl_si = self.excl_si_edit.toPlainText().strip()
        excl_ta = self.excl_ta_edit.toPlainText().strip()
        if (excl_si or excl_ta) and not excl_en:
            QMessageBox.warning(
                self, _t("common.validation_error"), _t("warranty.policy.exclusions_translation_requires_en")
            )
            self.tabs.setCurrentIndex(1)
            self.excl_en_edit.setFocus()
            return

        payload = {
            "name": name_en,
            "name_si": self.name_si_input.text().strip() or None,
            "name_ta": self.name_ta_input.text().strip() or None,
            "warranty_type": self.type_combo.currentData(),
            "duration": duration,
            "duration_unit": self.unit_combo.currentData(),
            "remedy": self.remedy_combo.currentData(),
            "provider_name": self.provider_input.text().strip() or None,
            "supplier_cover_months": self.supplier_cover_spin.value(),
            "is_active": self.active_check.isChecked(),
            "terms_text": terms_en or None,
            "terms_text_si": terms_si or None,
            "terms_text_ta": terms_ta or None,
            "exclusions_text": excl_en or None,
            "exclusions_text_si": excl_si or None,
            "exclusions_text_ta": excl_ta or None,
        }

        try:
            if self.policy:
                WarrantyService.update_policy(self.policy.id, payload)
            else:
                WarrantyService.create_policy(payload)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
