"""
#604: Sales action shortcuts must show in every language, styled apart from
the label. Pay's "(F5)" lived inside the translated text ("  Pay (F5)"), so
Sinhala/Tamil ("ගෙවීම", "பணம் செலுத்து") silently dropped it. The key is
now a separate, themed badge (QLabel#lblShortcut) that no translation can
remove; the tiles' badges are restyled to be readable (they were ~2:1).
"""

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import _t, get_language, set_language
from cbpos.ui.widgets.action_panel import ActionPanel

EXPECTED_TILE_KEYS = {
    "action_panel.btn_customer": "F2",
    "action_panel.btn_search": "F3",
    "action_panel.btn_qty": "F4",
    "action_panel.btn_hold": "F6",
    "action_panel.btn_recall": "F7",
    "action_panel.btn_drawer": "F8",
    "action_panel.btn_void": "Del",
}


@pytest.fixture
def panel(qapp, monkeypatch, request):
    theme = getattr(request, "param", "Dark")
    monkeypatch.setattr(ThemeService, "theme_change_callbacks", [])
    monkeypatch.setattr(ThemeService, "current_theme", ThemeService.current_theme)
    captured: list[str] = []
    monkeypatch.setattr(ThemeService, "_set_stylesheet", captured.append)
    ThemeService.apply_theme(theme)
    original_lang = get_language()

    host = QWidget()
    host.setStyleSheet(captured[-1])
    p = ActionPanel(host)
    host.resize(320, 700)
    p.resize(320, 700)
    host.show()
    QApplication.processEvents()
    yield host, p
    set_language(original_lang)
    host.close()
    host.deleteLater()


def _pay_badge(p: ActionPanel) -> QLabel:
    badges = p.btn_pay.findChildren(QLabel, "lblShortcut")
    assert len(badges) == 1, "Pay has no shortcut badge"
    return badges[0]


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_every_action_shows_its_shortcut(panel, lang):
    _host, p = panel
    set_language(lang)
    QApplication.processEvents()

    shown = {btn._label_key: btn.lbl_shortcut.text() for btn in p._action_btns if btn.lbl_shortcut.isVisible()}
    assert shown == EXPECTED_TILE_KEYS

    badge = _pay_badge(p)
    assert badge.isVisible()
    assert badge.text() == "F5"
    # The key is never part of the translated label itself any more.
    assert "F5" not in p.btn_pay.text()
    assert p.btn_pay.text().strip() == _t("action_panel.btn_pay").strip()


def test_refund_tile_shows_no_fake_shortcut(panel):
    """Refund has no keyboard shortcut; "Ref" looked like a key that doesn't exist."""
    _host, p = panel
    assert not p.btn_ref.lbl_shortcut.isVisible()


def _luminance(c: QColor) -> float:
    def ch(x: int) -> float:
        v = x / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def _badge_contrast(host: QWidget, badge: QLabel) -> float:
    """Contrast between the badge's text color and its painted chip background."""
    img = host.grab().toImage()
    pos = badge.mapTo(host, badge.rect().topLeft())
    bg = img.pixelColor(pos.x() + 1, pos.y() + badge.height() // 2)
    fg = badge.palette().color(badge.foregroundRole())
    hi, lo = sorted([_luminance(fg), _luminance(bg)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("panel", ["Dark", "Light"], indirect=True)
def test_badges_are_readable(panel):
    host, p = panel
    for btn in p._action_btns:
        if btn.lbl_shortcut.isVisible():
            assert _badge_contrast(host, btn.lbl_shortcut) >= 4.5, btn._label_key
    assert _badge_contrast(host, _pay_badge(p)) >= 4.5
