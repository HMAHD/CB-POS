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
from PyQt6.QtGui import QColor
from sqlalchemy import select
from cbpos.core.database import Database
from cbpos.core.models import Category


class CategoryDialog(QDialog):
    def __init__(self, category: Category = None, parent=None):
        super().__init__(parent)
        self.category = category
        self.setWindowTitle("Category Manager" if category else "New Category")
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

        self.name_input = QLineEdit()

        # Parent Category
        self.parent_combo = QComboBox()
        self.parent_combo.addItem("None", None)
        self.load_categories()

        # Color Picker
        color_layout = QHBoxLayout()
        self.lbl_color = QLabel()
        self.lbl_color.setFixedSize(30, 30)
        style = f"background-color: {self.selected_color}; border: 1px solid gray;"  # noqa: E702,E231
        self.lbl_color.setStyleSheet(style)

        btn_color = QPushButton("Pick Color")
        btn_color.clicked.connect(self.pick_color)

        color_layout.addWidget(self.lbl_color)
        color_layout.addWidget(btn_color)
        color_layout.addStretch()

        form.addRow("Name:", self.name_input)
        form.addRow("Parent Category:", self.parent_combo)
        form.addRow("Color:", color_layout)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_categories(self):
        db = Database()
        with db.get_session() as session:
            categories = session.scalars(select(Category)).all()
            for cat in categories:
                # Avoid self-parenting
                if self.category and cat.id == self.category.id:
                    continue
                self.parent_combo.addItem(cat.name, cat.id)

    def pick_color(self):
        color = QColorDialog.getColor(
            QColor(self.selected_color), self, "Select Category Color"
        )
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
            QMessageBox.warning(self, "Error", "Name is required")
            return

        parent_id = self.parent_combo.currentData()

        db = Database()
        with db.get_session() as session:
            try:
                if self.category:
                    cat = session.get(Category, self.category.id)
                    cat.name = name
                    cat.parent_id = parent_id
                    cat.color = self.selected_color
                else:
                    cat = Category(
                        name=name, parent_id=parent_id, color=self.selected_color
                    )
                    session.add(cat)

                session.commit()
                self.accept()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
