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
    ShopInfoPage,
    SalesTaxPage,
    InventoryPage,
    DocumentPage,
    HardwarePage,
    ReceiptPage,
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

        # Sidebar Items (7 consolidated pages)
        import qtawesome as qta

        items = [
            ("Shop Info", "fa5s.store"),
            ("Sales & Tax", "fa5s.shopping-cart"),
            ("Inventory", "fa5s.boxes"),
            ("Documents", "fa5s.file-invoice"),
            ("Hardware", "fa5s.print"),
            ("Receipt", "fa5s.receipt"),
            ("Network", "fa5s.network-wired"),
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

        # Initialize Pages (7 consolidated)
        self.pages = [
            ShopInfoPage(),
            SalesTaxPage(),
            InventoryPage(),
            DocumentPage(),
            HardwarePage(),
            ReceiptPage(),
            NetworkPage(),
        ]

        for page in self.pages:
            self.stack.addWidget(page)

        body_layout.addWidget(self.stack, 1)
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

        self.setWindowTitle("Settings - CB POS")
        self.sidebar.setCurrentRow(0)

    def change_page(self, index):
        self.stack.setCurrentIndex(index)

    def load_settings(self):
        settings = ConfigService.get_all()
        for page in self.pages:
            page.load(settings)

    def save_all(self):
        current_config = ConfigService.get_all()
        current_lang = current_config.get("language", "en")
        current_theme = current_config.get("theme", "Dark")
        current_font_size = current_config.get("font_size", 12)

        all_settings = {}
        try:
            for page in self.pages:
                all_settings.update(page.save())
        except ValueError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
            return

        ConfigService.update_all(all_settings)

        new_theme = all_settings.get("theme", current_theme)
        new_lang = all_settings.get("language", current_lang)
        new_font_size = all_settings.get("font_size", current_font_size)

        ThemeService.apply_theme(new_theme)

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
