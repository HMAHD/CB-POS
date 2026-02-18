from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
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
    NetworkPage,
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

        # Body: Sidebar (25%) + Content (75%)
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar (Fixed width for consistency)
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(260)
        self.sidebar.setObjectName("SettingsSidebar")
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
            ("Network", "fa5s.network-wired"),
            ("My Profile", "fa5s.user-cog"),
        ]

        for item_text, icon_name in items:
            item = QListWidgetItem(item_text)
            item.setIcon(qta.icon(icon_name, color="#CCCCCC"))
            item.setSizeHint(QSize(0, 50))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.sidebar.addItem(item)

        body_layout.addWidget(self.sidebar)

        # Content Area (Expands to fill remaining space)
        self.stack = QStackedWidget()
        self.stack.setObjectName("SettingsContent")

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
            NetworkPage(),
            ProfilePage(),
        ]

        for page in self.pages:
            self.stack.addWidget(page)

        body_layout.addWidget(self.stack, 1)  # Stretch factor: content takes remaining space
        main_layout.addLayout(body_layout, 1)

        # Footer Bar
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

        # Set window title
        self.setWindowTitle("Settings - CB POS")

        # Select first item
        self.sidebar.setCurrentRow(0)

    def change_page(self, index):
        self.stack.setCurrentIndex(index)

    def load_settings(self):
        settings = ConfigService.get_all()
        for page in self.pages:
            page.load(settings)

    def save_all(self):
        # Capture current state BEFORE update
        current_config = ConfigService.get_all()
        current_lang = current_config.get("language", "en")
        current_theme = current_config.get("theme", "Dark")
        current_font_size = current_config.get("font_size", 12)

        # Collect settings from all pages
        all_settings = {}
        try:
            for page in self.pages:
                all_settings.update(page.save())
        except ValueError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
            return

        # Persist settings
        ConfigService.update_all(all_settings)

        # Check what changed
        new_theme = all_settings.get("theme", current_theme)
        new_lang = all_settings.get("language", current_lang)
        new_font_size = all_settings.get("font_size", current_font_size)

        # Apply Theme Immediately
        ThemeService.apply_theme(new_theme)

        # Determine if restart is required
        # Use .get() to avoid KeyErrors if keys are missing
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
