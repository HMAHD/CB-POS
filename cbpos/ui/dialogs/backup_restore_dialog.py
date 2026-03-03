"""
Data Safety dialog — Backup, Restore, Maintenance, and Export tabs.

Provides a polished, tabbed interface for all data safety operations:
- Backup: list, create, clean old backups
- Restore: verify and restore from encrypted backup
- Maintenance: database info, VACUUM, integrity check
- Export: link to data export dialog
"""

import logging

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QGroupBox,
    QFormLayout,
    QFrame,
    QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor

from cbpos.core.services.backup_service import BackupService
from cbpos.core.services.config_service import ConfigService
from cbpos.ui.workers import BackupWorker, RestoreWorker

logger = logging.getLogger(__name__)


class BackupRestoreDialog(QDialog):
    """Tabbed dialog for backup, restore, maintenance, and export operations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Data Safety")
        self.setObjectName("BackupRestoreDialog")
        self.setMinimumSize(780, 560)
        self.resize(840, 600)
        self._init_ui()
        self._refresh_backup_list()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)

        # Title
        title = QLabel("Data Safety")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        subtitle = QLabel("Protect your business data with backups, restore, and maintenance tools.")
        subtitle.setObjectName("DialogSubtitle")
        layout.addWidget(subtitle)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_backup_tab(), "Backup")
        self.tabs.addTab(self._build_restore_tab(), "Restore")
        self.tabs.addTab(self._build_maintenance_tab(), "Maintenance")
        self.tabs.addTab(self._build_export_tab(), "Export Data")
        layout.addWidget(self.tabs, 1)

        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "secondary")
        btn_close.setFixedWidth(120)
        btn_close.clicked.connect(self.accept)
        close_layout.addWidget(btn_close)
        layout.addLayout(close_layout)

    # ── Backup Tab ────────────────────────────────────────────────────────

    def _build_backup_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(12)

        # Backup directory display
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(8)
        lbl_dir = QLabel("Backup Folder:")
        lbl_dir.setProperty("class", "muted")
        dir_layout.addWidget(lbl_dir)

        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        self.lbl_backup_dir = QLabel(backup_dir)
        self.lbl_backup_dir.setProperty("class", "value")
        self.lbl_backup_dir.setWordWrap(True)
        dir_layout.addWidget(self.lbl_backup_dir, 1)

        btn_change_dir = QPushButton("Change")
        btn_change_dir.setProperty("class", "secondary")
        btn_change_dir.setFixedWidth(80)
        btn_change_dir.clicked.connect(self._change_backup_dir)
        dir_layout.addWidget(btn_change_dir)
        layout.addLayout(dir_layout)

        # Backup list table
        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(4)
        self.backup_table.setHorizontalHeaderLabels(["Filename", "Date", "Size", "Type"])
        self.backup_table.setObjectName("BackupTable")
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
        layout.addWidget(self.backup_table, 1)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_create_backup = QPushButton("Create Backup Now")
        self.btn_create_backup.setProperty("class", "success")
        self.btn_create_backup.clicked.connect(self._create_backup)
        btn_layout.addWidget(self.btn_create_backup)

        self.btn_clean_old = QPushButton("Clean Old Backups")
        self.btn_clean_old.setProperty("class", "secondary")
        self.btn_clean_old.clicked.connect(self._clean_old_backups)
        btn_layout.addWidget(self.btn_clean_old)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("class", "secondary")
        btn_refresh.clicked.connect(self._refresh_backup_list)
        btn_layout.addWidget(btn_refresh)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return tab

    def _refresh_backup_list(self) -> None:
        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        backups = BackupService.list_backups(backup_dir)
        self.backup_table.setRowCount(len(backups))
        self._backup_data = backups

        for row, b in enumerate(backups):
            self.backup_table.setItem(row, 0, QTableWidgetItem(b["filename"]))
            self.backup_table.setItem(row, 1, QTableWidgetItem(b["date"]))
            self.backup_table.setItem(row, 2, QTableWidgetItem(b["size"]))
            type_text = "Pre-Restore" if b.get("is_pre_restore") else "Regular"
            self.backup_table.setItem(row, 3, QTableWidgetItem(type_text))

    def _change_backup_dir(self) -> None:
        current = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        chosen = QFileDialog.getExistingDirectory(self, "Choose Backup Folder", current)
        if chosen:
            ConfigService.set("backup_dir", chosen)
            self.lbl_backup_dir.setText(chosen)
            self._refresh_backup_list()

    def _create_backup(self) -> None:
        self.btn_create_backup.setEnabled(False)
        self.btn_create_backup.setText("Creating backup...")
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        self._backup_worker = BackupWorker(backup_dir)
        self._backup_worker.finished.connect(self._on_backup_finished)
        self._backup_worker.error.connect(self._on_backup_error)
        self._backup_worker.start()

    def _on_backup_finished(self, path: str, password: str) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_create_backup.setEnabled(True)
        self.btn_create_backup.setText("Create Backup Now")
        self._refresh_backup_list()

        # Secure password dialog with show/hide toggle and copy button
        dlg = QDialog(self)
        dlg.setWindowTitle("Backup Complete")
        dlg.setMinimumWidth(450)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(20, 20, 20, 20)
        dlg_layout.setSpacing(12)

        lbl_success = QLabel(f"Backup saved to:\n{path}")  # noqa: E231
        lbl_success.setWordWrap(True)
        dlg_layout.addWidget(lbl_success)

        lbl_pwd_info = QLabel("Keep this password safe \u2014 you need it to restore.")
        lbl_pwd_info.setProperty("class", "muted")
        lbl_pwd_info.setWordWrap(True)
        dlg_layout.addWidget(lbl_pwd_info)

        pwd_row = QHBoxLayout()
        pwd_input = QLineEdit(password)
        pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        pwd_input.setReadOnly(True)
        pwd_row.addWidget(pwd_input, 1)

        btn_toggle = QPushButton("Show")
        btn_toggle.setFixedWidth(60)

        def toggle_visibility() -> None:
            if pwd_input.echoMode() == QLineEdit.EchoMode.Password:
                pwd_input.setEchoMode(QLineEdit.EchoMode.Normal)
                btn_toggle.setText("Hide")
            else:
                pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
                btn_toggle.setText("Show")

        btn_toggle.clicked.connect(toggle_visibility)
        pwd_row.addWidget(btn_toggle)
        dlg_layout.addLayout(pwd_row)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Copy Password")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(password))
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_ok = QPushButton("OK")
        btn_ok.setProperty("class", "accent")
        btn_ok.setFixedWidth(80)
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_ok)
        dlg_layout.addLayout(btn_row)

        dlg.exec()

    def _on_backup_error(self, error: str) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_create_backup.setEnabled(True)
        self.btn_create_backup.setText("Create Backup Now")
        QMessageBox.critical(self, "Backup Failed", f"Could not create backup:\n{error}")  # noqa: E231

    def _clean_old_backups(self) -> None:
        keep = ConfigService.get("backup_retention_count") or 5
        reply = QMessageBox.question(
            self,
            "Clean Old Backups",
            f"This will delete all backups except the {keep} most recent.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        deleted = BackupService.cleanup_old_backups(backup_dir, keep)
        self._refresh_backup_list()
        QMessageBox.information(self, "Cleanup Done", f"Deleted {deleted} old backup(s).")

    # ── Restore Tab ───────────────────────────────────────────────────────

    def _build_restore_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        # Warning banner
        warning = QLabel(
            "Restoring a backup will replace your current database and settings.\n"
            "A safety snapshot will be created automatically before restoring."
        )
        warning.setObjectName("RestoreWarning")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        # File selection
        grp_file = QGroupBox("Select Backup File")
        grp_file.setProperty("class", "card")
        file_layout = QVBoxLayout(grp_file)

        file_row = QHBoxLayout()
        self.input_restore_path = QLineEdit()
        self.input_restore_path.setPlaceholderText("Choose a backup file (.zip)...")
        self.input_restore_path.setProperty("class", "dialog-input")
        self.input_restore_path.setReadOnly(True)
        file_row.addWidget(self.input_restore_path, 1)

        btn_browse = QPushButton("Browse")
        btn_browse.setProperty("class", "secondary")
        btn_browse.clicked.connect(self._browse_restore_file)
        file_row.addWidget(btn_browse)
        file_layout.addLayout(file_row)

        # Password
        pwd_row = QHBoxLayout()
        lbl_pwd = QLabel("Password:")
        lbl_pwd.setProperty("class", "muted")
        lbl_pwd.setFixedWidth(80)
        pwd_row.addWidget(lbl_pwd)
        self.input_restore_password = QLineEdit()
        self.input_restore_password.setPlaceholderText("Enter backup password...")
        self.input_restore_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_restore_password.setProperty("class", "dialog-input")
        pwd_row.addWidget(self.input_restore_password, 1)
        file_layout.addLayout(pwd_row)

        layout.addWidget(grp_file)

        # Verification result
        self.lbl_verify_result = QLabel("")
        self.lbl_verify_result.setWordWrap(True)
        self.lbl_verify_result.setProperty("class", "muted")
        layout.addWidget(self.lbl_verify_result)

        layout.addStretch()

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_verify = QPushButton("Verify Backup")
        self.btn_verify.setProperty("class", "primary")
        self.btn_verify.clicked.connect(self._verify_backup)
        btn_layout.addWidget(self.btn_verify)

        self.btn_restore = QPushButton("Restore Backup")
        self.btn_restore.setProperty("class", "danger")
        self.btn_restore.clicked.connect(self._restore_backup)
        btn_layout.addWidget(self.btn_restore)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return tab

    def _browse_restore_file(self) -> None:
        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        path, _ = QFileDialog.getOpenFileName(self, "Select Backup File", backup_dir, "Backup Files (*.zip)")
        if path:
            self.input_restore_path.setText(path)
            self.lbl_verify_result.setText("")

    def _verify_backup(self) -> None:
        path = self.input_restore_path.text().strip()
        password = self.input_restore_password.text()
        if not path:
            QMessageBox.warning(self, "No File", "Please select a backup file first.")
            return
        if not password:
            QMessageBox.warning(self, "No Password", "Please enter the backup password.")
            return

        result = BackupService.verify_backup(path, password)
        if result["valid"]:
            file_count = len(result["files"])
            self.lbl_verify_result.setProperty("class", "status-ok")
            self.lbl_verify_result.setText(f"Backup is valid. Size: {result['size']} | Files: {file_count}")
        else:
            self.lbl_verify_result.setProperty("class", "status-err")
            self.lbl_verify_result.setText(f"Verification failed: {result['error']}")

    def _restore_backup(self) -> None:
        path = self.input_restore_path.text().strip()
        password = self.input_restore_password.text()
        if not path:
            QMessageBox.warning(self, "No File", "Please select a backup file first.")
            return
        if not password:
            QMessageBox.warning(self, "No Password", "Please enter the backup password.")
            return

        reply = QMessageBox.warning(
            self,
            "Confirm Restore",
            "This will replace your current database with the backup.\n"
            "A safety snapshot will be saved first.\n\n"
            "The application will need to restart after restoring.\n\n"
            "Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_restore.setEnabled(False)
        self.btn_restore.setText("Restoring...")
        self.btn_verify.setEnabled(False)
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        self._restore_worker = RestoreWorker(path, password)
        self._restore_worker.finished.connect(self._on_restore_finished)
        self._restore_worker.error.connect(self._on_restore_error)
        self._restore_worker.start()

    def _on_restore_finished(self, success: bool) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_restore.setEnabled(True)
        self.btn_restore.setText("Restore Backup")
        self.btn_verify.setEnabled(True)

        if success:
            QMessageBox.information(
                self,
                "Restore Complete",
                "Backup has been restored successfully.\n\n"
                "Please restart the application for changes to take effect.",
            )
            # Close the dialog so the user can restart
            self.accept()
        else:
            QMessageBox.critical(self, "Restore Failed", "Restore did not complete successfully.")

    def _on_restore_error(self, error: str) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_restore.setEnabled(True)
        self.btn_restore.setText("Restore Backup")
        self.btn_verify.setEnabled(True)
        QMessageBox.critical(self, "Restore Failed", f"Could not restore backup:\n{error}")  # noqa: E231

    # ── Maintenance Tab ───────────────────────────────────────────────────

    def _build_maintenance_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        # Database info card
        grp_info = QGroupBox("Database Information")
        grp_info.setProperty("class", "card")
        info_layout = QFormLayout(grp_info)
        info_layout.setVerticalSpacing(10)
        info_layout.setHorizontalSpacing(20)

        self.lbl_db_size = QLabel("--")
        self.lbl_db_size.setProperty("class", "value")
        info_layout.addRow(self._info_label("Database Size:"), self.lbl_db_size)

        self.lbl_products_count = QLabel("--")
        self.lbl_products_count.setProperty("class", "value")
        info_layout.addRow(self._info_label("Products:"), self.lbl_products_count)

        self.lbl_customers_count = QLabel("--")
        self.lbl_customers_count.setProperty("class", "value")
        info_layout.addRow(self._info_label("Customers:"), self.lbl_customers_count)

        self.lbl_sales_count = QLabel("--")
        self.lbl_sales_count.setProperty("class", "value")
        info_layout.addRow(self._info_label("Sales:"), self.lbl_sales_count)

        layout.addWidget(grp_info)

        # Actions card
        grp_actions = QGroupBox("Maintenance Tools")
        grp_actions.setProperty("class", "card")
        actions_layout = QVBoxLayout(grp_actions)
        actions_layout.setSpacing(12)

        # Optimize row
        optimize_row = QHBoxLayout()
        optimize_info = QVBoxLayout()
        lbl_opt_title = QLabel("Optimize Database")
        lbl_opt_title.setProperty("class", "value")
        optimize_info.addWidget(lbl_opt_title)
        lbl_opt_desc = QLabel("Reclaims unused space and defragments the database file.")
        lbl_opt_desc.setProperty("class", "muted")
        lbl_opt_desc.setWordWrap(True)
        optimize_info.addWidget(lbl_opt_desc)
        optimize_row.addLayout(optimize_info, 1)

        self.btn_vacuum = QPushButton("Optimize")
        self.btn_vacuum.setProperty("class", "primary")
        self.btn_vacuum.setFixedWidth(140)
        self.btn_vacuum.clicked.connect(self._run_vacuum)
        optimize_row.addWidget(self.btn_vacuum)
        actions_layout.addLayout(optimize_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("Separator")
        sep.setFixedHeight(1)
        actions_layout.addWidget(sep)

        # Integrity check row
        integrity_row = QHBoxLayout()
        integrity_info = QVBoxLayout()
        lbl_int_title = QLabel("Check Integrity")
        lbl_int_title.setProperty("class", "value")
        integrity_info.addWidget(lbl_int_title)
        lbl_int_desc = QLabel("Verifies the database structure is healthy and not corrupted.")
        lbl_int_desc.setProperty("class", "muted")
        lbl_int_desc.setWordWrap(True)
        integrity_info.addWidget(lbl_int_desc)
        integrity_row.addLayout(integrity_info, 1)

        self.btn_integrity = QPushButton("Check")
        self.btn_integrity.setProperty("class", "secondary")
        self.btn_integrity.setFixedWidth(140)
        self.btn_integrity.clicked.connect(self._run_integrity_check)
        integrity_row.addWidget(self.btn_integrity)
        actions_layout.addLayout(integrity_row)

        self.lbl_maintenance_status = QLabel("")
        self.lbl_maintenance_status.setWordWrap(True)
        actions_layout.addWidget(self.lbl_maintenance_status)

        layout.addWidget(grp_actions)
        layout.addStretch()

        # Load DB info on first show
        self._load_db_info()

        return tab

    def _info_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("class", "muted")
        return lbl

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
        self.btn_vacuum.setText("Optimizing...")
        self.lbl_maintenance_status.setText("")
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        from cbpos.ui.workers import VacuumWorker

        self._vacuum_worker = VacuumWorker()
        self._vacuum_worker.finished.connect(self._on_vacuum_finished)
        self._vacuum_worker.error.connect(self._on_vacuum_error)
        self._vacuum_worker.start()

    def _on_vacuum_finished(self, result: dict) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_vacuum.setEnabled(True)
        self.btn_vacuum.setText("Optimize")
        saved = result.get("saved", "0 KB")
        self.lbl_maintenance_status.setProperty("class", "status-ok")
        self.lbl_maintenance_status.setText(f"Optimization complete. Space saved: {saved}")
        self._load_db_info()

    def _on_vacuum_error(self, error: str) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_vacuum.setEnabled(True)
        self.btn_vacuum.setText("Optimize")
        self.lbl_maintenance_status.setProperty("class", "status-err")
        self.lbl_maintenance_status.setText(f"Optimization failed: {error}")

    def _run_integrity_check(self) -> None:
        self.btn_integrity.setEnabled(False)
        self.btn_integrity.setText("Checking...")
        QApplication.processEvents()

        try:
            from cbpos.core.services.maintenance_service import MaintenanceService

            ok, message = MaintenanceService.integrity_check()
            if ok:
                self.lbl_maintenance_status.setProperty("class", "status-ok")
                self.lbl_maintenance_status.setText("Database integrity check passed.")
            else:
                self.lbl_maintenance_status.setProperty("class", "status-err")
                self.lbl_maintenance_status.setText(f"Integrity issues found: {message}")
        except Exception as e:
            self.lbl_maintenance_status.setProperty("class", "status-err")
            self.lbl_maintenance_status.setText(f"Check failed: {e}")
        finally:
            self.btn_integrity.setEnabled(True)
            self.btn_integrity.setText("Check")

    # ── Export Data Tab ───────────────────────────────────────────────────

    def _build_export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        # Info card
        grp_export = QGroupBox("Export Your Data")
        grp_export.setProperty("class", "card")
        export_layout = QVBoxLayout(grp_export)
        export_layout.setSpacing(12)

        desc = QLabel(
            "Export your business data to CSV, Excel, or PDF files.\n"
            "Useful for accounting, analysis, or sharing data with other systems."
        )
        desc.setProperty("class", "muted")
        desc.setWordWrap(True)
        export_layout.addWidget(desc)

        btn_open_export = QPushButton("Open Export Dialog")
        btn_open_export.setProperty("class", "primary")
        btn_open_export.setFixedWidth(200)
        btn_open_export.clicked.connect(self._open_export_dialog)
        export_layout.addWidget(btn_open_export)

        layout.addWidget(grp_export)
        layout.addStretch()

        return tab

    def _open_export_dialog(self) -> None:
        try:
            from cbpos.ui.dialogs.data_export_dialog import DataExportDialog

            dlg = DataExportDialog(self)
            dlg.exec()
        except Exception as e:
            logger.error("Could not open export dialog: %s", e)
            QMessageBox.critical(self, "Error", f"Could not open export dialog:\n{e}")  # noqa: E231
