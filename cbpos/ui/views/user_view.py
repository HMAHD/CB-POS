import weakref
from datetime import datetime, time

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
    QFrame,
    QDateEdit,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor
from cbpos.core.services.user_service import UserService
from cbpos.core.services.theme_service import ThemeService
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
        # A plain `lambda: unregister_language_callback(self.retranslate_ui)`
        # closes over self, so self -> destroyed signal -> lambda -> self is
        # a reference cycle that only the cyclic GC can break. When that GC
        # pass runs late enough to have to unwind a QObject whose C++ side is
        # already mid-teardown, calling back into it here segfaults instead
        # of raising. A weakref avoids creating the cycle in the first place,
        # so plain refcounting reclaims the view without ever needing a GC
        # pass to touch it.
        self_ref = weakref.ref(self)

        def _unregister():
            view = self_ref()
            if view is not None:
                unregister_language_callback(view.retranslate_ui)

        self.destroyed.connect(_unregister)

    def init_ui(self):
        layout = QVBoxLayout(self)

        from cbpos.ui.widgets.page_header import PageHeader

        self._page_header = PageHeader(icon_name=Icons.USERS)
        layout.addWidget(self._page_header)

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
        # Qt's default row-number gutter and the real "ID" column both show
        # the same number (users are created sequentially, so the PK
        # almost always equals the row number) -- keep the genuinely
        # useful ID column, drop the redundant gutter (#295).
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.edit_user)

        layout.addWidget(self.table)

    def init_log_tab(self):
        layout = QVBoxLayout(self.log_tab)

        # Filter Bar
        filter_frame = QFrame()
        filter_frame.setObjectName("DocFilterBar")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(8)

        self.lbl_log_event = QLabel()
        self.lbl_log_event.setObjectName("DocFilterLabel")
        filter_layout.addWidget(self.lbl_log_event)
        self.log_event_filter = QComboBox()
        self.log_event_filter.setObjectName("DocFilterCombo")
        self.log_event_filter.setMinimumWidth(130)
        filter_layout.addWidget(self.log_event_filter)

        self.lbl_log_from = QLabel()
        self.lbl_log_from.setObjectName("DocFilterLabel")
        filter_layout.addWidget(self.lbl_log_from)
        self.log_date_from = QDateEdit()
        self.log_date_from.setObjectName("DocDateEdit")
        self.log_date_from.setCalendarPopup(True)
        self.log_date_from.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addWidget(self.log_date_from)

        self.lbl_log_to = QLabel()
        self.lbl_log_to.setObjectName("DocFilterLabel")
        filter_layout.addWidget(self.lbl_log_to)
        self.log_date_to = QDateEdit()
        self.log_date_to.setObjectName("DocDateEdit")
        self.log_date_to.setCalendarPopup(True)
        self.log_date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.log_date_to)

        filter_layout.addStretch(1)

        self.log_filter_btn = QPushButton()
        self.log_filter_btn.setObjectName("DocFilterBtn")
        self.log_filter_btn.clicked.connect(self.apply_log_filter)
        filter_layout.addWidget(self.log_filter_btn)

        self.log_clear_btn = QPushButton()
        self.log_clear_btn.setObjectName("DocClearBtn")
        self.log_clear_btn.clicked.connect(self.clear_log_filter)
        filter_layout.addWidget(self.log_clear_btn)

        layout.addWidget(filter_frame)

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
        self._page_header.set_title(_t("management.sidebar_users"))
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

        self.lbl_log_event.setText(_t("user.filter_event_type"))
        self.lbl_log_from.setText(_t("user.filter_from"))
        self.lbl_log_to.setText(_t("user.filter_to"))
        self.log_filter_btn.setText(_t("user.btn_filter"))
        self.log_clear_btn.setText(_t("user.btn_clear"))

        current_event_type = self.log_event_filter.currentData()
        self.log_event_filter.clear()
        self.log_event_filter.addItem(_t("user.event_all"), None)
        self.log_event_filter.addItem(_t("user.event_login"), "LOGIN")
        self.log_event_filter.addItem(_t("user.event_logout"), "LOGOUT")
        self.log_event_filter.addItem(_t("user.event_timeout"), "TIMEOUT")
        self.log_event_filter.addItem(_t("user.event_security"), "SECURITY")
        self.log_event_filter.addItem(_t("user.event_inventory"), "INVENTORY")
        self.log_event_filter.addItem(_t("user.event_transaction"), "TRANSACTION")
        self.log_event_filter.addItem(_t("user.event_credit"), "CREDIT")
        self.log_event_filter.addItem(_t("user.event_purchase"), "PURCHASE")
        restored_index = self.log_event_filter.findData(current_event_type)
        self.log_event_filter.setCurrentIndex(restored_index if restored_index != -1 else 0)

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

    # Destructive actions get flagged red even though their event_type
    # (TRANSACTION) is shared with routine actions like TRANSFER_ORDER.
    _DESTRUCTIVE_ACTIONS = {"VOID_SALE", "REFUND"}

    # (dark theme color, light theme color) per event_type. LOGIN/LOGOUT/
    # TIMEOUT are deliberately absent -- they're the noisy majority of rows
    # and coloring them would drown out the events that actually need
    # attention.
    _EVENT_TYPE_COLORS = {
        "SECURITY": ("#FFDC00", "#B8860B"),
        "INVENTORY": ("#20C997", "#0CA678"),
        "TRANSACTION": ("#00BCEB", "#0D6EFD"),
        "CREDIT": ("#39FF14", "#198754"),
        "PURCHASE": ("#B794F6", "#6F42C1"),
    }

    def _log_event_color(self, log) -> QColor:
        is_light = ThemeService.current_theme.lower() == "light"

        if log.action in self._DESTRUCTIVE_ACTIONS:
            return QColor("#DC3545" if is_light else "#FF4136")

        colors = self._EVENT_TYPE_COLORS.get(log.event_type)
        if colors is None:
            return None
        return QColor(colors[1] if is_light else colors[0])

    def apply_log_filter(self):
        self.load_logs()

    def clear_log_filter(self):
        self.log_event_filter.setCurrentIndex(0)
        self.log_date_from.setDate(QDate.currentDate().addMonths(-1))
        self.log_date_to.setDate(QDate.currentDate())
        self.load_logs()

    def load_logs(self):
        date_from = datetime.combine(self.log_date_from.date().toPyDate(), time.min)
        date_to = datetime.combine(self.log_date_to.date().toPyDate(), time.max)

        logs = UserService.get_recent_activity(
            event_type=self.log_event_filter.currentData(),
            date_from=date_from,
            date_to=date_to,
        )
        self.log_table.setRowCount(len(logs))

        for row, log in enumerate(logs):
            self.log_table.setItem(row, 0, QTableWidgetItem(str(log.timestamp)))
            self.log_table.setItem(
                row,
                1,
                QTableWidgetItem(log.user.username if log.user else _t("user.unknown_user")),
            )
            event_item = QTableWidgetItem(log.event_type)
            color = self._log_event_color(log)
            if color is not None:
                event_item.setForeground(color)
            self.log_table.setItem(row, 2, event_item)
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
