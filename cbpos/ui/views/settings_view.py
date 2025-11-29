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
    QCheckBox,
    QSpinBox,
    QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtPrintSupport import QPrinterInfo
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
        self.tab_documents = QWidget()

        self.tabs.addTab(self.tab_general, "General")
        self.tabs.addTab(self.tab_hardware, "Hardware")
        self.tabs.addTab(self.tab_documents, "Documents")
        self.tabs.addTab(self.tab_appearance, "Appearance")

        self.init_general_tab()
        self.init_hardware_tab()
        self.init_documents_tab()
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
        layout.setSpacing(15)

        # === PRINTER CONFIGURATION ===
        grp_printer = QGroupBox("Printer Configuration")
        form_printer = QFormLayout(grp_printer)

        # Get available system printers
        available_printers = QPrinterInfo.availablePrinterNames()
        if not available_printers:
            available_printers = ["No printers found"]

        # Receipt Printer
        self.combo_receipt_printer = QComboBox()
        self.combo_receipt_printer.addItems(available_printers)
        form_printer.addRow("Receipt Printer (Thermal):", self.combo_receipt_printer)

        # A4 Printer
        self.combo_a4_printer = QComboBox()
        self.combo_a4_printer.addItems(available_printers)
        form_printer.addRow("A4 Printer (Invoice):", self.combo_a4_printer)

        # Auto-Print Checkbox
        self.chk_auto_print = QCheckBox("Print receipt automatically after sale")
        self.chk_auto_print.setChecked(True)
        form_printer.addRow("Auto-Print:", self.chk_auto_print)

        # Receipt Copies
        self.spin_copies = QSpinBox()
        self.spin_copies.setRange(1, 5)
        self.spin_copies.setValue(1)
        form_printer.addRow("Receipt Copies:", self.spin_copies)

        layout.addWidget(grp_printer)

        # === SCALE CONFIGURATION ===
        grp_scale = QGroupBox("Scale Barcode Configuration (Grocery)")
        form_scale = QFormLayout(grp_scale)

        # Barcode Prefix
        self.input_scale_prefix = QLineEdit()
        self.input_scale_prefix.setPlaceholderText("e.g., 20")
        self.input_scale_prefix.setMaxLength(2)
        form_scale.addRow("Barcode Prefix (2 digits):", self.input_scale_prefix)

        # Decimal Places
        self.spin_decimal_places = QSpinBox()
        self.spin_decimal_places.setRange(0, 5)
        self.spin_decimal_places.setValue(3)
        form_scale.addRow("Decimal Places (Weight):", self.spin_decimal_places)

        layout.addWidget(grp_scale)

        # === BANKING DETAILS ===
        grp_banking = QGroupBox("Banking Details (For A4 Invoices)")
        form_banking = QFormLayout(grp_banking)

        # Bank Name
        self.input_bank_name = QLineEdit()
        self.input_bank_name.setPlaceholderText("e.g., Commercial Bank of Ceylon")
        form_banking.addRow("Bank Name:", self.input_bank_name)

        # Account Number
        self.input_account_number = QLineEdit()
        self.input_account_number.setPlaceholderText("e.g., 1234567890")
        form_banking.addRow("Account Number:", self.input_account_number)

        # Branch
        self.input_bank_branch = QLineEdit()
        self.input_bank_branch.setPlaceholderText("e.g., Colombo Fort")
        form_banking.addRow("Branch:", self.input_bank_branch)

        layout.addWidget(grp_banking)

        layout.addWidget(grp_banking)

        layout.addStretch()

    def init_documents_tab(self):
        layout = QFormLayout(self.tab_documents)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Explanation
        lbl_info = QLabel(
            "Configure document number formats. Use {Y}, {M}, {D} for date parts and {seq:05d} for sequence."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("color: #AAAAAA; font-style: italic;")
        layout.addRow(lbl_info)

        # Reset Period
        self.combo_reset_period = QComboBox()
        self.combo_reset_period.addItems(["YEARLY", "MONTHLY", "NEVER"])
        layout.addRow("Sequence Reset Period:", self.combo_reset_period)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addRow(line)

        # Formats
        self.input_fmt_sale = QLineEdit()
        self.input_fmt_sale.setPlaceholderText("INV-{Y}-{seq:05d}")
        layout.addRow("Sale Invoice Format:", self.input_fmt_sale)

        self.input_fmt_purchase = QLineEdit()
        self.input_fmt_purchase.setPlaceholderText("GRN-{Y}-{seq:05d}")
        layout.addRow("Purchase (GRN) Format:", self.input_fmt_purchase)

        self.input_fmt_return = QLineEdit()
        self.input_fmt_return.setPlaceholderText("CN-{Y}-{seq:05d}")
        layout.addRow("Return (CN) Format:", self.input_fmt_return)

        # Preview
        self.lbl_preview = QLabel("Preview: INV-2023-00001")
        self.lbl_preview.setStyleSheet("font-weight: bold; color: #39FF14;")
        layout.addRow("Example Preview:", self.lbl_preview)

        # Connect changes to preview
        self.input_fmt_sale.textChanged.connect(self.update_preview)

    def update_preview(self, text):
        from datetime import datetime

        now = datetime.now()
        try:
            # Simple mock render
            rendered = (
                text.replace("{Y}", now.strftime("%Y"))
                .replace("{M}", now.strftime("%m"))
                .replace("{D}", now.strftime("%d"))
                .replace("{seq:05d}", "00001")
            )
            self.lbl_preview.setText(f"Preview: {rendered}")
        except Exception:
            self.lbl_preview.setText("Preview: Invalid Format")

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

        # Hardware - Printers
        receipt_printer = settings.get("receipt_printer_name", "")
        if receipt_printer:
            index = self.combo_receipt_printer.findText(receipt_printer)
            if index >= 0:
                self.combo_receipt_printer.setCurrentIndex(index)

        a4_printer = settings.get("a4_printer_name", "")
        if a4_printer:
            index = self.combo_a4_printer.findText(a4_printer)
            if index >= 0:
                self.combo_a4_printer.setCurrentIndex(index)

        self.chk_auto_print.setChecked(settings.get("auto_print_receipt", True))
        self.spin_copies.setValue(settings.get("receipt_copies", 1))

        # Hardware - Scale
        self.input_scale_prefix.setText(settings.get("scale_barcode_prefix", "20"))
        self.spin_decimal_places.setValue(settings.get("scale_decimal_places", 3))

        # Hardware - Banking
        self.input_bank_name.setText(
            settings.get("company_bank_name", "Commercial Bank of Ceylon")
        )
        self.input_account_number.setText(
            settings.get("company_account_number", "1234567890")
        )
        self.input_bank_branch.setText(
            settings.get("company_bank_branch", "Colombo Fort")
        )

        # Documents
        self.combo_reset_period.setCurrentText(
            settings.get("doc_reset_period", "YEARLY")
        )
        self.input_fmt_sale.setText(
            settings.get("doc_format_sale", "INV-{Y}-{seq:05d}")
        )
        self.input_fmt_purchase.setText(
            settings.get("doc_format_purchase", "GRN-{Y}-{seq:05d}")
        )
        self.input_fmt_return.setText(
            settings.get("doc_format_return", "CN-{Y}-{seq:05d}")
        )

        # Appearance
        self.combo_language.setCurrentText(settings.get("language", "en"))

    def save_settings(self):
        # Validate Scale Prefix
        scale_prefix = self.input_scale_prefix.text().strip()
        if len(scale_prefix) != 2 or not scale_prefix.isdigit():
            QMessageBox.warning(
                self,
                "Validation Error",
                "Scale Barcode Prefix must be exactly 2 digits (e.g., '20').",
            )
            return

        data = {
            # General
            "shop_name": self.input_shop_name.text(),
            "shop_address": self.input_address.text(),
            "shop_phone": self.input_phone.text(),
            "vat_number": self.input_vat.text(),
            "receipt_header": self.input_header.text(),
            "receipt_footer": self.input_footer.text(),
            # Hardware - Printers
            "receipt_printer_name": self.combo_receipt_printer.currentText(),
            "a4_printer_name": self.combo_a4_printer.currentText(),
            "auto_print_receipt": self.chk_auto_print.isChecked(),
            "receipt_copies": self.spin_copies.value(),
            # Hardware - Scale
            "scale_barcode_prefix": scale_prefix,
            "scale_decimal_places": self.spin_decimal_places.value(),
            # Hardware - Banking
            "company_bank_name": self.input_bank_name.text(),
            "company_account_number": self.input_account_number.text(),
            "company_bank_branch": self.input_bank_branch.text(),
            # Documents
            "doc_reset_period": self.combo_reset_period.currentText(),
            "doc_format_sale": self.input_fmt_sale.text(),
            "doc_format_purchase": self.input_fmt_purchase.text(),
            "doc_format_return": self.input_fmt_return.text(),
            # Appearance
            "language": self.combo_language.currentText(),
        }

        ConfigService.update_all(data)
        QMessageBox.information(self, "Success", "Settings saved successfully!")
