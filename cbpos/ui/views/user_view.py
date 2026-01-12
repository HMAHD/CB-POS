from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QDialog,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QMessageBox,
    QTabWidget,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.user_service import UserService
from cbpos.ui.dialogs.permission_dialog import PermissionDialog
from cbpos.ui.resources.icons import Icons


class UserDialog(QDialog):
    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("Add User" if not user else "Edit User")
        self.setFixedWidth(400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Username
        layout.addWidget(QLabel("Username:"))
        self.txt_username = QLineEdit()
        if self.user:
            self.txt_username.setText(self.user.username)
        layout.addWidget(self.txt_username)

        # PIN
        layout.addWidget(QLabel("PIN (Leave empty to keep unchanged):" if self.user else "PIN:"))
        self.txt_pin = QLineEdit()
        self.txt_pin.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.txt_pin)

        # Role
        layout.addWidget(QLabel("Role:"))
        self.cmb_role = QComboBox()
        self.roles = UserService.get_all_roles()
        for role in self.roles:
            self.cmb_role.addItem(role.name, role.id)

        if self.user and self.user.role:
            index = self.cmb_role.findData(self.user.role_id)
            if index >= 0:
                self.cmb_role.setCurrentIndex(index)
        layout.addWidget(self.cmb_role)

        # Active
        self.chk_active = QCheckBox("Active")
        self.chk_active.setChecked(True)
        if self.user:
            self.chk_active.setChecked(self.user.is_active)
        layout.addWidget(self.chk_active)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def save(self):
        username = self.txt_username.text().strip()
        pin = self.txt_pin.text().strip()
        role_id = self.cmb_role.currentData()
        is_active = self.chk_active.isChecked()

        if not username:
            QMessageBox.warning(self, "Error", "Username is required.")
            return

        if not self.user and not pin:
            QMessageBox.warning(self, "Error", "PIN is required for new users.")
            return

        if pin and (len(pin) < 4 or len(pin) > 6 or not pin.isdigit()):
            QMessageBox.warning(self, "Error", "PIN must be 4-6 digits.")
            return

        try:
            if self.user:
                UserService.update_user(self.user.id, username, pin if pin else None, role_id, is_active)
            else:
                UserService.create_user(username, pin, role_id)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save user: {str(e)}")


class UserView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Users
        self.user_tab = QWidget()
        self.init_user_tab()
        self.tabs.addTab(self.user_tab, "Users")

        # Tab 2: Activity Log
        self.log_tab = QWidget()
        self.init_log_tab()
        self.tabs.addTab(self.log_tab, "Activity Log")

        # Load data
        self.load_users()
        self.load_logs()

        # Refresh on tab change
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def init_user_tab(self):
        layout = QVBoxLayout(self.user_tab)

        # Toolbar
        toolbar = QHBoxLayout()

        btn_add = QPushButton("Add User")
        btn_add.setIcon(Icons.get("fa5s.plus"))
        btn_add.clicked.connect(self.add_user)

        btn_perms = QPushButton("Manage Permissions")
        btn_perms.setIcon(Icons.get("fa5s.lock"))
        btn_perms.clicked.connect(self.manage_permissions)

        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_perms)
        toolbar.addStretch()

        layout.addLayout(toolbar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Username", "Role", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_user)

        layout.addWidget(self.table)

    def init_log_tab(self):
        layout = QVBoxLayout(self.log_tab)

        self.log_table = QTableWidget()
        self.log_table.setColumnCount(5)
        self.log_table.setHorizontalHeaderLabels(["Time", "User", "Event", "Terminal", "Details"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout.addWidget(self.log_table)

    def load_users(self):
        self.users = UserService.get_all_users()
        self.table.setRowCount(len(self.users))

        for row, user in enumerate(self.users):
            self.table.setItem(row, 0, QTableWidgetItem(str(user.id)))
            self.table.setItem(row, 1, QTableWidgetItem(user.username))
            self.table.setItem(row, 2, QTableWidgetItem(user.role.name if user.role else "None"))

            status = "Active" if user.is_active else "Inactive"
            item_status = QTableWidgetItem(status)
            if not user.is_active:
                item_status.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 3, item_status)

    def load_logs(self):
        logs = UserService.get_recent_activity()
        self.log_table.setRowCount(len(logs))

        for row, log in enumerate(logs):
            self.log_table.setItem(row, 0, QTableWidgetItem(str(log.timestamp)))
            self.log_table.setItem(row, 1, QTableWidgetItem(log.user.username if log.user else "Unknown"))
            self.log_table.setItem(row, 2, QTableWidgetItem(log.event_type))
            self.log_table.setItem(row, 3, QTableWidgetItem(log.terminal_id or "-"))
            self.log_table.setItem(row, 4, QTableWidgetItem(log.details or ""))

    def on_tab_changed(self, index):
        if index == 0:
            self.load_users()
        else:
            self.load_logs()

    def add_user(self):
        dialog = UserDialog(parent=self)
        if dialog.exec():
            self.load_users()

    def edit_user(self):
        row = self.table.currentRow()
        if row < 0:
            return

        user = self.users[row]
        dialog = UserDialog(user, parent=self)
        if dialog.exec():
            self.load_users()

    def manage_permissions(self):
        dialog = PermissionDialog(parent=self)
        dialog.exec()
