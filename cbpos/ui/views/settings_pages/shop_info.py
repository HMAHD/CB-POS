"""Shop information settings page (business, banking, email, appearance)."""

from PyQt6.QtCore import Qt, QTime
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTimeEdit,
)

from cbpos.core.services.language_service import LanguageService
from cbpos.core.utils.formatters import DEFAULT_CURRENCY_SYMBOL
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.dialogs.guide_dialog import GuideDialog
from cbpos.ui.views.settings_pages.base import SettingsPage
from cbpos.ui.widgets.help_icon_button import HelpIconButton


class ShopInfoPage(SettingsPage):
    """Consolidated: General + Payment banking + Automation email settings."""

    TAB_BUSINESS = 0
    TAB_BANKING = 1
    TAB_EMAIL = 2
    TAB_APPEARANCE = 3

    def init_ui(self):
        """Build the Business, Banking, Email and Appearance tabs."""
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

        self.btn_help = HelpIconButton(on_click=self._show_smtp_guide)
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
        self.lbl_restart.setWordWrap(True)
        self._form_appear.addRow("", self.lbl_restart)

        self.tabs.addTab(self._tab_appear, "")

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def retranslate_ui(self) -> None:
        """Update all widget text and tab labels from the translation system."""
        self._page_title.setText(_t("settings.shop_info.title"))
        self.btn_reset_defaults.setText(_t("settings.btn_reset_defaults"))
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
        self.equalize_form_labels()

    def _prefill_gmail(self):
        """Pre-fill SMTP fields with Gmail defaults."""
        self.input_smtp_host.setText("smtp.gmail.com")
        self.input_smtp_port.setText("587")
        if not self.input_smtp_user.text():
            self.input_smtp_user.setFocus()

    def _show_smtp_guide(self):
        """Show a clean step-by-step SMTP setup guide dialog."""
        guide_steps = [
            ("settings.shop_info.guide_step1_title", "settings.shop_info.guide_step1_detail"),
            ("settings.shop_info.guide_step2_title", "settings.shop_info.guide_step2_detail"),
            ("settings.shop_info.guide_step3_title", "settings.shop_info.guide_step3_detail"),
            ("settings.shop_info.guide_step4_title", "settings.shop_info.guide_step4_detail"),
        ]
        dlg = GuideDialog(
            title_key="settings.shop_info.email_guide_title",
            heading_key="settings.shop_info.email_guide_heading",
            steps=guide_steps,
            note_key="settings.shop_info.guide_important_note",
            close_key="settings.shop_info.guide_btn_close",
            parent=self,
        )
        dlg.exec()

    def load(self, settings: dict):
        """Populate business, banking, email and appearance fields from the settings dict."""
        self.input_shop_name.setText(settings.get("shop_name", ""))
        self.input_address.setText(settings.get("shop_address", ""))
        self.input_phone.setText(settings.get("shop_phone", ""))
        self.input_vat.setText(settings.get("vat_number", ""))
        self.input_tax_id.setText(settings.get("company_tax_id", ""))
        self.input_currency.setText(settings.get("currency_symbol") or DEFAULT_CURRENCY_SYMBOL)

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
        """Return business, banking, email and appearance fields as a settings dict."""
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


__all__ = ["ShopInfoPage"]
