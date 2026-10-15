"""#617: Settings section headers put the divider line on the same row as
the title, at mid-text height -- in Light theme (#CCCCCC line) the title
read as struck through. The divider must sit under the title instead, so
every section reads as a heading followed by a rule.
"""

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QFrame, QLabel

from cbpos.ui.views.settings_pages import SettingsPage

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def header(qapp):
    w = SettingsPage._make_section_header("settings.hardware.section_printer_selection")
    w.resize(600, w.sizeHint().height())
    w.show()
    qapp.processEvents()
    yield w
    w.deleteLater()


def _parts(header):
    title = header.findChild(QLabel, "SettingsSectionTitle")
    line = header.findChild(QFrame, "SettingsSectionLine")
    return title, line


def test_divider_sits_below_the_title(header):
    title, line = _parts(header)

    assert line.geometry().top() >= title.geometry().bottom()


def test_divider_spans_the_full_header_width(header):
    title, line = _parts(header)

    assert line.geometry().left() == title.geometry().left()
    assert line.width() == header.contentsRect().width()


def test_light_divider_is_a_soft_rule_not_mid_grey():
    qss = (Path(__file__).resolve().parents[2] / "cbpos/ui/styles/light.qss").read_text(encoding="utf-8")
    block = qss.split("QFrame#SettingsSectionLine", 1)[1].split("}", 1)[0]

    assert "#CCCCCC" not in block.upper()
