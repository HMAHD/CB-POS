"""
#333 (continued): the user's original complaint was "black background
AND an emoji" under the mode icon. Fixing the emoji alone (Icons.get()
pixmap instead of a raw glyph) left the background half unfixed --
QLabel#StatusIcon never set its own background, so it fell through to
the global QWidget rule's dark background instead of inheriting its
parent QFrame#StatusCard's lighter card surface, painting a visible
mismatched box behind the icon.
"""

from pathlib import Path

from tests.helpers.qss import rendered_qss

STYLE_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


def _rule_block(qss: str, selector: str) -> str:
    start = qss.index(selector)
    end = qss.index("}", start)
    return qss[start:end]


class TestStatusIconHasATransparentBackground:
    def test_dark_theme(self):
        qss = rendered_qss("dark.qss")
        block = _rule_block(qss, "QLabel#StatusIcon {")
        assert "background" in block and "transparent" in block

    def test_light_theme(self):
        qss = rendered_qss("light.qss")
        block = _rule_block(qss, "QLabel#StatusIcon {")
        assert "background" in block and "transparent" in block
