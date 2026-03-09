"""Update notification and download dialog for CB POS.

Shows the user that a new version is available, displays the changelog,
and handles downloading + launching the installer.
"""

import logging
import subprocess
import sys
from typing import Any, Dict

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from cbpos.config import Config
from cbpos.core.services.update_service import UpdateService

logger = logging.getLogger(__name__)


class _DownloadThread(QThread):
    """Background thread that downloads the installer."""

    progress = pyqtSignal(int, int)  # bytes_downloaded, total_bytes
    finished_ok = pyqtSignal(str)  # path to downloaded file
    finished_err = pyqtSignal(str)  # error message

    def __init__(self, url: str, sha256: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._sha256 = sha256

    def run(self) -> None:
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

    def run(self) -> None:
        result = UpdateService.check_for_update()
        if result:
            self.update_available.emit(result)
        else:
            self.no_update.emit()


class UpdateDialog(QDialog):
    """Dialog shown when a new version is available."""

    def __init__(self, manifest: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self._manifest = manifest
        self._download_thread: _DownloadThread | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle("Update Available")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        version = self._manifest.get("version", "?")
        date = self._manifest.get("release_date", "")
        changelog = self._manifest.get("changelog", "")

        # Header
        header = QLabel(f"<h3>CB POS {version} is available</h3>")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # Current vs new
        info = QLabel(f"Your version: <b>{Config.VERSION}</b>" f" \u2192 New version: <b>{version}</b>")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        if date:
            date_lbl = QLabel(f"Released: {date}")
            date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            date_lbl.setStyleSheet("color: #888;")
            layout.addWidget(date_lbl)

        # Changelog
        if changelog:
            cl_label = QLabel(f"<b>What's new:</b><br>{changelog}")  # noqa: E231
            cl_label.setWordWrap(True)
            layout.addWidget(cl_label)

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

        self._btn_update = QPushButton("Download && Install")
        self._btn_update.setDefault(True)
        self._btn_update.clicked.connect(self._start_download)
        btn_layout.addWidget(self._btn_update)

        self._btn_skip = QPushButton("Remind Me Later")
        self._btn_skip.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_skip)

        layout.addLayout(btn_layout)

    def _start_download(self) -> None:
        url = self._manifest.get("download_url", "")
        if not url:
            QMessageBox.warning(self, "Error", "No download URL in update manifest.")
            return

        sha = self._manifest.get("sha256", "")

        self._btn_update.setEnabled(False)
        self._btn_skip.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status.setVisible(True)
        self._status.setText("Downloading update...")

        self._download_thread = _DownloadThread(url, sha, self)
        self._download_thread.progress.connect(self._on_progress)
        self._download_thread.finished_ok.connect(self._on_download_ok)
        self._download_thread.finished_err.connect(self._on_download_err)
        self._download_thread.start()

    def _on_progress(self, downloaded: int, total: int) -> None:
        pct = int(downloaded * 100 / total) if total else 0
        self._progress.setValue(pct)
        mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        self._status.setText(f"Downloading... {mb:.1f} / {total_mb:.1f} MB")  # noqa: E231

    def _on_download_ok(self, path: str) -> None:
        self._progress.setValue(100)
        self._status.setText("Download complete. Launching installer...")

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
                    "Automatic installer launch is only supported on Windows. " "Installer was downloaded to: %s",
                    path,
                )
                QMessageBox.information(
                    self,
                    "Manual Update Required",
                    "Automatic installer launch is only supported on Windows.\n\n"
                    f"The installer was saved to:\n{path}\n"  # noqa: E231
                    "Please run it manually.",
                )
                self._btn_skip.setEnabled(True)
                self._btn_skip.setText("Close")
        except OSError as e:
            logger.error("Failed to launch installer: %s", e)
            QMessageBox.warning(
                self,
                "Error",
                f"Could not launch installer:\n{e}\n\n"  # noqa: E231
                f"The installer was saved to:\n{path}\n"  # noqa: E231
                "Please run it manually.",
            )
            self._btn_skip.setEnabled(True)
            self._btn_skip.setText("Close")

    def _on_download_err(self, error: str) -> None:
        self._status.setText("Download failed.")
        self._progress.setVisible(False)
        self._btn_update.setEnabled(True)
        self._btn_skip.setEnabled(True)
        QMessageBox.warning(self, "Download Failed", error)


def check_for_updates_async(parent=None, silent: bool = True) -> _CheckThread:
    """Spawn a background update check.

    Args:
        parent: Parent QWidget (keeps thread alive).
        silent: If True, only show dialog when an update is found.
                If False, also inform the user when up-to-date.

    Returns:
        The running ``_CheckThread`` (caller must keep a reference).
    """

    def _on_update(manifest: Dict[str, Any]) -> None:
        dlg = UpdateDialog(manifest, parent)
        dlg.exec()

    def _on_no_update() -> None:
        if not silent:
            QMessageBox.information(
                parent,
                "No Updates",
                f"You are running the latest version ({Config.VERSION}).",
            )

    thread = _CheckThread(parent)
    thread.update_available.connect(_on_update)
    thread.no_update.connect(_on_no_update)
    thread.start()
    return thread
