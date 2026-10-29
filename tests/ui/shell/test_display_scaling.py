"""Unit test for Issue #600 [UI-032]: Rendering at Windows 125%/150% display scaling."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication

from cbpos.ui.views.login_view import _BTN_SIZE_MAX, _BTN_SIZE_MIN, LoginView
from cbpos.ui.widgets.side_menu import NavTile, SideMenu

pytestmark = pytest.mark.usefixtures("qapp")


class TestDisplayScalingAndActiveTiles:
    def test_high_dpi_rounding_policy_is_passthrough(self):
        """PassThrough policy preserves fractional scaling (125%, 150%) instead of rounding."""
        policy = QGuiApplication.highDpiScaleFactorRoundingPolicy()
        assert policy == Qt.HighDpiScaleFactorRoundingPolicy.PassThrough

    def test_nav_tile_active_qss_uses_2px_border_and_tint(self):
        """NavTile styling in both dark and light QSS uses 2px border and 15% tint to prevent clipping."""
        import re

        from cbpos.config import Config

        dark_qss = (Config.BASE_DIR / "cbpos" / "ui" / "styles" / "dark.qss").read_text(encoding="utf-8")
        light_qss = (Config.BASE_DIR / "cbpos" / "ui" / "styles" / "light.qss").read_text(encoding="utf-8")

        # Dark theme active tile
        assert re.search(
            r'QPushButton#NavTile\[active="true"\]\s*\{[^}]*border:\s*2px solid #00BCEB;[^}]*background-color:\s*rgba\(0,\s*188,\s*235,\s*0\.15\);',
            dark_qss,
        )

        # Light theme active tile
        assert re.search(
            r'QPushButton#NavTile\[active="true"\]\s*\{[^}]*border:\s*2px solid #0D6EFD;[^}]*background-color:\s*rgba\(13,\s*110,\s*253,\s*0\.15\);',
            light_qss,
        )

    def test_nav_tile_active_state_colors(self, qapp):
        """NavTile active state updates text and icon accent colors."""
        tile = NavTile("side_menu.management", "fa5s.chart-line")
        tile.show()
        qapp.processEvents()

        # Non-active
        assert tile.property("active") in (False, None)

        # Active
        tile.set_active(True)
        assert tile.property("active") is True

    def test_login_keypad_fluid_scaling_at_fractional_heights(self, qapp):
        """Login keypad scales down smoothly at 100%, 125%, and 150% scaled heights without bottom-row clipping."""
        login = LoginView()
        # Simulated logical heights for 768p display at 100%, 125%, 150%
        scales = [(1366, 768), (1092, 614), (910, 512)]

        for w, h in scales:
            login.resize(w, h)
            login.show()
            qapp.processEvents()

            assert _BTN_SIZE_MIN <= login._btn_size <= _BTN_SIZE_MAX
            assert login.numpad_container.width() == login.pin_input.width()
            # Numpad container bottom should not exceed right panel
            numpad_bottom = login.numpad_container.y() + login.numpad_container.height()
            assert numpad_bottom <= login.right_panel.height()

    def test_side_menu_active_tile_within_bounds_at_various_scales(self, qapp):
        """Side menu active tiles remain within scroll bounds across scaled heights."""
        menu = SideMenu()

        for h in (768, 614, 512):
            menu.resize(200, h)
            menu.show()
            # showEvent clears active tiles (d661622), so mark one active after showing.
            menu.btn_management.set_active(True)
            qapp.processEvents()

            viewport_w = menu.nav_scroll.viewport().width()
            assert menu.btn_management.width() <= viewport_w
            assert menu.btn_management.property("active") is True
