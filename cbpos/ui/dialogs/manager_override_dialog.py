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


class ManagerOverrideDialog(QDialog):
    """
    Dialog to request Manager PIN for restricted actions.
    """

    def __init__(self, permission_required: str, parent=None):
        """Initialize the dialog for the permission code that requires manager approval."""
        super().__init__(parent)
        self.permission_required = permission_required
        self.authorized_user = None

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

        btn_verify = QPushButton(_t("manager_override.verify"))
        btn_verify.setProperty("class", "accent")
        btn_verify.clicked.connect(self.verify_pin)
        layout.addWidget(btn_verify)

        btn_cancel = QPushButton(_t("common.cancel"))
        btn_cancel.setProperty("class", "secondary")
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

    def showEvent(self, event):
        """Focus the PIN input when the dialog is shown."""
        super().showEvent(event)
        self.pin_input.setFocus()

    def verify_pin(self):
        """Verify the entered PIN and, if the user holds the required permission, accept the dialog."""
        pin = self.pin_input.text()
        if not pin:
            return

        user = AuthService.authenticate_pin(pin)
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
            QMessageBox.warning(self, _t("manager_override.invalid_pin"), _t("manager_override.invalid_pin_msg"))
            self.pin_input.clear()
