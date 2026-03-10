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
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class BackupRestoreDialog(QDialog):
    """Tabbed dialog for backup, restore, maintenance, and export operations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("data_safety.title"))
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
        title = QLabel(_t("data_safety.title"))
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        subtitle = QLabel(_t("data_safety.subtitle"))
        subtitle.setObjectName("DialogSubtitle")
        layout.addWidget(subtitle)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_backup_tab(), _t("data_safety.tab_backup"))
        self.tabs.addTab(self._build_restore_tab(), _t("data_safety.tab_restore"))
        self.tabs.addTab(self._build_maintenance_tab(), _t("data_safety.tab_maintenance"))
        self.tabs.addTab(self._build_export_tab(), _t("data_safety.tab_export"))
        layout.addWidget(self.tabs, 1)

        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        btn_close = QPushButton(_t("common.close"))
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
        lbl_dir = QLabel(_t("data_safety.backup_folder"))
        lbl_dir.setProperty("class", "muted")
        dir_layout.addWidget(lbl_dir)

        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        self.lbl_backup_dir = QLabel(backup_dir)
        self.lbl_backup_dir.setProperty("class", "value")
        self.lbl_backup_dir.setWordWrap(True)
        dir_layout.addWidget(self.lbl_backup_dir, 1)

        btn_change_dir = QPushButton(_t("data_safety.btn_change"))
        btn_change_dir.setProperty("class", "secondary")
        btn_change_dir.setFixedWidth(80)
        btn_change_dir.clicked.connect(self._change_backup_dir)
        dir_layout.addWidget(btn_change_dir)
        layout.addLayout(dir_layout)

        # Backup list table
        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(4)
        self.backup_table.setHorizontalHeaderLabels(
            [
                _t("data_safety.backup_header_filename"),
                _t("data_safety.backup_header_date"),
                _t("data_safety.backup_header_size"),
                _t("data_safety.backup_header_type"),
            ]
        )
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

        self.btn_create_backup = QPushButton(_t("data_safety.btn_create_backup"))
        self.btn_create_backup.setProperty("class", "success")
        self.btn_create_backup.clicked.connect(self._create_backup)
        btn_layout.addWidget(self.btn_create_backup)

        self.btn_clean_old = QPushButton(_t("data_safety.btn_clean_old"))
        self.btn_clean_old.setProperty("class", "secondary")
        self.btn_clean_old.clicked.connect(self._clean_old_backups)
        btn_layout.addWidget(self.btn_clean_old)

        btn_refresh = QPushButton(_t("data_safety.btn_refresh"))
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
            type_text = (
                _t("data_safety.backup_type_pre_restore")
                if b.get("is_pre_restore")
                else _t("data_safety.backup_type_regular")
            )
            self.backup_table.setItem(row, 3, QTableWidgetItem(type_text))

    def _change_backup_dir(self) -> None:
        current = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        chosen = QFileDialog.getExistingDirectory(self, _t("data_safety.restore_choose_folder"), current)
        if chosen:
            ConfigService.set("backup_dir", chosen)
            self.lbl_backup_dir.setText(chosen)
            self._refresh_backup_list()

    def _create_backup(self) -> None:
        self.btn_create_backup.setEnabled(False)
        self.btn_create_backup.setText(_t("data_safety.backup_creating"))
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
        self._backup_worker = BackupWorker(backup_dir)
        self._backup_worker.finished.connect(self._on_backup_finished)
        self._backup_worker.error.connect(self._on_backup_error)
        self._backup_worker.start()

    def _on_backup_finished(self, path: str, password: str) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_create_backup.setEnabled(True)
        self.btn_create_backup.setText(_t("data_safety.btn_create_backup"))
        self._refresh_backup_list()

        # Secure password dialog with show/hide toggle and copy button
        dlg = QDialog(self)
        dlg.setWindowTitle(_t("data_safety.backup_complete_title"))
        dlg.setMinimumWidth(450)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(20, 20, 20, 20)
        dlg_layout.setSpacing(12)

        lbl_success = QLabel(_t("data_safety.backup_saved_to", path=path))
        lbl_success.setWordWrap(True)
        dlg_layout.addWidget(lbl_success)

        lbl_pwd_info = QLabel(_t("data_safety.backup_pwd_info"))
        lbl_pwd_info.setProperty("class", "muted")
        lbl_pwd_info.setWordWrap(True)
        dlg_layout.addWidget(lbl_pwd_info)

        pwd_row = QHBoxLayout()
        pwd_input = QLineEdit(password)
        pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        pwd_input.setReadOnly(True)
        pwd_row.addWidget(pwd_input, 1)

        btn_toggle = QPushButton(_t("data_safety.btn_show"))
        btn_toggle.setFixedWidth(60)

        def toggle_visibility() -> None:
            if pwd_input.echoMode() == QLineEdit.EchoMode.Password:
                pwd_input.setEchoMode(QLineEdit.EchoMode.Normal)
                btn_toggle.setText(_t("data_safety.btn_hide"))
            else:
                pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
                btn_toggle.setText(_t("data_safety.btn_show"))

        btn_toggle.clicked.connect(toggle_visibility)
        pwd_row.addWidget(btn_toggle)
        dlg_layout.addLayout(pwd_row)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton(_t("data_safety.btn_copy_password"))
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(password))
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_ok = QPushButton(_t("common.ok"))
        btn_ok.setProperty("class", "accent")
        btn_ok.setFixedWidth(80)
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_ok)
        dlg_layout.addLayout(btn_row)

        dlg.exec()

    def _on_backup_error(self, error: str) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_create_backup.setEnabled(True)
        self.btn_create_backup.setText(_t("data_safety.btn_create_backup"))
        QMessageBox.critical(
            self, _t("data_safety.backup_failed_title"), _t("data_safety.backup_failed_msg", error=error)
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
            self, _t("data_safety.clean_done_title"), _t("data_safety.clean_done_msg", count=deleted)
        )

    # ── Restore Tab ───────────────────────────────────────────────────────

    def _build_restore_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        # Warning banner
        warning = QLabel(_t("data_safety.restore_warning_full"))
        warning.setObjectName("RestoreWarning")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        # File selection
        grp_file = QGroupBox(_t("data_safety.restore_file_group"))
        grp_file.setProperty("class", "card")
        file_layout = QVBoxLayout(grp_file)

        file_row = QHBoxLayout()
        self.input_restore_path = QLineEdit()
        self.input_restore_path.setPlaceholderText(_t("data_safety.restore_file_placeholder"))
        self.input_restore_path.setProperty("class", "dialog-input")
        self.input_restore_path.setReadOnly(True)
        file_row.addWidget(self.input_restore_path, 1)

        btn_browse = QPushButton(_t("common.browse"))
        btn_browse.setProperty("class", "secondary")
        btn_browse.clicked.connect(self._browse_restore_file)
        file_row.addWidget(btn_browse)
        file_layout.addLayout(file_row)

        # Password
        pwd_row = QHBoxLayout()
        lbl_pwd = QLabel(_t("data_safety.restore_pwd_label"))
        lbl_pwd.setProperty("class", "muted")
        lbl_pwd.setFixedWidth(80)
        pwd_row.addWidget(lbl_pwd)
        self.input_restore_password = QLineEdit()
        self.input_restore_password.setPlaceholderText(_t("data_safety.restore_pwd_placeholder"))
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

        self.btn_verify = QPushButton(_t("data_safety.btn_verify"))
        self.btn_verify.setProperty("class", "primary")
        self.btn_verify.clicked.connect(self._verify_backup)
        btn_layout.addWidget(self.btn_verify)

        self.btn_restore = QPushButton(_t("data_safety.btn_restore"))
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

    def _verify_backup(self) -> None:
        path = self.input_restore_path.text().strip()
        password = self.input_restore_password.text()
        if not path:
            QMessageBox.warning(self, _t("data_safety.restore_no_file_title"), _t("data_safety.restore_no_file_msg"))
            return
        if not password:
            QMessageBox.warning(self, _t("data_safety.restore_no_pwd_title"), _t("data_safety.restore_no_pwd_msg"))
            return

        result = BackupService.verify_backup(path, password)
        if result["valid"]:
            file_count = len(result["files"])
            self.lbl_verify_result.setProperty("class", "status-ok")
            self.lbl_verify_result.setText(_t("data_safety.restore_valid", size=result["size"], count=file_count))
        else:
            self.lbl_verify_result.setProperty("class", "status-err")
            self.lbl_verify_result.setText(_t("data_safety.restore_invalid", error=result["error"]))

    def _restore_backup(self) -> None:
        path = self.input_restore_path.text().strip()
        password = self.input_restore_password.text()
        if not path:
            QMessageBox.warning(self, _t("data_safety.restore_no_file_title"), _t("data_safety.restore_no_file_msg"))
            return
        if not password:
            QMessageBox.warning(self, _t("data_safety.restore_no_pwd_title"), _t("data_safety.restore_no_pwd_msg"))
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
        self.btn_restore.setText(_t("data_safety.restore_restoring"))
        self.btn_verify.setEnabled(False)
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        self._restore_worker = RestoreWorker(path, password)
        self._restore_worker.finished.connect(self._on_restore_finished)
        self._restore_worker.error.connect(self._on_restore_error)
        self._restore_worker.start()

    def _on_restore_finished(self, success: bool) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_restore.setEnabled(True)
        self.btn_restore.setText(_t("data_safety.btn_restore"))
        self.btn_verify.setEnabled(True)

        if success:
            QMessageBox.information(
                self,
                _t("data_safety.restore_complete_title"),
                _t("data_safety.restore_complete_msg"),
            )
            # Close the dialog so the user can restart
            self.accept()
        else:
            QMessageBox.critical(self, _t("data_safety.restore_failed_title"), _t("data_safety.restore_failed_msg"))

    def _on_restore_error(self, error: str) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_restore.setEnabled(True)
        self.btn_restore.setText(_t("data_safety.btn_restore"))
        self.btn_verify.setEnabled(True)
        QMessageBox.critical(
            self, _t("data_safety.restore_failed_title"), _t("data_safety.restore_failed_error_msg", error=error)
        )

    # ── Maintenance Tab ───────────────────────────────────────────────────

    def _build_maintenance_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        # Database info card
        grp_info = QGroupBox(_t("data_safety.maintenance_group_info"))
        grp_info.setProperty("class", "card")
        info_layout = QFormLayout(grp_info)
        info_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        info_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        info_layout.setVerticalSpacing(10)
        info_layout.setHorizontalSpacing(20)

        self.lbl_db_size = QLabel("--")
        self.lbl_db_size.setProperty("class", "value")
        info_layout.addRow(self._info_label(_t("data_safety.maintenance_db_size")), self.lbl_db_size)

        self.lbl_products_count = QLabel("--")
        self.lbl_products_count.setProperty("class", "value")
        info_layout.addRow(self._info_label(_t("data_safety.maintenance_products")), self.lbl_products_count)

        self.lbl_customers_count = QLabel("--")
        self.lbl_customers_count.setProperty("class", "value")
        info_layout.addRow(self._info_label(_t("data_safety.maintenance_customers")), self.lbl_customers_count)

        self.lbl_sales_count = QLabel("--")
        self.lbl_sales_count.setProperty("class", "value")
        info_layout.addRow(self._info_label(_t("data_safety.maintenance_sales")), self.lbl_sales_count)

        layout.addWidget(grp_info)

        # Actions card
        grp_actions = QGroupBox(_t("data_safety.maintenance_group_tools"))
        grp_actions.setProperty("class", "card")
        actions_layout = QVBoxLayout(grp_actions)
        actions_layout.setSpacing(12)

        # Optimize row
        optimize_row = QHBoxLayout()
        optimize_info = QVBoxLayout()
        lbl_opt_title = QLabel(_t("data_safety.maintenance_optimize_title"))
        lbl_opt_title.setProperty("class", "value")
        optimize_info.addWidget(lbl_opt_title)
        lbl_opt_desc = QLabel(_t("data_safety.maintenance_optimize_desc"))
        lbl_opt_desc.setProperty("class", "muted")
        lbl_opt_desc.setWordWrap(True)
        optimize_info.addWidget(lbl_opt_desc)
        optimize_row.addLayout(optimize_info, 1)

        self.btn_vacuum = QPushButton(_t("data_safety.maintenance_btn_optimize"))
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
        lbl_int_title = QLabel(_t("data_safety.maintenance_integrity_title"))
        lbl_int_title.setProperty("class", "value")
        integrity_info.addWidget(lbl_int_title)
        lbl_int_desc = QLabel(_t("data_safety.maintenance_integrity_desc"))
        lbl_int_desc.setProperty("class", "muted")
        lbl_int_desc.setWordWrap(True)
        integrity_info.addWidget(lbl_int_desc)
        integrity_row.addLayout(integrity_info, 1)

        self.btn_integrity = QPushButton(_t("data_safety.maintenance_btn_check"))
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
        self.btn_vacuum.setText(_t("data_safety.maintenance_optimizing"))
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
        self.btn_vacuum.setText(_t("data_safety.maintenance_btn_optimize"))
        saved = result.get("saved", "0 KB")
        self.lbl_maintenance_status.setProperty("class", "status-ok")
        self.lbl_maintenance_status.setText(_t("data_safety.maintenance_optimize_complete", saved=saved))
        self._load_db_info()

    def _on_vacuum_error(self, error: str) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_vacuum.setEnabled(True)
        self.btn_vacuum.setText(_t("data_safety.maintenance_btn_optimize"))
        self.lbl_maintenance_status.setProperty("class", "status-err")
        self.lbl_maintenance_status.setText(_t("data_safety.maintenance_optimize_failed", error=error))

    def _run_integrity_check(self) -> None:
        self.btn_integrity.setEnabled(False)
        self.btn_integrity.setText(_t("data_safety.maintenance_checking"))
        QApplication.processEvents()

        try:
            from cbpos.core.services.maintenance_service import MaintenanceService

            ok, message = MaintenanceService.integrity_check()
            if ok:
                self.lbl_maintenance_status.setProperty("class", "status-ok")
                self.lbl_maintenance_status.setText(_t("data_safety.maintenance_integrity_passed"))
            else:
                self.lbl_maintenance_status.setProperty("class", "status-err")
                self.lbl_maintenance_status.setText(_t("data_safety.maintenance_integrity_failed", message=message))
        except Exception as e:
            self.lbl_maintenance_status.setProperty("class", "status-err")
            self.lbl_maintenance_status.setText(_t("data_safety.maintenance_integrity_failed", message=str(e)))
        finally:
            self.btn_integrity.setEnabled(True)
            self.btn_integrity.setText(_t("data_safety.maintenance_btn_check"))

    # ── Export Data Tab ───────────────────────────────────────────────────

    def _build_export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        # Info card
        grp_export = QGroupBox(_t("data_safety.export_group_title"))
        grp_export.setProperty("class", "card")
        export_layout = QVBoxLayout(grp_export)
        export_layout.setSpacing(12)

        desc = QLabel(_t("data_safety.export_desc"))
        desc.setProperty("class", "muted")
        desc.setWordWrap(True)
        export_layout.addWidget(desc)

        btn_open_export = QPushButton(_t("data_safety.btn_open_export"))
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
            QMessageBox.critical(self, _t("common.error"), _t("data_safety.export_open_failed", error=str(e)))
