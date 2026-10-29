"""
#254: Reports built its own custom-painted bar-chart icon
(_ReportPlaceholderIcon) + ReportEmptyText/ReportEmptySubtext labels --
one of (at least) three different empty-state implementations found
across the app, with no shared visual language between them. Reports
was the screen that triggered this review; it now uses the shared
EmptyStateWidget like the POS cart does (#257).
"""

import pytest

from cbpos.ui.views.reports.report_viewer import ReportViewer
from cbpos.ui.widgets.empty_state_widget import EmptyStateWidget

pytestmark = pytest.mark.usefixtures("qapp")


class TestReportViewerUsesTheSharedEmptyStateWidget:
    def test_empty_state_is_the_shared_widget(self, db_session):
        view = ReportViewer()
        assert isinstance(view.empty_state_widget, EmptyStateWidget)

    def test_empty_state_has_a_real_icon(self, db_session):
        view = ReportViewer()
        assert not view.empty_state_widget._icon_label.pixmap().isNull()

    def test_retranslate_sets_title_and_subtitle(self, db_session):
        view = ReportViewer()
        view.retranslate_ui()
        assert view.empty_state_widget._title_label.text() != ""
        assert view.empty_state_widget._subtitle_label.text() != ""
