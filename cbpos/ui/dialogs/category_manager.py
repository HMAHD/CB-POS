"""
Dialog for managing product categories (CRUD) with tree view and inline editing.
"""

import logging
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QComboBox,
    QPushButton,
    QLineEdit,
    QColorDialog,
    QMessageBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap, QIcon
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from cbpos.core.database import Database
from cbpos.core.models import Category, Product

logger = logging.getLogger(__name__)

CATEGORY_ID_ROLE = Qt.ItemDataRole.UserRole


def _color_icon(hex_color: str, size: int = 16) -> QIcon:
    """Create a small colored square icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(hex_color))
    return QIcon(pixmap)


class CategoryManagerDialog(QDialog):
    """Category manager with tree view, inline form, and subcategory support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Category Manager")
        self.setMinimumSize(640, 500)
        self.resize(700, 540)
        self.setObjectName("CategoryManagerDialog")
        self.selected_color = "#00BCEB"
        self._editing_id = None
        self._setup_ui()
        self._load_tree()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Left: Tree ──
        left = QVBoxLayout()
        left.setSpacing(8)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Category", "Products"])
        self.tree.setColumnWidth(0, 280)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.currentItemChanged.connect(self._on_selection_changed)
        left.addWidget(self.tree)

        layout.addLayout(left, 2)

        # ── Right: Form + Actions ──
        right = QVBoxLayout()
        right.setSpacing(10)

        # Form
        form_group = QGroupBox("Category Details")
        form_layout = QFormLayout(form_group)
        form_layout.setSpacing(10)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Category name")
        form_layout.addRow("Name:", self.txt_name)

        self.combo_parent = QComboBox()
        form_layout.addRow("Parent:", self.combo_parent)

        # Color picker row
        color_row = QHBoxLayout()
        self.lbl_color = QLabel()
        self.lbl_color.setFixedSize(32, 32)
        self._update_color_preview()
        self.btn_pick_color = QPushButton("Pick Color")
        self.btn_pick_color.clicked.connect(self._pick_color)
        color_row.addWidget(self.lbl_color)
        color_row.addWidget(self.btn_pick_color)
        color_row.addStretch()
        form_layout.addRow("Color:", color_row)

        right.addWidget(form_group)

        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_save = QPushButton("Save New")
        self.btn_save.setProperty("class", "primary")
        self.btn_save.clicked.connect(self._save_category)
        btn_layout.addWidget(self.btn_save)

        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.setProperty("class", "danger")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete_category)
        btn_layout.addWidget(self.btn_delete)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        btn_layout.addWidget(sep)

        self.btn_clear = QPushButton("Clear / New")
        self.btn_clear.clicked.connect(self._clear_form)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        right.addLayout(btn_layout)

        layout.addLayout(right, 1)

    # ── Tree loading ──

    def _load_tree(self) -> None:
        """Reload the full category tree from DB."""
        self.tree.clear()
        db = Database()
        with db.get_session() as session:
            categories = (
                session.execute(
                    select(Category)
                    .options(
                        joinedload(Category.subcategories),
                        joinedload(Category.products),
                    )
                    .where(Category.parent_id.is_(None))
                    .order_by(Category.name)
                )
                .unique()
                .scalars()
                .all()
            )

            for cat in categories:
                item = self._make_tree_item(cat)
                self.tree.addTopLevelItem(item)
                for sub in sorted(cat.subcategories, key=lambda c: c.name):
                    child = self._make_tree_item(sub)
                    item.addChild(child)

        self.tree.expandAll()
        self._populate_parent_combo()

    def _make_tree_item(self, cat: Category) -> QTreeWidgetItem:
        product_count = len(cat.products) if cat.products else 0
        item = QTreeWidgetItem([cat.name, str(product_count)])
        item.setData(0, CATEGORY_ID_ROLE, cat.id)
        item.setIcon(0, _color_icon(cat.color or "#FFFFFF"))
        return item

    def _populate_parent_combo(self, exclude_id: int = None) -> None:
        """Populate parent combo with all categories, excluding self and descendants."""
        self.combo_parent.clear()
        self.combo_parent.addItem("None (Top Level)", None)

        db = Database()
        with db.get_session() as session:
            all_cats = session.execute(select(Category).order_by(Category.name)).scalars().all()

            excluded_ids = set()
            if exclude_id:
                excluded_ids = {exclude_id} | self._get_descendant_ids(session, exclude_id)

            for c in all_cats:
                if c.id not in excluded_ids:
                    self.combo_parent.addItem(_color_icon(c.color or "#FFFFFF"), c.name, c.id)

    # ── Selection ──

    def _on_selection_changed(self, current: QTreeWidgetItem, _prev: QTreeWidgetItem) -> None:
        has_selection = current is not None
        self.btn_delete.setEnabled(has_selection)

        if not has_selection:
            self._editing_id = None
            return

        cat_id = current.data(0, CATEGORY_ID_ROLE)
        self._editing_id = cat_id

        db = Database()
        with db.get_session() as session:
            cat = session.get(Category, cat_id)
            if not cat:
                return

            self.txt_name.setText(cat.name)
            self.selected_color = cat.color or "#00BCEB"
            self._update_color_preview()

            # Rebuild parent combo excluding self + descendants
            self._populate_parent_combo(exclude_id=cat_id)
            idx = self.combo_parent.findData(cat.parent_id)
            if idx >= 0:
                self.combo_parent.setCurrentIndex(idx)

        self.btn_save.setText("Update")

    def _get_descendant_ids(self, session, cat_id: int) -> set:
        """Get all descendant category IDs to prevent circular parenting."""
        children = session.execute(select(Category.id).where(Category.parent_id == cat_id)).scalars().all()
        ids = set(children)
        for child_id in children:
            ids |= self._get_descendant_ids(session, child_id)
        return ids

    # ── Actions ──

    def _save_category(self) -> None:
        """Add or update a category based on current editing state."""
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Category name is required.")
            self.txt_name.setFocus()
            return

        parent_id = self.combo_parent.currentData()

        db = Database()
        with db.get_session() as session:
            try:
                if self._editing_id:
                    # Update existing
                    cat = session.get(Category, self._editing_id)
                    if not cat:
                        return
                    cat.name = name
                    cat.parent_id = parent_id
                    cat.color = self.selected_color
                else:
                    # Create new
                    cat = Category(
                        name=name,
                        color=self.selected_color,
                        parent_id=parent_id,
                    )
                    session.add(cat)
                session.commit()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
                return

        self._load_tree()
        self._clear_form()

    def _delete_category(self) -> None:
        current = self.tree.currentItem()
        if not current:
            return

        cat_id = current.data(0, CATEGORY_ID_ROLE)
        cat_name = current.text(0)

        db = Database()
        with db.get_session() as session:
            all_ids = {cat_id} | self._get_descendant_ids(session, cat_id)

            product_count = session.execute(
                select(func.count(Product.id)).where(Product.category_id.in_(all_ids))
            ).scalar()

            if product_count > 0:
                QMessageBox.warning(
                    self,
                    "Cannot Delete",
                    f"Cannot delete '{cat_name}': {product_count} product(s) "
                    f"use this category or its subcategories.\n\n"
                    f"Reassign the products first.",
                )
                return

            sub_count = len(all_ids) - 1
            msg = f"Delete category '{cat_name}'?"
            if sub_count > 0:
                msg += f"\n\nThis will also delete {sub_count} subcategory(ies)."

            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            try:
                for cid in sorted(all_ids, reverse=True):
                    cat = session.get(Category, cid)
                    if cat:
                        session.delete(cat)
                session.commit()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
                return

        self._load_tree()
        self._clear_form()

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.selected_color), self, "Select Category Color")
        if color.isValid():
            self.selected_color = color.name()
            self._update_color_preview()

    def _update_color_preview(self) -> None:
        """Update the color swatch label."""
        self.lbl_color.setStyleSheet(
            f"background-color: {self.selected_color}; " f"border: 1px solid #3E3E42; border-radius: 4px;"
        )

    def _clear_form(self) -> None:
        """Clear form and reset to 'add new' mode."""
        self._editing_id = None
        self.txt_name.clear()
        self.selected_color = "#00BCEB"
        self._update_color_preview()
        self.btn_save.setText("Save New")
        self.btn_delete.setEnabled(False)
        self.tree.clearSelection()
        self._populate_parent_combo()
        self.txt_name.setFocus()
