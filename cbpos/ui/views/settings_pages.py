from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
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
    QMessageBox,
    QApplication,
    QProgressDialog,
)
from PyQt6.QtCore import Qt, QTime
from PyQt6.QtPrintSupport import QPrinterInfo
from sqlalchemy.engine import URL
from cbpos.core.services.language_service import LanguageService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.user_service import UserService
from cbpos.ui.dialogs.receipt_preview_dialog import ReceiptPreviewDialog
from cbpos.core.models import Sale, SaleItem, Product
from cbpos.config import Config
import decimal
import socket


class SettingsPage(QWidget):
    """Base class for settings pages with standardized layout patterns."""

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

    def create_form_container(self, top_margin=30, side_margin=30, bottom_margin=30):
        """
        Creates a standardized form layout container for settings pages.

        Returns:
            tuple: (container_layout, form_layout, form_widget)
            - container_layout: QVBoxLayout with top alignment
            - form_layout: QFormLayout with proper spacing and growth policy
            - form_widget: QWidget wrapping the form_layout (ensures full-width)

        Usage:
            container, form, form_widget = self.create_form_container()
            # Add form rows
            form.addRow("Label:", widget)
            # Add form widget to container
            container.addWidget(form_widget)
        """
        # Main container with top alignment
        container = QVBoxLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        container.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Create widget to hold form (forces full width expansion)
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(side_margin, top_margin, side_margin, bottom_margin)
        form_layout.setVerticalSpacing(15)
        form_layout.setHorizontalSpacing(20)

        # Force Left & Top alignment to prevent centering
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # Keep labels right-aligned for professional look
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        return container, form_layout, form_widget

    def create_group_container(self, top_margin=30, side_margin=30, bottom_margin=30):
        """
        Creates a standardized group-based layout container for settings pages.

        Returns:
            QVBoxLayout: Main layout with proper spacing and top alignment

        Usage:
            main_layout = self.create_group_container()
            # Add groups
            grp = QGroupBox("Section Title")
            form = QFormLayout(grp)
            main_layout.addWidget(grp)
        """
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(side_margin, top_margin, side_margin, bottom_margin)
        main_layout.setSpacing(20)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        return main_layout

    def configure_form_layout(self, form_layout):
        """
        Applies standard configuration to a QFormLayout.
        Use this for forms inside QGroupBox widgets.
        """
        form_layout.setVerticalSpacing(15)
        form_layout.setHorizontalSpacing(20)

        # Force Left & Top alignment to prevent centering
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # Keep labels right-aligned for professional look
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)


class GeneralPage(SettingsPage):
    def init_ui(self):
        container, layout, form_widget = self.create_form_container()

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

        # Add form widget to container
        container.addWidget(form_widget)

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
        container, layout, form_widget = self.create_form_container()

        self.combo_search_mode = QComboBox()
        self.combo_search_mode.addItems(["ALL", "BARCODE", "NAME"])
        layout.addRow("Default Search Mode:", self.combo_search_mode)

        self.chk_quick_pay = QCheckBox()
        layout.addRow("Enable Quick Pay (F12):", self.chk_quick_pay)

        self.chk_void_reason = QCheckBox()
        layout.addRow("Require Reason for Void:", self.chk_void_reason)

        container.addWidget(form_widget)

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
        main_layout = self.create_group_container()

        # Warning
        lbl_warn = QLabel("Note: Changing these values affects ALL future sales immediately.")
        lbl_warn.setStyleSheet("color: #FF4136; font-style: italic;")
        main_layout.addWidget(lbl_warn)

        # Create a widget to hold the form (forces full width)
        form_widget = QWidget()
        layout = QFormLayout(form_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.configure_form_layout(layout)

        self.spin_vat = QSpinBox()
        self.spin_vat.setRange(0, 100)
        self.spin_vat.setSuffix("%")
        layout.addRow("VAT Rate:", self.spin_vat)

        self.spin_sscl = QDoubleSpinBox()
        self.spin_sscl.setRange(0, 100)
        self.spin_sscl.setDecimals(2)
        self.spin_sscl.setSuffix("%")
        layout.addRow("SSCL Rate:", self.spin_sscl)

        self.spin_sscl_turnover = QDoubleSpinBox()
        self.spin_sscl_turnover.setRange(0, 100)
        self.spin_sscl_turnover.setDecimals(1)
        self.spin_sscl_turnover.setSuffix("%")
        layout.addRow("SSCL Turnover Base:", self.spin_sscl_turnover)

        main_layout.addWidget(form_widget)

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
        container, layout, form_widget = self.create_form_container()

        self.chk_negative_stock = QCheckBox()
        layout.addRow("Allow Negative Stock (Overselling):", self.chk_negative_stock)

        self.chk_auto_barcodes = QCheckBox()
        layout.addRow("Auto-Generate Barcodes for New Items:", self.chk_auto_barcodes)

        container.addWidget(form_widget)

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
        container, layout, form_widget = self.create_form_container()

        self.combo_reset_period = QComboBox()
        self.combo_reset_period.addItems(["YEARLY", "MONTHLY", "NEVER"])
        layout.addRow("Reset Period:", self.combo_reset_period)

        self.input_fmt_sale = QLineEdit()
        self.input_fmt_sale.setPlaceholderText("INV-{Y}-{seq:05d}")
        layout.addRow("Sale Format:", self.input_fmt_sale)

        self.input_fmt_purchase = QLineEdit()
        self.input_fmt_purchase.setPlaceholderText("GRN-{Y}-{seq:05d}")
        layout.addRow("Purchase Format:", self.input_fmt_purchase)

        self.input_fmt_return = QLineEdit()
        self.input_fmt_return.setPlaceholderText("CN-{Y}-{seq:05d}")
        layout.addRow("Return Format:", self.input_fmt_return)

        container.addWidget(form_widget)

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
        main_layout = self.create_group_container()

        # Printers
        grp_printer = QGroupBox("Printers")
        form_printer = QFormLayout(grp_printer)
        self.configure_form_layout(form_printer)

        available_printers = QPrinterInfo.availablePrinterNames() or ["No printers found"]

        self.combo_receipt_printer = QComboBox()
        self.combo_receipt_printer.addItems(available_printers)
        form_printer.addRow("Receipt Printer:", self.combo_receipt_printer)

        self.combo_a4_printer = QComboBox()
        self.combo_a4_printer.addItems(available_printers)
        form_printer.addRow("A4 Printer:", self.combo_a4_printer)

        self.chk_auto_print = QCheckBox()
        form_printer.addRow("Auto-Print Receipt:", self.chk_auto_print)

        self.spin_copies = QSpinBox()
        self.spin_copies.setRange(1, 5)
        form_printer.addRow("Copies:", self.spin_copies)

        main_layout.addWidget(grp_printer)

        # Scale
        grp_scale = QGroupBox("Weighing Scale")
        form_scale = QFormLayout(grp_scale)
        self.configure_form_layout(form_scale)

        self.input_scale_prefix = QLineEdit()
        self.input_scale_prefix.setMaxLength(2)
        form_scale.addRow("Barcode Prefix (2 digits):", self.input_scale_prefix)

        self.spin_decimal_places = QSpinBox()
        self.spin_decimal_places.setRange(0, 4)
        form_scale.addRow("Decimal Places:", self.spin_decimal_places)

        main_layout.addWidget(grp_scale)

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
        main_layout = self.create_group_container()

        form = QFormLayout()
        self.configure_form_layout(form)

        self.chk_show_receipt_dialog = QCheckBox()
        form.addRow("Show Receipt Options Dialog after Sale:", self.chk_show_receipt_dialog)

        main_layout.addLayout(form)

        # Banking Details
        grp_bank = QGroupBox("Banking Details (For Invoices)")
        form_bank = QFormLayout(grp_bank)
        self.configure_form_layout(form_bank)

        self.input_bank_name = QLineEdit()
        self.input_account_no = QLineEdit()
        self.input_branch = QLineEdit()

        form_bank.addRow("Bank Name:", self.input_bank_name)
        form_bank.addRow("Account Number:", self.input_account_no)
        form_bank.addRow("Branch:", self.input_branch)

        main_layout.addWidget(grp_bank)

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
        main_layout = self.create_group_container()

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
        main_layout.addWidget(grp_logo)

        # Content
        grp_content = QGroupBox("Content")
        form_content = QFormLayout(grp_content)
        self.configure_form_layout(form_content)

        self.txt_header = QTextEdit()
        self.txt_header.setFixedHeight(80)
        form_content.addRow("Header Text:", self.txt_header)

        self.txt_footer = QTextEdit()
        self.txt_footer.setFixedHeight(80)
        form_content.addRow("Footer Text:", self.txt_footer)

        self.chk_show_barcode = QCheckBox()
        self.chk_merge_items = QCheckBox()
        self.chk_show_tax = QCheckBox()

        form_content.addRow("Show Barcode:", self.chk_show_barcode)
        form_content.addRow("Merge Duplicate Items:", self.chk_merge_items)
        form_content.addRow("Show Tax Breakdown:", self.chk_show_tax)

        main_layout.addWidget(grp_content)

        # Preview Button
        self.btn_preview = QPushButton("Preview Receipt")
        self.btn_preview.setStyleSheet("background-color: #007ACC; color: white;")
        self.btn_preview.clicked.connect(self.preview_receipt)
        main_layout.addWidget(self.btn_preview)

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
        container, form_layout, form_widget = self.create_form_container()

        # 1. Auto-Report Scheduler
        self.chk_auto_report = QCheckBox()
        form_layout.addRow("Enable Daily Auto-Report:", self.chk_auto_report)

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

        container.addWidget(form_widget)

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
        main_layout = self.create_group_container()

        form = QFormLayout()
        self.configure_form_layout(form)

        self.input_name = QLineEdit()
        form.addRow("Display Name:", self.input_name)

        self.input_current_pin = QLineEdit()
        self.input_current_pin.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Current PIN:", self.input_current_pin)

        self.input_new_pin = QLineEdit()
        self.input_new_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_new_pin.setPlaceholderText("Leave empty to keep current")
        form.addRow("New PIN:", self.input_new_pin)

        main_layout.addLayout(form)

        # Update Button
        self.btn_update = QPushButton("Update Profile")
        self.btn_update.setStyleSheet("background-color: #007ACC; color: white; padding: 10px;")
        self.btn_update.clicked.connect(self.update_profile)
        main_layout.addWidget(self.btn_update)

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
            QMessageBox.warning(self, "Error", "Current PIN is required.")
            return

        # Verify Current PIN
        verified_user = AuthService.verify_pin(current_pin)
        if not verified_user or verified_user.id != user.id:
            QMessageBox.critical(self, "Error", "Invalid Current PIN.")
            return

        # Update
        success = UserService.update_user_profile(user.id, display_name, new_pin if new_pin else None)

        if success:
            QMessageBox.information(self, "Success", "Profile updated successfully.")
            self.input_current_pin.clear()
            self.input_new_pin.clear()
        else:
            QMessageBox.critical(self, "Error", "Failed to update profile.")


class NetworkPage(SettingsPage):
    """Network database configuration for multi-terminal setup - Connectivity Dashboard."""

    def __init__(self):
        self.connection_tested = False  # Track if connection test passed
        super().__init__()

    def init_ui(self):
        # Main container with card-based layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(25)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # === CARD 1: Hero Status Card ===
        self.status_card = QFrame()
        self.status_card.setObjectName("StatusCard")
        self.status_card.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout(self.status_card)
        status_layout.setContentsMargins(20, 20, 20, 20)
        status_layout.setSpacing(15)

        # Icon/Mode indicator
        self.lbl_mode_icon = QLabel("💻")  # Will change to 🖥️ for Network
        self.lbl_mode_icon.setObjectName("StatusIcon")

        # Status text
        status_text_layout = QVBoxLayout()
        self.lbl_status_title = QLabel("Single Computer Mode")
        self.lbl_status_title.setObjectName("StatusTitle")
        self.lbl_status_subtitle = QLabel("Standalone • Local Database")
        self.lbl_status_subtitle.setObjectName("StatusSubtitle")
        status_text_layout.addWidget(self.lbl_status_title)
        status_text_layout.addWidget(self.lbl_status_subtitle)

        # Mode selector (right side)
        mode_selector_layout = QVBoxLayout()
        mode_label = QLabel("Database Mode:")
        mode_label.setObjectName("StatusModeLabel")
        self.cmb_db_mode = QComboBox()
        self.cmb_db_mode.addItems(["Standalone", "Network"])
        self.cmb_db_mode.setObjectName("StatusModeSelector")
        self.cmb_db_mode.currentTextChanged.connect(self._on_mode_changed)
        mode_selector_layout.addWidget(mode_label)
        mode_selector_layout.addWidget(self.cmb_db_mode)

        status_layout.addWidget(self.lbl_mode_icon)
        status_layout.addLayout(status_text_layout, 1)
        status_layout.addLayout(mode_selector_layout)

        main_layout.addWidget(self.status_card)

        # === CARD 2: Server Configuration Card ===
        self.config_card = QFrame()
        self.config_card.setObjectName("NetworkCard")
        self.config_card.setFrameShape(QFrame.Shape.StyledPanel)
        config_layout = QVBoxLayout(self.config_card)
        config_layout.setContentsMargins(25, 25, 25, 25)
        config_layout.setSpacing(18)

        # Card title
        config_title = QLabel("📡 Server Configuration")
        config_title.setObjectName("CardTitle")
        config_layout.addWidget(config_title)

        # Helper: Show this computer's IP (cross-platform UDP socket trick)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # Connect to a public DNS server (Google's) to determine the routing IP
                # This doesn't actually send a packet
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "127.0.0.1"  # Safe fallback

        self.lbl_local_ip = QLabel(f"💡 This Computer's IP: {local_ip}")
        self.lbl_local_ip.setObjectName("IPHelper")
        config_layout.addWidget(self.lbl_local_ip)

        # Compact grid layout for inputs (2 columns: label + input, stacked vertically)
        grid_layout = QGridLayout()
        grid_layout.setVerticalSpacing(12)
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setColumnStretch(0, 0)  # Label column: fixed width
        grid_layout.setColumnStretch(1, 1)  # Input column: stretches

        # Row 0: Host IP
        lbl_host = QLabel("Host IP:")
        lbl_host.setObjectName("FormLabel")
        self.input_host = QLineEdit()
        self.input_host.setObjectName("InputNetwork")
        self.input_host.setPlaceholderText("e.g., 192.168.1.100")
        grid_layout.addWidget(lbl_host, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        grid_layout.addWidget(self.input_host, 0, 1)

        # Row 1: Port
        lbl_port = QLabel("Port:")
        lbl_port.setObjectName("FormLabel")
        self.input_port = QSpinBox()
        self.input_port.setObjectName("InputNetwork")
        self.input_port.setRange(1, 65535)
        self.input_port.setValue(5432)
        grid_layout.addWidget(lbl_port, 1, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        grid_layout.addWidget(self.input_port, 1, 1)

        # Row 2: Database Name
        lbl_dbname = QLabel("Database Name:")
        lbl_dbname.setObjectName("FormLabel")
        self.input_dbname = QLineEdit()
        self.input_dbname.setObjectName("InputNetwork")
        self.input_dbname.setPlaceholderText("cbpos")
        grid_layout.addWidget(lbl_dbname, 2, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        grid_layout.addWidget(self.input_dbname, 2, 1)

        # Row 3: Username
        lbl_user = QLabel("Username:")
        lbl_user.setObjectName("FormLabel")
        self.input_user = QLineEdit()
        self.input_user.setObjectName("InputNetwork")
        self.input_user.setPlaceholderText("postgres")
        grid_layout.addWidget(lbl_user, 3, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        grid_layout.addWidget(self.input_user, 3, 1)

        # Row 4: Password
        lbl_password = QLabel("Password:")
        lbl_password.setObjectName("FormLabel")
        self.input_password = QLineEdit()
        self.input_password.setObjectName("InputNetwork")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setPlaceholderText("••••••••")
        grid_layout.addWidget(lbl_password, 4, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        grid_layout.addWidget(self.input_password, 4, 1)

        config_layout.addLayout(grid_layout)

        # Test Connection Button (full width)
        test_btn_layout = QHBoxLayout()
        self.btn_test = QPushButton("🔌 Test Connection")
        self.btn_test.setObjectName("BtnTestNetwork")
        self.btn_test.clicked.connect(self._test_connection)
        self.lbl_test_status = QLabel("")
        self.lbl_test_status.setObjectName("TestStatus")
        test_btn_layout.addWidget(self.btn_test)
        test_btn_layout.addWidget(self.lbl_test_status, 1)
        config_layout.addLayout(test_btn_layout)

        main_layout.addWidget(self.config_card)

        # === CARD 3: Data Migration Card (The Magic Section) ===
        self.migration_card = QFrame()
        self.migration_card.setObjectName("MigrationCard")
        self.migration_card.setFrameShape(QFrame.Shape.StyledPanel)
        migration_layout = QVBoxLayout(self.migration_card)
        migration_layout.setContentsMargins(25, 25, 25, 25)
        migration_layout.setSpacing(18)

        migration_title = QLabel("🚀 First-Time Server Setup")
        migration_title.setObjectName("CardTitle")
        migration_layout.addWidget(migration_title)

        migration_info = QLabel(
            "Setting up the Main Server? Upload your current data to get started.\n\n"
            "This will transfer all products, customers, and sales history to the network database.\n"
            "⚠ The target database must be empty."
        )
        migration_info.setWordWrap(True)
        migration_info.setObjectName("MigrationInfo")
        migration_layout.addWidget(migration_info)

        self.btn_migrate = QPushButton("📤 Upload Local Data to Server")
        self.btn_migrate.setObjectName("BtnMigrate")
        self.btn_migrate.setEnabled(False)  # Disabled until connection test passes
        self.btn_migrate.clicked.connect(self._migrate_data)
        migration_layout.addWidget(self.btn_migrate)

        main_layout.addWidget(self.migration_card)

        # Warning footer
        self.lbl_warning = QLabel("⚠ Changing database mode requires application restart.")
        self.lbl_warning.setObjectName("NetworkWarning")
        self.lbl_warning.setWordWrap(True)
        main_layout.addWidget(self.lbl_warning)

        # Initialize visibility
        self._on_mode_changed("Standalone")

    def load(self, settings: dict):
        """Load network settings into UI."""
        db_mode = settings.get("db_mode", "standalone")
        self.cmb_db_mode.setCurrentText("Standalone" if db_mode == "standalone" else "Network")

        self.input_host.setText(settings.get("network_db_host", "localhost"))
        self.input_port.setValue(settings.get("network_db_port", 5432))
        self.input_dbname.setText(settings.get("network_db_name", "cbpos"))
        self.input_user.setText(settings.get("network_db_user", "postgres"))
        self.input_password.setText(settings.get("network_db_password", ""))

        # Update visibility based on loaded mode
        self._on_mode_changed(self.cmb_db_mode.currentText())

    def save(self) -> dict:
        """Return network settings to save."""
        db_mode = "standalone" if self.cmb_db_mode.currentText() == "Standalone" else "network"

        return {
            "db_mode": db_mode,
            "network_db_host": self.input_host.text().strip(),
            "network_db_port": self.input_port.value(),
            "network_db_name": self.input_dbname.text().strip(),
            "network_db_user": self.input_user.text().strip(),
            "network_db_password": self.input_password.text(),
        }

    def _on_mode_changed(self, mode: str):
        """Update UI based on selected mode - show/hide cards and update status."""
        is_network = mode == "Network"

        # Update Hero Status Card
        if is_network:
            self.lbl_mode_icon.setText("🌐")
            self.lbl_status_title.setText("Network Mode")
            self.lbl_status_subtitle.setText("Multi-Terminal • Shared Database")
        else:
            self.lbl_mode_icon.setText("💻")
            self.lbl_status_title.setText("Single Computer Mode")
            self.lbl_status_subtitle.setText("Standalone • Local Database")

        # Show/hide configuration and migration cards
        self.config_card.setVisible(is_network)
        self.migration_card.setVisible(is_network)

        # Reset connection test status
        self.connection_tested = False
        self.btn_migrate.setEnabled(False)
        self.lbl_test_status.setText("")

    def _get_network_config(self):
        """Extracts and cleans network configuration from UI."""
        return {
            "host": self.input_host.text().strip(),
            "port": self.input_port.value(),
            "dbname": self.input_dbname.text().strip(),
            "user": self.input_user.text().strip(),
            "password": self.input_password.text(),
        }

    def _test_connection(self):
        """Test database connection with current credentials and update status."""
        from cbpos.core.database import Database

        # Get network config from UI
        cfg = self._get_network_config()

        # Validate inputs
        if not all([cfg["host"], cfg["dbname"], cfg["user"]]):
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please fill in all required fields (Host, Database Name, Username).",
            )
            return

        # Show testing state
        self.lbl_test_status.setText("⏳ Testing...")
        self.btn_test.setEnabled(False)

        # Process events to show the status
        QApplication.processEvents()

        # Test connection
        success, message = Database.test_connection(
            mode="network",
            host=cfg["host"],
            port=cfg["port"],
            dbname=cfg["dbname"],
            user=cfg["user"],
            password=cfg["password"],
        )

        # Update status
        self.btn_test.setEnabled(True)

        if success:
            self.connection_tested = True
            self.lbl_test_status.setText("✅ Connected")
            self.btn_migrate.setEnabled(True)  # Enable migration button
            QMessageBox.information(self, "Connection Test", f"✓ {message}\n\nYou can now upload your data.")
        else:
            self.connection_tested = False
            self.lbl_test_status.setText("❌ Failed")
            self.btn_migrate.setEnabled(False)
            QMessageBox.critical(self, "Connection Test", f"✗ {message}")

    def _migrate_data(self):
        """Migrate data from local SQLite to PostgreSQL server."""
        from cbpos.core.services.migration_service import MigrationService

        # Get network config from UI
        cfg = self._get_network_config()

        # Validate inputs
        if not all([cfg["host"], cfg["dbname"], cfg["user"]]):
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please fill in all required connection fields before migrating data.",
            )
            return

        # Confirm with user
        confirm = QMessageBox.question(
            self,
            "Confirm Data Migration",
            f"This will upload ALL your local data to:\n\n"
            f"  Host: {cfg['host']}:{cfg['port']}\n"
            f"  Database: {cfg['dbname']}\n\n"
            f"The target database must be empty. This operation may take several minutes.\n\n"
            f"Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Build database URLs
        sqlite_url = Config.DB_URI

        # Use SQLAlchemy URL.create to safely handle special characters in password
        url_obj = URL.create(
            drivername="postgresql+psycopg2",
            username=cfg["user"],
            password=cfg["password"],
            host=cfg["host"],
            port=cfg["port"],
            database=cfg["dbname"],
        )
        postgres_url = url_obj.render_as_string(hide_password=False)

        # Show progress dialog
        progress = QProgressDialog("Migrating data to server...\nPlease wait.", None, 0, 0, self)
        progress.setWindowTitle("Data Migration")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()

        # Process events to ensure dialog appears
        QApplication.processEvents()

        try:
            # Perform migration
            success, message = MigrationService.migrate_sqlite_to_postgres(sqlite_url, postgres_url)

            progress.close()

            if success:
                QMessageBox.information(
                    self,
                    "Migration Successful",
                    f"{message}\n\n"
                    f"Next steps:\n"
                    f"1. Save these network settings\n"
                    f"2. Restart the application\n"
                    f"3. All terminals can now connect to the server",
                )
            else:
                QMessageBox.critical(self, "Migration Failed", f"Migration error:\n\n{message}")

        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Migration Error", f"Unexpected error during migration:\n\n{str(e)}")
