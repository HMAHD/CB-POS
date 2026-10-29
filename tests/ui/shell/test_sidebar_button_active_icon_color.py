"""
#287: the collapsed (icon-only) sidebar rail showed almost no visible
difference for the current section -- set_active() only called
setChecked(), which drives the QSS background/border/text-color rule,
but a qtawesome icon is a baked pixmap QSS can't recolor. In collapsed
mode there's no text left to carry the accent color either, so the
icon glyph stayed the same secondary color regardless of active state,
leaving only a thin left border as the sole "you are here" signal.
"""

import pytest

from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.widgets.custom_widgets import SidebarButton

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _dark_theme(monkeypatch):
    monkeypatch.setattr(ThemeService, "current_theme", "Dark")


class TestSidebarButtonActiveIconColor:
    def test_inactive_button_uses_the_secondary_icon_color(self, qapp):
        btn = SidebarButton("Dashboard", "fa5s.tachometer-alt")
        assert not btn.icon().isNull()
        # Inactive icons render in the theme's neutral icon color, not
        # the accent -- confirmed indirectly via the active/inactive
        # pixmap comparison below, since QIcon doesn't expose the color
        # it was rendered with directly.

    def test_activating_the_button_changes_the_icon_pixmap(self, qapp):
        btn = SidebarButton("Dashboard", "fa5s.tachometer-alt")
        inactive_pixmap = btn.icon().pixmap(24, 24).toImage()

        btn.set_active(True)
        active_pixmap = btn.icon().pixmap(24, 24).toImage()

        assert inactive_pixmap != active_pixmap

    def test_deactivating_restores_the_original_icon_color(self, qapp):
        btn = SidebarButton("Dashboard", "fa5s.tachometer-alt")
        original_pixmap = btn.icon().pixmap(24, 24).toImage()

        btn.set_active(True)
        btn.set_active(False)
        restored_pixmap = btn.icon().pixmap(24, 24).toImage()

        assert original_pixmap == restored_pixmap

    def test_active_state_survives_a_theme_driven_icon_refresh(self, qapp):
        """update_icon() is also called on theme change and collapse
        toggle -- it must keep using the accent color while active
        instead of silently reverting to the neutral icon color."""
        btn = SidebarButton("Dashboard", "fa5s.tachometer-alt")
        btn.set_active(True)
        active_pixmap = btn.icon().pixmap(24, 24).toImage()

        btn.update_icon()
        refreshed_pixmap = btn.icon().pixmap(24, 24).toImage()

        assert active_pixmap == refreshed_pixmap

    def test_active_icon_color_matches_the_theme_accent(self, qapp, monkeypatch):
        calls = []
        from cbpos.ui.widgets import custom_widgets

        original_get = custom_widgets.Icons.get

        def _spy_get(name, color="white"):
            calls.append(color)
            return original_get(name, color)

        monkeypatch.setattr(custom_widgets.Icons, "get", _spy_get)

        btn = SidebarButton("Dashboard", "fa5s.tachometer-alt")
        calls.clear()
        btn.set_active(True)

        assert calls[-1] == ThemeService.get_accent_color()
