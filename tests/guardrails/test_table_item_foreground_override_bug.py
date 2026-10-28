"""
QListWidget::item / QTableWidget::item set an explicit `color` in both
themes' QSS. Since that value merely duplicated the global QWidget default
text color, it looked harmless -- but a QSS `color` on the item selector
takes priority over a per-item setForeground()/ForegroundRole call at paint
time, so it silently defeated every "color this specific row" feature in
the app: load_users()'s red-for-inactive-user status column, and the new
Activity Log event-type color coding (#301). Confirmed live via an
offscreen render before this test was written -- colored items rendered
plain white/black regardless of setForeground().
"""

from pathlib import Path

STYLE_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


def _base_item_rule(qss: str) -> str:
    start = qss.index("QListWidget::item, QTableWidget::item {")
    end = qss.index("}", start)
    return qss[start:end]


class TestDarkTheme:
    def test_base_item_rule_does_not_hardcode_a_text_color(self):
        qss = (STYLE_DIR / "dark.qss").read_text()
        block = _base_item_rule(qss)
        assert "color:" not in block


class TestLightTheme:
    def test_base_item_rule_does_not_hardcode_a_text_color(self):
        qss = (STYLE_DIR / "light.qss").read_text()
        block = _base_item_rule(qss)
        assert "color:" not in block
