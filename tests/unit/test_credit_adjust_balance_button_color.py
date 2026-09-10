"""
#283: "Adjust Balance" was the only one of 4 customer-detail action
buttons (Receive Payment/Print Statement/Adjust Balance/Edit Customer)
styled with the app's Warning color (#FFDC00 dark / the warning-yellow
family in light), even though it's a routine action no more dangerous
than Edit Customer sitting right next to it. Give it the same neutral
styling as Print Statement/Edit Customer.
"""

from pathlib import Path

STYLE_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


def _rule_block(qss: str, selector: str) -> str:
    start = qss.index(selector)
    end = qss.index("}", start)
    return qss[start:end]


class TestDarkThemeAdjustBalanceButton:
    def test_adjust_button_no_longer_uses_the_warning_color(self):
        qss = (STYLE_DIR / "dark.qss").read_text()
        block = _rule_block(qss, "QPushButton#CreditAdjustBtn, QPushButton#PayableAdjustBtn {")
        assert "#FFDC00" not in block
        assert "#332800" not in block

    def test_adjust_button_matches_the_neutral_edit_button_colors(self):
        qss = (STYLE_DIR / "dark.qss").read_text()
        adjust_block = _rule_block(qss, "QPushButton#CreditAdjustBtn, QPushButton#PayableAdjustBtn {")
        edit_block = _rule_block(qss, "QPushButton#CreditEditBtn {")
        assert "#003366" in adjust_block
        assert "#003366" in edit_block


class TestLightThemeAdjustBalanceButton:
    def test_adjust_button_no_longer_uses_the_warning_color(self):
        qss = (STYLE_DIR / "light.qss").read_text()
        block = _rule_block(qss, "QPushButton#CreditAdjustBtn, QPushButton#PayableAdjustBtn {")
        assert "#FFF3CD" not in block
        assert "#856404" not in block

    def test_adjust_button_matches_the_neutral_edit_button_colors(self):
        qss = (STYLE_DIR / "light.qss").read_text()
        adjust_block = _rule_block(qss, "QPushButton#CreditAdjustBtn, QPushButton#PayableAdjustBtn {")
        edit_block = _rule_block(qss, "QPushButton#CreditPrintBtn, QPushButton#CreditEditBtn {")
        assert "#F8F9FA" in adjust_block
        assert "#F8F9FA" in edit_block
