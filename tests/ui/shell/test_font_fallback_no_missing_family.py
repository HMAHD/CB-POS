"""Regression tests for Qt missing font family warning (#Qt Warning: Populating font family aliases took ... ms).

Qt Style Sheets (QSS) do not treat "sans-serif" as a CSS generic keyword.
Instead, Qt queries QFontDatabase for a font literally named "Sans-serif".
When missing, Qt populates all OS font aliases, blocking startup by 200-350 ms.
"""

from pathlib import Path

import pytest
from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtWidgets import QLabel

from cbpos.core.services.theme_service import ThemeService
from cbpos.infrastructure.resource_loader import ResourceLoader
from tests.helpers.qss import rendered_qss

STYLES_DIR = Path(__file__).resolve().parents[3] / "cbpos" / "ui" / "styles"


@pytest.mark.parametrize("theme_file", ["dark.qss", "light.qss"])
def test_qss_font_family_does_not_contain_generic_sans_serif(theme_file: str):
    """Ensure QSS stylesheets do not include 'sans-serif' which triggers Qt alias population."""
    content = rendered_qss(theme_file)
    for line in content.splitlines():
        if "font-family:" in line:
            assert "sans-serif" not in line.lower(), (
                f"{theme_file} contains generic 'sans-serif' in font-family: {line.strip()}"
            )


def test_resource_loader_css_does_not_contain_generic_sans_serif():
    """Ensure ResourceLoader.get_font_family_css() does not append generic 'sans-serif'."""
    css = ResourceLoader.get_font_family_css()
    assert "sans-serif" not in css.lower(), f"ResourceLoader.get_font_family_css() includes 'sans-serif': {css}"


def test_theme_application_emits_no_font_alias_warnings(qapp):
    """Ensure applying themes and rendering glyphs emits zero font alias population warnings."""
    ResourceLoader.load_fonts()

    captured_warnings = []

    def handler(mode, ctx, msg):
        if "Populating font family aliases" in msg:
            captured_warnings.append(msg)

    qInstallMessageHandler(handler)
    try:
        ThemeService.set_stylesheet_handler(lambda css: qapp.setStyleSheet(css))
        for theme in ["Dark", "Light"]:
            ThemeService.apply_theme(theme)
            lbl = QLabel("★ 100 Current Points")
            lbl.show()
            qapp.processEvents()
            lbl.deleteLater()
    finally:
        qInstallMessageHandler(None)
        qapp.setStyleSheet("")

    assert captured_warnings == [], (
        f"Qt populated font family aliases (delaying startup/rendering): {captured_warnings}"
    )
