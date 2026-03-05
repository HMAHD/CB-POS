from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFormLayout,
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
    QScrollArea,
    QDialog,
    QTabWidget,
)
from PyQt6.QtCore import Qt, QTime, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtPrintSupport import QPrinterInfo
from sqlalchemy.engine import URL
from cbpos.core.services.language_service import LanguageService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.models import Sale, SaleItem, Product
from cbpos.config import Config
import decimal
import socket

# Gmail SMTP setup guide content — kept separate for maintainability
_GMAIL_GUIDE_STEPS = [
    (
        "1",
        "Enable 2-Step Verification",
        "Go to myaccount.google.com \u2192 Security\n" "Turn on 2-Step Verification for your account.",
    ),
    (
        "2",
        "Create an App Password",
        "In your Google Account, search for 'App Passwords'.\n"
        "Select app: 'Other' \u2192 type 'CB POS' \u2192 Generate.",
    ),
    (
        "3",
        "Copy the password",
        "Google will show a 16-character password.\n" "Copy it \u2014 you won't be able to see it again.",
    ),
    (
        "4",
        "Paste in CB POS",
        "Click 'Use Gmail' to fill Host & Port.\n"
        "Enter your Gmail as SMTP User.\n"
        "Paste the App Password as SMTP Password.",
    ),
]


class SettingsPage(QWidget):
    """Base class for settings pages with standardized tab-based layout."""

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

    def _create_page_layout(self, title_text: str, subtitle_text: str) -> tuple[QVBoxLayout, QTabWidget]:
        """Creates the standard page layout: title + subtitle + tab widget.

        Returns:
            tuple: (main_layout, tab_widget)
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(title_text)
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        subtitle = QLabel(subtitle_text)
        subtitle.setProperty("class", "muted")
        layout.addWidget(subtitle)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        return layout, tabs

    def _build_form_tab(self) -> tuple[QWidget, QFormLayout]:
        """Creates a tab widget with a scrollable form layout inside.

        Returns:
            tuple: (tab_widget, form_layout)
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("SettingsScrollArea")
        tab_layout.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("SettingsScrollInner")
        form = QFormLayout(inner)
        form.setContentsMargins(16, 20, 16, 20)
        form.setVerticalSpacing(15)
        form.setHorizontalSpacing(20)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        scroll.setWidget(inner)

        return tab, form

    def _build_vbox_tab(self) -> tuple[QWidget, QVBoxLayout]:
        """Creates a tab widget with a scrollable vertical layout inside.

        Returns:
            tuple: (tab_widget, vbox_layout)
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("SettingsScrollArea")
        tab_layout.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("SettingsScrollInner")
        vbox = QVBoxLayout(inner)
        vbox.setContentsMargins(16, 20, 16, 20)
        vbox.setSpacing(16)
        vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(inner)

        return tab, vbox

    def configure_form_layout(self, form_layout: QFormLayout) -> None:
        """Applies standard configuration to a QFormLayout."""
        form_layout.setVerticalSpacing(15)
        form_layout.setHorizontalSpacing(20)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

    @staticmethod
    def _make_section_header(title: str) -> QWidget:
        """Create a styled section header with title and horizontal divider.

        Returns a single widget containing: [title] ── [line] that spans the
        full width of the form.  Use with ``form.addRow(header)`` (single-arg
        overload so it spans both columns).
        """
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 10, 0, 2)
        row.setSpacing(10)

        lbl = QLabel(title)
        lbl.setObjectName("SettingsSectionTitle")
        row.addWidget(lbl)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("SettingsSectionLine")
        row.addWidget(line, 1)

        return container


class ShopInfoPage(SettingsPage):
    """Consolidated: General + Payment banking + Automation email settings."""

    def init_ui(self):
        _, self.tabs = self._create_page_layout(
            "Shop Info",
            "Business details, banking, email, and appearance settings.",
        )

        # --- Tab 1: Business ---
        tab_biz, form_biz = self._build_form_tab()

        self.input_shop_name = QLineEdit()
        self.input_address = QLineEdit()
        self.input_phone = QLineEdit()
        self.input_vat = QLineEdit()
        self.input_tax_id = QLineEdit()
        self.input_currency = QLineEdit()

        form_biz.addRow("Shop Name:", self.input_shop_name)
        form_biz.addRow("Address:", self.input_address)
        form_biz.addRow("Phone:", self.input_phone)
        form_biz.addRow("VAT Number:", self.input_vat)
        form_biz.addRow("Company Tax ID:", self.input_tax_id)
        form_biz.addRow("Currency Symbol:", self.input_currency)

        self.tabs.addTab(tab_biz, "Business")

        # --- Tab 2: Banking ---
        tab_bank, form_bank = self._build_form_tab()

        self.input_bank_name = QLineEdit()
        self.input_account_no = QLineEdit()
        self.input_branch = QLineEdit()

        form_bank.addRow("Bank Name:", self.input_bank_name)
        form_bank.addRow("Account Number:", self.input_account_no)
        form_bank.addRow("Branch:", self.input_branch)

        self.tabs.addTab(tab_bank, "Banking")

        # --- Tab 3: Email ---
        tab_email, form_email = self._build_form_tab()

        # Helper buttons row at top
        email_btn_row = QHBoxLayout()
        email_btn_row.addStretch()

        btn_gmail = QPushButton("Use Gmail")
        btn_gmail.setFixedHeight(32)
        btn_gmail.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_gmail.setObjectName("BtnGmailHelper")
        btn_gmail.setProperty("class", "link")
        btn_gmail.setToolTip("Fill Gmail SMTP settings automatically")
        btn_gmail.clicked.connect(self._prefill_gmail)
        email_btn_row.addWidget(btn_gmail)

        btn_help = QPushButton()
        info_icon_path = str(Config.BASE_DIR / "cbpos" / "assets" / "icons" / "info-circle-cyan.svg")
        btn_help.setIcon(QIcon(info_icon_path))
        btn_help.setIconSize(QSize(24, 24))
        btn_help.setFixedSize(28, 28)
        btn_help.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_help.setObjectName("BtnInfoIcon")
        btn_help.setToolTip("How to set up Gmail email (step-by-step guide)")
        btn_help.clicked.connect(self._show_smtp_guide)
        email_btn_row.addWidget(btn_help)

        form_email.addRow(email_btn_row)

        self.chk_auto_report = QCheckBox()
        form_email.addRow("Enable Daily Auto-Report:", self.chk_auto_report)

        self.time_auto_report = QTimeEdit()
        self.time_auto_report.setDisplayFormat("HH:mm")
        form_email.addRow("Report Time:", self.time_auto_report)

        self.input_admin_email = QLineEdit()
        self.input_admin_email.setPlaceholderText("yourname@gmail.com")
        form_email.addRow("Admin Email:", self.input_admin_email)

        self.input_smtp_host = QLineEdit()
        self.input_smtp_host.setPlaceholderText("smtp.gmail.com")
        form_email.addRow("SMTP Host:", self.input_smtp_host)

        self.input_smtp_port = QLineEdit()
        self.input_smtp_port.setPlaceholderText("587")
        form_email.addRow("SMTP Port:", self.input_smtp_port)

        self.input_smtp_user = QLineEdit()
        self.input_smtp_user.setPlaceholderText("yourname@gmail.com")
        form_email.addRow("SMTP User (Email):", self.input_smtp_user)

        self.input_smtp_pass = QLineEdit()
        self.input_smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_smtp_pass.setPlaceholderText("16-character App Password")
        form_email.addRow("SMTP Password:", self.input_smtp_pass)

        self.tabs.addTab(tab_email, "Email")

        # --- Tab 4: Appearance ---
        tab_appear, form_appear = self._build_form_tab()

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(8, 24)
        self.spin_font_size.setSuffix(" px")
        form_appear.addRow("Font Size:", self.spin_font_size)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["Ceylon Night (Dark)", "Ceylon Day (Light)"])
        form_appear.addRow("Theme:", self.combo_theme)

        self.combo_language = QComboBox()
        languages = LanguageService.get_available_languages()
        for code, name in languages.items():
            self.combo_language.addItem(f"{name} ({code})", code)
        form_appear.addRow("Language:", self.combo_language)

        lbl_restart = QLabel("(Font Size and Language changes require restart)")
        lbl_restart.setProperty("class", "warning-hint")
        form_appear.addRow("", lbl_restart)

        self.tabs.addTab(tab_appear, "Appearance")

    def _prefill_gmail(self):
        """Pre-fill SMTP fields with Gmail defaults."""
        self.input_smtp_host.setText("smtp.gmail.com")
        self.input_smtp_port.setText("587")
        if not self.input_smtp_user.text():
            self.input_smtp_user.setFocus()

    def _show_smtp_guide(self):
        """Show a clean step-by-step SMTP setup guide dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Email Setup Guide")
        dlg.setMinimumWidth(480)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("How to set up email with Gmail")
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        for num, heading, detail in _GMAIL_GUIDE_STEPS:
            step_frame = QFrame()
            step_frame.setObjectName("SmtpGuideStep")
            step_layout = QHBoxLayout(step_frame)
            step_layout.setContentsMargins(12, 10, 12, 10)

            num_label = QLabel(num)
            num_label.setFixedSize(32, 32)
            num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num_label.setObjectName("SmtpGuideStepNum")
            step_layout.addWidget(num_label)

            text_layout = QVBoxLayout()
            text_layout.setSpacing(2)
            h = QLabel(f"<b>{heading}</b>")
            h.setProperty("class", "transparent")
            d = QLabel(detail)
            d.setWordWrap(True)
            d.setProperty("class", "muted")
            text_layout.addWidget(h)
            text_layout.addWidget(d)
            step_layout.addLayout(text_layout, 1)

            layout.addWidget(step_frame)

        note = QLabel("<b>Important:</b> Your regular Gmail password will NOT work. " "You must use an App Password.")
        note.setWordWrap(True)
        note.setProperty("class", "muted")
        layout.addWidget(note)

        btn_close = QPushButton("Got it")
        btn_close.setProperty("class", "primary")
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

        dlg.exec()

    def load(self, settings: dict):
        self.input_shop_name.setText(settings.get("shop_name", ""))
        self.input_address.setText(settings.get("shop_address", ""))
        self.input_phone.setText(settings.get("shop_phone", ""))
        self.input_vat.setText(settings.get("vat_number", ""))
        self.input_tax_id.setText(settings.get("company_tax_id", ""))
        self.input_currency.setText(settings.get("currency_symbol", "Rs."))

        self.input_bank_name.setText(settings.get("company_bank_name", ""))
        self.input_account_no.setText(settings.get("company_account_number", ""))
        self.input_branch.setText(settings.get("company_bank_branch", ""))

        self.chk_auto_report.setChecked(settings.get("auto_report_enabled", False))
        self.time_auto_report.setTime(QTime.fromString(settings.get("auto_report_time", "22:00"), "HH:mm"))
        self.input_admin_email.setText(settings.get("admin_email", ""))
        self.input_smtp_host.setText(settings.get("smtp_host", ""))
        self.input_smtp_port.setText(str(settings.get("smtp_port", "587")))
        self.input_smtp_user.setText(settings.get("smtp_user", ""))
        self.input_smtp_pass.setText(settings.get("smtp_pass", ""))

        self.spin_font_size.setValue(settings.get("font_size", 12))
        current_theme = settings.get("theme", "Dark")
        self.combo_theme.setCurrentIndex(0 if current_theme == "Dark" else 1)
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
            "company_bank_name": self.input_bank_name.text(),
            "company_account_number": self.input_account_no.text(),
            "company_bank_branch": self.input_branch.text(),
            "auto_report_enabled": self.chk_auto_report.isChecked(),
            "auto_report_time": self.time_auto_report.time().toString("HH:mm"),
            "admin_email": self.input_admin_email.text(),
            "smtp_host": self.input_smtp_host.text(),
            "smtp_port": self.input_smtp_port.text(),
            "smtp_user": self.input_smtp_user.text(),
            "smtp_pass": self.input_smtp_pass.text(),
            "font_size": self.spin_font_size.value(),
            "theme": theme_selection,
            "language": lang_code,
        }


class SalesTaxPage(SettingsPage):
    """Sales search mode + Tax configuration."""

    def init_ui(self):
        _, self.tabs = self._create_page_layout(
            "Sales & Tax",
            "Search defaults and Sri Lankan tax configuration.",
        )

        # --- Tab 1: Sales ---
        tab_sales, form_sales = self._build_form_tab()

        self.combo_search_mode = QComboBox()
        self.combo_search_mode.addItems(["ALL", "BARCODE", "NAME"])
        form_sales.addRow("Default Search Mode:", self.combo_search_mode)

        self.spin_max_discount = QDoubleSpinBox()
        self.spin_max_discount.setRange(0, 100)
        self.spin_max_discount.setDecimals(1)
        self.spin_max_discount.setSuffix("%")
        self.spin_max_discount.setFixedWidth(200)
        self.spin_max_discount.setToolTip("Maximum discount % a cashier can apply. 0 = no limit.")
        form_sales.addRow("Max Discount:", self.spin_max_discount)

        self.spin_loyalty_ratio = QSpinBox()
        self.spin_loyalty_ratio.setRange(1, 10000)
        self.spin_loyalty_ratio.setPrefix("Rs. ")
        self.spin_loyalty_ratio.setToolTip("Spend this amount to earn 1 loyalty point")
        form_sales.addRow("Loyalty Points Ratio:", self.spin_loyalty_ratio)

        self.spin_default_credit = QSpinBox()
        self.spin_default_credit.setRange(0, 1000000)
        self.spin_default_credit.setPrefix("Rs. ")
        self.spin_default_credit.setToolTip("Default credit limit for new customers. 0 = no credit.")
        form_sales.addRow("Default Credit Limit:", self.spin_default_credit)

        self.tabs.addTab(tab_sales, "Sales")

        # --- Tab 2: Tax ---
        tab_tax, form_tax = self._build_form_tab()

        lbl_warn = QLabel("Note: Changing these values affects ALL future sales immediately.")
        lbl_warn.setProperty("class", "warning-hint")
        form_tax.addRow(lbl_warn)

        self.spin_vat = QSpinBox()
        self.spin_vat.setRange(0, 100)
        self.spin_vat.setSuffix("%")
        self.spin_vat.setFixedWidth(200)
        form_tax.addRow("VAT Rate:", self.spin_vat)

        self.spin_sscl = QDoubleSpinBox()
        self.spin_sscl.setRange(0, 100)
        self.spin_sscl.setDecimals(2)
        self.spin_sscl.setSuffix("%")
        self.spin_sscl.setFixedWidth(200)
        form_tax.addRow("SSCL Rate:", self.spin_sscl)

        self.spin_sscl_turnover = QDoubleSpinBox()
        self.spin_sscl_turnover.setRange(0, 100)
        self.spin_sscl_turnover.setDecimals(1)
        self.spin_sscl_turnover.setSuffix("%")
        self.spin_sscl_turnover.setFixedWidth(200)
        form_tax.addRow("SSCL Turnover Base:", self.spin_sscl_turnover)

        self.tabs.addTab(tab_tax, "Tax")

    def load(self, settings: dict):
        self.combo_search_mode.setCurrentText(settings.get("default_search_mode", "ALL"))
        self.spin_max_discount.setValue(float(settings.get("max_discount_percent", 15.0)))
        self.spin_loyalty_ratio.setValue(int(settings.get("loyalty_points_ratio", 100)))
        self.spin_default_credit.setValue(int(settings.get("default_credit_limit", 0)))
        self.spin_vat.setValue(int(settings.get("tax_vat_rate", 18)))
        self.spin_sscl.setValue(float(settings.get("tax_sscl_rate", 2.5)))
        self.spin_sscl_turnover.setValue(float(settings.get("tax_sscl_turnover_pct", 50.0)))

    def save(self) -> dict:
        return {
            "default_search_mode": self.combo_search_mode.currentText(),
            "max_discount_percent": self.spin_max_discount.value(),
            "loyalty_points_ratio": self.spin_loyalty_ratio.value(),
            "default_credit_limit": self.spin_default_credit.value(),
            "tax_vat_rate": self.spin_vat.value(),
            "tax_sscl_rate": self.spin_sscl.value(),
            "tax_sscl_turnover_pct": self.spin_sscl_turnover.value(),
        }


class DocumentPage(SettingsPage):
    """Documents + Terminal ID."""

    def init_ui(self):
        _, self.tabs = self._create_page_layout(
            "Documents",
            "Terminal ID, numbering formats, and reset period.",
        )

        tab_docs, form_docs = self._build_form_tab()

        self.input_terminal_id = QLineEdit()
        self.input_terminal_id.setPlaceholderText("TERM-01")
        form_docs.addRow("Terminal ID:", self.input_terminal_id)

        self.combo_reset_period = QComboBox()
        self.combo_reset_period.addItems(["YEARLY", "MONTHLY", "NEVER"])
        form_docs.addRow("Reset Period:", self.combo_reset_period)

        self.input_fmt_sale = QLineEdit()
        self.input_fmt_sale.setPlaceholderText("INV-{Y}-{seq:05d}")
        form_docs.addRow("Sale Format:", self.input_fmt_sale)

        self.input_fmt_purchase = QLineEdit()
        self.input_fmt_purchase.setPlaceholderText("GRN-{Y}-{seq:05d}")
        form_docs.addRow("Purchase Format:", self.input_fmt_purchase)

        self.input_fmt_return = QLineEdit()
        self.input_fmt_return.setPlaceholderText("CN-{Y}-{seq:05d}")
        form_docs.addRow("Return Format:", self.input_fmt_return)

        self.tabs.addTab(tab_docs, "Numbering")

    def load(self, settings: dict):
        self.input_terminal_id.setText(settings.get("terminal_id", "TERM-01"))
        self.combo_reset_period.setCurrentText(settings.get("doc_reset_period", "YEARLY"))
        self.input_fmt_sale.setText(settings.get("doc_format_sale", "INV-{Y}-{seq:05d}"))
        self.input_fmt_purchase.setText(settings.get("doc_format_purchase", "GRN-{Y}-{seq:05d}"))
        self.input_fmt_return.setText(settings.get("doc_format_return", "CN-{Y}-{seq:05d}"))

    def save(self) -> dict:
        return {
            "terminal_id": self.input_terminal_id.text().strip() or "TERM-01",
            "doc_reset_period": self.combo_reset_period.currentText(),
            "doc_format_sale": self.input_fmt_sale.text(),
            "doc_format_purchase": self.input_fmt_purchase.text(),
            "doc_format_return": self.input_fmt_return.text(),
        }


class HardwarePage(SettingsPage):
    """Hardware + Paper Width."""

    def init_ui(self):
        _, self.tabs = self._create_page_layout(
            "Hardware",
            "Printer selection, paper size, and weighing scale settings.",
        )

        # --- Tab 1: Printers ---
        tab_printer, vbox_printer = self._build_vbox_tab()

        available_printers = QPrinterInfo.availablePrinterNames() or ["No printers found"]

        # Section: Printer Selection
        vbox_printer.addWidget(self._make_section_header("Printer Selection"))

        sel_form = QFormLayout()
        self.configure_form_layout(sel_form)
        sel_form.setContentsMargins(0, 0, 0, 0)
        sel_form.setVerticalSpacing(10)

        self.combo_receipt_printer = QComboBox()
        self.combo_receipt_printer.addItems(available_printers)
        sel_form.addRow("Receipt Printer:", self.combo_receipt_printer)

        self.combo_a4_printer = QComboBox()
        self.combo_a4_printer.addItems(available_printers)
        sel_form.addRow("A4 Printer:", self.combo_a4_printer)

        self.combo_paper_width = QComboBox()
        self.combo_paper_width.addItems(["80mm", "58mm"])
        sel_form.addRow("Paper Width:", self.combo_paper_width)
        vbox_printer.addLayout(sel_form)

        # Section: Print Behavior
        vbox_printer.addWidget(self._make_section_header("Print Behavior"))

        beh_form = QFormLayout()
        self.configure_form_layout(beh_form)
        beh_form.setContentsMargins(0, 0, 0, 0)
        beh_form.setVerticalSpacing(10)

        self.chk_auto_print = QCheckBox("Automatically print after completing a sale")
        beh_form.addRow("Auto-Print Receipt:", self.chk_auto_print)

        self.spin_copies = QSpinBox()
        self.spin_copies.setRange(1, 5)
        beh_form.addRow("Copies:", self.spin_copies)
        vbox_printer.addLayout(beh_form)

        # Test Buttons
        vbox_printer.addWidget(self._make_section_header("Test Hardware"))
        test_row = QHBoxLayout()
        self.btn_test_print = QPushButton("Test Print")
        self.btn_test_print.setProperty("class", "accent")
        self.btn_test_print.clicked.connect(self._test_print)
        test_row.addWidget(self.btn_test_print)

        self.btn_open_drawer = QPushButton("Open Drawer")
        self.btn_open_drawer.clicked.connect(self._test_drawer)
        test_row.addWidget(self.btn_open_drawer)
        test_row.addStretch()
        vbox_printer.addLayout(test_row)

        self.tabs.addTab(tab_printer, "Printers")

        # --- Tab: Paper Cut & Drawer ---
        tab_cut, vbox_cut = self._build_vbox_tab()

        # Section: Paper Cut
        vbox_cut.addWidget(self._make_section_header("Paper Cut"))

        cut_form = QFormLayout()
        self.configure_form_layout(cut_form)
        cut_form.setContentsMargins(0, 0, 0, 0)
        cut_form.setVerticalSpacing(10)

        self.chk_auto_cut = QCheckBox("Disable for tear-bar printers")
        cut_form.addRow("Auto-Cut Paper:", self.chk_auto_cut)

        self.combo_cut_type = QComboBox()
        self.combo_cut_type.addItems(["partial", "full"])
        self.combo_cut_type.setToolTip("Partial is safer for cheap cutters")
        cut_form.addRow("Cut Type:", self.combo_cut_type)

        self.spin_feed_lines = QSpinBox()
        self.spin_feed_lines.setRange(1, 8)
        self.spin_feed_lines.setToolTip("Lines of blank paper before cut")
        cut_form.addRow("Feed Lines Before Cut:", self.spin_feed_lines)
        vbox_cut.addLayout(cut_form)

        # Section: Cash Drawer
        vbox_cut.addWidget(self._make_section_header("Cash Drawer"))

        drawer_form = QFormLayout()
        self.configure_form_layout(drawer_form)
        drawer_form.setContentsMargins(0, 0, 0, 0)
        drawer_form.setVerticalSpacing(10)

        self.chk_drawer_cash_only = QCheckBox("Only open drawer for cash payments")
        drawer_form.addRow("Drawer on Cash Only:", self.chk_drawer_cash_only)
        vbox_cut.addLayout(drawer_form)

        self.tabs.addTab(tab_cut, "Cut & Drawer")

        # --- Tab: Scale ---
        tab_scale, vbox_scale = self._build_vbox_tab()

        vbox_scale.addWidget(self._make_section_header("Weighing Scale Barcodes"))

        scale_form = QFormLayout()
        self.configure_form_layout(scale_form)
        scale_form.setContentsMargins(0, 0, 0, 0)
        scale_form.setVerticalSpacing(10)

        self.input_scale_prefix = QLineEdit()
        self.input_scale_prefix.setMaxLength(2)
        scale_form.addRow("Barcode Prefix (2 digits):", self.input_scale_prefix)

        self.spin_decimal_places = QSpinBox()
        self.spin_decimal_places.setRange(0, 4)
        scale_form.addRow("Decimal Places:", self.spin_decimal_places)
        vbox_scale.addLayout(scale_form)

        self.tabs.addTab(tab_scale, "Weighing Scale")

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

        paper_width = settings.get("paper_width", "80mm")
        idx = self.combo_paper_width.findText(paper_width)
        if idx >= 0:
            self.combo_paper_width.setCurrentIndex(idx)

        self.chk_auto_print.setChecked(settings.get("auto_print_receipt", True))
        self.spin_copies.setValue(settings.get("receipt_copies", 1))
        self.input_scale_prefix.setText(settings.get("scale_barcode_prefix", "20"))
        self.spin_decimal_places.setValue(settings.get("scale_decimal_places", 3))

        # Cut & Drawer
        self.chk_auto_cut.setChecked(settings.get("auto_cut_paper", True))
        cut_type = settings.get("cut_type", "partial")
        idx = self.combo_cut_type.findText(cut_type)
        if idx >= 0:
            self.combo_cut_type.setCurrentIndex(idx)
        self.spin_feed_lines.setValue(settings.get("feed_lines_before_cut", 3))
        self.chk_drawer_cash_only.setChecked(settings.get("drawer_on_cash_only", True))

    def save(self) -> dict:
        prefix = self.input_scale_prefix.text()
        if len(prefix) != 2 or not prefix.isdigit():
            raise ValueError("Scale Barcode Prefix must be exactly 2 digits.")

        return {
            "receipt_printer_name": self.combo_receipt_printer.currentText(),
            "a4_printer_name": self.combo_a4_printer.currentText(),
            "paper_width": self.combo_paper_width.currentText(),
            "auto_print_receipt": self.chk_auto_print.isChecked(),
            "receipt_copies": self.spin_copies.value(),
            "scale_barcode_prefix": prefix,
            "scale_decimal_places": self.spin_decimal_places.value(),
            "auto_cut_paper": self.chk_auto_cut.isChecked(),
            "cut_type": self.combo_cut_type.currentText(),
            "feed_lines_before_cut": self.spin_feed_lines.value(),
            "drawer_on_cash_only": self.chk_drawer_cash_only.isChecked(),
        }

    def _test_print(self) -> None:
        """Send a test print to the configured printer."""
        from cbpos.core.services.hardware_test_service import HardwareTestService

        success, message = HardwareTestService.test_receipt_printer()
        if success:
            QMessageBox.information(self, "Test Print", message)
        else:
            QMessageBox.warning(self, "Test Print", message)

    def _test_drawer(self) -> None:
        """Send a kick signal to the cash drawer."""
        from cbpos.core.services.hardware_test_service import HardwareTestService

        success, message = HardwareTestService.test_cash_drawer()
        if success:
            QMessageBox.information(self, "Cash Drawer", message)
        else:
            QMessageBox.warning(self, "Cash Drawer", message)


class ReceiptPage(SettingsPage):
    """Receipt settings with live preview split-pane layout.

    Left panel: settings tabs (Content + Display).
    Right panel: live receipt preview that auto-updates on every change.
    """

    def init_ui(self):
        from PyQt6.QtCore import QTimer
        from cbpos.ui.widgets.receipt_preview_widget import ReceiptPreviewWidget

        # --- Custom layout: split-pane instead of standard vertical ---
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(8)

        title = QLabel("Receipt")
        title.setProperty("class", "dialog-title")
        root.addWidget(title)

        subtitle = QLabel("Customize receipt content and display — preview updates live.")
        subtitle.setProperty("class", "muted")
        root.addWidget(subtitle)

        # Horizontal split: settings | preview
        split = QHBoxLayout()
        split.setSpacing(16)

        # --- Left: Tab widget with settings ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.tabs = QTabWidget()
        left_layout.addWidget(self.tabs)
        split.addWidget(left_panel, 55)

        # --- Right: Live preview ---
        self._preview = ReceiptPreviewWidget()
        split.addWidget(self._preview, 45)

        root.addLayout(split, 1)

        # Debounce timer for live preview refresh
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(300)
        self._refresh_timer.timeout.connect(self._refresh_preview)

        # ===================== Tab 1: Content =====================
        tab_content, vbox_content = self._build_vbox_tab()

        # Section: Logo
        vbox_content.addWidget(self._make_section_header("Shop Logo"))

        logo_form = QFormLayout()
        self.configure_form_layout(logo_form)
        logo_form.setContentsMargins(0, 0, 0, 0)
        logo_form.setVerticalSpacing(10)
        logo_row = QHBoxLayout()
        self.input_logo_path = QLineEdit()
        self.input_logo_path.setReadOnly(True)
        self.input_logo_path.setPlaceholderText("No logo selected")
        self.btn_browse_logo = QPushButton("Browse...")
        self.btn_browse_logo.clicked.connect(self.browse_logo)
        self.btn_clear_logo = QPushButton("Clear")
        self.btn_clear_logo.clicked.connect(self._clear_logo)
        logo_row.addWidget(self.input_logo_path, 1)
        logo_row.addWidget(self.btn_browse_logo)
        logo_row.addWidget(self.btn_clear_logo)
        logo_form.addRow("Logo:", logo_row)
        vbox_content.addLayout(logo_form)

        # Section: Header & Footer
        vbox_content.addWidget(self._make_section_header("Header & Footer"))

        hf_form = QFormLayout()
        self.configure_form_layout(hf_form)
        hf_form.setContentsMargins(0, 0, 0, 0)
        hf_form.setVerticalSpacing(10)

        self.txt_header = QTextEdit()
        self.txt_header.setFixedHeight(64)
        self.txt_header.setPlaceholderText("Printed at the top of every receipt")
        hf_form.addRow("Header Text:", self.txt_header)

        self.txt_footer = QTextEdit()
        self.txt_footer.setFixedHeight(64)
        self.txt_footer.setPlaceholderText("Printed at the bottom of every receipt")
        hf_form.addRow("Footer Text:", self.txt_footer)

        vbox_content.addLayout(hf_form)
        self.tabs.addTab(tab_content, "Content")

        # ===================== Tab 2: Display =====================
        tab_display, vbox_display = self._build_vbox_tab()

        # Section: Receipt Elements
        vbox_display.addWidget(self._make_section_header("Receipt Elements"))

        elem_form = QFormLayout()
        self.configure_form_layout(elem_form)
        elem_form.setContentsMargins(0, 0, 0, 0)
        elem_form.setVerticalSpacing(10)

        self.chk_show_barcode = QCheckBox("Print barcode of the sale reference")
        self.chk_merge_items = QCheckBox("Combine identical line items into one row")
        self.chk_show_tax = QCheckBox("Show VAT and SSCL breakdown on receipt")

        elem_form.addRow("Show Barcode:", self.chk_show_barcode)
        elem_form.addRow("Merge Items:", self.chk_merge_items)
        elem_form.addRow("Tax Breakdown:", self.chk_show_tax)
        vbox_display.addLayout(elem_form)

        # Section: Staff & Terminal
        vbox_display.addWidget(self._make_section_header("Staff & Terminal"))

        staff_form = QFormLayout()
        self.configure_form_layout(staff_form)
        staff_form.setContentsMargins(0, 0, 0, 0)
        staff_form.setVerticalSpacing(10)

        self.chk_show_cashier = QCheckBox("Print cashier username on receipt")
        self.chk_show_terminal = QCheckBox("Print terminal ID on receipt")

        staff_form.addRow("Cashier Name:", self.chk_show_cashier)
        staff_form.addRow("Terminal ID:", self.chk_show_terminal)
        vbox_display.addLayout(staff_form)

        # Section: QR Code
        vbox_display.addWidget(self._make_section_header("QR Code"))

        qr_form = QFormLayout()
        self.configure_form_layout(qr_form)
        qr_form.setContentsMargins(0, 0, 0, 0)
        qr_form.setVerticalSpacing(10)

        self.chk_show_qr = QCheckBox("Print QR code (e.g. shop website or WhatsApp)")
        qr_form.addRow("Show QR Code:", self.chk_show_qr)

        self.input_qr_content = QLineEdit()
        self.input_qr_content.setPlaceholderText("https://wa.me/94767378901")
        self.input_qr_content.setToolTip("URL or text encoded in QR code")
        qr_form.addRow("QR Content:", self.input_qr_content)
        vbox_display.addLayout(qr_form)

        self.tabs.addTab(tab_display, "Display")

        # --- Connect all inputs to live preview refresh ---
        self._connect_live_signals()

    # ------------------------------------------------------------------
    # Signal wiring for live preview
    # ------------------------------------------------------------------

    def _connect_live_signals(self) -> None:
        """Connect every settings widget's change signal to the debounced refresh."""
        trigger = self._schedule_refresh
        # Text inputs
        self.input_logo_path.textChanged.connect(trigger)
        self.txt_header.textChanged.connect(trigger)
        self.txt_footer.textChanged.connect(trigger)
        self.input_qr_content.textChanged.connect(trigger)
        # Checkboxes
        self.chk_show_barcode.stateChanged.connect(trigger)
        self.chk_merge_items.stateChanged.connect(trigger)
        self.chk_show_tax.stateChanged.connect(trigger)
        self.chk_show_cashier.stateChanged.connect(trigger)
        self.chk_show_terminal.stateChanged.connect(trigger)
        self.chk_show_qr.stateChanged.connect(trigger)

    def _schedule_refresh(self) -> None:
        """Restart the debounce timer — preview refreshes after 300 ms of inactivity."""
        self._refresh_timer.start()

    def _refresh_preview(self) -> None:
        """Build receipt commands from current settings and update the preview."""
        commands = ReceiptBuilder.build_receipt(
            self._make_dummy_sale(),
            config_override=self.save(),
        )
        self._preview.set_commands(commands)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Logo", "", "Images (*.png *.jpg *.bmp)")
        if path:
            self.input_logo_path.setText(path)

    def _clear_logo(self) -> None:
        self.input_logo_path.clear()

    def load(self, settings: dict) -> None:
        # Block signals during bulk load to avoid N refreshes
        self._refresh_timer.stop()
        self.input_logo_path.setText(settings.get("receipt_logo_path", ""))
        self.txt_header.setText(settings.get("receipt_header", ""))
        self.txt_footer.setText(settings.get("receipt_footer", ""))
        self.chk_show_barcode.setChecked(settings.get("show_barcode", True))
        self.chk_merge_items.setChecked(settings.get("merge_items", False))
        self.chk_show_tax.setChecked(settings.get("show_tax_breakdown", True))
        self.chk_show_cashier.setChecked(settings.get("show_cashier_on_receipt", True))
        self.chk_show_terminal.setChecked(settings.get("show_terminal_on_receipt", False))
        self.chk_show_qr.setChecked(settings.get("show_qr_on_receipt", False))
        self.input_qr_content.setText(settings.get("receipt_qr_content", ""))
        # Single refresh after all fields loaded
        self._refresh_preview()

    def save(self) -> dict:
        return {
            "receipt_logo_path": self.input_logo_path.text(),
            "receipt_header": self.txt_header.toPlainText(),
            "receipt_footer": self.txt_footer.toPlainText(),
            "show_barcode": self.chk_show_barcode.isChecked(),
            "merge_items": self.chk_merge_items.isChecked(),
            "show_tax_breakdown": self.chk_show_tax.isChecked(),
            "show_cashier_on_receipt": self.chk_show_cashier.isChecked(),
            "show_terminal_on_receipt": self.chk_show_terminal.isChecked(),
            "show_qr_on_receipt": self.chk_show_qr.isChecked(),
            "receipt_qr_content": self.input_qr_content.text(),
        }

    @staticmethod
    def _make_dummy_sale() -> Sale:
        """Create a realistic sample sale for the preview."""
        from datetime import datetime

        sale = Sale(
            id=12345,
            document_number="INV-2026-00042",
            date=datetime.now(),
            total_amount=decimal.Decimal("1500.00"),
            tax_vat=decimal.Decimal("228.81"),
            tax_sscl=decimal.Decimal("37.50"),
            net_revenue=decimal.Decimal("1233.69"),
        )
        p1 = Product(name_en="Paracetamol 500mg")
        p2 = Product(name_en="Vitamin C Tablets")
        p3 = Product(name_en="Hand Sanitizer 250ml")
        sale.items = [
            SaleItem(
                product=p1,
                qty=decimal.Decimal("2"),
                unit_price=decimal.Decimal("150.00"),
                subtotal=decimal.Decimal("300.00"),
            ),
            SaleItem(
                product=p2,
                qty=decimal.Decimal("1"),
                unit_price=decimal.Decimal("450.00"),
                subtotal=decimal.Decimal("450.00"),
            ),
            SaleItem(
                product=p3,
                qty=decimal.Decimal("3"),
                unit_price=decimal.Decimal("250.00"),
                subtotal=decimal.Decimal("750.00"),
            ),
        ]
        return sale


class SystemPage(SettingsPage):
    """System settings: session security, feature toggles, and behavior."""

    def init_ui(self):
        _, self.tabs = self._create_page_layout(
            "System",
            "Session security, POS behavior, inventory, and backup settings.",
        )

        # --- Tab 1: Security ---
        tab_sec, form_sec = self._build_form_tab()

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(0, 60)
        self.spin_timeout.setSuffix(" min")
        self.spin_timeout.setSpecialValueText("Disabled (no auto-lock)")
        self.spin_timeout.setToolTip("Auto-logout after inactivity. 0 = disabled.")
        form_sec.addRow("Inactivity Timeout:", self.spin_timeout)

        self.chk_void_reason = QCheckBox()
        self.chk_void_reason.setToolTip("Require a reason when voiding a transaction")
        form_sec.addRow("Require Void Reason:", self.chk_void_reason)

        self.spin_max_login = QSpinBox()
        self.spin_max_login.setRange(1, 20)
        self.spin_max_login.setToolTip("Failed login attempts before account lockout")
        form_sec.addRow("Max Login Attempts:", self.spin_max_login)

        self.spin_lockout = QSpinBox()
        self.spin_lockout.setRange(30, 3600)
        self.spin_lockout.setSuffix(" sec")
        self.spin_lockout.setToolTip("How long an account is locked after too many failed attempts")
        form_sec.addRow("Lockout Duration:", self.spin_lockout)

        self.tabs.addTab(tab_sec, "Security")

        # --- Tab 2: POS Behavior ---
        tab_pos, form_pos = self._build_form_tab()

        self.chk_quick_pay = QCheckBox()
        self.chk_quick_pay.setToolTip("Allow instant cash payment with F12")
        form_pos.addRow("Enable Quick Pay (F12):", self.chk_quick_pay)

        self.chk_show_receipt_dialog = QCheckBox()
        self.chk_show_receipt_dialog.setToolTip("Show print/email options after completing a sale")
        form_pos.addRow("Show Receipt Options after Sale:", self.chk_show_receipt_dialog)

        self.chk_auto_barcode_select = QCheckBox()
        self.chk_auto_barcode_select.setToolTip("Automatically select product when barcode matches exactly")
        form_pos.addRow("Auto-Select on Barcode Match:", self.chk_auto_barcode_select)

        self.chk_enable_sounds = QCheckBox()
        self.chk_enable_sounds.setToolTip("Play audio feedback on scan, payment, and errors")
        form_pos.addRow("Enable Sound Effects:", self.chk_enable_sounds)

        self.tabs.addTab(tab_pos, "POS Behavior")

        # --- Tab 3: Inventory ---
        tab_inv, form_inv = self._build_form_tab()

        self.chk_negative_stock = QCheckBox()
        self.chk_negative_stock.setToolTip("Allow selling items even when stock is zero or negative")
        form_inv.addRow("Allow Negative Stock:", self.chk_negative_stock)

        self.chk_auto_barcodes = QCheckBox()
        self.chk_auto_barcodes.setToolTip("Auto-generate barcodes for new products without one")
        form_inv.addRow("Auto-Generate Barcodes:", self.chk_auto_barcodes)

        self.chk_loyalty = QCheckBox()
        form_inv.addRow("Enable Loyalty Points:", self.chk_loyalty)

        self.chk_touch_mode = QCheckBox()
        self.chk_touch_mode.setToolTip("Enable touch-friendly UI elements")
        form_inv.addRow("Enable Touch Mode:", self.chk_touch_mode)

        self.tabs.addTab(tab_inv, "Features")

        # --- Tab 4: Backup ---
        tab_backup, form_backup = self._build_form_tab()

        self.chk_auto_backup = QCheckBox()
        self.chk_auto_backup.setToolTip("Automatically create a backup when closing the application")
        form_backup.addRow("Auto-Backup on Close:", self.chk_auto_backup)

        self.spin_retention = QSpinBox()
        self.spin_retention.setRange(1, 50)
        self.spin_retention.setSuffix(" backups")
        self.spin_retention.setToolTip("Number of most recent backups to keep during cleanup")
        form_backup.addRow("Keep Recent Backups:", self.spin_retention)

        backup_dir_layout = QHBoxLayout()
        self.input_backup_dir = QLineEdit()
        self.input_backup_dir.setPlaceholderText("Default: ~/Documents/CB-POS-Backups")
        self.input_backup_dir.setReadOnly(True)
        backup_dir_layout.addWidget(self.input_backup_dir, 1)

        self.btn_browse_backup = QPushButton("Browse")
        self.btn_browse_backup.clicked.connect(self._browse_backup_dir)
        backup_dir_layout.addWidget(self.btn_browse_backup)

        form_backup.addRow("Backup Folder:", backup_dir_layout)

        self.tabs.addTab(tab_backup, "Backup")

    def _browse_backup_dir(self) -> None:
        current = self.input_backup_dir.text() or ""
        chosen = QFileDialog.getExistingDirectory(self, "Choose Backup Folder", current)
        if chosen:
            self.input_backup_dir.setText(chosen)

    def load(self, settings: dict):
        self.spin_timeout.setValue(int(settings.get("session_timeout_minutes", 0)))
        self.chk_void_reason.setChecked(settings.get("require_void_reason", True))
        self.spin_max_login.setValue(int(settings.get("max_login_attempts", 5)))
        self.spin_lockout.setValue(int(settings.get("lockout_duration_seconds", 300)))
        self.chk_quick_pay.setChecked(settings.get("quick_pay_enabled", True))
        self.chk_show_receipt_dialog.setChecked(settings.get("show_receipt_dialog", True))
        self.chk_auto_barcode_select.setChecked(settings.get("auto_select_barcode_match", True))
        self.chk_enable_sounds.setChecked(settings.get("enable_sounds", True))
        self.chk_negative_stock.setChecked(settings.get("allow_negative_stock", False))
        self.chk_auto_barcodes.setChecked(settings.get("auto_generate_barcodes", True))
        self.chk_loyalty.setChecked(settings.get("enable_loyalty", True))
        self.chk_touch_mode.setChecked(settings.get("enable_touch_mode", True))
        self.chk_auto_backup.setChecked(settings.get("auto_backup_on_close", True))
        self.spin_retention.setValue(int(settings.get("backup_retention_count", 5)))
        self.input_backup_dir.setText(settings.get("backup_dir", ""))

    def save(self) -> dict:
        return {
            "session_timeout_minutes": self.spin_timeout.value(),
            "require_void_reason": self.chk_void_reason.isChecked(),
            "max_login_attempts": self.spin_max_login.value(),
            "lockout_duration_seconds": self.spin_lockout.value(),
            "quick_pay_enabled": self.chk_quick_pay.isChecked(),
            "show_receipt_dialog": self.chk_show_receipt_dialog.isChecked(),
            "auto_select_barcode_match": self.chk_auto_barcode_select.isChecked(),
            "enable_sounds": self.chk_enable_sounds.isChecked(),
            "allow_negative_stock": self.chk_negative_stock.isChecked(),
            "auto_generate_barcodes": self.chk_auto_barcodes.isChecked(),
            "enable_loyalty": self.chk_loyalty.isChecked(),
            "enable_touch_mode": self.chk_touch_mode.isChecked(),
            "auto_backup_on_close": self.chk_auto_backup.isChecked(),
            "backup_retention_count": self.spin_retention.value(),
            "backup_dir": self.input_backup_dir.text(),
        }


class NetworkPage(SettingsPage):
    """Network database configuration for multi-terminal setup."""

    def __init__(self):
        self.connection_tested = False
        super().__init__()

    def init_ui(self):
        _, self.tabs = self._create_page_layout(
            "Network",
            "Database mode and multi-terminal server configuration.",
        )

        # --- Tab 1: Mode ---
        tab_mode, mode_layout = self._build_vbox_tab()

        # Status Card
        self.status_card = QFrame()
        self.status_card.setObjectName("StatusCard")
        self.status_card.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout(self.status_card)
        status_layout.setContentsMargins(20, 20, 20, 20)
        status_layout.setSpacing(15)

        self.lbl_mode_icon = QLabel("\U0001f4bb")
        self.lbl_mode_icon.setObjectName("StatusIcon")

        status_text_layout = QVBoxLayout()
        self.lbl_status_title = QLabel("Single Computer Mode")
        self.lbl_status_title.setObjectName("StatusTitle")
        self.lbl_status_subtitle = QLabel("Standalone \u2022 Local Database")
        self.lbl_status_subtitle.setObjectName("StatusSubtitle")
        status_text_layout.addWidget(self.lbl_status_title)
        status_text_layout.addWidget(self.lbl_status_subtitle)

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

        mode_layout.addWidget(self.status_card)

        self.lbl_warning = QLabel("Changing database mode requires application restart.")
        self.lbl_warning.setObjectName("NetworkWarning")
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.setProperty("class", "warning-hint")
        self.lbl_warning.setVisible(False)
        mode_layout.addWidget(self.lbl_warning)

        self.tabs.addTab(tab_mode, "Mode")

        # --- Tab 2: Server Configuration ---
        tab_server, server_layout = self._build_vbox_tab()

        self.config_card = QFrame()
        self.config_card.setObjectName("NetworkCard")
        self.config_card.setFrameShape(QFrame.Shape.StyledPanel)
        config_layout = QVBoxLayout(self.config_card)
        config_layout.setContentsMargins(25, 25, 25, 25)
        config_layout.setSpacing(18)

        config_title = QLabel("Server Configuration")
        config_title.setObjectName("CardTitle")
        config_layout.addWidget(config_title)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "127.0.0.1"

        self.lbl_local_ip = QLabel(f"This Computer's IP: {local_ip}")
        self.lbl_local_ip.setObjectName("IPHelper")
        config_layout.addWidget(self.lbl_local_ip)

        grid_layout = QGridLayout()
        grid_layout.setVerticalSpacing(12)
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)

        lbl_host = QLabel("Host IP:")
        lbl_host.setObjectName("FormLabel")
        self.input_host = QLineEdit()
        self.input_host.setObjectName("InputNetwork")
        self.input_host.setPlaceholderText("e.g., 192.168.1.100")
        grid_layout.addWidget(
            lbl_host,
            0,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_host, 0, 1)

        lbl_port = QLabel("Port:")
        lbl_port.setObjectName("FormLabel")
        self.input_port = QSpinBox()
        self.input_port.setObjectName("InputNetwork")
        self.input_port.setRange(1, 65535)
        self.input_port.setValue(5432)
        grid_layout.addWidget(
            lbl_port,
            1,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_port, 1, 1)

        lbl_dbname = QLabel("Database Name:")
        lbl_dbname.setObjectName("FormLabel")
        self.input_dbname = QLineEdit()
        self.input_dbname.setObjectName("InputNetwork")
        self.input_dbname.setPlaceholderText("cbpos")
        grid_layout.addWidget(
            lbl_dbname,
            2,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_dbname, 2, 1)

        lbl_user = QLabel("Username:")
        lbl_user.setObjectName("FormLabel")
        self.input_user = QLineEdit()
        self.input_user.setObjectName("InputNetwork")
        self.input_user.setPlaceholderText("postgres")
        grid_layout.addWidget(
            lbl_user,
            3,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_user, 3, 1)

        lbl_password = QLabel("Password:")
        lbl_password.setObjectName("FormLabel")
        self.input_password = QLineEdit()
        self.input_password.setObjectName("InputNetwork")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setPlaceholderText("password")
        grid_layout.addWidget(
            lbl_password,
            4,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_password, 4, 1)

        config_layout.addLayout(grid_layout)

        test_btn_layout = QHBoxLayout()
        self.btn_test = QPushButton("Test Connection")
        self.btn_test.setObjectName("BtnTestNetwork")
        self.btn_test.clicked.connect(self._test_connection)
        self.lbl_test_status = QLabel("")
        self.lbl_test_status.setObjectName("TestStatus")
        test_btn_layout.addWidget(self.btn_test)
        test_btn_layout.addWidget(self.lbl_test_status, 1)
        config_layout.addLayout(test_btn_layout)

        server_layout.addWidget(self.config_card)

        self.tabs.addTab(tab_server, "Server")

        # --- Tab 3: Migration ---
        tab_migrate, migrate_layout = self._build_vbox_tab()

        self.migration_card = QFrame()
        self.migration_card.setObjectName("MigrationCard")
        self.migration_card.setFrameShape(QFrame.Shape.StyledPanel)
        migration_layout = QVBoxLayout(self.migration_card)
        migration_layout.setContentsMargins(25, 25, 25, 25)
        migration_layout.setSpacing(18)

        migration_title = QLabel("First-Time Server Setup")
        migration_title.setObjectName("CardTitle")
        migration_layout.addWidget(migration_title)

        migration_info = QLabel(
            "Setting up the Main Server? Upload your current data to get started.\n\n"
            "This will transfer all products, customers, and sales history to the "
            "network database.\nThe target database must be empty."
        )
        migration_info.setWordWrap(True)
        migration_info.setObjectName("MigrationInfo")
        migration_layout.addWidget(migration_info)

        self.btn_migrate = QPushButton("Upload Local Data to Server")
        self.btn_migrate.setObjectName("BtnMigrate")
        self.btn_migrate.setEnabled(False)
        self.btn_migrate.clicked.connect(self._migrate_data)
        migration_layout.addWidget(self.btn_migrate)

        migrate_layout.addWidget(self.migration_card)

        self.tabs.addTab(tab_migrate, "Migration")

        self._on_mode_changed("Standalone")

    def load(self, settings: dict):
        db_mode = settings.get("db_mode", "standalone")
        self.cmb_db_mode.setCurrentText("Standalone" if db_mode == "standalone" else "Network")
        self.input_host.setText(settings.get("network_db_host", "localhost"))
        self.input_port.setValue(settings.get("network_db_port", 5432))
        self.input_dbname.setText(settings.get("network_db_name", "cbpos"))
        self.input_user.setText(settings.get("network_db_user", "postgres"))
        self.input_password.setText(settings.get("network_db_password", ""))
        self._original_mode = self.cmb_db_mode.currentText()
        self._on_mode_changed(self.cmb_db_mode.currentText())

    def save(self) -> dict:
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
        is_network = mode == "Network"
        if is_network:
            self.lbl_mode_icon.setText("\U0001f310")
            self.lbl_status_title.setText("Network Mode")
            self.lbl_status_subtitle.setText("Multi-Terminal \u2022 Shared Database")
        else:
            self.lbl_mode_icon.setText("\U0001f4bb")
            self.lbl_status_title.setText("Single Computer Mode")
            self.lbl_status_subtitle.setText("Standalone \u2022 Local Database")
        self.connection_tested = False
        self.btn_migrate.setEnabled(False)
        self.lbl_test_status.setText("")
        if hasattr(self, "_original_mode"):
            self.lbl_warning.setVisible(mode != self._original_mode)

    def _get_network_config(self):
        return {
            "host": self.input_host.text().strip(),
            "port": self.input_port.value(),
            "dbname": self.input_dbname.text().strip(),
            "user": self.input_user.text().strip(),
            "password": self.input_password.text(),
        }

    def _test_connection(self):
        from cbpos.core.database import Database

        cfg = self._get_network_config()
        if not all([cfg["host"], cfg["dbname"], cfg["user"]]):
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please fill in all required fields (Host, Database Name, Username).",
            )
            return

        self.lbl_test_status.setText("Testing...")
        self.btn_test.setEnabled(False)
        QApplication.processEvents()

        success, message = Database.test_connection(
            mode="network",
            host=cfg["host"],
            port=cfg["port"],
            dbname=cfg["dbname"],
            user=cfg["user"],
            password=cfg["password"],
        )
        self.btn_test.setEnabled(True)

        if success:
            self.connection_tested = True
            self.lbl_test_status.setText("Connected")
            self.btn_migrate.setEnabled(True)
            QMessageBox.information(
                self,
                "Connection Test",
                f"{message}\n\nYou can now upload your data.",
            )
        else:
            self.connection_tested = False
            self.lbl_test_status.setText("Failed")
            self.btn_migrate.setEnabled(False)
            QMessageBox.critical(self, "Connection Test", message)

    def _migrate_data(self):
        from cbpos.core.services.migration_service import MigrationService

        cfg = self._get_network_config()
        if not all([cfg["host"], cfg["dbname"], cfg["user"]]):
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please fill in all required connection fields before migrating data.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Data Migration",
            f"This will upload ALL your local data to:\n\n"  # noqa: E231
            f"  Host: {cfg['host']}:{cfg['port']}\n"  # noqa: E231
            f"  Database: {cfg['dbname']}\n\n"  # noqa: E231
            f"The target database must be empty. This operation may take several minutes.\n\n"
            f"Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        sqlite_url = Config.DB_URI
        url_obj = URL.create(
            drivername="postgresql+psycopg2",
            username=cfg["user"],
            password=cfg["password"],
            host=cfg["host"],
            port=cfg["port"],
            database=cfg["dbname"],
        )
        postgres_url = url_obj

        progress = QProgressDialog("Migrating data to server...\nPlease wait.", None, 0, 0, self)
        progress.setWindowTitle("Data Migration")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        try:
            success, message = MigrationService.migrate_sqlite_to_postgres(sqlite_url, postgres_url)
            progress.close()
            if success:
                QMessageBox.information(
                    self,
                    "Migration Successful",
                    f"{message}\n\nNext steps:\n"  # noqa: E231
                    f"1. Save these network settings\n"
                    f"2. Restart the application\n"
                    f"3. All terminals can now connect to the server",
                )
            else:
                QMessageBox.critical(
                    self,
                    "Migration Failed",
                    f"Migration error:\n\n{message}",  # noqa: E231
                )
        except Exception as e:
            progress.close()
            import logging

            logging.getLogger(__name__).exception("Data migration failed: %s", e)
            QMessageBox.critical(
                self,
                "Migration Error",
                "An unexpected error occurred during migration.\n" "Please check the application logs for details.",
            )
