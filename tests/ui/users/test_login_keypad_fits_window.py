"""
#601: the login keypad was sized from the *screen* height and its buttons'
fixed size set the window's minimum height, so on a 1366x768 display (or
any short window) the C / 0 / Enter row ended up below the window's
bottom edge -- touch-only cashiers couldn't press 0 or Enter to log in.
The keypad is now sized from the right panel's own height.
"""

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication, QWidget

from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.views.login_view import LoginView

SIZES = [(1366, 768), (1024, 768), (1280, 600), (800, 600), (1366, 700), (1600, 900), (1920, 1080)]


@pytest.fixture(params=["Dark", "Light"])
def host(qapp, monkeypatch, request):
    """A plain parent widget standing in for MainWindow's view stack, themed."""
    # LoginView registers a theme callback with no unregister API; keep it
    # out of the real (class-level) list so the view can't outlive the test.
    monkeypatch.setattr(ThemeService, "theme_change_callbacks", [])
    monkeypatch.setattr(ThemeService, "current_theme", ThemeService.current_theme)
    captured: list[str] = []
    monkeypatch.setattr(ThemeService, "_set_stylesheet", captured.append)
    ThemeService.apply_theme(request.param)

    parent = QWidget()
    # The real QSS (fonts, paddings) is what makes the heading/PIN field
    # tall enough to matter -- scoped to this widget, not the whole app.
    parent.setStyleSheet(captured[-1])
    view = LoginView()
    view.setParent(parent)
    yield parent, view
    parent.close()
    parent.deleteLater()


def _place(parent: QWidget, view: LoginView, w: int, h: int) -> None:
    parent.resize(w, h)
    view.setGeometry(0, 0, w, h)
    parent.show()
    for _ in range(3):
        QApplication.processEvents()


@pytest.mark.parametrize(("w", "h"), SIZES)
def test_whole_keypad_is_inside_the_window(host, w, h):
    parent, view = host
    _place(parent, view, w, h)

    # Inside MainWindow, the view's minimum height becomes the window's: a
    # minimum taller than the window is exactly what pushed the bottom
    # row off-screen.
    assert view.minimumSizeHint().height() <= h

    window = QRect(0, 0, w, h)
    pin_bottom = view.pin_input.mapTo(parent, view.pin_input.rect().bottomLeft()).y()
    for btn in view._numpad_buttons:
        rect = QRect(btn.mapTo(parent, btn.rect().topLeft()), btn.size())
        assert btn.isVisible()
        assert window.contains(rect), f"{btn.text()!r} at {rect.getRect()} is outside the {w}x{h} window"
        assert rect.top() > pin_bottom, "keypad squeezed up into the PIN field"
        assert btn.width() >= 56  # still a usable touch target


@pytest.mark.parametrize(("w", "h"), [(1366, 768), (1920, 1080)])
def test_keypad_keeps_full_size_when_there_is_room(host, w, h):
    parent, view = host
    _place(parent, view, w, h)
    assert view._numpad_buttons[0].width() == 110


def test_pin_group_is_vertically_centred(host):
    parent, view = host
    _place(parent, view, 1920, 1080)
    top = view.pin_heading.mapTo(view.right_panel, view.pin_heading.rect().topLeft()).y()
    bottom = view.help_hint.mapTo(view.right_panel, view.help_hint.rect().bottomLeft()).y()
    gap_above = top
    gap_below = view.right_panel.height() - bottom
    assert abs(gap_above - gap_below) <= 20


def test_footer_wraps_within_a_max_width(host):
    _parent, view = host
    assert view.footer_label.wordWrap()
    assert view.footer_label.maximumWidth() <= 420
