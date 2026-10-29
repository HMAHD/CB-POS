"""User management view: accounts, roles, permissions, and activity log."""

from datetime import datetime, time

from PyQt6.QtCore import QDate
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.user_service import UserService
from cbpos.core.utils.audit_format import format_audit_action, format_audit_details, format_log_time
from cbpos.core.utils.display_labels import display_role_name, event_type_label
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.components.activation import Activatable
from cbpos.ui.dialogs.permission_dialog import PermissionDialog
from cbpos.ui.dialogs.role_manager import RoleManagerDialog
from cbpos.ui.dialogs.user_dialog import UserDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, INFO, SUCCESS, WARNING, is_light_theme, status_color
from cbpos.ui.widgets.status_pill_delegate import StatusPillDelegate, set_status_pill
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)


class UserView(QWidget, Activatable):
    """User management screen with tabs for the user list and the activity log."""

    def __init__(self):
        """Build the UI and register the translation callback with a weakref-safe unregister on destroy."""
        super().__init__()
        self.init_ui()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def init_ui(self):
        """Build the page header and the Users/Activity Log tabs, then load their initial data."""
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
        """Build the user tab's toolbar (add/permissions/roles) and the user table."""
        layout = QVBoxLayout(self.user_tab)

        # Toolbar
        toolbar = QHBoxLayout()

        self.btn_add = QPushButton()
        self.btn_add.setProperty("class", "primary")
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
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # ID
                1: QHeaderView.ResizeMode.Stretch,  # Username
                2: QHeaderView.ResizeMode.ResizeToContents,  # Role
                3: QHeaderView.ResizeMode.ResizeToContents,  # Status
            },
            minimum_section_size=60,
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setItemDelegateForColumn(3, StatusPillDelegate(self.table))
        self.empty_users_state = attach_table_empty_state(self.table, Icons.USERS, "common.no_items")
        # Qt's default row-number gutter and the real "ID" column both show
        # the same number (users are created sequentially, so the PK
        # almost always equals the row number) -- keep the genuinely
        # useful ID column, drop the redundant gutter (#295).
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.edit_user)

        layout.addWidget(self.table)

    def init_log_tab(self):
        """Build the activity log tab's filter bar (event type, date range) and log table."""
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
        self.log_clear_btn.setProperty("class", "secondary")
        self.log_clear_btn.clicked.connect(self.clear_log_filter)
        filter_layout.addWidget(self.log_clear_btn)

        layout.addWidget(filter_frame)

        self.log_table = QTableWidget()
        self.log_table.setColumnCount(6)
        configure_table_columns(
            self.log_table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.ResizeToContents,  # Time
                1: QHeaderView.ResizeMode.ResizeToContents,  # User
                2: QHeaderView.ResizeMode.ResizeToContents,  # Event
                3: QHeaderView.ResizeMode.ResizeToContents,  # Action
                4: QHeaderView.ResizeMode.ResizeToContents,  # Terminal
                5: QHeaderView.ResizeMode.Stretch,  # Details - needs the room
            },
        )
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.empty_logs_state = attach_table_empty_state(self.log_table, Icons.HISTORY, "common.no_items")

        layout.addWidget(self.log_table)

    def retranslate_ui(self):
        """Update all widget text, table headers, and event-type filter options from the translation system."""
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
        align_numeric_headers(self.table, [0])
        self.log_table.setHorizontalHeaderLabels(
            [
                _t("user.col_time"),
                _t("user.col_user"),
                _t("user.col_event"),
                _t("user.col_action"),
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
        self.log_event_filter.addItem(_t("user.event_pricing"), "PRICING")
        restored_index = self.log_event_filter.findData(current_event_type)
        self.log_event_filter.setCurrentIndex(restored_index if restored_index != -1 else 0)

    def load_users(self):
        """Refresh the user table from UserService, highlighting inactive users in red."""
        self.users = UserService.get_all_users()
        with batch_table_update(self.table):
            self.table.setRowCount(len(self.users))

            # Hoist LEGB locals
            set_item = self.table.setItem
            TableItem = QTableWidgetItem
            num_align = NUMERIC_ALIGNMENT
            pill_setter = set_status_pill
            role_formatter = display_role_name
            no_role_str = _t("user.no_role")
            active_str = _t("common.active")
            inactive_str = _t("common.inactive")
            status_success = SUCCESS
            status_danger = DANGER

            for row, user in enumerate(self.users):
                id_item = TableItem(str(user.id))
                id_item.setTextAlignment(num_align)
                set_item(row, 0, id_item)
                set_item(row, 1, TableItem(user.username))
                set_item(
                    row,
                    2,
                    TableItem(role_formatter(user.role) if user.role else no_role_str),
                )

                status = active_str if user.is_active else inactive_str
                item_status = TableItem(status)
                meaning = status_success if user.is_active else status_danger
                pill_setter(item_status, status, meaning)
                set_item(row, 3, item_status)

    # Destructive actions get flagged red even though their event_type
    # (TRANSACTION) is shared with routine actions like TRANSFER_ORDER.
    _DESTRUCTIVE_ACTIONS = {"VOID_SALE", "REFUND"}

    # A palette meaning (#559), or a (dark, light) pair for categories that
    # aren't a status, per event_type. LOGIN/LOGOUT/TIMEOUT are deliberately
    # absent -- they're the noisy majority of rows and coloring them would
    # drown out the events that actually need attention.
    _EVENT_TYPE_COLORS = {
        "SECURITY": WARNING,
        "INVENTORY": ("#20C997", "#0B7A5E"),
        "TRANSACTION": INFO,
        "CREDIT": SUCCESS,
        "PURCHASE": ("#B794F6", "#6F42C1"),
        "PRICING": ("#FD9A4B", "#B35400"),
    }

    def _log_event_color(self, log) -> QColor:
        if log.action in self._DESTRUCTIVE_ACTIONS:
            return status_color(DANGER)

        colors = self._EVENT_TYPE_COLORS.get(log.event_type)
        if colors is None:
            return None
        if isinstance(colors, str):
            return status_color(colors)
        return QColor(colors[1] if is_light_theme() else colors[0])

    def apply_log_filter(self):
        """Reload the activity log using the current filter settings."""
        self.load_logs()

    def clear_log_filter(self):
        """Reset the event-type and date-range filters to their defaults and reload the log."""
        self.log_event_filter.setCurrentIndex(0)
        self.log_date_from.setDate(QDate.currentDate().addMonths(-1))
        self.log_date_to.setDate(QDate.currentDate())
        self.load_logs()

    def load_logs(self):
        """Fetch activity log entries matching the current filters and populate the log table."""
        date_from = datetime.combine(self.log_date_from.date().toPyDate(), time.min)
        date_to = datetime.combine(self.log_date_to.date().toPyDate(), time.max)

        logs = UserService.get_recent_activity(
            event_type=self.log_event_filter.currentData(),
            date_from=date_from,
            date_to=date_to,
        )
        with batch_table_update(self.log_table):
            self.log_table.setRowCount(len(logs))

            # Hoist LEGB locals
            set_item = self.log_table.setItem
            TableItem = QTableWidgetItem
            fmt_time = format_log_time
            lbl_event = event_type_label
            fmt_action = format_audit_action
            fmt_details = format_audit_details
            get_color = self._log_event_color
            unknown_user_str = _t("user.unknown_user")

            for row, log in enumerate(logs):
                set_item(row, 0, TableItem(fmt_time(log.timestamp)))
                set_item(
                    row,
                    1,
                    TableItem(log.user.username if log.user else unknown_user_str),
                )
                event_item = TableItem(lbl_event(log.event_type))
                color = get_color(log)
                if color is not None:
                    event_item.setForeground(color)
                set_item(row, 2, event_item)
                set_item(row, 3, TableItem(fmt_action(log.action)))
                set_item(row, 4, TableItem(log.terminal_id or "-"))
                # Raw JSON stays in the DB; it is made readable only for display (#613)
                set_item(row, 5, TableItem(fmt_details(log.action, log.details)))

    def on_tab_changed(self, index):
        """Refresh the users table or the activity log when the active tab changes."""
        if index == 0:
            self.load_users()
        else:
            self.load_logs()

    def add_user(self):
        """Check permission, then open the add-user dialog and refresh the table on save."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.ADMIN_MANAGE_USERS, self):
            return

        dialog = UserDialog(parent=self)
        if dialog.exec():
            self.load_users()

    def edit_user(self):
        """Check permission, then open the edit dialog for the selected row and refresh the table on save."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

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
        """Check permission, then open the permission-management dialog."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.ADMIN_MANAGE_ROLES, self):
            return

        dialog = PermissionDialog(parent=self)
        dialog.exec()

    def manage_roles(self):
        """Check permission, then open the role-manager dialog and refresh the user table afterward."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.ADMIN_MANAGE_ROLES, self):
            return

        dialog = RoleManagerDialog(parent=self)
        dialog.exec()
        self.load_users()

    def on_activated(self) -> None:
        """Reload when this view is shown again, so the user never sees stale data."""
        self.load_users()
