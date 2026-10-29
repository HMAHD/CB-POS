"""
Qt treats a single "&" in text set on a mnemonic-sensitive widget (QPushButton,
QToolButton, QTabBar, QGroupBox, ...) as an accelerator marker: the "&" is
consumed and the next character gets an underline, instead of the "&"
being displayed. "Cut & Drawer" (a QTabBar tab label) rendered as "Cut
Drawer" with a hidden accelerator on "D" -- Qt's escape for a literal "&"
is "&&".

While fixing the reported tab label, a full sweep of every i18n string
containing a literal "&" found two more confirmed instances of the same
bug: "Close Shift & Print" (a QPushButton) and "Sales & Tax" (a
QToolButton-based sidebar nav button). Everything else that matched was
QLabel text with no buddy set, which Qt does not mnemonic-parse.
"""

import json
from pathlib import Path

import pytest

I18N_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "i18n"

MNEMONIC_AFFECTED_KEYS = [
    ("settings", "hardware", "tab_cut_drawer"),
    ("shift_closing", "close_and_print"),
    ("settings", "sidebar_sales_tax"),
]


def _get(data: dict, path: tuple[str, ...]) -> str:
    node = data
    for key in path:
        node = node[key]
    return node


@pytest.mark.parametrize("locale", ["en", "si", "ta"])
class TestMnemonicSensitiveLabelsEscapeAmpersand:
    def test_labels_on_buttons_and_tabs_use_escaped_ampersand(self, locale):
        with open(I18N_DIR / f"{locale}.json", encoding="utf-8") as fh:
            data = json.load(fh)

        for path in MNEMONIC_AFFECTED_KEYS:
            value = _get(data, path)
            assert "&&" in value, f"{'.'.join(path)} in {locale}.json has an unescaped '&': {value!r}"
