"""Top-level Settings screen with sidebar navigation to configuration pages."""

import contextlib
import json
import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.constants.permissions import Permissions
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.views.settings_pages import (
    DocumentPage,
    HardwarePage,
    NetworkPage,
    ReceiptPage,
    SalesTaxPage,
    ShopInfoPage,
    SystemPage,
)
from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar

logger = logging.getLogger(__name__)


class SettingsView(QWidget):
    """Settings screen with a sidebar for config pages and operational tools (payments, data safety, admin)."""

    close_requested = pyqtSignal()
    logout_requested = pyqtSignal()
    request_pos_view = pyqtSignal()

    def __init__(self):
        """Build the UI, load current settings, and register the translation callback."""
        super().__init__()
        self._settings_dirty = False
        self._saved_snapshot: dict = {}
        self.init_ui()
        self.load_settings()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def init_ui(self):
        """Build the sidebar, stacked config/operational pages, and Save/Cancel footer."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # --- Sidebar ---
        self.sidebar = CollapsibleSidebar()
        self.sidebar.nav_clicked.connect(self.switch_page)
        self.sidebar.pos_clicked.connect(self._on_pos_clicked)
        self.sidebar.logout_clicked.connect(self._on_logout_clicked)

        # Navigation buttons — config pages
        self.btn_shop_info = self.sidebar.add_nav_button("", "fa5s.store", 0)
        self.btn_sales_tax = self.sidebar.add_nav_button("", "fa5s.shopping-cart", 1)
        self.btn_documents = self.sidebar.add_nav_button("", "fa5s.file-invoice", 2)
        self.btn_hardware = self.sidebar.add_nav_button("", "fa5s.print", 3)
        self.btn_receipt = self.sidebar.add_nav_button("", "fa5s.receipt", 4)
        self.btn_system = self.sidebar.add_nav_button("", "fa5s.cogs", 5)
        self.btn_network = self.sidebar.add_nav_button("", "fa5s.network-wired", 6)
        self.btn_payment_methods = self.sidebar.add_nav_button("", "fa5s.credit-card", 7)

        # Operational buttons
        self.btn_data_safety = self.sidebar.add_nav_button("", "fa5s.shield-alt", 8)
        self.btn_admin_tools = self.sidebar.add_nav_button("", "fa5s.toolbox", 9)

        self.sidebar.finalize()
        self.sidebar.highlight(0)
        body_layout.addWidget(self.sidebar)

        # --- Content Area ---
        self.stack = QStackedWidget()
        self.stack.setObjectName("SettingsContent")
        self.stack.currentChanged.connect(self.sidebar.highlight)

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
        from cbpos.ui.views.admin_tools_view import AdminToolsView
        from cbpos.ui.views.data_safety_view import DataSafetyView
        from cbpos.ui.views.payment_methods_view import PaymentMethodsView

        self.payment_methods_view = PaymentMethodsView()
        self.stack.addWidget(self.payment_methods_view)

        self.data_safety_view = DataSafetyView()
        self.stack.addWidget(self.data_safety_view)

        self.admin_tools_view = AdminToolsView()
        self.stack.addWidget(self.admin_tools_view)

        body_layout.addWidget(self.stack, 1)
        main_layout.addLayout(body_layout, 1)

        # --- Footer Bar (Save/Cancel shown only on config pages 0-6;
        #     the frame itself always stays visible to reserve its height) ---
        self.footer_frame = QFrame()
        self.footer_frame.setFixedHeight(70)
        self.footer_frame.setObjectName("SettingsFooter")
        footer_layout = QHBoxLayout(self.footer_frame)
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

        main_layout.addWidget(self.footer_frame)

        # Hide Save/Cancel (not the frame) on operational pages (they auto-save)
        self.stack.currentChanged.connect(self._update_footer_visibility)

    def retranslate_ui(self) -> None:
        """Update all translatable text in the view."""
        self.setWindowTitle(_t("settings.title"))

        # Nav buttons
        self.btn_shop_info.setText(_t("settings.sidebar_shop_info"))
        self.btn_sales_tax.setText(_t("settings.sidebar_sales_tax"))
        self.btn_documents.setText(_t("settings.sidebar_documents"))
        self.btn_hardware.setText(_t("settings.sidebar_hardware"))
        self.btn_receipt.setText(_t("settings.sidebar_receipt"))
        self.btn_system.setText(_t("settings.sidebar_system"))
        self.btn_network.setText(_t("settings.sidebar_network"))
        self.btn_payment_methods.setText(_t("settings.sidebar_payments"))
        self.btn_data_safety.setText(_t("settings.sidebar_data_safety"))
        self.btn_admin_tools.setText(_t("settings.sidebar_admin_tools"))

        # Bottom sidebar buttons
        self.sidebar.retranslate_pos_logout()

        # Footer buttons
        self.btn_save.setText(_t("settings.btn_save"))
        self.btn_cancel.setText(_t("settings.btn_cancel"))

    # ------------------------------------------------------------------
    # Page switching with unsaved-changes guard
    # ------------------------------------------------------------------

    def _take_snapshot(self) -> dict:
        """Collect current values from all config pages for dirty comparison."""
        snapshot: dict = {}
        for page in self.pages:
            with contextlib.suppress(ValueError, Exception):
                snapshot.update(page.save())
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

    def _update_footer_visibility(self, index: int) -> None:
        """Hide only the Save/Cancel buttons on operational pages (they
        auto-save) -- never the whole footer_frame. Hiding the frame
        itself let Qt reclaim its 70px, making those 3 pages' content
        area render taller than every config page's, a jump a user would
        read as "this page feels different" for no visible reason."""
        has_save = index < len(self.pages)
        self.btn_save.setVisible(has_save)
        self.btn_cancel.setVisible(has_save)

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

    # ------------------------------------------------------------------
    # User / permissions
    # ------------------------------------------------------------------

    def set_user(self, user) -> None:
        """Show/hide admin-only sidebar buttons based on user permissions."""
        is_admin = PermissionService.user_has_permission(user, Permissions.ADMIN_SETTINGS)
        self.btn_data_safety.setVisible(is_admin)
        self.btn_admin_tools.setVisible(is_admin)

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def load_settings(self):
        """Load current settings into every config page and snapshot the values for dirty-checking."""
        settings = ConfigService.get_all()
        for page in self.pages:
            page.load(settings)
        self._saved_snapshot = self._take_snapshot()

    def save_all(self):
        """Validate and save all config pages, then apply the changes live.

        Checks the ADMIN_SETTINGS permission, audits tax-rate changes to
        AuditLog, persists settings, restarts the scheduler timer if the
        auto-report toggle changed, applies the new theme/language
        immediately, and prompts for a restart if font size or
        terminal/db mode changed.
        """
        from cbpos.core.utils.permission_helper import check_permission_with_override

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
            from cbpos.core.database import Database
            from cbpos.core.models import AuditLog
            from cbpos.core.services.auth_service import AuthService

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
                    logger.warning("Tax audit log failed: %s", e)

        ConfigService.update_all(all_settings)

        # Start/stop the auto-report scheduler timer live (#320) -- it used
        # to only be read once at process launch, so toggling this
        # checkbox had no effect until the next full app restart.
        if all_settings.get("auto_report_enabled") != current_config.get("auto_report_enabled"):
            from cbpos.core.services.scheduler_service import SchedulerService

            if all_settings.get("auto_report_enabled"):
                SchedulerService.start_timer()
            else:
                SchedulerService.stop_timer()

        new_theme = all_settings.get("theme", current_theme)
        new_lang = all_settings.get("language", current_lang)
        new_font_size = all_settings.get("font_size", current_font_size)

        ThemeService.apply_theme(new_theme)

        # Apply language change immediately (live retranslation)
        if new_lang != current_lang:
            from cbpos.i18n import set_language

            set_language(new_lang)

        restart_required = (
            new_font_size != current_font_size
            or all_settings.get("db_mode") != current_config.get("db_mode")
            or all_settings.get("terminal_mode") != current_config.get("terminal_mode")
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

    # ------------------------------------------------------------------
    # Responsive
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        """Auto-collapse sidebar on narrow screens."""
        super().resizeEvent(event)
        self.sidebar.handle_resize(event.size().width())
