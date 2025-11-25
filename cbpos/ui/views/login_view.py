import os
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, 
    QPushButton, QGridLayout, QMessageBox, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QIntValidator
from cbpos.core.services.auth_service import AuthService
from cbpos.core.models import User
from cbpos.config import Config

class LoginView(QWidget):
    login_success = pyqtSignal(User)

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- LEFT PANEL (Branding) ---
        left_panel = QWidget()
        left_panel.setStyleSheet("background-color: #001226;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Logo
        logo_label = QLabel()
        # Config.BASE_DIR is project root. Assets are in cbpos/assets/logo
        logo_path = os.path.join(Config.BASE_DIR, "cbpos", "assets", "logo", "Logo_light.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scaled_pixmap = pixmap.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
        else:
            logo_label.setText("CB POS")
            logo_label.setObjectName("LogoText")
        
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Multilingual Welcome Text
        welcome_text = QLabel("Welcome / ආයුබෝවන් / வணக்கம்")
        welcome_text.setObjectName("Subtitle")
        welcome_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_text.setStyleSheet("font-size: 24px; color: #00BCEB; font-weight: bold; margin-top: 20px;")

        left_layout.addStretch()
        left_layout.addWidget(logo_label)
        left_layout.addWidget(welcome_text)
        left_layout.addStretch()

        # Footer
        footer_label = QLabel(f"Version {Config.VERSION} | © 2026 Ceylon Byte")
        footer_label.setStyleSheet("color: #888888; font-size: 12px;")
        footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(footer_label)
        left_layout.addSpacing(20)

        # --- RIGHT PANEL (Interaction) ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.setContentsMargins(50, 50, 50, 50)

        # PIN Display
        self.pin_input = QLineEdit()
        self.pin_input.setPlaceholderText("Enter PIN")
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setReadOnly(False) # Allow keyboard input
        self.pin_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_input.setFixedWidth(300)
        
        # Validator (Numbers only, max 4 digits)
        self.pin_input.setValidator(QIntValidator(0, 9999))
        self.pin_input.setMaxLength(4)
        
        # Handle Enter Key
        self.pin_input.returnPressed.connect(self.attempt_login)
        
        right_layout.addWidget(self.pin_input)
        right_layout.addSpacing(20)

        # Numpad Grid
        numpad_layout = QGridLayout()
        numpad_layout.setSpacing(10)

        buttons = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('C', 3, 0), ('0', 3, 1), ('⏎', 3, 2)
        ]

        for text, row, col in buttons:
            btn = QPushButton(text)
            btn.setFixedSize(80, 80)
            btn.setObjectName("NumpadBtn")
            
            if text == 'C':
                btn.clicked.connect(self.clear_pin)
                btn.setStyleSheet("color: #FF4136; border-color: #FF4136;")
            elif text == '⏎':
                btn.clicked.connect(self.attempt_login)
                btn.setStyleSheet("color: #39FF14; border-color: #39FF14;")
            else:
                btn.clicked.connect(lambda checked, t=text: self.append_pin(t))
            
            numpad_layout.addWidget(btn, row, col)

        right_layout.addLayout(numpad_layout)

        # Add panels to main layout
        main_layout.addWidget(left_panel, 40)
        main_layout.addWidget(right_panel, 60)
        
        # Set focus to input
        self.pin_input.setFocus()

    def append_pin(self, digit):
        current_text = self.pin_input.text()
        if len(current_text) < 4:
            self.pin_input.setText(current_text + digit)
            self.pin_input.setFocus() # Keep focus

    def clear_pin(self):
        self.pin_input.clear()
        self.pin_input.setFocus()

    def attempt_login(self):
        pin = self.pin_input.text()
        if not pin:
            return

        user = AuthService.verify_pin(pin)
        if user:
            self.login_success.emit(user)
        else:
            self.pin_input.clear()
            QMessageBox.warning(self, "Login Failed", "Invalid PIN. Please try again.")
