import os
from PyQt6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QApplication,
)
from PyQt6.QtCore import Qt
from cbpos.ui.views.login_view import LoginView

from cbpos.infrastructure.hardware.scanner import BarcodeScanner


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CB POS - Industrial Retail System")
        self.resize(1024, 768)  # Default resolution

        # Scanner Hook
        self.scanner = BarcodeScanner(QApplication.instance())
        self.scanner.barcode_scanned.connect(self.on_barcode_scanned)

        # Load Theme
        self.load_theme()

        # Central Widget (Stack)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top Bar
        self.top_bar = QWidget()
        self.top_bar.setFixedHeight(40)
        self.top_bar.setStyleSheet(
            "background-color: #001226; border-bottom: 1px solid #00BCEB;"
        )
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(10, 0, 10, 0)

        self.lbl_status_printer = QLabel("PRINTER")
        self.lbl_status_printer.setStyleSheet(
            "color: #39FF14; font-weight: bold;"
        )  # Green = OK
        top_layout.addWidget(self.lbl_status_printer)

        top_layout.addSpacing(20)

        self.lbl_status_network = QLabel("OFFLINE MODE")
        self.lbl_status_network.setStyleSheet(
            "color: #FFDC00; font-weight: bold;"
        )  # Yellow = Offline
        top_layout.addWidget(self.lbl_status_network)

        top_layout.addStretch()

        self.lbl_user = QLabel("Not Logged In")
        self.lbl_user.setStyleSheet("color: white;")
        top_layout.addWidget(self.lbl_user)

        top_layout.addSpacing(20)

        # Settings Button
        from PyQt6.QtWidgets import QPushButton

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(30, 30)
        self.btn_settings.setStyleSheet(
            "background-color: #003366; color: white; border: none; font-size: 16px;"
        )
        self.btn_settings.clicked.connect(self.show_settings)
        top_layout.addWidget(self.btn_settings)

        main_layout.addWidget(self.top_bar)
        self.top_bar.setVisible(False)  # Hide by default (Login Screen)

        # Stack
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # Initialize Views
        self.init_views()

    def load_theme(self):
        """Load the global stylesheet."""
        theme_path = os.path.join(os.path.dirname(__file__), "styles", "theme.qss")
        try:
            with open(theme_path, "r") as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print(f"Warning: Theme file not found at {theme_path}")

    def init_views(self):
        """Initialize and add views to the stack."""
        # 1. Login View
        self.login_view = LoginView()
        self.login_view.login_success.connect(self.on_login_success)
        self.stack.addWidget(self.login_view)

        # 2. Dashboard (Placeholder)
        self.dashboard_view = QWidget()
        layout = QVBoxLayout(self.dashboard_view)
        label = QLabel("Welcome to CB POS Dashboard")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 32px; color: #39FF14;")
        layout.addWidget(label)
        self.stack.addWidget(self.dashboard_view)

        # Start at Login
        self.stack.setCurrentWidget(self.login_view)

    def on_login_success(self, user):
        self.user = user
        self.lbl_user.setText(
            f"User: {user.username} | Role: {user.role.name if user.role else 'N/A'}"
        )
        self.top_bar.setVisible(True)  # Show Status Bar
        print(f"Logged in as: {user.username}")

        # Load Sales View
        from cbpos.ui.views.sales_view import SalesView
        from cbpos.ui.views.settings_view import SettingsView

        self.sales_view = SalesView()
        self.settings_view = SettingsView()

        self.stack.addWidget(self.sales_view)
        self.stack.addWidget(self.settings_view)

        # Switch to Sales View
        self.stack.setCurrentWidget(self.sales_view)

    def on_barcode_scanned(self, barcode):
        print(f"Global Scanner Hook: {barcode}")
        # Pass to current view if it has a handler
        current_widget = self.stack.currentWidget()
        if hasattr(current_widget, "process_barcode_external"):
            current_widget.process_barcode_external(barcode)
        elif hasattr(current_widget, "barcode_input"):
            # Fallback: set text in input if it exists
            current_widget.barcode_input.setText(barcode)
            if hasattr(current_widget, "process_barcode"):
                current_widget.process_barcode()

    def show_settings(self):
        if hasattr(self, "settings_view"):
            self.stack.setCurrentWidget(self.settings_view)
