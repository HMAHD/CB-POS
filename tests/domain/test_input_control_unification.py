"""
Tests for UI-007 (Issue #563) and UI-009 (Issue #565):
- Unified input control styling (QLineEdit, QDateEdit, QComboBox, QSpinBox)
- Single generic QLineEdit rule per QSS file
- High contrast input borders in Dark mode (#555555)
- White focus background in Light mode (#FFFFFF)
- Surface/elevation tokens in Light mode (#SettingsContent, dividers, guide steps)
"""

import re
from pathlib import Path

from tests.helpers.qss import rendered_qss

STYLES_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"
COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(css: str) -> str:
    return COMMENT_RE.sub("", css)


def _load(theme_file: str) -> str:
    return rendered_qss(theme_file)


class TestInputControlStylingUnification:
    """Validate acceptance criteria for Issue #563."""

    def test_single_generic_qlineedit_rule_per_theme(self):
        """Each QSS file must have exactly one generic 'QLineEdit {' rule."""
        for theme_file in ("dark.qss", "light.qss"):
            content = _strip_comments(_load(theme_file))
            # Match generic QLineEdit { at start of line or after whitespace, not QLineEdit#Id or QWidget QLineEdit
            matches = re.findall(r"(?:^|\n)\s*QLineEdit\s*\{", content)
            assert len(matches) == 1, f"{theme_file} has {len(matches)} generic QLineEdit rules; expected exactly 1"

    def test_dark_mode_generic_input_borders_have_contrast(self):
        """In Dark mode, input borders use #555555 for visible boundaries."""
        dark_css = _strip_comments(_load("dark.qss"))
        # Verify baseline QLineEdit uses #555555 border
        line_edit_match = re.search(r"QLineEdit\s*\{([^}]+)\}", dark_css)
        assert line_edit_match is not None
        assert "#555555" in line_edit_match.group(1)
        assert "#3A3A3A" not in line_edit_match.group(1)

        # Verify QDateEdit uses #555555 border
        date_edit_match = re.search(r"QDateEdit,\s*QTimeEdit,\s*QDateTimeEdit\s*\{([^}]+)\}", dark_css)
        assert date_edit_match is not None
        assert "#555555" in date_edit_match.group(1)

    def test_light_mode_focus_keeps_white_fill(self):
        """In Light mode, focused inputs remain white, not gray #F8F9FA."""
        light_css = _strip_comments(_load("light.qss"))
        line_edit_focus = re.search(r"QLineEdit:focus\s*\{([^}]+)\}", light_css)
        assert line_edit_focus is not None
        assert "background-color: #FFFFFF;" in line_edit_focus.group(1)

        date_edit_focus = re.search(
            r"QDateEdit:focus,\s*QTimeEdit:focus,\s*QDateTimeEdit:focus\s*\{([^}]+)\}", light_css
        )
        assert date_edit_focus is not None
        assert "background-color: #FFFFFF;" in date_edit_focus.group(1)

    def test_input_error_states_defined(self):
        """Inputs have [error='true'] rule for validation feedback."""
        for theme_file in ("dark.qss", "light.qss"):
            css = _strip_comments(_load(theme_file))
            assert 'QLineEdit[error="true"]' in css
            assert 'QDateEdit[error="true"]' in css
            assert 'QComboBox[error="true"]' in css
            assert 'QSpinBox[error="true"]' in css


class TestElevationAndSurfaceTokens:
    """Validate acceptance criteria for Issue #565."""

    def test_settings_content_page_background_and_focus(self):
        """In Light mode, SettingsContent uses #F8F9FA page color with white inputs on focus."""
        light_css = _strip_comments(_load("light.qss"))
        settings_content = re.search(r"QWidget#SettingsContent\s*\{([^}]+)\}", light_css)
        assert settings_content is not None
        assert "background-color: #F8F9FA;" in settings_content.group(1)

        settings_focus = re.search(r"QWidget#SettingsContent\s+QLineEdit:focus[^{]*\{([^}]+)\}", light_css)
        assert settings_focus is not None
        assert "background-color: #FFFFFF;" in settings_focus.group(1)

    def test_guide_step_cards_have_contrast_and_accent(self):
        """Email/SMTP guide step cards have distinct surface and accent border."""
        light_css = _strip_comments(_load("light.qss"))
        guide_match = re.search(r"QFrame#SmtpGuideStep\s*\{([^}]+)\}", light_css)
        assert guide_match is not None
        # A raised surface (tokens, D20), not the plain card white.
        assert "background-color: #FFFFFF;" not in guide_match.group(1)
        assert "border: 1px solid #CED4DA;" in guide_match.group(1)
        assert "border-left: 3px solid #0D6EFD;" in guide_match.group(1)

    def test_sidebar_dividers_defined(self):
        """Sidebar dividers use #CED4DA in Light mode and #3E3E42 in Dark mode."""
        light_css = _strip_comments(_load("light.qss"))
        assert "#CED4DA" in re.search(r"QWidget#PriceListSidebarPanel\s*\{([^}]+)\}", light_css).group(1)
        assert "#CED4DA" in re.search(r"#ReportSidebarPanel\s*\{([^}]+)\}", light_css).group(1)

        dark_css = _strip_comments(_load("dark.qss"))
        assert "#3E3E42" in re.search(r"QWidget#PriceListSidebarPanel\s*\{([^}]+)\}", dark_css).group(1)
        assert "#3E3E42" in re.search(r"#ReportSidebarPanel\s*\{([^}]+)\}", dark_css).group(1)
