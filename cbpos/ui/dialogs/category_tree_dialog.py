from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QInputDialog,
    QMessageBox,
    QColorDialog,
    QLabel,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QAction
from cbpos.core.services.category_service import CategoryService


class CategoryTreeDialog(QDialog):
    """
    Hierarchical Category Manager with Tree View.
    Supports drag & drop reparenting, color icons, and context menu.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Category Manager (Tree View)")
        self.setMinimumSize(600, 500)
        self.init_ui()
        self.load_categories()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Category Manager - Hierarchical View")
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Category Name", "Color"])
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.itemChanged.connect(self.on_item_dropped)
        layout.addWidget(self.tree)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_add_root = QPushButton("Add Root Category")
        btn_add_root.setProperty("class", "primary")
        btn_add_root.clicked.connect(self.add_root_category)
        btn_layout.addWidget(btn_add_root)

        btn_layout.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.load_categories)
        btn_layout.addWidget(btn_refresh)

        btn_close = QPushButton("Close")
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

        action_add_sub = QAction("Add Sub-category", self)
        action_add_sub.triggered.connect(lambda: self.add_subcategory(item))
        menu.addAction(action_add_sub)

        action_edit = QAction("Edit", self)
        action_edit.triggered.connect(lambda: self.edit_category(item))
        menu.addAction(action_edit)

        action_change_color = QAction("Change Color", self)
        action_change_color.triggered.connect(lambda: self.change_category_color(item))
        menu.addAction(action_change_color)

        menu.addSeparator()

        action_delete = QAction("Delete", self)
        action_delete.triggered.connect(lambda: self.delete_category(item))
        menu.addAction(action_delete)

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def add_root_category(self):
        """Add a new root category."""
        name, ok = QInputDialog.getText(self, "Add Root Category", "Category Name:")
        if ok and name:
            try:
                CategoryService.create(name=name)
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))
                return
            self.load_categories()

    def add_subcategory(self, parent_item: QTreeWidgetItem):
        """Add a subcategory under the selected category."""
        parent_id = parent_item.data(0, Qt.ItemDataRole.UserRole)

        name, ok = QInputDialog.getText(self, "Add Sub-category", "Category Name:")
        if ok and name:
            try:
                CategoryService.create(name=name, parent_id=parent_id)
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))
                return
            self.load_categories()

    def edit_category(self, item: QTreeWidgetItem):
        """Edit category name."""
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        current_name = item.text(0)

        name, ok = QInputDialog.getText(self, "Edit Category", "Category Name:", text=current_name)
        if ok and name:
            try:
                CategoryService.update(category_id, name=name)
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))
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
                QMessageBox.warning(self, "Error", str(e))
                return
            self.load_categories()

    def delete_category(self, item: QTreeWidgetItem):
        """Delete category."""
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        category_name = item.text(0)

        reply = QMessageBox.question(
            self,
            "Delete Category",
            "Are you sure you want to delete '{0}'?\nAll products in this category will become uncategorized.".format(
                category_name
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                CategoryService.delete(category_id)
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))
                return
            self.load_categories()

    def on_item_dropped(self, item: QTreeWidgetItem, column: int):
        """Handle drag & drop reparenting."""
        # Note: This is a simplified handler. Full implementation would need
        # to properly detect parent changes and update the database.
        # For now, we'll disable automatic updates and require manual confirmation.
        pass  # Implement if drag & drop persistence is needed
