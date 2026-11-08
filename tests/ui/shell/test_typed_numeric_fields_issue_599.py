"""Unit tests verifying Issue #599 [UI-031-B]:

- Typed numeric fields: Decimal money input for promotions
- No spin buttons in Settings Sales/Tax/System
- Clear idle-timeout checkbox and enable state
- Idle timeout localization in Sinhala
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QAbstractSpinBox

from cbpos.core.models import Promotion
from cbpos.i18n import set_language, unregister_language_callback
from cbpos.ui.views.promotion_view import PromotionDialog
from cbpos.ui.views.settings_pages import SalesTaxPage, SystemPage

pytestmark = pytest.mark.usefixtures("qapp")


class TestPromotionDecimalValue:
    """A promotion value of 12.35 is saved and reloaded exactly as 12.35 without float precision loss."""

    def test_promotion_value_exact_decimal_save_and_reload(self, db_session):
        now = datetime.now()
        promo = Promotion(
            name="Precise Decimal Promo",
            type="FIXED_AMOUNT",
            value=Decimal("12.35"),
            start_time=now,
            end_time=now + timedelta(days=7),
            days_of_week=None,
        )

        dialog = PromotionDialog(promotion=promo)
        assert dialog.value_input.text() == "12.35"
        assert dialog.value_input.decimal_value() == Decimal("12.35")
        assert dialog.value_input.value() == 12.35

        data = dialog.get_data()
        assert data["value"] == Decimal("12.35")
        assert isinstance(data["value"], Decimal)

        # Update to another exact decimal
        dialog.value_input.setText("49.99")
        assert dialog.value_input.decimal_value() == Decimal("49.99")
        assert dialog.get_data()["value"] == Decimal("49.99")


class TestSettingsNumericFieldSteppers:
    """Settings Tax/Sales/System numeric fields show no +/- buttons; arrow keys still step."""

    def test_sales_and_tax_numeric_fields_have_no_buttons(self):
        page = SalesTaxPage()
        try:
            fields = [
                page.spin_max_discount,
                page.spin_loyalty_ratio,
                page.spin_default_credit,
                page.spin_vat,
                page.spin_sscl,
                page.spin_sscl_turnover,
            ]
            for field in fields:
                assert field.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons

            # Stepping via keyboard / stepBy still works (spin_vat has singleStep 0.5 per #810)
            page.spin_vat.setValue(18)
            page.spin_vat.stepBy(1)
            assert page.spin_vat.value() == 18.5
            page.spin_vat.stepBy(-1)
            assert page.spin_vat.value() == 18
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()

    def test_system_numeric_fields_have_no_buttons(self):
        page = SystemPage()
        try:
            fields = [
                page.spin_timeout,
                page.spin_max_login,
                page.spin_lockout,
                page.spin_retention,
            ]
            for field in fields:
                assert field.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()


class TestSystemIdleTimeoutControl:
    """Idle timeout control uses a checkbox toggle and minutes input enabled only when checked."""

    def test_idle_timeout_disabled_by_default_or_zero(self):
        page = SystemPage()
        try:
            page.load({"session_timeout_minutes": 0})
            assert not page.chk_timeout.isChecked()
            assert not page.spin_timeout.isEnabled()
            assert not page._lbl_timeout.isEnabled()
            assert page.save()["session_timeout_minutes"] == 0
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()

    def test_idle_timeout_enabled_when_positive(self):
        page = SystemPage()
        try:
            page.load({"session_timeout_minutes": 15})
            assert page.chk_timeout.isChecked()
            assert page.spin_timeout.isEnabled()
            assert page._lbl_timeout.isEnabled()
            assert page.spin_timeout.value() == 15
            assert page.save()["session_timeout_minutes"] == 15
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()

    def test_idle_timeout_toggling(self):
        page = SystemPage()
        try:
            page.load({"session_timeout_minutes": 0})
            assert not page.chk_timeout.isChecked()

            # Enable timeout
            page.chk_timeout.setChecked(True)
            assert page.spin_timeout.isEnabled()
            assert page._lbl_timeout.isEnabled()
            page.spin_timeout.setValue(10)
            assert page.save()["session_timeout_minutes"] == 10

            # Disable timeout
            page.chk_timeout.setChecked(False)
            assert not page.spin_timeout.isEnabled()
            assert not page._lbl_timeout.isEnabled()
            assert page.save()["session_timeout_minutes"] == 0
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()

    def test_idle_timeout_readable_in_sinhala(self):
        page = SystemPage()
        try:
            set_language("si")
            page.retranslate_ui()
            assert "ක්‍රියා විරහිත වූ විට තිරය අගුළු දමන්න" in page.chk_timeout.text()
            assert "නිෂ්ක්‍රිය කාල සීමාව:" in page._lbl_timeout.text()
            assert page.spin_timeout.suffix() == " මිනි"
        finally:
            set_language("en")
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()
