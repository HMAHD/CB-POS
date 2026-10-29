import weakref

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
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
from cbpos.core.utils.destroy_hooks import call_on_destroyed
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.resources.icons import Icons
from cbpos.ui.utils.style_helpers import refresh_style
from cbpos.ui.widgets.elided_label import ElidedLabel

_BTN_H = 70


def _get_initials(name: str) -> str:
    """Extract up to 2 uppercase initials from a customer name."""
    parts = [p.strip() for p in name.split() if p.strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


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
        register_language_callback(self.retranslate_ui, owner=self)

        # Re-tint the tile icons if the theme changes under a live panel
        # (#603). Held through a weakref: ThemeService's callback list is
        # class-level and would otherwise keep the panel alive.
        self_ref = weakref.ref(self)

        def _on_theme_changed():
            widget = self_ref()
            if widget is not None:
                widget.refresh_theme()

        ThemeService.register_theme_callback(_on_theme_changed, owner=self)
        # Not destroyed.connect(<nested function>): that can segfault (see destroy_hooks).
        call_on_destroyed(self, ThemeService.unregister_theme_callback, _on_theme_changed)

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
        customer_frame = QFrame()
        customer_frame.setObjectName("CustomerPanel")
        self.customer_frame = customer_frame
        customer_frame.setProperty("hasCustomer", False)
        customer_frame_layout = QVBoxLayout(customer_frame)
        customer_frame_layout.setContentsMargins(12, 10, 12, 10)
        customer_frame_layout.setSpacing(6)

        # Top Header Row: Category tag on left, contextual action buttons on right
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        self.lbl_cust_title = QLabel()
        self.lbl_cust_title.setObjectName("CustTitle")
        top_row.addWidget(self.lbl_cust_title)
        top_row.addStretch()

        self.btn_cust_select = QPushButton()
        self.btn_cust_select.setObjectName("BtnCustomerSelect")
        self.btn_cust_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cust_select.setProperty("mode", "select")
        self.btn_cust_select.clicked.connect(self.customer_clicked.emit)
        top_row.addWidget(self.btn_cust_select)

        self.btn_cust_clear = QPushButton()
        self.btn_cust_clear.setObjectName("BtnCustomerClear")
        self.btn_cust_clear.setIcon(Icons.get("fa5s.times", "#888888"))
        self.btn_cust_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cust_clear.setFixedSize(24, 24)
        self.btn_cust_clear.setToolTip(_t("action_panel.clear_customer"))
        self.btn_cust_clear.clicked.connect(self.customer_cleared.emit)
        self.btn_cust_clear.setVisible(False)
        top_row.addWidget(self.btn_cust_clear)

        customer_frame_layout.addLayout(top_row)

        # Hairline divider
        self.points_divider = QFrame()
        self.points_divider.setObjectName("PointsDivider")
        self.points_divider.setFixedHeight(1)
        self.points_divider.setVisible(False)
        customer_frame_layout.addWidget(self.points_divider)

        # Main Info Row: Avatar + Details
        main_info_row = QHBoxLayout()
        main_info_row.setContentsMargins(0, 2, 0, 0)
        main_info_row.setSpacing(10)

        self.lbl_cust_icon = QLabel()
        self.lbl_cust_icon.setObjectName("CustAvatar")
        self.lbl_cust_icon.setFixedSize(38, 38)
        self.lbl_cust_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cust_icon.setPixmap(Icons.get(Icons.CUSTOMER, "#888888").pixmap(20, 20))
        self.lbl_cust_icon.setProperty("hasCustomer", False)
        main_info_row.addWidget(self.lbl_cust_icon)

        details_col = QVBoxLayout()
        details_col.setContentsMargins(0, 0, 0, 0)
        details_col.setSpacing(3)

        self.lbl_customer = ElidedLabel()
        self.lbl_customer.setObjectName("CustomerLabel")
        details_col.addWidget(self.lbl_customer)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)

        self.points_row = QWidget()
        self.points_row.setObjectName("PointsRow")
        points_row_layout = QHBoxLayout(self.points_row)
        points_row_layout.setContentsMargins(6, 2, 8, 2)
        points_row_layout.setSpacing(4)

        self.lbl_points_icon = QLabel()
        self.lbl_points_icon.setObjectName("PointsIcon")
        self.lbl_points_icon.setPixmap(Icons.get(Icons.POINTS, "#FFDC00").pixmap(11, 11))
        points_row_layout.addWidget(self.lbl_points_icon)

        self.lbl_points = QLabel("")
        self.lbl_points.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_points.setObjectName("PointsLabel")
        points_row_layout.addWidget(self.lbl_points)
        self.points_row.setVisible(False)
        meta_row.addWidget(self.points_row)

        self.lbl_phone = QLabel("")
        self.lbl_phone.setObjectName("CustomerPhoneLabel")
        self.lbl_phone.setVisible(False)
        meta_row.addWidget(self.lbl_phone)
        meta_row.addStretch()

        details_col.addLayout(meta_row)
        main_info_row.addLayout(details_col, 1)

        customer_frame_layout.addLayout(main_info_row)
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
        self.lbl_cust_title.setText(_t("action_panel.customer_title").upper())
        if not self._has_customer:
            self.lbl_customer.setText(_t("action_panel.walk_in_customer"))
            self.btn_cust_select.setText(_t("action_panel.btn_select_customer"))
        else:
            self.btn_cust_select.setText(_t("action_panel.change_customer"))
        self.btn_cust_clear.setToolTip(_t("action_panel.clear_customer"))
        self.btn_pay.setText(_t("action_panel.btn_pay"))

        for lbl in self._section_labels:
            lbl.retranslate()

        for btn in self._action_btns:
            btn.retranslate()

    def set_customer_info(self, name, phone, points):
        """Show the selected customer's profile, points, and action controls.

        Args:
            name: Customer's full name (shown elided; full name + phone as tooltip).
            phone: Customer's phone number, included in the tooltip if present.
            points: Loyalty points balance shown in the points row.
        """
        self._has_customer = True
        self.lbl_customer.setText(name or "")
        self.lbl_customer.setToolTip(f"{name} ({phone})" if phone else name)
        self.lbl_points.setText(_t("action_panel.points", points=points))
        if phone:
            self.lbl_phone.setText(str(phone))
            self.lbl_phone.setVisible(True)
        else:
            self.lbl_phone.setText("")
            self.lbl_phone.setVisible(False)

        # Update avatar initials or fallback icon
        initials = _get_initials(name)
        if initials:
            self.lbl_cust_icon.setPixmap(QPixmap())
            self.lbl_cust_icon.setText(initials)
        else:
            self.lbl_cust_icon.setText("")
            self.lbl_cust_icon.setPixmap(Icons.get(Icons.CUSTOMER, "#00BCEB").pixmap(20, 20))

        self.btn_cust_select.setText(_t("action_panel.change_customer"))
        self.btn_cust_select.setProperty("mode", "change")
        refresh_style(self.btn_cust_select)

        self.customer_frame.setProperty("hasCustomer", True)
        refresh_style(self.customer_frame)

        self.lbl_cust_icon.setProperty("hasCustomer", True)
        refresh_style(self.lbl_cust_icon)

        self.points_divider.setVisible(True)
        self.points_row.setVisible(True)
        self.btn_cust_clear.setVisible(True)

    def clear_customer_info(self):
        """Reset the customer card back to the Walk-in Customer placeholder."""
        self._has_customer = False
        self.lbl_customer.setText(_t("action_panel.walk_in_customer"))
        self.lbl_customer.setToolTip("")
        self.lbl_points.setText("")
        self.lbl_phone.setText("")
        self.lbl_phone.setVisible(False)

        self.lbl_cust_icon.setText("")
        self.lbl_cust_icon.setPixmap(Icons.get(Icons.CUSTOMER, "#888888").pixmap(20, 20))

        self.btn_cust_select.setText(_t("action_panel.btn_select_customer"))
        self.btn_cust_select.setProperty("mode", "select")
        refresh_style(self.btn_cust_select)

        self.customer_frame.setProperty("hasCustomer", False)
        refresh_style(self.customer_frame)

        self.lbl_cust_icon.setProperty("hasCustomer", False)
        refresh_style(self.lbl_cust_icon)

        self.points_divider.setVisible(False)
        self.points_row.setVisible(False)
        self.btn_cust_clear.setVisible(False)
