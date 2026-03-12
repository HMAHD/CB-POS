from PyQt6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QWidget,
    QVBoxLayout,
    QApplication,
)
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import Qt
from cbpos.ui.views.login_view import LoginView
from cbpos.ui.views.sales_view import SalesView
from cbpos.ui.views.management_view import ManagementView
from cbpos.ui.views.settings_view import SettingsView
from cbpos.infrastructure.hardware.scanner import BarcodeScanner
from cbpos.infrastructure.session_watchdog import SessionWatchdog
from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
import logging

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("")
        self.resize(1280, 800)

        # Scanner Hook
        self.scanner = BarcodeScanner(QApplication.instance())
        self.scanner.barcode_scanned.connect(self.on_barcode_scanned)

        # Session Watchdog (0 = disabled)
        timeout = int(ConfigService.get("session_timeout_minutes") or 0)
        self.watchdog = SessionWatchdog(timeout_minutes=max(timeout, 0), parent=self)
        self.watchdog.session_expired.connect(self.logout)

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Stack
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)

        # Initialize Views
        self.init_views()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def retranslate_ui(self) -> None:
        """Update all translatable text in the window."""
        self.setWindowTitle(_t("main_window.title"))

    def init_views(self):
        # 0. Login View
        self.login_view = LoginView()
        self.login_view.login_success.connect(self.on_login_success)
        self.stack.addWidget(self.login_view)

        # 1. Sales View
        self.sales_view = SalesView()
        # Connect Side Menu Signals
        self.sales_view.side_menu.management_clicked.connect(self.switch_to_management)
        self.sales_view.side_menu.documents_clicked.connect(self.switch_to_documents)
        self.sales_view.side_menu.receive_payment_clicked.connect(self.sales_view.open_receive_payment)
        self.sales_view.side_menu.reprint_receipt_clicked.connect(self.sales_view.open_reprint_receipt)
        self.sales_view.side_menu.refund_clicked.connect(self.sales_view.open_sale_history)
        self.sales_view.side_menu.history_clicked.connect(self.sales_view.open_sale_history)
        self.sales_view.side_menu.logout_clicked.connect(self.logout)
        self.sales_view.side_menu.settings_clicked.connect(self.switch_to_settings)
        self.sales_view.side_menu.fullscreen_clicked.connect(self.toggle_fullscreen)
        self.sales_view.side_menu.power_clicked.connect(self.close)
        self.stack.addWidget(self.sales_view)

        # 2. Management View
        self.management_view = ManagementView()
        self.management_view.logout_requested.connect(self.logout)
        self.management_view.request_pos_view.connect(lambda: self.stack.setCurrentWidget(self.sales_view))
        self.management_view.convert_proforma_to_sale.connect(self.on_convert_proforma)
        self.stack.addWidget(self.management_view)

        # 3. Settings View (Top Level)
        self.settings_view = SettingsView()
        self.settings_view.close_requested.connect(self.go_back)
        self.settings_view.logout_requested.connect(self.logout)
        self.settings_view.request_pos_view.connect(lambda: self.stack.setCurrentWidget(self.sales_view))
        self.stack.addWidget(self.settings_view)

        self.stack.setCurrentWidget(self.login_view)

        # Fullscreen Shortcut
        self.shortcut_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.shortcut_esc.activated.connect(self.exit_fullscreen)

        # Track history for "Back" button
        self.last_index = 0
        self.stack.currentChanged.connect(self.on_stack_changed)

    def on_stack_changed(self, index):
        # Don't track SettingsView (index 3) as a history point
        if index != 3:
            self.last_index = index

    def go_back(self):
        self.stack.setCurrentIndex(self.last_index)

    def on_login_success(self, user):
        self.user = user

        # Start Watchdog
        self.watchdog.start_monitoring()

        # Pass user to views
        if hasattr(self.management_view, "set_user"):
            self.management_view.set_user(user)

        if hasattr(self.settings_view, "set_user"):
            self.settings_view.set_user(user)

        if hasattr(self.sales_view, "side_menu"):
            self.sales_view.side_menu.set_user(user)

        # Switch to Sales View (Default)
        self.stack.setCurrentWidget(self.sales_view)

    def logout(self):
        self.user = None

        # Stop Watchdog
        self.watchdog.stop_monitoring()

        self.stack.setCurrentWidget(self.login_view)

    def on_barcode_scanned(self, barcode):
        # Pass to current view
        current = self.stack.currentWidget()
        if hasattr(current, "process_barcode_external"):
            current.process_barcode_external(barcode)

    def switch_to_management(self):
        self.stack.setCurrentWidget(self.management_view)
        # Hide side menu in sales view if open
        self.sales_view.side_menu.setVisible(False)

    def switch_to_documents(self):
        self.stack.setCurrentWidget(self.management_view)
        self.management_view.switch_tab(5)  # Documents is index 5
        self.sales_view.side_menu.setVisible(False)

    def switch_to_settings(self):
        # Save current index before switching
        self.last_index = self.stack.currentIndex()
        self.stack.setCurrentWidget(self.settings_view)
        # Hide side menu in sales view if open
        self.sales_view.side_menu.setVisible(False)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
            # Optional: Show notification/toast here
            logger.info(_t("main_window.fullscreen_hint"))

    def on_convert_proforma(self, cart_data: dict) -> None:
        """Handle proforma-to-sale conversion by loading items into the SalesView cart."""
        from decimal import Decimal

        # Clear existing cart
        self.sales_view.cart_service.clear()

        # Load proforma items into cart
        for item in cart_data.get("items", []):
            product = item.get("product")
            qty = Decimal(str(item.get("quantity", 1)))
            if product:
                self.sales_view.cart_service.add_item(product, qty)

        # Set customer if specified
        if cart_data.get("customer_id"):
            from cbpos.core.services.customer_service import CustomerService

            customer = CustomerService().get_customer(cart_data["customer_id"])
            if customer:
                self.sales_view.cart_service.set_customer(customer)

        # Store proforma_id for marking as converted after sale completes
        self.sales_view._pending_proforma_id = cart_data.get("proforma_id")

        # Switch to SalesView
        self.stack.setCurrentWidget(self.sales_view)
        self.sales_view.update_cart_display()

    def closeEvent(self, event) -> None:
        """Auto-backup on close if enabled in settings."""
        if ConfigService.get("auto_backup_on_close"):
            try:
                from cbpos.core.services.backup_service import BackupService

                backup_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
                BackupService.create_backup(backup_dir)
                keep = int(ConfigService.get("backup_retention_count") or 5)
                BackupService.cleanup_old_backups(backup_dir, keep)
            except Exception:
                logging.getLogger(__name__).exception("Auto-backup on close failed")
        super().closeEvent(event)

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
