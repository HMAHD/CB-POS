from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QPushButton,
    QLabel,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from cbpos.ui.resources.icons import Icons

_BTN_H = 70


class ActionBtn(QPushButton):
    """Action tile — shortcut top-left, icon center, label bottom."""

    def __init__(self, shortcut_text, label_text, icon_name=None, color=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionGridBtn")
        self._icon_name = icon_name

        self.setFixedHeight(_BTN_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QGridLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(0)
        layout.setRowStretch(0, 0)
        layout.setRowStretch(1, 1)
        layout.setRowStretch(2, 0)

        # Shortcut (Top-Left, subtle)
        self.lbl_shortcut = QLabel(shortcut_text)
        self.lbl_shortcut.setObjectName("lblShortcut")
        self.lbl_shortcut.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.lbl_shortcut, 0, 0)

        # Icon (Center)
        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_icon, 1, 0)

        # Label (Bottom)
        self.lbl_text = QLabel(label_text)
        self.lbl_text.setObjectName("lblText")
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(self.lbl_text, 2, 0)

        self._apply_theme_styles(icon_name)

        if color:
            self.setProperty("btnColor", color)

    def _apply_theme_styles(self, icon_name: str | None = None) -> None:
        """Apply theme-aware colors directly."""
        from cbpos.core.services.theme_service import ThemeService

        self.lbl_icon.setObjectName("lblIcon")
        is_dark = ThemeService.current_theme.lower() == "dark"

        text_color = "#FFFFFF" if is_dark else "#1A1A1A"
        shortcut_color = "#666666" if is_dark else "#AAAAAA"
        self.lbl_text.setStyleSheet(f"color: {text_color}; background: transparent; font-size: 12px; font-weight: 500;")
        self.lbl_shortcut.setStyleSheet(f"color: {shortcut_color}; background: transparent; font-size: 9px;")
        self.lbl_icon.setStyleSheet("background: transparent;")

        if icon_name:
            icon_color = "white" if is_dark else "#1A1A1A"
            icon = Icons.get(icon_name, color=icon_color)
            self.lbl_icon.setPixmap(icon.pixmap(28, 28))

    def set_icon(self, icon_name: str) -> None:
        """Set icon with theme-aware color."""
        from cbpos.core.services.theme_service import ThemeService

        if icon_name:
            is_dark = ThemeService.current_theme.lower() == "dark"
            icon_color = "white" if is_dark else "#1A1A1A"
            icon = Icons.get(icon_name, color=icon_color)
            self.lbl_icon.setPixmap(icon.pixmap(28, 28))

    def refresh_theme(self) -> None:
        """Re-apply theme colors (called when theme changes)."""
        self._apply_theme_styles(self._icon_name)


class SectionLabel(QLabel):
    """Section header label for grouping action buttons."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("ActionSectionLabel")


class ActionPanel(QWidget):
    """Right-side control panel for Sales View."""

    customer_clicked = pyqtSignal()
    pay_clicked = pyqtSignal()

    action_f2 = pyqtSignal()
    action_f3 = pyqtSignal()
    action_f4 = pyqtSignal()
    action_f6 = pyqtSignal()
    action_f7 = pyqtSignal()
    action_f8 = pyqtSignal()
    action_del = pyqtSignal()
    action_ref = pyqtSignal()
    action_more = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        # ── 1. Customer Card ─────────────────────────────────────
        customer_frame = QFrame()
        customer_frame.setObjectName("CustomerPanel")
        cust_layout = QHBoxLayout(customer_frame)
        cust_layout.setContentsMargins(10, 8, 10, 8)
        cust_layout.setSpacing(10)

        # Customer icon
        self.lbl_cust_icon = QLabel()
        self.lbl_cust_icon.setFixedSize(32, 32)
        self.lbl_cust_icon.setPixmap(Icons.get("fa5s.user-circle", "#00BCEB").pixmap(28, 28))
        self.lbl_cust_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cust_icon.setStyleSheet("background: transparent;")
        cust_layout.addWidget(self.lbl_cust_icon)

        # Customer info (name + subtitle)
        cust_info = QVBoxLayout()
        cust_info.setSpacing(0)
        lbl_cust_title = QLabel("Customer")
        lbl_cust_title.setObjectName("CustTitle")
        cust_info.addWidget(lbl_cust_title)
        self.lbl_customer = QLabel("Walk-in Customer")
        self.lbl_customer.setObjectName("CustomerLabel")
        cust_info.addWidget(self.lbl_customer)
        cust_layout.addLayout(cust_info)

        cust_layout.addStretch()

        self.btn_cust_select = QPushButton("Select \u25BE")
        self.btn_cust_select.setObjectName("BtnCustomerSelect")
        self.btn_cust_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cust_select.clicked.connect(self.customer_clicked.emit)
        cust_layout.addWidget(self.btn_cust_select)

        layout.addWidget(customer_frame)

        # Points Label (hidden when empty)
        self.lbl_points = QLabel("")
        self.lbl_points.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_points.setObjectName("PointsLabel")
        layout.addWidget(self.lbl_points)

        # ── 2. Orders Section ────────────────────────────────────
        layout.addSpacing(10)
        layout.addWidget(SectionLabel("Orders"))
        layout.addSpacing(4)

        orders_grid = QGridLayout()
        orders_grid.setSpacing(6)

        self.btn_f2 = ActionBtn("F2", "Customer", Icons.CUSTOMERS)
        self.btn_f2.clicked.connect(self.action_f2.emit)
        orders_grid.addWidget(self.btn_f2, 0, 0)

        self.btn_f3 = ActionBtn("F3", "Search", Icons.SEARCH)
        self.btn_f3.clicked.connect(self.action_f3.emit)
        orders_grid.addWidget(self.btn_f3, 0, 1)

        self.btn_f4 = ActionBtn("F4", "Qty", Icons.EDIT)
        self.btn_f4.clicked.connect(self.action_f4.emit)
        orders_grid.addWidget(self.btn_f4, 1, 0)

        self.btn_f6 = ActionBtn("F6", "Hold", Icons.HOLD, "#FFDC00")
        self.btn_f6.clicked.connect(self.action_f6.emit)
        orders_grid.addWidget(self.btn_f6, 1, 1)

        layout.addLayout(orders_grid)

        # ── 3. Transaction Section ───────────────────────────────
        layout.addSpacing(10)
        layout.addWidget(SectionLabel("Transaction"))
        layout.addSpacing(4)

        txn_grid = QGridLayout()
        txn_grid.setSpacing(6)

        self.btn_f7 = ActionBtn("F7", "Recall", Icons.RECALL)
        self.btn_f7.clicked.connect(self.action_f7.emit)
        txn_grid.addWidget(self.btn_f7, 0, 0)

        self.btn_f8 = ActionBtn("F8", "Drawer", Icons.DRAWER)
        self.btn_f8.clicked.connect(self.action_f8.emit)
        txn_grid.addWidget(self.btn_f8, 0, 1)

        self.btn_del = ActionBtn("Del", "Void", Icons.VOID, "#FF4136")
        self.btn_del.clicked.connect(self.action_del.emit)
        txn_grid.addWidget(self.btn_del, 1, 0)

        self.btn_ref = ActionBtn("Ref", "Refund", Icons.HISTORY, "#FF4136")
        self.btn_ref.clicked.connect(self.action_ref.emit)
        txn_grid.addWidget(self.btn_ref, 1, 1)

        layout.addLayout(txn_grid)

        # ── 4. Specialty Section ─────────────────────────────────
        layout.addSpacing(10)
        layout.addWidget(SectionLabel("Specialty"))
        layout.addSpacing(4)

        self.btn_more = ActionBtn("", "Touch", Icons.GRID)
        self.btn_more.clicked.connect(self.action_more.emit)
        layout.addWidget(self.btn_more)

        # ── 5. Spacer + Pay Button ───────────────────────────────
        layout.addStretch()

        self.btn_pay = QPushButton("  Pay (F5)")
        self.btn_pay.setFixedHeight(56)
        self.btn_pay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pay.setObjectName("BtnPay")
        self.btn_pay.clicked.connect(self.pay_clicked.emit)
        self._apply_pay_icon()
        layout.addWidget(self.btn_pay)

    def _apply_pay_icon(self) -> None:
        """Set pay button icon."""
        icon = Icons.get("fa5s.cash-register", "white")
        self.btn_pay.setIcon(icon)

    def set_customer_info(self, name, phone, points):
        self.lbl_customer.setText(f"{name} ({phone})")
        self.lbl_points.setText(f"Points: {points}")

    def clear_customer_info(self):
        self.lbl_customer.setText("Walk-in Customer")
        self.lbl_points.setText("")
