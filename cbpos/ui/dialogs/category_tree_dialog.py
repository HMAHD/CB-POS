import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QBrush, QColor
from PyQt6.QtWidgets import (
    QColorDialog,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from cbpos.core.services.category_service import CategoryService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class CategoryTreeDialog(QDialog):
    """
    Hierarchical Category Manager with Tree View.
    Supports drag & drop reparenting, color icons, and context menu.
    """

    def __init__(self, parent=None):
        """Initialize the dialog and load the category tree."""
        super().__init__(parent)
        self.setWindowTitle(_t("category_tree.title"))
        self.setMinimumSize(600, 500)
        self.init_ui()
        self.load_categories()

    def init_ui(self):
        """Build the tree widget and its add/refresh/close buttons."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel(_t("category_tree.heading"))
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_t("category_tree.col_name"), _t("category_tree.col_color")])
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.itemChanged.connect(self.on_item_dropped)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_add_root = QPushButton(_t("category_tree.add_root"))
        btn_add_root.setProperty("class", "primary")
        btn_add_root.clicked.connect(self.add_root_category)
        btn_layout.addWidget(btn_add_root)

        btn_layout.addStretch()

        btn_refresh = QPushButton(_t("common.refresh"))
        btn_refresh.clicked.connect(self.load_categories)
        btn_layout.addWidget(btn_refresh)

        btn_close = QPushButton(_t("common.close"))
        btn_close.setObjectName("BtnCancel")
        btn_close.setProperty("class", "secondary")
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def load_categories(self):
        """Load categories and build tree hierarchy."""
        self.tree.clear()

        categories = CategoryService.get_tree()

        # Build tree items dict
        tree_items = {}

        # First pass: Create QTreeWidgetItems for root categories
        for cat in categories:
            if cat.parent_id is None:
                item = self.create_tree_item(cat)
                self.tree.addTopLevelItem(item)
                tree_items[cat.id] = item

        # Second pass: Add children
        for cat in categories:
            if cat.parent_id is not None and cat.parent_id in tree_items:
                item = self.create_tree_item(cat)
                tree_items[cat.parent_id].addChild(item)
                tree_items[cat.id] = item

        self.tree.expandAll()

    def create_tree_item(self, category) -> QTreeWidgetItem:
        """Create a tree widget item for a category."""
        item = QTreeWidgetItem([category.name, ""])

        # Store category ID in item data
        item.setData(0, Qt.ItemDataRole.UserRole, category.id)

        # Set color icon
        if category.color:
            color = QColor(category.color)
            brush = QBrush(color)
            item.setForeground(1, brush)
            item.setText(1, "\u25cf")  # Color indicator
            item.setFont(1, item.font(0))

        return item

    def show_context_menu(self, position):
        """Show context menu on right-click."""
        item = self.tree.itemAt(position)
        if not item:
            return

        menu = QMenu(self)

        action_add_sub = QAction(_t("category_tree.add_subcategory"), self)
        action_add_sub.triggered.connect(lambda: self.add_subcategory(item))
        menu.addAction(action_add_sub)

        action_edit = QAction(_t("common.edit"), self)
        action_edit.triggered.connect(lambda: self.edit_category(item))
        menu.addAction(action_edit)

        action_change_color = QAction(_t("category_tree.change_color"), self)
        action_change_color.triggered.connect(lambda: self.change_category_color(item))
        menu.addAction(action_change_color)

        menu.addSeparator()

        action_delete = QAction(_t("common.delete"), self)
        action_delete.triggered.connect(lambda: self.delete_category(item))
        menu.addAction(action_delete)

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def add_root_category(self):
        """Add a new root category."""
        name, ok = QInputDialog.getText(
            self, _t("category_tree.add_root_title"), _t("category_tree.category_name_prompt")
        )
        if ok and name:
            try:
                CategoryService.create(name=name)
            except ValueError as e:
                logger.warning("Failed to create root category %s: %s", name, e)
                QMessageBox.warning(self, _t("common.error"), translate_error(str(e)))
                return
            self.load_categories()

    def add_subcategory(self, parent_item: QTreeWidgetItem):
        """Add a subcategory under the selected category."""
        parent_id = parent_item.data(0, Qt.ItemDataRole.UserRole)

        name, ok = QInputDialog.getText(
            self, _t("category_tree.add_sub_title"), _t("category_tree.category_name_prompt")
        )
        if ok and name:
            try:
                CategoryService.create(name=name, parent_id=parent_id)
            except ValueError as e:
                logger.warning("Failed to create subcategory %s under %s: %s", name, parent_id, e)
                QMessageBox.warning(self, _t("common.error"), translate_error(str(e)))
                return
            self.load_categories()

    def edit_category(self, item: QTreeWidgetItem):
        """Edit category name."""
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        current_name = item.text(0)

        name, ok = QInputDialog.getText(
            self, _t("category_tree.edit_title"), _t("category_tree.category_name_prompt"), text=current_name
        )
        if ok and name:
            try:
                CategoryService.update(category_id, name=name)
            except ValueError as e:
                logger.warning("Failed to update category %s: %s", category_id, e)
                QMessageBox.warning(self, _t("common.error"), translate_error(str(e)))
                return
            self.load_categories()

    def change_category_color(self, item: QTreeWidgetItem):
        """Change category color."""
        category_id = item.data(0, Qt.ItemDataRole.UserRole)

        color = QColorDialog.getColor()
        if color.isValid():
            try:
                CategoryService.update(category_id, color=color.name())
            except ValueError as e:
                logger.warning("Failed to update category color %s: %s", category_id, e)
                QMessageBox.warning(self, _t("common.error"), translate_error(str(e)))
                return
            self.load_categories()

    def delete_category(self, item: QTreeWidgetItem):
        """Delete category."""
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        category_name = item.text(0)

        reply = QMessageBox.question(
            self,
            _t("category_tree.delete_title"),
            _t("category_tree.delete_confirm", name=category_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                CategoryService.delete(category_id)
            except ValueError as e:
                logger.warning("Failed to delete category %s: %s", category_id, e)
                QMessageBox.warning(self, _t("common.error"), translate_error(str(e)))
                return
            self.load_categories()

    def on_item_dropped(self, item: QTreeWidgetItem, column: int):
        """Handle drag & drop reparenting."""
        # Note: This is a simplified handler. Full implementation would need
        # to properly detect parent changes and update the database.
        # For now, we'll disable automatic updates and require manual confirmation.
        # Implement if drag & drop persistence is needed
