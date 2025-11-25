import os
from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QLabel, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt
from cbpos.ui.views.login_view import LoginView
from cbpos.core.models import User

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CB POS - Industrial Retail System")
        self.resize(1024, 768) # Default resolution
        
        # Load Theme
        self.load_theme()

        # Central Widget (Stack)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

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

    def on_login_success(self, user: User):
        """Handle successful login."""
        print(f"Logged in as: {user.name} ({user.role})")
        
        # Lazy load Sales View
        from cbpos.ui.views.sales_view import SalesView
        self.sales_view = SalesView()
        self.stack.addWidget(self.sales_view)
        
        # Switch to Sales View
        self.stack.setCurrentWidget(self.sales_view)
