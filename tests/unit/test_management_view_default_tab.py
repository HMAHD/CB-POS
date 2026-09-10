"""
ManagementView's 10 sub-views are built lazily by switch_tab() (#227) --
only _get_or_create_view(), called from switch_tab(), ever adds a widget
to the internal QStackedWidget. Before that change, all 10 views were
built eagerly at construction time, so QStackedWidget defaulted to
showing the first one added (Dashboard) automatically. That implicit
default silently disappeared when construction became lazy: entering
Management for the first time after a fresh app restart showed a
genuinely empty stack (count() == 0, currentWidget() is None) until the
user manually clicked a sidebar item.
"""

import pytest

from cbpos.ui.views.dashboard_view import DashboardView
from cbpos.ui.views.management_view import ManagementView

pytestmark = pytest.mark.usefixtures("qapp")


class TestManagementViewLandsOnDashboardByDefault:
    def test_stack_is_populated_immediately_after_construction(self, db_session):
        view = ManagementView()

        assert view.stack.count() > 0
        assert view.stack.currentWidget() is not None

    def test_default_tab_is_the_dashboard(self, db_session):
        view = ManagementView()

        assert isinstance(view.stack.currentWidget(), DashboardView)
