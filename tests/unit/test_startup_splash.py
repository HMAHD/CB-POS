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
