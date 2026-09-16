from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.constants import ACTION_BTN_HEIGHT, SIDEBAR_WIDTH
from cbpos.ui.resources.icons import Icons


class NavTile(QPushButton):
    """Large navigation tile — icon above text, 2-column grid layout."""

    def __init__(self, text_key: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("NavTile")
        self.icon_name = icon_name
        self._text_key = text_key
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 12, 6, 8)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icon
        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_icon)

        # Text
        self.lbl_text = QLabel()
        self.lbl_text.setObjectName("NavTileText")
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_text.setWordWrap(True)
        layout.addWidget(self.lbl_text)

        self._apply_theme()

    def set_active(self, active: bool) -> None:
        """Toggle active state (highlighted border + accent color)."""
        self._active = active
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_theme()

    def _apply_theme(self) -> None:
        """Set icon and label colors directly — QSS can't cascade into QPushButton children."""
        from cbpos.core.services.theme_service import ThemeService

        is_dark = ThemeService.current_theme.lower() == "dark"

        if self._active:
            icon_color = "#00BCEB" if is_dark else "#0D6EFD"
            text_color = "#00BCEB" if is_dark else "#0D6EFD"
        else:
            icon_color = ThemeService.get_icon_color()
            text_color = "#CCCCCC" if is_dark else "#333333"

        pixmap = Icons.get(self.icon_name, icon_color).pixmap(28, 28)
        self.lbl_icon.setPixmap(pixmap)
        self.lbl_icon.setStyleSheet("background: transparent;")
        # Font size lives in QSS (#NavTileText, pt units so it scales with
        # Windows DPI settings — #207); only the active-state-dependent
        # color needs to be set here.
        self.lbl_text.setStyleSheet(f"color: {text_color}; background: transparent;")

    def update_icon(self) -> None:
        """Public API for theme change callbacks."""
        self._apply_theme()

    def retranslate(self) -> None:
        """Update text from translation key."""
        self.lbl_text.setText(_t(self._text_key))


class IconButton(QPushButton):
    """Icon-only button for the bottom toolbar."""

    def __init__(self, icon_name: str, tooltip_key: str, color: str | None = None):
        super().__init__()
        self.setObjectName("IconButton")

        self.icon_name = icon_name
        self._tooltip_key = tooltip_key
        self._fixed_color = color
        self.update_icon()
        self.setIconSize(QSize(20, 20))
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def update_icon(self) -> None:
        """Update icon color based on current theme."""
        from cbpos.core.services.theme_service import ThemeService

        if self._fixed_color:
            icon_color = self._fixed_color
        else:
            icon_color = ThemeService.get_icon_color()
        self.setIcon(Icons.get(self.icon_name, icon_color))

    def retranslate(self) -> None:
        """Update tooltip from translation key."""
        self.setToolTip(_t(self._tooltip_key))


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

        # Critical: QWidget doesn't paint QSS background without this
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setXOffset(-5)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 140))
        self.setGraphicsEffect(shadow)

        self.raise_()
        self._nav_buttons: list[NavTile] = []
        self.init_ui()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Section Header ────────────────────────────────────────
        self.lbl_section = QLabel()
        self.lbl_section.setObjectName("MenuSectionHeader")
        self.lbl_section.setContentsMargins(16, 14, 0, 8)
        main_layout.addWidget(self.lbl_section)

        # ── Navigation Tiles (single column) ─────────────────────
        nav_container = QWidget()
        nav_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(10, 4, 10, 4)
        nav_layout.setSpacing(20)

        self.btn_management = NavTile("side_menu.management", "fa5s.chart-line")
        self.btn_management.clicked.connect(self._on_management)
        nav_layout.addWidget(self.btn_management)
        self._nav_buttons.append(self.btn_management)

        self.btn_history = NavTile("side_menu.sales_history", "fa5s.history")
        self.btn_history.clicked.connect(self._on_history)
        nav_layout.addWidget(self.btn_history)
        self._nav_buttons.append(self.btn_history)

        self.btn_documents = NavTile("side_menu.documents", "fa5s.file-invoice")
        self.btn_documents.clicked.connect(self._on_documents)
        nav_layout.addWidget(self.btn_documents)
        self._nav_buttons.append(self.btn_documents)

        self.btn_receive_payment = NavTile("side_menu.receive_payment", "fa5s.hand-holding-usd")
        self.btn_receive_payment.clicked.connect(self._on_receive_payment)
        nav_layout.addWidget(self.btn_receive_payment)
        self._nav_buttons.append(self.btn_receive_payment)

        self.btn_reprint = NavTile("side_menu.reprint_receipt", "fa5s.print")
        self.btn_reprint.clicked.connect(self._on_reprint)
        nav_layout.addWidget(self.btn_reprint)
        self._nav_buttons.append(self.btn_reprint)

        self.btn_refund = NavTile("side_menu.refund", "fa5s.undo")
        self.btn_refund.clicked.connect(self._on_refund)
        nav_layout.addWidget(self.btn_refund)
        self._nav_buttons.append(self.btn_refund)

        main_layout.addWidget(nav_container)

        # ── Spacer ────────────────────────────────────────────────
        main_layout.addStretch(1)

        # ── Separator ─────────────────────────────────────────────
        main_layout.addWidget(self._make_separator())

        # ── User Profile + Sign Out (centered block) ────────────
        bottom_block = QWidget()
        bottom_block.setObjectName("UserProfileRow")
        bottom_block.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        block_layout = QVBoxLayout(bottom_block)
        block_layout.setContentsMargins(0, 12, 0, 8)
        block_layout.setSpacing(8)

        # Avatar + Name + Role — centered horizontally
        profile_row = QHBoxLayout()
        profile_row.setSpacing(10)
        profile_row.addStretch()

        self.lbl_avatar = QLabel()
        self.lbl_avatar.setFixedSize(36, 36)
        self.lbl_avatar.setPixmap(Icons.get("fa5s.user-circle", "#00BCEB").pixmap(36, 36))
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile_row.addWidget(self.lbl_avatar)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(1)

        self.lbl_username = QLabel()
        self.lbl_username.setObjectName("MenuUsername")
        info_layout.addWidget(self.lbl_username)

        self.lbl_role = QLabel()
        self.lbl_role.setObjectName("MenuRole")
        info_layout.addWidget(self.lbl_role)

        profile_row.addLayout(info_layout)
        profile_row.addStretch()

        block_layout.addLayout(profile_row)

        # Sign Out — centered horizontally
        signout_row = QHBoxLayout()
        signout_row.setSpacing(6)
        signout_row.addStretch()

        self.btn_logout_icon = QLabel()
        self.btn_logout_icon.setFixedSize(18, 18)
        self.btn_logout_icon.setPixmap(Icons.get("fa5s.sign-out-alt", "#FF4136").pixmap(16, 16))
        self.btn_logout_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_logout_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        signout_row.addWidget(self.btn_logout_icon)

        self.btn_logout = QPushButton()
        self.btn_logout.setObjectName("SignOutBtn")
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logout.setFixedHeight(28)
        self.btn_logout.clicked.connect(self.logout_clicked.emit)
        signout_row.addWidget(self.btn_logout)

        signout_row.addStretch()

        block_layout.addLayout(signout_row)

        main_layout.addWidget(bottom_block)

        # ── Separator ─────────────────────────────────────────────
        main_layout.addWidget(self._make_separator())

        # ── Bottom Toolbar ────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setObjectName("SideMenuToolbar")
        toolbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        toolbar.setFixedHeight(ACTION_BTN_HEIGHT)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(20, 0, 20, 0)
        toolbar_layout.setSpacing(0)

        self.btn_settings = IconButton("fa5s.cog", "side_menu.settings_tooltip")
        self.btn_settings.clicked.connect(self.settings_clicked.emit)
        toolbar_layout.addWidget(self.btn_settings)

        toolbar_layout.addStretch()

        self.btn_fullscreen = IconButton("fa5s.expand", "side_menu.fullscreen_tooltip")
        self.btn_fullscreen.clicked.connect(self.fullscreen_clicked.emit)
        toolbar_layout.addWidget(self.btn_fullscreen)

        toolbar_layout.addStretch()

        self.btn_power = IconButton("fa5s.power-off", "side_menu.exit_tooltip", color="#FF4136")
        self.btn_power.clicked.connect(self.power_clicked.emit)
        toolbar_layout.addWidget(self.btn_power)

        main_layout.addWidget(toolbar)

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _make_separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("MenuSeparator")
        line.setFixedHeight(1)
        return line

    def _set_active(self, btn: NavTile) -> None:
        """Highlight the clicked nav tile, clear others."""
        for b in self._nav_buttons:
            b.set_active(b is btn)

    # ── Click handlers (set active + emit signal) ────────────────

    def _on_management(self) -> None:
        self._set_active(self.btn_management)
        self.management_clicked.emit()

    def _on_history(self) -> None:
        self._set_active(self.btn_history)
        self.history_clicked.emit()

    def _on_documents(self) -> None:
        self._set_active(self.btn_documents)
        self.documents_clicked.emit()

    def _on_receive_payment(self) -> None:
        self._set_active(self.btn_receive_payment)
        self.receive_payment_clicked.emit()

    def _on_reprint(self) -> None:
        self._set_active(self.btn_reprint)
        self.reprint_receipt_clicked.emit()

    def _on_refund(self) -> None:
        self._set_active(self.btn_refund)
        self.refund_clicked.emit()

    # ── Translation ──────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        """Update all translatable widget text (called on language change)."""
        self.lbl_section.setText(_t("side_menu.menu_header"))
        self.lbl_username.setText(_t("side_menu.guest"))
        self.lbl_role.setText(_t("side_menu.no_role"))
        self.btn_logout.setText(_t("side_menu.sign_out"))

        for btn in self._nav_buttons:
            btn.retranslate()

        self.btn_settings.retranslate()
        self.btn_fullscreen.retranslate()
        self.btn_power.retranslate()

    # ── Public API ────────────────────────────────────────────────

    def set_user(self, user) -> None:
        """Update user info and permissions."""
        if user:
            self.lbl_username.setText(user.username)
            self.lbl_role.setText(user.role.name if user.role else _t("side_menu.unknown_role"))

            is_admin = user.role and user.role.name.lower() in [
                "admin",
                "manager",
                "owner",
            ]

            self.btn_management.setVisible(is_admin)
            self.btn_settings.setVisible(is_admin)
        else:
            self.lbl_username.setText(_t("side_menu.guest"))
            self.lbl_role.setText(_t("side_menu.not_logged_in"))
            self.btn_management.setVisible(False)
            self.btn_settings.setVisible(False)

    def clear_active(self) -> None:
        """Reset all nav tiles to inactive state."""
        for b in self._nav_buttons:
            b.set_active(False)

    def update_all_icons(self) -> None:
        """Update all icons in the side menu when theme changes."""
        for btn in self._nav_buttons:
            btn.update_icon()

        # Sign out icon
        self.btn_logout_icon.setPixmap(Icons.get("fa5s.sign-out-alt", "#FF4136").pixmap(16, 16))

        for btn in [self.btn_settings, self.btn_fullscreen, self.btn_power]:
            btn.update_icon()

        self.lbl_avatar.setPixmap(Icons.get("fa5s.user-circle", "#00BCEB").pixmap(36, 36))
