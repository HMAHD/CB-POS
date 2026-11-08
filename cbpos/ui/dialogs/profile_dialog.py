from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.user_service import UserService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t
from cbpos.ui.workers import PinCheckWorker, start_background_job


class ProfileDialog(QDialog):
    """Standalone dialog for user profile and PIN change."""

    def __init__(self, parent=None):
        """Initialize the dialog and load the current user's profile."""
        super().__init__(parent)
        self.setWindowTitle(_t("profile.title"))
        self.setMinimumSize(400, 300)
        self.resize(400, 300)
        self.setObjectName("ProfileDialog")
        self._pin_worker: PinCheckWorker | None = None
        self._pin_check_gen: int = 0
        self.init_ui()
        self.load_user()

    def init_ui(self):
        """Build the display name and PIN change form."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel(_t("profile.title"))
        title.setObjectName("DialogTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(15)
        form.setHorizontalSpacing(20)

        self.input_name = QLineEdit()
        form.addRow(_t("profile.display_name"), self.input_name)

        self.input_current_pin = QLineEdit()
        self.input_current_pin.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(_t("profile.current_pin"), self.input_current_pin)

        self.input_new_pin = QLineEdit()
        self.input_new_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_new_pin.setPlaceholderText(_t("profile.new_pin_placeholder"))
        form.addRow(_t("profile.new_pin"), self.input_new_pin)

        layout.addLayout(form)

        self.btn_update = QPushButton(_t("profile.btn_update"))
        self.btn_update.setObjectName("BtnSave")
        self.btn_update.clicked.connect(self.update_profile)
        layout.addWidget(self.btn_update)

    def load_user(self):
        """Populate the display name field from the currently logged-in user."""
        user = AuthService.get_current_user()
        if user:
            self.input_name.setText(user.username)

    def _set_checking_state(self, checking: bool):
        """Enable or disable dialog controls while background verification runs."""
        self.input_name.setEnabled(not checking)
        self.input_current_pin.setEnabled(not checking)
        self.input_new_pin.setEnabled(not checking)
        self.btn_update.setEnabled(not checking)
        self.btn_update.setText(_t("login.checking") if checking else _t("profile.btn_update"))

    def update_profile(self):
        """Verify the current PIN asynchronously, then update the display name and optionally the PIN."""
        if self._pin_worker is not None and self._pin_worker.isRunning():
            return

        user = AuthService.get_current_user()
        if not user:
            return

        current_pin = self.input_current_pin.text()
        new_pin = self.input_new_pin.text()
        display_name = self.input_name.text()

        if not current_pin:
            QMessageBox.warning(self, _t("common.error"), _t("profile.pin_required"))
            return

        lockout_secs = AuthService.get_terminal_lockout_seconds()
        if lockout_secs > 0:
            QMessageBox.warning(self, _t("common.error"), _t("login.locked", seconds=lockout_secs))
            return

        self._set_checking_state(True)
        self._pin_check_gen += 1
        gen = self._pin_check_gen
        self._pin_worker = PinCheckWorker(mode="check_own", pin=current_pin, user_id=user.id)
        self._pin_worker.result.connect(
            lambda res, g=gen, u_id=user.id, dn=display_name, np=new_pin: self._on_profile_pin_result(
                res, g, u_id, dn, np
            )
        )
        start_background_job(self._pin_worker)

    def _on_profile_pin_result(
        self,
        matched: bool,
        gen: int,
        user_id: int,
        display_name: str,
        new_pin: str,
    ):
        """Handle worker verification result and proceed with profile update if PIN is valid."""
        if gen != self._pin_check_gen:
            return
        self._pin_worker = None
        self._set_checking_state(False)

        if not matched:
            lockout_secs = AuthService.get_terminal_lockout_seconds()
            if lockout_secs > 0:
                QMessageBox.warning(self, _t("common.error"), _t("login.locked", seconds=lockout_secs))
            else:
                QMessageBox.critical(self, _t("common.error"), _t("profile.invalid_pin"))
            return

        try:
            success = UserService.update_user_profile(user_id, display_name, new_pin if new_pin else None)
        except ValueError as e:
            err_code = str(e)
            msg = _t("users.pin_in_use") if err_code == "pin_in_use" else translate_error(err_code)
            QMessageBox.warning(self, _t("common.error"), msg)
            self.input_new_pin.setFocus()
            self.input_new_pin.selectAll()
            return

        if success:
            QMessageBox.information(self, _t("common.success"), _t("profile.update_success"))
            self.accept()
        else:
            QMessageBox.critical(self, _t("common.error"), _t("profile.update_failed"))

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
