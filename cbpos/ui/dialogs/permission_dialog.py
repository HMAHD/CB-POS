from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
    QHeaderView,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.user_service import UserService


class PermissionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Permission Manager")
        self.resize(800, 600)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(False)
        layout.addWidget(self.tree)

        # Load Data
        self.load_data()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save Changes")
        btn_save.clicked.connect(self.save_changes)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def load_data(self):
        self.roles = UserService.get_all_roles()
        self.permissions = PermissionService.get_all_permissions()

        # Setup Columns: Permission | Role 1 | Role 2 | ...
        headers = ["Permission"] + [role.name for role in self.roles]
        self.tree.setHeaderLabels(headers)

        # Group permissions
        grouped_perms = {}
        for perm in self.permissions:
            group = perm.group or "Other"
            if group not in grouped_perms:
                grouped_perms[group] = []
            grouped_perms[group].append(perm)

        # Populate Tree
        for group_name, perms in grouped_perms.items():
            group_item = QTreeWidgetItem(self.tree)
            group_item.setText(0, group_name)
            group_item.setExpanded(True)
            # Make group item unselectable/gray?
            group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

            for perm in perms:
                perm_item = QTreeWidgetItem(group_item)
                perm_item.setText(0, perm.description or perm.code)
                perm_item.setData(0, Qt.ItemDataRole.UserRole, perm.id)

                for i, role in enumerate(self.roles):
                    col_index = i + 1
                    checkbox = Qt.CheckState.Unchecked
                    if perm in role.permissions:
                        checkbox = Qt.CheckState.Checked

                    perm_item.setCheckState(col_index, checkbox)

                    # Prevent disabling critical admin permissions
                    if role.name == "Admin" and perm.code in [
                        "admin.manage_users",
                        "admin.manage_roles",
                    ]:
                        perm_item.setFlags(perm_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                        perm_item.setCheckState(col_index, Qt.CheckState.Checked)  # Force Checked

        # Resize columns
        for i in range(len(headers)):
            self.tree.header().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

    def save_changes(self):
        try:
            # Iterate through all items
            root = self.tree.invisibleRootItem()
            for i in range(root.childCount()):
                group_item = root.child(i)
                for j in range(group_item.childCount()):
                    perm_item = group_item.child(j)
                    perm_id = perm_item.data(0, Qt.ItemDataRole.UserRole)

                    for k, role in enumerate(self.roles):
                        col_index = k + 1
                        is_checked = perm_item.checkState(col_index) == Qt.CheckState.Checked

                        # Update role permission
                        PermissionService.update_role_permission(role.id, perm_id, is_checked)

            QMessageBox.information(self, "Success", "Permissions updated successfully.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save permissions: {str(e)}")
