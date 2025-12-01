from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QPushButton,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService


class ManagerOverrideDialog(QDialog):
    """
    Dialog to request Manager PIN for restricted actions.
    """

    def __init__(self, permission_required: str, parent=None):
        super().__init__(parent)
        self.permission_required = permission_required
        self.authorized_user = None

        self.setWindowTitle("Manager Override Required")
        self.setFixedSize(300, 200)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet("background-color: #001F3F; color: white;")

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        btn_verify = QPushButton("Verify")
        btn_verify.setStyleSheet("background-color: #00BCEB; color: black; font-weight: bold; padding: 10px;")
        btn_verify.clicked.connect(self.verify_pin)
        layout.addWidget(btn_verify)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #FF4136; color: white; padding: 10px;")
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

    def verify_pin(self):
        pin = self.pin_input.text()
        if not pin:
            return

        user = AuthService.verify_pin(pin)
        if user:
            if PermissionService.user_has_permission(user, self.permission_required):
                self.authorized_user = user
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Access Denied",
                    "This user does not have the required permission.",
                )
                self.pin_input.clear()
        else:
            QMessageBox.warning(self, "Invalid PIN", "Invalid PIN. Please try again.")
            self.pin_input.clear()
