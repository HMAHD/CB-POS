"""Sales and tax configuration settings page."""

from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSpinBox,
)

from cbpos.core.utils.formatters import DEFAULT_CURRENCY_SYMBOL, get_currency_symbol
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.dialogs.guide_dialog import GuideDialog
from cbpos.ui.views.settings_pages.base import SettingsPage
from cbpos.ui.widgets.help_icon_button import HelpIconButton


class SalesTaxPage(SettingsPage):
    """Sales search mode + Tax configuration."""

    def init_ui(self):
        """Build the Sales and Tax tabs."""
        _, self.tabs = self._create_page_layout("", "")

        # --- Tab 1: Sales ---
        self._tab_sales, self._form_sales = self._build_form_tab()

        self.combo_search_mode = QComboBox()
        self.combo_search_mode.setFixedWidth(200)
        self._lbl_search_mode = QLabel()
        self._form_sales.addRow(self._lbl_search_mode, self.combo_search_mode)

        self.spin_max_discount = QDoubleSpinBox()
        self.spin_max_discount.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_max_discount.setRange(0, 100)
        self.spin_max_discount.setDecimals(1)
        self.spin_max_discount.setSuffix("%")
        self.spin_max_discount.setFixedWidth(200)
        self._lbl_max_discount = QLabel()
        self._form_sales.addRow(self._lbl_max_discount, self.spin_max_discount)

        self.spin_loyalty_ratio = QSpinBox()
        self.spin_loyalty_ratio.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_loyalty_ratio.setRange(1, 10000)
        self.spin_loyalty_ratio.setFixedWidth(200)
        self._lbl_loyalty_ratio = QLabel()
        # Retained for legacy test compatibility (#754); not added to layout

        self.spin_default_credit = QSpinBox()
        self.spin_default_credit.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_default_credit.setRange(0, 1000000)
        self.spin_default_credit.setFixedWidth(200)
        self._lbl_default_credit = QLabel()
        self._form_sales.addRow(self._lbl_default_credit, self.spin_default_credit)

        self.chk_promo_stacking = QCheckBox()
        self._lbl_promo_stacking_hint = QLabel()
        self._lbl_promo_stacking_hint.setProperty("class", "muted")
        self._lbl_promo_stacking_hint.setWordWrap(True)
        self._form_sales.addRow(self.chk_promo_stacking)
        self._form_sales.addRow(self._lbl_promo_stacking_hint)

        self.tabs.addTab(self._tab_sales, "")

        # --- Tab 2: Tax ---
        self._tab_tax, self._form_tax = self._build_form_tab()

        self.chk_vat_registered = QCheckBox()
        self.chk_vat_registered.stateChanged.connect(self._toggle_tax_fields)
        self._form_tax.addRow(self.chk_vat_registered)

        self.lbl_vat_hint = QLabel()
        self.lbl_vat_hint.setProperty("class", "muted")
        self.lbl_vat_hint.setWordWrap(True)
        self._form_tax.addRow(self.lbl_vat_hint)

        self.lbl_tax_warn = QLabel()
        self.lbl_tax_warn.setProperty("class", "warning-hint")
        self._form_tax.addRow(self.lbl_tax_warn)

        self.spin_vat = QDoubleSpinBox()
        self.spin_vat.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_vat.setRange(0.0, 100.0)
        self.spin_vat.setDecimals(2)
        self.spin_vat.setSingleStep(0.5)
        self.spin_vat.setSuffix(" %")
        self.spin_vat.setFixedWidth(200)
        self._lbl_vat_rate = QLabel()
        self._form_tax.addRow(self._lbl_vat_rate, self.spin_vat)

        self.spin_sscl = QDoubleSpinBox()
        self.spin_sscl.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_sscl.setRange(0, 100)
        self.spin_sscl.setDecimals(2)
        self.spin_sscl.setSuffix("%")
        self.spin_sscl.setFixedWidth(200)
        self._lbl_sscl_rate = QLabel()
        self._form_tax.addRow(self._lbl_sscl_rate, self.spin_sscl)

        sscl_turnover_row = QHBoxLayout()
        self.spin_sscl_turnover = QDoubleSpinBox()
        self.spin_sscl_turnover.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_sscl_turnover.setRange(0, 100)
        self.spin_sscl_turnover.setDecimals(1)
        self.spin_sscl_turnover.setSuffix("%")
        self.spin_sscl_turnover.setFixedWidth(200)
        sscl_turnover_row.addWidget(self.spin_sscl_turnover)

        self.btn_sscl_turnover_help = HelpIconButton(on_click=self._show_sscl_guide)
        sscl_turnover_row.addWidget(self.btn_sscl_turnover_help)
        sscl_turnover_row.addStretch()

        self._lbl_sscl_turnover = QLabel()
        self._form_tax.addRow(self._lbl_sscl_turnover, sscl_turnover_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        self._form_tax.addRow(sep)

        item_exempt_row = QHBoxLayout()
        self.chk_item_tax_exemptions = QCheckBox()
        item_exempt_row.addWidget(self.chk_item_tax_exemptions)
        self.btn_item_exempt_help = HelpIconButton(on_click=self._show_exemptions_guide)
        item_exempt_row.addWidget(self.btn_item_exempt_help)
        item_exempt_row.addStretch()
        self._form_tax.addRow(item_exempt_row)

        self.lbl_item_exemptions_hint = QLabel()
        self.lbl_item_exemptions_hint.setProperty("class", "muted")
        self.lbl_item_exemptions_hint.setWordWrap(True)
        self._form_tax.addRow(self.lbl_item_exemptions_hint)

        self.tabs.addTab(self._tab_tax, "")

        # --- Tab 3: Loyalty ---
        self._tab_loyalty, self._form_loyalty = self._build_form_tab()

        self._header_loyalty = self._make_section_header("settings.loyalty.section_loyalty")
        self._form_loyalty.addRow(self._header_loyalty)

        self.chk_enable_loyalty = QCheckBox()
        self._form_loyalty.addRow("", self.chk_enable_loyalty)

        self.spin_points_ratio = QSpinBox()
        self.spin_points_ratio.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_points_ratio.setRange(0, 100000)
        self.spin_points_ratio.setFixedWidth(200)
        self._lbl_points_ratio = QLabel()
        self._form_loyalty.addRow(self._lbl_points_ratio, self.spin_points_ratio)

        self.spin_point_value = QDoubleSpinBox()
        self.spin_point_value.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_point_value.setDecimals(2)
        self.spin_point_value.setRange(0.0, 10000.0)
        self.spin_point_value.setFixedWidth(200)
        self._lbl_point_value = QLabel()
        self._form_loyalty.addRow(self._lbl_point_value, self.spin_point_value)

        self.spin_min_redeem = QSpinBox()
        self.spin_min_redeem.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_min_redeem.setRange(0, 100000)
        self.spin_min_redeem.setFixedWidth(200)
        self._lbl_min_redeem = QLabel()
        self._form_loyalty.addRow(self._lbl_min_redeem, self.spin_min_redeem)

        self.chk_show_on_receipt = QCheckBox()
        self._form_loyalty.addRow("", self.chk_show_on_receipt)

        self.tabs.addTab(self._tab_loyalty, "")
        self.chk_enable_loyalty.toggled.connect(self._toggle_loyalty_fields)

        self.set_currency_symbol(get_currency_symbol())
        self._toggle_tax_fields()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def _show_sscl_guide(self) -> None:
        """Show guide dialog explaining SSCL turnover liable base percentage."""
        steps = [
            ("settings.sales_tax.guide_sscl_step1_title", "settings.sales_tax.guide_sscl_step1_detail"),
            ("settings.sales_tax.guide_sscl_step2_title", "settings.sales_tax.guide_sscl_step2_detail"),
        ]
        dlg = GuideDialog(
            title_key="settings.sales_tax.guide_sscl_title",
            steps=steps,
            note_key="settings.sales_tax.guide_sscl_note",
            parent=self,
        )
        dlg.exec()

    def _show_exemptions_guide(self) -> None:
        """Show guide dialog explaining category and item-level tax exemptions."""
        steps = [
            ("settings.sales_tax.guide_exempt_step1_title", "settings.sales_tax.guide_exempt_step1_detail"),
            ("settings.sales_tax.guide_exempt_step2_title", "settings.sales_tax.guide_exempt_step2_detail"),
            ("settings.sales_tax.guide_exempt_step3_title", "settings.sales_tax.guide_exempt_step3_detail"),
        ]
        dlg = GuideDialog(
            title_key="settings.sales_tax.guide_exempt_title",
            steps=steps,
            note_key="settings.sales_tax.guide_exempt_note",
            parent=self,
        )
        dlg.exec()

    def retranslate_ui(self) -> None:
        """Update all widget text and tab labels from the translation system."""
        self._page_title.setText(_t("settings.sales_tax.title"))
        self.btn_reset_defaults.setText(_t("settings.btn_reset_defaults"))
        self._page_subtitle.setText(_t("settings.sales_tax.subtitle"))

        self.tabs.setTabText(0, _t("settings.sales_tax.tab_sales"))
        self.tabs.setTabText(1, _t("settings.sales_tax.tab_tax"))
        self.tabs.setTabText(2, _t("settings.loyalty.tab_loyalty"))

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
        self.chk_promo_stacking.setText(_t("settings.sales_tax.promo_stack_with_price_lists"))
        self.chk_promo_stacking.setToolTip(_t("settings.sales_tax.tooltip_promo_stack_with_price_lists"))
        self._lbl_promo_stacking_hint.setText(_t("settings.sales_tax.hint_promo_stack_with_price_lists"))

        # Tax tab
        self.chk_vat_registered.setText(_t("settings.sales_tax.vat_registered"))
        self.chk_vat_registered.setToolTip(_t("settings.sales_tax.tooltip_vat_registered"))
        self.lbl_vat_hint.setText(_t("settings.sales_tax.hint_vat_registered"))
        self.lbl_tax_warn.setText(_t("settings.sales_tax.tax_warning"))
        self._lbl_vat_rate.setText(_t("settings.sales_tax.vat_rate"))
        self._lbl_sscl_rate.setText(_t("settings.sales_tax.sscl_rate"))
        self._lbl_sscl_turnover.setText(_t("settings.sales_tax.sscl_turnover_base"))
        self.btn_sscl_turnover_help.setToolTip(_t("settings.sales_tax.sscl_turnover_help"))
        self.chk_item_tax_exemptions.setText(_t("settings.sales_tax.item_tax_exemptions"))
        self.chk_item_tax_exemptions.setToolTip(_t("settings.sales_tax.tooltip_item_tax_exemptions"))
        self.btn_item_exempt_help.setToolTip(_t("settings.sales_tax.tooltip_item_tax_exemptions"))
        self.lbl_item_exemptions_hint.setText(_t("settings.sales_tax.hint_item_tax_exemptions"))

        # Loyalty tab
        self.chk_enable_loyalty.setText(_t("settings.loyalty.enable_loyalty"))
        self.chk_enable_loyalty.setToolTip(_t("settings.loyalty.tooltip_enable_loyalty"))
        self._lbl_points_ratio.setText(_t("settings.loyalty.points_ratio"))
        self.spin_points_ratio.setToolTip(_t("settings.loyalty.tooltip_points_ratio"))
        self._lbl_point_value.setText(_t("settings.loyalty.point_value"))
        self.spin_point_value.setToolTip(_t("settings.loyalty.tooltip_point_value"))
        self._lbl_min_redeem.setText(_t("settings.loyalty.min_redeem_points"))
        self.spin_min_redeem.setToolTip(_t("settings.loyalty.tooltip_min_redeem_points"))
        self.spin_min_redeem.setSuffix(_t("settings.loyalty.suffix_points"))
        self.chk_show_on_receipt.setText(_t("settings.loyalty.show_on_receipt"))
        self.chk_show_on_receipt.setToolTip(_t("settings.loyalty.tooltip_show_on_receipt"))

        self._retranslate_section_headers()
        self.equalize_form_labels()

    def _toggle_tax_fields(self) -> None:
        """Enable/disable tax rate fields and sub-options based on VAT registration status."""
        enabled = self.chk_vat_registered.isChecked()
        # Labels are toggled with their fields so the whole row reads as
        # inactive, not just the input (#564).
        for widget in (
            self.spin_vat,
            self._lbl_vat_rate,
            self.spin_sscl,
            self._lbl_sscl_rate,
            self.spin_sscl_turnover,
            self._lbl_sscl_turnover,
            self.btn_sscl_turnover_help,
            self.chk_item_tax_exemptions,
            self.btn_item_exempt_help,
            self.lbl_item_exemptions_hint,
        ):
            widget.setEnabled(enabled)

    def _toggle_loyalty_fields(self, enabled: bool) -> None:
        """Enable or disable dependent settings controls based on loyalty toggle."""
        self.spin_points_ratio.setEnabled(enabled)
        self.spin_point_value.setEnabled(enabled)
        self.spin_min_redeem.setEnabled(enabled)
        self.chk_show_on_receipt.setEnabled(enabled)

    def set_currency_symbol(self, symbol: str) -> None:
        """Show ``symbol`` (the Shop Info currency, even unsaved) on the money spin boxes."""
        prefix = f"{(symbol or '').strip() or DEFAULT_CURRENCY_SYMBOL} "
        if hasattr(self, "spin_loyalty_ratio"):
            self.spin_loyalty_ratio.setPrefix(prefix)
        if hasattr(self, "spin_points_ratio"):
            self.spin_points_ratio.setPrefix(prefix)
        if hasattr(self, "spin_point_value"):
            self.spin_point_value.setPrefix(prefix)
        if hasattr(self, "spin_default_credit"):
            self.spin_default_credit.setPrefix(prefix)

    def load(self, settings: dict):
        """Populate sales and tax fields from the settings dict."""
        self.set_currency_symbol(settings.get("currency_symbol") or get_currency_symbol())
        mode = settings.get("default_search_mode", "ALL")
        idx = self.combo_search_mode.findData(mode)
        if idx >= 0:
            self.combo_search_mode.setCurrentIndex(idx)
        self.spin_max_discount.setValue(float(settings.get("max_discount_percent", 15.0)))
        self.spin_loyalty_ratio.setValue(int(settings.get("loyalty_points_ratio", 100)))
        self.spin_default_credit.setValue(int(settings.get("default_credit_limit", 0)))
        self.chk_promo_stacking.setChecked(bool(settings.get("promotion_stack_with_price_lists", False)))
        self.chk_vat_registered.setChecked(settings.get("vat_registered", False))
        self.spin_vat.setValue(float(settings.get("tax_vat_rate", 18.0)))
        self.spin_sscl.setValue(float(settings.get("tax_sscl_rate", 2.5)))
        self.spin_sscl_turnover.setValue(float(settings.get("tax_sscl_turnover_pct", 50.0)))
        self.chk_item_tax_exemptions.setChecked(settings.get("item_tax_exemptions", False))
        self._toggle_tax_fields()

        # Loyalty
        from cbpos.core.services.config_service import ConfigService

        ConfigService._migrate_loyalty_keys(settings)

        enabled = settings.get("enable_loyalty", ConfigService.DEFAULTS["enable_loyalty"])
        self.chk_enable_loyalty.setChecked(bool(enabled))

        ratio = settings.get("loyalty_points_ratio")
        if ratio is None:
            ratio = settings.get("points_ratio", ConfigService.DEFAULTS["loyalty_points_ratio"])
        self.spin_points_ratio.setValue(int(ratio))
        self.spin_loyalty_ratio.setValue(int(ratio))

        val = settings.get("loyalty_point_value")
        if val is None:
            val = settings.get("point_value", ConfigService.DEFAULTS["loyalty_point_value"])
        self.spin_point_value.setValue(float(val))

        min_pts = settings.get("loyalty_min_redeem_points", ConfigService.DEFAULTS["loyalty_min_redeem_points"])
        self.spin_min_redeem.setValue(int(min_pts))

        show_rec = settings.get("show_loyalty_on_receipt")
        if show_rec is None:
            show_rec = settings.get("receipt_show_loyalty", ConfigService.DEFAULTS["show_loyalty_on_receipt"])
        self.chk_show_on_receipt.setChecked(bool(show_rec))

        self._toggle_loyalty_fields(self.chk_enable_loyalty.isChecked())

    def save(self) -> dict:
        """Return sales, tax, and loyalty fields as a settings dict."""
        return {
            "default_search_mode": self.combo_search_mode.currentData() or "ALL",
            "max_discount_percent": self.spin_max_discount.value(),
            "default_credit_limit": self.spin_default_credit.value(),
            "promotion_stack_with_price_lists": self.chk_promo_stacking.isChecked(),
            "vat_registered": self.chk_vat_registered.isChecked(),
            "tax_vat_rate": round(self.spin_vat.value(), 2),
            "tax_sscl_rate": self.spin_sscl.value(),
            "tax_sscl_turnover_pct": self.spin_sscl_turnover.value(),
            "item_tax_exemptions": self.chk_item_tax_exemptions.isChecked(),
            "enable_loyalty": self.chk_enable_loyalty.isChecked(),
            "loyalty_points_ratio": self.spin_points_ratio.value(),
            "loyalty_point_value": round(self.spin_point_value.value(), 2),
            "loyalty_min_redeem_points": self.spin_min_redeem.value(),
            "show_loyalty_on_receipt": self.chk_show_on_receipt.isChecked(),
        }

    def validate(self) -> None:
        """Validate sales, tax, and loyalty settings."""
        if self.spin_points_ratio.value() < 1:
            raise ValueError(_t("settings.loyalty.error_points_ratio_positive"))
        if self.spin_point_value.value() <= 0:
            raise ValueError(_t("settings.loyalty.error_point_value_positive"))
        if self.spin_min_redeem.value() <= 0:
            raise ValueError(_t("settings.loyalty.error_min_redeem_positive"))


__all__ = ["SalesTaxPage"]
