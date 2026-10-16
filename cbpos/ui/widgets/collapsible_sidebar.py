from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.utils.style_helpers import refresh_style
from cbpos.ui.widgets.custom_widgets import SidebarButton

EXPANDED_WIDTH = 250
COLLAPSED_WIDTH = 70
ANIMATION_DURATION = 300
RESPONSIVE_BREAKPOINT = 1024

# Below this height (1366x768 and 1024x768 screens) nav buttons shrink so
# more fit before the list has to scroll (#591).
COMPACT_HEIGHT = 800
BUTTON_HEIGHT = 50
COMPACT_BUTTON_HEIGHT = 40
NAV_SPACING = 10
COMPACT_NAV_SPACING = 4


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

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the header, bottom POS/Logout section, and collapse animation.

        Restores the last-persisted collapsed state via ``ConfigService``.
        Call ``add_nav_button()``/``add_section_label()`` to populate the nav
        list, then ``finalize()`` once done.
        """
        super().__init__(parent)
        self.is_collapsed = bool(ConfigService.get("sidebar_collapsed"))
        self.nav_buttons: list[SidebarButton] = []
        self._section_labels: list[QLabel] = []
        self.is_compact = False

        self.setFixedWidth(EXPANDED_WIDTH)
        self.setObjectName("SidebarContainer")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

        # --- Header (Logo + Toggle) ---
        header = QWidget()
        header.setFixedHeight(60)
        self._header_layout = QHBoxLayout(header)
        # 18px horizontal margin per #608 (16-20px)
        self._header_layout.setContentsMargins(18, 10, 18, 10)

        self.lbl_logo = QLabel()
        self._load_logo()

        self.btn_toggle = QToolButton()
        icon_color = ThemeService.get_icon_color()
        self.btn_toggle.setIcon(Icons.get("fa5s.bars", icon_color))
        self.btn_toggle.setObjectName("SidebarToggle")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle)

        # Stretches allowing centering in collapsed state and right-alignment in expanded state
        self._header_layout.addStretch(0)  # index 0
        self._header_layout.addWidget(self.lbl_logo, 0, Qt.AlignmentFlag.AlignVCenter)  # index 1
        self._header_layout.addStretch(1)  # index 2
        self._header_layout.addWidget(self.btn_toggle, 0, Qt.AlignmentFlag.AlignVCenter)  # index 3
        self._header_layout.addStretch(0)  # index 4

        self._layout.addWidget(header)
        self._layout.addSpacing(10)

        # --- Nav list (scrollable) ---
        # add_nav_button()/add_section_label() fill this. It scrolls, while
        # POS/Logout below stay pinned outside it, so they can never be
        # clipped on a short screen such as 1366x768 (#591).
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setObjectName("SidebarNavScroll")
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_inner = QWidget()
        nav_inner.setObjectName("SidebarNavInner")
        self.nav_layout = QVBoxLayout(nav_inner)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(NAV_SPACING)
        self.nav_scroll.setWidget(nav_inner)
        self._layout.addWidget(self.nav_scroll, 1)

        # --- Bottom Section (POS + Logout) ---
        self._bottom_widget = QWidget()
        self._bottom_widget.setObjectName("UserProfileContainer")
        bottom_layout = QVBoxLayout(self._bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        # Pulls POS/Logout visually away from the nav list above, so they
        # read as a distinct "exit cluster" rather than two more rows in
        # the same list (#315).
        self._bottom_divider = QFrame()
        self._bottom_divider.setObjectName("SidebarBottomDivider")
        self._bottom_divider.setFixedHeight(1)
        bottom_layout.addWidget(self._bottom_divider)
        bottom_layout.addSpacing(8)

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
        if self.is_compact:
            btn.setFixedHeight(COMPACT_BUTTON_HEIGHT)
        self.nav_layout.addWidget(btn)
        self.nav_buttons.append(btn)
        return btn

    def add_section_label(self, text: str) -> QLabel:
        """Insert a subtle section-break label into the nav list.

        Gives the eye a resting point between groups of nav items (e.g.
        day-to-day operational screens vs. management/admin ones)
        instead of one flat, undifferentiated list (#315). The divider
        line above the text stays visible even when collapsed; only the
        text itself hides, since there's no room for it on the icon-only
        rail -- mirroring ``add_nav_button()``'s own collapsed handling.

        Args:
            text: Section name, upper-cased automatically.

        Returns:
            The created label -- callers should call ``.setText(...)``
            directly on it (upper-cased) to retranslate, same as any
            other label; this widget doesn't cache the original text.
        """
        wrapper = QWidget()
        wrapper.setObjectName("SidebarSectionWrapper")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)

        divider = QFrame()
        divider.setObjectName("SidebarSectionDivider")
        divider.setFixedHeight(1)
        wrapper_layout.addWidget(divider)

        label = QLabel(text.upper())
        label.setObjectName("SidebarSectionLabel")
        wrapper_layout.addWidget(label)

        self.nav_layout.addWidget(wrapper)
        self._section_labels.append(label)
        return label

    def finalize(self) -> None:
        """Call after all nav buttons have been added.

        Inserts the stretch and bottom section, applies initial collapsed
        state if needed, and refreshes styles.
        """
        if not self._stretch_added:
            self.nav_layout.addStretch()
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
            refresh_style(btn)

    def retranslate_pos_logout(self) -> None:
        """Update POS and Logout button text from i18n.

        Called by the owning view's ``retranslate_ui`` method.
        """
        self.btn_pos.setText(_t("management.sidebar_pos"))
        self.btn_logout.setText(_t("management.sidebar_logout"))

    # ------------------------------------------------------------------
    # Collapse / Expand
    # ------------------------------------------------------------------

    def toggle(self) -> None:
        """Animate between expanded and collapsed states (manual user action -- persisted)."""
        self._apply_collapse(not self.is_collapsed, persist=True)

    def set_collapsed(self, collapsed: bool) -> None:
        """Programmatically set collapsed state (e.g. for responsive layout).

        Unlike ``toggle()``, this does not persist the change as a user
        preference -- a transient, automatic layout adjustment (see
        ``handle_resize()``) must never masquerade as the user's own
        explicit collapse/expand choice (#276), or a later, valid resize
        can never undo it.
        """
        if collapsed == self.is_collapsed:
            return
        self._apply_collapse(collapsed, persist=False)

    def _apply_collapse(self, collapsed: bool, persist: bool) -> None:
        """Animate to the given collapsed state, optionally persisting it."""
        start = self.width()

        if collapsed:
            end = COLLAPSED_WIDTH
            self.lbl_logo.setVisible(False)
            self._header_layout.setContentsMargins(0, 10, 0, 10)
            self._header_layout.setStretch(0, 1)
            self._header_layout.setStretch(2, 0)
            self._header_layout.setStretch(4, 1)
            self._header_layout.invalidate()
            style = Qt.ToolButtonStyle.ToolButtonIconOnly
        else:
            end = EXPANDED_WIDTH
            self.lbl_logo.setVisible(True)
            self._header_layout.setContentsMargins(18, 10, 18, 10)
            self._header_layout.setStretch(0, 0)
            self._header_layout.setStretch(2, 1)
            self._header_layout.setStretch(4, 0)
            self._header_layout.invalidate()
            style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon

        self.is_collapsed = collapsed

        if persist:
            ConfigService.set("sidebar_collapsed", self.is_collapsed)

        self._anim_min.setStartValue(start)
        self._anim_min.setEndValue(end)
        self._anim_min.start()

        self._anim_max.setStartValue(start)
        self._anim_max.setEndValue(end)
        self._anim_max.start()

        self._apply_button_style(style)
        self._update_all_styles()

    def resizeEvent(self, event) -> None:
        """Switch to compact buttons on short screens, normal ones on tall screens."""
        super().resizeEvent(event)
        self.set_compact(event.size().height() < COMPACT_HEIGHT)

    def set_compact(self, compact: bool) -> None:
        """Shrink nav and POS/Logout buttons and their spacing on a short screen.

        Args:
            compact: True for 40px buttons 4px apart, False for 50px buttons 10px apart.
        """
        if compact == self.is_compact:
            return
        self.is_compact = compact
        self.nav_layout.setSpacing(COMPACT_NAV_SPACING if compact else NAV_SPACING)
        height = COMPACT_BUTTON_HEIGHT if compact else BUTTON_HEIGHT
        for btn in [*self.nav_buttons, self.btn_pos, self.btn_logout]:
            btn.setFixedHeight(height)
            btn.setProperty("compact", compact)
            refresh_style(btn)

    def handle_resize(self, width: int) -> None:
        """Auto-collapse/expand based on parent width.

        Call from the owning view's ``resizeEvent``. Collapses when below
        ``RESPONSIVE_BREAKPOINT`` and re-expands only if the user hasn't
        manually collapsed.
        """
        if width <= 0:
            return
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
        self._header_layout.setContentsMargins(0, 10, 0, 10)
        self._header_layout.setStretch(0, 1)
        self._header_layout.setStretch(2, 0)
        self._header_layout.setStretch(4, 1)
        self._header_layout.invalidate()
        self._apply_button_style(Qt.ToolButtonStyle.ToolButtonIconOnly)

    def _is_toggle_centered_when_collapsed(self) -> bool:
        """Return True if toggle is centered when collapsed."""
        if not self.is_collapsed:
            return False
        margins = self._header_layout.contentsMargins()
        return (
            margins.left() == margins.right()
            and self._header_layout.stretch(0) == self._header_layout.stretch(4)
            and self._header_layout.stretch(0) > 0
        )

    def _apply_button_style(self, style: Qt.ToolButtonStyle) -> None:
        """Set the tool-button style on all buttons.

        Also refreshes each button's icon, since SidebarButton pads its
        icon pixmap differently depending on whether it's showing text
        beside the icon or collapsed to icon-only (#314).
        """
        buttons = [self.btn_pos, self.btn_logout, *self.nav_buttons]
        for btn in buttons:
            btn.setToolButtonStyle(style)
            btn.update_icon()

    def _update_all_styles(self) -> None:
        """Refresh the ``collapsed`` QSS property on every button."""
        buttons = [*self.nav_buttons, self.btn_pos, self.btn_logout]
        for btn in buttons:
            btn.setProperty("collapsed", self.is_collapsed)
            refresh_style(btn)

        # Section-label text has no room on the icon-only rail; the
        # divider line above each one stays visible either way.
        for label in self._section_labels:
            label.setVisible(not self.is_collapsed)

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
        buttons = [*self.nav_buttons, self.btn_pos, self.btn_logout]
        for btn in buttons:
            if hasattr(btn, "update_icon"):
                btn.update_icon()

        icon_color = ThemeService.get_icon_color()
        self.btn_toggle.setIcon(Icons.get("fa5s.bars", icon_color))
        self._load_logo()
