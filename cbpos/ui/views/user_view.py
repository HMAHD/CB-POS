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
from cbpos.ui.dialogs.role_manager import RoleManagerDialog
from cbpos.ui.resources.icons import Icons
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.widgets.table_helpers import configure_table_columns


class UserDialog(QDialog):
    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle(_t("user.add_user") if not user else _t("user.edit_user"))
        self.setFixedWidth(400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Username
        layout.addWidget(QLabel(_t("user.username_label")))
        self.txt_username = QLineEdit()
        if self.user:
            self.txt_username.setText(self.user.username)
        layout.addWidget(self.txt_username)

        # PIN
        layout.addWidget(QLabel(_t("user.pin_keep_unchanged") if self.user else _t("user.pin_label")))
        self.txt_pin = QLineEdit()
        self.txt_pin.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.txt_pin)

        # Role
        layout.addWidget(QLabel(_t("user.role_label")))
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
        self.chk_active = QCheckBox(_t("common.active"))
        self.chk_active.setChecked(True)
        if self.user:
            self.chk_active.setChecked(self.user.is_active)
        layout.addWidget(self.chk_active)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton(_t("common.save"))
        btn_save.clicked.connect(self.save)
        btn_cancel = QPushButton(_t("common.cancel"))
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
            QMessageBox.warning(self, _t("common.error"), _t("user.username_required"))
            return

        if not self.user and not pin:
            QMessageBox.warning(self, _t("common.error"), _t("user.pin_required"))
            return

        if pin and (len(pin) < 4 or len(pin) > 6 or not pin.isdigit()):
            QMessageBox.warning(self, _t("common.error"), _t("user.pin_invalid"))
            return

        try:
            if self.user:
                UserService.update_user(self.user.id, username, pin if pin else None, role_id, is_active)
            else:
                UserService.create_user(username, pin, role_id)
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("user.save_failed", error=str(e)),
            )


class UserView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Users
        self.user_tab = QWidget()
        self.init_user_tab()
        self.tabs.addTab(self.user_tab, "")

        # Tab 2: Activity Log
        self.log_tab = QWidget()
        self.init_log_tab()
        self.tabs.addTab(self.log_tab, "")

        # Load data
        self.load_users()
        self.load_logs()

        # Refresh on tab change
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def init_user_tab(self):
        layout = QVBoxLayout(self.user_tab)

        # Toolbar
        toolbar = QHBoxLayout()

        self.btn_add = QPushButton()
        self.btn_add.setIcon(Icons.get("fa5s.plus"))
        self.btn_add.clicked.connect(self.add_user)

        self.btn_perms = QPushButton()
        self.btn_perms.setIcon(Icons.get("fa5s.lock"))
        self.btn_perms.clicked.connect(self.manage_permissions)

        self.btn_roles = QPushButton()
        self.btn_roles.setIcon(Icons.get("fa5s.user-tag"))
        self.btn_roles.clicked.connect(self.manage_roles)

        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_perms)
        toolbar.addWidget(self.btn_roles)
        toolbar.addStretch()

        layout.addLayout(toolbar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_user)

        layout.addWidget(self.table)

    def init_log_tab(self):
        layout = QVBoxLayout(self.log_tab)

        self.log_table = QTableWidget()
        self.log_table.setColumnCount(5)
        configure_table_columns(
            self.log_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # Time
                1: QHeaderView.ResizeMode.ResizeToContents,  # User
                2: QHeaderView.ResizeMode.ResizeToContents,  # Event
                3: QHeaderView.ResizeMode.ResizeToContents,  # Terminal
                4: QHeaderView.ResizeMode.Stretch,  # Details - needs the room
            },
        )
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout.addWidget(self.log_table)

    def retranslate_ui(self):
        self.tabs.setTabText(0, _t("user.tab_users"))
        self.tabs.setTabText(1, _t("user.tab_activity_log"))
        self.btn_add.setText(_t("user.add_user"))
        self.btn_perms.setText(_t("user.manage_permissions"))
        self.btn_roles.setText(_t("user.manage_roles"))
        self.table.setHorizontalHeaderLabels(
            [
                _t("common.id"),
                _t("user.col_username"),
                _t("user.col_role"),
                _t("common.status"),
            ]
        )
        self.log_table.setHorizontalHeaderLabels(
            [
                _t("user.col_time"),
                _t("user.col_user"),
                _t("user.col_event"),
                _t("user.col_terminal"),
                _t("user.col_details"),
            ]
        )

    def load_users(self):
        self.users = UserService.get_all_users()
        self.table.setRowCount(len(self.users))

        for row, user in enumerate(self.users):
            self.table.setItem(row, 0, QTableWidgetItem(str(user.id)))
            self.table.setItem(row, 1, QTableWidgetItem(user.username))
            self.table.setItem(
                row,
                2,
                QTableWidgetItem(user.role.name if user.role else _t("user.no_role")),
            )

            status = _t("common.active") if user.is_active else _t("common.inactive")
            item_status = QTableWidgetItem(status)
            if not user.is_active:
                item_status.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 3, item_status)

    def load_logs(self):
        logs = UserService.get_recent_activity()
        self.log_table.setRowCount(len(logs))

        for row, log in enumerate(logs):
            self.log_table.setItem(row, 0, QTableWidgetItem(str(log.timestamp)))
            self.log_table.setItem(
                row,
                1,
                QTableWidgetItem(log.user.username if log.user else _t("user.unknown_user")),
            )
            self.log_table.setItem(row, 2, QTableWidgetItem(log.event_type))
            self.log_table.setItem(row, 3, QTableWidgetItem(log.terminal_id or "-"))
            self.log_table.setItem(row, 4, QTableWidgetItem(log.details or ""))

    def on_tab_changed(self, index):
        if index == 0:
            self.load_users()
        else:
            self.load_logs()

    def add_user(self):
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.ADMIN_MANAGE_USERS, self):
            return

        dialog = UserDialog(parent=self)
        if dialog.exec():
            self.load_users()

    def edit_user(self):
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.ADMIN_MANAGE_USERS, self):
            return

        row = self.table.currentRow()
        if row < 0:
            return

        user = self.users[row]
        dialog = UserDialog(user, parent=self)
        if dialog.exec():
            self.load_users()

    def manage_permissions(self):
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.ADMIN_MANAGE_ROLES, self):
            return

        dialog = PermissionDialog(parent=self)
        dialog.exec()

    def manage_roles(self):
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.ADMIN_MANAGE_ROLES, self):
            return

        dialog = RoleManagerDialog(parent=self)
        dialog.exec()
        self.load_users()
