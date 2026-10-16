"""
#298: the dialog's default 800x600 size only showed 5 of the 10
permission groups (36 permission codes total) before scrolling, with no
visual hint there was more content below the fold -- reading as "lacks
a lot more permissions" even though every group was really there. Its
checkboxes are also QTreeWidgetItem.setCheckState() calls, not real
QCheckBox widgets, so they never picked up the app's themed
QCheckBox::indicator style and rendered as plain grey native squares.
"""

from pathlib import Path

import pytest

from cbpos.ui.dialogs.permission_dialog import PermissionDialog

pytestmark = pytest.mark.usefixtures("qapp")

STYLE_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


class TestDialogShowsMoreContentByDefault:
    def test_default_height_is_taller_than_the_old_600px(self, db_session):
        dialog = PermissionDialog()
        assert dialog.height() >= 700

    def test_minimum_height_is_raised_to_match(self, db_session):
        dialog = PermissionDialog()
        assert dialog.minimumHeight() >= 550


class TestTreeCheckboxesAreThemed:
    def test_dark_theme_styles_tree_widget_indicators(self):
        qss = (STYLE_DIR / "dark.qss").read_text()
        assert "QTreeWidget::indicator" in qss
        assert "QTreeWidget::indicator:indeterminate" in qss

    def test_light_theme_styles_tree_widget_indicators(self):
        qss = (STYLE_DIR / "light.qss").read_text()
        assert "QTreeWidget::indicator" in qss
        assert "QTreeWidget::indicator:indeterminate" in qss
