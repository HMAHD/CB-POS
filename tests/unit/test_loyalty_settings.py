"""Unit tests for Issue #754: Loyalty settings section: point value, minimum redeem, show on receipt.

Verifies:
1. One Loyalty section shows all five settings, translated en/si/ta, with tooltips.
2. Existing Enable Loyalty / Points Ratio values carry over after upgrade (no reset).
3. Defaults: Point Value Rs. 1, Minimum Redeem 100 points, Show on receipt on, Ratio 100, Enable on.
4. Settings save/validate like other pages (positive values, Points Ratio >= 1).
5. Turning loyalty off disables the other loyalty settings' controls (documented in tooltip).
6. Tests for load/save/defaults/migration of old keys.
7. SalesTaxPage and SystemPage no longer own loyalty settings.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import get_language, set_language
from cbpos.ui.views.settings_pages import LoyaltyPage, SalesTaxPage, SystemPage
from cbpos.ui.views.settings_view import SettingsView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _restore_language():
    original = get_language()
    set_language("en")
    yield
    set_language(original)


class TestLoyaltySettingsDefaults:
    def test_default_config_has_all_five_loyalty_keys(self):
        assert ConfigService.DEFAULTS["enable_loyalty"] is True
        assert ConfigService.DEFAULTS["loyalty_points_ratio"] == 100
        assert ConfigService.DEFAULTS["loyalty_point_value"] == 1.0
        assert ConfigService.DEFAULTS["loyalty_min_redeem_points"] == 100
        assert ConfigService.DEFAULTS["show_loyalty_on_receipt"] is True


class TestLoyaltyPageUI:
    def test_page_has_all_five_controls_and_section_header(self, qtbot):
        page = LoyaltyPage()
        qtbot.addWidget(page)

        assert hasattr(page, "chk_enable_loyalty")
        assert hasattr(page, "spin_points_ratio")
        assert hasattr(page, "spin_point_value")
        assert hasattr(page, "spin_min_redeem")
        assert hasattr(page, "chk_show_on_receipt")
        assert hasattr(page, "btn_reset_defaults")
        assert hasattr(page, "_header_loyalty")

    def test_turning_loyalty_off_disables_dependent_controls(self, qtbot):
        page = LoyaltyPage()
        qtbot.addWidget(page)

        # Checked by default -> dependents enabled
        page.chk_enable_loyalty.setChecked(True)
        assert page.spin_points_ratio.isEnabled() is True
        assert page.spin_point_value.isEnabled() is True
        assert page.spin_min_redeem.isEnabled() is True
        assert page.chk_show_on_receipt.isEnabled() is True

        # Uncheck -> dependents disabled
        page.chk_enable_loyalty.setChecked(False)
        assert page.spin_points_ratio.isEnabled() is False
        assert page.spin_point_value.isEnabled() is False
        assert page.spin_min_redeem.isEnabled() is False
        assert page.chk_show_on_receipt.isEnabled() is False

        # Re-check -> dependents re-enabled
        page.chk_enable_loyalty.setChecked(True)
        assert page.spin_points_ratio.isEnabled() is True
        assert page.spin_point_value.isEnabled() is True
        assert page.spin_min_redeem.isEnabled() is True
        assert page.chk_show_on_receipt.isEnabled() is True

    @pytest.mark.parametrize("lang", ["en", "si", "ta"])
    def test_all_five_settings_have_labels_and_tooltips(self, qtbot, lang):
        set_language(lang)
        page = LoyaltyPage()
        qtbot.addWidget(page)

        # Tooltips exist and non-empty
        assert len(page.chk_enable_loyalty.toolTip()) > 10
        assert len(page.spin_points_ratio.toolTip()) > 10
        assert len(page.spin_point_value.toolTip()) > 10
        assert len(page.spin_min_redeem.toolTip()) > 10
        assert len(page.chk_show_on_receipt.toolTip()) > 10

        # Enable loyalty tooltip documents effect of turning it off
        enable_tip = page.chk_enable_loyalty.toolTip().lower()
        if lang == "en":
            assert "disabled" in enable_tip or "off" in enable_tip or "no effect" in enable_tip


class TestLoyaltyPageLoadSaveValidation:
    def test_load_and_save_cycle(self, qtbot):
        page = LoyaltyPage()
        qtbot.addWidget(page)

        settings = {
            "enable_loyalty": True,
            "loyalty_points_ratio": 200,
            "loyalty_point_value": 2.50,
            "loyalty_min_redeem_points": 50,
            "show_loyalty_on_receipt": False,
        }
        page.load(settings)
        saved = page.save()

        assert saved["enable_loyalty"] is True
        assert saved["loyalty_points_ratio"] == 200
        assert saved["loyalty_point_value"] == 2.50
        assert saved["loyalty_min_redeem_points"] == 50
        assert saved["show_loyalty_on_receipt"] is False

    def test_carry_over_existing_enable_loyalty_and_ratio_after_upgrade(self, qtbot):
        """Old settings.json with only old keys carries over without reset."""
        page = LoyaltyPage()
        qtbot.addWidget(page)

        old_settings = {
            "enable_loyalty": False,
            "loyalty_points_ratio": 150,
        }
        page.load(old_settings)
        saved = page.save()

        assert saved["enable_loyalty"] is False
        assert saved["loyalty_points_ratio"] == 150
        # New settings take defaults
        assert saved["loyalty_point_value"] == 1.0
        assert saved["loyalty_min_redeem_points"] == 100
        assert saved["show_loyalty_on_receipt"] is True

    def test_migration_of_legacy_aliases(self, qtbot):
        """Legacy aliases like points_ratio or min_redeem_points carry over cleanly."""
        page = LoyaltyPage()
        qtbot.addWidget(page)

        legacy = {
            "points_ratio": 300,
            "point_value": 1.5,
            "min_redeem_points": 75,
            "receipt_show_loyalty": False,
        }
        page.load(legacy)
        saved = page.save()

        assert saved["loyalty_points_ratio"] == 300
        assert saved["loyalty_point_value"] == 1.5
        assert saved["loyalty_min_redeem_points"] == 75
        assert saved["show_loyalty_on_receipt"] is False

    def test_validate_rejects_non_positive_values(self, qtbot):
        page = LoyaltyPage()
        qtbot.addWidget(page)

        # Points ratio < 1
        page.spin_points_ratio.setValue(0)
        page.spin_point_value.setValue(1.0)
        page.spin_min_redeem.setValue(100)
        with pytest.raises(ValueError, match=r"(?i)ratio"):
            page.validate()

        # Point value <= 0
        page.spin_points_ratio.setValue(100)
        page.spin_point_value.setValue(0.0)
        with pytest.raises(ValueError, match=r"(?i)value"):
            page.validate()

        # Min redeem <= 0
        page.spin_point_value.setValue(1.0)
        page.spin_min_redeem.setValue(0)
        with pytest.raises(ValueError, match=r"(?i)minimum|redeem"):
            page.validate()

        # Valid values pass
        page.spin_min_redeem.setValue(50)
        page.validate()  # Does not raise

    def test_reset_to_defaults(self, qtbot, db_session):
        page = LoyaltyPage()
        qtbot.addWidget(page)

        page.load(
            {
                "enable_loyalty": False,
                "loyalty_points_ratio": 500,
                "loyalty_point_value": 5.0,
                "loyalty_min_redeem_points": 500,
                "show_loyalty_on_receipt": False,
            }
        )

        with (
            patch("cbpos.ui.views.settings_pages.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes),
            patch("cbpos.ui.views.settings_pages.QMessageBox.information"),
        ):
            page._reset_to_defaults()

        saved = page.save()
        assert saved["enable_loyalty"] is True
        assert saved["loyalty_points_ratio"] == 100
        assert saved["loyalty_point_value"] == 1.0
        assert saved["loyalty_min_redeem_points"] == 100
        assert saved["show_loyalty_on_receipt"] is True


class TestDecouplingFromOldPages:
    def test_sales_tax_and_system_pages_no_longer_save_loyalty_keys(self, qtbot):
        sales_page = SalesTaxPage()
        qtbot.addWidget(sales_page)
        sales_saved = sales_page.save()
        assert "loyalty_points_ratio" not in sales_saved

        sys_page = SystemPage()
        qtbot.addWidget(sys_page)
        sys_saved = sys_page.save()
        assert "enable_loyalty" not in sys_saved


class TestSettingsViewIntegration:
    def test_settings_view_includes_loyalty_page_and_sidebar_button(self, qtbot, db_session):
        view = SettingsView()
        qtbot.addWidget(view)

        loyalty_pages = [p for p in view.pages if isinstance(p, LoyaltyPage)]
        assert len(loyalty_pages) == 1
        assert hasattr(view, "btn_loyalty")
        assert view.btn_loyalty.text() != ""
