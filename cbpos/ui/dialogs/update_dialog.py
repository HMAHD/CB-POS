"""Update notification and download dialog for CB POS.

Shows the user that a new version is available, displays the changelog,
and handles downloading + launching the installer.
"""

import logging
import subprocess
import sys
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from cbpos.config import Config
from cbpos.core.services.update_service import UpdateService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class _DownloadThread(QThread):
    """Background thread that downloads the installer."""

    progress = pyqtSignal(int, int)  # bytes_downloaded, total_bytes
    finished_ok = pyqtSignal(str)  # path to downloaded file
    finished_err = pyqtSignal(str)  # error message

    def __init__(self, url: str, sha256: str, parent=None) -> None:
        """Store the installer `url` and expected `sha256` checksum to download."""
        super().__init__(parent)
        self._url = url
        self._sha256 = sha256

    def run(self) -> None:
        """Download and checksum-verify the installer, emitting `finished_ok`/`finished_err`."""
        try:
            path = UpdateService.download_installer(
                self._url,
                self._sha256,
                progress_callback=self._on_progress,
            )
            self.finished_ok.emit(path)
        except Exception as e:
            self.finished_err.emit(str(e))

    def _on_progress(self, downloaded: int, total: int) -> None:
        self.progress.emit(downloaded, total)


class _CheckThread(QThread):
    """Background thread that checks for updates without blocking the UI."""

    update_available = pyqtSignal(dict)  # manifest data
    no_update = pyqtSignal()
    check_failed = pyqtSignal(str)  # error message

    def run(self) -> None:
        """Check for an available update, emitting `update_available`, `no_update`, or `check_failed`."""
        try:
            result = UpdateService.check_for_update()
            if result:
                self.update_available.emit(result)
            else:
                self.no_update.emit()
        except Exception as e:
            logger.info("Update check thread caught error: %s", e)
            self.check_failed.emit(str(e))


class UpdateDialog(QDialog):
    """Dialog shown when a new version is available."""

    def __init__(self, manifest: dict[str, Any], parent=None) -> None:
        """Build the dialog showing the new version, changelog, and download button from `manifest`."""
        super().__init__(parent)
        self._manifest = manifest
        self._is_required = bool(manifest.get("is_required", False))
        self._download_thread: _DownloadThread | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        if self._is_required:
            self.setWindowTitle(_t("update.required_title", default="Important update"))
        else:
            self.setWindowTitle(_t("update.title", default="Update Available"))

        self.setMinimumWidth(440)
        self.setMinimumHeight(320)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        version = self._manifest.get("version", "?")
        date = self._manifest.get("release_date", "")
        changelog = self._manifest.get("changelog", "")

        # Header
        header = QLabel(f"<h3>{_t('update.version_available', version=version)}</h3>")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # Current vs new
        info = QLabel(
            _t("update.your_version", version=Config.VERSION) + " \u2192 " + _t("update.new_version", version=version)
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        if date:
            date_lbl = QLabel(_t("update.released", date=date))
            date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            date_lbl.setProperty("class", "muted")
            layout.addWidget(date_lbl)

        # Required update notice
        self.lbl_required_notice = QLabel(
            _t(
                "update.required_body",
                default="This update fixes a serious problem. Please install it as soon as you can.",
            )
        )
        self.lbl_required_notice.setWordWrap(True)
        self.lbl_required_notice.setProperty("class", "warning")
        self.lbl_required_notice.setVisible(self._is_required)
        layout.addWidget(self.lbl_required_notice)

        # Changelog (scrollable, read-only, plain-text)
        if changelog:
            cl_title = QLabel(f"<b>{_t('update.whats_new')}:</b>")
            layout.addWidget(cl_title)

            self._cl_edit = QPlainTextEdit()
            self._cl_edit.setReadOnly(True)
            self._cl_edit.setPlainText(str(changelog).strip())
            self._cl_edit.setMinimumHeight(100)
            self._cl_edit.setMaximumHeight(180)
            layout.addWidget(self._cl_edit)

        # Progress bar (hidden until download starts)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setVisible(False)
        layout.addWidget(self._status)

        # Buttons
        btn_layout = QHBoxLayout()

        self._btn_update = QPushButton(_t("update.download_install"))
        self._btn_update.setProperty("class", "primary")
        self._btn_update.setDefault(True)
        self._btn_update.clicked.connect(self._start_download)
        btn_layout.addWidget(self._btn_update)

        skip_text = _t("common.close") if self._is_required else _t("update.remind_later")
        self._btn_skip = QPushButton(skip_text)
        self._btn_skip.setObjectName("BtnCancel")
        self._btn_skip.setProperty("class", "secondary")
        self._btn_skip.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_skip)

        layout.addLayout(btn_layout)

    def _start_download(self) -> None:
        url = self._manifest.get("download_url", "")
        if not url:
            QMessageBox.warning(self, _t("common.error"), _t("update.no_download_url"))
            return

        sha = self._manifest.get("sha256", "")

        self._btn_update.setEnabled(False)
        self._btn_skip.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)  # Indeterminate until first progress
        self._status.setVisible(True)
        self._status.setText(_t("update.downloading"))

        self._download_thread = _DownloadThread(url, sha, self)
        self._download_thread.progress.connect(self._on_progress)
        self._download_thread.finished_ok.connect(self._on_download_ok)
        self._download_thread.finished_err.connect(self._on_download_err)
        self._download_thread.start()

    def _on_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            pct = int(downloaded * 100 / total)
            self._progress.setRange(0, 100)
            self._progress.setValue(pct)
            mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            self._status.setText(_t("update.downloading_progress", downloaded=f"{mb:.1f}", total=f"{total_mb:.1f}"))
        else:
            self._progress.setRange(0, 0)
            mb = downloaded / (1024 * 1024)
            self._status.setText(_t("update.downloading") + f" ({mb:.1f} MB)")

    def _on_download_ok(self, path: str) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._status.setText(_t("update.launching_installer"))

        # Launch the installer on supported platforms
        try:
            if sys.platform == "win32":
                # /SILENT runs a quiet install; remove for full wizard
                subprocess.Popen([path, "/SILENT"], close_fds=True)
                logger.info("Installer launched: %s", path)
                # Close the application so the installer can overwrite files
                QApplication.instance().quit()
            else:
                # Non-Windows: automatic launch is not supported
                logger.warning(
                    "Automatic installer launch is only supported on Windows. Installer was downloaded to: %s",
                    path,
                )
                QMessageBox.information(
                    self,
                    _t("update.manual_required"),
                    _t("update.manual_message", path=path),
                )
                self._btn_skip.setEnabled(True)
                self._btn_skip.setText(_t("common.close"))
        except OSError as e:
            logger.error("Failed to launch installer: %s", e)
            QMessageBox.warning(
                self,
                _t("common.error"),
                _t("update.launch_failed", error=translate_error(str(e)), path=path),
            )
            self._btn_skip.setEnabled(True)
            self._btn_skip.setText(_t("common.close"))

    def _on_download_err(self, error: str) -> None:
        self._status.setText(_t("update.download_failed"))
        self._progress.setVisible(False)
        self._btn_update.setEnabled(True)
        self._btn_update.setText(_t("update.retry", default="Retry"))
        self._btn_skip.setEnabled(True)
        self._btn_skip.setText(_t("common.close"))
        QMessageBox.warning(self, _t("update.download_failed"), error)


_active_check_thread: _CheckThread | None = None


def check_for_updates_async(
    parent=None,
    silent: bool = True,
    button: QPushButton | None = None,
) -> _CheckThread | None:
    """Spawn a background update check.

    Args:
        parent: Parent QWidget (keeps thread alive).
        silent: If True, only show dialog when an update is found.
                If False, inform the user when up-to-date or failed.
        button: Optional QPushButton to disable and set to 'Checking...' during the check.

    Returns:
        The running ``_CheckThread``, or None if a check is already running.
    """
    global _active_check_thread
    thread_to_run: _CheckThread | None = None
    if _active_check_thread is not None and _active_check_thread.isRunning():
        if silent:
            logger.info("Silent update check already in progress, ignoring duplicate request.")
            return None
        logger.info("Attaching manual update check request to running check thread.")
        thread = _active_check_thread
    else:
        thread = _CheckThread(parent)
        _active_check_thread = thread
        thread_to_run = thread

    orig_btn_text = button.text() if button is not None else ""
    if button is not None:
        button.setEnabled(False)
        button.setText(_t("update.checking", default="Checking..."))

    def _cleanup() -> None:
        global _active_check_thread
        if _active_check_thread is thread:
            _active_check_thread = None
        if button is not None:
            button.setText(orig_btn_text)
            button.setEnabled(True)

    def _on_update(manifest: dict[str, Any]) -> None:
        _cleanup()
        dlg = UpdateDialog(manifest, parent)
        dlg.exec()

    def _on_no_update() -> None:
        _cleanup()
        if not silent:
            QMessageBox.information(
                parent,
                _t("update.no_updates"),
                _t("update.latest_version", version=Config.VERSION),
            )

    def _on_failed(error_msg: str) -> None:
        _cleanup()
        if not silent:
            QMessageBox.warning(
                parent,
                _t("common.error"),
                _t(
                    "update.check_failed",
                    error=translate_error(error_msg),
                    default=f"Could not check for updates: {error_msg}",
                ),
            )

    thread.update_available.connect(_on_update)
    thread.no_update.connect(_on_no_update)
    thread.check_failed.connect(_on_failed)
    thread.finished.connect(_cleanup)
    if thread_to_run is not None:
        thread_to_run.start()
    return thread
