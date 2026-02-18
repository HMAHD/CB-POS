from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QPushButton,
    QLabel,
    QFrame,
    QHBoxLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from cbpos.ui.resources.icons import Icons


class ActionBtn(QPushButton):
    """
    Custom Action Button with 'Key-Corner' layout.
    Top-Left: Shortcut (e.g., F1)
    Center: Icon
    Bottom: Text
    """

    def __init__(self, shortcut_text, label_text, icon_name=None, color=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 80)
        self.setProperty("class", "ActionGridBtn")
        self._icon_name = icon_name  # Store for theme updates

        # Main Layout
        layout = QGridLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(0)

        # 1. Shortcut Label (Top-Left)
        self.lbl_shortcut = QLabel(shortcut_text)
        self.lbl_shortcut.setObjectName("lblShortcut")
        self.lbl_shortcut.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.lbl_shortcut, 0, 0)

        # 2. Icon (Center)
        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_icon, 1, 0)

        # 3. Text (Bottom)
        self.lbl_text = QLabel(label_text)
        self.lbl_text.setObjectName("lblText")
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.lbl_text.setWordWrap(True)
        layout.addWidget(self.lbl_text, 2, 0)

        # Apply theme-aware styling
        self._apply_theme_styles(icon_name)

        # Apply custom color if provided
        if color:
            self.setProperty("btnColor", color)

    def _apply_theme_styles(self, icon_name=None):
        """Apply theme-aware colors to labels and icons."""
        from cbpos.core.services.theme_service import ThemeService

        is_dark = ThemeService.current_theme.lower() == "dark"

        # Both themes now use Dark Navy backgrounds, so both use white icons
        if is_dark:
            shortcut_color = "#AAAAAA"  # Subtle gray for shortcuts
            text_color = "#FFFFFF"      # White for text
            icon_color = "white"
        else:
            # Light theme now uses Dark Navy buttons, so white icons/text
            shortcut_color = "#AAAAAA"  # Light gray for shortcuts
            text_color = "#FFFFFF"      # White for text
            icon_color = "white"        # White icons on Navy background

        # Apply styles with transparent background
        self.lbl_shortcut.setStyleSheet(f"background: transparent; color: {shortcut_color};")
        self.lbl_text.setStyleSheet(f"background: transparent; color: {text_color};")
        self.lbl_icon.setStyleSheet("background: transparent;")

        # Set icon with correct color
        if icon_name:
            icon = Icons.get(icon_name, color=icon_color)
            self.lbl_icon.setPixmap(icon.pixmap(32, 32))

    def set_icon(self, icon_name):
        from cbpos.core.services.theme_service import ThemeService
        is_dark = ThemeService.current_theme.lower() == "dark"
        # Both themes use white icons now (Dark Navy backgrounds in both)
        icon_color = "white"
        if icon_name:
            icon = Icons.get(icon_name, color=icon_color)
            self.lbl_icon.setPixmap(icon.pixmap(32, 32))


class ActionPanel(QWidget):
    """
    Right-side control panel for Sales View.
    Contains:
    1. Customer Selection
    2. Action Grid (F-Keys)
    3. Pay Button
    """

    # Signals to communicate with SalesView
    customer_clicked = pyqtSignal()
    pay_clicked = pyqtSignal()

    # Action Signals
    action_f2 = pyqtSignal()  # Customer
    action_f3 = pyqtSignal()  # Search
    action_f4 = pyqtSignal()  # Qty
    action_f6 = pyqtSignal()  # Hold
    action_f7 = pyqtSignal()  # Recall
    action_f8 = pyqtSignal()  # Drawer
    action_del = pyqtSignal()  # Void
    action_ref = pyqtSignal()  # Refund
    action_more = pyqtSignal()  # More

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- 1. Customer Section ---
        customer_frame = QFrame()
        customer_frame.setObjectName("CustomerPanel")
        cust_layout = QHBoxLayout(customer_frame)
        cust_layout.setContentsMargins(5, 5, 5, 5)

        self.lbl_customer = QLabel("Walk-in Customer")
        self.lbl_customer.setObjectName("CustomerLabel")
        self.lbl_customer.setStyleSheet("background: transparent;")

        self.btn_cust_select = QPushButton("Select")
        self.btn_cust_select.setFixedWidth(70)
        self.btn_cust_select.setObjectName("BtnCustomerSelect")
        self.btn_cust_select.clicked.connect(self.customer_clicked.emit)

        cust_layout.addWidget(self.lbl_customer)
        cust_layout.addStretch()
        cust_layout.addWidget(self.btn_cust_select)

        layout.addWidget(customer_frame)

        # Points Label
        self.lbl_points = QLabel("")
        self.lbl_points.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_points.setObjectName("PointsLabel")
        self.lbl_points.setStyleSheet("background: transparent;")
        layout.addWidget(self.lbl_points)

        # --- 2. Action Grid ---
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        # Row 0
        self.btn_f2 = ActionBtn("F2", "Customer", Icons.CUSTOMERS)
        self.btn_f2.clicked.connect(self.action_f2.emit)
        grid_layout.addWidget(self.btn_f2, 0, 0)

        self.btn_f3 = ActionBtn("F3", "Search", Icons.SEARCH)
        self.btn_f3.clicked.connect(self.action_f3.emit)
        grid_layout.addWidget(self.btn_f3, 0, 1)

        self.btn_f4 = ActionBtn("F4", "Qty", Icons.EDIT)
        self.btn_f4.clicked.connect(self.action_f4.emit)
        grid_layout.addWidget(self.btn_f4, 0, 2)

        # Row 1
        self.btn_f6 = ActionBtn("F6", "Hold", Icons.HOLD, "#FFDC00")
        self.btn_f6.clicked.connect(self.action_f6.emit)
        grid_layout.addWidget(self.btn_f6, 1, 0)

        self.btn_f7 = ActionBtn("F7", "Recall", Icons.RECALL)
        self.btn_f7.clicked.connect(self.action_f7.emit)
        grid_layout.addWidget(self.btn_f7, 1, 1)

        self.btn_f8 = ActionBtn("F8", "Drawer", Icons.INVENTORY)
        self.btn_f8.clicked.connect(self.action_f8.emit)
        grid_layout.addWidget(self.btn_f8, 1, 2)

        # Row 2
        self.btn_del = ActionBtn("Del", "Void", Icons.VOID, "#FF4136")
        self.btn_del.clicked.connect(self.action_del.emit)
        grid_layout.addWidget(self.btn_del, 2, 0)

        self.btn_ref = ActionBtn("Ref", "Refund", Icons.HISTORY, "#FF4136")
        self.btn_ref.clicked.connect(self.action_ref.emit)
        grid_layout.addWidget(self.btn_ref, 2, 1)

        self.btn_more = ActionBtn("...", "More", Icons.SETTINGS)
        self.btn_more.clicked.connect(self.action_more.emit)
        grid_layout.addWidget(self.btn_more, 2, 2)

        layout.addLayout(grid_layout)

        # Spacer
        layout.addStretch()

        # --- 3. Pay Button ---
        self.btn_pay = QPushButton("PAY (F5)")
        self.btn_pay.setFixedHeight(80)
        self.btn_pay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pay.setObjectName("BtnPay")
        self.btn_pay.clicked.connect(self.pay_clicked.emit)
        layout.addWidget(self.btn_pay)

    def set_customer_info(self, name, phone, points):
        self.lbl_customer.setText(f"{name} ({phone})")
        self.lbl_points.setText(f"Points: {points}")

    def clear_customer_info(self):
        self.lbl_customer.setText("Walk-in Customer")
        self.lbl_points.setText("")
