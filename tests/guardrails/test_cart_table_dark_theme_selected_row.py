"""
Right-clicking a cart row explicitly selects it first
(SalesView.show_cart_context_menu calls self.cart_table.selectRow(row))
before showing the context menu. light.qss themes that selection
(QTableWidget#CartTable::item:selected), but dark.qss never defined the
same rule -- so in dark mode, right-clicking a cart line fell back to
Qt's unbranded default palette highlight instead of a themed one, even
though this feature's own code is what triggers the selection.
"""

from pathlib import Path

from tests.helpers.qss import rendered_qss

STYLE_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


class TestDarkThemeCartTableSelection:
    def test_cart_table_has_a_themed_selected_item_rule(self):
        qss = rendered_qss("dark.qss")
        assert "QTableWidget#CartTable::item:selected" in qss
