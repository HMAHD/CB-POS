from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService
from cbpos.i18n import _t
from cbpos.ui.workers import PinCheckWorker, start_background_job


class ManagerOverrideDialog(QDialog):
    """
    Dialog to request Manager PIN for restricted actions.
    """

    def __init__(self, permission_required: str, parent=None):
        """Initialize the dialog for the permission code that requires manager approval."""
        super().__init__(parent)
        self.permission_required = permission_required
        self.authorized_user = None
        self._pin_worker: PinCheckWorker | None = None
        self._pin_check_gen: int = 0

        self.setWindowTitle(_t("manager_override.title"))
        self.setMinimumSize(300, 200)
        self.resize(300, 200)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.init_ui()

    def init_ui(self):
        """Build the PIN input and verify/cancel buttons."""
        layout = QVBoxLayout(self)

        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setPlaceholderText(_t("manager_override.pin_placeholder"))
        self.pin_input.returnPressed.connect(self.verify_pin)
        layout.addWidget(self.pin_input)

        self.btn_verify = QPushButton(_t("manager_override.verify"))
        self.btn_verify.setProperty("class", "accent")
        self.btn_verify.clicked.connect(self.verify_pin)
        layout.addWidget(self.btn_verify)

        self.btn_cancel = QPushButton(_t("common.cancel"))
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)

    def showEvent(self, event):
        """Focus the PIN input when the dialog is shown."""
        super().showEvent(event)
        self.pin_input.setFocus()

    def _set_checking_state(self, checking: bool):
        """Enable or disable dialog controls while background verification runs."""
        self.pin_input.setEnabled(not checking)
        self.btn_verify.setEnabled(not checking)
        self.btn_cancel.setEnabled(not checking)
        self.btn_verify.setText(_t("login.checking") if checking else _t("manager_override.verify"))

    def verify_pin(self):
        """Verify the entered PIN asynchronously and, if the user holds the required permission, accept the dialog."""
        if self._pin_worker is not None and self._pin_worker.isRunning():
            return

        pin = self.pin_input.text()
        if not pin:
            return

        lockout_secs = AuthService.get_terminal_lockout_seconds()
        if lockout_secs > 0:
            QMessageBox.warning(self, _t("common.error"), _t("login.locked", seconds=lockout_secs))
            self.pin_input.clear()
            return

        self._set_checking_state(True)
        self._pin_check_gen += 1
        gen = self._pin_check_gen
        self._pin_worker = PinCheckWorker(mode="authenticate", pin=pin)
        self._pin_worker.result.connect(lambda res, g=gen: self._on_verify_result(res, g))
        start_background_job(self._pin_worker)

    def _on_verify_result(self, user, gen: int):
        """Handle worker verification result on the main thread."""
        if gen != self._pin_check_gen:
            return
        self._pin_worker = None
        self._set_checking_state(False)

        if user:
            if PermissionService.user_has_permission(user, self.permission_required):
                self.authorized_user = user
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    _t("manager_override.access_denied"),
                    _t("manager_override.no_permission"),
                )
                self.pin_input.clear()
        else:
            lockout_secs = AuthService.get_terminal_lockout_seconds()
            if lockout_secs > 0:
                QMessageBox.warning(self, _t("common.error"), _t("login.locked", seconds=lockout_secs))
            else:
                QMessageBox.warning(self, _t("manager_override.invalid_pin"), _t("manager_override.invalid_pin_msg"))
            self.pin_input.clear()

    def reject(self):
        """Cancel any running worker and reject the dialog."""
        self._pin_check_gen += 1
        self._pin_worker = None
        super().reject()

    def closeEvent(self, event):
        """Cancel any running worker and close the dialog."""
        self._pin_check_gen += 1
        self._pin_worker = None
        super().closeEvent(event)
