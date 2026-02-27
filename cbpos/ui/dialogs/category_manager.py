import logging

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QLineEdit,
    QComboBox,
    QPushButton,
    QLabel,
    QColorDialog,
    QMessageBox,
    QFormLayout,
    QFrame,
    QInputDialog,
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
    """Full category manager with tree view, CRUD, and subcategory support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Category Manager")
        self.setMinimumSize(500, 450)
        self.resize(560, 520)
        self.selected_color = "#FFFFFF"
        self._setup_ui()
        self._load_tree()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- Toolbar ---
        toolbar = QHBoxLayout()
        self.btn_new = QPushButton("+ New Category")
        self.btn_new.clicked.connect(self._add_category)

        self.btn_sub = QPushButton("+ Subcategory")
        self.btn_sub.setEnabled(False)
        self.btn_sub.clicked.connect(self._add_subcategory)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setProperty("class", "danger")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete_category)

        toolbar.addWidget(self.btn_new)
        toolbar.addWidget(self.btn_sub)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_delete)
        layout.addLayout(toolbar)

        # --- Tree ---
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Category", "Products"])
        self.tree.setColumnWidth(0, 350)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self.tree, 1)

        # --- Edit Panel ---
        self.edit_frame = QFrame()
        self.edit_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.edit_frame.setVisible(False)
        edit_layout = QVBoxLayout(self.edit_frame)
        edit_layout.setContentsMargins(10, 10, 10, 10)

        form = QFormLayout()
        form.setSpacing(8)

        self.edit_name = QLineEdit()
        form.addRow("Name:", self.edit_name)

        self.edit_parent = QComboBox()
        form.addRow("Parent:", self.edit_parent)

        # Color row
        color_layout = QHBoxLayout()
        self.lbl_color = QLabel()
        self.lbl_color.setFixedSize(30, 30)
        self.lbl_color.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid gray; border-radius: 2px;"
        )
        self.btn_pick_color = QPushButton("Pick Color")
        self.btn_pick_color.clicked.connect(self._pick_color)
        color_layout.addWidget(self.lbl_color)
        color_layout.addWidget(self.btn_pick_color)
        color_layout.addStretch()
        form.addRow("Color:", color_layout)

        edit_layout.addLayout(form)

        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setProperty("class", "primary")
        self.btn_save.clicked.connect(self._save_changes)
        edit_layout.addWidget(self.btn_save)

        layout.addWidget(self.edit_frame)

    # ── Tree loading ──────────────────────────────────────────────

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

    def _make_tree_item(self, cat: Category) -> QTreeWidgetItem:
        product_count = len(cat.products) if cat.products else 0
        item = QTreeWidgetItem([cat.name, str(product_count)])
        item.setData(0, CATEGORY_ID_ROLE, cat.id)
        item.setIcon(0, _color_icon(cat.color or "#FFFFFF"))
        return item

    # ── Selection ─────────────────────────────────────────────────

    def _on_selection_changed(self, current: QTreeWidgetItem, _prev: QTreeWidgetItem) -> None:
        has_selection = current is not None
        self.btn_sub.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)
        self.edit_frame.setVisible(has_selection)

        if not has_selection:
            return

        cat_id = current.data(0, CATEGORY_ID_ROLE)
        db = Database()
        with db.get_session() as session:
            cat = session.get(Category, cat_id)
            if not cat:
                return

            self.edit_name.setText(cat.name)
            self.selected_color = cat.color or "#FFFFFF"
            self.lbl_color.setStyleSheet(
                f"background-color: {self.selected_color}; border: 1px solid gray; border-radius: 2px;"
            )

            # Populate parent combo (exclude self and own children)
            self.edit_parent.clear()
            self.edit_parent.addItem("None (Top Level)", None)

            all_cats = session.execute(
                select(Category).order_by(Category.name)
            ).scalars().all()

            excluded_ids = self._get_descendant_ids(session, cat_id)
            excluded_ids.add(cat_id)

            for c in all_cats:
                if c.id not in excluded_ids:
                    self.edit_parent.addItem(c.name, c.id)

            idx = self.edit_parent.findData(cat.parent_id)
            if idx >= 0:
                self.edit_parent.setCurrentIndex(idx)

    def _get_descendant_ids(self, session, cat_id: int) -> set:
        """Get all descendant category IDs to prevent circular parenting."""
        children = session.execute(
            select(Category.id).where(Category.parent_id == cat_id)
        ).scalars().all()
        ids = set(children)
        for child_id in children:
            ids |= self._get_descendant_ids(session, child_id)
        return ids

    # ── Actions ───────────────────────────────────────────────────

    def _add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "New Category", "Category name:")
        if not ok or not name.strip():
            return

        color = QColorDialog.getColor(QColor("#00BCEB"), self, "Category Color")
        if not color.isValid():
            return

        db = Database()
        with db.get_session() as session:
            try:
                cat = Category(name=name.strip(), color=color.name(), parent_id=None)
                session.add(cat)
                session.commit()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
                return

        self._load_tree()

    def _add_subcategory(self) -> None:
        current = self.tree.currentItem()
        if not current:
            return

        parent_id = current.data(0, CATEGORY_ID_ROLE)
        parent_name = current.text(0)

        name, ok = QInputDialog.getText(
            self, "New Subcategory", f"Subcategory under '{parent_name}':"
        )
        if not ok or not name.strip():
            return

        color = QColorDialog.getColor(QColor("#00BCEB"), self, "Subcategory Color")
        if not color.isValid():
            return

        db = Database()
        with db.get_session() as session:
            try:
                cat = Category(name=name.strip(), color=color.name(), parent_id=parent_id)
                session.add(cat)
                session.commit()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
                return

        self._load_tree()

    def _delete_category(self) -> None:
        current = self.tree.currentItem()
        if not current:
            return

        cat_id = current.data(0, CATEGORY_ID_ROLE)
        cat_name = current.text(0)

        db = Database()
        with db.get_session() as session:
            # Collect this category + all descendant IDs
            all_ids = {cat_id} | self._get_descendant_ids(session, cat_id)

            # Guard: check for products in this category or subcategories
            product_count = session.execute(
                select(func.count(Product.id)).where(
                    Product.category_id.in_(all_ids)
                )
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

            # Confirm
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Delete category '{cat_name}' and all its subcategories?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            try:
                # Delete descendants first (deepest first), then self
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

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self.selected_color), self, "Select Category Color"
        )
        if color.isValid():
            self.selected_color = color.name()
            self.lbl_color.setStyleSheet(
                f"background-color: {self.selected_color}; border: 1px solid gray; border-radius: 2px;"
            )

    def _save_changes(self) -> None:
        current = self.tree.currentItem()
        if not current:
            return

        cat_id = current.data(0, CATEGORY_ID_ROLE)
        name = self.edit_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Name is required.")
            return

        parent_id = self.edit_parent.currentData()

        db = Database()
        with db.get_session() as session:
            try:
                cat = session.get(Category, cat_id)
                if not cat:
                    return
                cat.name = name
                cat.parent_id = parent_id
                cat.color = self.selected_color
                session.commit()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
                return

        self._load_tree()
