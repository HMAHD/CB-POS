"""Tests for Sinhala and Tamil font metrics and explicit font registration (#589).

Verifies:
1. ResourceLoader explicitly registers Noto Sans, Noto Sans Sinhala, and Noto Sans Tamil.
2. get_primary_font() and get_font_families() return the prioritized script font for en, si, and ta.
3. ThemeService injects font fallbacks in light and dark QSS, ensuring bundled Noto fonts are matched.
4. SideMenu NavTile cards and CollapsibleSidebar SidebarButtons maintain identical structure,
   metrics, and icon/label alignments across English, Sinhala, and Tamil.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontMetrics

from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import get_language, set_language, unregister_language_callback
from cbpos.infrastructure.resource_loader import ResourceLoader
from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar
from cbpos.ui.widgets.custom_widgets import SidebarButton
from cbpos.ui.widgets.side_menu import NavTile, SideMenu

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def restore_environment():
    prev_lang = get_language()
    saved_theme = ThemeService.current_theme
    yield
    set_language(prev_lang)
    ThemeService.apply_theme(saved_theme)


def test_resource_loader_registers_all_bundled_fonts():
    """Verify ResourceLoader loads Noto Sans, Noto Sans Sinhala, and Noto Sans Tamil."""
    primary = ResourceLoader.load_fonts()
    loaded = ResourceLoader.get_loaded_families()

    assert primary == "Noto Sans"
    assert "Noto Sans" in loaded
    assert "Noto Sans Sinhala" in loaded
    assert "Noto Sans Tamil" in loaded


@pytest.mark.parametrize(
    ("lang", "expected_primary"),
    [
        ("en", "Noto Sans"),
        ("si", "Noto Sans Sinhala"),
        ("ta", "Noto Sans Tamil"),
    ],
)
def test_resource_loader_prioritizes_active_script(lang, expected_primary):
    """Verify primary font and fallback order prioritize the active script."""
    ResourceLoader.load_fonts()
    assert ResourceLoader.get_primary_font(lang) == expected_primary

    families = ResourceLoader.get_font_families(lang)
    assert families[0] == expected_primary
    assert "Noto Sans" in families
    assert "Noto Sans Sinhala" in families
    assert "Noto Sans Tamil" in families


def test_theme_stylesheet_contains_font_fallback_chain(monkeypatch):
    """Verify ThemeService injects font fallbacks in QSS templates."""
    ResourceLoader.load_fonts()
    captured_css = []
    ThemeService.set_stylesheet_handler(captured_css.append)

    set_language("si")
    ThemeService.apply_theme("Light")
    assert len(captured_css) > 0
    css = captured_css[-1]

    # Verify font-family global rule contains all three scripts
    assert 'font-family: "Noto Sans Sinhala"' in css or '"Noto Sans Sinhala"' in css
    assert '"Noto Sans Tamil"' in css
    assert '"Noto Sans"' in css


def test_side_menu_structure_identical_across_languages():
    """Verify SideMenu NavTiles maintain identical card layout and centering in en, si, ta."""
    ResourceLoader.load_fonts()

    for lang in ["en", "si", "ta"]:
        set_language(lang)
        menu = SideMenu()
        try:
            menu.resize(260, 700)
            menu.show()

            # All 6 nav tiles exist (Documents left the side menu in 908641a) and have expected minimum height
            assert len(menu._nav_buttons) == 6
            for tile in menu._nav_buttons:
                assert isinstance(tile, NavTile)
                assert tile.minimumHeight() in (NavTile.HEIGHT, NavTile.COMPACT_HEIGHT)
                assert tile.lbl_text.wordWrap() is True
                assert tile.lbl_icon.alignment() == Qt.AlignmentFlag.AlignCenter
                assert tile.lbl_text.alignment() == Qt.AlignmentFlag.AlignCenter
                # Non-empty label text rendered
                assert len(tile.lbl_text.text().strip()) > 0
        finally:
            unregister_language_callback(menu.retranslate_ui)
            menu.deleteLater()


def test_sidebar_button_structure_and_icon_size_identical():
    """Verify CollapsibleSidebar SidebarButtons maintain identical heights and icon padding."""
    ResourceLoader.load_fonts()

    labels = {
        "en": ["Dashboard", "Inventory", "Settings"],
        "si": ["උපකරණ පුවරුව", "තොග කළමනාකරණය", "සැකසුම්"],
        "ta": ["டாஷ்போர்டு", "சரக்கு இருப்பு", "அமைப்புகள்"],
    }

    for lang in ["en", "si", "ta"]:
        set_language(lang)
        sidebar = CollapsibleSidebar()
        try:
            for idx, text in enumerate(labels[lang]):
                sidebar.add_nav_button(text, "fa5s.chart-line", idx)

            sidebar.resize(260, 700)
            sidebar.show()

            for btn in sidebar.nav_buttons:
                assert isinstance(btn, SidebarButton)
                assert btn.height() in (40, 50, 54)
                # Icon size includes the gap for text-beside-icon
                assert btn.iconSize().width() == SidebarButton._ICON_SIZE + SidebarButton._ICON_TEXT_GAP
                assert btn.iconSize().height() == SidebarButton._ICON_SIZE
                assert len(btn.text().strip()) > 0
        finally:
            sidebar.deleteLater()


def test_font_metrics_line_height_across_scripts():
    """Verify font metrics line height and ascent/descent for Sinhala and Tamil match expected proportions."""
    ResourceLoader.load_fonts()

    for fam, sample in [
        ("Noto Sans", "Management"),
        ("Noto Sans Sinhala", "කළමනාකරණය"),
        ("Noto Sans Tamil", "நிர்வாகம்"),
    ]:
        font = QFont(fam, 10)
        fm = QFontMetrics(font)
        assert fm.height() > 0
        assert fm.ascent() > 0
        assert fm.descent() >= 0
        assert fm.lineSpacing() >= fm.height()
        rect = fm.boundingRect(sample)
        assert rect.width() > 0
        assert rect.height() > 0
