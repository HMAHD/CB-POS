"""Unit tests for touch-friendly tooltips and visible guides (#579 [UI-020-B]).

Verifies:
1. No tooltip in the application locale files (EN, SI, TA) exceeds 140 characters.
2. Touch-friendly visible hints and HelpIconButton guides on SalesTaxPage,
   ReceiptPage, and NetworkPage.
3. GuideDialog invocations when help icon buttons are tapped/clicked.
4. Translation keys for hints and guides exist across all supported languages.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication, QLabel

from cbpos.i18n import _t, set_language
from cbpos.ui.dialogs.guide_dialog import GuideDialog
from cbpos.ui.views.settings_pages import NetworkPage, ReceiptPage, SalesTaxPage
from cbpos.ui.widgets.help_icon_button import HelpIconButton

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def app_instance():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestTooltipLengthConstraints:
    """Ensure no tooltip in the app exceeds 140 characters."""

    @pytest.mark.parametrize("lang", ["en", "si", "ta"])
    def test_all_tooltips_under_140_chars(self, lang):
        locale_path = Path(__file__).resolve().parents[2] / "cbpos" / "i18n" / f"{lang}.json"
        assert locale_path.exists(), f"Locale file {locale_path} missing"

        with open(locale_path, encoding="utf-8") as f:
            data = json.load(f)

        tooltips = []

        def walk(obj, prefix=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    path = f"{prefix}.{k}" if prefix else k
                    walk(v, path)
            elif isinstance(obj, str):
                key_last = prefix.split(".")[-1]
                if "tooltip" in key_last.lower() or key_last.endswith("_help"):
                    tooltips.append((prefix, obj))

        walk(data)
        assert len(tooltips) > 0

        too_long = [(k, len(v), v) for k, v in tooltips if len(v) > 140]
        assert not too_long, f"Language {lang} has {len(too_long)} tooltips > 140 chars: {too_long}"


class TestSalesTaxPageTouchFriendlyHelp:
    """Ensure SalesTaxPage replaces dense tooltips with visible hints and GuideDialogs."""

    def test_sales_tax_visible_hints_and_help_buttons_exist(self, qtbot):
        page = SalesTaxPage()
        qtbot.addWidget(page)

        # VAT hint
        assert isinstance(page.lbl_vat_hint, QLabel)
        assert page.lbl_vat_hint.property("class") == "muted"
        assert page.lbl_vat_hint.wordWrap() is True

        # SSCL Guide button
        assert isinstance(page.btn_sscl_turnover_help, HelpIconButton)

        # Item tax exemptions hint and help button
        assert isinstance(page.btn_item_exempt_help, HelpIconButton)
        assert isinstance(page.lbl_item_exemptions_hint, QLabel)
        assert page.lbl_item_exemptions_hint.property("class") == "muted"
        assert page.lbl_item_exemptions_hint.wordWrap() is True

    def test_sscl_help_button_invokes_guide_dialog(self, qtbot, monkeypatch):
        page = SalesTaxPage()
        qtbot.addWidget(page)
        page.chk_vat_registered.setChecked(True)

        guide_exec = MagicMock()
        monkeypatch.setattr(GuideDialog, "exec", guide_exec)

        page.btn_sscl_turnover_help.click()
        guide_exec.assert_called_once()

    def test_exemptions_help_button_invokes_guide_dialog(self, qtbot, monkeypatch):
        page = SalesTaxPage()
        qtbot.addWidget(page)
        page.chk_vat_registered.setChecked(True)

        guide_exec = MagicMock()
        monkeypatch.setattr(GuideDialog, "exec", guide_exec)

        page.btn_item_exempt_help.click()
        guide_exec.assert_called_once()

    def test_toggle_tax_fields_enables_and_disables_hints_and_buttons(self, qtbot):
        page = SalesTaxPage()
        qtbot.addWidget(page)

        page.chk_vat_registered.setChecked(False)
        assert not page.btn_sscl_turnover_help.isEnabled()
        assert not page.btn_item_exempt_help.isEnabled()
        assert not page.lbl_item_exemptions_hint.isEnabled()

        page.chk_vat_registered.setChecked(True)
        assert page.btn_sscl_turnover_help.isEnabled()
        assert page.btn_item_exempt_help.isEnabled()
        assert page.lbl_item_exemptions_hint.isEnabled()


class TestReceiptPageTouchFriendlyHelp:
    """Ensure ReceiptPage replaces logo tooltip paragraph with visible hint & GuideDialog."""

    def test_receipt_logo_hint_and_guide_button_exist(self, qtbot):
        page = ReceiptPage()
        qtbot.addWidget(page)
        page._refresh_timer.stop()

        assert isinstance(page.lbl_logo_hint, QLabel)
        assert page.lbl_logo_hint.property("class") == "muted"
        assert page.lbl_logo_hint.wordWrap() is True
        assert isinstance(page.btn_logo_help, HelpIconButton)

    def test_logo_help_button_invokes_guide_dialog(self, qtbot, monkeypatch):
        page = ReceiptPage()
        qtbot.addWidget(page)
        page._refresh_timer.stop()

        guide_exec = MagicMock()
        monkeypatch.setattr(GuideDialog, "exec", guide_exec)

        page.btn_logo_help.click()
        guide_exec.assert_called_once()


class TestNetworkPageTouchFriendlyHelp:
    """Ensure NetworkPage has visible hints and HelpIconButton guides for modes."""

    def test_network_mode_hints_and_guide_buttons_exist(self, qtbot):
        page = NetworkPage()
        qtbot.addWidget(page)

        # Database mode
        assert isinstance(page.btn_db_mode_help, HelpIconButton)
        assert isinstance(page.lbl_db_mode_hint, QLabel)
        assert page.lbl_db_mode_hint.property("class") == "muted"
        assert page.lbl_db_mode_hint.wordWrap() is True

        # LAN sync terminal mode
        assert isinstance(page.btn_terminal_mode_help, HelpIconButton)
        assert isinstance(page.lbl_terminal_mode_hint, QLabel)
        assert page.lbl_terminal_mode_hint.property("class") == "muted"
        assert page.lbl_terminal_mode_hint.wordWrap() is True

        # LAN sync port hint
        assert isinstance(page.lbl_sync_port_hint, QLabel)
        assert page.lbl_sync_port_hint.property("class") == "muted"
        assert page.lbl_sync_port_hint.wordWrap() is True

    def test_db_mode_help_button_invokes_guide_dialog(self, qtbot, monkeypatch):
        page = NetworkPage()
        qtbot.addWidget(page)

        guide_exec = MagicMock()
        monkeypatch.setattr(GuideDialog, "exec", guide_exec)

        page.btn_db_mode_help.click()
        guide_exec.assert_called_once()

    def test_terminal_mode_help_button_invokes_guide_dialog(self, qtbot, monkeypatch):
        page = NetworkPage()
        qtbot.addWidget(page)

        guide_exec = MagicMock()
        monkeypatch.setattr(GuideDialog, "exec", guide_exec)

        page.btn_terminal_mode_help.click()
        guide_exec.assert_called_once()


class TestTranslationsForHintsAndGuides:
    """Ensure all hints and guides exist and translate correctly in EN, SI, and TA."""

    REQUIRED_KEYS = [
        "settings.sales_tax.hint_vat_registered",
        "settings.sales_tax.hint_item_tax_exemptions",
        "settings.sales_tax.guide_sscl_title",
        "settings.sales_tax.guide_sscl_step1_title",
        "settings.sales_tax.guide_sscl_step1_detail",
        "settings.sales_tax.guide_sscl_step2_title",
        "settings.sales_tax.guide_sscl_step2_detail",
        "settings.sales_tax.guide_sscl_note",
        "settings.sales_tax.guide_exempt_title",
        "settings.sales_tax.guide_exempt_step1_title",
        "settings.sales_tax.guide_exempt_step1_detail",
        "settings.sales_tax.guide_exempt_step2_title",
        "settings.sales_tax.guide_exempt_step2_detail",
        "settings.sales_tax.guide_exempt_step3_title",
        "settings.sales_tax.guide_exempt_step3_detail",
        "settings.sales_tax.guide_exempt_note",
        "settings.receipt.logo_hint",
        "settings.receipt.tooltip_logo_help",
        "settings.receipt.guide_logo_title",
        "settings.receipt.guide_logo_step1_title",
        "settings.receipt.guide_logo_step1_detail",
        "settings.receipt.guide_logo_step2_title",
        "settings.receipt.guide_logo_step2_detail",
        "settings.receipt.guide_logo_step3_title",
        "settings.receipt.guide_logo_step3_detail",
        "settings.receipt.guide_logo_note",
        "settings.network.hint_db_mode",
        "settings.network.hint_terminal_mode",
        "settings.network.hint_sync_port",
        "settings.network.guide_db_mode_title",
        "settings.network.guide_db_mode_step1_title",
        "settings.network.guide_db_mode_step1_detail",
        "settings.network.guide_db_mode_step2_title",
        "settings.network.guide_db_mode_step2_detail",
        "settings.network.guide_db_mode_step3_title",
        "settings.network.guide_db_mode_step3_detail",
        "settings.network.guide_db_mode_note",
        "settings.network.guide_terminal_mode_title",
        "settings.network.guide_terminal_mode_step1_title",
        "settings.network.guide_terminal_mode_step1_detail",
        "settings.network.guide_terminal_mode_step2_title",
        "settings.network.guide_terminal_mode_step2_detail",
        "settings.network.guide_terminal_mode_step3_title",
        "settings.network.guide_terminal_mode_step3_detail",
        "settings.network.guide_terminal_mode_note",
    ]

    @pytest.mark.parametrize("lang", ["en", "si", "ta"])
    def test_required_keys_defined(self, lang):
        set_language(lang)
        for key in self.REQUIRED_KEYS:
            val = _t(key)
            assert val != key, f"Missing translation for key '{key}' in language '{lang}'"
            assert len(val.strip()) > 0
        set_language("en")
