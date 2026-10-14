"""Startup splash (#691): shows the logo and a translated loading line."""

import pytest

from cbpos.i18n import get_language, set_language, translate_in
from cbpos.ui.startup_splash import create_startup_splash


@pytest.fixture
def restore_language():
    previous = get_language()
    yield
    set_language(previous)


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_splash_shows_translated_loading_text(qapp, restore_language, lang):
    set_language(lang)
    splash = create_startup_splash()
    try:
        assert splash.objectName() == "StartupSplash"
        assert not splash.pixmap().isNull()
        assert splash.message() == translate_in(lang, "startup.splash_loading")
        assert splash.message() != "startup.splash_loading"
    finally:
        splash.close()
        splash.deleteLater()


def test_splash_finishes_when_window_shows(qapp, qtbot):
    from PyQt6.QtWidgets import QWidget

    splash = create_startup_splash()
    splash.show()
    window = QWidget()
    window.show()
    splash.finish(window)
    qtbot.waitUntil(lambda: not splash.isVisible(), timeout=3000)
    window.close()


# --- Real startup steps on the splash (#722) ---

_STARTUP_KEYS = [
    "startup.splash_loading",
    "startup.checking_data",
    "startup.updating_data",
    "startup.preparing_screen",
    "startup.setting_up_reports",
    "startup.loading_printing",
    "startup.loading_pdf",
    "startup.loading_screens",
    "startup.preparing_counter",
    "startup.starting_sync",
    "startup.connecting_main_pc",
]


def test_status_changes_the_line_and_paints_it_now(qapp, monkeypatch):
    from cbpos.ui import startup_splash

    painted = []
    monkeypatch.setattr(startup_splash.QApplication, "processEvents", lambda *a: painted.append(True))
    splash = create_startup_splash()
    splash.show()
    try:
        startup_splash.set_startup_status("startup.checking_data")
        assert splash.message() == translate_in(get_language(), "startup.checking_data")
        assert painted
    finally:
        splash.close()


def test_status_is_a_no_op_once_the_splash_is_closed(qapp):
    from cbpos.ui import startup_splash

    splash = create_startup_splash()
    splash.show()
    splash.close()  # e.g. the setup wizard took over
    startup_splash.set_startup_status("startup.checking_data")
    assert splash.message() == translate_in(get_language(), "startup.splash_loading")


def test_status_without_a_live_splash_does_nothing(qapp):
    import gc

    from cbpos.ui import startup_splash

    splash = create_startup_splash()
    del splash
    gc.collect()
    startup_splash.set_startup_status("startup.checking_data")  # must not raise


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_every_step_fits_on_one_line_of_the_splash(qapp, lang):
    """showMessage() doesn't wrap plain text, so a long line gets cut off."""
    from PyQt6.QtGui import QFont, QFontMetrics

    from cbpos.infrastructure.resource_loader import ResourceLoader
    from cbpos.ui import startup_splash

    primary = ResourceLoader.load_fonts()
    font = QFont(primary, 11)
    font.setFamilies(ResourceLoader.get_font_families())
    metrics = QFontMetrics(font)
    room = startup_splash._SIZE[0] - 2 * 16  # leave a margin each side
    for key in _STARTUP_KEYS:
        text = translate_in(lang, key)
        assert text != key
        assert metrics.horizontalAdvance(text) <= room, (lang, key, text)
