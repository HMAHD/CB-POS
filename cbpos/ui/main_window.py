import logging
import weakref

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.shift_service import ShiftService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.infrastructure.hardware.scanner import BarcodeScanner
from cbpos.infrastructure.session_watchdog import SessionWatchdog
from cbpos.ui.dialogs.start_shift_dialog import StartShiftDialog
from cbpos.ui.views.login_view import LoginView
from cbpos.ui.views.management_view import ManagementView
from cbpos.ui.views.sales_view import SalesView
from cbpos.ui.views.settings_view import SettingsView

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level window: owns the view stack (login/sales/management/settings),
    the barcode scanner and session watchdog, and cross-view navigation/signal wiring.
    """

    def __init__(self):
        """Build the window chrome, hook the scanner/watchdog, and initialize all views."""
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

        # Sync Status Bar (top-right, only visible in main/terminal mode)
        from cbpos.ui.widgets.sync_status_widget import SyncStatusWidget

        self._sync_status_bar = QWidget()
        sync_bar_layout = QHBoxLayout(self._sync_status_bar)
        sync_bar_layout.setContentsMargins(0, 0, 0, 0)
        sync_bar_layout.addStretch()
        self.sync_status = SyncStatusWidget()
        sync_bar_layout.addWidget(self.sync_status)
        self.main_layout.addWidget(self._sync_status_bar)

        # Sync server/client references (set by main.py)
        self._sync_server = None
        self._sync_client = None

        # Stack
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)

        # Initialize Views
        self.init_views()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        # A plain lambda closing over `self` creates a reference cycle
        # (self -> Qt's destroyed-signal connection list -> the lambda ->
        # self) that only a full gc.collect() pass can break -- and can
        # segfault if that pass runs while the QObject's C++ side is mid-
        # teardown (#392). A weakref avoids creating the cycle at all.
        self_ref = weakref.ref(self)

        def _unregister():
            view = self_ref()
            if view is not None:
                unregister_language_callback(view.retranslate_ui)

        self.destroyed.connect(_unregister)

    def retranslate_ui(self) -> None:
        """Update all translatable text in the window."""
        self.setWindowTitle(_t("main_window.title"))

    def init_views(self):
        """Create login/sales/management/settings views, wire their signals, and add them to the stack."""
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
        self.sales_view.side_menu.shift_status_clicked.connect(self.sales_view.open_shift_status)
        self.sales_view.side_menu.close_shift_clicked.connect(self.sales_view.open_shift_closing)
        self.sales_view.shift_closed.connect(self.logout)
        self.sales_view.printer_setup_requested.connect(self.open_hardware_settings)
        self.sales_view.side_menu.logout_clicked.connect(self.logout)
        self.sales_view.side_menu.settings_clicked.connect(self.switch_to_settings)
        self.sales_view.side_menu.fullscreen_clicked.connect(self.toggle_fullscreen)
        self.sales_view.side_menu.power_clicked.connect(self.close)
        self.stack.addWidget(self.sales_view)

        # 2. Management View
        self.management_view = ManagementView()
        self.management_view.logout_requested.connect(self.logout)
        self.management_view.request_pos_view.connect(self._navigate_to_pos)
        self.management_view.convert_proforma_to_sale.connect(self.on_convert_proforma)
        self.stack.addWidget(self.management_view)

        # 3. Settings View (Top Level)
        self.settings_view = SettingsView()
        self.settings_view.close_requested.connect(self.go_back)
        self.settings_view.logout_requested.connect(self.logout)
        self.settings_view.request_pos_view.connect(self._navigate_to_pos)
        self.stack.addWidget(self.settings_view)

        self.stack.setCurrentWidget(self.login_view)

        # Fullscreen Shortcut
        self.shortcut_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.shortcut_esc.activated.connect(self.exit_fullscreen)

        # Track history for "Back" button
        self.last_index = 0
        self.stack.currentChanged.connect(self.on_stack_changed)

    def on_stack_changed(self, index):
        """Record the last non-Settings view index, so the Settings back button returns to it."""
        # Don't track SettingsView (index 3) as a history point
        if index != 3:
            self.last_index = index

    def go_back(self):
        """Return to whichever view was active before switching to Settings."""
        self.stack.setCurrentIndex(self.last_index)

    def _navigate_to_pos(self) -> None:
        """Switch to the POS/Sales view."""
        self.stack.setCurrentWidget(self.sales_view)

    def on_login_success(self, user):
        """Start the session watchdog, propagate the logged-in user to views, and show Sales."""
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

        # Switch to Sales View first (#526) -- StartShiftDialog is modal and
        # blocks synchronously, so if it opened before this the login/PIN
        # page would still be the visually active page underneath it the
        # whole time the dialog is open.
        self.stack.setCurrentWidget(self.sales_view)

        # A shift must be open before reaching Sales -- prompt for the
        # starting float if one isn't already (e.g. after a crash/relogin
        # mid-shift, the existing shift is reused instead of re-prompting).
        if ShiftService().get_current_shift(user.id) is None:
            StartShiftDialog(user.id, parent=self).exec()

    def logout(self):
        """Clear the current user, stop the watchdog, and return to the login screen."""
        self.user = None
        self.sales_view.side_menu.set_user(None)

        # Stop Watchdog
        self.watchdog.stop_monitoring()

        self.stack.setCurrentWidget(self.login_view)

    def on_barcode_scanned(self, barcode):
        """Route a global scanner event to whichever view is currently active."""
        # Pass to current view
        current = self.stack.currentWidget()
        if hasattr(current, "process_barcode_external"):
            current.process_barcode_external(barcode)

    def switch_to_management(self):
        """Show the Management view and close the Sales view's side menu."""
        self.stack.setCurrentWidget(self.management_view)
        # Hide side menu in sales view if open
        self.sales_view.side_menu.setVisible(False)

    def switch_to_documents(self):
        """Show Management pre-switched to its Documents tab."""
        self.stack.setCurrentWidget(self.management_view)
        self.management_view.switch_tab(5)  # Documents is index 5
        self.sales_view.side_menu.setVisible(False)

    def switch_to_settings(self):
        """Show Settings, remembering the current view so Settings' back button can return to it."""
        # Save current index before switching
        self.last_index = self.stack.currentIndex()
        self.stack.setCurrentWidget(self.settings_view)
        # Hide side menu in sales view if open
        self.sales_view.side_menu.setVisible(False)

    def open_hardware_settings(self) -> None:
        """Show Settings on its Hardware page (from the Sales no-printer notice)."""
        self.switch_to_settings()
        self.settings_view.switch_page(SettingsView.HARDWARE_PAGE)

    def toggle_fullscreen(self):
        """Toggle between fullscreen and normal window state."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
            # Optional: Show notification/toast here
            logger.info(_t("main_window.fullscreen_hint"))

    def on_convert_proforma(self, cart_data: dict) -> None:
        """Handle proforma-to-sale conversion by loading items into the SalesView cart."""
        from decimal import Decimal

        # Clear existing cart and customer -- routed through the view's own
        # clear_customer() (not cart_service directly) so the action panel
        # display and self.customer stay in sync with cart_service instead
        # of silently keeping whatever customer was selected before this
        # conversion started.
        self.sales_view.cart_service.clear()
        self.sales_view.clear_customer()

        # Load proforma items into cart
        for item in cart_data.get("items", []):
            product = item.get("product")
            qty = Decimal(str(item.get("quantity", 1)))
            if product:
                self.sales_view.cart_service.add_item(product, qty)

        # Set customer if specified -- via the view's own set_customer() so
        # the action panel actually shows who the proforma was for, instead
        # of the customer being attached to cart_service (for pricing) while
        # the display and self.customer (used for the resulting Sale's own
        # customer_id) stayed on Walk-in.
        if cart_data.get("customer_id"):
            from cbpos.core.services.customer_service import CustomerService

            customer = CustomerService().get_customer(cart_data["customer_id"])
            if customer:
                self.sales_view.set_customer(customer)

        # Store proforma_id for marking as converted after sale completes
        self.sales_view._pending_proforma_id = cart_data.get("proforma_id")

        # Switch to SalesView
        self.stack.setCurrentWidget(self.sales_view)
        self.sales_view.update_cart_display()

    def closeEvent(self, event) -> None:
        """Warn about an active cart, auto-backup on close if enabled, stop sync threads."""
        cart_items = self.sales_view.cart_service.items
        if cart_items:
            from PyQt6.QtWidgets import QMessageBox

            box = QMessageBox(self)
            box.setWindowTitle(_t("main_window.exit_confirm_title"))
            box.setText(_t("main_window.exit_confirm_message", count=len(cart_items)))
            box.setIcon(QMessageBox.Icon.Warning)
            hold_btn = box.addButton(_t("main_window.exit_hold_and_exit"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(_t("main_window.exit_without_saving"), QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = box.addButton(_t("main_window.exit_cancel"), QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(cancel_btn)
            box.exec()

            clicked = box.clickedButton()
            if clicked is cancel_btn:
                event.ignore()
                return
            if clicked is hold_btn:
                self.sales_view.hold_bill()

        # Stop sync server/client
        if self._sync_server:
            self._sync_server.stop()
        if self._sync_client:
            self._sync_client.stop()

        # Stop the shared print/drawer worker thread (if one was ever
        # started) -- QThread aborts the process if destroyed while still
        # running, so it must be joined before the app exits.
        from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

        PrintWorker.shutdown()

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
        """Leave fullscreen mode if currently fullscreen (bound to the Escape shortcut)."""
        if self.isFullScreen():
            self.showNormal()
