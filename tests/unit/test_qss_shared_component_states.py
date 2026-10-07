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


def _load_for_app(theme_file: str) -> str:
    content = (STYLES_DIR / theme_file).read_text(encoding="utf-8")
    return content.replace("{{FONT_FAMILY}}", "Sans Serif").replace("{{FONT_SIZE}}", "12px")


@pytest.fixture
def themed(qapp):
    """Apply a theme's stylesheet to the app for one test, then clear it."""

    def _apply(theme_file: str) -> None:
        qapp.setStyleSheet(_load_for_app(theme_file))

    yield _apply
    qapp.setStyleSheet("")


@pytest.mark.parametrize("theme_file", THEMES)
def test_in_cell_line_edit_fills_the_row(qtbot, themed, theme_file):
    """#569: the in-cell editor must not inherit the form QLineEdit style
    (8px padding, 16px font) nor be squeezed by the ::item padding."""
    from PyQt6.QtWidgets import QLineEdit, QTableWidget, QTableWidgetItem

    themed(theme_file)
    table = QTableWidget(2, 2)
    qtbot.addWidget(table)
    for r in range(2):
        for c in range(2):
            table.setItem(r, c, QTableWidgetItem("12.500"))
    table.resize(400, 200)
    table.show()
    table.setCurrentCell(0, 1)
    table.editItem(table.item(0, 1))
    editor = table.findChild(QLineEdit)
    assert editor is not None
    editor.ensurePolished()
    assert editor.font().pixelSize() == 13
    assert editor.geometry().height() >= table.rowHeight(0) - 4
    table.closePersistentEditor(table.item(0, 1))
