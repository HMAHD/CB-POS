from typing import List, Optional

from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QToolButton,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap
from cbpos.i18n import _t
from cbpos.ui.widgets.custom_widgets import SidebarButton
from cbpos.ui.resources.icons import Icons
from cbpos.core.services.theme_service import ThemeService
from cbpos.core.services.config_service import ConfigService

EXPANDED_WIDTH = 250
COLLAPSED_WIDTH = 70
ANIMATION_DURATION = 300
RESPONSIVE_BREAKPOINT = 1024


class CollapsibleSidebar(QFrame):
    """Reusable collapsible sidebar with logo, nav buttons, and POS/Logout bottom section.

    Used by ManagementView and SettingsView to avoid duplicating ~120 lines of
    identical sidebar construction, animation, and theme-update code.

    Signals:
        nav_clicked(int): Emitted when a navigation button is clicked, with its index.
        pos_clicked(): Emitted when the POS/Sales button is clicked.
        logout_clicked(): Emitted when the Logout button is clicked.
    """

    nav_clicked = pyqtSignal(int)
    pos_clicked = pyqtSignal()
    logout_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.is_collapsed = bool(ConfigService.get("sidebar_collapsed"))
        self.nav_buttons: List[SidebarButton] = []

        self.setFixedWidth(EXPANDED_WIDTH)
        self.setObjectName("SidebarContainer")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

        # --- Header (Logo + Toggle) ---
        header = QWidget()
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_logo = QLabel()
        self._load_logo()

        self.btn_toggle = QToolButton()
        icon_color = ThemeService.get_icon_color()
        self.btn_toggle.setIcon(Icons.get("fa5s.bars", icon_color))
        self.btn_toggle.setObjectName("SidebarToggle")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle)

        header_layout.addWidget(self.lbl_logo)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_toggle)

        self._layout.addWidget(header)
        self._layout.addSpacing(10)

        # Placeholder: nav buttons are added here by add_nav_button()
        # A stretch separates nav buttons from the bottom section.

        # --- Bottom Section (POS + Logout) ---
        self._bottom_widget = QWidget()
        self._bottom_widget.setObjectName("UserProfileContainer")
        bottom_layout = QVBoxLayout(self._bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        self.btn_pos = SidebarButton("", "fa5s.cash-register")
        self.btn_pos.setObjectName("BtnPos")
        self.btn_pos.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_pos.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_pos.clicked.connect(self.pos_clicked.emit)
        bottom_layout.addWidget(self.btn_pos)

        self.btn_logout = SidebarButton("", Icons.LOGOUT)
        self.btn_logout.setObjectName("BtnLogout")
        self.btn_logout.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_logout.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_logout.clicked.connect(self.logout_clicked.emit)
        bottom_layout.addWidget(self.btn_logout)

        bottom_layout.addSpacing(10)

        # Stretch + bottom are added after nav buttons in finalize()
        self._stretch_added = False

        # --- Animation ---
        self._anim_min = QPropertyAnimation(self, b"minimumWidth")
        self._anim_min.setDuration(ANIMATION_DURATION)
        self._anim_min.setEasingCurve(QEasingCurve.Type.InOutQuart)

        self._anim_max = QPropertyAnimation(self, b"maximumWidth")
        self._anim_max.setDuration(ANIMATION_DURATION)
        self._anim_max.setEasingCurve(QEasingCurve.Type.InOutQuart)

        # Register theme callback
        ThemeService.register_theme_callback(self._on_theme_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_nav_button(self, text: str, icon: str, index: int) -> SidebarButton:
        """Create and add a navigation button to the sidebar.

        Args:
            text: Button label.
            icon: qtawesome icon name (e.g. ``"fa5s.store"``).
            index: Stack index this button switches to.

        Returns:
            The created ``SidebarButton`` instance.
        """
        btn = SidebarButton(text, icon)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda checked=False, idx=index: self.nav_clicked.emit(idx))
        self._layout.addWidget(btn)
        self.nav_buttons.append(btn)
        return btn

    def finalize(self) -> None:
        """Call after all nav buttons have been added.

        Inserts the stretch and bottom section, applies initial collapsed
        state if needed, and refreshes styles.
        """
        if not self._stretch_added:
            self._layout.addStretch()
            self._layout.addWidget(self._bottom_widget)
            self._stretch_added = True

        if self.is_collapsed:
            self._apply_collapsed_state()

        self._update_all_styles()

    def highlight(self, index: int) -> None:
        """Highlight the nav button at *index* and deactivate all others."""
        for i, btn in enumerate(self.nav_buttons):
            is_active = i == index
            btn.set_active(is_active)
            btn.setProperty("active", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def retranslate_pos_logout(self) -> None:
        """Update POS and Logout button text from i18n.

        Called by the owning view's ``retranslate_ui`` method.
        """
        self.btn_pos.setText("   " + _t("management.sidebar_pos"))
        self.btn_logout.setText("   " + _t("management.sidebar_logout"))

    # ------------------------------------------------------------------
    # Collapse / Expand
    # ------------------------------------------------------------------

    def toggle(self) -> None:
        """Animate between expanded and collapsed states."""
        start = self.width()

        if self.is_collapsed:
            end = EXPANDED_WIDTH
            self.lbl_logo.setVisible(True)
            style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            self.is_collapsed = False
        else:
            end = COLLAPSED_WIDTH
            self.lbl_logo.setVisible(False)
            style = Qt.ToolButtonStyle.ToolButtonIconOnly
            self.is_collapsed = True

        ConfigService.set("sidebar_collapsed", self.is_collapsed)

        self._anim_min.setStartValue(start)
        self._anim_min.setEndValue(end)
        self._anim_min.start()

        self._anim_max.setStartValue(start)
        self._anim_max.setEndValue(end)
        self._anim_max.start()

        self._apply_button_style(style)
        self._update_all_styles()

    def set_collapsed(self, collapsed: bool) -> None:
        """Programmatically set collapsed state (e.g. for responsive layout)."""
        if collapsed == self.is_collapsed:
            return
        self.toggle()

    def handle_resize(self, width: int) -> None:
        """Auto-collapse/expand based on parent width.

        Call from the owning view's ``resizeEvent``. Collapses when below
        ``RESPONSIVE_BREAKPOINT`` and re-expands only if the user hasn't
        manually collapsed.
        """
        if width < RESPONSIVE_BREAKPOINT and not self.is_collapsed:
            self.set_collapsed(True)
        elif width >= RESPONSIVE_BREAKPOINT and self.is_collapsed:
            if not ConfigService.get("sidebar_collapsed"):
                self.set_collapsed(False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_collapsed_state(self) -> None:
        """Set sidebar to collapsed mode without animation (used at init)."""
        self.setFixedWidth(COLLAPSED_WIDTH)
        self.lbl_logo.setVisible(False)
        self._apply_button_style(Qt.ToolButtonStyle.ToolButtonIconOnly)

    def _apply_button_style(self, style: Qt.ToolButtonStyle) -> None:
        """Set the tool-button style on all buttons."""
        self.btn_pos.setToolButtonStyle(style)
        self.btn_logout.setToolButtonStyle(style)
        for btn in self.nav_buttons:
            btn.setToolButtonStyle(style)

    def _update_all_styles(self) -> None:
        """Refresh the ``collapsed`` QSS property on every button."""
        buttons = self.nav_buttons + [self.btn_pos, self.btn_logout]
        for btn in buttons:
            btn.setProperty("collapsed", self.is_collapsed)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _load_logo(self) -> None:
        """Load the logo image from the current theme."""
        logo_path = ThemeService.get_logo_path()
        logo_pixmap = QPixmap(logo_path)
        if not logo_pixmap.isNull():
            self.lbl_logo.setPixmap(logo_pixmap.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_logo.setText("")
            self.lbl_logo.setObjectName("SidebarLogo")

    def _on_theme_changed(self) -> None:
        """Refresh all icons and the logo when the theme changes."""
        buttons = self.nav_buttons + [self.btn_pos, self.btn_logout]
        for btn in buttons:
            if hasattr(btn, "update_icon"):
                btn.update_icon()

        icon_color = ThemeService.get_icon_color()
        self.btn_toggle.setIcon(Icons.get("fa5s.bars", icon_color))
        self._load_logo()
