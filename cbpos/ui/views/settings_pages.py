from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFormLayout,
    QGroupBox,
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QTextEdit,
    QFileDialog,
    QTimeEdit,
    QFrame,
)
from PyQt6.QtCore import Qt, QTime
from PyQt6.QtPrintSupport import QPrinterInfo
from cbpos.core.services.language_service import LanguageService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.user_service import UserService
from cbpos.ui.dialogs.receipt_preview_dialog import ReceiptPreviewDialog
from cbpos.core.models import Sale, SaleItem, Product
import decimal


class SettingsPage(QWidget):
    """Base class for settings pages."""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize the UI. Override in subclasses."""
        pass

    def load(self, settings: dict):
        """Load settings into UI. Override in subclasses."""
        pass

    def save(self) -> dict:
        """Return a dictionary of settings to save. Override in subclasses."""
        return {}


class GeneralPage(SettingsPage):
    def init_ui(self):
        layout = QFormLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("General Settings")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB; margin-bottom: 20px;")
        layout.addRow(lbl_header)

        self.input_shop_name = QLineEdit()
        self.input_address = QLineEdit()
        self.input_phone = QLineEdit()
        self.input_vat = QLineEdit()
        self.input_tax_id = QLineEdit()
        self.input_currency = QLineEdit()

        layout.addRow("Shop Name:", self.input_shop_name)
        layout.addRow("Address:", self.input_address)
        layout.addRow("Phone:", self.input_phone)
        layout.addRow("VAT Number:", self.input_vat)
        layout.addRow("Company Tax ID:", self.input_tax_id)
        layout.addRow("Currency Symbol:", self.input_currency)

        # Appearance
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(8, 24)
        self.spin_font_size.setSuffix(" px")
        layout.addRow("Font Size:", self.spin_font_size)

        lbl_restart = QLabel("(Requires Restart)")
        lbl_restart.setStyleSheet("color: #FF4136; font-size: 10px;")
        layout.addRow("", lbl_restart)

        # Theme
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["Ceylon Night (Dark)", "Ceylon Day (Light)"])
        layout.addRow("Theme:", self.combo_theme)

        # Language
        self.combo_language = QComboBox()
        languages = LanguageService.get_available_languages()
        for code, name in languages.items():
            self.combo_language.addItem(f"{name} ({code})", code)
        layout.addRow("Language:", self.combo_language)

    def load(self, settings: dict):
        self.input_shop_name.setText(settings.get("shop_name", ""))
        self.input_address.setText(settings.get("shop_address", ""))
        self.input_phone.setText(settings.get("shop_phone", ""))
        self.input_vat.setText(settings.get("vat_number", ""))
        self.input_tax_id.setText(settings.get("company_tax_id", ""))
        self.input_currency.setText(settings.get("currency_symbol", "Rs."))
        self.spin_font_size.setValue(settings.get("font_size", 12))

        current_theme = settings.get("theme", "Dark")
        index = 0 if current_theme == "Dark" else 1
        self.combo_theme.setCurrentIndex(index)

        current_lang = settings.get("language", "en")
        index = self.combo_language.findData(current_lang)
        if index >= 0:
            self.combo_language.setCurrentIndex(index)

    def save(self) -> dict:
        theme_selection = "Dark" if self.combo_theme.currentIndex() == 0 else "Light"
        lang_code = self.combo_language.currentData()
        return {
            "shop_name": self.input_shop_name.text(),
            "shop_address": self.input_address.text(),
            "shop_phone": self.input_phone.text(),
            "vat_number": self.input_vat.text(),
            "company_tax_id": self.input_tax_id.text(),
            "currency_symbol": self.input_currency.text(),
            "font_size": self.spin_font_size.value(),
            "theme": theme_selection,
            "language": lang_code,
        }


class SalesPage(SettingsPage):
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("Sales Configuration")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        form = QFormLayout()

        self.combo_search_mode = QComboBox()
        self.combo_search_mode.addItems(["ALL", "BARCODE", "NAME"])
        form.addRow("Default Search Mode:", self.combo_search_mode)

        self.chk_quick_pay = QCheckBox("Enable Quick Pay (F12)")
        form.addRow("", self.chk_quick_pay)

        self.chk_void_reason = QCheckBox("Require Reason for Void")
        form.addRow("", self.chk_void_reason)

        layout.addLayout(form)
        layout.addStretch()

    def load(self, settings: dict):
        self.combo_search_mode.setCurrentText(settings.get("default_search_mode", "ALL"))
        self.chk_quick_pay.setChecked(settings.get("quick_pay_enabled", True))
        self.chk_void_reason.setChecked(settings.get("require_void_reason", True))

    def save(self) -> dict:
        return {
            "default_search_mode": self.combo_search_mode.currentText(),
            "quick_pay_enabled": self.chk_quick_pay.isChecked(),
            "require_void_reason": self.chk_void_reason.isChecked(),
        }


class TaxPage(SettingsPage):
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("Tax Configuration")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        # Warning
        lbl_warn = QLabel("Note: Changing these values affects ALL future sales immediately.")
        lbl_warn.setStyleSheet("color: #FF4136; font-style: italic;")
        layout.addWidget(lbl_warn)

        form = QFormLayout()

        self.spin_vat = QSpinBox()
        self.spin_vat.setRange(0, 100)
        self.spin_vat.setSuffix("%")
        form.addRow("VAT Rate:", self.spin_vat)

        self.spin_sscl = QDoubleSpinBox()
        self.spin_sscl.setRange(0, 100)
        self.spin_sscl.setDecimals(2)
        self.spin_sscl.setSuffix("%")
        form.addRow("SSCL Rate:", self.spin_sscl)

        self.spin_sscl_turnover = QDoubleSpinBox()
        self.spin_sscl_turnover.setRange(0, 100)
        self.spin_sscl_turnover.setDecimals(1)
        self.spin_sscl_turnover.setSuffix("%")
        form.addRow("SSCL Turnover Base:", self.spin_sscl_turnover)

        layout.addLayout(form)
        layout.addStretch()

    def load(self, settings: dict):
        self.spin_vat.setValue(int(settings.get("tax_vat_rate", 18)))
        self.spin_sscl.setValue(float(settings.get("tax_sscl_rate", 2.5)))
        self.spin_sscl_turnover.setValue(float(settings.get("tax_sscl_turnover_pct", 50.0)))

    def save(self) -> dict:
        return {
            "tax_vat_rate": self.spin_vat.value(),
            "tax_sscl_rate": self.spin_sscl.value(),
            "tax_sscl_turnover_pct": self.spin_sscl_turnover.value(),
        }


class InventoryPage(SettingsPage):
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("Inventory Control")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        form = QFormLayout()

        self.chk_negative_stock = QCheckBox("Allow Negative Stock (Overselling)")
        form.addRow("", self.chk_negative_stock)

        self.chk_auto_barcodes = QCheckBox("Auto-Generate Barcodes for New Items")
        form.addRow("", self.chk_auto_barcodes)

        layout.addLayout(form)
        layout.addStretch()

    def load(self, settings: dict):
        self.chk_negative_stock.setChecked(settings.get("allow_negative_stock", False))
        self.chk_auto_barcodes.setChecked(settings.get("auto_generate_barcodes", True))

    def save(self) -> dict:
        return {
            "allow_negative_stock": self.chk_negative_stock.isChecked(),
            "auto_generate_barcodes": self.chk_auto_barcodes.isChecked(),
        }


class DocumentPage(SettingsPage):
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("Document Numbering")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        form = QFormLayout()

        self.combo_reset_period = QComboBox()
        self.combo_reset_period.addItems(["YEARLY", "MONTHLY", "NEVER"])
        form.addRow("Reset Period:", self.combo_reset_period)

        self.input_fmt_sale = QLineEdit()
        self.input_fmt_sale.setPlaceholderText("INV-{Y}-{seq:05d}")
        form.addRow("Sale Format:", self.input_fmt_sale)

        self.input_fmt_purchase = QLineEdit()
        self.input_fmt_purchase.setPlaceholderText("GRN-{Y}-{seq:05d}")
        form.addRow("Purchase Format:", self.input_fmt_purchase)

        self.input_fmt_return = QLineEdit()
        self.input_fmt_return.setPlaceholderText("CN-{Y}-{seq:05d}")
        form.addRow("Return Format:", self.input_fmt_return)

        layout.addLayout(form)
        layout.addStretch()

    def load(self, settings: dict):
        self.combo_reset_period.setCurrentText(settings.get("doc_reset_period", "YEARLY"))
        self.input_fmt_sale.setText(settings.get("doc_format_sale", "INV-{Y}-{seq:05d}"))
        self.input_fmt_purchase.setText(settings.get("doc_format_purchase", "GRN-{Y}-{seq:05d}"))
        self.input_fmt_return.setText(settings.get("doc_format_return", "CN-{Y}-{seq:05d}"))

    def save(self) -> dict:
        return {
            "doc_reset_period": self.combo_reset_period.currentText(),
            "doc_format_sale": self.input_fmt_sale.text(),
            "doc_format_purchase": self.input_fmt_purchase.text(),
            "doc_format_return": self.input_fmt_return.text(),
        }


class HardwarePage(SettingsPage):
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("Hardware Configuration")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        # Printers
        grp_printer = QGroupBox("Printers")
        form_printer = QFormLayout(grp_printer)

        available_printers = QPrinterInfo.availablePrinterNames() or ["No printers found"]

        self.combo_receipt_printer = QComboBox()
        self.combo_receipt_printer.addItems(available_printers)
        form_printer.addRow("Receipt Printer:", self.combo_receipt_printer)

        self.combo_a4_printer = QComboBox()
        self.combo_a4_printer.addItems(available_printers)
        form_printer.addRow("A4 Printer:", self.combo_a4_printer)

        self.chk_auto_print = QCheckBox("Auto-Print Receipt")
        form_printer.addRow("", self.chk_auto_print)

        self.spin_copies = QSpinBox()
        self.spin_copies.setRange(1, 5)
        form_printer.addRow("Copies:", self.spin_copies)

        layout.addWidget(grp_printer)

        # Scale
        grp_scale = QGroupBox("Weighing Scale")
        form_scale = QFormLayout(grp_scale)

        self.input_scale_prefix = QLineEdit()
        self.input_scale_prefix.setMaxLength(2)
        form_scale.addRow("Barcode Prefix (2 digits):", self.input_scale_prefix)

        self.spin_decimal_places = QSpinBox()
        self.spin_decimal_places.setRange(0, 4)
        form_scale.addRow("Decimal Places:", self.spin_decimal_places)

        layout.addWidget(grp_scale)
        layout.addStretch()

    def load(self, settings: dict):
        receipt_printer = settings.get("receipt_printer_name", "")
        if receipt_printer:
            idx = self.combo_receipt_printer.findText(receipt_printer)
            if idx >= 0:
                self.combo_receipt_printer.setCurrentIndex(idx)

        a4_printer = settings.get("a4_printer_name", "")
        if a4_printer:
            idx = self.combo_a4_printer.findText(a4_printer)
            if idx >= 0:
                self.combo_a4_printer.setCurrentIndex(idx)

        self.chk_auto_print.setChecked(settings.get("auto_print_receipt", True))
        self.spin_copies.setValue(settings.get("receipt_copies", 1))

        self.input_scale_prefix.setText(settings.get("scale_barcode_prefix", "20"))
        self.spin_decimal_places.setValue(settings.get("scale_decimal_places", 3))

    def save(self) -> dict:
        prefix = self.input_scale_prefix.text()
        if len(prefix) != 2 or not prefix.isdigit():
            raise ValueError("Scale Barcode Prefix must be exactly 2 digits.")

        return {
            "receipt_printer_name": self.combo_receipt_printer.currentText(),
            "a4_printer_name": self.combo_a4_printer.currentText(),
            "auto_print_receipt": self.chk_auto_print.isChecked(),
            "receipt_copies": self.spin_copies.value(),
            "scale_barcode_prefix": prefix,
            "scale_decimal_places": self.spin_decimal_places.value(),
        }


class PaymentPage(SettingsPage):
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("Payment Options")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        form = QFormLayout()

        self.chk_show_receipt_dialog = QCheckBox("Show Receipt Options Dialog after Sale")
        form.addRow("", self.chk_show_receipt_dialog)

        # Banking Details
        grp_bank = QGroupBox("Banking Details (For Invoices)")
        form_bank = QFormLayout(grp_bank)

        self.input_bank_name = QLineEdit()
        self.input_account_no = QLineEdit()
        self.input_branch = QLineEdit()

        form_bank.addRow("Bank Name:", self.input_bank_name)
        form_bank.addRow("Account Number:", self.input_account_no)
        form_bank.addRow("Branch:", self.input_branch)

        layout.addLayout(form)
        layout.addWidget(grp_bank)
        layout.addStretch()

    def load(self, settings: dict):
        self.chk_show_receipt_dialog.setChecked(settings.get("show_receipt_dialog", True))
        self.input_bank_name.setText(settings.get("company_bank_name", ""))
        self.input_account_no.setText(settings.get("company_account_number", ""))
        self.input_branch.setText(settings.get("company_bank_branch", ""))

    def save(self) -> dict:
        return {
            "show_receipt_dialog": self.chk_show_receipt_dialog.isChecked(),
            "company_bank_name": self.input_bank_name.text(),
            "company_account_number": self.input_account_no.text(),
            "company_bank_branch": self.input_branch.text(),
        }


class ReceiptPage(SettingsPage):
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("Receipt Designer")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        # Logo
        grp_logo = QGroupBox("Logo")
        logo_layout = QHBoxLayout(grp_logo)
        self.input_logo_path = QLineEdit()
        self.input_logo_path.setReadOnly(True)
        self.btn_browse_logo = QPushButton("Browse...")
        self.btn_browse_logo.clicked.connect(self.browse_logo)
        self.btn_clear_logo = QPushButton("Clear")
        self.btn_clear_logo.clicked.connect(lambda: self.input_logo_path.clear())

        logo_layout.addWidget(self.input_logo_path)
        logo_layout.addWidget(self.btn_browse_logo)
        logo_layout.addWidget(self.btn_clear_logo)
        layout.addWidget(grp_logo)

        # Content
        grp_content = QGroupBox("Content")
        form_content = QFormLayout(grp_content)

        self.txt_header = QTextEdit()
        self.txt_header.setFixedHeight(80)
        form_content.addRow("Header Text:", self.txt_header)

        self.txt_footer = QTextEdit()
        self.txt_footer.setFixedHeight(80)
        form_content.addRow("Footer Text:", self.txt_footer)

        self.chk_show_barcode = QCheckBox("Show Barcode")
        self.chk_merge_items = QCheckBox("Merge Duplicate Items")
        self.chk_show_tax = QCheckBox("Show Tax Breakdown")

        form_content.addRow("", self.chk_show_barcode)
        form_content.addRow("", self.chk_merge_items)
        form_content.addRow("", self.chk_show_tax)

        layout.addWidget(grp_content)

        # Preview Button
        self.btn_preview = QPushButton("Preview Receipt")
        self.btn_preview.setStyleSheet("background-color: #007ACC; color: white;")
        self.btn_preview.clicked.connect(self.preview_receipt)
        layout.addWidget(self.btn_preview)

        layout.addStretch()

    def browse_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Logo", "", "Images (*.png *.jpg *.bmp)")
        if path:
            self.input_logo_path.setText(path)

    def load(self, settings: dict):
        self.input_logo_path.setText(settings.get("receipt_logo_path", ""))
        self.txt_header.setText(settings.get("receipt_header", ""))
        self.txt_footer.setText(settings.get("receipt_footer", ""))
        self.chk_show_barcode.setChecked(settings.get("show_barcode", True))
        self.chk_merge_items.setChecked(settings.get("merge_items", True))
        self.chk_show_tax.setChecked(settings.get("show_tax_breakdown", True))

    def save(self) -> dict:
        return {
            "receipt_logo_path": self.input_logo_path.text(),
            "receipt_header": self.txt_header.toPlainText(),
            "receipt_footer": self.txt_footer.toPlainText(),
            "show_barcode": self.chk_show_barcode.isChecked(),
            "merge_items": self.chk_merge_items.isChecked(),
            "show_tax_breakdown": self.chk_show_tax.isChecked(),
        }

    def preview_receipt(self):
        # Create a dummy sale for preview
        dummy_sale = Sale(
            id=12345,
            total_amount=decimal.Decimal("1500.00"),
            tax_vat=decimal.Decimal("228.81"),
            tax_sscl=decimal.Decimal("37.50"),
            net_revenue=decimal.Decimal("1233.69"),
        )
        # Dummy items
        p1 = Product(name_en="Test Product 1")
        p2 = Product(name_en="Test Product 2")
        dummy_sale.items = [
            SaleItem(
                product=p1,
                qty=decimal.Decimal(1),
                unit_price=decimal.Decimal(500),
                subtotal=decimal.Decimal(500),
            ),
            SaleItem(
                product=p2,
                qty=decimal.Decimal(2),
                unit_price=decimal.Decimal(500),
                subtotal=decimal.Decimal(1000),
            ),
        ]

        # Use current UI settings for preview without saving
        current_settings = self.save()
        commands = ReceiptBuilder.build_receipt(dummy_sale, config_override=current_settings)

        dlg = ReceiptPreviewDialog(commands, self)
        dlg.exec()


class AutomationPage(SettingsPage):
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Title
        title = QLabel("Automation Settings")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(title)

        # Form Layout
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(15)

        # 1. Auto-Report Scheduler
        self.chk_auto_report = QCheckBox("Enable Daily Auto-Report")
        self.chk_auto_report.setStyleSheet("font-size: 16px;")
        form_layout.addRow("Scheduler:", self.chk_auto_report)

        self.time_auto_report = QTimeEdit()
        self.time_auto_report.setDisplayFormat("HH:mm")
        form_layout.addRow("Report Time:", self.time_auto_report)

        self.input_admin_email = QLineEdit()
        self.input_admin_email.setPlaceholderText("admin@example.com")
        form_layout.addRow("Admin Email:", self.input_admin_email)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form_layout.addRow(line)

        # 2. Email Settings (SMTP)
        self.input_smtp_host = QLineEdit()
        self.input_smtp_host.setPlaceholderText("smtp.gmail.com")
        form_layout.addRow("SMTP Host:", self.input_smtp_host)

        self.input_smtp_port = QLineEdit()
        self.input_smtp_port.setPlaceholderText("587")
        form_layout.addRow("SMTP Port:", self.input_smtp_port)

        self.input_smtp_user = QLineEdit()
        self.input_smtp_user.setPlaceholderText("email@example.com")
        form_layout.addRow("SMTP User:", self.input_smtp_user)

        self.input_smtp_pass = QLineEdit()
        self.input_smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_smtp_pass.setPlaceholderText("App Password")
        form_layout.addRow("SMTP Password:", self.input_smtp_pass)

        layout.addLayout(form_layout)
        layout.addStretch()

    def load(self, settings: dict):
        self.chk_auto_report.setChecked(settings.get("auto_report_enabled", False))
        self.time_auto_report.setTime(QTime.fromString(settings.get("auto_report_time", "22:00"), "HH:mm"))
        self.input_admin_email.setText(settings.get("admin_email", ""))

        self.input_smtp_host.setText(settings.get("smtp_host", ""))
        self.input_smtp_port.setText(str(settings.get("smtp_port", "587")))
        self.input_smtp_user.setText(settings.get("smtp_user", ""))
        self.input_smtp_pass.setText(settings.get("smtp_pass", ""))

    def save(self) -> dict:
        return {
            "auto_report_enabled": self.chk_auto_report.isChecked(),
            "auto_report_time": self.time_auto_report.time().toString("HH:mm"),
            "admin_email": self.input_admin_email.text(),
            "smtp_host": self.input_smtp_host.text(),
            "smtp_port": self.input_smtp_port.text(),
            "smtp_user": self.input_smtp_user.text(),
            "smtp_pass": self.input_smtp_pass.text(),
        }


class ProfilePage(SettingsPage):
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("My Profile")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        form = QFormLayout()

        self.input_name = QLineEdit()
        form.addRow("Display Name:", self.input_name)

        self.input_current_pin = QLineEdit()
        self.input_current_pin.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Current PIN:", self.input_current_pin)

        self.input_new_pin = QLineEdit()
        self.input_new_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_new_pin.setPlaceholderText("Leave empty to keep current")
        form.addRow("New PIN:", self.input_new_pin)

        layout.addLayout(form)

        # Update Button
        self.btn_update = QPushButton("Update Profile")
        self.btn_update.setStyleSheet("background-color: #007ACC; color: white; padding: 10px;")
        self.btn_update.clicked.connect(self.update_profile)
        layout.addWidget(self.btn_update)

        layout.addStretch()

    def load(self, settings: dict):
        user = AuthService.get_current_user()
        if user:
            self.input_name.setText(user.username)
        self.input_current_pin.clear()
        self.input_new_pin.clear()

    def save(self) -> dict:
        # Profile page handles its own saving via the button
        return {}

    def update_profile(self):
        user = AuthService.get_current_user()
        if not user:
            return

        current_pin = self.input_current_pin.text()
        new_pin = self.input_new_pin.text()
        display_name = self.input_name.text()

        if not current_pin:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Error", "Current PIN is required.")
            return

        # Verify Current PIN
        verified_user = AuthService.verify_pin(current_pin)
        if not verified_user or verified_user.id != user.id:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", "Invalid Current PIN.")
            return

        # Update
        success = UserService.update_user_profile(user.id, display_name, new_pin if new_pin else None)

        from PyQt6.QtWidgets import QMessageBox

        if success:
            QMessageBox.information(self, "Success", "Profile updated successfully.")
            self.input_current_pin.clear()
            self.input_new_pin.clear()
        else:
            QMessageBox.critical(self, "Error", "Failed to update profile.")
