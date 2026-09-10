"""
Category Manager's tree set a fixed width on the "Category" column but
never configured a resize mode for either column -- "Products" was left
entirely to Qt's default sizing. Its sibling manager dialog,
unit_manager.py, explicitly sets Stretch for its Name column and
ResizeToContents for the rest; Category Manager was the one dialog in
this pair that skipped it, leaving the tree's true content width free to
exceed its viewport (a horizontal scrollbar, and "Products" squeezed down
to just "P").
"""

import pytest
from PyQt6.QtWidgets import QHeaderView

from cbpos.ui.dialogs.category_manager import CategoryManagerDialog

pytestmark = pytest.mark.usefixtures("qapp")


class TestCategoryManagerTreeColumns:
    def test_category_column_stretches_products_sizes_to_contents(self, db_session):
        dialog = CategoryManagerDialog()
        header = dialog.tree.header()

        assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
        assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.ResizeToContents

    def test_stretch_last_section_is_disabled(self, db_session):
        dialog = CategoryManagerDialog()
        assert dialog.tree.header().stretchLastSection() is False
