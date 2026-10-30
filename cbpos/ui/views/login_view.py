from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIntValidator, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cbpos.config import Config
from cbpos.core.services.auth_service import AuthService
from cbpos.i18n import _t, register_language_callback

# Numpad geometry constants
_BTN_SIZE = 90  # Default/initial button width/height — _fit_keypad() adjusts this
_BTN_SIZE_MIN = 56  # Still a comfortable touch target; only reached on very short windows
_BTN_SIZE_MAX = 110
_BTN_GAP = 12  # Spacing between buttons
_NUM_COLS = 3
_NUM_ROWS = 4
# Total numpad width: 3 buttons + 2 gaps
_NUMPAD_W = _NUM_COLS * _BTN_SIZE + (_NUM_COLS - 1) * _BTN_GAP
_LOGO_MAX = 300
_LOGO_MIN = 120  # Below this the logo is hidden instead of shrunk further
_FOOTER_MAX_W = 420


class _PinPanel(QWidget):
    """Right-hand login panel that reports its own resizes.

    The keypad is sized from *this* panel's height (#601), so the panel
    has to say when that height changes -- the screen size says nothing
    about how much room the window actually gives it.
    """

    resized = pyqtSignal()

    def resizeEvent(self, event) -> None:
        """Notify listeners after the panel has its new size."""
        super().resizeEvent(event)
        self.resized.emit()


class LoginView(QWidget):
    """PIN-entry login screen with a branding panel and on-screen numpad.

    Emits ``login_success`` with the authenticated user once a valid PIN
    is entered.
    """

    login_success = pyqtSignal(object)

    def __init__(self):
        """Build the UI and register the theme/language callbacks."""
        super().__init__()
        self.logo_label: QLabel | None = None  # Store reference for theme updates
        self._logo_source: QPixmap | None = None
        self._logo_side: int | None = None
        self._btn_size: int | None = _BTN_SIZE
        self.init_ui()

        # Register theme callback to update logo
        from cbpos.core.services.theme_service import ThemeService

        ThemeService.register_theme_callback(self.update_logo, owner=self)

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def init_ui(self):
        """Build the branding panel (logo, welcome text, tagline) and the PIN entry panel with numpad."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── LEFT PANEL (Branding) ──────────────────────────────────
        self.left_panel = QWidget()
        left_panel = self.left_panel
        left_panel.setObjectName("LoginLeftPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Logo
        self.logo_label = QLabel()
        self.update_logo()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Multilingual Welcome Text
        self.welcome_text = QLabel()
        self.welcome_text.setObjectName("WelcomeText")
        self.welcome_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        left_layout.addStretch()
        left_layout.addWidget(self.logo_label)
        left_layout.addWidget(self.welcome_text)
        left_layout.addStretch()

        # Tagline
        self.tagline = QLabel()
        self.tagline.setObjectName("LoginTagline")
        self.tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tagline.setWordWrap(True)
        left_layout.addWidget(self.tagline)
        left_layout.addSpacing(10)

        # Footer -- wraps instead of running across the whole (narrow)
        # branding panel on one line (#601).
        self.footer_label = QLabel()
        self.footer_label.setObjectName("FooterLabel")
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer_label.setWordWrap(True)
        self.footer_label.setMaximumWidth(_FOOTER_MAX_W)
        left_layout.addWidget(self.footer_label)
        left_layout.addSpacing(20)

        # ── RIGHT PANEL (Interaction) ──────────────────────────────
        self.right_panel = _PinPanel()
        right_panel = self.right_panel
        right_panel.setObjectName("LoginRightPanel")
        right_panel.resized.connect(self._fit_keypad)
        self._right_layout = QVBoxLayout(right_panel)
        right_layout = self._right_layout
        right_layout.setContentsMargins(40, 40, 40, 40)
        right_layout.setSpacing(0)

        # Heading, PIN field, keypad and hint form one group, centred
        # vertically by equal stretches above and below it -- not by an
        # AlignCenter on the whole panel layout mixed with fixed spacings,
        # which left a large empty band above the PIN field (#601).
        pin_group = QVBoxLayout()
        pin_group.setSpacing(0)
        self._pin_group = pin_group
        right_layout.addStretch(1)
        right_layout.addLayout(pin_group)
        right_layout.addStretch(1)

        # PIN Heading
        self.pin_heading = QLabel()
        self.pin_heading.setObjectName("PinHeading")
        self.pin_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pin_group.addWidget(self.pin_heading)
        pin_group.addSpacing(10)

        # Info Label for auto-held bills on logout/timeout
        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("LoginInfoLabel")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setFixedWidth(_NUMPAD_W)
        self.lbl_info.setVisible(False)
        pin_group.addWidget(self.lbl_info, alignment=Qt.AlignmentFlag.AlignCenter)
        pin_group.addSpacing(6)

        # PIN Display — width matches numpad
        self.pin_input = QLineEdit()
        self.pin_input.setObjectName("PinInput")
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_input.setFixedWidth(_NUMPAD_W)
        self.pin_input.setValidator(QIntValidator(0, 999999))
        self.pin_input.setMaxLength(6)
        self.pin_input.returnPressed.connect(self.attempt_login)
        pin_group.addWidget(self.pin_input, alignment=Qt.AlignmentFlag.AlignCenter)

        # Inline Error Label
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("LoginErrorLabel")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.setVisible(False)
        pin_group.addWidget(self.lbl_error)

        pin_group.addSpacing(15)

        # ── Numpad ─────────────────────────────────────────────────
        # Container constrains the grid to exact numpad width. Its minimum
        # is pinned explicitly to the *smallest* keypad (#601): left to
        # the grid layout, the minimum would follow the buttons' current
        # fixed size, the window could never get shorter than today's
        # keypad, and the bottom row (C / 0 / Enter) was pushed off-screen
        # instead of the keypad shrinking. A shrinkable policy lets the
        # panel hand it less room; _fit_keypad() then resizes the buttons.
        self.numpad_container = QWidget()
        numpad_container = self.numpad_container
        numpad_container.setObjectName("NumpadContainer")
        numpad_container.setFixedWidth(_NUMPAD_W)
        numpad_container.setMinimumHeight(_NUM_ROWS * _BTN_SIZE_MIN + (_NUM_ROWS - 1) * _BTN_GAP)
        numpad_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)

        self._numpad_grid = QGridLayout(numpad_container)
        grid = self._numpad_grid
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(_BTN_GAP)
        grid.setVerticalSpacing(_BTN_GAP)

        buttons = [
            ("1", 0, 0),
            ("2", 0, 1),
            ("3", 0, 2),
            ("4", 1, 0),
            ("5", 1, 1),
            ("6", 1, 2),
            ("7", 2, 0),
            ("8", 2, 1),
            ("9", 2, 2),
            ("C", 3, 0),
            ("0", 3, 1),
            ("\u23ce", 3, 2),
        ]

        self._numpad_buttons = []
        for text, row, col in buttons:
            btn = QPushButton(text)
            btn.setFixedSize(_BTN_SIZE, _BTN_SIZE)
            btn.setObjectName("NumpadBtn")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            if text == "C":
                btn.clicked.connect(self.clear_pin)
                btn.setProperty("btnType", "clear")
            elif text == "\u23ce":
                btn.clicked.connect(self.attempt_login)
                btn.setProperty("btnType", "enter")
            else:
                btn.clicked.connect(lambda checked, t=text: self.append_pin(t))

            grid.addWidget(btn, row, col)
            self._numpad_buttons.append(btn)

        pin_group.addWidget(numpad_container, alignment=Qt.AlignmentFlag.AlignCenter)

        # Help Hint
        pin_group.addSpacing(15)
        self.help_hint = QLabel()
        self.help_hint.setObjectName("LoginHelpHint")
        self.help_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pin_group.addWidget(self.help_hint)

        # ── Assemble panels ────────────────────────────────────────
        main_layout.addWidget(left_panel, 40)
        main_layout.addWidget(right_panel, 60)

        # Focus
        self.pin_input.setFocus()

        # Enter key shortcuts
        self.shortcut_enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self.shortcut_enter.activated.connect(self.attempt_login)
        self.shortcut_num_enter = QShortcut(QKeySequence(Qt.Key.Key_Enter), self)
        self.shortcut_num_enter.activated.connect(self.attempt_login)

        self._btn_size = _BTN_SIZE

    def resizeEvent(self, event) -> None:
        """Pick the panel layout for the window size and fit the logo.

        The keypad itself is sized by ``_fit_keypad()``, from the right
        panel's own resize -- see there.
        """
        super().resizeEvent(event)

        # Below ~1200px wide, the branding panel leaves too little room for
        # the numpad; hide it and let the right panel take the full width
        # (#220). Also tighten the right panel's margins on short windows so
        # the keypad gets as much of the height as possible.
        self.left_panel.setVisible(self.width() >= 1200)
        v_margin = 20 if self.height() < 900 else 40
        self._right_layout.setContentsMargins(40, v_margin, 40, v_margin)
        self._fit_logo()

    def _fit_logo(self) -> None:
        """Shrink the branding logo on short windows, hiding it when tiny (#601)."""
        source = self._logo_source
        if source is None or source.isNull():
            return
        # ~320px covers the welcome text, tagline, footer and spacing
        # around the logo in the branding column.
        side = min(_LOGO_MAX, self.height() - 320)
        if side < _LOGO_MIN:
            self.logo_label.setVisible(False)
            return
        self.logo_label.setVisible(True)
        if side != self._logo_side:
            self._logo_side = side
            self.logo_label.setPixmap(
                source.scaled(
                    side,
                    side,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def _fit_keypad(self) -> None:
        """Size the keypad from the room the right panel actually has (#601).

        It used to be keyed off the *screen* height, which says nothing
        about the window: with a title bar and taskbar on a 1366x768
        display, the C / 0 / Enter row ended up below the window's bottom
        edge. Sizing off the panel is not circular any more because the
        keypad container's minimum is pinned to the smallest keypad (see
        init_ui), so the panel's height comes from the window, not from
        the buttons' current size.
        """
        margins = self._right_layout.contentsMargins()
        # Everything in the PIN group except the keypad. The error label
        # is counted even while hidden, so showing "Invalid PIN" never
        # pushes the bottom row out.
        error_h = max(self.lbl_error.sizeHint().height(), self.lbl_error.fontMetrics().lineSpacing())
        other_h = (
            self.pin_heading.sizeHint().height()
            + 10
            + self.pin_input.sizeHint().height()
            + error_h
            + 15
            + 15
            + self.help_hint.sizeHint().height()
        )
        avail_h = self.right_panel.height() - margins.top() - margins.bottom() - other_h
        avail_w = self.right_panel.width() - margins.left() - margins.right()
        by_h = (avail_h - (_NUM_ROWS - 1) * _BTN_GAP) // _NUM_ROWS
        by_w = (avail_w - (_NUM_COLS - 1) * _BTN_GAP) // _NUM_COLS
        btn_size = max(_BTN_SIZE_MIN, min(_BTN_SIZE_MAX, by_h, by_w))

        if btn_size == self._btn_size:
            return
        self._btn_size = btn_size

        for btn in self._numpad_buttons:
            btn.setFixedSize(btn_size, btn_size)

        numpad_w = _NUM_COLS * btn_size + (_NUM_COLS - 1) * _BTN_GAP
        self.numpad_container.setFixedWidth(numpad_w)
        self.pin_input.setFixedWidth(numpad_w)

    def retranslate_ui(self) -> None:
        """Update all translatable widget text (called on language change)."""
        self.welcome_text.setText(_t("login.welcome"))
        self.tagline.setText(_t("login.subtitle"))
        self.footer_label.setText(_t("login.version_footer", version=Config.VERSION))
        self.pin_heading.setText(_t("login.enter_your_pin"))
        self.pin_input.setPlaceholderText(_t("login.enter_pin_placeholder"))
        self.help_hint.setText(_t("login.forgot_pin_hint"))
        if getattr(self, "_held_bill_id", None):
            self.lbl_info.setText(_t("login.bill_held", id=self._held_bill_id))

    def show_held_bill_notice(self, held_id: int) -> None:
        """Show a notice that an open cart was auto-held."""
        self._held_bill_id = held_id
        self.lbl_info.setText(_t("login.bill_held", id=held_id))
        self.lbl_info.setVisible(True)

    def clear_held_bill_notice(self) -> None:
        """Clear the held bill notice."""
        self._held_bill_id = None
        self.lbl_info.setVisible(False)

    # ── Events ─────────────────────────────────────────────────────

    def showEvent(self, event):
        """Force focus on PIN input when view becomes visible, checking lockout."""
        super().showEvent(event)
        lockout_secs = AuthService.get_terminal_lockout_seconds()
        if lockout_secs > 0:
            self._set_locked_state(True, lockout_secs)
        else:
            self.pin_input.setFocus()

    def _set_locked_state(self, locked: bool, seconds: int = 0) -> None:
        """Enable or disable the PIN input and numpad buttons based on lockout state."""
        self.pin_input.setEnabled(not locked)
        for btn in self._numpad_buttons:
            btn.setEnabled(not locked)

        if locked:
            self.lbl_error.setText(_t("login.locked", seconds=seconds))
            self.lbl_error.setVisible(True)
            if not hasattr(self, "_lockout_timer") or self._lockout_timer is None:
                self._lockout_timer = QTimer(self)
                self._lockout_timer.timeout.connect(self._on_lockout_tick)
            if not self._lockout_timer.isActive():
                self._lockout_timer.start(1000)
        else:
            if hasattr(self, "_lockout_timer") and self._lockout_timer is not None and self._lockout_timer.isActive():
                self._lockout_timer.stop()
            self.lbl_error.setVisible(False)
            self.pin_input.clear()
            self.pin_input.setFocus()

    def _on_lockout_tick(self) -> None:
        """Handle 1-second timer tick for lockout countdown."""
        lockout_secs = AuthService.get_terminal_lockout_seconds()
        if lockout_secs <= 0:
            self._set_locked_state(False)
        else:
            self.lbl_error.setText(_t("login.locked", seconds=lockout_secs))

    def keyPressEvent(self, event):
        """Route physical numpad digits to PIN input."""
        text = event.text()
        if text.isdigit():
            self.append_pin(text)
            event.accept()
            return
        super().keyPressEvent(event)

    # ── Actions ────────────────────────────────────────────────────

    def append_pin(self, digit: str) -> None:
        """Append digit to PIN input (called by numpad buttons)."""
        self.lbl_error.setVisible(False)
        current_text = self.pin_input.text()
        if len(current_text) < 6:
            self.pin_input.setText(current_text + digit)

    def clear_pin(self) -> None:
        """Clear the PIN input (called by the numpad's C button)."""
        self.lbl_error.setVisible(False)
        self.pin_input.clear()
        self.pin_input.setFocus()

    def attempt_login(self) -> None:
        """Verify the entered PIN and emit `login_success`, or show an error."""
        pin = self.pin_input.text()
        if not pin:
            return

        lockout_secs = AuthService.get_terminal_lockout_seconds()
        if lockout_secs > 0:
            self._set_locked_state(True, lockout_secs)
            return

        user = AuthService.login(pin)
        if user:
            self.clear_held_bill_notice()
            self.lbl_error.setVisible(False)
            self.login_success.emit(user)
        else:
            self.pin_input.clear()
            lockout_secs = AuthService.get_terminal_lockout_seconds()
            if lockout_secs > 0:
                self._set_locked_state(True, lockout_secs)
            else:
                remaining = AuthService.get_terminal_failures_remaining()
                if remaining <= 2:
                    self.lbl_error.setText(_t("login.attempts_left", count=remaining))
                else:
                    self.lbl_error.setText(_t("login.invalid_pin"))
                self.lbl_error.setVisible(True)
                self.pin_input.setFocus()

    def update_logo(self):
        """Update logo for login view (uses 02.png for both themes - navy background)."""
        if not hasattr(self, "logo_label") or self.logo_label is None:
            return

        logo_path = Config.BASE_DIR / "cbpos" / "assets" / "logo" / "02.png"

        if logo_path.exists():
            self._logo_source = QPixmap(str(logo_path))
            self._logo_side = None
            self._fit_logo()
        else:
            self.logo_label.setText(_t("login.logo_fallback"))
            self.logo_label.setObjectName("LogoText")
