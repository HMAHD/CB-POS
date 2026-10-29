"""Unit test for Issue #609 [UI-040]: Dashboard content scrollable and reachable at 1366x768."""

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QScrollArea

from cbpos.ui.views.dashboard_view import DashboardView

pytestmark = pytest.mark.usefixtures("qapp")


class TestDashboardScrolling:
    @pytest.fixture(autouse=True)
    def disable_auto_refresh(self, monkeypatch):
        """Disable background data refresh threads during UI geometry tests."""
        monkeypatch.setattr(DashboardView, "refresh_all", lambda self: None)

    def test_dashboard_has_accessible_scroll_area(self, qapp):
        """Dashboard exposes a QScrollArea with widgetResizable=True."""
        view = DashboardView()
        assert hasattr(view, "scroll_area")
        assert isinstance(view.scroll_area, QScrollArea)
        assert view.scroll_area.widgetResizable() is True

    def test_dashboard_reachable_at_1366_768(self, qapp):
        """At 1366x768, all dashboard rows (including Row 4) are reachable by scrolling."""
        view = DashboardView()
        # Typical 1366x768 laptop screen leaves ~1116x680 for content pane in ManagementView
        view.resize(1116, 680)
        view.show()
        qapp.processEvents()

        scroll = view.scroll_area
        vbar = scroll.verticalScrollBar()
        assert vbar.maximum() > 0, "Dashboard content should be scrollable on 768p displays"

        # Scroll to bottom
        vbar.setValue(vbar.maximum())
        qapp.processEvents()

        # Check Row 4 panels are reachable in visible viewport
        cat_panel = view.category_chart.parentWidget()
        cust_panel = view.customer_chart.parentWidget()

        # Both panels in Row 4 should be within the scroll container and fully visible
        viewport_rect = scroll.viewport().rect()
        cat_in_viewport = cat_panel.mapTo(scroll.viewport(), QPoint(0, 0))
        cust_in_viewport = cust_panel.mapTo(scroll.viewport(), QPoint(0, 0))

        # Y position in viewport should be within viewport boundaries
        assert cat_in_viewport.y() + cat_panel.height() <= viewport_rect.bottom() + 30
        assert cust_in_viewport.y() + cust_panel.height() <= viewport_rect.bottom() + 30

    def test_wheel_events_on_charts_and_tables_scroll_dashboard(self, qapp):
        """Wheel events over charts and tables smoothly scroll the dashboard instead of being swallowed."""
        view = DashboardView()
        view.resize(1116, 600)
        view.show()
        qapp.processEvents()

        scroll = view.scroll_area
        vbar = scroll.verticalScrollBar()
        initial_val = vbar.value()
        assert vbar.maximum() > 0

        # Simulate wheel event over monthly chart
        chart = view.monthly_chart
        pt = QPointF(chart.width() / 2, chart.height() / 2)
        wheel_event = QWheelEvent(
            pt,
            chart.mapToGlobal(pt),
            QPoint(0, 0),
            QPoint(0, -120),  # Scroll down
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        qapp.sendEvent(chart, wheel_event)
        qapp.processEvents()
        assert vbar.value() > initial_val, "Wheel event over chart should scroll the dashboard"

        # Simulate wheel event over products table
        val_before_table = vbar.value()
        table = view.products_table
        pt_table = QPointF(table.width() / 2, table.height() / 2)
        wheel_event_table = QWheelEvent(
            pt_table,
            table.mapToGlobal(pt_table),
            QPoint(0, 0),
            QPoint(0, -120),  # Scroll down
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        qapp.sendEvent(table.viewport(), wheel_event_table)
        qapp.processEvents()
        assert vbar.value() > val_before_table, "Wheel event over table should scroll the dashboard"
