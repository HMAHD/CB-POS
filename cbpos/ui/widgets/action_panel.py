import weakref

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.theme_service import ThemeService
from cbpos.core.utils.formatters import format_short_name
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.elided_label import ElidedLabel

_BTN_H = 70


class ActionBtn(QPushButton):
    """Action tile — shortcut top-left, icon center, label bottom."""

    def __init__(self, shortcut_text, label_key, icon_name=None, color=None, parent=None):
        """Build the tile layout: shortcut label, icon, and text.

        Args:
            shortcut_text: Keyboard shortcut shown top-left (e.g. "F2"); empty for none.
            label_key: i18n key for the bottom label, applied by ``retranslate()``.
            icon_name: qtawesome icon name shown in the center.
            color: Optional ``btnColor`` QSS property value for tinting.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("ActionGridBtn")
        self._icon_name = icon_name
        self._label_key = label_key

        self.setFixedHeight(_BTN_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QGridLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(0)
        layout.setRowStretch(0, 0)
        layout.setRowStretch(1, 1)
        layout.setRowStretch(2, 0)

        # Shortcut badge (top-left). Kept apart from the translated label so
        # no translation can drop the key (#604); sized to its text so the
        # QSS chip background hugs the key instead of filling the row.
        self.lbl_shortcut = QLabel(shortcut_text)
        self.lbl_shortcut.setObjectName("lblShortcut")
        self.lbl_shortcut.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_shortcut.setVisible(bool(shortcut_text))
        layout.addWidget(self.lbl_shortcut, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # Icon (Center)
        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_icon, 1, 0)

        # Label (Bottom)
        self.lbl_text = QLabel()
        self.lbl_text.setObjectName("lblText")
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(self.lbl_text, 2, 0)

        self._apply_theme_styles(icon_name)

        if color:
            self.setProperty("btnColor", color)

    def _apply_theme_styles(self, icon_name: str | None = None) -> None:
        """Apply the theme-dependent icon color.

        Label colors come from the theme QSS (#lblText/#lblShortcut in
        dark.qss and light.qss), so they follow whichever stylesheet is
        active; only the icon -- a pre-rendered pixmap -- has to be
        re-tinted here (#603).
        """
        self.lbl_icon.setObjectName("lblIcon")
        self.lbl_icon.setStyleSheet("background: transparent;")
        self.set_icon(icon_name)

    def set_icon(self, icon_name: str | None) -> None:
        """Set icon with theme-aware color."""
        if icon_name:
            is_dark = ThemeService.current_theme.lower() == "dark"
            icon_color = "white" if is_dark else "#1A1A1A"
            icon = Icons.get(icon_name, color=icon_color)
            self.lbl_icon.setPixmap(icon.pixmap(28, 28))

    def refresh_theme(self) -> None:
        """Re-apply theme colors (called when theme changes)."""
        self._apply_theme_styles(self._icon_name)

    def retranslate(self) -> None:
        """Update label text from translation key."""
        self.lbl_text.setText(_t(self._label_key))


class SectionLabel(QLabel):
    """Section header label for grouping action buttons."""

    def __init__(self, text_key: str, parent=None):
        """Create a section label bound to an i18n key.

        Args:
            text_key: i18n key applied by ``retranslate()``.
            parent: Optional parent widget.
        """
        super().__init__(parent=parent)
        self._text_key = text_key
        self.setObjectName("ActionSectionLabel")

    def retranslate(self) -> None:
        """Update text from translation key."""
        self.setText(_t(self._text_key))


class ActionPanel(QWidget):
    """Right-side control panel for Sales View."""

    customer_clicked = pyqtSignal()
    customer_cleared = pyqtSignal()
    pay_clicked = pyqtSignal()

    action_f2 = pyqtSignal()
    action_f3 = pyqtSignal()
    action_f4 = pyqtSignal()
    action_f6 = pyqtSignal()
    action_f7 = pyqtSignal()
    action_f8 = pyqtSignal()
    action_del = pyqtSignal()
    action_ref = pyqtSignal()

    def __init__(self, parent=None):
        """Build the panel and register for live language updates."""
        super().__init__(parent)
        self._section_labels: list[SectionLabel] = []
        self._action_btns: list[ActionBtn] = []
        self._has_customer = False
        self.init_ui()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        # weakref avoids a self -> destroyed-connection -> lambda -> self
        # reference cycle that only a full gc.collect() can break, which
        # can segfault mid-teardown (#392).
        self_ref = weakref.ref(self)

        # Re-tint the tile icons if the theme changes under a live panel
        # (#603). Held through the weakref too: ThemeService's callback
        # list is class-level and would otherwise keep the panel alive.
        def _on_theme_changed():
            widget = self_ref()
            if widget is not None:
                widget.refresh_theme()

        ThemeService.register_theme_callback(_on_theme_changed)

        def _unregister():
            ThemeService.unregister_theme_callback(_on_theme_changed)
            widget = self_ref()
            if widget is not None:
                unregister_language_callback(widget.retranslate_ui)

        self.destroyed.connect(_unregister)

    def refresh_theme(self) -> None:
        """Re-tint every action tile's icon for the current theme."""
        for btn in self._action_btns:
            btn.refresh_theme()

    def init_ui(self):
        """Lay out the customer card, action button grids, and pay button."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        # ── 1. Customer Card ─────────────────────────────────────
        # Three internal rows: row 1 is icon + name/phone (full card
        # width, so a long name/translated phone gets real room instead
        # of being squeezed against a fixed-width button); row 2 is the
        # Select/Clear controls; row 3 (#255) is the loyalty-points
        # badge -- all inside the same frame/border instead of floating
        # below it as unrelated sibling widgets.
        customer_frame = QFrame()
        customer_frame.setObjectName("CustomerPanel")
        customer_frame_layout = QVBoxLayout(customer_frame)
        customer_frame_layout.setContentsMargins(10, 10, 10, 10)
        customer_frame_layout.setSpacing(8)

        cust_layout = QHBoxLayout()
        cust_layout.setContentsMargins(0, 0, 0, 0)
        cust_layout.setSpacing(10)

        # Customer icon
        self.lbl_cust_icon = QLabel()
        self.lbl_cust_icon.setFixedSize(32, 32)
        self.lbl_cust_icon.setPixmap(Icons.get(Icons.CUSTOMER, "#00BCEB").pixmap(28, 28))
        self.lbl_cust_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cust_icon.setStyleSheet("background: transparent;")
        cust_layout.addWidget(self.lbl_cust_icon)

        # Customer info (name + subtitle). ElidedLabel keeps a long name
        # from silently overflowing past the card's edge with no visual
        # indication or way to read the rest -- the full string stays
        # available as a tooltip and via .text(). Now the only other
        # thing sharing this row is the icon, so it gets the full card
        # width instead of being cut down to a handful of characters by
        # a same-row Select button (worse still with long translated
        # button labels, e.g. Sinhala/Tamil).
        cust_info = QVBoxLayout()
        cust_info.setSpacing(0)
        self.lbl_cust_title = QLabel()
        self.lbl_cust_title.setObjectName("CustTitle")
        cust_info.addWidget(self.lbl_cust_title)
        self.lbl_customer = ElidedLabel()
        self.lbl_customer.setObjectName("CustomerLabel")
        cust_info.addWidget(self.lbl_customer)
        cust_layout.addLayout(cust_info, 1)

        customer_frame_layout.addLayout(cust_layout)

        # Row 2: Select (grows to fill) + Clear (fixed, only once a real
        # customer is selected) -- its own full-width row instead of
        # squeezed into row 1, and a bigger touch target to match the
        # rest of the panel's touch-friendly controls.
        cust_btn_row = QHBoxLayout()
        cust_btn_row.setContentsMargins(0, 0, 0, 0)
        cust_btn_row.setSpacing(8)

        self.btn_cust_select = QPushButton()
        self.btn_cust_select.setObjectName("BtnCustomerSelect")
        self.btn_cust_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cust_select.setMinimumHeight(32)
        self.btn_cust_select.clicked.connect(self.customer_clicked.emit)
        cust_btn_row.addWidget(self.btn_cust_select, 1)

        # Manual reset to Walk-in Customer -- previously only reachable
        # through a right-click context menu on the name, easy to miss.
        # Only visible once a real customer is actually selected.
        self.btn_cust_clear = QPushButton()
        self.btn_cust_clear.setObjectName("BtnCustomerClear")
        self.btn_cust_clear.setIcon(Icons.get("fa5s.user-slash", "#888888"))
        self.btn_cust_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cust_clear.setFixedSize(32, 32)
        self.btn_cust_clear.setToolTip(_t("action_panel.clear_customer"))
        self.btn_cust_clear.clicked.connect(self.customer_cleared.emit)
        self.btn_cust_clear.setVisible(False)
        cust_btn_row.addWidget(self.btn_cust_clear)

        customer_frame_layout.addLayout(cust_btn_row)

        # Row 2: divider + points badge, hidden entirely for Walk-in
        # Customer (no loyalty points) instead of just clearing the text,
        # so the default state doesn't reserve a blank strip of space.
        self.points_divider = QFrame()
        self.points_divider.setObjectName("PointsDivider")
        self.points_divider.setFixedHeight(1)
        self.points_divider.setVisible(False)
        customer_frame_layout.addWidget(self.points_divider)

        self.points_row = QWidget()
        # A plain QWidget paints the app's global background color (Qt's
        # global "QWidget { background-color: ... }" rule) instead of
        # letting the parent CustomerPanel's surface color show through --
        # it needs its own objectName to opt out of that with a targeted
        # "background: transparent" rule.
        self.points_row.setObjectName("PointsRow")
        points_row_layout = QHBoxLayout(self.points_row)
        points_row_layout.setContentsMargins(0, 6, 0, 0)
        points_row_layout.setSpacing(6)
        # Indent to line up under the name, not under the icon above it
        # (icon width 32px + the row's own 10px spacing).
        points_row_layout.addSpacing(42)

        self.lbl_points_icon = QLabel()
        self.lbl_points_icon.setPixmap(Icons.get(Icons.POINTS, "#FFDC00").pixmap(12, 12))
        self.lbl_points_icon.setStyleSheet("background: transparent;")
        points_row_layout.addWidget(self.lbl_points_icon)

        self.lbl_points = QLabel("")
        self.lbl_points.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_points.setObjectName("PointsLabel")
        points_row_layout.addWidget(self.lbl_points)
        points_row_layout.addStretch()
        self.points_row.setVisible(False)
        customer_frame_layout.addWidget(self.points_row)

        layout.addWidget(customer_frame)

        # ── 2. Orders Section ────────────────────────────────────
        layout.addSpacing(10)
        self.section_orders = SectionLabel("action_panel.section_orders")
        self._section_labels.append(self.section_orders)
        layout.addWidget(self.section_orders)
        layout.addSpacing(4)

        orders_grid = QGridLayout()
        orders_grid.setSpacing(6)

        self.btn_f2 = ActionBtn("F2", "action_panel.btn_customer", Icons.CUSTOMERS)
        self.btn_f2.clicked.connect(self.action_f2.emit)
        orders_grid.addWidget(self.btn_f2, 0, 0)
        self._action_btns.append(self.btn_f2)

        self.btn_f3 = ActionBtn("F3", "action_panel.btn_search", Icons.SEARCH)
        self.btn_f3.clicked.connect(self.action_f3.emit)
        orders_grid.addWidget(self.btn_f3, 0, 1)
        self._action_btns.append(self.btn_f3)

        self.btn_f4 = ActionBtn("F4", "action_panel.btn_qty", Icons.EDIT)
        self.btn_f4.clicked.connect(self.action_f4.emit)
        orders_grid.addWidget(self.btn_f4, 1, 0)
        self._action_btns.append(self.btn_f4)

        self.btn_f6 = ActionBtn("F6", "action_panel.btn_hold", Icons.HOLD, "#FFDC00")
        self.btn_f6.clicked.connect(self.action_f6.emit)
        orders_grid.addWidget(self.btn_f6, 1, 1)
        self._action_btns.append(self.btn_f6)

        layout.addLayout(orders_grid)

        # ── 3. Transaction Section ───────────────────────────────
        layout.addSpacing(10)
        self.section_transaction = SectionLabel("action_panel.section_transaction")
        self._section_labels.append(self.section_transaction)
        layout.addWidget(self.section_transaction)
        layout.addSpacing(4)

        txn_grid = QGridLayout()
        txn_grid.setSpacing(6)

        self.btn_f7 = ActionBtn("F7", "action_panel.btn_recall", Icons.RECALL)
        self.btn_f7.clicked.connect(self.action_f7.emit)
        txn_grid.addWidget(self.btn_f7, 0, 0)
        self._action_btns.append(self.btn_f7)

        self.btn_f8 = ActionBtn("F8", "action_panel.btn_drawer", Icons.DRAWER)
        self.btn_f8.clicked.connect(self.action_f8.emit)
        txn_grid.addWidget(self.btn_f8, 0, 1)
        self._action_btns.append(self.btn_f8)

        self.btn_del = ActionBtn("Del", "action_panel.btn_void", Icons.VOID, "#FF4136")
        self.btn_del.clicked.connect(self.action_del.emit)
        txn_grid.addWidget(self.btn_del, 1, 0)
        self._action_btns.append(self.btn_del)

        # No keyboard shortcut for Refund -- the old "Ref" badge looked like
        # a key that doesn't exist.
        self.btn_ref = ActionBtn("", "action_panel.btn_refund", Icons.HISTORY, "#FF4136")
        self.btn_ref.clicked.connect(self.action_ref.emit)
        txn_grid.addWidget(self.btn_ref, 1, 1)
        self._action_btns.append(self.btn_ref)

        layout.addLayout(txn_grid)

        # ── 4. Spacer + Pay Button ───────────────────────────────
        layout.addStretch()

        self.btn_pay = QPushButton()
        self.btn_pay.setFixedHeight(56)
        self.btn_pay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pay.setObjectName("BtnPay")
        self.btn_pay.clicked.connect(self.pay_clicked.emit)
        self._apply_pay_icon()
        # F5 as its own badge, not inside the translated "Pay" text, which
        # Sinhala/Tamil had dropped (#604).
        pay_layout = QHBoxLayout(self.btn_pay)
        pay_layout.setContentsMargins(0, 0, 12, 0)
        pay_layout.addStretch()
        self.lbl_pay_shortcut = QLabel("F5")
        self.lbl_pay_shortcut.setObjectName("lblShortcut")
        self.lbl_pay_shortcut.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pay_layout.addWidget(self.lbl_pay_shortcut, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.btn_pay)

    def _apply_pay_icon(self) -> None:
        """Set pay button icon."""
        icon = Icons.get("fa5s.cash-register", "white")
        self.btn_pay.setIcon(icon)

    def retranslate_ui(self) -> None:
        """Update all translatable widget text (called on language change)."""
        self.lbl_cust_title.setText(_t("action_panel.customer_title"))
        # A language switch used to always overwrite the name field with
        # "Walk-in Customer," even while a real customer was selected --
        # only re-apply the placeholder text when there's genuinely no
        # customer selected right now.
        if not self._has_customer:
            self.lbl_customer.setText(_t("action_panel.walk_in_customer"))
        self.btn_cust_select.setText(_t("action_panel.select_customer"))
        self.btn_cust_clear.setToolTip(_t("action_panel.clear_customer"))
        self.btn_pay.setText(_t("action_panel.btn_pay"))

        for lbl in self._section_labels:
            lbl.retranslate()

        for btn in self._action_btns:
            btn.retranslate()

    def set_customer_info(self, name, phone, points):
        """Show the selected customer's short name, points, and clear button.

        Args:
            name: Customer's full name (shown elided; full name + phone as tooltip).
            phone: Customer's phone number, included in the tooltip if present.
            points: Loyalty points balance shown in the points row.
        """
        self._has_customer = True
        # The full name + phone is still there on hover -- the card only
        # has room for a short label, and a phone number adds little at
        # a glance once a customer is already selected.
        self.lbl_customer.setText(format_short_name(name))
        self.lbl_customer.setToolTip(f"{name} ({phone})" if phone else name)
        self.lbl_points.setText(_t("action_panel.points", points=points))
        self.points_divider.setVisible(True)
        self.points_row.setVisible(True)
        self.btn_cust_clear.setVisible(True)

    def clear_customer_info(self):
        """Reset the customer card back to the Walk-in Customer placeholder."""
        self._has_customer = False
        self.lbl_customer.setText(_t("action_panel.walk_in_customer"))
        self.lbl_points.setText("")
        self.points_divider.setVisible(False)
        self.points_row.setVisible(False)
        self.btn_cust_clear.setVisible(False)
