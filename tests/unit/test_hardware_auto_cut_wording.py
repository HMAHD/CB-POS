"""
#575: the Auto-Cut checkbox read "Disable for tear-bar printers", but ticking it turns
auto-cut ON. The checkbox now says what ticking does, and the tear-bar advice is a muted
hint below it, in all three languages.
"""

from unittest.mock import patch

import pytest

from cbpos.i18n import get_language, set_language, translate_in
from cbpos.ui.views.settings_pages import HardwarePage

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def page():
    original = get_language()
    with patch("cbpos.ui.views.settings_pages.QPrinterInfo.availablePrinterNames", return_value=[]):
        p = HardwarePage()
    yield p
    set_language(original)
    p.deleteLater()


def test_english_checkbox_describes_what_ticking_does(page):
    set_language("en")
    assert page.chk_auto_cut.text() == "Cut paper automatically after each receipt"
    assert page.lbl_auto_cut_hint.text() == "Turn off if your printer has no cutter"


def test_hint_is_a_muted_label_not_checkbox_text(page):
    assert page.lbl_auto_cut_hint.property("class") == "muted"
    assert "Turn off" not in page.chk_auto_cut.text()


@pytest.mark.parametrize("lang", ["si", "ta"])
def test_checkbox_and_hint_translated(page, lang):
    set_language(lang)
    chk = page.chk_auto_cut.text()
    hint = page.lbl_auto_cut_hint.text()
    assert chk == translate_in(lang, "settings.hardware.chk_auto_cut")
    assert hint == translate_in(lang, "settings.hardware.hint_auto_cut")
    assert chk != translate_in("en", "settings.hardware.chk_auto_cut")
    assert hint != translate_in("en", "settings.hardware.hint_auto_cut")
    # The "turn it off" advice belongs in the hint, never on the checkbox itself.
    turn_off = {"si": "ඕෆ්", "ta": "ஆஃப்"}[lang]
    assert turn_off not in chk
    assert turn_off in hint
