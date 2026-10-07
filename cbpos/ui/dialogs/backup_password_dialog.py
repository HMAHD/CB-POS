"""Set or change the shop backup password (#619).

One password locks every backup the app makes -- manual, automatic on
close, and the safety snapshot taken before a restore. It is not tied to
this PC, so backups can be restored on a new computer with it.
"""

import logging

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class BackupPasswordDialog(QDialog):
    """Ask for a new shop backup password (twice) and store it."""

    def __init__(self, parent: QWidget | None = None, changing: bool = False) -> None:
        """Build the dialog.

        Args:
            parent: Parent widget.
            changing: True when replacing an existing password -- the text
                then explains that only new backups use it.
        """
        super().__init__(parent)
        self.setObjectName("BackupPasswordDialog")
        self.setMinimumWidth(460)
        self._changing = changing

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.lbl_intro = QLabel()
        self.lbl_intro.setWordWrap(True)
        layout.addWidget(self.lbl_intro)

        self.lbl_note = QLabel()
        self.lbl_note.setProperty("class", "muted")
        self.lbl_note.setWordWrap(True)
        layout.addWidget(self.lbl_note)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.lbl_password = QLabel()
        form.addRow(self.lbl_password, self.input_password)
        self.input_confirm = QLineEdit()
        self.input_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.lbl_confirm = QLabel()
        form.addRow(self.lbl_confirm, self.input_confirm)
        layout.addLayout(form)

        self.btn_toggle = QPushButton()
        self.btn_toggle.setProperty("class", "secondary")
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.toggled.connect(self._toggle_visibility)
        toggle_row = QHBoxLayout()
        toggle_row.addStretch()
        toggle_row.addWidget(self.btn_toggle)
        layout.addLayout(toggle_row)

        self.lbl_error = QLabel()
        self.lbl_error.setProperty("class", "debit")
        self.lbl_error.setWordWrap(True)
        layout.addWidget(self.lbl_error)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_cancel = QPushButton()
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)
        self.btn_save = QPushButton()
        self.btn_save.setProperty("class", "primary")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._save)
        btn_row.addWidget(self.btn_save)
        layout.addLayout(btn_row)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Apply translated text."""
        key = "change" if self._changing else "set"
        self.setWindowTitle(_t(f"backup_password.title_{key}"))
        self.lbl_intro.setText(_t("backup_password.intro"))
        self.lbl_note.setText(_t(f"backup_password.note_{key}"))
        self.lbl_password.setText(_t("backup_password.new_password"))
        self.lbl_confirm.setText(_t("backup_password.confirm_password"))
        self.input_password.setPlaceholderText(
            _t("backup_password.min_length", count=ConfigService.MIN_BACKUP_PASSWORD_LENGTH)
        )
        self.btn_toggle.setText(_t("data_safety.btn_hide" if self.btn_toggle.isChecked() else "data_safety.btn_show"))
        self.btn_cancel.setText(_t("common.cancel"))
        self.btn_save.setText(_t("backup_password.btn_save"))

    def _toggle_visibility(self, visible: bool) -> None:
        """Show or hide what the user typed (their own password, on request)."""
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self.input_password.setEchoMode(mode)
        self.input_confirm.setEchoMode(mode)
        self.btn_toggle.setText(_t("data_safety.btn_hide" if visible else "data_safety.btn_show"))

    def _save(self) -> None:
        """Validate and store the password, then close."""
        password = self.input_password.text()
        if len(password) < ConfigService.MIN_BACKUP_PASSWORD_LENGTH:
            self.lbl_error.setText(_t("backup_password.too_short", count=ConfigService.MIN_BACKUP_PASSWORD_LENGTH))
            return
        if password != self.input_confirm.text():
            self.lbl_error.setText(_t("backup_password.mismatch"))
            return
        try:
            ConfigService.set_backup_password(password)
        except (OSError, ValueError) as e:
            logger.error("Could not save the backup password: %s", type(e).__name__)
            self.lbl_error.setText(_t("backup_password.save_failed"))
            return
        self.accept()


def ensure_backup_password(parent: QWidget | None) -> str | None:
    """Return the shop backup password, asking the user to set one first if needed.

    Returns:
        The password, or None if none is set and the user cancelled.
    """
    password = ConfigService.get_backup_password()
    if password:
        return password
    dialog = BackupPasswordDialog(parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return ConfigService.get_backup_password() if accepted else None
