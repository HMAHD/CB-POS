"""
Tests for Issue #597 [UI-030]:
Fix table column sizing that truncates money values and ensures text columns absorb spare width.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView

from cbpos.ui.dialogs.permission_dialog import PermissionDialog
from cbpos.ui.views.dashboard_view import DashboardView
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.views.reports.report_viewer import ReportViewer
from cbpos.ui.views.user_view import UserView

pytestmark = pytest.mark.usefixtures("qapp")


class TestDashboardProductsTableColumnSizing:
    def test_products_table_has_stretch_and_content_sizing(self, db_session):
        view = DashboardView()
        header = view.products_table.horizontalHeader()

        assert header.stretchLastSection() is False
        assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
        assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.ResizeToContents
        assert header.minimumSectionSize() >= 110

        # Verify money column header is right-aligned
        item = view.products_table.horizontalHeaderItem(1)
        assert item is not None
        assert item.textAlignment() & Qt.AlignmentFlag.AlignRight


class TestDocumentBrowserTableColumnSizing:
    def test_doc_table_has_minimum_section_size(self, db_session):
        view = DocumentBrowserView()
        header = view.doc_table.horizontalHeader()

        assert header.minimumSectionSize() >= 80
        assert header.sectionResizeMode(3) == QHeaderView.ResizeMode.Stretch
        assert header.sectionResizeMode(4) == QHeaderView.ResizeMode.ResizeToContents

    def test_line_items_table_column_modes_and_minimum_size(self, db_session):
        view = DocumentBrowserView()
        header = view.items_table.horizontalHeader()

        assert header.stretchLastSection() is False
        assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
        for col in (1, 2, 3, 4):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents
        assert header.minimumSectionSize() >= 70


class TestUserViewTableColumnSizing:
    def test_users_table_username_stretches_and_other_columns_resize_to_contents(self, db_session):
        view = UserView()
        header = view.table.horizontalHeader()

        assert header.stretchLastSection() is False
        assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents  # ID
        assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch  # Username
        assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.ResizeToContents  # Role
        assert header.sectionResizeMode(3) == QHeaderView.ResizeMode.ResizeToContents  # Status
        assert header.minimumSectionSize() >= 60


class TestPermissionDialogColumnSizing:
    def test_permission_name_stretches_and_roles_resize_to_contents(self, db_session):
        dialog = PermissionDialog()
        header = dialog.tree.header()

        assert header.stretchLastSection() is False
        assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
        for col in range(1, header.count()):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents
        assert header.minimumSectionSize() >= 80


class TestReportViewerColumnSizing:
    def test_report_header_minimum_section_size_prevents_truncation(self, db_session):
        viewer = ReportViewer()
        header = viewer.table_view.horizontalHeader()

        assert header.stretchLastSection() is False
        assert header.minimumSectionSize() >= 80
