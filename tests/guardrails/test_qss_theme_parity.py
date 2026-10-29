"""Dark and light themes must style the same selectors.

Replaces per-screen tests that checked one selector existed in each theme.
Whether a rule *looks* right is the RELEASE_PLAN §0.7 screenshot gate.
"""

import re
from pathlib import Path

STYLES = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"

# Pre-existing gaps (2026-10-29). Fix them and remove them from here; never add to this list.
_KNOWN_DARK_ONLY = {
    "QDoubleSpinBox#DiscountValueInput:focus",
    "QGroupBox#NetworkCredentialsGroup",
    "QGroupBox#NetworkCredentialsGroup::title",
    "QWidget#CreditBookView QLabel",
    "QWidget#Sidebar",
}
_KNOWN_LIGHT_ONLY = {
    "QLabel#CardTrend",
    "QPushButton#BtnTestNetwork:pressed",
    "QTableWidget#CartTable::item",
    "QToolButton#SearchModeBtn:hover",
    "QWidget#HeaderWidget QPushButton",
    "QWidget#SearchWidget QLineEdit",
    "QWidget#SearchWidget QLineEdit:focus",
    "QWidget#SidebarContainer QLabel",
    "QWidget#SidebarContainer QPushButton",
}


def _selectors(name: str) -> set[str]:
    text = (STYLES / name).read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"\{\{[A-Z_]+\}\}", "X", text)  # template placeholders
    found = set()
    for block in re.finditer(r"([^{}]+)\{", text):
        for selector in block.group(1).split(","):
            selector = " ".join(selector.split())
            if selector:
                found.add(selector)
    return found


def test_dark_and_light_style_the_same_selectors():
    dark, light = _selectors("dark.qss"), _selectors("light.qss")
    assert (dark - light) - _KNOWN_DARK_ONLY == set(), "styled only in dark.qss"
    assert (light - dark) - _KNOWN_LIGHT_ONLY == set(), "styled only in light.qss"


def test_known_gaps_list_only_shrinks():
    dark, light = _selectors("dark.qss"), _selectors("light.qss")
    assert dark - light >= _KNOWN_DARK_ONLY, "a known gap was fixed: remove it from _KNOWN_DARK_ONLY"
    assert light - dark >= _KNOWN_LIGHT_ONLY, "a known gap was fixed: remove it from _KNOWN_LIGHT_ONLY"
