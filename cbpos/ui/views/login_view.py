from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QGridLayout,
    QSizePolicy,
    QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QIntValidator, QKeySequence, QShortcut
from cbpos.core.services.auth_service import AuthService
from cbpos.config import Config
from cbpos.i18n import _t, register_language_callback, unregister_language_callback

# Numpad geometry constants
_BTN_SIZE = 90  # Default/initial button width/height — resizeEvent adjusts this
_BTN_SIZE_MIN = 72
_BTN_SIZE_MAX = 110
_BTN_GAP = 12  # Spacing between buttons
_NUM_COLS = 3
_NUM_ROWS = 4
# Total numpad width: 3 buttons + 2 gaps
_NUMPAD_W = _NUM_COLS * _BTN_SIZE + (_NUM_COLS - 1) * _BTN_GAP


class LoginView(QWidget):
    login_success = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.logo_label = None  # Store reference for theme updates
        self.init_ui()

        # Register theme callback to update logo
        from cbpos.core.services.theme_service import ThemeService

        ThemeService.register_theme_callback(self.update_logo)

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def init_ui(self):
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

        # Footer
        self.footer_label = QLabel()
        self.footer_label.setObjectName("FooterLabel")
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.footer_label)
        left_layout.addSpacing(20)

        # ── RIGHT PANEL (Interaction) ──────────────────────────────
        self.right_panel = QWidget()
        right_panel = self.right_panel
        right_panel.setObjectName("LoginRightPanel")
        self._right_layout = QVBoxLayout(right_panel)
        right_layout = self._right_layout
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.setContentsMargins(40, 40, 40, 40)

        # PIN Heading
        self.pin_heading = QLabel()
        self.pin_heading.setObjectName("PinHeading")
        self.pin_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.pin_heading)
        right_layout.addSpacing(10)

        # PIN Display — width matches numpad
        self.pin_input = QLineEdit()
        self.pin_input.setObjectName("PinInput")
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_input.setFixedWidth(_NUMPAD_W)
        self.pin_input.setValidator(QIntValidator(0, 999999))
        self.pin_input.setMaxLength(6)
        self.pin_input.returnPressed.connect(self.attempt_login)
        right_layout.addWidget(self.pin_input, alignment=Qt.AlignmentFlag.AlignCenter)

        # Inline Error Label
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("LoginErrorLabel")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.setVisible(False)
        right_layout.addWidget(self.lbl_error)

        right_layout.addSpacing(15)

        # ── Numpad ─────────────────────────────────────────────────
        # Container constrains the grid to exact numpad width.
        self.numpad_container = QWidget()
        numpad_container = self.numpad_container
        numpad_container.setObjectName("NumpadContainer")
        numpad_container.setFixedWidth(_NUMPAD_W)
        numpad_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

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

        right_layout.addWidget(numpad_container, alignment=Qt.AlignmentFlag.AlignCenter)

        # Help Hint
        right_layout.addSpacing(15)
        self.help_hint = QLabel()
        self.help_hint.setObjectName("LoginHelpHint")
        self.help_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.help_hint)

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
        """Scale the numpad to the screen size instead of a fixed pixel size,
        so it stays usable from small screens to high-DPI displays (#199).

        Deliberately keyed off screen geometry, not self.right_panel.height():
        the numpad's own buttons are setFixedSize, so the panel's reported
        height can never shrink below what the *current* button size already
        demands — sizing off it would be circular and never actually shrink
        anything. Screen geometry has no such feedback loop.
        """
        super().resizeEvent(event)

        # Below ~1200px wide, the branding panel leaves too little room for
        # the numpad; hide it and let the right panel take the full width
        # (#220). Also tighten the right panel's margins on short windows so
        # the numpad doesn't get pushed into the help-hint text below it.
        self.left_panel.setVisible(self.width() >= 1200)
        v_margin = 20 if self.height() < 900 else 40
        self._right_layout.setContentsMargins(40, v_margin, 40, v_margin)

        screen = QApplication.primaryScreen().availableGeometry()
        # Reserve roughly the space taken by everything above/below the
        # numpad (heading, PIN field, error label, spacing, help hint) so
        # the button grid itself gets what's actually left.
        available_h = screen.height() - 260
        btn_size = max(_BTN_SIZE_MIN, min(_BTN_SIZE_MAX, available_h // _NUM_ROWS))

        if btn_size == getattr(self, "_btn_size", None):
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

    # ── Events ─────────────────────────────────────────────────────

    def showEvent(self, event):
        """Force focus on PIN input when view becomes visible."""
        super().showEvent(event)
        self.pin_input.setFocus()

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
        self.lbl_error.setVisible(False)
        self.pin_input.clear()
        self.pin_input.setFocus()

    def attempt_login(self) -> None:
        pin = self.pin_input.text()
        if not pin:
            return

        user = AuthService.verify_pin(pin)
        if user:
            self.lbl_error.setVisible(False)
            self.login_success.emit(user)
        else:
            self.pin_input.clear()
            self.lbl_error.setText(_t("login.invalid_pin"))
            self.lbl_error.setVisible(True)

    def update_logo(self):
        """Update logo for login view (uses 02.png for both themes - navy background)."""
        if not hasattr(self, "logo_label") or self.logo_label is None:
            return

        logo_path = Config.BASE_DIR / "cbpos" / "assets" / "logo" / "02.png"

        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            scaled_pixmap = pixmap.scaled(
                300,
                300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.logo_label.setPixmap(scaled_pixmap)
        else:
            self.logo_label.setText(_t("login.logo_fallback"))
            self.logo_label.setObjectName("LogoText")
