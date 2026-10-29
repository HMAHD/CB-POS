"""
Reports' results table and the Document Browser table both truncated real
data, via two different mechanisms of the same underlying bug (UX-077/#261):
Reports forced its *last* column to bloat via setStretchLastSection(True)
regardless of content; Document Browser left 4 of its 7 columns with no
resize mode at all, while also never disabling the same stretch-last-section
default, so a third column (USER) competed for space by accident too.
"""

import pandas as pd
import pytest
from PyQt6.QtWidgets import QHeaderView

from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.views.reports.report_viewer import ReportViewer

pytestmark = pytest.mark.usefixtures("qapp")


class TestReportViewerColumns:
    def test_columns_resize_to_their_own_content_not_stretch_last(self, db_session):
        viewer = ReportViewer()
        viewer.table_model.set_data(pd.DataFrame({"CATEGORY": ["Total Sales"], "AMOUNT": [500.0], "TYPE": ["Inflow"]}))
        header = viewer.table_view.horizontalHeader()

        assert header.stretchLastSection() is False
        for col in range(3):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents


class TestDocumentBrowserViewColumns:
    def test_party_column_stretches_the_rest_size_to_contents(self, db_session):
        view = DocumentBrowserView()
        header = view.doc_table.horizontalHeader()

        assert header.stretchLastSection() is False
        assert header.sectionResizeMode(3) == QHeaderView.ResizeMode.Stretch
        for col in (0, 1, 2, 4, 5, 6):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents
