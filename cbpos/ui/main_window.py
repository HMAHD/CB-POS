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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CB POS - Industrial Retail System")
        self.resize(1280, 800)

        # Scanner Hook
        self.scanner = BarcodeScanner(QApplication.instance())
        self.scanner.barcode_scanned.connect(self.on_barcode_scanned)

        # Session Watchdog
        self.watchdog = SessionWatchdog(timeout_minutes=5, parent=self)
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

    def init_views(self):
        # 0. Login View
        self.login_view = LoginView()
        self.login_view.login_success.connect(self.on_login_success)
        self.stack.addWidget(self.login_view)

        # 1. Sales View
        self.sales_view = SalesView()
        # Connect Side Menu Signals
        self.sales_view.side_menu.management_clicked.connect(self.switch_to_management)
        self.sales_view.side_menu.logout_clicked.connect(self.logout)
        self.sales_view.side_menu.settings_clicked.connect(self.switch_to_settings)
        self.sales_view.side_menu.fullscreen_clicked.connect(self.toggle_fullscreen)
        self.sales_view.side_menu.power_clicked.connect(self.close)
        self.stack.addWidget(self.sales_view)

        # 2. Management View
        self.management_view = ManagementView()
        self.management_view.logout_requested.connect(self.logout)
        self.management_view.request_pos_view.connect(lambda: self.stack.setCurrentWidget(self.sales_view))
        self.stack.addWidget(self.management_view)

        # 3. Settings View (Top Level)
        self.settings_view = SettingsView()
        self.settings_view.close_requested.connect(self.go_back)
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
            print("Press Esc to exit fullscreen")

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
