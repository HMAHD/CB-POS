from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QDialogButtonBox,
    QHBoxLayout,
    QColorDialog,
    QLabel,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from cbpos.core.models import Category
from cbpos.core.services.category_service import CategoryService
from cbpos.i18n import _t


class CategoryDialog(QDialog):
    def __init__(self, category: Category = None, parent=None):
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

    def setup_ui(self):
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
        style = f"background-color: {self.selected_color}; border: 1px solid gray;"  # noqa: E702,E231
        self.lbl_color.setStyleSheet(style)

        btn_color = QPushButton(_t("category_dialog.pick_color"))
        btn_color.clicked.connect(self.pick_color)

        color_layout.addWidget(self.lbl_color)
        color_layout.addWidget(btn_color)
        color_layout.addStretch()

        form.addRow(_t("category_dialog.name"), self.name_input)
        form.addRow(_t("category_dialog.parent_category"), self.parent_combo)
        form.addRow(_t("category_dialog.color"), color_layout)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_categories(self):
        categories = CategoryService.get_all()
        for cat in categories:
            # Avoid self-parenting
            if self.category and cat.id == self.category.id:
                continue
            self.parent_combo.addItem(cat.name, cat.id)

    def pick_color(self):
        color = QColorDialog.getColor(QColor(self.selected_color), self, _t("category_dialog.select_color"))
        if color.isValid():
            self.selected_color = color.name()
            self.lbl_color.setStyleSheet(
                f"background-color: {self.selected_color}; border: 1px solid gray;"  # noqa: E702,E231
            )

    def load_data(self):
        self.name_input.setText(self.category.name)
        index = self.parent_combo.findData(self.category.parent_id)
        if index >= 0:
            self.parent_combo.setCurrentIndex(index)

    def save(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, _t("common.error"), _t("category_dialog.name_required"))
            return

        parent_id = self.parent_combo.currentData()

        try:
            if self.category:
                CategoryService.update(
                    self.category.id,
                    name=name,
                    color=self.selected_color,
                    parent_id=parent_id,
                )
            else:
                CategoryService.create(
                    name=name,
                    color=self.selected_color,
                    parent_id=parent_id,
                )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))
