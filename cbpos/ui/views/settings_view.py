from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QComboBox,
    QFormLayout,
    QMessageBox,
    QGroupBox,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.config_service import ConfigService


class SettingsView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Title
        title = QLabel("System Configuration")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #00BCEB;")
        main_layout.addWidget(title)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane { border: 1px solid #003366; }
            QTabBar::tab { background: #001F3F; color: white; padding: 10px; }
            QTabBar::tab:selected { background: #00BCEB; color: black; }
        """
        )

        self.tab_general = QWidget()
        self.tab_hardware = QWidget()
        self.tab_appearance = QWidget()

        self.tabs.addTab(self.tab_general, "General")
        self.tabs.addTab(self.tab_hardware, "Hardware")
        self.tabs.addTab(self.tab_appearance, "Appearance")

        self.init_general_tab()
        self.init_hardware_tab()
        self.init_appearance_tab()

        main_layout.addWidget(self.tabs)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save Settings")
        btn_save.setStyleSheet(
            "background-color: #39FF14; color: black; font-weight: bold; padding: 10px;"
        )
        btn_save.clicked.connect(self.save_settings)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)

        main_layout.addLayout(btn_layout)

    def init_general_tab(self):
        layout = QFormLayout(self.tab_general)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(20, 20, 20, 20)

        self.input_shop_name = QLineEdit()
        self.input_address = QLineEdit()
        self.input_phone = QLineEdit()
        self.input_vat = QLineEdit()
        self.input_header = QLineEdit()
        self.input_footer = QLineEdit()

        layout.addRow("Shop Name:", self.input_shop_name)
        layout.addRow("Address:", self.input_address)
        layout.addRow("Phone:", self.input_phone)
        layout.addRow("VAT Number:", self.input_vat)
        layout.addRow("Receipt Header:", self.input_header)
        layout.addRow("Receipt Footer:", self.input_footer)

    def init_hardware_tab(self):
        layout = QVBoxLayout(self.tab_hardware)
        layout.setContentsMargins(20, 20, 20, 20)

        # Printer Group
        grp_printer = QGroupBox("Printer Configuration")
        form_layout = QFormLayout(grp_printer)

        self.combo_printer_type = QComboBox()
        self.combo_printer_type.addItems(["USB", "NETWORK", "MOCK"])

        self.input_printer_path = QLineEdit()
        self.input_printer_path.setPlaceholderText(
            "e.g., COM3, 192.168.1.100, or empty for Auto-USB"
        )

        form_layout.addRow("Printer Type:", self.combo_printer_type)
        form_layout.addRow("Path / IP:", self.input_printer_path)

        layout.addWidget(grp_printer)

        # Test Print
        btn_test = QPushButton("Test Print")
        btn_test.setStyleSheet("background-color: #FFDC00; color: black;")
        btn_test.clicked.connect(self.test_print)
        layout.addWidget(btn_test)

        layout.addStretch()

    def init_appearance_tab(self):
        layout = QFormLayout(self.tab_appearance)
        layout.setContentsMargins(20, 20, 20, 20)

        self.combo_language = QComboBox()
        self.combo_language.addItems(["en", "si", "ta"])

        layout.addRow("Language:", self.combo_language)

    def load_settings(self):
        settings = ConfigService.get_all()

        # General
        self.input_shop_name.setText(settings.get("shop_name", ""))
        self.input_address.setText(settings.get("shop_address", ""))
        self.input_phone.setText(settings.get("shop_phone", ""))
        self.input_vat.setText(settings.get("vat_number", ""))
        self.input_header.setText(settings.get("receipt_header", ""))
        self.input_footer.setText(settings.get("receipt_footer", ""))

        # Hardware
        self.combo_printer_type.setCurrentText(settings.get("printer_type", "USB"))
        self.input_printer_path.setText(settings.get("printer_path", ""))

        # Appearance
        self.combo_language.setCurrentText(settings.get("language", "en"))

    def save_settings(self):
        data = {
            "shop_name": self.input_shop_name.text(),
            "shop_address": self.input_address.text(),
            "shop_phone": self.input_phone.text(),
            "vat_number": self.input_vat.text(),
            "receipt_header": self.input_header.text(),
            "receipt_footer": self.input_footer.text(),
            "printer_type": self.combo_printer_type.currentText(),
            "printer_path": self.input_printer_path.text(),
            "language": self.combo_language.currentText(),
        }

        ConfigService.update_all(data)
        QMessageBox.information(self, "Success", "Settings saved successfully!")

    def test_print(self):
        # TODO: Implement actual test print via PrinterService
        QMessageBox.information(self, "Test Print", "Test print signal sent (Mock).")
