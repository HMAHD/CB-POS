from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.permission_service import PermissionService
from cbpos.core.utils.display_labels import display_role_name
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.constants import ACTION_BTN_HEIGHT, SIDEBAR_WIDTH
from cbpos.ui.resources.icons import Icons
from cbpos.ui.utils.style_helpers import refresh_style


class NavTile(QPushButton):
    """Large navigation tile — icon above text, 2-column grid layout."""

    HEIGHT = 80
    COMPACT_HEIGHT = 60
    ICON_SIZE = 28
    COMPACT_ICON_SIZE = 22

    def __init__(self, text_key: str, icon_name: str, parent=None):
        """Build the icon-above-text tile layout.

        Args:
            text_key: i18n key for the label, applied by ``retranslate()``.
            icon_name: qtawesome icon name.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("NavTile")
        self.icon_name = icon_name
        self._text_key = text_key
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._icon_size = self.ICON_SIZE

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 12, 6, 8)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout = layout

        # Icon
        self.lbl_icon = QLabel()
        self.lbl_icon.setObjectName("NavTileIcon")
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
        self.lbl_text.setProperty("active", active)
        refresh_style(self)
        refresh_style(self.lbl_text)
        self._apply_theme()

    def _apply_theme(self) -> None:
        """Set icon pixmap directly (rendered from SVG)."""
        from cbpos.core.services.theme_service import ThemeService

        is_dark = ThemeService.current_theme.lower() == "dark"

        if self._active:
            icon_color = "#00BCEB" if is_dark else "#0D6EFD"
        else:
            icon_color = ThemeService.get_icon_color()

        pixmap = Icons.get(self.icon_name, icon_color).pixmap(self._icon_size, self._icon_size)
        self.lbl_icon.setPixmap(pixmap)

    def update_icon(self) -> None:
        """Public API for theme change callbacks."""
        self._apply_theme()

    def set_compact(self, compact: bool) -> None:
        """Use a shorter tile with a smaller icon and tighter padding (#590)."""
        self.setMinimumHeight(self.COMPACT_HEIGHT if compact else self.HEIGHT)
        if compact:
            self._layout.setContentsMargins(6, 6, 6, 6)
            self._layout.setSpacing(3)
        else:
            self._layout.setContentsMargins(6, 12, 6, 8)
            self._layout.setSpacing(6)
        self._icon_size = self.COMPACT_ICON_SIZE if compact else self.ICON_SIZE
        self._apply_theme()

    def retranslate(self) -> None:
        """Update text from translation key."""
        self.lbl_text.setText(_t(self._text_key))


class IconButton(QPushButton):
    """Icon-only button for the bottom toolbar."""

    def __init__(self, icon_name: str, tooltip_key: str, color: str | None = None):
        """Create a fixed-size icon-only toolbar button.

        Args:
            icon_name: qtawesome icon name.
            tooltip_key: i18n key for the tooltip, applied by ``retranslate()``.
            color: Optional fixed icon color; theme-based when omitted.
        """
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
    """Slide-in overlay menu: navigation tiles, user profile/sign-out block,
    and a bottom toolbar (settings/fullscreen/power). Hidden until shown by
    the owning window.
    """

    # Signals
    management_clicked = pyqtSignal()
    history_clicked = pyqtSignal()
    documents_clicked = pyqtSignal()
    receive_payment_clicked = pyqtSignal()
    reprint_receipt_clicked = pyqtSignal()
    refund_clicked = pyqtSignal()
    shift_clicked = pyqtSignal()
    logout_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    fullscreen_clicked = pyqtSignal()
    power_clicked = pyqtSignal()

    # A door reads as "leave"; power-off stays reserved for exiting the app.
    SIGN_OUT_ICON = "fa5s.door-open"

    # Below this height (1366x768 and 1024x768 screens) the tiles shrink so
    # more of them fit before the list has to scroll (#590).
    COMPACT_HEIGHT = 800
    TILE_SPACING = 20
    COMPACT_TILE_SPACING = 8

    def __init__(self, parent=None):
        """Build the menu (hidden until shown) and register for live language updates."""
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setVisible(False)
        self.setObjectName("POSSideMenu")
        self._user = None

        # Critical: QWidget doesn't paint QSS background without this
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # A QGraphicsDropShadowEffect used to sit here for a soft depth cue.
        # Removed (#524): it forces the *entire* panel through an offscreen
        # blur-composite pass on every repaint of any child, including a
        # single nav button's hover/pressed state change -- measured at a
        # ~35x repaint-cost increase (0.06ms -> 2.05ms per repaint) versus
        # no effect at all. The QSS border-left on #POSSideMenu still gives
        # a visible edge without that cost.

        self.raise_()
        self._nav_buttons: list[NavTile] = []
        self.is_compact = False
        self.init_ui()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def init_ui(self) -> None:
        """Lay out the nav tiles, user profile/sign-out block, and bottom toolbar."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Section Header ────────────────────────────────────────
        self.lbl_section = QLabel()
        self.lbl_section.setObjectName("MenuSectionHeader")
        self.lbl_section.setContentsMargins(16, 14, 0, 8)
        main_layout.addWidget(self.lbl_section)

        # ── Navigation Tiles (single column, scrollable) ─────────
        # The tiles scroll; the profile/Sign Out block and the toolbar
        # below sit outside the scroll area so they can never be clipped
        # on a short screen such as 1366x768 (#590).
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setObjectName("SideMenuScroll")
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        nav_container = QWidget()
        nav_container.setObjectName("SideMenuScrollInner")
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(10, 4, 10, 4)
        nav_layout.setSpacing(self.TILE_SPACING)
        self.nav_layout = nav_layout

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

        # One Shift tile: X-read, Cash In/Out and End Shift live in one dialog (#605)
        self.btn_shift = NavTile("side_menu.shift", "fa5s.user-clock")
        self.btn_shift.clicked.connect(self._on_shift)
        nav_layout.addWidget(self.btn_shift)
        self._nav_buttons.append(self.btn_shift)

        nav_layout.addStretch(1)
        self.nav_scroll.setWidget(nav_container)
        main_layout.addWidget(self.nav_scroll, 1)

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
        info_layout.setSpacing(4)

        self.lbl_username = QLabel()
        self.lbl_username.setObjectName("MenuUsername")
        info_layout.addWidget(self.lbl_username)

        self.lbl_role = QLabel()
        self.lbl_role.setObjectName("MenuRole")
        info_layout.addWidget(self.lbl_role)

        profile_row.addLayout(info_layout)
        profile_row.addStretch()

        block_layout.addLayout(profile_row)

        # Sign Out — one button carrying its own icon, so tapping the icon
        # or the text both sign out, with a touch-sized hit area (#607).
        signout_row = QHBoxLayout()
        signout_row.setContentsMargins(16, 0, 16, 0)

        self.btn_logout = QPushButton()
        self.btn_logout.setObjectName("SignOutBtn")
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logout.setIcon(Icons.get(self.SIGN_OUT_ICON, "#FF4136"))
        self.btn_logout.setIconSize(QSize(18, 18))
        self.btn_logout.setMinimumHeight(40)
        self.btn_logout.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_logout.clicked.connect(self.logout_clicked.emit)
        signout_row.addWidget(self.btn_logout)

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

    # ── Compact mode ──────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        """Switch to compact tiles on short screens, roomy tiles on tall ones."""
        super().resizeEvent(event)
        self.set_compact(event.size().height() < self.COMPACT_HEIGHT)

    def set_compact(self, compact: bool) -> None:
        """Shrink tiles and spacing so more tiles fit on a short screen.

        Args:
            compact: True for small tiles (60px, 8px apart), False for the
                normal ones (80px, 20px apart).
        """
        if compact == self.is_compact:
            return
        self.is_compact = compact
        self.nav_layout.setSpacing(self.COMPACT_TILE_SPACING if compact else self.TILE_SPACING)
        for tile in self._nav_buttons:
            tile.set_compact(compact)

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

    def _on_shift(self) -> None:
        self._set_active(self.btn_shift)
        self.shift_clicked.emit()

    # ── Translation ──────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        """Update all translatable widget text (called on language change)."""
        self.lbl_section.setText(_t("side_menu.menu_header"))
        if self._user:
            self.set_user(self._user)
        else:
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
        """Update user info and permissions; None shows Guest."""
        self._user = user
        if user:
            self.lbl_username.setText(user.username)
            self.lbl_role.setText(display_role_name(user.role) if user.role else _t("side_menu.unknown_role"))

            # By permission, never by role name: renaming a role must not change access (#549)
            self.btn_management.setVisible(PermissionService.can_open_management(user))
            self.btn_settings.setVisible(PermissionService.can_open_settings(user))
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

        self.btn_logout.setIcon(Icons.get(self.SIGN_OUT_ICON, "#FF4136"))

        for btn in [self.btn_settings, self.btn_fullscreen, self.btn_power]:
            btn.update_icon()

        self.lbl_avatar.setPixmap(Icons.get("fa5s.user-circle", "#00BCEB").pixmap(36, 36))
