from PyQt6.QtCore import QAbstractItemModel, QEvent, QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHeaderView,
    QMessageBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME, CRITICAL_ADMIN_PERMISSIONS
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.user_service import UserService
from cbpos.core.utils.display_labels import display_role_name, permission_group_label, permission_label
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t
from cbpos.ui.utils.layout_helpers import protect_vertical_sizing
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.table_helpers import configure_table_columns

# Per-cell flag for a role-column cell that must stay ticked. Item flags are per-row in a
# QTreeWidget, so the lock lives in the cell's data and _RoleCheckDelegate enforces it (#614).
LOCKED_CELL_ROLE = Qt.ItemDataRole.UserRole + 1
ORIGINAL_CHECK_STATE_ROLE = Qt.ItemDataRole.UserRole + 2


class _RoleCheckDelegate(QStyledItemDelegate):
    """Role-column delegate: draws the check indicator centered in the cell, and refuses to toggle
    (and greys out) cells flagged with LOCKED_CELL_ROLE."""

    @staticmethod
    def _style(option: QStyleOptionViewItem) -> QStyle:
        return option.widget.style() if option.widget else QApplication.style()

    def _indicator_rect(self, option: QStyleOptionViewItem, index: QModelIndex) -> QRect:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        rect = self._style(opt).subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, opt, opt.widget)
        rect.moveCenter(option.rect.center())
        return rect

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Keep rows tall enough for the themed indicator, so neighbouring checkboxes don't overlap."""
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), self._indicator_rect(option, index).height() + 6))
        return size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """Paint the cell background, then the check indicator centered in the cell."""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = self._style(opt)
        has_check = bool(opt.features & QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator)
        check_rect = self._indicator_rect(option, index)

        opt.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        if not has_check:
            return

        opt.rect = check_rect
        opt.state &= ~(
            QStyle.StateFlag.State_On
            | QStyle.StateFlag.State_Off
            | QStyle.StateFlag.State_NoChange
            | QStyle.StateFlag.State_HasFocus
        )
        if opt.checkState == Qt.CheckState.Checked:
            opt.state |= QStyle.StateFlag.State_On
        elif opt.checkState == Qt.CheckState.PartiallyChecked:
            opt.state |= QStyle.StateFlag.State_NoChange
        else:
            opt.state |= QStyle.StateFlag.State_Off
        if index.data(LOCKED_CELL_ROLE):
            opt.state &= ~QStyle.StateFlag.State_Enabled
        style.drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck, opt, painter, opt.widget)

    def editorEvent(
        self, event: QEvent, model: QAbstractItemModel, option: QStyleOptionViewItem, index: QModelIndex
    ) -> bool:
        """Toggle on a click inside the centered indicator or on Space/Select; locked cells never toggle."""
        if index.data(LOCKED_CELL_ROLE) or index.data(Qt.ItemDataRole.CheckStateRole) is None:
            return False
        if not index.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            return False

        event_type = event.type()
        if event_type in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
        ):
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            if not self._indicator_rect(option, index).contains(event.position().toPoint()):
                return False
            if event_type != QEvent.Type.MouseButtonRelease:
                return True  # swallow press/double-click on the box; toggle on release, as Qt does
        elif event_type == QEvent.Type.KeyPress:
            if event.key() not in (Qt.Key.Key_Space, Qt.Key.Key_Select):
                return False
        else:
            return False

        checked = Qt.CheckState(index.data(Qt.ItemDataRole.CheckStateRole)) == Qt.CheckState.Checked
        new_state = Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked
        res = model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)

        # If a parent/group item was toggled, ensure locked child cells stay checked (#552)
        tree = (
            option.widget
            if isinstance(option.widget, QTreeWidget)
            else (self.parent() if isinstance(self.parent(), QTreeWidget) else None)
        )
        if tree is not None:
            item = tree.itemFromIndex(index)
            if item is not None and item.childCount() > 0:
                self._restore_locked_descendants(item, index.column())

        return res

    @classmethod
    def _restore_locked_descendants(cls, item: QTreeWidgetItem, column: int) -> None:
        """Re-assert original check state on any descendant flagged with LOCKED_CELL_ROLE."""
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(column, LOCKED_CELL_ROLE):
                orig_state = child.data(column, ORIGINAL_CHECK_STATE_ROLE)
                if orig_state is not None:
                    child.setCheckState(column, orig_state)
                else:
                    child.setCheckState(column, Qt.CheckState.Checked)
            if child.childCount() > 0:
                cls._restore_locked_descendants(child, column)


class PermissionDialog(QDialog):
    """Dialog for editing which permissions each role grants, as a tree of permission groups with a checkbox
    column per role."""

    def __init__(self, parent=None):
        """Initialize the dialog and build the permission tree."""
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
        """Build the permission tree and the save/close buttons."""
        layout = QVBoxLayout(self)

        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(False)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)

        # Load Data
        self.load_data()

        # Buttons
        footer, self.btn_save, self.btn_close = make_dialog_footer(
            primary_key="permission.save_changes",
            on_primary=self.save_changes,
            cancel_key="common.close",
            on_cancel=self.reject,
            primary_object_name="BtnSave",
            cancel_object_name="BtnCancel",
        )
        layout.addLayout(footer)
        protect_vertical_sizing(self)

    def load_data(self):
        """Load roles and permissions, and populate the tree with one checkbox column per role."""
        self.roles = UserService.get_all_roles()
        self.permissions = PermissionService.get_all_permissions()

        # Setup Columns: Permission | Role 1 | Role 2 | ...
        headers = [_t("permission.col_permission")] + [display_role_name(role) for role in self.roles]
        self.tree.setHeaderLabels(headers)

        self._check_delegate = _RoleCheckDelegate(self.tree)
        for col_index in range(1, len(headers)):
            self.tree.setItemDelegateForColumn(col_index, self._check_delegate)

        # Group permissions by their stored group; labels are translated by code at display
        # time, so databases seeded with English descriptions ("Sales Add_Item") read right (#583).
        grouped_perms = {}
        for perm in self.permissions:
            grouped_perms.setdefault(perm.group or None, []).append(perm)

        # Identify acting user and non-admin constraints
        current_user = AuthService.get_current_user()
        is_non_admin = bool(current_user and current_user.role and current_user.role.name != ADMIN_ROLE_NAME)
        actor_perm_ids = (
            {p.id for p in current_user.role.permissions} if (current_user and current_user.role) else set()
        )

        # Populate Tree
        for group_name, perms in grouped_perms.items():
            group_item = QTreeWidgetItem(self.tree)
            group_item.setText(0, permission_group_label(group_name))
            group_item.setExpanded(True)
            # Group rows act as parent toggles for each role column (#552)
            group_item.setFlags(
                (group_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                | Qt.ItemFlag.ItemIsAutoTristate
                | Qt.ItemFlag.ItemIsUserCheckable
            )

            for perm in perms:
                perm_item = QTreeWidgetItem(group_item)
                perm_item.setText(0, permission_label(perm.code, perm.description))
                perm_item.setData(0, Qt.ItemDataRole.UserRole, perm.id)

                for i, role in enumerate(self.roles):
                    col_index = i + 1
                    checkbox = Qt.CheckState.Unchecked
                    if perm in role.permissions:
                        checkbox = Qt.CheckState.Checked

                    perm_item.setCheckState(col_index, checkbox)
                    perm_item.setData(col_index, ORIGINAL_CHECK_STATE_ROLE, checkbox)

                    # Lock only Admin's own critical cells, so other roles can still be granted
                    # them (#614). PermissionService re-adds them on save regardless (#551).
                    if role.name == ADMIN_ROLE_NAME and perm.code in CRITICAL_ADMIN_PERMISSIONS:
                        perm_item.setCheckState(col_index, Qt.CheckState.Checked)  # Force Checked
                        perm_item.setData(col_index, ORIGINAL_CHECK_STATE_ROLE, Qt.CheckState.Checked)
                        perm_item.setData(col_index, LOCKED_CELL_ROLE, True)
                        perm_item.setToolTip(col_index, _t("permission.admin_locked_tooltip"))
                    elif is_non_admin and role.name == ADMIN_ROLE_NAME:
                        perm_item.setData(col_index, LOCKED_CELL_ROLE, True)
                        perm_item.setToolTip(col_index, _t("roles.cannot_edit_admin"))
                    elif is_non_admin and current_user and role.id == current_user.role_id:
                        perm_item.setData(col_index, LOCKED_CELL_ROLE, True)
                        perm_item.setToolTip(col_index, _t("roles.cannot_edit_own_role"))
                    elif is_non_admin and perm.id not in actor_perm_ids:
                        perm_item.setData(col_index, LOCKED_CELL_ROLE, True)
                        perm_item.setToolTip(col_index, _t("roles.cannot_grant_unheld"))

        # Resize columns: permission title column stretches to absorb space, while role columns resize to content.
        column_modes = {0: QHeaderView.ResizeMode.Stretch}
        for i in range(1, len(headers)):
            column_modes[i] = QHeaderView.ResizeMode.ResizeToContents
        configure_table_columns(
            self.tree.header(),
            column_modes,
            stretch_last_section=False,
            minimum_section_size=80,
        )

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
        """Apply the tree's checked permissions to each role via PermissionService."""
        current_user = AuthService.get_current_user()
        is_non_admin = bool(current_user and current_user.role and current_user.role.name != ADMIN_ROLE_NAME)
        effective_actor_id = current_user.id if current_user else None

        try:
            role_permission_map = self.collect_role_permission_map(self.tree, self.roles)
            for role in self.roles:
                if is_non_admin:
                    if role.name == ADMIN_ROLE_NAME:
                        continue
                    if current_user and role.id == current_user.role_id:
                        continue

                new_ids = role_permission_map.get(role.id, [])
                if effective_actor_id is not None:
                    PermissionService.update_role_permissions(
                        role.id,
                        new_ids,
                        acting_user_id=effective_actor_id,
                    )
                else:
                    PermissionService.update_role_permissions(role.id, new_ids)

            QMessageBox.information(self, _t("common.success"), _t("permission.save_success"))
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), _t("permission.save_failed", error=translate_error(str(e))))
