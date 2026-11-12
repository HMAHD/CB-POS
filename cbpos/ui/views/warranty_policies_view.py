"""Warranty Policies view for managing warranty coverage rules (#821)."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import WarrantyPolicy
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.warranty_service import WarrantyService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.terminal_guard import catalog_is_read_only
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.components.activation import Activatable
from cbpos.ui.dialogs.warranty_policy_dialog import WarrantyPolicyDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.read_only_banner import ReadOnlyBanner
from cbpos.ui.widgets.table_helpers import (
    attach_table_empty_state,
    batch_table_update,
)

logger = logging.getLogger(__name__)

POLICY_ID_ROLE = Qt.ItemDataRole.UserRole


class WarrantyPoliciesView(QWidget, Activatable):
    """View displaying and managing warranty policies."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policies: list[WarrantyPolicy] = []
        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)
        self.load_data()

    def init_ui(self) -> None:
        """Initialize table layout, search filter, and action toolbar."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Till banner if read-only
        if catalog_is_read_only():
            main_layout.addWidget(ReadOnlyBanner())

        # Top toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "heading-2")
        toolbar.addWidget(self.lbl_title)

        toolbar.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_t("common.search"))
        self.search_input.setFixedWidth(240)
        self.search_input.textChanged.connect(self._filter_table)
        toolbar.addWidget(self.search_input)

        self.btn_new = QPushButton()
        self.btn_new.setProperty("class", "primary")
        self.btn_new.setIcon(Icons.get(Icons.ADD))
        self.btn_new.clicked.connect(self._on_new_policy)
        toolbar.addWidget(self.btn_new)

        main_layout.addLayout(toolbar)

        # Error banner
        self.error_banner = QWidget()
        banner_layout = QHBoxLayout(self.error_banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        self.lbl_error = QLabel(_t("warranty.load_error_banner"))
        self.lbl_error.setProperty("class", "danger")
        banner_layout.addWidget(self.lbl_error)
        banner_layout.addStretch()
        self.btn_retry = QPushButton(_t("common.retry"))
        self.btn_retry.setProperty("class", "secondary")
        self.btn_retry.clicked.connect(self.load_data)
        banner_layout.addWidget(self.btn_retry)
        self.error_banner.hide()
        main_layout.addWidget(self.error_banner)

        # Policies table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)

        attach_table_empty_state(
            self.table,
            Icons.WARRANTY,
            "warranty.empty_title",
            "warranty.empty_desc",
        )

        main_layout.addWidget(self.table)

    def retranslate_ui(self) -> None:
        """Update localized text for view components."""
        self.lbl_title.setText(_t("warranty.policies"))
        self.search_input.setPlaceholderText(_t("common.search"))
        self.btn_new.setText(_t("warranty.new_policy"))
        if hasattr(self, "lbl_error"):
            self.lbl_error.setText(_t("warranty.load_error_banner"))
            self.btn_retry.setText(_t("common.retry"))

        headers = [
            _t("warranty.col_name"),
            _t("warranty.col_type"),
            _t("warranty.col_duration"),
            _t("warranty.col_remedy"),
            _t("warranty.col_provider"),
            _t("warranty.col_status"),
            _t("common.actions"),
        ]
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        self._render_table()

    def activate(self) -> None:
        """Activatable interface: refresh policies when view becomes active."""
        self.load_data()

    def load_data(self) -> None:
        """Fetch all policies (including inactive) from WarrantyService."""
        try:
            self._policies = WarrantyService.list_policies(include_inactive=True)
            if hasattr(self, "error_banner"):
                self.error_banner.hide()
            self._render_table()
            self._update_permissions()
        except Exception as e:
            logger.error("Failed to load warranty policies: %s", e)
            if hasattr(self, "error_banner"):
                self.error_banner.show()
            self.btn_new.setEnabled(False)

    def _update_permissions(self) -> None:
        """Enable/disable buttons based on current user permissions and terminal role."""
        if catalog_is_read_only():
            self.btn_new.setEnabled(False)
            return

        curr = AuthService.get_current_user()
        can_manage = curr and PermissionService.user_has_permission(curr, Permissions.WARRANTY_MANAGE_POLICIES)
        self.btn_new.setEnabled(bool(can_manage))

    def _render_table(self) -> None:
        """Render policy rows into table widget."""
        query = self.search_input.text().strip().lower()

        filtered = [
            p
            for p in self._policies
            if not query
            or query in p.name.lower()
            or (p.name_si and query in p.name_si.lower())
            or (p.name_ta and query in p.name_ta.lower())
            or (p.provider_name and query in p.provider_name.lower())
        ]

        with batch_table_update(self.table):
            self.table.setRowCount(len(filtered))
            for row_idx, policy in enumerate(filtered):
                # 0: Name
                name_item = QTableWidgetItem(policy.get_display_name())
                name_item.setData(POLICY_ID_ROLE, policy.id)
                self.table.setItem(row_idx, 0, name_item)

                # 1: Type
                type_key = f"warranty.types.{policy.warranty_type.lower()}"
                type_text = _t(type_key, default=policy.warranty_type)
                self.table.setItem(row_idx, 1, QTableWidgetItem(type_text))

                # 2: Duration
                unit_key = f"warranty.units.{policy.duration_unit.lower()}"
                unit_text = _t(unit_key, default=policy.duration_unit)
                dur_text = f"{policy.duration} {unit_text}"
                self.table.setItem(row_idx, 2, QTableWidgetItem(dur_text))

                # 3: Remedy
                rem_key = f"warranty.remedies.{policy.remedy.lower()}"
                rem_text = _t(rem_key, default=policy.remedy)
                self.table.setItem(row_idx, 3, QTableWidgetItem(rem_text))

                # 4: Provider
                prov_text = policy.provider_name or _t("warranty.types.shop")
                self.table.setItem(row_idx, 4, QTableWidgetItem(prov_text))

                # 5: Status
                status_text = _t("warranty.active") if policy.is_active else _t("warranty.inactive")
                status_item = QTableWidgetItem(status_text)
                if not policy.is_active:
                    status_item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(row_idx, 5, status_item)

                # 6: Actions widget
                actions_widget = self._create_actions_widget(policy)
                self.table.setCellWidget(row_idx, 6, actions_widget)

    def _create_actions_widget(self, policy: WarrantyPolicy) -> QWidget:
        """Create inline Edit and Activate/Deactivate action buttons."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        curr = AuthService.get_current_user()
        can_manage = (
            curr
            and PermissionService.user_has_permission(curr, Permissions.WARRANTY_MANAGE_POLICIES)
            and not catalog_is_read_only()
        )

        btn_edit = QPushButton(_t("common.edit"))
        btn_edit.setProperty("class", "secondary")
        btn_edit.setEnabled(bool(can_manage))
        btn_edit.clicked.connect(lambda _, p=policy: self._on_edit_policy(p))
        layout.addWidget(btn_edit)

        if policy.is_active:
            btn_toggle = QPushButton(_t("warranty.deactivate"))
            btn_toggle.setProperty("class", "danger")
            btn_toggle.setEnabled(bool(can_manage))
            btn_toggle.clicked.connect(lambda _, pid=policy.id: self._on_deactivate_policy(pid))
        else:
            btn_toggle = QPushButton(_t("warranty.activate"))
            btn_toggle.setProperty("class", "primary")
            btn_toggle.setEnabled(bool(can_manage))
            btn_toggle.clicked.connect(lambda _, pid=policy.id: self._on_activate_policy(pid))
        layout.addWidget(btn_toggle)

        return widget

    def _filter_table(self) -> None:
        self._render_table()

    def _on_new_policy(self) -> None:
        dialog = WarrantyPolicyDialog(parent=self)
        if dialog.exec():
            self.load_data()

    def _on_row_double_clicked(self, row: int, col: int) -> None:
        if getattr(self, "read_only", False) or catalog_is_read_only():
            return
        from cbpos.core.utils.permission_helper import check_permission_with_override

        user = check_permission_with_override(Permissions.WARRANTY_MANAGE_POLICIES, self)
        if not user:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        policy_id = item.data(POLICY_ID_ROLE)
        policy = next((p for p in self._policies if p.id == policy_id), None)
        if policy:
            self._on_edit_policy(policy)

    def _on_edit_policy(self, policy: WarrantyPolicy) -> None:
        dialog = WarrantyPolicyDialog(parent=self, policy=policy)
        if dialog.exec():
            self.load_data()

    def _deactivate_policy(self, policy: WarrantyPolicy) -> None:
        """Deactivate policy helper with confirmation dialog."""
        self._on_deactivate_policy(policy.id)

    def _on_deactivate_policy(self, policy_id: int) -> None:
        reply = QMessageBox.question(
            self,
            _t("warranty.deactivate_confirm_title"),
            _t("warranty.deactivate_confirm_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            curr = AuthService.get_current_user()
            user_id = curr.id if curr else None
            WarrantyService.deactivate_policy(policy_id, acting_user_id=user_id)
            self.load_data()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))

    def _on_activate_policy(self, policy_id: int) -> None:
        try:
            curr = AuthService.get_current_user()
            user_id = curr.id if curr else None
            WarrantyService.activate_policy(policy_id, acting_user_id=user_id)
            self.load_data()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
