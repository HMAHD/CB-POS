"""Dialog for LAN Sync TLS certificate fingerprint verification and pairing (#800)."""

import json
import logging

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.logging_service import LoggingService
from cbpos.i18n import _t
from cbpos.infrastructure import sync_tls
from cbpos.ui.dialogs.admin_pin_dialog import AdminPinDialog
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


class FetchCertWorker(QThread):
    """Fetches the server's TLS certificate off the UI thread without sending any credentials."""

    finished_cert = pyqtSignal(bool, str, str)  # success, pem_or_error, fingerprint

    def __init__(self, host: str, port: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host
        self.port = port

    def run(self):
        """Perform raw TLS certificate fetch."""
        try:
            pem = sync_tls.fetch_server_certificate(self.host, self.port, timeout=5.0)
            fp = sync_tls.cert_fingerprint(pem)
            self.finished_cert.emit(True, pem, fp)
        except Exception as e:
            logger.warning("Failed to fetch server certificate from %s:%s: %s", self.host, self.port, e)
            self.finished_cert.emit(False, str(e), "")


def _format_fp_display(fp: str) -> str:
    """Format canonical fingerprint into 4 lines of 8 pairs for readable display."""
    if not fp:
        return ""
    if "\n" in fp:
        return fp
    parts = fp.split(":")
    if len(parts) == 32:
        return "\n".join([":".join(parts[i : i + 8]) for i in range(0, 32, 8)])
    return fp


class SyncPairingDialog(QDialog):
    """Modal dialog to compare and pin Main PC TLS certificate fingerprint."""

    def __init__(self, host: str, port: int, re_pair: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SyncPairingDialog")
        self.setWindowTitle(_t("sync_pairing.title"))
        self.resize(620, 440)
        self.setMinimumSize(560, 380)

        self.host = host
        self.port = port
        self.re_pair = re_pair
        self._presented_pem: str = ""
        self._presented_fp: str = ""

        self._init_ui()
        install_wheel_guard(self)
        self._start_fetch()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Title / Instruction
        self.lbl_title = QLabel(_t("sync_pairing.title"))
        self.lbl_title.setObjectName("DialogTitle")
        font_title = self.lbl_title.font()
        font_title.setPointSize(font_title.pointSize() + 3)
        font_title.setBold(True)
        self.lbl_title.setFont(font_title)
        layout.addWidget(self.lbl_title)

        if self.re_pair:
            self.lbl_alert = QLabel(_t("sync_pairing.changed"))
            self.lbl_alert.setObjectName("PairingAlert")
            self.lbl_alert.setStyleSheet(
                "background-color: rgba(244, 67, 54, 0.15); color: #F44336; border: 1px solid #F44336; "
                "border-radius: 6px; padding: 10px; font-weight: bold;"
            )
            self.lbl_alert.setWordWrap(True)
            layout.addWidget(self.lbl_alert)

        self.lbl_instruction = QLabel(_t("sync_pairing.instruction"))
        self.lbl_instruction.setObjectName("PairingInstruction")
        self.lbl_instruction.setWordWrap(True)
        self.lbl_instruction.setProperty("class", "muted")
        layout.addWidget(self.lbl_instruction)

        # Loading bar while fetching
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(6)
        self.lbl_loading = QLabel(_t("sync_pairing.fetching"))
        self.lbl_loading.setProperty("class", "muted")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.lbl_loading)

        # Fingerprint card container
        self.card_frame = QFrame()
        self.card_frame.setObjectName("FingerprintCard")
        self.card_frame.setStyleSheet(
            "QFrame#FingerprintCard { background-color: rgba(0, 0, 0, 0.1); border: 1px solid rgba(128, 128, 128, 0.3); border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(self.card_frame)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(11)

        if self.re_pair:
            # Side by side comparison
            comp_layout = QHBoxLayout()
            comp_layout.setSpacing(16)

            left_box = QVBoxLayout()
            lbl_prev_title = QLabel(_t("sync_pairing.previous"))
            lbl_prev_title.setStyleSheet("font-weight: bold; color: #888;")
            prev_raw = ConfigService.get("sync_pinned_cert_fp") or _t("common.unknown")
            self.lbl_prev_fp = QLabel(_format_fp_display(prev_raw))
            self.lbl_prev_fp.setFont(mono_font)
            self.lbl_prev_fp.setWordWrap(True)
            left_box.addWidget(lbl_prev_title)
            left_box.addWidget(self.lbl_prev_fp)
            comp_layout.addLayout(left_box)

            right_box = QVBoxLayout()
            lbl_pres_title = QLabel(_t("sync_pairing.presented"))
            lbl_pres_title.setStyleSheet("font-weight: bold; color: #FF9800;")
            self.lbl_presented_fp = QLabel("")
            self.lbl_presented_fp.setFont(mono_font)
            self.lbl_presented_fp.setWordWrap(True)
            right_box.addWidget(lbl_pres_title)
            right_box.addWidget(self.lbl_presented_fp)
            comp_layout.addLayout(right_box)

            card_layout.addLayout(comp_layout)

            self.lbl_admin_note = QLabel(_t("sync_pairing.admin_needed"))
            self.lbl_admin_note.setProperty("class", "muted")
            card_layout.addWidget(self.lbl_admin_note)
        else:
            self.lbl_presented_fp = QLabel("")
            self.lbl_presented_fp.setFont(mono_font)
            self.lbl_presented_fp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_presented_fp.setWordWrap(True)
            self.lbl_presented_fp.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            card_layout.addWidget(self.lbl_presented_fp)

        self.card_frame.setVisible(False)
        layout.addWidget(self.card_frame)

        layout.addStretch()

        # Footer buttons: Cancel is default!
        footer_layout, self.btn_pair, self.btn_cancel = make_dialog_footer(
            primary_key="sync_pairing.match",
            on_primary=self._on_pair_clicked,
            cancel_key="common.cancel",
            on_cancel=self.reject,
            primary_object_name="BtnMatchPair",
        )

        # Ensure Cancel is the default button so pressing Enter doesn't pair accidentally
        self.btn_cancel.setDefault(True)
        self.btn_pair.setDefault(False)
        self.btn_pair.setEnabled(False)

        layout.addLayout(footer_layout)

    def _start_fetch(self) -> None:
        self.worker = FetchCertWorker(self.host, self.port, parent=self)
        self.worker.finished_cert.connect(self._on_cert_fetched)
        self.worker.start()

    def _on_cert_fetched(self, success: bool, pem_or_error: str, fingerprint: str) -> None:
        self.progress_bar.setVisible(False)
        self.lbl_loading.setVisible(False)

        if not success:
            err_msg = _t("sync_pairing.fetch_failed", error=pem_or_error)
            QMessageBox.critical(self, _t("common.error"), err_msg)
            self.reject()
            return

        self._presented_pem = pem_or_error
        self._presented_fp = fingerprint

        # Display multiline fingerprint for readability
        multiline_fp = sync_tls.cert_fingerprint(pem_or_error, multiline=True)
        self.lbl_presented_fp.setText(multiline_fp)
        self.card_frame.setVisible(True)
        self.btn_pair.setEnabled(True)

    def _on_pair_clicked(self) -> None:
        if not self._presented_pem or not self._presented_fp:
            return

        admin_user_id = None
        if self.re_pair:
            # Require Admin authentication
            pin_dialog = AdminPinDialog(parent=self)
            if not pin_dialog.exec():
                return
            pin = pin_dialog.pin()
            user, role = AuthService.authenticate_pin(pin)
            if not user or not role or (role.access_level < 9 and role.name != "Admin"):
                QMessageBox.warning(
                    self,
                    _t("common.error"),
                    _t("permission.admin_override_failed"),
                )
                return
            admin_user_id = user.id

        # Save pinned certificate and canonical fingerprint
        ConfigService.set("sync_pinned_cert_pem", self._presented_pem)
        ConfigService.set("sync_pinned_cert_fp", self._presented_fp)

        # Audit log the pairing action
        try:
            details = json.dumps(
                {
                    "fingerprint": self._presented_fp,
                    "host": self.host,
                    "port": self.port,
                    "re_pair": self.re_pair,
                }
            )
            LoggingService.log_action(
                user_id=admin_user_id,
                action="SYNC_PAIRED",
                event_type="SECURITY",
                details=details,
            )
        except Exception as e:
            logger.error("Failed to write SYNC_PAIRED audit log: %s", e)

        QMessageBox.information(
            self,
            _t("sync_pairing.title"),
            _t("sync_pairing.pair_success"),
        )
        self.accept()
