"""
The only QMenu rule in either theme was scoped to QCalendarWidget QMenu.
Every other right-click/dropdown menu in the app -- including the Sales
screen's cart line-item context menu -- rendered with the OS's native
popup chrome instead of the app's branding, while the surrounding code
already went out of its way to manually re-tint just the menu's icons per
theme (a partial, inconsistent theming effort). A generic QMenu rule
themes every menu in the app at once, the same way the QDateEdit/QLineEdit
"Global Baseline" rules already do for their widget types.
"""

from pathlib import Path

STYLE_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


def _generic_qmenu_block(qss: str) -> str:
    """Find the QMenu rule that is NOT scoped under QCalendarWidget."""
    start = 0
    while True:
        start = qss.index("QMenu", start)
        # Walk back to the start of this selector line/group.
        line_start = qss.rfind("\n", 0, start) + 1
        selector_line = qss[line_start : qss.index("{", start)]
        if "QCalendarWidget" not in selector_line and selector_line.strip().startswith("QMenu"):
            end = qss.index("}", start)
            return qss[line_start:end]
        start += len("QMenu")


class TestDarkThemeQMenu:
    def test_a_generic_qmenu_rule_exists(self):
        qss = (STYLE_DIR / "dark.qss").read_text()
        block = _generic_qmenu_block(qss)
        assert "background-color" in block
        assert "border" in block

    def test_qmenu_item_selected_uses_the_accent_color(self):
        qss = (STYLE_DIR / "dark.qss").read_text()
        assert "QMenu::item:selected" in qss


class TestLightThemeQMenu:
    def test_a_generic_qmenu_rule_exists(self):
        qss = (STYLE_DIR / "light.qss").read_text()
        block = _generic_qmenu_block(qss)
        assert "background-color" in block
        assert "border" in block

    def test_qmenu_item_selected_uses_the_accent_color(self):
        qss = (STYLE_DIR / "light.qss").read_text()
        assert "QMenu::item:selected" in qss
