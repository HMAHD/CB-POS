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
from PyQt6.QtGui import QIcon, QIntValidator
from PyQt6.QtPrintSupport import QPrinterInfo
from sqlalchemy.engine import URL
from cbpos.core.services.language_service import LanguageService
from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.resources.icons import Icons
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.models import Sale, SaleItem, SalePayment, Product
from cbpos.config import Config
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
import decimal
import socket


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

        self._page_title = QLabel(title_text)
        self._page_title.setProperty("class", "dialog-title")
        layout.addWidget(self._page_title)

        self._page_subtitle = QLabel(subtitle_text)
        self._page_subtitle.setProperty("class", "muted")
        layout.addWidget(self._page_subtitle)

        tabs = QTabWidget()
        # Native styles (e.g. Windows) elide tab labels with "..." once the
        # bar is narrower than its tabs' natural width -- ElideNone plus the
        # scroll buttons QTabBar already enables by default keeps every
        # label fully readable instead of silently truncating it (#321).
        tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
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

        Returns a single widget containing: [title] -- [line] that spans the
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
        _, self.tabs = self._create_page_layout("", "")

        # --- Tab 1: Business ---
        self._tab_biz, self._form_biz = self._build_form_tab()

        self.input_shop_name = QLineEdit()
        self.input_address = QLineEdit()
        self.input_phone = QLineEdit()
        self.input_vat = QLineEdit()
        self.input_tax_id = QLineEdit()
        self.input_currency = QLineEdit()

        self._lbl_shop_name = QLabel()
        self._lbl_address = QLabel()
        self._lbl_phone = QLabel()
        self._lbl_vat = QLabel()
        self._lbl_tax_id = QLabel()
        self._lbl_currency = QLabel()

        self._form_biz.addRow(self._lbl_shop_name, self.input_shop_name)
        self._form_biz.addRow(self._lbl_address, self.input_address)
        self._form_biz.addRow(self._lbl_phone, self.input_phone)
        self._form_biz.addRow(self._lbl_vat, self.input_vat)
        self._form_biz.addRow(self._lbl_tax_id, self.input_tax_id)
        self._form_biz.addRow(self._lbl_currency, self.input_currency)

        self.tabs.addTab(self._tab_biz, "")

        # --- Tab 2: Banking ---
        self._tab_bank, self._form_bank = self._build_form_tab()

        self.input_bank_name = QLineEdit()
        self.input_account_no = QLineEdit()
        self.input_branch = QLineEdit()

        self._lbl_bank_name = QLabel()
        self._lbl_account_no = QLabel()
        self._lbl_branch = QLabel()

        self._form_bank.addRow(self._lbl_bank_name, self.input_bank_name)
        self._form_bank.addRow(self._lbl_account_no, self.input_account_no)
        self._form_bank.addRow(self._lbl_branch, self.input_branch)

        self.tabs.addTab(self._tab_bank, "")

        # --- Tab 3: Email ---
        self._tab_email, self._form_email = self._build_form_tab()

        # Helper buttons row at top
        email_btn_row = QHBoxLayout()
        email_btn_row.addStretch()

        self.btn_gmail = QPushButton()
        self.btn_gmail.setFixedHeight(32)
        self.btn_gmail.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gmail.setObjectName("BtnGmailHelper")
        self.btn_gmail.setProperty("class", "link")
        self.btn_gmail.clicked.connect(self._prefill_gmail)
        email_btn_row.addWidget(self.btn_gmail)

        self.btn_help = QPushButton()
        info_icon_path = str(Config.BASE_DIR / "cbpos" / "assets" / "icons" / "info-circle-cyan.svg")
        self.btn_help.setIcon(QIcon(info_icon_path))
        self.btn_help.setIconSize(QSize(24, 24))
        self.btn_help.setFixedSize(28, 28)
        self.btn_help.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_help.setObjectName("BtnInfoIcon")
        self.btn_help.clicked.connect(self._show_smtp_guide)
        email_btn_row.addWidget(self.btn_help)

        self._form_email.addRow(email_btn_row)

        self.chk_auto_report = QCheckBox()
        self._lbl_auto_report = QLabel()
        self._form_email.addRow(self._lbl_auto_report, self.chk_auto_report)

        self.time_auto_report = QTimeEdit()
        self.time_auto_report.setDisplayFormat("HH:mm")
        self.time_auto_report.setFixedWidth(200)
        self._lbl_report_time = QLabel()
        self._form_email.addRow(self._lbl_report_time, self.time_auto_report)

        self.input_admin_email = QLineEdit()
        self._lbl_admin_email = QLabel()
        self._form_email.addRow(self._lbl_admin_email, self.input_admin_email)

        self.input_smtp_host = QLineEdit()
        self._lbl_smtp_host = QLabel()
        self._form_email.addRow(self._lbl_smtp_host, self.input_smtp_host)

        self.input_smtp_port = QLineEdit()
        self.input_smtp_port.setValidator(QIntValidator(1, 65535))
        self._lbl_smtp_port = QLabel()
        self._form_email.addRow(self._lbl_smtp_port, self.input_smtp_port)

        self.input_smtp_user = QLineEdit()
        self._lbl_smtp_user = QLabel()
        self._form_email.addRow(self._lbl_smtp_user, self.input_smtp_user)

        self.input_smtp_pass = QLineEdit()
        self.input_smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._lbl_smtp_pass = QLabel()
        self._form_email.addRow(self._lbl_smtp_pass, self.input_smtp_pass)

        self.tabs.addTab(self._tab_email, "")

        # --- Tab 4: Appearance ---
        self._tab_appear, self._form_appear = self._build_form_tab()

        # QLineEdit + QIntValidator instead of QSpinBox for clean rendering
        # (QSpinBox +/- buttons break under QSS), matching the pattern
        # already proven in product_editor.py's Stock group.
        self.spin_font_size = QLineEdit()
        self.spin_font_size.setValidator(QIntValidator(8, 24))
        self.spin_font_size.setFixedWidth(200)
        self._lbl_font_size = QLabel()
        self._form_appear.addRow(self._lbl_font_size, self.spin_font_size)

        self.combo_theme = QComboBox()
        self.combo_theme.setFixedWidth(200)
        self._lbl_theme = QLabel()
        self._form_appear.addRow(self._lbl_theme, self.combo_theme)

        self.combo_language = QComboBox()
        self.combo_language.setFixedWidth(200)
        languages = LanguageService.get_available_languages()
        for code, name in languages.items():
            self.combo_language.addItem(f"{name} ({code})", code)
        self._lbl_language = QLabel()
        self._form_appear.addRow(self._lbl_language, self.combo_language)

        self.lbl_restart = QLabel()
        self.lbl_restart.setProperty("class", "warning-hint")
        self._form_appear.addRow("", self.lbl_restart)

        self.tabs.addTab(self._tab_appear, "")

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def retranslate_ui(self) -> None:
        self._page_title.setText(_t("settings.shop_info.title"))
        self._page_subtitle.setText(_t("settings.shop_info.subtitle"))

        # Tab titles
        self.tabs.setTabText(0, _t("settings.shop_info.tab_business"))
        self.tabs.setTabText(1, _t("settings.shop_info.tab_banking"))
        self.tabs.setTabText(2, _t("settings.shop_info.tab_email"))
        self.tabs.setTabText(3, _t("settings.shop_info.tab_appearance"))

        # Business
        self._lbl_shop_name.setText(_t("settings.shop_info.shop_name"))
        self._lbl_address.setText(_t("settings.shop_info.address"))
        self._lbl_phone.setText(_t("settings.shop_info.phone"))
        self._lbl_vat.setText(_t("settings.shop_info.vat_number"))
        self._lbl_tax_id.setText(_t("settings.shop_info.company_tax_id"))
        self._lbl_currency.setText(_t("settings.shop_info.currency_symbol"))

        # Banking
        self._lbl_bank_name.setText(_t("settings.shop_info.bank_name"))
        self._lbl_account_no.setText(_t("settings.shop_info.account_number"))
        self._lbl_branch.setText(_t("settings.shop_info.branch"))

        # Email
        self.btn_gmail.setText(_t("settings.shop_info.btn_use_gmail"))
        self.btn_gmail.setToolTip(_t("settings.shop_info.tooltip_gmail"))
        self.btn_help.setToolTip(_t("settings.shop_info.tooltip_email_help"))
        self._lbl_auto_report.setText(_t("settings.shop_info.enable_auto_report"))
        self.chk_auto_report.setToolTip(_t("settings.shop_info.tooltip_auto_report"))
        self._lbl_report_time.setText(_t("settings.shop_info.report_time"))
        self._lbl_admin_email.setText(_t("settings.shop_info.admin_email"))
        self.input_admin_email.setPlaceholderText(_t("settings.shop_info.admin_email_placeholder"))
        self._lbl_smtp_host.setText(_t("settings.shop_info.smtp_host"))
        self.input_smtp_host.setPlaceholderText(_t("settings.shop_info.smtp_host_placeholder"))
        self._lbl_smtp_port.setText(_t("settings.shop_info.smtp_port"))
        self.input_smtp_port.setPlaceholderText(_t("settings.shop_info.smtp_port_placeholder"))
        self._lbl_smtp_user.setText(_t("settings.shop_info.smtp_user"))
        self.input_smtp_user.setPlaceholderText(_t("settings.shop_info.smtp_user_placeholder"))
        self._lbl_smtp_pass.setText(_t("settings.shop_info.smtp_password"))
        self.input_smtp_pass.setPlaceholderText(_t("settings.shop_info.smtp_password_placeholder"))

        # Appearance
        self._lbl_font_size.setText(_t("settings.shop_info.font_size"))
        self._lbl_theme.setText(_t("settings.shop_info.theme"))

        # Re-populate theme combo preserving selection
        current_theme_idx = self.combo_theme.currentIndex()
        self.combo_theme.clear()
        self.combo_theme.addItems(
            [
                _t("settings.shop_info.theme_dark"),
                _t("settings.shop_info.theme_light"),
            ]
        )
        if current_theme_idx >= 0:
            self.combo_theme.setCurrentIndex(current_theme_idx)

        self._lbl_language.setText(_t("settings.shop_info.language"))
        self.lbl_restart.setText(_t("settings.shop_info.restart_hint"))

    def _prefill_gmail(self):
        """Pre-fill SMTP fields with Gmail defaults."""
        self.input_smtp_host.setText("smtp.gmail.com")
        self.input_smtp_port.setText("587")
        if not self.input_smtp_user.text():
            self.input_smtp_user.setFocus()

    def _show_smtp_guide(self):
        """Show a clean step-by-step SMTP setup guide dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle(_t("settings.shop_info.email_guide_title"))
        dlg.setMinimumWidth(480)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel(_t("settings.shop_info.email_guide_heading"))
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        guide_steps = [
            ("1", _t("settings.shop_info.guide_step1_title"), _t("settings.shop_info.guide_step1_detail")),
            ("2", _t("settings.shop_info.guide_step2_title"), _t("settings.shop_info.guide_step2_detail")),
            ("3", _t("settings.shop_info.guide_step3_title"), _t("settings.shop_info.guide_step3_detail")),
            ("4", _t("settings.shop_info.guide_step4_title"), _t("settings.shop_info.guide_step4_detail")),
        ]

        for num, heading, detail in guide_steps:
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

        note = QLabel("<b>" + _t("common.important") + ":</b> " + _t("settings.shop_info.guide_important_note"))
        note.setWordWrap(True)
        note.setProperty("class", "muted")
        layout.addWidget(note)

        btn_close = QPushButton(_t("settings.shop_info.guide_btn_close"))
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

        self.spin_font_size.setText(str(settings.get("font_size", 12)))
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
            "font_size": int(self.spin_font_size.text() or 12),
            "theme": theme_selection,
            "language": lang_code,
        }


class SalesTaxPage(SettingsPage):
    """Sales search mode + Tax configuration."""

    def init_ui(self):
        _, self.tabs = self._create_page_layout("", "")

        # --- Tab 1: Sales ---
        self._tab_sales, self._form_sales = self._build_form_tab()

        self.combo_search_mode = QComboBox()
        self.combo_search_mode.setFixedWidth(200)
        self._lbl_search_mode = QLabel()
        self._form_sales.addRow(self._lbl_search_mode, self.combo_search_mode)

        self.spin_max_discount = QDoubleSpinBox()
        self.spin_max_discount.setRange(0, 100)
        self.spin_max_discount.setDecimals(1)
        self.spin_max_discount.setSuffix("%")
        self.spin_max_discount.setFixedWidth(200)
        self._lbl_max_discount = QLabel()
        self._form_sales.addRow(self._lbl_max_discount, self.spin_max_discount)

        self.spin_loyalty_ratio = QSpinBox()
        self.spin_loyalty_ratio.setRange(1, 10000)
        self.spin_loyalty_ratio.setPrefix("Rs. ")
        self.spin_loyalty_ratio.setFixedWidth(200)
        self._lbl_loyalty_ratio = QLabel()
        self._form_sales.addRow(self._lbl_loyalty_ratio, self.spin_loyalty_ratio)

        self.spin_default_credit = QSpinBox()
        self.spin_default_credit.setRange(0, 1000000)
        self.spin_default_credit.setPrefix("Rs. ")
        self.spin_default_credit.setFixedWidth(200)
        self._lbl_default_credit = QLabel()
        self._form_sales.addRow(self._lbl_default_credit, self.spin_default_credit)

        self.tabs.addTab(self._tab_sales, "")

        # --- Tab 2: Tax ---
        self._tab_tax, self._form_tax = self._build_form_tab()

        self.chk_vat_registered = QCheckBox()
        self.chk_vat_registered.stateChanged.connect(self._toggle_tax_fields)
        self._form_tax.addRow(self.chk_vat_registered)

        self.lbl_tax_warn = QLabel()
        self.lbl_tax_warn.setProperty("class", "warning-hint")
        self._form_tax.addRow(self.lbl_tax_warn)

        self.spin_vat = QSpinBox()
        self.spin_vat.setRange(0, 100)
        self.spin_vat.setSuffix("%")
        self.spin_vat.setFixedWidth(200)
        self._lbl_vat_rate = QLabel()
        self._form_tax.addRow(self._lbl_vat_rate, self.spin_vat)

        self.spin_sscl = QDoubleSpinBox()
        self.spin_sscl.setRange(0, 100)
        self.spin_sscl.setDecimals(2)
        self.spin_sscl.setSuffix("%")
        self.spin_sscl.setFixedWidth(200)
        self._lbl_sscl_rate = QLabel()
        self._form_tax.addRow(self._lbl_sscl_rate, self.spin_sscl)

        self.spin_sscl_turnover = QDoubleSpinBox()
        self.spin_sscl_turnover.setRange(0, 100)
        self.spin_sscl_turnover.setDecimals(1)
        self.spin_sscl_turnover.setSuffix("%")
        self.spin_sscl_turnover.setFixedWidth(200)
        self._lbl_sscl_turnover = QLabel()
        self._form_tax.addRow(self._lbl_sscl_turnover, self.spin_sscl_turnover)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        self._form_tax.addRow(sep)

        self.chk_item_tax_exemptions = QCheckBox()
        self._form_tax.addRow(self.chk_item_tax_exemptions)

        self.tabs.addTab(self._tab_tax, "")

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def retranslate_ui(self) -> None:
        self._page_title.setText(_t("settings.sales_tax.title"))
        self._page_subtitle.setText(_t("settings.sales_tax.subtitle"))

        self.tabs.setTabText(0, _t("settings.sales_tax.tab_sales"))
        self.tabs.setTabText(1, _t("settings.sales_tax.tab_tax"))

        # Sales tab
        self._lbl_search_mode.setText(_t("settings.sales_tax.default_search_mode"))

        # Re-populate search mode combo preserving selection
        current_data = self.combo_search_mode.currentData()
        self.combo_search_mode.clear()
        self.combo_search_mode.addItem(_t("settings.sales_tax.search_mode_all"), "ALL")
        self.combo_search_mode.addItem(_t("settings.sales_tax.search_mode_barcode"), "BARCODE")
        self.combo_search_mode.addItem(_t("settings.sales_tax.search_mode_name"), "NAME")
        if current_data:
            idx = self.combo_search_mode.findData(current_data)
            if idx >= 0:
                self.combo_search_mode.setCurrentIndex(idx)

        self._lbl_max_discount.setText(_t("settings.sales_tax.max_discount"))
        self.spin_max_discount.setToolTip(_t("settings.sales_tax.tooltip_max_discount"))
        self._lbl_loyalty_ratio.setText(_t("settings.sales_tax.loyalty_ratio"))
        self.spin_loyalty_ratio.setToolTip(_t("settings.sales_tax.tooltip_loyalty_ratio"))
        self._lbl_default_credit.setText(_t("settings.sales_tax.default_credit_limit"))
        self.spin_default_credit.setToolTip(_t("settings.sales_tax.tooltip_default_credit"))

        # Tax tab
        self.chk_vat_registered.setText(_t("settings.sales_tax.vat_registered"))
        self.chk_vat_registered.setToolTip(_t("settings.sales_tax.tooltip_vat_registered"))
        self.lbl_tax_warn.setText(_t("settings.sales_tax.tax_warning"))
        self._lbl_vat_rate.setText(_t("settings.sales_tax.vat_rate"))
        self._lbl_sscl_rate.setText(_t("settings.sales_tax.sscl_rate"))
        self._lbl_sscl_turnover.setText(_t("settings.sales_tax.sscl_turnover_base"))
        self.chk_item_tax_exemptions.setText(_t("settings.sales_tax.item_tax_exemptions"))
        self.chk_item_tax_exemptions.setToolTip(_t("settings.sales_tax.tooltip_item_tax_exemptions"))

    def _toggle_tax_fields(self) -> None:
        """Enable/disable tax rate fields and sub-options based on VAT registration status."""
        enabled = self.chk_vat_registered.isChecked()
        self.spin_vat.setEnabled(enabled)
        self.spin_sscl.setEnabled(enabled)
        self.spin_sscl_turnover.setEnabled(enabled)
        self.chk_item_tax_exemptions.setEnabled(enabled)

    def load(self, settings: dict):
        mode = settings.get("default_search_mode", "ALL")
        idx = self.combo_search_mode.findData(mode)
        if idx >= 0:
            self.combo_search_mode.setCurrentIndex(idx)
        self.spin_max_discount.setValue(float(settings.get("max_discount_percent", 15.0)))
        self.spin_loyalty_ratio.setValue(int(settings.get("loyalty_points_ratio", 100)))
        self.spin_default_credit.setValue(int(settings.get("default_credit_limit", 0)))
        self.chk_vat_registered.setChecked(settings.get("vat_registered", False))
        self.spin_vat.setValue(int(settings.get("tax_vat_rate", 18)))
        self.spin_sscl.setValue(float(settings.get("tax_sscl_rate", 2.5)))
        self.spin_sscl_turnover.setValue(float(settings.get("tax_sscl_turnover_pct", 50.0)))
        self.chk_item_tax_exemptions.setChecked(settings.get("item_tax_exemptions", False))
        self._toggle_tax_fields()

    def save(self) -> dict:
        return {
            "default_search_mode": self.combo_search_mode.currentData() or "ALL",
            "max_discount_percent": self.spin_max_discount.value(),
            "loyalty_points_ratio": self.spin_loyalty_ratio.value(),
            "default_credit_limit": self.spin_default_credit.value(),
            "vat_registered": self.chk_vat_registered.isChecked(),
            "tax_vat_rate": self.spin_vat.value(),
            "tax_sscl_rate": self.spin_sscl.value(),
            "tax_sscl_turnover_pct": self.spin_sscl_turnover.value(),
            "item_tax_exemptions": self.chk_item_tax_exemptions.isChecked(),
        }


class DocumentPage(SettingsPage):
    """Documents + Terminal ID."""

    def init_ui(self):
        _, self.tabs = self._create_page_layout("", "")

        self._tab_docs, self._form_docs = self._build_form_tab()

        self.input_terminal_id = QLineEdit()
        self._lbl_terminal_id = QLabel()
        self._form_docs.addRow(self._lbl_terminal_id, self.input_terminal_id)

        self.combo_reset_period = QComboBox()
        self._lbl_reset_period = QLabel()
        self._form_docs.addRow(self._lbl_reset_period, self.combo_reset_period)

        self.input_fmt_sale = QLineEdit()
        self._lbl_sale_fmt = QLabel()
        self._form_docs.addRow(self._lbl_sale_fmt, self.input_fmt_sale)

        self.input_fmt_purchase = QLineEdit()
        self._lbl_purchase_fmt = QLabel()
        self._form_docs.addRow(self._lbl_purchase_fmt, self.input_fmt_purchase)

        self.input_fmt_return = QLineEdit()
        self._lbl_return_fmt = QLabel()
        self._form_docs.addRow(self._lbl_return_fmt, self.input_fmt_return)

        self.tabs.addTab(self._tab_docs, "")

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def retranslate_ui(self) -> None:
        self._page_title.setText(_t("settings.documents.title"))
        self._page_subtitle.setText(_t("settings.documents.subtitle"))

        self.tabs.setTabText(0, _t("settings.documents.tab_numbering"))

        self._lbl_terminal_id.setText(_t("settings.documents.terminal_id"))
        self.input_terminal_id.setPlaceholderText(_t("settings.documents.terminal_id_placeholder"))

        self._lbl_reset_period.setText(_t("settings.documents.reset_period"))

        # Re-populate reset period combo preserving selection
        current_data = self.combo_reset_period.currentData()
        self.combo_reset_period.clear()
        self.combo_reset_period.addItem(_t("settings.documents.reset_yearly"), "YEARLY")
        self.combo_reset_period.addItem(_t("settings.documents.reset_monthly"), "MONTHLY")
        self.combo_reset_period.addItem(_t("settings.documents.reset_never"), "NEVER")
        if current_data:
            idx = self.combo_reset_period.findData(current_data)
            if idx >= 0:
                self.combo_reset_period.setCurrentIndex(idx)

        self._lbl_sale_fmt.setText(_t("settings.documents.sale_format"))
        self.input_fmt_sale.setPlaceholderText(_t("settings.documents.sale_format_placeholder"))
        self._lbl_purchase_fmt.setText(_t("settings.documents.purchase_format"))
        self.input_fmt_purchase.setPlaceholderText(_t("settings.documents.purchase_format_placeholder"))
        self._lbl_return_fmt.setText(_t("settings.documents.return_format"))
        self.input_fmt_return.setPlaceholderText(_t("settings.documents.return_format_placeholder"))

    def load(self, settings: dict):
        self.input_terminal_id.setText(settings.get("terminal_id", "TERM-01"))
        period = settings.get("doc_reset_period", "YEARLY")
        idx = self.combo_reset_period.findData(period)
        if idx >= 0:
            self.combo_reset_period.setCurrentIndex(idx)
        self.input_fmt_sale.setText(settings.get("doc_format_sale", "INV-{Y}-{seq:05d}"))
        self.input_fmt_purchase.setText(settings.get("doc_format_purchase", "GRN-{Y}-{seq:05d}"))
        self.input_fmt_return.setText(settings.get("doc_format_return", "CN-{Y}-{seq:05d}"))

    def save(self) -> dict:
        return {
            "terminal_id": self.input_terminal_id.text().strip() or "TERM-01",
            "doc_reset_period": self.combo_reset_period.currentData() or "YEARLY",
            "doc_format_sale": self.input_fmt_sale.text(),
            "doc_format_purchase": self.input_fmt_purchase.text(),
            "doc_format_return": self.input_fmt_return.text(),
        }


class HardwarePage(SettingsPage):
    """Hardware + Paper Width."""

    def init_ui(self):
        _, self.tabs = self._create_page_layout("", "")

        # --- Tab 1: Printers ---
        tab_printer, vbox_printer = self._build_vbox_tab()

        available_printers = QPrinterInfo.availablePrinterNames() or [_t("settings.hardware.no_printers")]

        # Section: Printer Selection
        self._header_printer_sel = self._make_section_header(_t("settings.hardware.section_printer_selection"))
        vbox_printer.addWidget(self._header_printer_sel)

        sel_form = QFormLayout()
        self.configure_form_layout(sel_form)
        sel_form.setContentsMargins(0, 0, 0, 0)
        sel_form.setVerticalSpacing(10)

        self.combo_receipt_printer = QComboBox()
        self.combo_receipt_printer.addItems(available_printers)
        self._lbl_receipt_printer = QLabel()
        sel_form.addRow(self._lbl_receipt_printer, self.combo_receipt_printer)

        self.combo_a4_printer = QComboBox()
        self.combo_a4_printer.addItems(available_printers)
        self._lbl_a4_printer = QLabel()
        sel_form.addRow(self._lbl_a4_printer, self.combo_a4_printer)

        # Printer detection only ever ran once, here at construction time,
        # and this page is built once and kept alive for the rest of the
        # session -- a printer plugged in after launch needed a full app
        # restart to appear (#323).
        self.btn_refresh_printers = QPushButton()
        self.btn_refresh_printers.setProperty("class", "secondary")
        self.btn_refresh_printers.clicked.connect(self._refresh_printer_list)
        sel_form.addRow("", self.btn_refresh_printers)

        self.combo_paper_width = QComboBox()
        self.combo_paper_width.addItems(["80mm", "58mm"])
        self._lbl_paper_width = QLabel()
        sel_form.addRow(self._lbl_paper_width, self.combo_paper_width)
        vbox_printer.addLayout(sel_form)

        # Section: Print Behavior
        self._header_print_beh = self._make_section_header(_t("settings.hardware.section_print_behavior"))
        vbox_printer.addWidget(self._header_print_beh)

        beh_form = QFormLayout()
        self.configure_form_layout(beh_form)
        beh_form.setContentsMargins(0, 0, 0, 0)
        beh_form.setVerticalSpacing(10)

        self.chk_auto_print = QCheckBox()
        self._lbl_auto_print = QLabel()
        beh_form.addRow(self._lbl_auto_print, self.chk_auto_print)

        self.spin_copies = QSpinBox()
        self.spin_copies.setRange(1, 5)
        self.spin_copies.setFixedWidth(200)
        self._lbl_copies = QLabel()
        beh_form.addRow(self._lbl_copies, self.spin_copies)
        vbox_printer.addLayout(beh_form)

        # Test Buttons
        self._header_test_hw = self._make_section_header(_t("settings.hardware.section_test_hardware"))
        vbox_printer.addWidget(self._header_test_hw)
        test_row = QHBoxLayout()
        self.btn_test_print = QPushButton()
        self.btn_test_print.setProperty("class", "accent")
        self.btn_test_print.clicked.connect(self._test_print)
        test_row.addWidget(self.btn_test_print)

        self.btn_open_drawer = QPushButton()
        self.btn_open_drawer.clicked.connect(self._test_drawer)
        test_row.addWidget(self.btn_open_drawer)
        test_row.addStretch()
        vbox_printer.addLayout(test_row)

        self.tabs.addTab(tab_printer, "")

        # --- Tab: Paper Cut & Drawer ---
        tab_cut, vbox_cut = self._build_vbox_tab()

        # Section: Paper Cut
        self._header_paper_cut = self._make_section_header(_t("settings.hardware.section_paper_cut"))
        vbox_cut.addWidget(self._header_paper_cut)

        cut_form = QFormLayout()
        self.configure_form_layout(cut_form)
        cut_form.setContentsMargins(0, 0, 0, 0)
        cut_form.setVerticalSpacing(10)

        self.chk_auto_cut = QCheckBox()
        self._lbl_auto_cut = QLabel()
        cut_form.addRow(self._lbl_auto_cut, self.chk_auto_cut)

        self.combo_cut_type = QComboBox()
        self._lbl_cut_type = QLabel()
        cut_form.addRow(self._lbl_cut_type, self.combo_cut_type)

        self.spin_feed_lines = QSpinBox()
        self.spin_feed_lines.setRange(1, 8)
        self._lbl_feed_lines = QLabel()
        cut_form.addRow(self._lbl_feed_lines, self.spin_feed_lines)
        vbox_cut.addLayout(cut_form)

        # Section: Cash Drawer
        self._header_cash_drawer = self._make_section_header(_t("settings.hardware.section_cash_drawer"))
        vbox_cut.addWidget(self._header_cash_drawer)

        drawer_form = QFormLayout()
        self.configure_form_layout(drawer_form)
        drawer_form.setContentsMargins(0, 0, 0, 0)
        drawer_form.setVerticalSpacing(10)

        self.chk_drawer_cash_only = QCheckBox()
        self._lbl_drawer_cash_only = QLabel()
        drawer_form.addRow(self._lbl_drawer_cash_only, self.chk_drawer_cash_only)
        vbox_cut.addLayout(drawer_form)

        self.tabs.addTab(tab_cut, "")

        # --- Tab: Scale ---
        tab_scale, vbox_scale = self._build_vbox_tab()

        self._header_scale = self._make_section_header(_t("settings.hardware.section_weighing_scale"))
        vbox_scale.addWidget(self._header_scale)

        scale_form = QFormLayout()
        self.configure_form_layout(scale_form)
        scale_form.setContentsMargins(0, 0, 0, 0)
        scale_form.setVerticalSpacing(10)

        self.input_scale_prefix = QLineEdit()
        self.input_scale_prefix.setMaxLength(2)
        self._lbl_barcode_prefix = QLabel()
        scale_form.addRow(self._lbl_barcode_prefix, self.input_scale_prefix)

        self.spin_decimal_places = QSpinBox()
        self.spin_decimal_places.setRange(0, 4)
        self._lbl_decimal_places = QLabel()
        scale_form.addRow(self._lbl_decimal_places, self.spin_decimal_places)
        vbox_scale.addLayout(scale_form)

        self.tabs.addTab(tab_scale, "")

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def retranslate_ui(self) -> None:
        self._page_title.setText(_t("settings.hardware.title"))
        self._page_subtitle.setText(_t("settings.hardware.subtitle"))

        self.tabs.setTabText(0, _t("settings.hardware.tab_printers"))
        self.tabs.setTabText(1, _t("settings.hardware.tab_cut_drawer"))
        self.tabs.setTabText(2, _t("settings.hardware.tab_weighing_scale"))

        # Printers tab
        self._lbl_receipt_printer.setText(_t("settings.hardware.receipt_printer"))
        self._lbl_a4_printer.setText(_t("settings.hardware.a4_printer"))
        self.btn_refresh_printers.setText(_t("settings.hardware.btn_refresh_printers"))
        self._lbl_paper_width.setText(_t("settings.hardware.paper_width"))
        self._lbl_auto_print.setText(_t("settings.hardware.auto_print"))
        self.chk_auto_print.setText(_t("settings.hardware.chk_auto_print"))
        self.chk_auto_print.setToolTip(_t("settings.hardware.tooltip_auto_print"))
        self._lbl_copies.setText(_t("settings.hardware.copies"))
        self.btn_test_print.setText(_t("settings.hardware.btn_test_print"))
        self.btn_open_drawer.setText(_t("settings.hardware.btn_open_drawer"))

        # Cut & Drawer tab
        self._lbl_auto_cut.setText(_t("settings.hardware.auto_cut"))
        self.chk_auto_cut.setText(_t("settings.hardware.chk_auto_cut"))
        self.chk_auto_cut.setToolTip(_t("settings.hardware.tooltip_auto_cut"))

        self._lbl_cut_type.setText(_t("settings.hardware.cut_type"))
        # Re-populate cut type combo preserving selection
        current_cut_data = self.combo_cut_type.currentData()
        self.combo_cut_type.clear()
        self.combo_cut_type.addItem(_t("settings.hardware.cut_partial"), "partial")
        self.combo_cut_type.addItem(_t("settings.hardware.cut_full"), "full")
        if current_cut_data:
            idx = self.combo_cut_type.findData(current_cut_data)
            if idx >= 0:
                self.combo_cut_type.setCurrentIndex(idx)
        self.combo_cut_type.setToolTip(_t("settings.hardware.tooltip_cut_type"))

        self._lbl_feed_lines.setText(_t("settings.hardware.feed_lines"))
        self.spin_feed_lines.setToolTip(_t("settings.hardware.tooltip_feed_lines"))
        self._lbl_drawer_cash_only.setText(_t("settings.hardware.drawer_cash_only"))
        self.chk_drawer_cash_only.setText(_t("settings.hardware.chk_drawer_cash_only"))
        self.chk_drawer_cash_only.setToolTip(_t("settings.hardware.tooltip_drawer_cash_only"))

        # Scale tab
        self._lbl_barcode_prefix.setText(_t("settings.hardware.barcode_prefix"))
        self._lbl_decimal_places.setText(_t("settings.hardware.decimal_places"))

    def _refresh_printer_list(self) -> None:
        """Re-scan for connected printers without needing an app restart.

        Preserves each combo's current selection when it's still present
        in the rescanned list.
        """
        current_receipt = self.combo_receipt_printer.currentText()
        current_a4 = self.combo_a4_printer.currentText()

        available_printers = QPrinterInfo.availablePrinterNames() or [_t("settings.hardware.no_printers")]

        self.combo_receipt_printer.clear()
        self.combo_receipt_printer.addItems(available_printers)
        idx = self.combo_receipt_printer.findText(current_receipt)
        if idx >= 0:
            self.combo_receipt_printer.setCurrentIndex(idx)

        self.combo_a4_printer.clear()
        self.combo_a4_printer.addItems(available_printers)
        idx = self.combo_a4_printer.findText(current_a4)
        if idx >= 0:
            self.combo_a4_printer.setCurrentIndex(idx)

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
        idx = self.combo_cut_type.findData(cut_type)
        if idx >= 0:
            self.combo_cut_type.setCurrentIndex(idx)
        self.spin_feed_lines.setValue(settings.get("feed_lines_before_cut", 3))
        self.chk_drawer_cash_only.setChecked(settings.get("drawer_on_cash_only", True))

    def save(self) -> dict:
        prefix = self.input_scale_prefix.text()
        if len(prefix) != 2 or not prefix.isdigit():
            raise ValueError(_t("settings.hardware.scale_prefix_error"))

        return {
            "receipt_printer_name": self.combo_receipt_printer.currentText(),
            "a4_printer_name": self.combo_a4_printer.currentText(),
            "paper_width": self.combo_paper_width.currentText(),
            "auto_print_receipt": self.chk_auto_print.isChecked(),
            "receipt_copies": self.spin_copies.value(),
            "scale_barcode_prefix": prefix,
            "scale_decimal_places": self.spin_decimal_places.value(),
            "auto_cut_paper": self.chk_auto_cut.isChecked(),
            "cut_type": self.combo_cut_type.currentData() or "partial",
            "feed_lines_before_cut": self.spin_feed_lines.value(),
            "drawer_on_cash_only": self.chk_drawer_cash_only.isChecked(),
        }

    def _test_print(self) -> None:
        """Send a test print to the configured printer."""
        from cbpos.core.services.hardware_test_service import HardwareTestService

        success, message = HardwareTestService.test_receipt_printer()
        if success:
            QMessageBox.information(
                self,
                _t("settings.hardware.test_print_title"),
                message,
            )
        else:
            QMessageBox.warning(
                self,
                _t("settings.hardware.test_print_title"),
                message,
            )

    def _test_drawer(self) -> None:
        """Send a kick signal to the cash drawer."""
        from cbpos.core.services.hardware_test_service import HardwareTestService

        success, message = HardwareTestService.test_cash_drawer()
        if success:
            QMessageBox.information(
                self,
                _t("settings.hardware.cash_drawer_title"),
                message,
            )
        else:
            QMessageBox.warning(
                self,
                _t("settings.hardware.cash_drawer_title"),
                message,
            )


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

        self._page_title = QLabel()
        self._page_title.setProperty("class", "dialog-title")
        root.addWidget(self._page_title)

        self._page_subtitle = QLabel()
        self._page_subtitle.setProperty("class", "muted")
        root.addWidget(self._page_subtitle)

        # Copies/auto-print (Hardware) and document numbering format
        # (Documents) are just as much "receipt customization" as anything
        # on this page, but live on two other, unrelated-sounding sidebar
        # sections with no link back here -- someone tuning header/footer/
        # logo would feel done and never realize the rest is elsewhere (#331).
        self._lbl_receipt_cross_ref = QLabel()
        self._lbl_receipt_cross_ref.setObjectName("ReceiptCrossRefHint")
        self._lbl_receipt_cross_ref.setProperty("class", "muted")
        self._lbl_receipt_cross_ref.setWordWrap(True)
        root.addWidget(self._lbl_receipt_cross_ref)

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
        self._header_logo = self._make_section_header(_t("settings.receipt.section_logo"))
        vbox_content.addWidget(self._header_logo)

        logo_form = QFormLayout()
        self.configure_form_layout(logo_form)
        logo_form.setContentsMargins(0, 0, 0, 0)
        logo_form.setVerticalSpacing(10)
        logo_row = QHBoxLayout()
        self.input_logo_path = QLineEdit()
        self.input_logo_path.setReadOnly(True)
        self.btn_browse_logo = QPushButton()
        self.btn_browse_logo.clicked.connect(self.browse_logo)
        self.btn_clear_logo = QPushButton()
        self.btn_clear_logo.clicked.connect(self._clear_logo)
        logo_row.addWidget(self.input_logo_path, 1)
        logo_row.addWidget(self.btn_browse_logo)
        logo_row.addWidget(self.btn_clear_logo)
        self._lbl_logo = QLabel()
        logo_form.addRow(self._lbl_logo, logo_row)

        self._lbl_logo_hint = QLabel()
        self._lbl_logo_hint.setProperty("class", "muted")
        self._lbl_logo_hint.setWordWrap(True)
        logo_form.addRow("", self._lbl_logo_hint)
        vbox_content.addLayout(logo_form)

        # Section: Header & Footer
        self._header_hf = self._make_section_header(_t("settings.receipt.section_header_footer"))
        vbox_content.addWidget(self._header_hf)

        hf_form = QFormLayout()
        self.configure_form_layout(hf_form)
        hf_form.setContentsMargins(0, 0, 0, 0)
        hf_form.setVerticalSpacing(10)

        header_container = QWidget()
        header_container_layout = QVBoxLayout(header_container)
        header_container_layout.setContentsMargins(0, 0, 0, 0)
        header_container_layout.setSpacing(2)
        self.txt_header = QTextEdit()
        self.txt_header.setFixedHeight(64)
        self.txt_header.textChanged.connect(self._update_header_char_count)
        header_container_layout.addWidget(self.txt_header)
        self._lbl_header_char_count = QLabel()
        self._lbl_header_char_count.setObjectName("CharCountHint")
        header_container_layout.addWidget(self._lbl_header_char_count)
        self._lbl_header_text = QLabel()
        hf_form.addRow(self._lbl_header_text, header_container)

        footer_container = QWidget()
        footer_container_layout = QVBoxLayout(footer_container)
        footer_container_layout.setContentsMargins(0, 0, 0, 0)
        footer_container_layout.setSpacing(2)
        self.txt_footer = QTextEdit()
        self.txt_footer.setFixedHeight(64)
        self.txt_footer.textChanged.connect(self._update_footer_char_count)
        footer_container_layout.addWidget(self.txt_footer)
        self._lbl_footer_char_count = QLabel()
        self._lbl_footer_char_count.setObjectName("CharCountHint")
        footer_container_layout.addWidget(self._lbl_footer_char_count)
        self._lbl_footer_text = QLabel()
        hf_form.addRow(self._lbl_footer_text, footer_container)

        vbox_content.addLayout(hf_form)

        # Section: Receipt Language
        self._header_receipt_lang = self._make_section_header(_t("settings.receipt.section_receipt_language"))
        vbox_content.addWidget(self._header_receipt_lang)

        lang_form = QFormLayout()
        self.configure_form_layout(lang_form)
        lang_form.setContentsMargins(0, 0, 0, 0)
        lang_form.setVerticalSpacing(10)

        self.combo_receipt_lang = QComboBox()
        self.combo_receipt_lang.addItem(_t("settings.receipt.lang_same_as_ui"), "")
        self.combo_receipt_lang.addItem("English", "en")
        self.combo_receipt_lang.addItem("සිංහල (Sinhala)", "si")
        self.combo_receipt_lang.addItem("தமிழ் (Tamil)", "ta")
        self._lbl_receipt_lang = QLabel()
        lang_form.addRow(self._lbl_receipt_lang, self.combo_receipt_lang)

        self._lbl_receipt_lang_hint = QLabel()
        self._lbl_receipt_lang_hint.setProperty("class", "muted")
        self._lbl_receipt_lang_hint.setWordWrap(True)
        lang_form.addRow("", self._lbl_receipt_lang_hint)
        vbox_content.addLayout(lang_form)

        self.tabs.addTab(tab_content, "")

        # ===================== Tab 2: Display =====================
        tab_display, vbox_display = self._build_vbox_tab()

        # Section: Receipt Elements
        self._header_elements = self._make_section_header(_t("settings.receipt.section_receipt_elements"))
        vbox_display.addWidget(self._header_elements)

        elem_form = QFormLayout()
        self.configure_form_layout(elem_form)
        elem_form.setContentsMargins(0, 0, 0, 0)
        elem_form.setVerticalSpacing(10)

        self.chk_show_barcode = QCheckBox()
        self.chk_merge_items = QCheckBox()
        self.chk_show_tax = QCheckBox()

        self._lbl_show_barcode = QLabel()
        self._lbl_merge_items = QLabel()
        self._lbl_tax_breakdown = QLabel()

        elem_form.addRow(self._lbl_show_barcode, self.chk_show_barcode)
        elem_form.addRow(self._lbl_merge_items, self.chk_merge_items)
        elem_form.addRow(self._lbl_tax_breakdown, self.chk_show_tax)
        vbox_display.addLayout(elem_form)

        # Section: Staff & Terminal
        self._header_staff = self._make_section_header(_t("settings.receipt.section_staff_terminal"))
        vbox_display.addWidget(self._header_staff)

        staff_form = QFormLayout()
        self.configure_form_layout(staff_form)
        staff_form.setContentsMargins(0, 0, 0, 0)
        staff_form.setVerticalSpacing(10)

        self.chk_show_cashier = QCheckBox()
        self.chk_show_terminal = QCheckBox()

        self._lbl_cashier_name = QLabel()
        self._lbl_terminal_id = QLabel()

        staff_form.addRow(self._lbl_cashier_name, self.chk_show_cashier)
        staff_form.addRow(self._lbl_terminal_id, self.chk_show_terminal)
        vbox_display.addLayout(staff_form)

        self.tabs.addTab(tab_display, "")

        # --- Connect all inputs to live preview refresh ---
        self._connect_live_signals()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def retranslate_ui(self) -> None:
        self._page_title.setText(_t("settings.receipt.title"))
        self._page_subtitle.setText(_t("settings.receipt.subtitle"))
        self._lbl_receipt_cross_ref.setText(_t("settings.receipt.cross_ref_hint"))

        self.tabs.setTabText(0, _t("settings.receipt.tab_content"))
        self.tabs.setTabText(1, _t("settings.receipt.tab_display"))

        # Content tab
        self._lbl_logo.setText(_t("settings.receipt.logo_label"))
        self.input_logo_path.setPlaceholderText(_t("settings.receipt.logo_placeholder"))
        self.btn_browse_logo.setText(_t("settings.receipt.btn_browse_logo"))
        self.btn_clear_logo.setText(_t("settings.receipt.btn_clear_logo"))
        self._lbl_logo_hint.setText(_t("settings.receipt.logo_hint"))
        self._lbl_header_text.setText(_t("settings.receipt.header_text"))
        self.txt_header.setPlaceholderText(_t("settings.receipt.header_placeholder"))
        self._lbl_footer_text.setText(_t("settings.receipt.footer_text"))
        self.txt_footer.setPlaceholderText(_t("settings.receipt.footer_placeholder"))

        # Receipt language
        self._lbl_receipt_lang.setText(_t("settings.receipt.receipt_language"))
        self._lbl_receipt_lang_hint.setText(_t("settings.receipt.receipt_language_hint"))
        self.combo_receipt_lang.setItemText(0, _t("settings.receipt.lang_same_as_ui"))

        # Display tab
        self._lbl_show_barcode.setText(_t("settings.receipt.show_barcode"))
        self.chk_show_barcode.setText(_t("settings.receipt.chk_show_barcode"))
        self.chk_show_barcode.setToolTip(_t("settings.receipt.tooltip_show_barcode"))
        self._lbl_merge_items.setText(_t("settings.receipt.merge_items"))
        self.chk_merge_items.setText(_t("settings.receipt.chk_merge_items"))
        self.chk_merge_items.setToolTip(_t("settings.receipt.tooltip_merge_items"))
        self._lbl_tax_breakdown.setText(_t("settings.receipt.tax_breakdown"))
        self.chk_show_tax.setText(_t("settings.receipt.chk_show_tax"))
        self.chk_show_tax.setToolTip(_t("settings.receipt.tooltip_show_tax"))
        self._lbl_cashier_name.setText(_t("settings.receipt.cashier_name"))
        self.chk_show_cashier.setText(_t("settings.receipt.chk_show_cashier"))
        self.chk_show_cashier.setToolTip(_t("settings.receipt.tooltip_show_cashier"))
        self._lbl_terminal_id.setText(_t("settings.receipt.terminal_id"))
        self.chk_show_terminal.setText(_t("settings.receipt.chk_show_terminal"))
        self.chk_show_terminal.setToolTip(_t("settings.receipt.tooltip_show_terminal"))

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
        self.combo_receipt_lang.currentIndexChanged.connect(trigger)
        # Checkboxes
        self.chk_show_barcode.stateChanged.connect(trigger)
        self.chk_merge_items.stateChanged.connect(trigger)
        self.chk_show_tax.stateChanged.connect(trigger)
        self.chk_show_cashier.stateChanged.connect(trigger)
        self.chk_show_terminal.stateChanged.connect(trigger)

    def _schedule_refresh(self) -> None:
        """Restart the debounce timer -- preview refreshes after 300 ms of inactivity."""
        self._refresh_timer.start()

    def _refresh_preview(self) -> None:
        """Build receipt commands from current settings and update the preview."""
        from cbpos.core.services.config_service import ConfigService

        # paper_width lives on the Hardware tab, not this page's own fields,
        # so it can't come from self.save() -- read the real saved value
        # directly. Without this the preview always rendered at a hardcoded
        # 80mm regardless of what the shop actually configured (#325).
        self._preview.set_paper_width(ConfigService.get("paper_width"))

        commands = ReceiptBuilder.build_receipt(
            self._make_dummy_sale(),
            config_override=self.save(),
        )
        self._preview.set_commands(commands)
        self._update_header_char_count()
        self._update_footer_char_count()

    def _current_line_chars(self) -> int:
        """Characters-per-line budget for the shop's configured paper width.

        Mirrors BaseReceiptBuilder._append_header_block's own 58mm=32 /
        80mm=42 mapping, since that's the real value free-form header/footer
        text gets pre-wrapped to before printing.
        """
        from cbpos.core.services.config_service import ConfigService

        paper_width = ConfigService.get("paper_width")
        return 32 if paper_width == "58mm" else 42

    def _set_char_count_hint(self, label: QLabel, text: str) -> None:
        line_chars = self._current_line_chars()
        longest = max((len(line) for line in text.split("\n")), default=0)
        label.setText(_t("settings.receipt.char_count_hint", longest=longest, limit=line_chars))

    def _update_header_char_count(self) -> None:
        self._set_char_count_hint(self._lbl_header_char_count, self.txt_header.toPlainText())

    def _update_footer_char_count(self) -> None:
        self._set_char_count_hint(self._lbl_footer_char_count, self.txt_footer.toPlainText())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            _t("settings.receipt.select_logo_title"),
            "",
            _t("settings.receipt.select_logo_filter"),
        )
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
        from cbpos.core.services.config_service import ConfigService

        _d = ConfigService.DEFAULTS
        self.chk_show_barcode.setChecked(settings.get("show_barcode", _d["show_barcode"]))
        self.chk_merge_items.setChecked(settings.get("merge_items", _d["merge_items"]))
        self.chk_show_tax.setChecked(settings.get("show_tax_breakdown", _d["show_tax_breakdown"]))
        self.chk_show_cashier.setChecked(settings.get("show_cashier_on_receipt", _d["show_cashier_on_receipt"]))
        self.chk_show_terminal.setChecked(settings.get("show_terminal_on_receipt", _d["show_terminal_on_receipt"]))

        # Receipt language
        receipt_lang = settings.get("receipt_language", "")
        idx = self.combo_receipt_lang.findData(receipt_lang)
        if idx >= 0:
            self.combo_receipt_lang.setCurrentIndex(idx)

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
            "receipt_language": self.combo_receipt_lang.currentData() or "",
        }

    @staticmethod
    def _make_dummy_sale() -> Sale:
        """Create a realistic sample sale for the preview."""
        from datetime import datetime

        sale = Sale(
            id=42,
            document_number="INV-2026-00042",
            date=datetime.now(),
            total_amount=decimal.Decimal("1450.00"),
            tax_vat=decimal.Decimal("221.19"),
            tax_sscl=decimal.Decimal("36.25"),
            net_revenue=decimal.Decimal("1192.56"),
        )
        p1 = Product(name_en="Product A")
        p2 = Product(name_en="Product B")
        p3 = Product(name_en="Product C")
        sale.items = [
            SaleItem(
                product=p1,
                qty=decimal.Decimal("2"),
                unit_price=decimal.Decimal("150.00"),
                original_price=decimal.Decimal("150.00"),
                subtotal=decimal.Decimal("300.00"),
            ),
            SaleItem(
                product=p2,
                qty=decimal.Decimal("1"),
                unit_price=decimal.Decimal("400.00"),
                original_price=decimal.Decimal("450.00"),
                subtotal=decimal.Decimal("400.00"),
            ),
            SaleItem(
                product=p3,
                qty=decimal.Decimal("3"),
                unit_price=decimal.Decimal("250.00"),
                original_price=decimal.Decimal("250.00"),
                subtotal=decimal.Decimal("750.00"),
            ),
        ]
        sale.payments = [
            SalePayment(payment_method="Cash", amount=decimal.Decimal("1500.00")),
        ]
        return sale


class SystemPage(SettingsPage):
    """System settings: session security, feature toggles, and behavior."""

    def init_ui(self):
        _, self.tabs = self._create_page_layout("", "")

        # --- Tab 1: Security ---
        self._tab_sec, self._form_sec = self._build_form_tab()

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(0, 60)
        self.spin_timeout.setSuffix(" min")
        # Wider than the usual 200px house convention -- its special
        # value text ("Disabled (no auto-lock)") needs the extra room,
        # confirmed by rendering it: at 200px it clips to ")led (no
        # auto-lock)", reproducing the exact truncation #332 described.
        self.spin_timeout.setFixedWidth(260)
        self._lbl_timeout = QLabel()
        self._form_sec.addRow(self._lbl_timeout, self.spin_timeout)

        self.chk_void_reason = QCheckBox()
        self._lbl_void_reason = QLabel()
        self._form_sec.addRow(self._lbl_void_reason, self.chk_void_reason)

        self.spin_max_login = QSpinBox()
        self.spin_max_login.setRange(3, 20)
        self.spin_max_login.setFixedWidth(200)
        self._lbl_max_login = QLabel()
        self._form_sec.addRow(self._lbl_max_login, self.spin_max_login)

        self.spin_lockout = QSpinBox()
        self.spin_lockout.setRange(30, 3600)
        self.spin_lockout.setSuffix(" sec")
        self.spin_lockout.setFixedWidth(200)
        self._lbl_lockout = QLabel()
        self._form_sec.addRow(self._lbl_lockout, self.spin_lockout)

        self.tabs.addTab(self._tab_sec, "")

        # --- Tab 2: POS Behavior ---
        self._tab_pos, self._form_pos = self._build_form_tab()

        self.chk_quick_pay = QCheckBox()
        self._lbl_quick_pay = QLabel()
        self._form_pos.addRow(self._lbl_quick_pay, self.chk_quick_pay)

        self.chk_show_receipt_dialog = QCheckBox()
        self._lbl_receipt_dialog = QLabel()
        self._form_pos.addRow(self._lbl_receipt_dialog, self.chk_show_receipt_dialog)

        self.chk_auto_barcode_select = QCheckBox()
        self._lbl_auto_barcode = QLabel()
        self._form_pos.addRow(self._lbl_auto_barcode, self.chk_auto_barcode_select)

        self.chk_enable_sounds = QCheckBox()
        self._lbl_sounds = QLabel()
        self._form_pos.addRow(self._lbl_sounds, self.chk_enable_sounds)

        self.tabs.addTab(self._tab_pos, "")

        # --- Tab 3: Inventory ---
        self._tab_inv, self._form_inv = self._build_form_tab()

        self.chk_negative_stock = QCheckBox()
        self._lbl_negative_stock = QLabel()
        self._form_inv.addRow(self._lbl_negative_stock, self.chk_negative_stock)

        self.chk_auto_barcodes = QCheckBox()
        self._lbl_auto_barcodes = QLabel()
        self._form_inv.addRow(self._lbl_auto_barcodes, self.chk_auto_barcodes)

        self.chk_loyalty = QCheckBox()
        self._lbl_loyalty = QLabel()
        self._form_inv.addRow(self._lbl_loyalty, self.chk_loyalty)

        self.tabs.addTab(self._tab_inv, "")

        # --- Tab 4: Backup ---
        self._tab_backup, self._form_backup = self._build_form_tab()

        self.chk_auto_backup = QCheckBox()
        self._lbl_auto_backup = QLabel()
        self._form_backup.addRow(self._lbl_auto_backup, self.chk_auto_backup)

        self.spin_retention = QSpinBox()
        self.spin_retention.setRange(1, 50)
        self.spin_retention.setSuffix(" backups")
        self._lbl_retention = QLabel()
        self._form_backup.addRow(self._lbl_retention, self.spin_retention)

        backup_dir_layout = QHBoxLayout()
        self.input_backup_dir = QLineEdit()
        self.input_backup_dir.setReadOnly(True)
        backup_dir_layout.addWidget(self.input_backup_dir, 1)

        self.btn_browse_backup = QPushButton()
        self.btn_browse_backup.clicked.connect(self._browse_backup_dir)
        backup_dir_layout.addWidget(self.btn_browse_backup)

        self._lbl_backup_folder = QLabel()
        self._form_backup.addRow(self._lbl_backup_folder, backup_dir_layout)

        self.tabs.addTab(self._tab_backup, "")

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def retranslate_ui(self) -> None:
        self._page_title.setText(_t("settings.system.title"))
        self._page_subtitle.setText(_t("settings.system.subtitle"))

        self.tabs.setTabText(0, _t("settings.system.tab_security"))
        self.tabs.setTabText(1, _t("settings.system.tab_pos_behavior"))
        self.tabs.setTabText(2, _t("settings.system.tab_features"))
        self.tabs.setTabText(3, _t("settings.system.tab_backup"))

        # Security
        self._lbl_timeout.setText(_t("settings.system.inactivity_timeout"))
        self.spin_timeout.setSpecialValueText(_t("settings.system.timeout_disabled"))
        self.spin_timeout.setToolTip(_t("settings.system.tooltip_timeout"))
        self._lbl_void_reason.setText(_t("settings.system.require_void_reason"))
        self.chk_void_reason.setToolTip(_t("settings.system.tooltip_void_reason"))
        self._lbl_max_login.setText(_t("settings.system.max_login_attempts"))
        self.spin_max_login.setToolTip(_t("settings.system.tooltip_max_login"))
        self._lbl_lockout.setText(_t("settings.system.lockout_duration"))
        self.spin_lockout.setToolTip(_t("settings.system.tooltip_lockout"))

        # POS Behavior
        self._lbl_quick_pay.setText(_t("settings.system.quick_pay"))
        self.chk_quick_pay.setToolTip(_t("settings.system.tooltip_quick_pay"))
        self._lbl_receipt_dialog.setText(_t("settings.system.show_receipt_dialog"))
        self.chk_show_receipt_dialog.setToolTip(_t("settings.system.tooltip_receipt_dialog"))
        self._lbl_auto_barcode.setText(_t("settings.system.auto_barcode_select"))
        self.chk_auto_barcode_select.setToolTip(_t("settings.system.tooltip_auto_barcode"))
        self._lbl_sounds.setText(_t("settings.system.enable_sounds"))
        self.chk_enable_sounds.setToolTip(_t("settings.system.tooltip_sounds"))

        # Features
        self._lbl_negative_stock.setText(_t("settings.system.negative_stock"))
        self.chk_negative_stock.setToolTip(_t("settings.system.tooltip_negative_stock"))
        self._lbl_auto_barcodes.setText(_t("settings.system.auto_barcodes"))
        self.chk_auto_barcodes.setToolTip(_t("settings.system.tooltip_auto_barcodes"))
        self._lbl_loyalty.setText(_t("settings.system.loyalty_points"))
        self.chk_loyalty.setToolTip(_t("settings.system.tooltip_loyalty"))

        # Backup
        self._lbl_auto_backup.setText(_t("settings.system.auto_backup"))
        self.chk_auto_backup.setToolTip(_t("settings.system.tooltip_auto_backup"))
        self._lbl_retention.setText(_t("settings.system.backup_retention"))
        self.spin_retention.setToolTip(_t("settings.system.tooltip_retention"))
        self._lbl_backup_folder.setText(_t("settings.system.backup_folder"))
        self.input_backup_dir.setPlaceholderText(_t("settings.system.backup_folder_placeholder"))
        self.btn_browse_backup.setText(_t("settings.system.btn_browse_backup"))

    def _browse_backup_dir(self) -> None:
        current = self.input_backup_dir.text() or ""
        chosen = QFileDialog.getExistingDirectory(self, _t("settings.system.choose_backup_folder"), current)
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
        _, self.tabs = self._create_page_layout("", "")

        # --- Tab 1: Mode ---
        tab_mode, mode_layout = self._build_vbox_tab()

        # One-line framing so this tab doesn't read as a duplicate of
        # LAN Sync (#334) -- Mode/Server/Migration configure switching the
        # whole app to one *shared* PostgreSQL database; LAN Sync instead
        # keeps *separate* SQLite databases synced between terminals. Two
        # genuinely different multi-terminal strategies with nothing on
        # either tab explaining which is which.
        self.lbl_mode_explainer = QLabel()
        self.lbl_mode_explainer.setWordWrap(True)
        self.lbl_mode_explainer.setProperty("class", "muted")
        mode_layout.addWidget(self.lbl_mode_explainer)

        # Status Card
        self.status_card = QFrame()
        self.status_card.setObjectName("StatusCard")
        self.status_card.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout(self.status_card)
        status_layout.setContentsMargins(20, 20, 20, 20)
        status_layout.setSpacing(15)

        self.lbl_mode_icon = QLabel()
        self.lbl_mode_icon.setObjectName("StatusIcon")
        self.lbl_mode_icon.setPixmap(Icons.get("fa5s.desktop", ThemeService.get_accent_color()).pixmap(32, 32))

        status_text_layout = QVBoxLayout()
        self.lbl_status_title = QLabel()
        self.lbl_status_title.setObjectName("StatusTitle")
        self.lbl_status_subtitle = QLabel()
        self.lbl_status_subtitle.setObjectName("StatusSubtitle")
        status_text_layout.addWidget(self.lbl_status_title)
        status_text_layout.addWidget(self.lbl_status_subtitle)

        mode_selector_layout = QVBoxLayout()
        self.lbl_db_mode = QLabel()
        self.lbl_db_mode.setObjectName("StatusModeLabel")
        self.cmb_db_mode = QComboBox()
        self.cmb_db_mode.setObjectName("StatusModeSelector")
        self.cmb_db_mode.currentTextChanged.connect(self._on_mode_changed)
        mode_selector_layout.addWidget(self.lbl_db_mode)
        mode_selector_layout.addWidget(self.cmb_db_mode)

        status_layout.addWidget(self.lbl_mode_icon)
        status_layout.addLayout(status_text_layout, 1)
        status_layout.addLayout(mode_selector_layout)

        mode_layout.addWidget(self.status_card)

        self.lbl_warning = QLabel()
        self.lbl_warning.setObjectName("NetworkWarning")
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.setProperty("class", "warning-hint")
        self.lbl_warning.setVisible(False)
        mode_layout.addWidget(self.lbl_warning)

        self.tabs.addTab(tab_mode, "")

        # --- Tab 2: Server Configuration ---
        tab_server, server_layout = self._build_vbox_tab()

        self.config_card = QFrame()
        self.config_card.setObjectName("NetworkCard")
        self.config_card.setFrameShape(QFrame.Shape.StyledPanel)
        config_layout = QVBoxLayout(self.config_card)
        config_layout.setContentsMargins(25, 25, 25, 25)
        config_layout.setSpacing(18)

        self.lbl_config_title = QLabel()
        self.lbl_config_title.setObjectName("CardTitle")
        config_layout.addWidget(self.lbl_config_title)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "127.0.0.1"
        self._local_ip = local_ip

        self.lbl_local_ip = QLabel()
        self.lbl_local_ip.setObjectName("IPHelper")
        config_layout.addWidget(self.lbl_local_ip)

        grid_layout = QGridLayout()
        grid_layout.setVerticalSpacing(12)
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)

        self.lbl_host = QLabel()
        self.lbl_host.setObjectName("FormLabel")
        self.input_host = QLineEdit()
        self.input_host.setObjectName("InputNetwork")
        grid_layout.addWidget(
            self.lbl_host,
            0,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_host, 0, 1)

        self.lbl_port = QLabel()
        self.lbl_port.setObjectName("FormLabel")
        self.input_port = QSpinBox()
        self.input_port.setObjectName("InputNetwork")
        self.input_port.setFixedHeight(38)
        self.input_port.setRange(1, 65535)
        self.input_port.setValue(5432)
        grid_layout.addWidget(
            self.lbl_port,
            1,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_port, 1, 1)

        self.lbl_dbname = QLabel()
        self.lbl_dbname.setObjectName("FormLabel")
        self.input_dbname = QLineEdit()
        self.input_dbname.setObjectName("InputNetwork")
        grid_layout.addWidget(
            self.lbl_dbname,
            2,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_dbname, 2, 1)

        self.lbl_user = QLabel()
        self.lbl_user.setObjectName("FormLabel")
        self.input_user = QLineEdit()
        self.input_user.setObjectName("InputNetwork")
        grid_layout.addWidget(
            self.lbl_user,
            3,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_user, 3, 1)

        self.lbl_password = QLabel()
        self.lbl_password.setObjectName("FormLabel")
        self.input_password = QLineEdit()
        self.input_password.setObjectName("InputNetwork")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        grid_layout.addWidget(
            self.lbl_password,
            4,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_password, 4, 1)

        config_layout.addLayout(grid_layout)

        test_btn_layout = QHBoxLayout()
        self.btn_test = QPushButton()
        self.btn_test.setObjectName("BtnTestNetwork")
        self.btn_test.clicked.connect(self._test_connection)
        self.lbl_test_status = QLabel("")
        self.lbl_test_status.setObjectName("TestStatus")
        test_btn_layout.addWidget(self.btn_test)
        test_btn_layout.addWidget(self.lbl_test_status, 1)
        config_layout.addLayout(test_btn_layout)

        server_layout.addWidget(self.config_card)

        self.tabs.addTab(tab_server, "")

        # --- Tab 3: Migration ---
        tab_migrate, migrate_layout = self._build_vbox_tab()

        self.migration_card = QFrame()
        self.migration_card.setObjectName("MigrationCard")
        self.migration_card.setFrameShape(QFrame.Shape.StyledPanel)
        migration_layout = QVBoxLayout(self.migration_card)
        migration_layout.setContentsMargins(25, 25, 25, 25)
        migration_layout.setSpacing(18)

        self.lbl_migration_title = QLabel()
        self.lbl_migration_title.setObjectName("CardTitle")
        migration_layout.addWidget(self.lbl_migration_title)

        self.lbl_migration_info = QLabel()
        self.lbl_migration_info.setWordWrap(True)
        self.lbl_migration_info.setObjectName("MigrationInfo")
        migration_layout.addWidget(self.lbl_migration_info)

        self.btn_migrate = QPushButton()
        self.btn_migrate.setObjectName("BtnMigrate")
        self.btn_migrate.setEnabled(False)
        self.btn_migrate.clicked.connect(self._migrate_data)
        migration_layout.addWidget(self.btn_migrate)

        migrate_layout.addWidget(self.migration_card)

        self.tabs.addTab(tab_migrate, "")

        # --- Tab 4: LAN Sync (Multi-Terminal) ---
        tab_sync, sync_layout = self._build_vbox_tab()

        self.sync_card = QFrame()
        self.sync_card.setObjectName("NetworkCard")
        self.sync_card.setFrameShape(QFrame.Shape.StyledPanel)
        sync_card_layout = QVBoxLayout(self.sync_card)
        sync_card_layout.setContentsMargins(25, 25, 25, 25)
        sync_card_layout.setSpacing(18)

        self.lbl_sync_title = QLabel()
        self.lbl_sync_title.setObjectName("CardTitle")
        sync_card_layout.addWidget(self.lbl_sync_title)

        self.lbl_sync_desc = QLabel()
        self.lbl_sync_desc.setWordWrap(True)
        self.lbl_sync_desc.setObjectName("MigrationInfo")
        sync_card_layout.addWidget(self.lbl_sync_desc)

        sync_grid = QGridLayout()
        sync_grid.setVerticalSpacing(12)
        sync_grid.setHorizontalSpacing(10)
        sync_grid.setColumnStretch(0, 0)
        sync_grid.setColumnStretch(1, 1)

        # Terminal Mode selector
        self.lbl_terminal_mode = QLabel()
        self.lbl_terminal_mode.setObjectName("FormLabel")
        self.cmb_terminal_mode = QComboBox()
        self.cmb_terminal_mode.addItem("", "standalone")
        self.cmb_terminal_mode.addItem("", "main")
        self.cmb_terminal_mode.addItem("", "terminal")
        self.cmb_terminal_mode.currentIndexChanged.connect(self._on_terminal_mode_changed)
        sync_grid.addWidget(self.lbl_terminal_mode, 0, 0, Qt.AlignmentFlag.AlignLeft)
        sync_grid.addWidget(self.cmb_terminal_mode, 0, 1)

        # Terminal ID
        self.lbl_sync_terminal_id = QLabel()
        self.lbl_sync_terminal_id.setObjectName("FormLabel")
        self.input_terminal_id = QLineEdit()
        self.input_terminal_id.setObjectName("InputNetwork")
        sync_grid.addWidget(self.lbl_sync_terminal_id, 1, 0, Qt.AlignmentFlag.AlignLeft)
        sync_grid.addWidget(self.input_terminal_id, 1, 1)

        # Sync server port (Main PC mode)
        self.lbl_sync_port = QLabel()
        self.lbl_sync_port.setObjectName("FormLabel")
        self.spin_sync_port = QSpinBox()
        self.spin_sync_port.setObjectName("InputNetwork")
        self.spin_sync_port.setFixedHeight(38)
        self.spin_sync_port.setRange(1024, 65535)
        self.spin_sync_port.setValue(5555)
        sync_grid.addWidget(self.lbl_sync_port, 2, 0, Qt.AlignmentFlag.AlignLeft)
        sync_grid.addWidget(self.spin_sync_port, 2, 1)

        # Main PC address (Terminal mode)
        self.lbl_main_pc_addr = QLabel()
        self.lbl_main_pc_addr.setObjectName("FormLabel")
        self.input_main_pc_addr = QLineEdit()
        self.input_main_pc_addr.setObjectName("InputNetwork")
        sync_grid.addWidget(self.lbl_main_pc_addr, 3, 0, Qt.AlignmentFlag.AlignLeft)
        sync_grid.addWidget(self.input_main_pc_addr, 3, 1)

        # Sync interval
        self.lbl_sync_interval = QLabel()
        self.lbl_sync_interval.setObjectName("FormLabel")
        self.spin_sync_interval = QSpinBox()
        self.spin_sync_interval.setObjectName("InputNetwork")
        self.spin_sync_interval.setFixedHeight(38)
        self.spin_sync_interval.setRange(1, 60)
        self.spin_sync_interval.setValue(3)
        sync_grid.addWidget(self.lbl_sync_interval, 4, 0, Qt.AlignmentFlag.AlignLeft)
        sync_grid.addWidget(self.spin_sync_interval, 4, 1)

        # Shared secret — required on both Main PC and every Terminal
        self.lbl_sync_secret = QLabel()
        self.lbl_sync_secret.setObjectName("FormLabel")
        self.input_sync_secret = QLineEdit()
        self.input_sync_secret.setObjectName("InputNetwork")
        self.input_sync_secret.setEchoMode(QLineEdit.EchoMode.Password)
        sync_grid.addWidget(self.lbl_sync_secret, 5, 0, Qt.AlignmentFlag.AlignLeft)
        sync_grid.addWidget(self.input_sync_secret, 5, 1)

        sync_card_layout.addLayout(sync_grid)

        # Test LAN Sync Connection button
        sync_test_layout = QHBoxLayout()
        self.btn_test_sync = QPushButton()
        self.btn_test_sync.setObjectName("BtnTestNetwork")
        self.btn_test_sync.clicked.connect(self._test_sync_connection)
        self.lbl_sync_test_status = QLabel("")
        self.lbl_sync_test_status.setObjectName("TestStatus")
        sync_test_layout.addWidget(self.btn_test_sync)
        sync_test_layout.addWidget(self.lbl_sync_test_status, 1)
        sync_card_layout.addLayout(sync_test_layout)

        # Forget Trusted Main PC — recovery path after intentionally
        # replacing the Main PC (see SyncClient._check_main_identity)
        self.btn_forget_main = QPushButton()
        self.btn_forget_main.setObjectName("BtnTestNetwork")
        self.btn_forget_main.clicked.connect(self._forget_trusted_main_pc)
        sync_card_layout.addWidget(self.btn_forget_main)

        # Server address display (Main PC mode)
        self.lbl_server_address = QLabel("")
        self.lbl_server_address.setObjectName("IPHelper")
        self.lbl_server_address.setWordWrap(True)
        sync_card_layout.addWidget(self.lbl_server_address)

        sync_layout.addWidget(self.sync_card)
        self.tabs.addTab(tab_sync, "")

        self._on_mode_changed("Standalone")
        self._on_terminal_mode_changed(0)

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

        # The first style polish on show() re-expands these spinboxes past
        # their #InputNetwork height (a pre-existing QSS specificity clash
        # with "QWidget#SettingsContent QSpinBox"), so pin the height again
        # one event-loop tick after the initial polish has already happened.
        from PyQt6.QtCore import QTimer

        def _fix_spinbox_heights():
            for spinbox in (self.input_port, self.spin_sync_port, self.spin_sync_interval):
                spinbox.setFixedHeight(38)

        QTimer.singleShot(0, _fix_spinbox_heights)

    def retranslate_ui(self) -> None:
        self._page_title.setText(_t("settings.network.title"))
        self._page_subtitle.setText(_t("settings.network.subtitle"))

        self.tabs.setTabText(0, _t("settings.network.tab_mode"))
        self.tabs.setTabText(1, _t("settings.network.tab_server"))
        self.tabs.setTabText(2, _t("settings.network.tab_migration"))
        self.tabs.setTabText(3, _t("settings.network.tab_lan_sync"))

        # Mode tab
        self.lbl_mode_explainer.setText(_t("settings.network.mode_explainer"))
        self.lbl_db_mode.setText(_t("settings.network.database_mode"))
        self.cmb_db_mode.setToolTip(_t("settings.network.tooltip_db_mode"))

        # Re-populate db mode combo preserving selection
        current_data = self.cmb_db_mode.currentData()
        self.cmb_db_mode.blockSignals(True)
        self.cmb_db_mode.clear()
        self.cmb_db_mode.addItem(_t("settings.network.mode_standalone"), "Standalone")
        self.cmb_db_mode.addItem(_t("settings.network.mode_network"), "Network")
        if current_data:
            idx = self.cmb_db_mode.findData(current_data)
            if idx >= 0:
                self.cmb_db_mode.setCurrentIndex(idx)
        self.cmb_db_mode.blockSignals(False)

        # Update status text based on current mode
        is_network = self.cmb_db_mode.currentData() == "Network"
        if is_network:
            self.lbl_status_title.setText(_t("settings.network.network_mode_title"))
            self.lbl_status_subtitle.setText(_t("settings.network.network_mode_subtitle"))
        else:
            self.lbl_status_title.setText(_t("settings.network.single_mode_title"))
            self.lbl_status_subtitle.setText(_t("settings.network.single_mode_subtitle"))

        self.lbl_warning.setText(_t("settings.network.mode_change_warning"))

        # Server tab
        self.lbl_config_title.setText(_t("settings.network.server_config_title"))
        self.lbl_local_ip.setText(_t("settings.network.local_ip").format(ip=self._local_ip))
        self.lbl_host.setText(_t("settings.network.host_ip"))
        self.input_host.setPlaceholderText(_t("settings.network.host_placeholder"))
        self.input_host.setToolTip(_t("settings.network.tooltip_host"))
        self.lbl_port.setText(_t("settings.network.port"))
        self.input_port.setToolTip(_t("settings.network.tooltip_port"))
        self.lbl_dbname.setText(_t("settings.network.database_name"))
        self.input_dbname.setPlaceholderText(_t("settings.network.database_name_placeholder"))
        self.input_dbname.setToolTip(_t("settings.network.tooltip_dbname"))
        self.lbl_user.setText(_t("settings.network.username"))
        self.input_user.setPlaceholderText(_t("settings.network.username_placeholder"))
        self.input_user.setToolTip(_t("settings.network.tooltip_user"))
        self.lbl_password.setText(_t("settings.network.password"))
        self.input_password.setPlaceholderText(_t("settings.network.password_placeholder"))
        self.input_password.setToolTip(_t("settings.network.tooltip_password"))
        self.btn_test.setText(_t("settings.network.btn_test_connection"))
        self.btn_test.setToolTip(_t("settings.network.tooltip_test_connection"))

        # Migration tab
        self.lbl_migration_title.setText(_t("settings.network.migration_title"))
        self.lbl_migration_info.setText(_t("settings.network.migration_info"))
        self.btn_migrate.setText(_t("settings.network.btn_upload"))
        self.btn_migrate.setToolTip(_t("settings.network.tooltip_migrate"))

        # LAN Sync tab
        self.lbl_sync_title.setText(_t("settings.network.sync_title"))
        self.lbl_sync_desc.setText(_t("settings.network.sync_desc"))

        self.lbl_terminal_mode.setText(_t("settings.network.terminal_mode"))
        current_terminal_mode = self.cmb_terminal_mode.currentData()
        self.cmb_terminal_mode.blockSignals(True)
        self.cmb_terminal_mode.clear()
        self.cmb_terminal_mode.addItem(_t("settings.network.terminal_mode_standalone"), "standalone")
        self.cmb_terminal_mode.addItem(_t("settings.network.terminal_mode_main"), "main")
        self.cmb_terminal_mode.addItem(_t("settings.network.terminal_mode_terminal"), "terminal")
        if current_terminal_mode:
            tm_idx = self.cmb_terminal_mode.findData(current_terminal_mode)
            if tm_idx >= 0:
                self.cmb_terminal_mode.setCurrentIndex(tm_idx)
        self.cmb_terminal_mode.blockSignals(False)
        self.cmb_terminal_mode.setToolTip(_t("settings.network.tooltip_terminal_mode"))

        self.lbl_sync_terminal_id.setText(_t("settings.network.sync_terminal_id"))
        self.input_terminal_id.setPlaceholderText(_t("settings.network.sync_terminal_id_placeholder"))
        self.input_terminal_id.setToolTip(_t("settings.network.tooltip_terminal_id"))

        self.lbl_sync_port.setText(_t("settings.network.sync_port"))
        self.spin_sync_port.setToolTip(_t("settings.network.tooltip_sync_port"))

        self.lbl_main_pc_addr.setText(_t("settings.network.main_pc_address"))
        self.input_main_pc_addr.setPlaceholderText(_t("settings.network.main_pc_address_placeholder"))
        self.input_main_pc_addr.setToolTip(_t("settings.network.tooltip_main_pc_address"))

        self.lbl_sync_interval.setText(_t("settings.network.sync_interval"))
        self.spin_sync_interval.setSuffix(_t("settings.network.sync_interval_suffix"))
        self.spin_sync_interval.setToolTip(_t("settings.network.tooltip_sync_interval"))

        self.lbl_sync_secret.setText(_t("settings.network.sync_secret"))
        self.input_sync_secret.setPlaceholderText(_t("settings.network.sync_secret_placeholder"))
        self.input_sync_secret.setToolTip(_t("settings.network.tooltip_sync_secret"))

        self.btn_test_sync.setText(_t("settings.network.btn_test_sync"))
        self.btn_test_sync.setToolTip(_t("settings.network.tooltip_test_sync"))

        self.btn_forget_main.setText(_t("settings.network.btn_forget_main"))
        self.btn_forget_main.setToolTip(_t("settings.network.tooltip_forget_main"))

    def load(self, settings: dict):
        db_mode = settings.get("db_mode", "standalone")
        mode_data = "Standalone" if db_mode == "standalone" else "Network"
        idx = self.cmb_db_mode.findData(mode_data)
        if idx >= 0:
            self.cmb_db_mode.setCurrentIndex(idx)
        self.input_host.setText(settings.get("network_db_host", "localhost"))
        self.input_port.setValue(settings.get("network_db_port", 5432))
        self.input_dbname.setText(settings.get("network_db_name", "cbpos"))
        self.input_user.setText(settings.get("network_db_user", "postgres"))
        self.input_password.setText(settings.get("network_db_password", ""))
        self._original_mode = self.cmb_db_mode.currentData()
        self._on_mode_changed(self.cmb_db_mode.currentData() or "Standalone")

        # LAN Sync settings
        terminal_mode = settings.get("terminal_mode", "standalone")
        tm_idx = self.cmb_terminal_mode.findData(terminal_mode)
        if tm_idx >= 0:
            self.cmb_terminal_mode.setCurrentIndex(tm_idx)
        self.input_terminal_id.setText(settings.get("terminal_id", "TERM-01"))
        self.spin_sync_port.setValue(int(settings.get("sync_server_port", 5555)))
        self.input_main_pc_addr.setText(settings.get("main_pc_address", ""))
        self.spin_sync_interval.setValue(int(settings.get("sync_interval_seconds", 3)))
        self.input_sync_secret.setText(settings.get("sync_shared_secret", ""))

    def save(self) -> dict:
        mode_data = self.cmb_db_mode.currentData() or "Standalone"
        db_mode = "standalone" if mode_data == "Standalone" else "network"
        return {
            "db_mode": db_mode,
            "network_db_host": self.input_host.text().strip(),
            "network_db_port": self.input_port.value(),
            "network_db_name": self.input_dbname.text().strip(),
            "network_db_user": self.input_user.text().strip(),
            "network_db_password": self.input_password.text(),
            # LAN Sync
            "terminal_mode": self.cmb_terminal_mode.currentData() or "standalone",
            "terminal_id": self.input_terminal_id.text().strip() or "TERM-01",
            "sync_server_port": self.spin_sync_port.value(),
            "main_pc_address": self.input_main_pc_addr.text().strip(),
            "sync_interval_seconds": self.spin_sync_interval.value(),
            "sync_shared_secret": self.input_sync_secret.text(),
        }

    def _on_mode_changed(self, mode: str):
        is_network = mode == "Network"
        icon_color = ThemeService.get_accent_color()
        if is_network:
            self.lbl_mode_icon.setPixmap(Icons.get("fa5s.network-wired", icon_color).pixmap(32, 32))
            self.lbl_status_title.setText(_t("settings.network.network_mode_title"))
            self.lbl_status_subtitle.setText(_t("settings.network.network_mode_subtitle"))
        else:
            self.lbl_mode_icon.setPixmap(Icons.get("fa5s.desktop", icon_color).pixmap(32, 32))
            self.lbl_status_title.setText(_t("settings.network.single_mode_title"))
            self.lbl_status_subtitle.setText(_t("settings.network.single_mode_subtitle"))
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
                _t("common.validation_error"),
                _t("settings.network.validation_required_fields"),
            )
            return

        self.lbl_test_status.setText(_t("settings.network.testing"))
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
            self.lbl_test_status.setText(_t("settings.network.connected"))
            self.btn_migrate.setEnabled(True)
            QMessageBox.information(
                self,
                _t("settings.network.connection_test_title"),
                _t("settings.network.connection_success_message").format(message=message),
            )
        else:
            self.connection_tested = False
            self.lbl_test_status.setText(_t("settings.network.failed"))
            self.btn_migrate.setEnabled(False)
            QMessageBox.critical(
                self,
                _t("settings.network.connection_test_title"),
                message,
            )

    def _migrate_data(self):
        from cbpos.core.services.migration_service import MigrationService

        cfg = self._get_network_config()
        if not all([cfg["host"], cfg["dbname"], cfg["user"]]):
            QMessageBox.warning(
                self,
                _t("common.validation_error"),
                _t("settings.network.validation_before_migrate"),
            )
            return

        confirm = QMessageBox.question(
            self,
            _t("settings.network.confirm_migration_title"),
            _t("settings.network.confirm_migration_message").format(
                host=cfg["host"],
                port=cfg["port"],
                dbname=cfg["dbname"],
            ),
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

        progress = QProgressDialog(
            _t("settings.network.migrating_progress"),
            None,
            0,
            0,
            self,
        )
        progress.setWindowTitle(_t("settings.network.migration_progress_title"))
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
                    _t("settings.network.migration_success_title"),
                    _t("settings.network.migration_success_message").format(message=message),
                )
            else:
                QMessageBox.critical(
                    self,
                    _t("settings.network.migration_failed_title"),
                    _t("settings.network.migration_failed_message").format(message=message),
                )
        except Exception as e:
            progress.close()
            import logging

            logging.getLogger(__name__).exception("Data migration failed: %s", e)
            QMessageBox.critical(
                self,
                _t("settings.network.migration_error_title"),
                _t("settings.network.migration_error_message"),
            )

    def _on_terminal_mode_changed(self, index: int) -> None:
        """Show/hide fields based on selected terminal mode."""
        mode = self.cmb_terminal_mode.currentData() or "standalone"

        is_main = mode == "main"
        is_terminal = mode == "terminal"
        is_sync = is_main or is_terminal

        # Terminal ID always visible when sync enabled
        self.lbl_sync_terminal_id.setVisible(is_sync)
        self.input_terminal_id.setVisible(is_sync)

        # Sync port only for Main PC
        self.lbl_sync_port.setVisible(is_main)
        self.spin_sync_port.setVisible(is_main)

        # Main PC address only for Terminal
        self.lbl_main_pc_addr.setVisible(is_terminal)
        self.input_main_pc_addr.setVisible(is_terminal)

        # Sync interval for both
        self.lbl_sync_interval.setVisible(is_sync)
        self.spin_sync_interval.setVisible(is_sync)

        # Shared secret for both
        self.lbl_sync_secret.setVisible(is_sync)
        self.input_sync_secret.setVisible(is_sync)

        # Test button only for Terminal mode
        self.btn_test_sync.setVisible(is_terminal)
        self.lbl_sync_test_status.setVisible(is_terminal)
        self.btn_forget_main.setVisible(is_terminal)

        # Server address display for Main PC
        if is_main:
            try:
                import socket

                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.1)
                s.connect(("10.255.255.255", 1))
                ip = s.getsockname()[0]
                s.close()
            except Exception:
                ip = "127.0.0.1"
            port = self.spin_sync_port.value()
            self.lbl_server_address.setText(_t("settings.network.sync_server_address_display", ip=ip, port=port))
            self.lbl_server_address.setVisible(True)
        else:
            self.lbl_server_address.setVisible(False)

    def _test_sync_connection(self) -> None:
        """Test the connection to the Main PC sync server."""
        address = self.input_main_pc_addr.text().strip()
        if not address:
            QMessageBox.warning(
                self,
                _t("settings.network.sync_validation_title"),
                _t("settings.network.sync_validation_message"),
            )
            return

        if address.startswith("http://"):
            address = "https://" + address[len("http://") :]
        elif not address.startswith("https://"):
            address = f"https://{address}"

        self.lbl_sync_test_status.setText(_t("settings.network.sync_test_testing"))
        self.btn_test_sync.setEnabled(False)
        QApplication.processEvents()

        try:
            import json
            import urllib.request
            import urllib.error

            from cbpos.infrastructure.sync_tls import build_client_ssl_context

            url = f"{address}/sync/heartbeat"
            req = urllib.request.Request(url, method="GET", headers={"X-Sync-Token": self.input_sync_secret.text()})
            with urllib.request.urlopen(req, timeout=5, context=build_client_ssl_context()) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("status") == "ok":
                version = data.get("protocol_version", "?")
                terminals = data.get("terminals_connected", 0)
                self.lbl_sync_test_status.setText(_t("settings.network.sync_test_connected"))
                QMessageBox.information(
                    self,
                    _t("settings.network.sync_success_title"),
                    _t("settings.network.sync_success_message", version=version, terminals=terminals),
                )
            else:
                self.lbl_sync_test_status.setText(_t("settings.network.sync_test_unexpected"))

        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.lbl_sync_test_status.setText(_t("settings.network.sync_test_unauthorized"))
                QMessageBox.critical(
                    self,
                    _t("settings.network.sync_failed_title"),
                    _t("settings.network.sync_failed_secret_message"),
                )
            else:
                self.lbl_sync_test_status.setText(_t("settings.network.sync_test_failed"))
                QMessageBox.critical(
                    self,
                    _t("settings.network.sync_failed_title"),
                    _t("settings.network.sync_failed_message", address=address, error=e),
                )
        except urllib.error.URLError as e:
            self.lbl_sync_test_status.setText(_t("settings.network.sync_test_failed"))
            QMessageBox.critical(
                self,
                _t("settings.network.sync_failed_title"),
                _t("settings.network.sync_failed_message", address=address, error=e),
            )
        except Exception as e:
            self.lbl_sync_test_status.setText(_t("settings.network.sync_test_error"))
            QMessageBox.critical(self, _t("settings.network.sync_error_title"), str(e))
        finally:
            self.btn_test_sync.setEnabled(True)

    def _forget_trusted_main_pc(self) -> None:
        """Clear the pinned Main PC identity so this Terminal will trust
        whichever machine answers at the configured address next time.

        Needed after intentionally replacing the Main PC — otherwise
        SyncClient refuses to sync against a different instance_id than
        the one it first connected to.
        """
        from cbpos.core.services.config_service import ConfigService

        reply = QMessageBox.question(
            self,
            _t("settings.network.btn_forget_main"),
            _t("settings.network.sync_forget_main_confirm_message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ConfigService.set("sync_known_main_instance_id", "")
            QMessageBox.information(
                self,
                _t("settings.network.btn_forget_main"),
                _t("settings.network.sync_forget_main_done_message"),
            )
