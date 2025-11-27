from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QCheckBox,
    QWidget,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.user_service import UserService
from cbpos.core.services.permission_service import PermissionService


class PermissionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Role Permissions")
        self.resize(800, 600)
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Table
        self.table = QTableWidget()
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save Changes")
        btn_save.clicked.connect(self.save_changes)
        btn_save.setStyleSheet(
            "background-color: #0074D9; color: white; padding: 10px;"
        )

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def load_data(self):
        self.roles = UserService.get_all_roles()
        self.permissions = PermissionService.get_all_permissions()

        # Setup Columns (Roles)
        self.table.setColumnCount(len(self.roles) + 1)
        headers = ["Permission"] + [role.name for role in self.roles]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        # Setup Rows (Permissions)
        self.table.setRowCount(len(self.permissions))

        for row, perm in enumerate(self.permissions):
            # Permission Name
            item = QTableWidgetItem(perm.description or perm.code)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, item)

            # Checkboxes for each Role
            for col, role in enumerate(self.roles):
                # Check if role has this permission
                has_perm = any(p.id == perm.id for p in role.permissions)

                chk_widget = QWidget()
                chk_layout = QHBoxLayout(chk_widget)
                chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                chk_layout.setContentsMargins(0, 0, 0, 0)

                checkbox = QCheckBox()
                checkbox.setChecked(has_perm)
                # Store data for retrieval
                checkbox.setProperty("role_id", role.id)
                checkbox.setProperty("perm_id", perm.id)

                chk_layout.addWidget(checkbox)
                self.table.setCellWidget(row, col + 1, chk_widget)

    def save_changes(self):
        # Collect data
        role_updates = {role.id: [] for role in self.roles}

        for row in range(self.table.rowCount()):
            for col in range(len(self.roles)):
                widget = self.table.cellWidget(row, col + 1)
                if widget:
                    checkbox = widget.findChild(QCheckBox)
                    if checkbox and checkbox.isChecked():
                        role_id = checkbox.property("role_id")
                        perm_id = checkbox.property("perm_id")
                        role_updates[role_id].append(perm_id)

        # Save
        success = True
        for role_id, perm_ids in role_updates.items():
            if not PermissionService.update_role_permissions(role_id, perm_ids):
                success = False

        if success:
            QMessageBox.information(
                self, "Success", "Permissions updated successfully."
            )
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to update some permissions.")
