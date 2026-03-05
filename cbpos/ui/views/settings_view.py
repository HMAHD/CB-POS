from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QFrame,
    QMessageBox,
    QLabel,
    QToolButton,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.widgets.custom_widgets import SidebarButton
from cbpos.ui.resources.icons import Icons
from cbpos.ui.views.settings_pages import (
    ShopInfoPage,
    SalesTaxPage,
    DocumentPage,
    HardwarePage,
    ReceiptPage,
    SystemPage,
    NetworkPage,
)


class SettingsView(QWidget):
    close_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.is_collapsed = False
        self.nav_buttons = []
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Body: Sidebar + Content
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # --- Sidebar (matches ManagementView pattern) ---
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(250)
        self.sidebar.setObjectName("SidebarContainer")
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(10)

        # Header (Logo + Toggle)
        header_container = QWidget()
        header_container.setFixedHeight(60)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_logo = QLabel()
        logo_path = ThemeService.get_logo_path()
        logo_pixmap = QPixmap(logo_path)
        if not logo_pixmap.isNull():
            self.lbl_logo.setPixmap(logo_pixmap.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_logo.setText("CB POS")
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
        self.sidebar_layout.addSpacing(10)

        # Navigation buttons — config pages
        self.btn_shop_info = self.create_nav_button("Shop Info", "fa5s.store", 0)
        self.btn_sales_tax = self.create_nav_button("Sales & Tax", "fa5s.shopping-cart", 1)
        self.btn_documents = self.create_nav_button("Documents", "fa5s.file-invoice", 2)
        self.btn_hardware = self.create_nav_button("Hardware", "fa5s.print", 3)
        self.btn_receipt = self.create_nav_button("Receipt", "fa5s.receipt", 4)
        self.btn_system = self.create_nav_button("System", "fa5s.cogs", 5)
        self.btn_network = self.create_nav_button("Network", "fa5s.network-wired", 6)
        self.btn_payment_methods = self.create_nav_button("Payments", "fa5s.credit-card", 7)

        # Operational buttons (same list, no gap)
        self.btn_data_safety = self.create_nav_button("Data Safety", "fa5s.shield-alt", 8)
        self.btn_admin_tools = self.create_nav_button("Admin Tools", "fa5s.toolbox", 9)

        self.sidebar_layout.addStretch()

        body_layout.addWidget(self.sidebar)

        # --- Content Area ---
        self.stack = QStackedWidget()
        self.stack.setObjectName("SettingsContent")
        self.stack.currentChanged.connect(self.highlight_active_page)

        # Config pages (participate in load/save)
        self.pages = [
            ShopInfoPage(),
            SalesTaxPage(),
            DocumentPage(),
            HardwarePage(),
            ReceiptPage(),
            SystemPage(),
            NetworkPage(),
        ]

        for page in self.pages:
            self.stack.addWidget(page)

        # Operational views (self-contained, no load/save)
        from cbpos.ui.views.payment_methods_view import PaymentMethodsView
        from cbpos.ui.views.data_safety_view import DataSafetyView
        from cbpos.ui.views.admin_tools_view import AdminToolsView

        self.payment_methods_view = PaymentMethodsView()
        self.stack.addWidget(self.payment_methods_view)

        self.data_safety_view = DataSafetyView()
        self.stack.addWidget(self.data_safety_view)

        self.admin_tools_view = AdminToolsView()
        self.stack.addWidget(self.admin_tools_view)

        body_layout.addWidget(self.stack, 1)
        main_layout.addLayout(body_layout, 1)

        # Footer Bar (unchanged)
        footer_frame = QFrame()
        footer_frame.setFixedHeight(70)
        footer_frame.setObjectName("SettingsFooter")
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(30, 15, 30, 15)
        footer_layout.setSpacing(15)

        footer_layout.addStretch()

        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setFixedSize(140, 40)
        self.btn_save.setObjectName("BtnSave")
        self.btn_save.clicked.connect(self.save_all)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedSize(120, 40)
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.clicked.connect(self.close_requested.emit)

        footer_layout.addWidget(self.btn_save)
        footer_layout.addWidget(self.btn_cancel)

        main_layout.addWidget(footer_frame)

        self.setWindowTitle("Settings - CB POS")

        # Animation
        self.anim_width = QPropertyAnimation(self.sidebar, b"minimumWidth")
        self.anim_width.setDuration(300)
        self.anim_width.setEasingCurve(QEasingCurve.Type.InOutQuart)

        self.anim_max_width = QPropertyAnimation(self.sidebar, b"maximumWidth")
        self.anim_max_width.setDuration(300)
        self.anim_max_width.setEasingCurve(QEasingCurve.Type.InOutQuart)

        # Apply initial styles
        self.update_sidebar_styles()
        self.highlight_active_page(0)

        # Register theme callback
        ThemeService.register_theme_callback(self.update_sidebar_icons)

    def create_nav_button(self, text: str, icon: str, index: int) -> SidebarButton:
        """Create a sidebar navigation button connected to the given stack index."""
        btn = SidebarButton(f"   {text}", icon)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda checked=False, idx=index: self.switch_page(idx))
        self.sidebar_layout.addWidget(btn)
        self.nav_buttons.append(btn)
        return btn

    def switch_page(self, index: int) -> None:
        """Switch the stacked widget to the given page index."""
        self.stack.setCurrentIndex(index)

    def highlight_active_page(self, index: int) -> None:
        """Highlight the active nav button based on current stack index."""
        for i, btn in enumerate(self.nav_buttons):
            is_active = i == index
            btn.set_active(is_active)
            btn.setProperty("active", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def toggle_sidebar(self) -> None:
        """Animate sidebar between expanded (250px) and collapsed (70px)."""
        start_width = self.sidebar.width()

        if self.is_collapsed:
            end_width = 250
            self.lbl_logo.setVisible(True)
            style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            self.is_collapsed = False
        else:
            end_width = 70
            self.lbl_logo.setVisible(False)
            style = Qt.ToolButtonStyle.ToolButtonIconOnly
            self.is_collapsed = True

        self.anim_width.setStartValue(start_width)
        self.anim_width.setEndValue(end_width)
        self.anim_width.start()

        self.anim_max_width.setStartValue(start_width)
        self.anim_max_width.setEndValue(end_width)
        self.anim_max_width.start()

        self.update_sidebar_styles()

        for btn in self.nav_buttons:
            btn.setToolButtonStyle(style)

    def update_sidebar_styles(self) -> None:
        """Update collapsed property on all sidebar buttons for QSS targeting."""
        for btn in self.nav_buttons:
            btn.setProperty("collapsed", self.is_collapsed)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def update_sidebar_icons(self) -> None:
        """Update sidebar button icons when theme changes."""
        for btn in self.nav_buttons:
            if hasattr(btn, "update_icon"):
                btn.update_icon()

        # Also update toggle button icon
        icon_color = ThemeService.get_icon_color()
        self.btn_toggle.setIcon(Icons.get("fa5s.bars", icon_color))

        # Update logo
        logo_path = ThemeService.get_logo_path()
        logo_pixmap = QPixmap(logo_path)
        if not logo_pixmap.isNull():
            self.lbl_logo.setPixmap(logo_pixmap.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation))

    def set_user(self, user) -> None:
        """Show/hide admin-only sidebar buttons based on user role."""
        role = user.role.name.lower() if user.role else "cashier"
        is_admin = "admin" in role
        self.btn_data_safety.setVisible(is_admin)
        self.btn_admin_tools.setVisible(is_admin)

    def load_settings(self):
        settings = ConfigService.get_all()
        for page in self.pages:
            page.load(settings)

    def save_all(self):
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        if not check_permission_with_override(Permissions.ADMIN_SETTINGS, self):
            return

        current_config = ConfigService.get_all()
        current_lang = current_config.get("language", "en")
        current_theme = current_config.get("theme", "Dark")
        current_font_size = current_config.get("font_size", 12)

        all_settings = {}
        try:
            for page in self.pages:
                all_settings.update(page.save())
        except ValueError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
            return

        ConfigService.update_all(all_settings)

        new_theme = all_settings.get("theme", current_theme)
        new_lang = all_settings.get("language", current_lang)
        new_font_size = all_settings.get("font_size", current_font_size)

        ThemeService.apply_theme(new_theme)

        restart_required = (
            new_lang != current_lang
            or new_font_size != current_font_size
            or all_settings.get("db_mode") != current_config.get("db_mode")
        )

        if restart_required:
            QMessageBox.information(
                self,
                "Restart Required",
                "Please restart the application to apply changes completely.",
            )
        else:
            QMessageBox.information(self, "Saved", "Settings saved successfully.")

        self.close_requested.emit()
