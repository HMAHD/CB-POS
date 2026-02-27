from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.user_service import UserService


class ProfileDialog(QDialog):
    """Standalone dialog for user profile and PIN change."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Profile")
        self.setFixedSize(400, 300)
        self.setObjectName("ProfileDialog")
        self.init_ui()
        self.load_user()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel("Edit Profile")
        title.setObjectName("DialogTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        form.setVerticalSpacing(15)
        form.setHorizontalSpacing(20)

        self.input_name = QLineEdit()
        form.addRow("Display Name:", self.input_name)

        self.input_current_pin = QLineEdit()
        self.input_current_pin.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Current PIN:", self.input_current_pin)

        self.input_new_pin = QLineEdit()
        self.input_new_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_new_pin.setPlaceholderText("Leave empty to keep current")
        form.addRow("New PIN:", self.input_new_pin)

        layout.addLayout(form)

        self.btn_update = QPushButton("Update Profile")
        self.btn_update.setObjectName("BtnSave")
        self.btn_update.clicked.connect(self.update_profile)
        layout.addWidget(self.btn_update)

    def load_user(self):
        user = AuthService.get_current_user()
        if user:
            self.input_name.setText(user.username)

    def update_profile(self):
        user = AuthService.get_current_user()
        if not user:
            return

        current_pin = self.input_current_pin.text()
        new_pin = self.input_new_pin.text()
        display_name = self.input_name.text()

        if not current_pin:
            QMessageBox.warning(self, "Error", "Current PIN is required.")
            return

        verified_user = AuthService.verify_pin(current_pin)
        if not verified_user or verified_user.id != user.id:
            QMessageBox.critical(self, "Error", "Invalid Current PIN.")
            return

        success = UserService.update_user_profile(user.id, display_name, new_pin if new_pin else None)

        if success:
            QMessageBox.information(self, "Success", "Profile updated successfully.")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to update profile.")
