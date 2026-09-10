"""
#342: lbl_db_path is a word-wrapped QLabel inside a QFormLayout with no
minimum width set anywhere on the label or its containing group -- the
classic QFormLayout + wrapped-QLabel sizing defect, where the field
column doesn't get allocated enough width for the wrapped text at
layout time, so only the first fragment paints visibly (e.g.
"/Users/akash/" instead of the full ".../cbpos.db" path). This is an
admin diagnostic screen whose entire purpose is letting someone confirm
exactly where their data lives.
"""

import pytest

from cbpos.ui.views.admin_tools_view import AdminToolsView

pytestmark = pytest.mark.usefixtures("qapp")


class TestDbPathLabelHasEnoughWidthToShowAFullPath:
    def test_db_path_label_has_a_realistic_minimum_width(self, db_session):
        view = AdminToolsView()
        assert view.lbl_db_path.minimumWidth() >= 350
