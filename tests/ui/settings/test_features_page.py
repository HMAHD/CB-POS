"""UI tests for Settings Features Page and SettingsView integration (#942)."""

from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.constants.features import IMPLEMENTED_FEATURES, Features
from cbpos.core.services.feature_flags import FeatureFlags
from cbpos.ui.views.settings_pages.features import FeaturesPage
from cbpos.ui.views.settings_view import SettingsView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def clean_flags(db_session):
    """Ensure feature flags cache and DB state are initialized."""
    FeatureFlags.invalidate_cache()
    yield db_session
    FeatureFlags.invalidate_cache()


def test_features_page_renders_only_implemented_features(clean_flags):
    """FeaturesPage only renders cards for IMPLEMENTED_FEATURES."""
    page = FeaturesPage()
    rendered_flags = set(page._switches.keys())
    assert rendered_flags == IMPLEMENTED_FEATURES

    # Implemented in #926
    assert Features.EXPIRY_DATES in rendered_flags
    assert Features.BATCHES in rendered_flags

    # Unimplemented flags from the preset matrix must NOT be rendered
    assert Features.VARIANTS not in rendered_flags
    assert Features.WEIGHT_SCALE not in rendered_flags
    assert Features.QUOTATIONS not in rendered_flags
    assert Features.DEPOSITS not in rendered_flags


def test_features_page_reflects_current_flag_state(clean_flags):
    """Checkbox state reflects FeatureFlags.is_on()."""
    clean_flags.commit()

    with patch.object(FeatureFlags, "is_on", side_effect=lambda f: f == Features.WARRANTY):
        page = FeaturesPage()
        assert page._switches[Features.WARRANTY].isChecked() is True
        assert page._switches[Features.CREDIT_BOOK].isChecked() is False
        assert page._switches[Features.SERIAL_TRACKING].isChecked() is False
        assert page._switches[Features.CHEQUES].isChecked() is False


def test_features_page_toggle_calls_feature_flags_set(clean_flags):
    """Toggling a checkbox invokes FeatureFlags.set()."""
    mock_user = MagicMock()
    mock_user.id = 42

    page = FeaturesPage()
    page.set_user(mock_user)

    with patch.object(FeatureFlags, "set") as mock_set:
        chk = page._switches[Features.WARRANTY]
        chk.setChecked(True)
        mock_set.assert_called_with(Features.WARRANTY, True, acting_user_id=42)


def test_features_page_toggle_error_reverts_state(clean_flags):
    """If FeatureFlags.set raises an error, the checkbox reverts state without looping."""
    page = FeaturesPage()
    chk = page._switches[Features.CREDIT_BOOK]
    chk.setChecked(False)

    with (
        patch.object(FeatureFlags, "set", side_effect=RuntimeError("Database lock")),
        patch("cbpos.ui.views.settings_pages.features.QMessageBox.critical") as mock_crit,
    ):
        chk.setChecked(True)
        mock_crit.assert_called_once()
        # Should be reverted to False
        assert chk.isChecked() is False


def test_features_page_read_only_on_till(clean_flags):
    """On a till terminal (terminal_mode='terminal'), all toggles are disabled with a tooltip."""
    from cbpos.core.services.config_service import ConfigService

    ConfigService.set("terminal_mode", "terminal")
    try:
        page = FeaturesPage()
        page.show()
        try:
            assert page.read_only_banner.isHidden() is False
            assert page.read_only_banner.isVisible() is True
            for chk in page._switches.values():
                assert chk.isEnabled() is False
                assert chk.toolTip() != ""
        finally:
            page.close()
            page.deleteLater()
    finally:
        ConfigService.set("terminal_mode", "standalone")


def test_settings_view_features_integration(clean_flags):
    """SettingsView has a Features nav button and stacked FeaturesPage at index 10."""
    view = SettingsView()
    assert hasattr(view, "btn_features")
    assert hasattr(view, "features_page")
    assert (
        view.stack.indexOf(view.features_page.parentWidget().parentWidget()) == 10
        or view.stack.widget(10).findChild(FeaturesPage) is not None
    )

    # Switch to features page
    view.switch_page(10)
    assert view.stack.currentIndex() == 10
    assert view._page_title_keys[10] == "settings.sidebar_features"
