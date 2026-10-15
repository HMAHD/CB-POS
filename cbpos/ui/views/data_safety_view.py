"""
Data Safety view — embedded in Settings view.

Provides a tabbed interface for all data safety operations:
- Backup: list, create, clean old backups
- Restore: verify and restore from encrypted backup
- Maintenance: database info, VACUUM, integrity check
- Export: link to data export dialog

Uses QSS objectNames and class properties for theme compatibility.
No hardcoded colors — works with both dark and light themes.
"""

import logging

from PyQt6.QtCore import Qt
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.backup_service import BackupService
from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.dialogs.backup_password_dialog import BackupPasswordDialog, ensure_backup_password
from cbpos.ui.views.data_safety.export_tab import ExportTabWidget
from cbpos.ui.views.data_safety.maintenance_tab import MaintenanceTabWidget
from cbpos.ui.views.data_safety.restore_tab import RestoreTabWidget
from cbpos.ui.widgets.loading_overlay import LoadingOverlay
from cbpos.ui.workers import (
    BackupListWorker,
    BackupWorker,
)

logger = logging.getLogger(__name__)


class DataSafetyView(QWidget):
    """Tabbed view for backup, restore, maintenance, and export operations."""

    # Backup table columns
    COL_FILENAME, COL_DATE, COL_SIZE, COL_TYPE, COL_ACTIONS = range(5)
    _TYPE_KEYS = {
        "manual": "data_safety.backup_type_manual",
        "auto": "data_safety.backup_type_auto",
        "snapshot": "data_safety.backup_type_snapshot",
    }

    def __init__(self) -> None:
        """Build the Backup, Restore, Maintenance, and Export tabs."""
        super().__init__()
        self._overlay = LoadingOverlay(self)
        self._init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def showEvent(self, event) -> None:
        """Refresh data when the view becomes visible."""
        super().showEvent(event)
        self._update_password_status()
        self._refresh_backup_list()
        self.maintenance_tab.refresh()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Title
        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "dialog-title")
        layout.addWidget(self.lbl_title)

        self.lbl_subtitle = QLabel()
        self.lbl_subtitle.setProperty("class", "muted")
        layout.addWidget(self.lbl_subtitle)

        # Tabs — let QSS handle tab styling
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_backup_tab(), "")
        self.restore_tab = RestoreTabWidget(self._overlay)
        self.restore_tab.password_changed.connect(self._update_password_status)
        self.tabs.addTab(self.restore_tab, "")
        self.maintenance_tab = MaintenanceTabWidget(self._overlay)
        self.tabs.addTab(self.maintenance_tab, "")
        self.export_tab = ExportTabWidget()
        self.tabs.addTab(self.export_tab, "")
        layout.addWidget(self.tabs, 1)

    # ── Backup Tab ────────────────────────────────────────────────────────

    def _build_backup_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(12)

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
        layout.addLayout(dir_layout)

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
        layout.addLayout(pwd_layout)

        # Newest backup and whether the shop password opens it (#619)
        self.lbl_last_backup = QLabel()
        self.lbl_last_backup.setObjectName("LastBackupStatus")
        self.lbl_last_backup.setWordWrap(True)
        self._last_status: dict | None = None
        layout.addWidget(self.lbl_last_backup)

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

        header = self.backup_table.horizontalHeader()
        header.setSectionResizeMode(self.COL_FILENAME, QHeaderView.ResizeMode.Stretch)
        for col in (self.COL_DATE, self.COL_SIZE, self.COL_TYPE):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.backup_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.backup_table.customContextMenuRequested.connect(self._show_backup_context_menu)
        layout.addWidget(self.backup_table, 1)

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
        layout.addLayout(btn_layout)

        return tab

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
        elif status.get("restorable"):
            text, css = _t("data_safety.last_backup_ok", date=status["date"]), "credit"
        else:
            text, css = _t("data_safety.last_backup_unverified", date=status["date"]), "debit"
        self.lbl_last_backup.setText(text)
        self.lbl_last_backup.setProperty("class", css)
        self.lbl_last_backup.style().unpolish(self.lbl_last_backup)
        self.lbl_last_backup.style().polish(self.lbl_last_backup)

    def _on_backup_list_loaded(self, backups: list) -> None:
        self._overlay.hide_loading()
        self._backup_data = backups

        self._fill_backup_table()

    def _fill_backup_table(self) -> None:
        """(Re)build the backup rows from ``self._backup_data``."""
        self.backup_table.setRowCount(len(self._backup_data))
        actions_width = self.backup_table.horizontalHeader().sectionSizeHint(self.COL_ACTIONS)
        for row, b in enumerate(self._backup_data):
            self.backup_table.setItem(row, self.COL_FILENAME, QTableWidgetItem(b["filename"]))
            self.backup_table.setItem(row, self.COL_DATE, QTableWidgetItem(b["date"]))
            size_text = b["size"]
            if b.get("original_size"):
                size_text = _t("data_safety.size_compressed_from", size=b["size"], original=b["original_size"])
            self.backup_table.setItem(row, self.COL_SIZE, QTableWidgetItem(size_text))
            kind = b.get("type") or ("snapshot" if b.get("is_pre_restore") else "manual")
            self.backup_table.setItem(row, self.COL_TYPE, QTableWidgetItem(_t(self._TYPE_KEYS[kind])))
            actions = self._make_row_actions(row)
            self.backup_table.setCellWidget(row, self.COL_ACTIONS, actions)
            actions_width = max(actions_width, actions.minimumWidth())
        # ResizeToContents ignores cell widgets, so size the column to the buttons
        self.backup_table.setColumnWidth(self.COL_ACTIONS, actions_width + 8)

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
        """Open the Restore tab with this backup's file filled in."""
        if row < 0 or row >= len(self._backup_data):
            return
        self.tabs.setCurrentWidget(self.restore_tab)
        self.restore_tab.load_backup(self._backup_data[row]["path"])

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
        self._update_password_status()
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
        self._update_password_status()

    def _update_password_status(self) -> None:
        """Show whether a shop backup password is set, and what that means."""
        if ConfigService.has_backup_password():
            self.lbl_pwd_status.setText(_t("data_safety.pwd_status_set"))
            self.btn_backup_password.setText(_t("data_safety.btn_change_password"))
        else:
            self.lbl_pwd_status.setText(_t("data_safety.pwd_status_not_set"))
            self.btn_backup_password.setText(_t("data_safety.btn_set_password"))
        self.restore_tab.refresh_password_hint()

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

    # ── Restore Tab ───────────────────────────────────────────────────────

    # ── Maintenance Tab ───────────────────────────────────────────────────

    # ── Export Data Tab ───────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.lbl_title.setText(_t("data_safety.title"))
        self.lbl_subtitle.setText(_t("data_safety.subtitle"))

        # Tab titles
        self.tabs.setTabText(0, _t("data_safety.tab_backup"))
        self.tabs.setTabText(1, _t("data_safety.tab_restore"))
        self.tabs.setTabText(2, _t("data_safety.tab_maintenance"))
        self.tabs.setTabText(3, _t("data_safety.tab_export"))

        # Backup tab
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
        self.btn_create_backup.setText(_t("data_safety.btn_create_backup"))
        self.btn_clean_old.setText(_t("data_safety.btn_clean_old"))
        self.btn_backup_refresh.setText(_t("data_safety.btn_refresh"))
        self.lbl_pwd_label.setText(_t("data_safety.pwd_label"))
        self._fill_backup_table()
        if self._last_status is not None:
            self._on_backup_status(self._last_status)

        self.restore_tab.retranslate_ui()

        self.maintenance_tab.retranslate_ui()

        self.export_tab.retranslate_ui()
