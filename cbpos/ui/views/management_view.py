import logging

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
from cbpos.ui.views.credit_book_view import CreditBookView
from cbpos.ui.views.reports.report_viewer import ReportViewer
from cbpos.ui.views.user_view import UserView
from cbpos.ui.views.pricelist_view import PriceListView
from cbpos.ui.views.promotion_view import PromotionView
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.i18n import _t, register_language_callback, unregister_language_callback

logger = logging.getLogger(__name__)


class ManagementView(QWidget):
    logout_requested = pyqtSignal()
    request_pos_view = pyqtSignal()
    convert_proforma_to_sale = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        from cbpos.core.services.config_service import ConfigService

        self.is_collapsed = bool(ConfigService.get("sidebar_collapsed"))
        self.init_ui()
        if self.is_collapsed:
            self._apply_collapsed_state()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def init_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. Sidebar
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(250)
        self.sidebar.setObjectName("SidebarContainer")  # For theme-specific styling
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(10)

        # 1.1 Header (Logo + Toggle)
        header_container = QWidget()
        header_container.setFixedHeight(60)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_logo = QLabel()
        from cbpos.core.services.theme_service import ThemeService

        logo_path = ThemeService.get_logo_path()
        logo_pixmap = QPixmap(logo_path)

        if not logo_pixmap.isNull():
            self.lbl_logo.setPixmap(logo_pixmap.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_logo.setText("")
            self.lbl_logo.setObjectName("SidebarLogo")

        self.btn_toggle = QToolButton()
        icon_color = ThemeService.get_icon_color()
        self.btn_toggle.setIcon(Icons.get("fa5s.bars", icon_color))
        self.btn_toggle.setObjectName("SidebarToggle")
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

        self.btn_dashboard = self.create_nav_button("", Icons.DASHBOARD, 0)
        self.btn_inventory = self.create_nav_button("", Icons.INVENTORY, 1)
        self.btn_purchasing = self.create_nav_button("", Icons.PURCHASE, 2)
        self.btn_customers = self.create_nav_button("", Icons.CREDIT_BOOK, 3)
        self.btn_reports = self.create_nav_button("", Icons.REPORTS, 4)
        self.btn_documents = self.create_nav_button("", Icons.DOCUMENTS, 5)
        self.btn_users = self.create_nav_button("", Icons.USERS, 6)
        self.btn_pricelists = self.create_nav_button("", Icons.PRICE_LIST, 7)
        self.btn_promotions = self.create_nav_button("", Icons.PROMOTION, 8)
        self.btn_stock_take = self.create_nav_button("", Icons.STOCK_TAKE, 9)

        # Push everything else to bottom
        self.sidebar_layout.addStretch()

        # 1.3 Bottom Section (POS + User + Logout)
        self.user_profile_widget = QWidget()
        self.user_profile_widget.setObjectName("UserProfileContainer")  # For killing artifact lines
        user_profile_layout = QVBoxLayout(self.user_profile_widget)
        user_profile_layout.setContentsMargins(0, 0, 0, 0)
        user_profile_layout.setSpacing(0)

        # POS Button
        self.btn_pos = SidebarButton("", "fa5s.cash-register")
        self.btn_pos.setObjectName("BtnPos")  # Special Styling
        self.btn_pos.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_pos.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_pos.clicked.connect(self.request_pos_view.emit)
        user_profile_layout.addWidget(self.btn_pos)

        self.btn_logout = SidebarButton("", Icons.LOGOUT)
        self.btn_logout.setObjectName("BtnLogout")  # Special Styling
        self.btn_logout.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_logout.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_logout.clicked.connect(self.logout_requested.emit)
        user_profile_layout.addWidget(self.btn_logout)

        user_profile_layout.addSpacing(10)

        self.sidebar_layout.addWidget(self.user_profile_widget)

        self.main_layout.addWidget(self.sidebar)

        # 2. Content Area
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        # Stack
        self.stack = QStackedWidget()
        self.stack.currentChanged.connect(self.highlight_active_tab)
        self.content_layout.addWidget(self.stack)

        self.main_layout.addWidget(self.content_area, 1)  # stretch to fill remaining space

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

        # Register callback to update icons when theme changes
        from cbpos.core.services.theme_service import ThemeService

        ThemeService.register_theme_callback(self.update_sidebar_icons)

    def retranslate_ui(self) -> None:
        """Update all translatable text in the view."""
        # Logo fallback text
        if self.lbl_logo.pixmap() is None or self.lbl_logo.pixmap().isNull():
            self.lbl_logo.setText(_t("management.logo_fallback"))

        # Nav buttons
        self.btn_dashboard.setText("   " + _t("management.sidebar_dashboard"))
        self.btn_inventory.setText("   " + _t("management.sidebar_inventory"))
        self.btn_purchasing.setText("   " + _t("management.sidebar_purchasing"))
        self.btn_customers.setText("   " + _t("management.sidebar_credit_book"))
        self.btn_reports.setText("   " + _t("management.sidebar_reports"))
        self.btn_documents.setText("   " + _t("management.sidebar_documents"))
        self.btn_users.setText("   " + _t("management.sidebar_users"))
        self.btn_pricelists.setText("   " + _t("management.sidebar_price_lists"))
        self.btn_promotions.setText("   " + _t("management.sidebar_promotions"))
        self.btn_stock_take.setText("   " + _t("management.sidebar_stock_take"))

        # Bottom buttons
        self.btn_pos.setText("   " + _t("management.sidebar_pos"))
        self.btn_logout.setText("   " + _t("management.sidebar_logout"))

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

        # 3. Credit Book (replaces Customers)
        self.credit_book_view = CreditBookView()
        self.stack.addWidget(self.credit_book_view)

        # 4. Reports
        self.reports_view = ReportViewer()
        self.stack.addWidget(self.reports_view)

        # 5. Documents (replaces History)
        self.document_view = DocumentBrowserView()
        self.document_view.convert_to_sale_requested.connect(self.convert_proforma_to_sale.emit)
        self.stack.addWidget(self.document_view)

        # 6. Users
        self.user_view = UserView()
        self.stack.addWidget(self.user_view)

        # 7. Price Lists
        self.pricelist_view = PriceListView()
        self.stack.addWidget(self.pricelist_view)

        # 8. Promotions
        self.promotion_view = PromotionView()
        self.stack.addWidget(self.promotion_view)

        # 9. Stock Take
        from cbpos.ui.views.stock_take_view import StockTakeView

        self.stock_take_view = StockTakeView()
        self.stack.addWidget(self.stock_take_view)

    def set_user(self, user):
        self.user = user

        # Permission check for Users tab
        role = user.role.name.lower() if user.role else "cashier"
        is_admin = "admin" in role
        self.btn_users.setVisible(is_admin)
        self.btn_pricelists.setVisible(is_admin)
        self.btn_promotions.setVisible(is_admin)
        self.btn_stock_take.setVisible(is_admin)

        if hasattr(self, "purchase_view"):
            self.purchase_view.set_user(user)
        if hasattr(self, "stock_take_view"):
            self.stock_take_view.set_user(user)

    def _apply_collapsed_state(self) -> None:
        """Set sidebar to collapsed (icon-only) mode without animation."""
        self.sidebar.setFixedWidth(70)
        self.lbl_logo.setVisible(False)
        style = Qt.ToolButtonStyle.ToolButtonIconOnly
        self.btn_pos.setToolButtonStyle(style)
        self.btn_logout.setToolButtonStyle(style)
        for btn in self.nav_buttons:
            btn.setToolButtonStyle(style)

    def toggle_sidebar(self):
        from cbpos.core.services.config_service import ConfigService

        start_width = self.sidebar.width()

        if self.is_collapsed:
            # Expand
            end_width = 250
            self.lbl_logo.setVisible(True)
            style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            self.is_collapsed = False
        else:
            # Collapse
            end_width = 70
            self.lbl_logo.setVisible(False)
            style = Qt.ToolButtonStyle.ToolButtonIconOnly
            self.is_collapsed = True

        ConfigService.set("sidebar_collapsed", self.is_collapsed)

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
        # Update Property for all buttons
        buttons = self.nav_buttons + [self.btn_pos, self.btn_logout]
        for btn in buttons:
            btn.setProperty("collapsed", self.is_collapsed)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def update_sidebar_icons(self):
        """
        Update all sidebar button icons when theme changes.
        Call this after theme switching to refresh icon colors.
        """
        buttons = self.nav_buttons + [self.btn_pos, self.btn_logout]
        for btn in buttons:
            if hasattr(btn, "update_icon"):
                btn.update_icon()
