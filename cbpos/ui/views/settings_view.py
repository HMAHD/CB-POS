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
from cbpos.i18n import _t, register_language_callback, unregister_language_callback


class SettingsView(QWidget):
    close_requested = pyqtSignal()
    logout_requested = pyqtSignal()
    request_pos_view = pyqtSignal()

    def __init__(self):
        super().__init__()
        from cbpos.core.services.config_service import ConfigService

        self.is_collapsed = bool(ConfigService.get("sidebar_collapsed"))
        self._settings_dirty = False
        self._saved_snapshot: dict = {}
        self.nav_buttons = []
        self.init_ui()
        if self.is_collapsed:
            self._apply_collapsed_state()
        self.load_settings()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

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
        self.sidebar_layout.addSpacing(10)

        # Navigation buttons — config pages
        self.btn_shop_info = self.create_nav_button("", "fa5s.store", 0)
        self.btn_sales_tax = self.create_nav_button("", "fa5s.shopping-cart", 1)
        self.btn_documents = self.create_nav_button("", "fa5s.file-invoice", 2)
        self.btn_hardware = self.create_nav_button("", "fa5s.print", 3)
        self.btn_receipt = self.create_nav_button("", "fa5s.receipt", 4)
        self.btn_system = self.create_nav_button("", "fa5s.cogs", 5)
        self.btn_network = self.create_nav_button("", "fa5s.network-wired", 6)
        self.btn_payment_methods = self.create_nav_button("", "fa5s.credit-card", 7)

        # Operational buttons (same list, no gap)
        self.btn_data_safety = self.create_nav_button("", "fa5s.shield-alt", 8)
        self.btn_admin_tools = self.create_nav_button("", "fa5s.toolbox", 9)

        self.sidebar_layout.addStretch()

        # Bottom Section (POS + Logout) — matches ManagementView
        self.user_profile_widget = QWidget()
        self.user_profile_widget.setObjectName("UserProfileContainer")
        user_profile_layout = QVBoxLayout(self.user_profile_widget)
        user_profile_layout.setContentsMargins(0, 0, 0, 0)
        user_profile_layout.setSpacing(0)

        self.btn_pos = SidebarButton("", "fa5s.cash-register")
        self.btn_pos.setObjectName("BtnPos")
        self.btn_pos.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_pos.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_pos.clicked.connect(self._on_pos_clicked)
        user_profile_layout.addWidget(self.btn_pos)

        self.btn_logout = SidebarButton("", Icons.LOGOUT)
        self.btn_logout.setObjectName("BtnLogout")
        self.btn_logout.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_logout.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_logout.clicked.connect(self._on_logout_clicked)
        user_profile_layout.addWidget(self.btn_logout)

        user_profile_layout.addSpacing(10)
        self.sidebar_layout.addWidget(self.user_profile_widget)

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

        self.btn_save = QPushButton("")
        self.btn_save.setFixedSize(140, 40)
        self.btn_save.setObjectName("BtnSave")
        self.btn_save.clicked.connect(self.save_all)

        self.btn_cancel = QPushButton("")
        self.btn_cancel.setFixedSize(120, 40)
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.clicked.connect(self.close_requested.emit)

        footer_layout.addWidget(self.btn_save)
        footer_layout.addWidget(self.btn_cancel)

        main_layout.addWidget(footer_frame)

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

    def retranslate_ui(self) -> None:
        """Update all translatable text in the view."""
        self.setWindowTitle(_t("settings.title"))

        # Nav buttons
        self.btn_shop_info.setText("   " + _t("settings.sidebar_shop_info"))
        self.btn_sales_tax.setText("   " + _t("settings.sidebar_sales_tax"))
        self.btn_documents.setText("   " + _t("settings.sidebar_documents"))
        self.btn_hardware.setText("   " + _t("settings.sidebar_hardware"))
        self.btn_receipt.setText("   " + _t("settings.sidebar_receipt"))
        self.btn_system.setText("   " + _t("settings.sidebar_system"))
        self.btn_network.setText("   " + _t("settings.sidebar_network"))
        self.btn_payment_methods.setText("   " + _t("settings.sidebar_payments"))
        self.btn_data_safety.setText("   " + _t("settings.sidebar_data_safety"))
        self.btn_admin_tools.setText("   " + _t("settings.sidebar_admin_tools"))

        # Bottom sidebar buttons
        self.btn_pos.setText("   " + _t("management.sidebar_pos"))
        self.btn_logout.setText("   " + _t("management.sidebar_logout"))

        # Footer buttons
        self.btn_save.setText(_t("settings.btn_save"))
        self.btn_cancel.setText(_t("settings.btn_cancel"))

    def create_nav_button(self, text: str, icon: str, index: int) -> SidebarButton:
        """Create a sidebar navigation button connected to the given stack index."""
        btn = SidebarButton(f"   {text}", icon)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda checked=False, idx=index: self.switch_page(idx))
        self.sidebar_layout.addWidget(btn)
        self.nav_buttons.append(btn)
        return btn

    def _take_snapshot(self) -> dict:
        """Collect current values from all config pages for dirty comparison."""
        snapshot: dict = {}
        for page in self.pages:
            try:
                snapshot.update(page.save())
            except (ValueError, Exception):
                pass
        return snapshot

    def switch_page(self, index: int) -> None:
        """Switch the stacked widget to the given page index.

        If settings have been modified, prompt the user before switching.
        """
        if self._saved_snapshot and self._take_snapshot() != self._saved_snapshot:
            reply = QMessageBox.question(
                self,
                _t("settings.unsaved_title"),
                _t("settings.unsaved_message"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
            # User chose to discard — reload to reset dirty state
            self.load_settings()
        self.stack.setCurrentIndex(index)

    def highlight_active_page(self, index: int) -> None:
        """Highlight the active nav button based on current stack index."""
        for i, btn in enumerate(self.nav_buttons):
            is_active = i == index
            btn.set_active(is_active)
            btn.setProperty("active", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _apply_collapsed_state(self) -> None:
        """Set sidebar to collapsed (icon-only) mode without animation."""
        self.sidebar.setFixedWidth(70)
        self.lbl_logo.setVisible(False)
        style = Qt.ToolButtonStyle.ToolButtonIconOnly
        self.btn_pos.setToolButtonStyle(style)
        self.btn_logout.setToolButtonStyle(style)
        for btn in self.nav_buttons:
            btn.setToolButtonStyle(style)

    def toggle_sidebar(self) -> None:
        """Animate sidebar between expanded (250px) and collapsed (70px)."""
        from cbpos.core.services.config_service import ConfigService

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

        ConfigService.set("sidebar_collapsed", self.is_collapsed)

        self.anim_width.setStartValue(start_width)
        self.anim_width.setEndValue(end_width)
        self.anim_width.start()

        self.anim_max_width.setStartValue(start_width)
        self.anim_max_width.setEndValue(end_width)
        self.anim_max_width.start()

        self.update_sidebar_styles()

        self.btn_pos.setToolButtonStyle(style)
        self.btn_logout.setToolButtonStyle(style)
        for btn in self.nav_buttons:
            btn.setToolButtonStyle(style)

    def update_sidebar_styles(self) -> None:
        """Update collapsed property on all sidebar buttons for QSS targeting."""
        buttons = self.nav_buttons + [self.btn_pos, self.btn_logout]
        for btn in buttons:
            btn.setProperty("collapsed", self.is_collapsed)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def update_sidebar_icons(self) -> None:
        """Update sidebar button icons when theme changes."""
        buttons = self.nav_buttons + [self.btn_pos, self.btn_logout]
        for btn in buttons:
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

    def _check_discard_unsaved(self) -> bool:
        """Check for unsaved changes and prompt user. Returns True if safe to proceed."""
        if self._saved_snapshot and self._take_snapshot() != self._saved_snapshot:
            reply = QMessageBox.question(
                self,
                _t("settings.unsaved_title"),
                _t("settings.unsaved_message"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return False
            self.load_settings()
        return True

    def _on_pos_clicked(self) -> None:
        """Navigate to POS/Sales view, prompting for unsaved changes."""
        if self._check_discard_unsaved():
            self.request_pos_view.emit()

    def _on_logout_clicked(self) -> None:
        """Logout, prompting for unsaved changes."""
        if self._check_discard_unsaved():
            self.logout_requested.emit()

    def load_settings(self):
        settings = ConfigService.get_all()
        for page in self.pages:
            page.load(settings)
        self._saved_snapshot = self._take_snapshot()

    def save_all(self):
        import json

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
            QMessageBox.warning(self, _t("common.validation_error"), str(e))
            return

        # Audit log tax rate changes before saving
        tax_keys = [
            "tax_vat_rate",
            "tax_sscl_rate",
            "tax_sscl_turnover_pct",
            "vat_registered",
        ]
        tax_changes = {}
        for key in tax_keys:
            old_val = current_config.get(key)
            new_val = all_settings.get(key)
            if new_val is not None and str(old_val) != str(new_val):
                tax_changes[key] = {"old": old_val, "new": new_val}

        if tax_changes:
            from cbpos.core.services.auth_service import AuthService
            from cbpos.core.database import Database
            from cbpos.core.models import AuditLog

            user = AuthService.get_current_user()
            if user:
                db = Database()
                try:
                    terminal_id = ConfigService.get("terminal_id") or "TERM-01"
                    with db.get_session() as session:
                        log = AuditLog(
                            user_id=user.id,
                            action="TAX_RATE_CHANGE",
                            event_type="SECURITY",
                            terminal_id=terminal_id,
                            details=json.dumps(tax_changes),
                        )
                        session.add(log)
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).warning("Tax audit log failed: %s", e)

        ConfigService.update_all(all_settings)

        new_theme = all_settings.get("theme", current_theme)
        new_lang = all_settings.get("language", current_lang)
        new_font_size = all_settings.get("font_size", current_font_size)

        ThemeService.apply_theme(new_theme)

        # Apply language change immediately (live retranslation)
        if new_lang != current_lang:
            from cbpos.i18n import set_language

            set_language(new_lang)

        restart_required = new_font_size != current_font_size or all_settings.get("db_mode") != current_config.get(
            "db_mode"
        )

        if restart_required:
            QMessageBox.information(
                self,
                _t("settings.restart_title"),
                _t("settings.restart_message"),
            )
        else:
            QMessageBox.information(
                self,
                _t("settings.saved_title"),
                _t("settings.saved_message"),
            )

        self._saved_snapshot = self._take_snapshot()
        self.close_requested.emit()
