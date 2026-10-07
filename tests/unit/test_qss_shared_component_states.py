"""Regression tests for the shared QSS component-state rules in both themes.

These are text-level checks on dark.qss / light.qss: they pin the
specific rule bodies that the shared-component issues (#568 and friends)
fixed, so a later edit can't quietly reintroduce them.
"""

import re
from pathlib import Path

import pytest

STYLES_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"
THEMES = ("dark.qss", "light.qss")
COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _css(theme_file: str) -> str:
    return COMMENT_RE.sub("", (STYLES_DIR / theme_file).read_text(encoding="utf-8"))


def _rules_for(theme_file: str, selector: str) -> list[str]:
    """Return the body of every rule whose selector list contains `selector` exactly."""
    bodies = []
    for sel_list, body in RULE_RE.findall(_css(theme_file)):
        selectors = [" ".join(s.split()) for s in sel_list.split(",")]
        if selector in selectors:
            bodies.append(body)
    return bodies


@pytest.mark.parametrize("theme_file", THEMES)
def test_generic_selected_item_rule_has_no_border(theme_file):
    """#568: a border on ::item:selected is drawn on every cell of the row
    and elides text in ResizeToContents columns."""
    bodies = _rules_for(theme_file, "QTableWidget::item:selected")
    assert bodies, "generic selected-item rule missing"
    for body in bodies:
        assert "border" not in body
