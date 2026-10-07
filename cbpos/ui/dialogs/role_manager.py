"""
Dialog for managing user roles (CRUD) — #296.

The Role table and User.role_id foreign key were already fully wired
(UserDialog's role picker, PermissionDialog's permission grid), but
nothing in the UI could create, rename, or delete a role itself. This
dialog fills that gap, modeled on CategoryManagerDialog's list + form
layout.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.services.role_service import RoleService
from cbpos.core.services.user_service import UserService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t
from cbpos.ui.widgets.table_helpers import configure_table_columns

logger = logging.getLogger(__name__)

ROLE_ID_ROLE = Qt.ItemDataRole.UserRole


class RoleManagerDialog(QDialog):
    """Role manager with a flat list, inline form, and Admin-role guards."""

    def __init__(self, parent=None):
        """Build the dialog and load the current role list."""
        super().__init__(parent)
        self.setWindowTitle(_t("role_manager.title"))
        self.setMinimumSize(560, 460)
        self.resize(600, 480)
        self.setObjectName("RoleManagerDialog")
        self._editing_id = None
        self._setup_ui()
        self._load_list()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Left: Role list ──
        left = QVBoxLayout()
        left.setSpacing(8)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_t("role_manager.col_role"), _t("role_manager.col_users")])
        configure_table_columns(
            self.tree.header(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.currentItemChanged.connect(self._on_selection_changed)
        left.addWidget(self.tree)

        layout.addLayout(left, 2)

        # ── Right: Form + Actions ──
        right = QVBoxLayout()
        right.setSpacing(10)

        form_group = QGroupBox(_t("role_manager.details_group"))
        form_layout = QFormLayout(form_group)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(10)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText(_t("role_manager.name_placeholder"))
        form_layout.addRow(_t("role_manager.name_label"), self.txt_name)

        right.addWidget(form_group)

        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_save = QPushButton(_t("role_manager.save_new"))
        self.btn_save.setProperty("class", "primary")
        self.btn_save.clicked.connect(self._save_role)
        btn_layout.addWidget(self.btn_save)

        self.btn_delete = QPushButton(_t("role_manager.delete_selected"))
        self.btn_delete.setProperty("class", "danger")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete_role)
        btn_layout.addWidget(self.btn_delete)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        btn_layout.addWidget(sep)

        self.btn_clear = QPushButton(_t("role_manager.clear_new"))
        self.btn_clear.clicked.connect(self._clear_form)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch()

        btn_close = QPushButton(_t("common.close"))
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        right.addLayout(btn_layout)

        layout.addLayout(right, 1)

    # ── List loading ──

    def _load_list(self) -> None:
        self.tree.clear()
        self.roles = UserService.get_all_roles()

        for role in sorted(self.roles, key=lambda r: r.name):
            user_count = RoleService.get_user_count_for_role(role.id)
            name = role.name
            if role.name == ADMIN_ROLE_NAME:
                name += _t("role_manager.builtin_suffix")
            item = QTreeWidgetItem([name, str(user_count)])
            item.setData(0, ROLE_ID_ROLE, role.id)
            self.tree.addTopLevelItem(item)

    # ── Selection ──

    def _on_selection_changed(self, current: QTreeWidgetItem, _prev: QTreeWidgetItem) -> None:
        has_selection = current is not None
        self.btn_delete.setEnabled(has_selection)

        if not has_selection:
            self._editing_id = None
            self._set_builtin_locked(False)
            return

        role_id = current.data(0, ROLE_ID_ROLE)
        self._editing_id = role_id

        role = next((r for r in self.roles if r.id == role_id), None)
        if not role:
            return

        self.txt_name.setText(role.name)
        self.btn_save.setText(_t("role_manager.update"))
        self._set_builtin_locked(role.name == ADMIN_ROLE_NAME)

    def _set_builtin_locked(self, locked: bool) -> None:
        """Show the built-in Admin role's rules up front: no rename, no delete (#614).
        RoleService still enforces both; this only stops the user hitting an error first."""
        tooltip = _t("role_manager.builtin_locked_tooltip") if locked else ""
        self.txt_name.setReadOnly(locked)
        self.txt_name.setToolTip(tooltip)
        if locked:
            self.btn_delete.setEnabled(False)
        self.btn_delete.setToolTip(tooltip)

    # ── Actions ──

    def _save_role(self) -> None:
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, _t("common.validation_error"), _t("role_manager.name_required"))
            self.txt_name.setFocus()
            return

        if self._editing_id:
            editing_role = next((r for r in self.roles if r.id == self._editing_id), None)
            if editing_role and editing_role.name == ADMIN_ROLE_NAME and name != ADMIN_ROLE_NAME:
                QMessageBox.warning(
                    self,
                    _t("role_manager.cannot_rename_title"),
                    _t("role_manager.cannot_rename_admin_msg"),
                )
                return

        try:
            if self._editing_id:
                RoleService.update(self._editing_id, name=name)
            else:
                RoleService.create(name=name)
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
            return

        self._load_list()
        self._clear_form()

    def _delete_role(self) -> None:
        current = self.tree.currentItem()
        if not current:
            return

        role_id = current.data(0, ROLE_ID_ROLE)
        role = next((r for r in self.roles if r.id == role_id), None)
        if not role:
            return

        if role.name == ADMIN_ROLE_NAME:
            QMessageBox.warning(
                self,
                _t("role_manager.cannot_delete_title"),
                _t("role_manager.cannot_delete_admin_msg"),
            )
            return

        user_count = RoleService.get_user_count_for_role(role_id)
        if user_count > 0:
            QMessageBox.warning(
                self,
                _t("role_manager.cannot_delete_title"),
                _t("role_manager.cannot_delete_in_use_msg", name=role.name, count=user_count),
            )
            return

        reply = QMessageBox.question(
            self,
            _t("role_manager.confirm_delete_title"),
            _t("role_manager.confirm_delete_msg", name=role.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            RoleService.delete(role_id)
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
            return

        self._load_list()
        self._clear_form()

    def _clear_form(self) -> None:
        self._editing_id = None
        self.txt_name.clear()
        self.btn_save.setText(_t("role_manager.save_new"))
        self.btn_delete.setEnabled(False)
        self._set_builtin_locked(False)
        self.tree.clearSelection()
        self.txt_name.setFocus()
