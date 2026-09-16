from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.user_service import UserService
from cbpos.i18n import _t


class PermissionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("permission.title"))
        # 800x600 only showed 5 of the 10 permission groups (46 rows
        # total) before scrolling, with no visual hint there was more
        # below the fold -- reading as "permissions are missing" even
        # though every group was genuinely there (#298).
        self.resize(850, 780)
        self.setMinimumSize(650, 550)
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
        btn_save = QPushButton(_t("permission.save_changes"))
        btn_save.clicked.connect(self.save_changes)
        btn_close = QPushButton(_t("common.close"))
        btn_close.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def load_data(self):
        self.roles = UserService.get_all_roles()
        self.permissions = PermissionService.get_all_permissions()

        # Setup Columns: Permission | Role 1 | Role 2 | ...
        headers = [_t("permission.col_permission")] + [role.name for role in self.roles]
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

    @staticmethod
    def collect_role_permission_map(tree: QTreeWidget, roles: list) -> dict:
        """Build {role_id: [checked permission ids]} from the tree's current check states."""
        role_permission_map = {role.id: [] for role in roles}
        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                perm_item = group_item.child(j)
                perm_id = perm_item.data(0, Qt.ItemDataRole.UserRole)

                for k, role in enumerate(roles):
                    col_index = k + 1
                    if perm_item.checkState(col_index) == Qt.CheckState.Checked:
                        role_permission_map[role.id].append(perm_id)
        return role_permission_map

    def save_changes(self):
        try:
            role_permission_map = self.collect_role_permission_map(self.tree, self.roles)
            for role_id, permission_ids in role_permission_map.items():
                PermissionService.update_role_permissions(role_id, permission_ids)

            QMessageBox.information(self, _t("common.success"), _t("permission.save_success"))
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), _t("permission.save_failed", error=str(e)))
