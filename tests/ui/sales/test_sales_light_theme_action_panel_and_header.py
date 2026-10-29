"""
#603: Sales screen in Light mode.

- On a fresh Light start the action tiles were already correct (dark
  icon/text on the light tile). They only went wrong if the theme changed
  under a live panel: icon pixmaps and inline label colors were baked in
  once from ``is_dark``. #673 made a theme change apply after restart,
  but the panel now re-tints anyway (label colors from QSS, icons on the
  theme callback) so it can't drift again.
- The header is navy in both themes, yet Light mode loaded the
  black-text logo onto it -- reproduced on a fresh Light start.
"""

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QWidget

from cbpos.core.services.theme_service import ThemeService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView
from cbpos.ui.widgets.action_panel import ActionPanel


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def theme(monkeypatch):
    """Apply a theme, returning its stylesheet (never touches the app's own)."""
    monkeypatch.setattr(ThemeService, "theme_change_callbacks", [])
    monkeypatch.setattr(ThemeService, "current_theme", ThemeService.current_theme)
    captured: list[str] = []
    monkeypatch.setattr(ThemeService, "_set_stylesheet", captured.append)

    def _apply(name: str) -> str:
        ThemeService.apply_theme(name)
        return captured[-1]

    return _apply


def _luminance(c: QColor) -> float:
    def ch(x: int) -> float:
        v = x / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def _contrast(a: QColor, b: QColor) -> float:
    hi, lo = sorted([_luminance(a), _luminance(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _icon_color(btn) -> QColor:
    img = btn.lbl_icon.pixmap().toImage()
    for x in range(img.width()):
        for y in range(img.height()):
            c = img.pixelColor(x, y)
            if c.alpha() == 255:
                return c
    raise AssertionError("icon pixmap is empty")


def _tile_background(host: QWidget, btn) -> QColor:
    img = host.grab().toImage()
    pos = btn.mapTo(host, btn.rect().topLeft())
    return img.pixelColor(pos.x() + btn.width() - 6, pos.y() + btn.height() // 2)


def _assert_tiles_readable(host: QWidget, panel: ActionPanel) -> None:
    for btn in panel._action_btns:
        bg = _tile_background(host, btn)
        text = btn.lbl_text.palette().color(btn.lbl_text.foregroundRole())
        assert _contrast(text, bg) >= 4.5, f"{btn._label_key} text {text.name()} on {bg.name()}"
        assert _contrast(_icon_color(btn), bg) >= 4.5, f"{btn._label_key} icon on {bg.name()}"


def _restyle(host: QWidget, css: str) -> None:
    host.setStyleSheet(css)
    host.show()
    for _ in range(3):
        QApplication.processEvents()


def test_fresh_light_start_tiles_are_readable(theme, qapp):
    css = theme("Light")
    host = QWidget()
    panel = ActionPanel(host)
    host.resize(320, 700)
    panel.resize(320, 700)
    _restyle(host, css)
    try:
        _assert_tiles_readable(host, panel)
    finally:
        host.close()
        host.deleteLater()


def test_switching_dark_to_light_retints_tiles(theme, qapp):
    css = theme("Dark")
    host = QWidget()
    panel = ActionPanel(host)
    host.resize(320, 700)
    panel.resize(320, 700)
    _restyle(host, css)
    try:
        _assert_tiles_readable(host, panel)
        _restyle(host, theme("Light"))
        _assert_tiles_readable(host, panel)
    finally:
        host.close()
        host.deleteLater()


def test_destroyed_panel_leaves_no_theme_callback(theme, qapp):
    theme("Dark")
    before = list(ThemeService.theme_change_callbacks)
    panel = ActionPanel()
    assert len(ThemeService.theme_change_callbacks) == len(before) + 1
    panel.destroyed.emit()  # what Qt emits when the C++ side goes away
    assert ThemeService.theme_change_callbacks == before
    panel.deleteLater()


@pytest.mark.parametrize("name", ["Dark", "Light"])
def test_header_logo_is_light_on_the_navy_header(theme, db_session, name):
    theme(name)
    view = SalesView()
    try:
        img = view.lbl_logo.pixmap().toImage()
        opaque = [
            img.pixelColor(x, y)
            for x in range(0, img.width(), 2)
            for y in range(0, img.height(), 2)
            if img.pixelColor(x, y).alpha() > 200
        ]
        assert opaque
        mean = sum(_luminance(c) for c in opaque) / len(opaque)
        assert mean > 0.5, f"{name}: header logo is dark (mean luminance {mean:.2f}) on a navy header"
    finally:
        view.deleteLater()
