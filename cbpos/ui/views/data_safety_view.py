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
import weakref

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.dialogs.backup_password_dialog import BackupPasswordDialog, ensure_backup_password
from cbpos.ui.widgets.loading_overlay import LoadingOverlay
from cbpos.ui.workers import BackupListWorker, BackupWorker, RestoreWorker

logger = logging.getLogger(__name__)


class DataSafetyView(QWidget):
    """Tabbed view for backup, restore, maintenance, and export operations."""

    def __init__(self) -> None:
        """Build the Backup, Restore, Maintenance, and Export tabs."""
        super().__init__()
        self._init_ui()
        self._overlay = LoadingOverlay(self)
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        # weakref avoids a self -> destroyed-connection -> lambda -> self
        # reference cycle that only a full gc.collect() can break, which
        # can segfault mid-teardown (#392).
        self_ref = weakref.ref(self)

        def _unregister():
            view = self_ref()
            if view is not None:
                unregister_language_callback(view.retranslate_ui)

        self.destroyed.connect(_unregister)

    def showEvent(self, event) -> None:
        """Refresh data when the view becomes visible."""
        super().showEvent(event)
        self._update_password_status()
        self._refresh_backup_list()
        self._load_db_info()

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
        self.tabs.addTab(self._build_restore_tab(), "")
        self.tabs.addTab(self._build_maintenance_tab(), "")
        self.tabs.addTab(self._build_export_tab(), "")
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
        self.backup_table.setColumnCount(4)
        self.backup_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.backup_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.backup_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.backup_table.verticalHeader().setVisible(False)
        self.backup_table.setAlternatingRowColors(True)

        header = self.backup_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
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
        self.backup_table.setRowCount(len(backups))
        self._backup_data = backups

        for row, b in enumerate(backups):
            self.backup_table.setItem(row, 0, QTableWidgetItem(b["filename"]))
            self.backup_table.setItem(row, 1, QTableWidgetItem(b["date"]))
            self.backup_table.setItem(row, 2, QTableWidgetItem(b["size"]))
            type_text = (
                _t("data_safety.backup_type_pre_restore")
                if b.get("is_pre_restore")
                else _t("data_safety.backup_type_regular")
            )
            self.backup_table.setItem(row, 3, QTableWidgetItem(type_text))

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
            self.input_restore_password.setPlaceholderText(_t("data_safety.restore_pwd_placeholder_shop"))
        else:
            self.lbl_pwd_status.setText(_t("data_safety.pwd_status_not_set"))
            self.btn_backup_password.setText(_t("data_safety.btn_set_password"))
            self.input_restore_password.setPlaceholderText(_t("data_safety.restore_pwd_placeholder"))

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
        """Offer a per-row Delete action (#341) -- previously the only way
        to remove a backup was the bulk "Clean Old Backups" action, which
        explicitly excludes pre-restore snapshots, leaving no way in the
        app to ever remove one."""
        row = self.backup_table.indexAt(position).row()
        if row < 0 or row >= len(self._backup_data):
            return
        self.backup_table.selectRow(row)

        menu = QMenu(self)
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

    def _build_restore_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        # Warning banner — objectName for theme-specific warning styling
        self.lbl_restore_warning = QLabel()
        self.lbl_restore_warning.setObjectName("RestoreWarning")
        self.lbl_restore_warning.setWordWrap(True)
        layout.addWidget(self.lbl_restore_warning)

        # File selection
        self.grp_restore_file = QGroupBox()
        file_layout = QVBoxLayout(self.grp_restore_file)

        file_row = QHBoxLayout()
        self.input_restore_path = QLineEdit()
        self.input_restore_path.setReadOnly(True)
        file_row.addWidget(self.input_restore_path, 1)

        self.btn_browse = QPushButton()
        self.btn_browse.clicked.connect(self._browse_restore_file)
        file_row.addWidget(self.btn_browse)
        file_layout.addLayout(file_row)

        # Password
        pwd_row = QHBoxLayout()
        self.input_restore_password = QLineEdit()
        self.input_restore_password.setEchoMode(QLineEdit.EchoMode.Password)
        pwd_row.addWidget(self.input_restore_password, 1)

        self.btn_toggle_restore_pwd = QPushButton()
        self.btn_toggle_restore_pwd.setFixedWidth(80)
        self.btn_toggle_restore_pwd.clicked.connect(self._toggle_restore_password_visibility)
        pwd_row.addWidget(self.btn_toggle_restore_pwd)
        file_layout.addLayout(pwd_row)

        layout.addWidget(self.grp_restore_file)

        # Verification result
        self.lbl_verify_result = QLabel("")
        self.lbl_verify_result.setWordWrap(True)
        layout.addWidget(self.lbl_verify_result)

        layout.addStretch()

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_verify = QPushButton()
        self.btn_verify.setProperty("class", "accent")
        self.btn_verify.clicked.connect(self._verify_backup)
        btn_layout.addWidget(self.btn_verify)

        self.btn_restore = QPushButton()
        self.btn_restore.setProperty("class", "danger")
        self.btn_restore.clicked.connect(self._restore_backup)
        btn_layout.addWidget(self.btn_restore)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return tab

    def _browse_restore_file(self) -> None:
        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, _t("data_safety.restore_select_file"), backup_dir, "Backup Files (*.zip)"
        )
        if path:
            self.input_restore_path.setText(path)
            self.lbl_verify_result.setText("")

    def _restore_password(self) -> str:
        """The typed password, or the shop backup password when left empty.

        Older backups made with a per-backup password still restore with
        the password typed here.
        """
        return self.input_restore_password.text() or ConfigService.get_backup_password() or ""

    def _verify_backup(self) -> None:
        path = self.input_restore_path.text().strip()
        password = self._restore_password()
        if not path:
            QMessageBox.warning(
                self,
                _t("data_safety.restore_no_file_title"),
                _t("data_safety.restore_no_file_msg"),
            )
            return
        if not password:
            QMessageBox.warning(
                self,
                _t("data_safety.restore_no_pwd_title"),
                _t("data_safety.restore_no_pwd_msg"),
            )
            return

        result = BackupService.verify_backup(path, password)
        if result["valid"]:
            file_count = len(result["files"])
            self.lbl_verify_result.setProperty("class", "credit")
            self.lbl_verify_result.setText(_t("data_safety.restore_valid", size=result["size"], count=file_count))
        else:
            self.lbl_verify_result.setProperty("class", "debit")
            self.lbl_verify_result.setText(_t("data_safety.restore_invalid", error=result["error"]))
        # Force style refresh after property change
        self.lbl_verify_result.style().unpolish(self.lbl_verify_result)
        self.lbl_verify_result.style().polish(self.lbl_verify_result)

    def _restore_backup(self) -> None:
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.DATA_SAFETY_RESTORE, self):
            return

        path = self.input_restore_path.text().strip()
        password = self._restore_password()
        if not path:
            QMessageBox.warning(
                self,
                _t("data_safety.restore_no_file_title"),
                _t("data_safety.restore_no_file_msg"),
            )
            return
        if not password:
            QMessageBox.warning(
                self,
                _t("data_safety.restore_no_pwd_title"),
                _t("data_safety.restore_no_pwd_msg"),
            )
            return

        reply = QMessageBox.warning(
            self,
            _t("data_safety.restore_confirm_title"),
            _t("data_safety.restore_confirm_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_restore.setEnabled(False)
        self.btn_verify.setEnabled(False)
        self._overlay.show_loading(_t("data_safety.restore_restoring"))

        self._restore_worker = RestoreWorker(path, password)
        self._restore_worker.result.connect(self._on_restore_finished)
        self._restore_worker.error.connect(self._on_restore_error)
        self._restore_worker.start()

    def _on_restore_finished(self, success: bool) -> None:
        self._overlay.hide_loading()
        self.btn_restore.setEnabled(True)
        self.btn_restore.setText(_t("data_safety.btn_restore"))
        self.btn_verify.setEnabled(True)

        if success:
            QMessageBox.information(
                self,
                _t("data_safety.restore_complete_title"),
                _t("data_safety.restore_complete_msg"),
            )
        else:
            QMessageBox.critical(
                self,
                _t("data_safety.restore_failed_title"),
                _t("data_safety.restore_failed_msg"),
            )

    def _on_restore_error(self, error: str) -> None:
        self._overlay.hide_loading()
        self.btn_restore.setEnabled(True)
        self.btn_restore.setText(_t("data_safety.btn_restore"))
        self.btn_verify.setEnabled(True)
        QMessageBox.critical(
            self,
            _t("data_safety.restore_failed_title"),
            _t("data_safety.restore_failed_error_msg", error=error),
        )

    def _toggle_restore_password_visibility(self) -> None:
        """Toggle visibility of the restore password input."""
        if self.input_restore_password.echoMode() == QLineEdit.EchoMode.Password:
            self.input_restore_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_restore_pwd.setText(_t("data_safety.btn_hide"))
        else:
            self.input_restore_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_restore_pwd.setText(_t("data_safety.btn_show"))

    # ── Maintenance Tab ───────────────────────────────────────────────────

    def _build_maintenance_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        # Database info card
        self.grp_info = QGroupBox()
        info_layout = QFormLayout(self.grp_info)
        info_layout.setVerticalSpacing(10)
        info_layout.setHorizontalSpacing(20)

        self.lbl_db_size = QLabel("--")
        self.lbl_db_size.setProperty("class", "bold")
        self.lbl_db_size_label = QLabel()
        info_layout.addRow(self.lbl_db_size_label, self.lbl_db_size)

        self.lbl_products_count = QLabel("--")
        self.lbl_products_count.setProperty("class", "bold")
        self.lbl_products_label = QLabel()
        info_layout.addRow(self.lbl_products_label, self.lbl_products_count)

        self.lbl_customers_count = QLabel("--")
        self.lbl_customers_count.setProperty("class", "bold")
        self.lbl_customers_label = QLabel()
        info_layout.addRow(self.lbl_customers_label, self.lbl_customers_count)

        self.lbl_sales_count = QLabel("--")
        self.lbl_sales_count.setProperty("class", "bold")
        self.lbl_sales_label = QLabel()
        info_layout.addRow(self.lbl_sales_label, self.lbl_sales_count)

        layout.addWidget(self.grp_info)

        # Actions card
        self.grp_actions = QGroupBox()
        actions_layout = QVBoxLayout(self.grp_actions)
        actions_layout.setSpacing(12)

        # Optimize row
        optimize_row = QHBoxLayout()
        optimize_info = QVBoxLayout()
        self.lbl_opt_title = QLabel()
        self.lbl_opt_title.setProperty("class", "bold")
        optimize_info.addWidget(self.lbl_opt_title)
        self.lbl_opt_desc = QLabel()
        self.lbl_opt_desc.setProperty("class", "muted")
        self.lbl_opt_desc.setWordWrap(True)
        optimize_info.addWidget(self.lbl_opt_desc)
        optimize_row.addLayout(optimize_info, 1)

        self.btn_vacuum = QPushButton()
        # Optimize and Check are equivalent maintenance actions -> same
        # (secondary) emphasis, neither is the screen's primary action.
        self.btn_vacuum.setProperty("class", "secondary")
        self.btn_vacuum.setFixedWidth(140)
        self.btn_vacuum.clicked.connect(self._run_vacuum)
        optimize_row.addWidget(self.btn_vacuum)
        actions_layout.addLayout(optimize_row)

        # Separator — let QSS style QFrame HLine
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        actions_layout.addWidget(sep)

        # Integrity check row
        integrity_row = QHBoxLayout()
        integrity_info = QVBoxLayout()
        self.lbl_int_title = QLabel()
        self.lbl_int_title.setProperty("class", "bold")
        integrity_info.addWidget(self.lbl_int_title)
        self.lbl_int_desc = QLabel()
        self.lbl_int_desc.setProperty("class", "muted")
        self.lbl_int_desc.setWordWrap(True)
        integrity_info.addWidget(self.lbl_int_desc)
        integrity_row.addLayout(integrity_info, 1)

        self.btn_integrity = QPushButton()
        self.btn_integrity.setProperty("class", "secondary")
        self.btn_integrity.setFixedWidth(140)
        self.btn_integrity.clicked.connect(self._run_integrity_check)
        integrity_row.addWidget(self.btn_integrity)
        actions_layout.addLayout(integrity_row)

        self.lbl_maintenance_status = QLabel("")
        self.lbl_maintenance_status.setWordWrap(True)
        actions_layout.addWidget(self.lbl_maintenance_status)

        layout.addWidget(self.grp_actions)
        layout.addStretch()

        return tab

    def _load_db_info(self) -> None:
        try:
            from cbpos.core.services.maintenance_service import MaintenanceService

            info = MaintenanceService.get_database_info()
            self.lbl_db_size.setText(info.get("size", "--"))
            self.lbl_products_count.setText(str(info.get("products", 0)))
            self.lbl_customers_count.setText(str(info.get("customers", 0)))
            self.lbl_sales_count.setText(str(info.get("sales", 0)))
        except Exception as e:
            logger.warning("Could not load DB info: %s", e)

    def _run_vacuum(self) -> None:
        self.btn_vacuum.setEnabled(False)
        self.lbl_maintenance_status.setText("")
        self._overlay.show_loading(_t("data_safety.maintenance_optimizing"))

        from cbpos.ui.workers import VacuumWorker

        self._vacuum_worker = VacuumWorker()
        self._vacuum_worker.result.connect(self._on_vacuum_finished)
        self._vacuum_worker.error.connect(self._on_vacuum_error)
        self._vacuum_worker.start()

    def _on_vacuum_finished(self, result: dict) -> None:
        self._overlay.hide_loading()
        self.btn_vacuum.setEnabled(True)
        self.btn_vacuum.setText(_t("data_safety.maintenance_btn_optimize"))
        saved = result.get("saved", "0 KB")
        self.lbl_maintenance_status.setProperty("class", "credit")
        self.lbl_maintenance_status.style().unpolish(self.lbl_maintenance_status)
        self.lbl_maintenance_status.style().polish(self.lbl_maintenance_status)
        self.lbl_maintenance_status.setText(_t("data_safety.maintenance_optimize_complete", saved=saved))
        self._load_db_info()

    def _on_vacuum_error(self, error: str) -> None:
        self._overlay.hide_loading()
        self.btn_vacuum.setEnabled(True)
        self.btn_vacuum.setText(_t("data_safety.maintenance_btn_optimize"))
        self.lbl_maintenance_status.setProperty("class", "debit")
        self.lbl_maintenance_status.style().unpolish(self.lbl_maintenance_status)
        self.lbl_maintenance_status.style().polish(self.lbl_maintenance_status)
        self.lbl_maintenance_status.setText(_t("data_safety.maintenance_optimize_failed", error=error))

    def _run_integrity_check(self) -> None:
        self.btn_integrity.setEnabled(False)
        self.lbl_maintenance_status.setText("")
        self._overlay.show_loading(_t("data_safety.maintenance_checking"))

        from cbpos.ui.workers import IntegrityCheckWorker

        self._integrity_worker = IntegrityCheckWorker()
        self._integrity_worker.result.connect(self._on_integrity_finished)
        self._integrity_worker.start()

    def _on_integrity_finished(self, ok: bool, message: str) -> None:
        self._overlay.hide_loading()
        self.btn_integrity.setEnabled(True)
        self.btn_integrity.setText(_t("data_safety.maintenance_btn_check"))
        if ok:
            self.lbl_maintenance_status.setProperty("class", "credit")
            self.lbl_maintenance_status.setText(_t("data_safety.maintenance_integrity_passed"))
        else:
            self.lbl_maintenance_status.setProperty("class", "debit")
            self.lbl_maintenance_status.setText(_t("data_safety.maintenance_integrity_failed", message=message))
        self.lbl_maintenance_status.style().unpolish(self.lbl_maintenance_status)
        self.lbl_maintenance_status.style().polish(self.lbl_maintenance_status)

    # ── Export Data Tab ───────────────────────────────────────────────────

    def _build_export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        self.lbl_export_desc = QLabel()
        self.lbl_export_desc.setProperty("class", "muted")
        self.lbl_export_desc.setWordWrap(True)
        layout.addWidget(self.lbl_export_desc)

        # Data type selection
        self.grp_data = QGroupBox()
        data_layout = QHBoxLayout(self.grp_data)
        data_layout.setSpacing(12)
        self.lbl_export_label = QLabel()
        data_layout.addWidget(self.lbl_export_label)
        self.cmb_export_data = QComboBox()
        self.cmb_export_data.setFixedWidth(200)
        self.cmb_export_data.currentTextChanged.connect(self._on_export_data_changed)
        data_layout.addWidget(self.cmb_export_data)
        data_layout.addStretch()
        layout.addWidget(self.grp_data)

        # Format selection
        self.grp_format = QGroupBox()
        fmt_layout = QHBoxLayout(self.grp_format)
        fmt_layout.setSpacing(12)
        self.lbl_fmt_label = QLabel()
        fmt_layout.addWidget(self.lbl_fmt_label)
        self.cmb_export_format = QComboBox()
        self.cmb_export_format.setFixedWidth(200)
        fmt_layout.addWidget(self.cmb_export_format)
        fmt_layout.addStretch()
        layout.addWidget(self.grp_format)

        # Date range (visible only for Sales)
        self.grp_export_dates = QGroupBox()
        dates_layout = QHBoxLayout(self.grp_export_dates)
        dates_layout.setSpacing(12)
        self.lbl_export_from = QLabel()
        dates_layout.addWidget(self.lbl_export_from)
        self.date_export_from = QDateEdit()
        self.date_export_from.setCalendarPopup(True)
        self.date_export_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_export_from.setDisplayFormat("yyyy-MM-dd")
        self.date_export_from.setFixedWidth(150)
        dates_layout.addWidget(self.date_export_from)
        self.lbl_export_to = QLabel()
        dates_layout.addWidget(self.lbl_export_to)
        self.date_export_to = QDateEdit()
        self.date_export_to.setCalendarPopup(True)
        self.date_export_to.setDate(QDate.currentDate())
        self.date_export_to.setDisplayFormat("yyyy-MM-dd")
        self.date_export_to.setFixedWidth(150)
        dates_layout.addWidget(self.date_export_to)
        dates_layout.addStretch()
        layout.addWidget(self.grp_export_dates)
        # Show date range only for Sales
        self.grp_export_dates.setVisible(False)

        layout.addStretch()

        # Export button and status
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_do_export = QPushButton()
        self.btn_do_export.setProperty("class", "accent")
        self.btn_do_export.setFixedWidth(140)
        self.btn_do_export.clicked.connect(self._do_inline_export)
        btn_row.addWidget(self.btn_do_export)

        self.lbl_export_status = QLabel("")
        self.lbl_export_status.setWordWrap(True)
        btn_row.addWidget(self.lbl_export_status, 1)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        return tab

    def _on_export_data_changed(self, text: str) -> None:
        """Show/hide date range based on selected data type."""
        self.grp_export_dates.setVisible(text == _t("data_safety.export_type_sales"))

    def _do_inline_export(self) -> None:
        """Export selected data type in the chosen format using a background thread."""
        from datetime import datetime
        from pathlib import Path

        from cbpos.core.services.data_export_service import DataExportService
        from cbpos.core.services.export_service import ExportService
        from cbpos.ui.workers import ExportWorker

        # Validate date range for Sales export
        data_type = self.cmb_export_data.currentText()
        if data_type == _t("data_safety.export_type_sales"):
            start = self.date_export_from.date()
            end = self.date_export_to.date()
            if start > end:
                QMessageBox.warning(
                    self,
                    _t("data_safety.export_invalid_date_title"),
                    _t("data_safety.export_invalid_date_msg"),
                )
                return

        # Ask for output directory
        default_dir = str(Path.home() / "Documents")
        output_dir = QFileDialog.getExistingDirectory(self, _t("data_safety.export_choose_folder"), default_dir)
        if not output_dir:
            return

        self.btn_do_export.setEnabled(False)
        self.btn_do_export.setText(_t("data_safety.export_exporting"))
        self.lbl_export_status.setText("")

        data_type = self.cmb_export_data.currentText()
        fmt_text = self.cmb_export_format.currentText()

        if fmt_text == _t("data_safety.export_format_excel"):
            ext = ".xlsx"
            fmt = "excel"
        else:
            ext = ".csv"
            fmt = "csv"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            if data_type == _t("data_safety.export_type_products"):
                df = DataExportService.get_products_dataframe()
                filepath = f"{output_dir}/products_{timestamp}{ext}"
                title = "Products"
            elif data_type == _t("data_safety.export_type_customers"):
                df = DataExportService.get_customers_dataframe()
                filepath = f"{output_dir}/customers_{timestamp}{ext}"
                title = "Customers"
            else:
                start = self.date_export_from.date().toPyDate()
                end = self.date_export_to.date().toPyDate()
                start_dt = datetime(start.year, start.month, start.day, 0, 0, 0)
                end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)
                df = DataExportService.get_sales_dataframe(start_dt, end_dt)
                filepath = f"{output_dir}/sales_{timestamp}{ext}"
                title = "Sales"
        except Exception as e:
            logger.exception("Export data fetch failed: %s", e)
            self.btn_do_export.setEnabled(True)
            self.btn_do_export.setText(_t("data_safety.export_btn"))
            self._set_export_status("debit", _t("data_safety.export_failed", error=e))
            return

        self._export_filepath = filepath
        self._export_data_type = data_type
        self._export_row_count = len(df)

        self._export_worker = ExportWorker(ExportService(), df, filepath, title, fmt)
        self._export_worker.result.connect(self._on_export_finished)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.start()

    def _on_export_finished(self, _msg: str) -> None:
        """Handle successful export from background thread."""
        self.btn_do_export.setEnabled(True)
        self.btn_do_export.setText(_t("data_safety.export_btn"))
        data_type = getattr(self, "_export_data_type", "")
        row_count = getattr(self, "_export_row_count", 0)
        filepath = getattr(self, "_export_filepath", "")
        self._set_export_status(
            "credit",
            _t(
                "data_safety.export_success",
                count=row_count,
                type=data_type.lower(),
                path=filepath,
            ),
        )

    def _on_export_error(self, error: str) -> None:
        """Handle export failure from background thread."""
        self.btn_do_export.setEnabled(True)
        self.btn_do_export.setText(_t("data_safety.export_btn"))
        self._set_export_status("debit", _t("data_safety.export_failed", error=error))

    def _set_export_status(self, css_class: str, text: str) -> None:
        """Update the export status label with the given class and text."""
        self.lbl_export_status.setProperty("class", css_class)
        self.lbl_export_status.setText(text)
        self.lbl_export_status.style().unpolish(self.lbl_export_status)
        self.lbl_export_status.style().polish(self.lbl_export_status)

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
            ]
        )
        self.btn_create_backup.setText(_t("data_safety.btn_create_backup"))
        self.btn_clean_old.setText(_t("data_safety.btn_clean_old"))
        self.btn_backup_refresh.setText(_t("data_safety.btn_refresh"))
        self.lbl_pwd_label.setText(_t("data_safety.pwd_label"))
        if self._last_status is not None:
            self._on_backup_status(self._last_status)

        # Restore tab
        self.lbl_restore_warning.setText(_t("data_safety.restore_warning_full"))
        self.grp_restore_file.setTitle(_t("data_safety.restore_file_group"))
        self.input_restore_path.setPlaceholderText(_t("data_safety.restore_file_placeholder"))
        self.btn_browse.setText(_t("data_safety.btn_browse"))
        self._update_password_status()
        self.btn_toggle_restore_pwd.setText(_t("data_safety.btn_show"))
        self.btn_verify.setText(_t("data_safety.btn_verify"))
        self.btn_restore.setText(_t("data_safety.btn_restore"))

        # Maintenance tab
        self.grp_info.setTitle(_t("data_safety.maintenance_group_info"))
        self.lbl_db_size_label.setText(_t("data_safety.maintenance_db_size"))
        self.lbl_products_label.setText(_t("data_safety.maintenance_products"))
        self.lbl_customers_label.setText(_t("data_safety.maintenance_customers"))
        self.lbl_sales_label.setText(_t("data_safety.maintenance_sales"))
        self.grp_actions.setTitle(_t("data_safety.maintenance_group_tools"))
        self.lbl_opt_title.setText(_t("data_safety.maintenance_optimize_title"))
        self.lbl_opt_desc.setText(_t("data_safety.maintenance_optimize_desc"))
        self.btn_vacuum.setText(_t("data_safety.maintenance_btn_optimize"))
        self.lbl_int_title.setText(_t("data_safety.maintenance_integrity_title"))
        self.lbl_int_desc.setText(_t("data_safety.maintenance_integrity_desc"))
        self.btn_integrity.setText(_t("data_safety.maintenance_btn_check"))

        # Export tab
        self.lbl_export_desc.setText(_t("data_safety.export_desc"))
        self.grp_data.setTitle(_t("data_safety.export_data_type"))
        self.lbl_export_label.setText(_t("data_safety.export_label"))
        self.cmb_export_data.clear()
        self.cmb_export_data.addItems(
            [
                _t("data_safety.export_type_products"),
                _t("data_safety.export_type_customers"),
                _t("data_safety.export_type_sales"),
            ]
        )
        self.grp_format.setTitle(_t("data_safety.export_format"))
        self.lbl_fmt_label.setText(_t("data_safety.export_format_label"))
        self.cmb_export_format.clear()
        self.cmb_export_format.addItems(
            [
                _t("data_safety.export_format_excel"),
                _t("data_safety.export_format_csv"),
            ]
        )
        self.grp_export_dates.setTitle(_t("data_safety.export_date_range_hint"))
        self.lbl_export_from.setText(_t("data_safety.export_from"))
        self.lbl_export_to.setText(_t("data_safety.export_to"))
        self.btn_do_export.setText(_t("data_safety.export_btn"))
