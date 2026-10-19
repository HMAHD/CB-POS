"""Unit test for Issue #592 [UI-027]: Layout recomputation after window restore or view switch."""

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QScrollArea

from cbpos.core.models import User
from cbpos.core.services.permission_service import PermissionService
from cbpos.ui.main_window import MainWindow
from cbpos.ui.views.dashboard_view import DashboardView
from cbpos.ui.views.management_view import ManagementView
from cbpos.ui.views.reports.report_viewer import ReportViewer
from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar

pytestmark = pytest.mark.usefixtures("qapp")


class TestLayoutRecomputation:
    @pytest.fixture(autouse=True)
    def disable_auto_refresh(self, monkeypatch):
        """Disable background data refresh threads and modal dialogs during UI geometry tests."""
        monkeypatch.setattr(DashboardView, "refresh_all", lambda self: None)
        monkeypatch.setattr("cbpos.ui.main_window.StartShiftDialog.exec", lambda self: 0)

    def test_sidebar_ignores_zero_width_on_minimize(self):
        """CollapsibleSidebar does not collapse when given zero or negative width during minimize."""
        sidebar = CollapsibleSidebar()
        sidebar.set_collapsed(False)
        assert sidebar.is_collapsed is False

        # Zero width (e.g. during minimize event) should not trigger responsive collapse
        sidebar.handle_resize(0)
        assert sidebar.is_collapsed is False

        sidebar.handle_resize(-100)
        assert sidebar.is_collapsed is False

        # Real width below breakpoint DOES trigger collapse
        sidebar.handle_resize(800)
        assert sidebar.is_collapsed is True

    def test_management_view_recomputes_on_restore_and_show(self, qapp, db_session):
        """ManagementView recomputes its layout and keeps headers visible on restore and show."""
        mgmt = ManagementView()
        mgmt.resize(1366, 768)
        mgmt.show()
        qapp.processEvents()

        assert mgmt.sidebar.width() > 0
        assert mgmt.stack.width() > 0

        # Simulate window state change (e.g. restore from minimized)
        event = QEvent(QEvent.Type.WindowStateChange)
        mgmt.changeEvent(event)
        qapp.processEvents()

        current_view = mgmt.stack.currentWidget()
        assert current_view is not None
        assert current_view.isVisible()
        assert mgmt.lbl_header_title.isVisible()
        assert mgmt.lbl_header_title.height() > 0

    def test_reports_view_switching_preserves_sidebar_scroll_and_header(self, qapp, db_session, monkeypatch):
        """Switching Reports -> Sales -> Reports 5 times keeps header, sidebar scroll and splitter intact."""
        # Allow all permissions for this test only; a bare assignment leaked "allow everything"
        # into every later test in the process (#728's menu gates then saw a cashier as admin)
        monkeypatch.setattr(PermissionService, "user_has_permission", staticmethod(lambda *args: True))

        win = MainWindow()
        win.resize(1366, 768)
        win.show()
        qapp.processEvents()

        # Login
        admin = User(id=1, username="admin", pin_hash="test", is_active=True)
        win.on_login_success(admin)
        qapp.processEvents()

        # Navigate to Management -> Reports
        win.switch_to_management()
        mgmt = win.management_view
        mgmt.switch_tab(4)  # Reports
        qapp.processEvents()

        reports = mgmt.stack.currentWidget()
        assert isinstance(reports, ReportViewer)

        # Switch between Sales and Reports 5 times
        for _ in range(5):
            win._navigate_to_pos()
            qapp.processEvents()
            win.switch_to_management()
            mgmt.switch_tab(4)
            qapp.processEvents()

        # Verify ReportViewer state
        assert reports.isVisible()
        assert mgmt.lbl_header_title.isVisible()
        assert mgmt.lbl_header_title.height() > 0

        # Splitter and sidebar scroll area
        sizes = reports.splitter.sizes()
        assert len(sizes) == 2
        assert sizes[0] >= 260, f"Reports sidebar should be at least 260px, got {sizes[0]}"
        assert sizes[1] > 0

        scroll = reports.findChild(QScrollArea, "ReportSidebarScroll")
        assert scroll is not None
        assert scroll.isVisible()
        assert scroll.width() >= 250
        assert scroll.height() > 200

        win.deleteLater()
