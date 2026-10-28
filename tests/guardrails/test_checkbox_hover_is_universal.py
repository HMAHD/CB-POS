"""
#319: investigated the claim that "only a few settings toggles have a
hover effect." dark.qss/light.qss's QCheckBox::indicator:hover rules
carry no objectName or class qualifier at all, and a full-repo sweep
confirms no QCheckBox anywhere calls setObjectName() on itself -- so
the rule already applies identically to every real QCheckBox. The only
non-QCheckBox check control in the app (Permission Manager's
QTreeWidgetItem.setCheckState() cells, the same root cause already
logged as #298/UX-060) already got matching QTreeWidget::indicator QSS
in a prior fix. No CSS change needed; this test locks in the premise
so a future checkbox doesn't quietly get scoped away from the rule.
"""

import re
from pathlib import Path

STYLE_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


class TestCheckboxHoverRuleIsUnqualified:
    def test_dark_theme_hover_rules_have_no_qualifier(self):
        qss = (STYLE_DIR / "dark.qss").read_text()
        assert re.search(r"(?m)^QCheckBox::indicator:unchecked:hover\s*\{", qss)
        assert re.search(r"(?m)^QCheckBox::indicator:checked:hover\s*\{", qss)

    def test_light_theme_hover_rules_have_no_qualifier(self):
        qss = (STYLE_DIR / "light.qss").read_text()
        assert re.search(r"(?m)^QCheckBox::indicator:unchecked:hover\s*\{", qss)
        assert re.search(r"(?m)^QCheckBox::indicator:checked:hover\s*\{", qss)


class TestNoCheckboxOptsOutViaObjectName:
    def test_no_checkbox_construction_line_sets_its_own_object_name(self):
        ui_dir = Path(__file__).resolve().parents[2] / "cbpos" / "ui"
        offenders = []
        for path in ui_dir.rglob("*.py"):
            text = path.read_text()
            for match in re.finditer(r"self\.(\w+)\s*=\s*QCheckBox\(", text):
                var = match.group(1)
                if re.search(rf"self\.{re.escape(var)}\.setObjectName\(", text):
                    offenders.append(f"{path}:{var}")
        assert offenders == []
