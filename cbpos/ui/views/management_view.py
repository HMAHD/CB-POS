import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QStackedWidget,
    QFrame,
    QLabel,
    QToolButton,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap
from cbpos.ui.widgets.custom_widgets import SidebarButton
from cbpos.ui.resources.icons import Icons
from cbpos.ui.views.dashboard_view import DashboardView
from cbpos.ui.views.inventory_view import InventoryView
from cbpos.ui.views.purchase_view import PurchaseView
from cbpos.ui.views.customer_view import CustomerView
from cbpos.ui.views.reports.report_viewer import ReportViewer
from cbpos.ui.views.user_view import UserView
from cbpos.ui.views.pricelist_view import PriceListView
from cbpos.ui.views.promotion_view import PromotionView
from cbpos.ui.views.history_view import HistoryView


class ManagementView(QWidget):
    logout_requested = pyqtSignal()
    request_pos_view = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.is_collapsed = False
        self.init_ui()

    def init_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. Sidebar
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(250)
        self.sidebar.setStyleSheet("background-color: #001830; border-right: 1px solid #003366;")
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(10)

        # 1.1 Header (Logo + Toggle)
        header_container = QWidget()
        header_container.setFixedHeight(60)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_logo = QLabel()
        # Use absolute path
        # Ensure we point to cbpos/assets
        logo_path = os.path.abspath(os.path.join("cbpos", "assets", "logo", "02.png"))
        logo_pixmap = QPixmap(logo_path)

        if not logo_pixmap.isNull():
            self.lbl_logo.setPixmap(logo_pixmap.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_logo.setText("CB POS")
            self.lbl_logo.setStyleSheet("color: white; font-weight: bold; font-size: 18px;")

        self.btn_toggle = QToolButton()
        self.btn_toggle.setIcon(Icons.get("fa5s.bars", "white"))
        self.btn_toggle.setStyleSheet("border: none; background: transparent;")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle_sidebar)

        header_layout.addWidget(self.lbl_logo)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_toggle)

        self.sidebar_layout.addWidget(header_container)

        # Spacer
        self.sidebar_layout.addSpacing(10)

        # 1.2 Nav Buttons
        self.nav_buttons = []

        self.btn_dashboard = self.create_nav_button("Dashboard", Icons.DASHBOARD, 0)
        self.btn_inventory = self.create_nav_button("Inventory", Icons.INVENTORY, 1)
        self.btn_purchasing = self.create_nav_button("Purchasing", Icons.PURCHASE, 2)
        self.btn_customers = self.create_nav_button("Customers", Icons.CUSTOMERS, 3)
        self.btn_reports = self.create_nav_button("Reports", Icons.REPORTS, 4)
        self.btn_history = self.create_nav_button("History", Icons.HISTORY, 5)
        self.btn_users = self.create_nav_button("Users", Icons.USERS, 6)
        self.btn_pricelists = self.create_nav_button("Price Lists", Icons.PRICE_LIST, 7)
        self.btn_promotions = self.create_nav_button("Promotions", Icons.PROMOTION, 8)

        # Push everything else to bottom
        self.sidebar_layout.addStretch()

        # 1.3 Bottom Section (POS + User + Logout)

        # POS Button
        self.btn_pos = SidebarButton("   POS / Sales", "fa5s.cash-register")
        self.btn_pos.setObjectName("BtnPos")  # Special Styling
        self.btn_pos.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_pos.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_pos.clicked.connect(self.request_pos_view.emit)
        self.sidebar_layout.addWidget(self.btn_pos)

        # User Info (Badge)
        self.lbl_badge = QLabel()
        self.lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_badge.setFixedHeight(50)  # Approx height for badge
        self.sidebar_layout.addWidget(self.lbl_badge)

        self.btn_logout = SidebarButton("   Logout", Icons.LOGOUT)
        self.btn_logout.setObjectName("BtnLogout")  # Special Styling
        self.btn_logout.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_logout.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_logout.clicked.connect(self.logout_requested.emit)
        self.sidebar_layout.addWidget(self.btn_logout)

        self.sidebar_layout.addSpacing(10)

        self.main_layout.addWidget(self.sidebar)

        # 2. Content Area
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        # Stack
        self.stack = QStackedWidget()
        self.stack.currentChanged.connect(self.highlight_active_tab)
        self.content_layout.addWidget(self.stack)

        self.main_layout.addWidget(self.content_area)

        # Initialize Views
        self.init_views()

        # Animation
        self.anim_width = QPropertyAnimation(self.sidebar, b"minimumWidth")
        self.anim_width.setDuration(300)
        self.anim_width.setEasingCurve(QEasingCurve.Type.InOutQuart)

        self.anim_max_width = QPropertyAnimation(self.sidebar, b"maximumWidth")
        self.anim_max_width.setDuration(300)
        self.anim_max_width.setEasingCurve(QEasingCurve.Type.InOutQuart)

        # Apply initial styles
        self.update_sidebar_styles()

    def create_nav_button(self, text, icon, index):
        # Add spaces for visual separation
        btn = SidebarButton(f"   {text}", icon)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda: self.switch_tab(index))
        self.sidebar_layout.addWidget(btn)
        self.nav_buttons.append(btn)
        return btn

    def switch_tab(self, index):
        self.stack.setCurrentIndex(index)

    def highlight_active_tab(self, index):
        """Highlight the active tab button."""
        for i, btn in enumerate(self.nav_buttons):
            is_active = i == index
            btn.set_active(is_active)

            # Dynamic Property for Styling
            btn.setProperty("active", is_active)

            # Force Style Refresh
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def init_views(self):
        # 0. Dashboard
        self.dashboard_view = DashboardView()
        self.stack.addWidget(self.dashboard_view)

        # 1. Inventory
        self.inventory_view = InventoryView()
        self.stack.addWidget(self.inventory_view)

        # 2. Purchasing
        self.purchase_view = PurchaseView()
        self.stack.addWidget(self.purchase_view)

        # 3. Customers
        self.customer_view = CustomerView()
        self.stack.addWidget(self.customer_view)

        # 4. Reports
        self.reports_view = ReportViewer()
        self.stack.addWidget(self.reports_view)

        # 5. History
        self.history_view = HistoryView()
        self.stack.addWidget(self.history_view)

        # 6. Users
        self.user_view = UserView()
        self.stack.addWidget(self.user_view)

        # 7. Price Lists
        self.pricelist_view = PriceListView()
        self.stack.addWidget(self.pricelist_view)

        # 8. Promotions
        self.promotion_view = PromotionView()
        self.stack.addWidget(self.promotion_view)

    def set_user(self, user):
        self.user = user

        # Badge Logic
        role = user.role.name.lower() if user.role else "cashier"
        badge_filename = ""

        if "admin" in role:
            badge_filename = "admin.png"
        elif "manager" in role or "mod" in role:
            badge_filename = "mod.png"

        if badge_filename:
            # Use pathlib for robust path handling
            # Ensure we point to cbpos/assets
            base_path = Path(os.getcwd())
            badge_path = base_path / "cbpos" / "assets" / "badge" / badge_filename
            print(f"Loading Badge from: {badge_path}")

            if badge_path.exists():
                pix = QPixmap(str(badge_path))
                if not pix.isNull():
                    self.lbl_badge.setPixmap(pix.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation))
                    self.lbl_badge.setVisible(not self.is_collapsed)
                    self.lbl_badge.setText("")  # Clear text
                else:
                    self.lbl_badge.setText(f"[{role.upper()}]")
                    self.lbl_badge.setStyleSheet("color: #00BCEB; font-weight: bold;")
            else:
                print(f"WARNING: Badge not found at {badge_path}")
                self.lbl_badge.setText(f"[{role.upper()}]")
                self.lbl_badge.setStyleSheet("color: #00BCEB; font-weight: bold;")
        else:
            self.lbl_badge.clear()

        # Permission check for Users tab
        is_admin = "admin" in role
        self.btn_users.setVisible(is_admin)
        self.btn_pricelists.setVisible(is_admin)
        self.btn_promotions.setVisible(is_admin)

        if hasattr(self, "purchase_view"):
            self.purchase_view.set_user(user)

    def toggle_sidebar(self):
        start_width = self.sidebar.width()

        if self.is_collapsed:
            # Expand
            end_width = 250
            self.lbl_logo.setVisible(True)
            # Only show badge if it has content (pixmap or text)
            if self.lbl_badge.pixmap() or self.lbl_badge.text():
                self.lbl_badge.setVisible(True)
            style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            self.is_collapsed = False
        else:
            # Collapse
            end_width = 70
            self.lbl_logo.setVisible(False)
            self.lbl_badge.setVisible(False)
            style = Qt.ToolButtonStyle.ToolButtonIconOnly
            self.is_collapsed = True

        # Animate
        self.anim_width.setStartValue(start_width)
        self.anim_width.setEndValue(end_width)
        self.anim_width.start()

        self.anim_max_width.setStartValue(start_width)
        self.anim_max_width.setEndValue(end_width)
        self.anim_max_width.start()

        # Update Buttons Styles
        self.update_sidebar_styles()

        # Update Button Style (Icon/Text)
        self.btn_pos.setToolButtonStyle(style)
        self.btn_logout.setToolButtonStyle(style)
        for btn in self.nav_buttons:
            btn.setToolButtonStyle(style)

    def update_sidebar_styles(self):
        """
        Dynamically update stylesheets based on collapsed state.
        This is necessary because QSS alone cannot handle the complex
        padding/alignment changes
        required for the collapsed 'icon-only' mode vs the expanded 'full-width' mode.
        """
        if self.is_collapsed:
            # Collapsed Styles (Center Align, No Padding)
            common_style = """
                QToolButton {
                    padding-left: 0px;
                    padding-right: 0px;
                    text-align: center;
                    border: none;
                    background: transparent;
                }
            """

            # POS Button (Keep colors but center)
            pos_style = """
                QToolButton {
                    color: #39FF14;
                    background-color: rgba(57, 255, 20, 0.1);
                    border: none;
                    border-top: 1px solid #333;
                    text-align: center;
                    padding-left: 0px;
                }
                QToolButton:hover { background-color: rgba(57, 255, 20, 0.2); }
            """

            # Logout Button (Keep colors but center)
            logout_style = """
                QToolButton {
                    color: #FF4136;
                    background-color: rgba(255, 65, 54, 0.1);
                    border: none;
                    text-align: center;
                    padding-left: 0px;
                }
                QToolButton:hover { background-color: rgba(255, 65, 54, 0.2); }
            """

            for btn in self.nav_buttons:
                btn.setStyleSheet(common_style)

            self.btn_pos.setStyleSheet(pos_style)
            self.btn_logout.setStyleSheet(logout_style)

        else:
            # Expanded Styles (Left Align, Padding)

            # Standard Nav Buttons - Clear style to let QSS take over
            for btn in self.nav_buttons:
                btn.setStyleSheet("")

            # POS Button (Specific Style)
            self.btn_pos.setStyleSheet(
                """
                QToolButton {
                    color: #39FF14;
                    background-color: rgba(57, 255, 20, 0.1);
                    border: none;
                    border-top: 1px solid #333;
                    text-align: left;
                    padding-left: 24px;
                }
                QToolButton:hover { background-color: rgba(57, 255, 20, 0.2); }
            """
            )

            # Logout Button (Specific Style)
            self.btn_logout.setStyleSheet(
                """
                QToolButton {
                    color: #FF4136;
                    background-color: rgba(255, 65, 54, 0.1);
                    border: none;
                    text-align: left;
                    padding-left: 24px;
                }
                QToolButton:hover { background-color: rgba(255, 65, 54, 0.2); }
            """
            )
