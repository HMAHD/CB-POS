import os
from PyQt6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QApplication,
    QFrame,
)
from PyQt6.QtCore import Qt
from cbpos.ui.views.login_view import LoginView
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.custom_widgets import SidebarButton
from cbpos.infrastructure.hardware.scanner import BarcodeScanner


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CB POS - Industrial Retail System")
        self.resize(1280, 800)

        # Scanner Hook
        self.scanner = BarcodeScanner(QApplication.instance())
        self.scanner.barcode_scanned.connect(self.on_barcode_scanned)

        # Load Theme
        self.load_theme()

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. Sidebar (Hidden initially)
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(250)
        self.sidebar.setStyleSheet(
            "background-color: #001226; border-right: 1px solid #003366;"
        )
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 20, 0, 20)
        self.sidebar_layout.setSpacing(5)

        # Logo Area
        lbl_logo = QLabel("CEYLON BYTE")
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_logo.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #00BCEB; margin-bottom: 20px;"
        )
        self.sidebar_layout.addWidget(lbl_logo)

        # Nav Buttons
        self.nav_buttons = []
        self.btn_dashboard = self.create_nav_button("Dashboard", Icons.DASHBOARD, 0)
        self.btn_sales = self.create_nav_button("Sales", Icons.SALES, 1)
        self.btn_inventory = self.create_nav_button("Inventory", Icons.INVENTORY, 2)
        self.btn_customers = self.create_nav_button("Customers", Icons.CUSTOMERS, 3)
        self.btn_reports = self.create_nav_button("Reports", Icons.REPORTS, 4)
        self.btn_settings = self.create_nav_button("Settings", Icons.SETTINGS, 5)

        self.sidebar_layout.addStretch()

        # User Info in Sidebar
        self.lbl_user = QLabel("Not Logged In")
        self.lbl_user.setStyleSheet("color: #AAAAAA; padding: 10px; font-size: 12px;")
        self.lbl_user.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_layout.addWidget(self.lbl_user)

        self.btn_logout = SidebarButton("Logout", Icons.LOGOUT)
        self.btn_logout.clicked.connect(self.logout)
        self.sidebar_layout.addWidget(self.btn_logout)

        self.main_layout.addWidget(self.sidebar)
        self.sidebar.setVisible(False)

        # 2. Main Content Area
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Top Bar (Status)
        self.top_bar = QWidget()
        self.top_bar.setFixedHeight(40)
        self.top_bar.setStyleSheet(
            "background-color: #001F3F; border-bottom: 1px solid #003366;"
        )
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)

        self.lbl_status_printer = QLabel("PRINTER")
        self.lbl_status_printer.setStyleSheet("color: #39FF14; font-weight: bold;")
        top_layout.addWidget(self.lbl_status_printer)

        top_layout.addStretch()

        self.lbl_date = QLabel("2023-10-27 10:00 AM")  # Placeholder
        self.lbl_date.setStyleSheet("color: white;")
        top_layout.addWidget(self.lbl_date)

        content_layout.addWidget(self.top_bar)
        self.top_bar.setVisible(False)

        # Stack
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)

        self.main_layout.addWidget(content_area)

        # Initialize Views
        self.init_views()

    def create_nav_button(self, text, icon, index):
        btn = SidebarButton(text, icon)
        btn.clicked.connect(lambda: self.switch_tab(index))
        self.sidebar_layout.addWidget(btn)
        self.nav_buttons.append(btn)
        return btn

    def switch_tab(self, index):
        self.stack.setCurrentIndex(index)
        # Update active state
        for i, btn in enumerate(self.nav_buttons):
            btn.set_active(i == index)

    def load_theme(self):
        theme_path = os.path.join(os.path.dirname(__file__), "styles", "theme.qss")
        try:
            with open(theme_path, "r") as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print(f"Warning: Theme file not found at {theme_path}")

    def init_views(self):
        # 0. Dashboard
        from cbpos.ui.views.dashboard_view import DashboardView

        self.dashboard_view = DashboardView()
        self.stack.addWidget(self.dashboard_view)

        # 1. Sales
        from cbpos.ui.views.sales_view import SalesView

        self.sales_view = SalesView()
        self.stack.addWidget(self.sales_view)

        # 2. Inventory (Placeholder)
        self.inventory_view = QLabel("Inventory View")
        self.inventory_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.inventory_view)

        # 3. Customers
        from cbpos.ui.views.customer_view import CustomerView

        self.customer_view = CustomerView()
        self.stack.addWidget(self.customer_view)

        # 4. Reports
        from cbpos.ui.views.reports_view import ReportsView

        self.reports_view = ReportsView()
        self.stack.addWidget(self.reports_view)

        # 5. Settings
        from cbpos.ui.views.settings_view import SettingsView

        self.settings_view = SettingsView()
        self.stack.addWidget(self.settings_view)

        # Login View
        self.login_view = LoginView()
        self.login_view.login_success.connect(self.on_login_success)
        self.stack.addWidget(self.login_view)

        self.stack.setCurrentWidget(self.login_view)

    def on_login_success(self, user):
        self.user = user
        self.lbl_user.setText(f"{user.username}\n{user.role.name if user.role else ''}")
        self.sidebar.setVisible(True)
        self.top_bar.setVisible(True)

        # Switch to Dashboard
        self.switch_tab(0)

    def logout(self):
        self.user = None
        self.sidebar.setVisible(False)
        self.top_bar.setVisible(False)
        self.stack.setCurrentWidget(self.login_view)

    def on_barcode_scanned(self, barcode):
        # Pass to current view
        current = self.stack.currentWidget()
        if hasattr(current, "process_barcode_external"):
            current.process_barcode_external(barcode)
