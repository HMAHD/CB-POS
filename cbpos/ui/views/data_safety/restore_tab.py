"""Data Safety -> Restore tab: verify a backup file, then restore it."""

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.backup_service import BackupService
from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t
from cbpos.ui.dialogs.backup_password_dialog import ensure_backup_password
from cbpos.ui.utils.style_helpers import set_status_class
from cbpos.ui.widgets.loading_overlay import LoadingOverlay
from cbpos.ui.workers import RestoreWorker, VerifyBackupWorker

logger = logging.getLogger(__name__)


class RestoreTabWidget(QWidget):
    """Pick a backup file and its password, verify it, restore it.

    Signals:
        password_changed: The shop backup password may have just been set
            (restoring asks for one first, for the safety snapshot).
    """

    password_changed = pyqtSignal()

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

    def load_backup(self, path: str) -> None:
        """Get ready to restore *path*: fill it in, clear the old password and result."""
        self.input_restore_path.setText(path)
        self.input_restore_password.clear()
        self.lbl_verify_result.setText("")
        self.input_restore_password.setFocus()

    def refresh_password_hint(self) -> None:
        """Say in the password box whether leaving it empty uses the shop password."""
        if ConfigService.has_backup_password():
            self.input_restore_password.setPlaceholderText(_t("data_safety.restore_pwd_placeholder_shop"))
        else:
            self.input_restore_password.setPlaceholderText(_t("data_safety.restore_pwd_placeholder"))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
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

        # Verify decrypts and checks the whole database -- keep it off the
        # UI thread so large backups don't freeze the window (#629).
        self.btn_verify.setEnabled(False)
        self.btn_restore.setEnabled(False)
        self.lbl_verify_result.setText("")
        self._overlay.show_loading(_t("data_safety.verify_running"))
        self._verify_worker = VerifyBackupWorker(path, password)
        self._verify_worker.result.connect(self._on_verify_finished)
        self._verify_worker.start()

    def _on_verify_finished(self, result: dict) -> None:
        self._overlay.hide_loading()
        self.btn_verify.setEnabled(True)
        self.btn_restore.setEnabled(True)
        if result["valid"]:
            file_count = len(result["files"])
            set_status_class(
                self.lbl_verify_result,
                "credit",
                _t("data_safety.restore_valid", size=result["size"], count=file_count),
            )
        else:
            code = result.get("error_code")
            error = _t(f"data_safety.error_{code}") if code else result["error"]
            set_status_class(self.lbl_verify_result, "debit", _t("data_safety.restore_invalid", error=error))

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

        # The safety snapshot is locked with the shop password -- no
        # password, no snapshot, no restore (#628).
        snapshot_password = ensure_backup_password(self)
        self.refresh_password_hint()
        self.password_changed.emit()
        if not snapshot_password:
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
        self._restore_worker.refused.connect(self._on_restore_refused)
        self._restore_worker.error.connect(self._on_restore_error)
        self._restore_worker.start()

    def _on_restore_refused(self, code: str) -> None:
        """The backup was rejected before anything changed -- say why in plain words."""
        self._on_restore_error(_t(f"data_safety.error_{code}"))

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

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.lbl_restore_warning.setText(_t("data_safety.restore_warning_full"))
        self.grp_restore_file.setTitle(_t("data_safety.restore_file_group"))
        self.input_restore_path.setPlaceholderText(_t("data_safety.restore_file_placeholder"))
        self.btn_browse.setText(_t("data_safety.btn_browse"))
        self.refresh_password_hint()
        self.btn_toggle_restore_pwd.setText(_t("data_safety.btn_show"))
        self.btn_verify.setText(_t("data_safety.btn_verify"))
        self.btn_restore.setText(_t("data_safety.btn_restore"))
