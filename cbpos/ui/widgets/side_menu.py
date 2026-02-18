from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor
from cbpos.ui.resources.icons import Icons


class MenuButton(QPushButton):
    """
    Flat button for the side menu.
    """

    def __init__(self, text: str, icon_name: str, is_destructive: bool = False):
        super().__init__()
        self.setText(f"  {text}")
        self.setObjectName("MenuButton")  # For CSS styling

        # Store the icon name and destructive flag for theme updates
        self.icon_name = icon_name
        self.is_destructive = is_destructive

        # Use theme service to get the correct color
        from cbpos.core.services.theme_service import ThemeService
        icon_color = "#FF4136" if is_destructive else ThemeService.get_icon_color()
        self.setIcon(Icons.get(icon_name, icon_color))
        self.setIconSize(QSize(24, 24))

        self.setFixedHeight(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Set property for CSS targeting
        if is_destructive:
            self.setProperty("destructive", True)


class IconButton(QPushButton):
    """
    Icon-only button for the bottom toolbar.
    """

    def __init__(self, icon_name: str, tooltip: str):
        super().__init__()
        self.setObjectName("IconButton")  # For CSS styling

        # Use theme service for icon color
        from cbpos.core.services.theme_service import ThemeService
        icon_color = ThemeService.get_icon_color()
        self.setIcon(Icons.get(icon_name, icon_color))
        self.setIconSize(QSize(24, 24))
        self.setToolTip(tooltip)
        self.setFixedSize(50, 50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class SideMenu(QWidget):
    # Signals
    management_clicked = pyqtSignal()
    history_clicked = pyqtSignal()
    documents_clicked = pyqtSignal()
    logout_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    fullscreen_clicked = pyqtSignal()
    power_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self.setVisible(False)
        self.setObjectName("POSSideMenu")  # For theme-specific styling

        # Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(-5)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

        # High Z-order to sit on top
        self.raise_()

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Section (Navigation)
        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 40, 0, 20)
        nav_layout.setSpacing(5)

        self.btn_management = MenuButton("Management", "fa5s.chart-line")
        self.btn_management.clicked.connect(self.management_clicked.emit)
        nav_layout.addWidget(self.btn_management)

        self.btn_history = MenuButton("Sales History", "fa5s.history")
        self.btn_history.clicked.connect(self.history_clicked.emit)
        nav_layout.addWidget(self.btn_history)

        self.btn_documents = MenuButton("Documents", "fa5s.file-invoice")
        self.btn_documents.clicked.connect(self.documents_clicked.emit)
        nav_layout.addWidget(self.btn_documents)

        nav_layout.addStretch()
        main_layout.addWidget(nav_container)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #003366; max-height: 1px;")
        main_layout.addWidget(line)

        # 2. Middle Section (User Profile)
        user_container = QWidget()
        user_layout = QVBoxLayout(user_container)
        user_layout.setContentsMargins(30, 30, 30, 30)
        user_layout.setSpacing(10)

        # Avatar
        self.lbl_avatar = QLabel()
        self.lbl_avatar.setPixmap(Icons.get("fa5s.user-circle", "#00BCEB").pixmap(64, 64))
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_layout.addWidget(self.lbl_avatar)

        # Name & Role
        self.lbl_username = QLabel("Guest")
        self.lbl_username.setObjectName("MenuUsername")
        self.lbl_username.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_layout.addWidget(self.lbl_username)

        self.lbl_role = QLabel("No Role")
        self.lbl_role.setObjectName("MenuRole")
        self.lbl_role.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_layout.addWidget(self.lbl_role)

        user_layout.addSpacing(20)

        # Logout
        self.btn_logout = MenuButton("Sign Out", "fa5s.sign-out-alt", is_destructive=True)
        self.btn_logout.clicked.connect(self.logout_clicked.emit)
        user_layout.addWidget(self.btn_logout)

        main_layout.addWidget(user_container)

        # Separator
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        line2.setStyleSheet("background-color: #003366; max-height: 1px;")
        main_layout.addWidget(line2)

        # 3. Bottom Section (System Toolbar)
        toolbar_container = QWidget()
        toolbar_container.setFixedHeight(80)
        toolbar_layout = QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(20, 0, 20, 0)
        toolbar_layout.setSpacing(20)
        toolbar_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_settings = IconButton("fa5s.cog", "Settings")
        self.btn_settings.clicked.connect(self.settings_clicked.emit)
        toolbar_layout.addWidget(self.btn_settings)

        self.btn_fullscreen = IconButton("fa5s.expand", "Toggle Fullscreen")
        self.btn_fullscreen.clicked.connect(self.fullscreen_clicked.emit)
        toolbar_layout.addWidget(self.btn_fullscreen)

        self.btn_power = IconButton("fa5s.power-off", "Exit Application")
        self.btn_power.clicked.connect(self.power_clicked.emit)
        toolbar_layout.addWidget(self.btn_power)

        main_layout.addWidget(toolbar_container)

    def set_user(self, user):
        """Update user info and permissions."""
        if user:
            self.lbl_username.setText(user.username)
            self.lbl_role.setText(user.role.name if user.role else "Unknown")

            # Permission Check (Simple role check for now, can be expanded)
            is_admin = user.role and user.role.name.lower() in [
                "admin",
                "manager",
                "owner",
            ]

            self.btn_management.setVisible(is_admin)
            self.btn_settings.setVisible(is_admin)
        else:
            self.lbl_username.setText("Guest")
            self.lbl_role.setText("Not Logged In")
            self.btn_management.setVisible(False)
            self.btn_settings.setVisible(False)
