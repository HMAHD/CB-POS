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
from cbpos.ui.constants import SIDEBAR_WIDTH, SIDEBAR_BUTTON_HEIGHT, ACTION_BTN_HEIGHT


class MenuButton(QPushButton):
    """Flat button for the side menu."""

    def __init__(self, text: str, icon_name: str, is_destructive: bool = False):
        super().__init__()
        self.setText(f"  {text}")
        self.setObjectName("MenuButton")

        self.icon_name = icon_name
        self.is_destructive = is_destructive

        self.update_icon()
        self.setIconSize(QSize(22, 22))
        self.setFixedHeight(SIDEBAR_BUTTON_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if is_destructive:
            self.setProperty("destructive", True)

    def update_icon(self):
        """Update icon color based on current theme."""
        from cbpos.core.services.theme_service import ThemeService

        icon_color = "#FF4136" if self.is_destructive else ThemeService.get_icon_color()
        self.setIcon(Icons.get(self.icon_name, icon_color))


class IconButton(QPushButton):
    """Icon-only button for the bottom toolbar."""

    def __init__(self, icon_name: str, tooltip: str):
        super().__init__()
        self.setObjectName("IconButton")

        self.icon_name = icon_name
        self.update_icon()
        self.setIconSize(QSize(22, 22))
        self.setToolTip(tooltip)
        self.setFixedSize(46, 46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def update_icon(self):
        """Update icon color based on current theme."""
        from cbpos.core.services.theme_service import ThemeService

        icon_color = ThemeService.get_icon_color()
        self.setIcon(Icons.get(self.icon_name, icon_color))


class SideMenu(QWidget):
    # Signals
    management_clicked = pyqtSignal()
    history_clicked = pyqtSignal()
    documents_clicked = pyqtSignal()
    receive_payment_clicked = pyqtSignal()
    reprint_receipt_clicked = pyqtSignal()
    refund_clicked = pyqtSignal()
    logout_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    fullscreen_clicked = pyqtSignal()
    power_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setVisible(False)
        self.setObjectName("POSSideMenu")

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setXOffset(-5)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        self.raise_()
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Navigation Section ─────────────────────────────────────
        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 16, 0, 8)
        nav_layout.setSpacing(2)

        self.btn_management = MenuButton("Management", "fa5s.chart-line")
        self.btn_management.clicked.connect(self.management_clicked.emit)
        nav_layout.addWidget(self.btn_management)

        self.btn_history = MenuButton("Sales History", "fa5s.history")
        self.btn_history.clicked.connect(self.history_clicked.emit)
        nav_layout.addWidget(self.btn_history)

        self.btn_documents = MenuButton("Documents", "fa5s.file-invoice")
        self.btn_documents.clicked.connect(self.documents_clicked.emit)
        nav_layout.addWidget(self.btn_documents)

        self.btn_receive_payment = MenuButton("Receive Payment", "fa5s.hand-holding-usd")
        self.btn_receive_payment.clicked.connect(self.receive_payment_clicked.emit)
        nav_layout.addWidget(self.btn_receive_payment)

        self.btn_reprint = MenuButton("Reprint Receipt", "fa5s.print")
        self.btn_reprint.clicked.connect(self.reprint_receipt_clicked.emit)
        nav_layout.addWidget(self.btn_reprint)

        self.btn_refund = MenuButton("Refund", "fa5s.undo")
        self.btn_refund.clicked.connect(self.refund_clicked.emit)
        nav_layout.addWidget(self.btn_refund)

        nav_layout.addStretch()
        main_layout.addWidget(nav_container)

        # ── Separator ──────────────────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("MenuSeparator")
        line.setFixedHeight(1)
        main_layout.addWidget(line)

        # ── User Profile Section ───────────────────────────────────
        user_container = QWidget()
        user_layout = QVBoxLayout(user_container)
        user_layout.setContentsMargins(20, 20, 20, 12)
        user_layout.setSpacing(6)

        # Avatar
        self.lbl_avatar = QLabel()
        self.lbl_avatar.setPixmap(Icons.get("fa5s.user-circle", "#00BCEB").pixmap(52, 52))
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

        main_layout.addWidget(user_container)

        # ── Sign Out ───────────────────────────────────────────────
        logout_container = QWidget()
        logout_layout = QVBoxLayout(logout_container)
        logout_layout.setContentsMargins(16, 0, 16, 8)
        logout_layout.setSpacing(0)

        self.btn_logout = MenuButton("Sign Out", "fa5s.sign-out-alt", is_destructive=True)
        self.btn_logout.clicked.connect(self.logout_clicked.emit)
        logout_layout.addWidget(self.btn_logout)

        main_layout.addWidget(logout_container)

        # ── Separator ──────────────────────────────────────────────
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setObjectName("MenuSeparator")
        line2.setFixedHeight(1)
        main_layout.addWidget(line2)

        # ── Bottom Toolbar ─────────────────────────────────────────
        toolbar_container = QWidget()
        toolbar_container.setFixedHeight(ACTION_BTN_HEIGHT)
        toolbar_layout = QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(20, 0, 20, 0)
        toolbar_layout.setSpacing(16)
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

    def update_all_icons(self):
        """Update all icons in the side menu when theme changes."""
        for btn in [
            self.btn_management,
            self.btn_history,
            self.btn_documents,
            self.btn_receive_payment,
            self.btn_reprint,
            self.btn_refund,
            self.btn_logout,
        ]:
            btn.update_icon()

        for btn in [self.btn_settings, self.btn_fullscreen, self.btn_power]:
            btn.update_icon()

        self.lbl_avatar.setPixmap(Icons.get("fa5s.user-circle", "#00BCEB").pixmap(52, 52))
