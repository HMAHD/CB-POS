"""
#286: the category panel/report-content splitter never called
setStretchFactor(), so a plain QSplitter kept its panels' proportional
ratio (~28:72) as the window resized instead of pinning the category
list to a fixed, comfortable width. On a large monitor this stretched
a panel whose actual content is short labels ("AUDIT", "Stock Movement
Audit") into far more width than it needs, starving the report
content pane on the right of the room it actually needs.
"""

import pytest

from cbpos.ui.views.reports.report_viewer import ReportViewer

pytestmark = pytest.mark.usefixtures("qapp")


class TestReportSidebarDoesNotStretch:
    def test_sidebar_pane_has_no_stretch_and_content_pane_takes_the_rest(self, db_session):
        viewer = ReportViewer()

        sidebar_stretch = viewer.splitter.widget(0).sizePolicy().horizontalStretch()
        content_stretch = viewer.splitter.widget(1).sizePolicy().horizontalStretch()
        assert sidebar_stretch == 0
        assert content_stretch == 1

    def test_sidebar_has_a_maximum_width(self, db_session):
        viewer = ReportViewer()

        assert viewer.splitter.widget(0).maximumWidth() <= 360
