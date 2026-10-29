"""#739: Settings section titles follow a live language switch.

`_make_section_header` set the title text once, and the pages'
`retranslate_ui` never touched it -- switching language with Settings open
left every section title (Printer Selection, Logo, ...) in the old language
until Settings was rebuilt.

Also: the idle-timeout tooltip said "0 = disabled", but the spin box only
takes 1-60 minutes; the "Lock screen when idle" checkbox is the off switch.
"""

import pytest
from PyQt6.QtWidgets import QLabel

from cbpos.i18n import get_language, set_language, translate_in
from cbpos.ui.views.settings_pages import HardwarePage, ReceiptPage, SystemPage

pytestmark = pytest.mark.usefixtures("qapp")

# A section title on each page that has section headers, with its i18n key.
PAGES_WITH_SECTIONS = [
    (HardwarePage, "settings.hardware.section_printer_selection"),
    (ReceiptPage, "settings.receipt.section_logo"),
]


@pytest.fixture(autouse=True)
def _restore_language():
    original = get_language()
    set_language("en")
    yield
    set_language(original)


def _section_titles(page) -> list[QLabel]:
    return page.findChildren(QLabel, "SettingsSectionTitle")


@pytest.mark.parametrize(("page_cls", "key"), PAGES_WITH_SECTIONS, ids=lambda v: getattr(v, "__name__", v))
@pytest.mark.parametrize("lang", ["si", "ta"])
def test_section_title_follows_live_language_switch(qtbot, page_cls, key, lang):
    english = translate_in("en", key)
    expected = translate_in(lang, key)
    assert expected != english  # otherwise the switch proves nothing

    page = page_cls()
    qtbot.addWidget(page)
    assert english in [lbl.text() for lbl in _section_titles(page)]

    set_language(lang)

    texts = [lbl.text() for lbl in _section_titles(page)]
    assert expected in texts
    assert english not in texts


@pytest.mark.parametrize("page_cls", [cls for cls, _ in PAGES_WITH_SECTIONS], ids=lambda c: c.__name__)
def test_no_section_title_stays_in_old_language(qtbot, page_cls):
    page = page_cls()
    qtbot.addWidget(page)
    english = [lbl.text() for lbl in _section_titles(page)]
    assert len(english) > 1

    set_language("si")
    sinhala = [lbl.text() for lbl in _section_titles(page)]
    stale = [en for en, si in zip(english, sinhala, strict=True) if en == si]
    assert not stale

    set_language("en")
    assert [lbl.text() for lbl in _section_titles(page)] == english


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_idle_timeout_tooltip_describes_real_control(qtbot, lang):
    page = SystemPage()
    qtbot.addWidget(page)
    set_language(lang)

    tip = page.spin_timeout.toolTip()
    assert (page.spin_timeout.minimum(), page.spin_timeout.maximum()) == (1, 60)
    assert "1" in tip and "60" in tip
    assert "0 =" not in tip
