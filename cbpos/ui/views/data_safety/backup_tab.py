"""Data Safety -> Backup tab: the backup folder, shop password, and backup list."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.backup_service import BackupService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.utils.formatters import format_relative_time
from cbpos.i18n import _t
from cbpos.ui.dialogs.backup_password_dialog import BackupPasswordDialog, ensure_backup_password
from cbpos.ui.resources.icons import Icons
from cbpos.ui.utils.style_helpers import set_status_class
from cbpos.ui.views.data_safety.network_notice import NetworkModeNoticeCard
from cbpos.ui.widgets.loading_overlay import LoadingOverlay
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    RelativeTimeTableWidgetItem,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)
from cbpos.ui.workers import BackupListWorker, BackupWorker

logger = logging.getLogger(__name__)


class BackupTabWidget(QWidget):
    """List, create, clean and delete backups; set the shop backup password.

    Signals:
        restore_requested(str): The user chose Restore on a backup row; the
            path of that backup file.
        password_changed: The shop backup password may have just been set
            or changed.
    """

    restore_requested = pyqtSignal(str)
    password_changed = pyqtSignal()

    # Backup table columns
    COL_FILENAME, COL_DATE, COL_SIZE, COL_TYPE, COL_ACTIONS = range(5)
    _TYPE_KEYS = {
        "manual": "data_safety.backup_type_manual",
        "auto": "data_safety.backup_type_auto",
        "snapshot": "data_safety.backup_type_snapshot",
    }

    def __init__(self, overlay: LoadingOverlay, parent: QWidget | None = None) -> None:
        """Build the tab.

        Args:
            overlay: The page's loading overlay, shown while a job runs.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._overlay = overlay
        self._build_ui()
        self.retranslate_ui()

    def refresh(self) -> None:
        """Re-read the password state and rescan the backup folder."""
        self._apply_mode()
        if not BackupService.is_supported():
            return
        self.refresh_password_status()
        self._refresh_backup_list()

    def _password_may_have_changed(self) -> None:
        self.refresh_password_status()
        self.password_changed.emit()

    def _apply_mode(self) -> None:
        supported = BackupService.is_supported()
        self.standalone_container.setVisible(supported)
        self.notice_card.setVisible(not supported)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(12)

        self.notice_card = NetworkModeNoticeCard()
        layout.addWidget(self.notice_card)

        self.standalone_container = QWidget()
        standalone_layout = QVBoxLayout(self.standalone_container)
        standalone_layout.setContentsMargins(0, 0, 0, 0)
        standalone_layout.setSpacing(12)

        # Backup directory display
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(8)
        self.lbl_dir_label = QLabel()
        self.lbl_dir_label.setProperty("class", "muted")
        dir_layout.addWidget(self.lbl_dir_label)

        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        self.lbl_backup_dir = QLabel(backup_dir)
        self.lbl_backup_dir.setWordWrap(True)
        dir_layout.addWidget(self.lbl_backup_dir, 1)

        self.btn_change_dir = QPushButton()
        self.btn_change_dir.setFixedWidth(100)
        self.btn_change_dir.clicked.connect(self._change_backup_dir)
        dir_layout.addWidget(self.btn_change_dir)
        standalone_layout.addLayout(dir_layout)

        # Shop backup password -- one password for every backup (#619)
        pwd_layout = QHBoxLayout()
        pwd_layout.setSpacing(8)
        self.lbl_pwd_label = QLabel()
        self.lbl_pwd_label.setProperty("class", "muted")
        pwd_layout.addWidget(self.lbl_pwd_label)
        self.lbl_pwd_status = QLabel()
        self.lbl_pwd_status.setWordWrap(True)
        pwd_layout.addWidget(self.lbl_pwd_status, 1)
        self.btn_backup_password = QPushButton()
        self.btn_backup_password.clicked.connect(self._change_backup_password)
        pwd_layout.addWidget(self.btn_backup_password)
        standalone_layout.addLayout(pwd_layout)

        # Newest backup and whether the shop password opens it (#619)
        self.lbl_last_backup = QLabel()
        self.lbl_last_backup.setObjectName("LastBackupStatus")
        self.lbl_last_backup.setWordWrap(True)
        self._last_status: dict | None = None
        standalone_layout.addWidget(self.lbl_last_backup)

        # Backup list table — QSS handles all table styling
        self.backup_table = QTableWidget()
        self._backup_data: list[dict] = []
        self.backup_table.setColumnCount(5)
        self.backup_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.backup_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.backup_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.backup_table.verticalHeader().setVisible(False)
        # Tall enough for the per-row Restore/Delete buttons (#620)
        self.backup_table.verticalHeader().setDefaultSectionSize(48)
        self.backup_table.setAlternatingRowColors(True)

        configure_table_columns(
            self.backup_table.horizontalHeader(),
            {
                self.COL_FILENAME: QHeaderView.ResizeMode.Stretch,
                self.COL_DATE: QHeaderView.ResizeMode.ResizeToContents,
                self.COL_SIZE: QHeaderView.ResizeMode.ResizeToContents,
                self.COL_TYPE: QHeaderView.ResizeMode.ResizeToContents,
                self.COL_ACTIONS: QHeaderView.ResizeMode.Interactive,
            },
        )
        self.empty_table_state = attach_table_empty_state(self.backup_table, Icons.DOCUMENTS, "common.no_items")
        self.backup_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.backup_table.customContextMenuRequested.connect(self._show_backup_context_menu)
        standalone_layout.addWidget(self.backup_table, 1)

        # Action buttons — use class properties for theme-aware styling
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_create_backup = QPushButton()
        self.btn_create_backup.setProperty("class", "primary")
        self.btn_create_backup.clicked.connect(self._create_backup)
        btn_layout.addWidget(self.btn_create_backup)

        self.btn_clean_old = QPushButton()
        self.btn_clean_old.clicked.connect(self._clean_old_backups)
        btn_layout.addWidget(self.btn_clean_old)

        self.btn_backup_refresh = QPushButton()
        self.btn_backup_refresh.clicked.connect(self._refresh_backup_list)
        btn_layout.addWidget(self.btn_backup_refresh)

        btn_layout.addStretch()
        standalone_layout.addLayout(btn_layout)

        layout.addWidget(self.standalone_container, 1)
        layout.addStretch(1)
        self._apply_mode()

    def _refresh_backup_list(self) -> None:
        """Scan the backup directory in the background.

        Runs on a QThread with the LoadingOverlay shown, matching every
        other operation on this page (create backup, restore, vacuum,
        integrity check, export) -- this call site was the one missed,
        so the UI froze with zero feedback while it scanned (#339).
        """
        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        self._overlay.show_loading(_t("data_safety.backup_list_loading"))
        self._backup_list_worker = BackupListWorker(backup_dir)
        self._backup_list_worker.status.connect(self._on_backup_status)
        self._backup_list_worker.result.connect(self._on_backup_list_loaded)
        self._backup_list_worker.error.connect(self._on_backup_list_error)
        self._backup_list_worker.start()

    def _on_backup_status(self, status: dict) -> None:
        """Show the newest backup's date and whether it can be restored."""
        self._last_status = status
        if not status.get("date"):
            text, css = _t("data_safety.last_backup_none"), "muted"
            self.lbl_last_backup.setToolTip("")
        else:
            raw_date = status["date"]
            rel_date = format_relative_time(raw_date)
            date_display = f"{rel_date} ({raw_date})" if rel_date and rel_date != raw_date else str(raw_date)
            if status.get("restorable"):
                text, css = _t("data_safety.last_backup_ok", date=date_display), "credit"
            else:
                text, css = _t("data_safety.last_backup_unverified", date=date_display), "debit"
            self.lbl_last_backup.setToolTip(str(raw_date))
        set_status_class(self.lbl_last_backup, css, text)

    def _on_backup_list_loaded(self, backups: list) -> None:
        self._overlay.hide_loading()
        self._backup_data = backups

        self._fill_backup_table()

    def _fill_backup_table(self) -> None:
        """(Re)build the backup rows from ``self._backup_data``."""
        with batch_table_update(self.backup_table):
            self.backup_table.setRowCount(len(self._backup_data))
            actions_width = self.backup_table.horizontalHeader().sectionSizeHint(self.COL_ACTIONS)

            # Hoist LEGB locals
            table = self.backup_table
            set_item = table.setItem
            set_cell_widget = table.setCellWidget
            TableItem = QTableWidgetItem
            RelTimeItem = RelativeTimeTableWidgetItem
            num_align = NUMERIC_ALIGNMENT
            col_filename = self.COL_FILENAME
            col_date = self.COL_DATE
            col_size = self.COL_SIZE
            col_type = self.COL_TYPE
            col_actions = self.COL_ACTIONS
            type_keys = self._TYPE_KEYS
            make_actions = self._make_row_actions

            for row, b in enumerate(self._backup_data):
                set_item(row, col_filename, TableItem(b["filename"]))
                set_item(row, col_date, RelTimeItem(b["date"], fmt="%Y-%m-%d %H:%M:%S"))
                size_text = b["size"]

                if b.get("original_size"):
                    size_text = _t("data_safety.size_compressed_from", size=b["size"], original=b["original_size"])
                size_item = TableItem(size_text)
                size_item.setTextAlignment(num_align)
                set_item(row, col_size, size_item)
                kind = b.get("type") or ("snapshot" if b.get("is_pre_restore") else "manual")
                set_item(row, col_type, TableItem(_t(type_keys[kind])))
                actions = make_actions(row)
                set_cell_widget(row, col_actions, actions)
                actions_width = max(actions_width, actions.minimumWidth())
            # ResizeToContents ignores cell widgets, so size the column to the buttons
            table.setColumnWidth(col_actions, actions_width + 8)

    def _make_row_actions(self, row: int) -> QWidget:
        """Restore and Delete buttons for one backup row (#620)."""
        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(4, 2, 4, 2)
        cell_layout.setSpacing(6)
        btn_restore = QPushButton(_t("data_safety.btn_restore_row"))
        btn_restore.setObjectName("BackupRowRestore")
        btn_restore.setProperty("class", "secondary")
        btn_restore.clicked.connect(lambda _=False, r=row: self._restore_from_row(r))
        cell_layout.addWidget(btn_restore)
        btn_delete = QPushButton(_t("data_safety.btn_delete_backup"))
        btn_delete.setObjectName("BackupRowDelete")
        btn_delete.setProperty("class", "danger")
        btn_delete.clicked.connect(lambda _=False, r=row: self._delete_backup_row(r))
        cell_layout.addWidget(btn_delete)
        # Apply the QSS padding now so the column sizes to the real buttons
        for btn in (btn_restore, btn_delete):
            btn.ensurePolished()
            btn.setMinimumWidth(btn.sizeHint().width())
        cell.setMinimumWidth(cell.sizeHint().width())
        return cell

    def _restore_from_row(self, row: int) -> None:
        """Ask for this backup to be restored (the page opens the Restore tab)."""
        if row < 0 or row >= len(self._backup_data):
            return
        self.restore_requested.emit(self._backup_data[row]["path"])

    def _on_backup_list_error(self, message: str) -> None:
        self._overlay.hide_loading()
        logger.error("Failed to list backups: %s", message)

    def _change_backup_dir(self) -> None:
        current = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        chosen = QFileDialog.getExistingDirectory(self, _t("data_safety.restore_choose_folder"), current)
        if chosen:
            ConfigService.set("backup_dir", chosen)
            self.lbl_backup_dir.setText(chosen)
            self._refresh_backup_list()

    def _create_backup(self) -> None:
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.DATA_SAFETY_BACKUP, self):
            return

        password = ensure_backup_password(self)
        self._password_may_have_changed()
        if not password:
            return

        self.btn_create_backup.setEnabled(False)
        self._overlay.show_loading(_t("data_safety.backup_creating"))

        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        self._backup_worker = BackupWorker(backup_dir, password)
        self._backup_worker.result.connect(self._on_backup_finished)
        self._backup_worker.error.connect(self._on_backup_error)
        self._backup_worker.start()

    def _on_backup_finished(self, path: str) -> None:
        self._overlay.hide_loading()
        self.btn_create_backup.setEnabled(True)
        self.btn_create_backup.setText(_t("data_safety.btn_create_backup"))
        self._refresh_backup_list()
        QMessageBox.information(
            self,
            _t("data_safety.backup_complete_title"),
            _t("data_safety.backup_saved_to", path=path) + "\n\n" + _t("data_safety.backup_locked_with_shop_pwd"),
        )

    def _change_backup_password(self) -> None:
        """Set or change the shop backup password (affects new backups only)."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.DATA_SAFETY_BACKUP, self):
            return
        dialog = BackupPasswordDialog(self, changing=ConfigService.has_backup_password())
        dialog.exec()
        dialog.deleteLater()
        self._password_may_have_changed()

    def refresh_password_status(self) -> None:
        """Show whether a shop backup password is set, and what that means."""
        if ConfigService.has_backup_password():
            self.lbl_pwd_status.setText(_t("data_safety.pwd_status_set"))
            self.btn_backup_password.setText(_t("data_safety.btn_change_password"))
        else:
            self.lbl_pwd_status.setText(_t("data_safety.pwd_status_not_set"))
            self.btn_backup_password.setText(_t("data_safety.btn_set_password"))

    def _on_backup_error(self, error: str) -> None:
        self._overlay.hide_loading()
        self.btn_create_backup.setEnabled(True)
        self.btn_create_backup.setText(_t("data_safety.btn_create_backup"))
        QMessageBox.critical(
            self,
            _t("data_safety.backup_failed_title"),
            _t("data_safety.backup_failed_msg", error=error),
        )

    def _clean_old_backups(self) -> None:
        keep = ConfigService.get("backup_retention_count") or 5
        reply = QMessageBox.question(
            self,
            _t("data_safety.clean_title"),
            _t("data_safety.clean_msg", keep=keep),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        deleted = BackupService.cleanup_old_backups(backup_dir, keep)
        self._refresh_backup_list()
        QMessageBox.information(
            self,
            _t("data_safety.clean_done_title"),
            _t("data_safety.clean_done_msg", count=deleted),
        )

    def _show_backup_context_menu(self, position) -> None:
        """Right-click Restore/Delete for a row -- same as the row buttons (#620).

        Delete was the first per-row action (#341): before it, the only way
        to remove a backup was the bulk "Clean Old Backups" action, which
        excluded pre-restore snapshots, leaving no way to ever remove one."""
        row = self.backup_table.indexAt(position).row()
        if row < 0 or row >= len(self._backup_data):
            return
        self.backup_table.selectRow(row)

        menu = QMenu(self)
        restore_action = menu.addAction(_t("data_safety.btn_restore_row"))
        restore_action.triggered.connect(lambda: self._restore_from_row(row))
        delete_action = menu.addAction(_t("data_safety.btn_delete_backup"))
        delete_action.triggered.connect(lambda: self._delete_backup_row(row))
        menu.exec(self.backup_table.viewport().mapToGlobal(position))

    def _delete_backup_row(self, row: int) -> None:
        """Permanently delete a single backup file after confirmation."""
        if row < 0 or row >= len(self._backup_data):
            return
        backup = self._backup_data[row]

        reply = QMessageBox.warning(
            self,
            _t("data_safety.confirm_delete_backup_title"),
            _t("data_safety.confirm_delete_backup_msg", filename=backup["filename"]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if BackupService.delete_backup(backup["path"]):
            self._refresh_backup_list()
        else:
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("data_safety.delete_backup_failed_msg", filename=backup["filename"]),
            )

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.notice_card.retranslate_ui()
        self.lbl_dir_label.setText(_t("data_safety.backup_folder"))
        self.btn_change_dir.setText(_t("data_safety.btn_change"))
        self.backup_table.setHorizontalHeaderLabels(
            [
                _t("data_safety.backup_header_filename"),
                _t("data_safety.backup_header_date"),
                _t("data_safety.backup_header_size"),
                _t("data_safety.backup_header_type"),
                _t("data_safety.backup_header_actions"),
            ]
        )
        align_numeric_headers(self.backup_table, [self.COL_SIZE])
        self.btn_create_backup.setText(_t("data_safety.btn_create_backup"))
        self.btn_clean_old.setText(_t("data_safety.btn_clean_old"))
        self.btn_backup_refresh.setText(_t("data_safety.btn_refresh"))
        self.lbl_pwd_label.setText(_t("data_safety.pwd_label"))
        self.refresh_password_status()
        self._fill_backup_table()
        if self._last_status is not None:
            self._on_backup_status(self._last_status)
