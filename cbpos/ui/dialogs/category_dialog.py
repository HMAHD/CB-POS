from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.models import Category
from cbpos.core.services.category_service import CategoryService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t
from cbpos.ui.styles.style_helpers import set_color_swatch
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class CategoryDialog(QDialog):
    """Dialog for creating or editing a category (name, parent category, and color)."""

    def __init__(self, category: Category = None, parent=None):
        """Initialize the dialog, pre-filling fields when editing an existing category."""
        super().__init__(parent)
        self.category = category
        self.setWindowTitle(_t("category_dialog.edit_title") if category else _t("category_dialog.new_title"))
        self.setMinimumWidth(400)

        self.selected_color = "#FFFFFF"
        if category:
            self.selected_color = category.color

        self.setup_ui()
        if category:
            self.load_data()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def setup_ui(self):
        """Build the name, parent category, and color picker form."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        self.name_input = QLineEdit()

        # Parent Category
        self.parent_combo = QComboBox()
        self.parent_combo.addItem(_t("category_dialog.none"), None)
        self.load_categories()

        # Color Picker
        color_layout = QHBoxLayout()
        self.lbl_color = QLabel()
        self.lbl_color.setFixedSize(30, 30)
        self.lbl_color.setAlignment(Qt.AlignmentFlag.AlignCenter)
        set_color_swatch(self.lbl_color, self.selected_color)

        btn_color = QPushButton(_t("category_dialog.pick_color"))
        btn_color.clicked.connect(self.pick_color)

        color_layout.addWidget(self.lbl_color)
        color_layout.addWidget(btn_color)
        color_layout.addStretch()

        form.addRow(_t("category_dialog.name"), self.name_input)
        form.addRow(_t("category_dialog.parent_category"), self.parent_combo)
        form.addRow(_t("category_dialog.color"), color_layout)

        from cbpos.core.services.warranty_service import WarrantyService

        if WarrantyService.is_enabled():
            self.warranty_combo = QComboBox()
            self.warranty_combo.addItem(_t("category_dialog.warranty_none"), None)
            for pol in WarrantyService.list_policies(include_inactive=False):
                self.warranty_combo.addItem(pol.get_display_name(), pol.id)
            form.addRow(_t("category_dialog.default_warranty"), self.warranty_combo)

        layout.addLayout(form)

        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self.save,
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)

    def load_categories(self):
        """Populate the parent category combo, excluding the category being edited."""
        categories = CategoryService.get_all()
        for cat in categories:
            # Avoid self-parenting
            if self.category and cat.id == self.category.id:
                continue
            self.parent_combo.addItem(cat.name, cat.id)

    def pick_color(self):
        """Open a color picker and update the selected color swatch."""
        color = QColorDialog.getColor(QColor(self.selected_color), self, _t("category_dialog.select_color"))
        if color.isValid():
            self.selected_color = color.name()
            set_color_swatch(self.lbl_color, self.selected_color)

    def load_data(self):
        """Populate the form fields from the category being edited."""
        self.name_input.setText(self.category.name)
        index = self.parent_combo.findData(self.category.parent_id)
        if index >= 0:
            self.parent_combo.setCurrentIndex(index)
        if hasattr(self, "warranty_combo") and getattr(self.category, "default_warranty_policy_id", None):
            assigned_id = self.category.default_warranty_policy_id
            w_idx = self.warranty_combo.findData(assigned_id)
            if w_idx < 0:
                from cbpos.core.services.warranty_service import WarrantyService

                pol = WarrantyService.get_policy(assigned_id)
                if pol:
                    self.warranty_combo.addItem(f"{pol.get_display_name()} (inactive)", pol.id)
                    w_idx = self.warranty_combo.findData(assigned_id)
            if w_idx >= 0:
                self.warranty_combo.setCurrentIndex(w_idx)

    def save(self):
        """Validate input and create or update the category via CategoryService."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, _t("common.error"), _t("category_dialog.name_required"))
            return

        parent_id = self.parent_combo.currentData()
        warranty_id = self.warranty_combo.currentData() if hasattr(self, "warranty_combo") else ...

        try:
            if self.category:
                update_kwargs = {
                    "name": name,
                    "color": self.selected_color,
                    "parent_id": parent_id,
                }
                if warranty_id is not ...:
                    update_kwargs["default_warranty_policy_id"] = warranty_id
                CategoryService.update(self.category.id, **update_kwargs)
            else:
                create_kwargs = {
                    "name": name,
                    "color": self.selected_color,
                    "parent_id": parent_id,
                }
                if warranty_id is not ... and warranty_id is not None:
                    create_kwargs["default_warranty_policy_id"] = warranty_id
                CategoryService.create(**create_kwargs)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
