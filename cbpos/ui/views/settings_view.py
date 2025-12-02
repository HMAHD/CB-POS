from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.views.settings_pages import (
    GeneralPage,
    SalesPage,
    TaxPage,
    InventoryPage,
    DocumentPage,
    HardwarePage,
    PaymentPage,
    ReceiptPage,
    AutomationPage,
    ProfilePage,
)


class SettingsView(QWidget):
    close_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #001F3F; border-bottom: 2px solid #003366;")
        header_frame.setFixedHeight(60)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 0, 20, 0)

        lbl_title = QLabel("Settings")
        lbl_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #00BCEB;")
        header_layout.addWidget(lbl_title)

        main_layout.addWidget(header_frame)

        # 2. Body (Sidebar + Content)
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 2.1 Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setStyleSheet(
            """
            QListWidget {
                background-color: #2D2D30;
                border: none;
                outline: none;
            }
            QListWidget::item {
                color: #FFFFFF;
                padding: 15px;
                border-bottom: 1px solid #3E3E42;
            }
            QListWidget::item:selected {
                background-color: #3E3E42;
                border-left: 4px solid #00BCEB;
                color: #FFFFFF;
            }
            QListWidget::item:hover {
                background-color: #3E3E42;
            }
        """
        )
        self.sidebar.currentRowChanged.connect(self.change_page)

        # Sidebar Items
        import qtawesome as qta

        items = [
            ("General", "fa5s.sliders-h"),
            ("Sales", "fa5s.shopping-cart"),
            ("Taxes", "fa5s.percent"),
            ("Inventory", "fa5s.boxes"),
            ("Documents", "fa5s.file-invoice"),
            ("Receipt", "fa5s.receipt"),
            ("Hardware", "fa5s.print"),
            ("Payments", "fa5s.credit-card"),
            ("Automation", "fa5s.robot"),
            ("My Profile", "fa5s.user-cog"),
        ]

        for item_text, icon_name in items:
            item = QListWidgetItem(item_text)
            item.setIcon(qta.icon(icon_name, color="white"))
            item.setSizeHint(QSize(0, 50))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.sidebar.addItem(item)

        body_layout.addWidget(self.sidebar)

        # 2.2 Content Area
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(
            "QWidget { background-color: #1E1E1E; color: #FFFFFF; } "
            "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit { "
            "background-color: #333337; color: white; border: 1px solid #555; "
            "padding: 5px; }"
        )

        # Initialize Pages
        self.pages = [
            GeneralPage(),
            SalesPage(),
            TaxPage(),
            InventoryPage(),
            DocumentPage(),
            ReceiptPage(),
            HardwarePage(),
            PaymentPage(),
            AutomationPage(),
            ProfilePage(),
        ]

        for page in self.pages:
            self.stack.addWidget(page)

        body_layout.addWidget(self.stack)
        main_layout.addLayout(body_layout)

        # 3. Footer
        footer_frame = QFrame()
        footer_frame.setFixedHeight(60)
        footer_frame.setStyleSheet("background-color: #2D2D30; border-top: 1px solid #3E3E42;")
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(20, 10, 20, 10)

        footer_layout.addStretch()

        self.btn_save = QPushButton("Save")
        self.btn_save.setFixedSize(100, 35)
        self.btn_save.setStyleSheet(
            "background-color: #39FF14; color: black; " "font-weight: bold; border-radius: 4px;"
        )
        self.btn_save.clicked.connect(self.save_all)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedSize(100, 35)
        self.btn_cancel.setStyleSheet(
            "background-color: #FF4136; color: white; " "font-weight: bold; border-radius: 4px;"
        )
        self.btn_cancel.clicked.connect(self.close_requested.emit)

        footer_layout.addWidget(self.btn_save)
        footer_layout.addWidget(self.btn_cancel)

        main_layout.addWidget(footer_frame)

        # Select first item
        self.sidebar.setCurrentRow(0)

    def change_page(self, index):
        self.stack.setCurrentIndex(index)

    def load_settings(self):
        settings = ConfigService.get_all()
        for page in self.pages:
            page.load(settings)

    def save_all(self):
        all_settings = {}
        try:
            for page in self.pages:
                all_settings.update(page.save())
        except ValueError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
            return

        # Capture current state BEFORE update
        current_lang = ConfigService.get_all().get("language", "en")
        current_font_size = ConfigService.get_all().get("font_size", 12)

        ConfigService.update_all(all_settings)

        # Apply Theme if theme OR font_size changed
        new_theme = all_settings.get("theme")
        new_font_size = all_settings.get("font_size")

        if new_theme or (new_font_size and new_font_size != current_font_size):
            # If theme not in settings (not changed), get current
            theme_to_apply = new_theme or ConfigService.get("theme")
            ThemeService.apply_theme(theme_to_apply)

        # Check if language changed
        new_lang = all_settings.get("language", "en")
        if new_lang != current_lang:
            QMessageBox.information(
                self,
                "Restart Required",
                "Please restart the application to apply language changes.",
            )
        else:
            QMessageBox.information(self, "Saved", "Settings saved successfully.")

        self.close_requested.emit()
