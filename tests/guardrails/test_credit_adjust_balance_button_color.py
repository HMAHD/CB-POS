"""
#283: "Adjust Balance" was the only one of 4 customer-detail action
buttons (Receive Payment/Print Statement/Adjust Balance/Edit Customer)
styled with the app's Warning color (#FFDC00 dark / the warning-yellow
family in light), even though it's a routine action no more dangerous
than Edit Customer sitting right next to it. Give it the same neutral
styling as Print Statement/Edit Customer.
"""

from pathlib import Path

from tests.helpers.qss import rendered_qss

STYLE_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


def _rule_block_containing(qss: str, target: str) -> str:
    for block in qss.split("}"):
        if target in block:
            return block
    raise ValueError(f"Block containing {target} not found")


class TestDarkThemeAdjustBalanceButton:
    def test_adjust_button_no_longer_uses_the_warning_color(self):
        qss = rendered_qss("dark.qss")
        block = _rule_block_containing(qss, "QPushButton#CreditAdjustBtn")
        assert "#FFDC00" not in block
        assert "#332800" not in block

    def test_adjust_button_matches_the_neutral_edit_button_colors(self):
        qss = rendered_qss("dark.qss")
        adjust_block = _rule_block_containing(qss, "QPushButton#CreditAdjustBtn")
        assert "QPushButton#CreditEditBtn" in adjust_block


class TestLightThemeAdjustBalanceButton:
    def test_adjust_button_no_longer_uses_the_warning_color(self):
        qss = rendered_qss("light.qss")
        block = _rule_block_containing(qss, "QPushButton#CreditAdjustBtn")
        assert "#FFF3CD" not in block
        assert "#856404" not in block

    def test_adjust_button_matches_the_neutral_edit_button_colors(self):
        qss = rendered_qss("light.qss")
        adjust_block = _rule_block_containing(qss, "QPushButton#CreditAdjustBtn")
        assert "QPushButton#CreditEditBtn" in adjust_block
