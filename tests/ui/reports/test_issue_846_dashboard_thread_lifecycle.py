"""Tests for #846: Dashboard thread lifecycle and crash prevention.

When DashboardView is re-shown or refreshed while a background load is in flight,
it must not abort (SIGABRT from destroyed running QThread), duplicate loads,
or leak threads.
"""

import threading
from unittest.mock import patch

import pytest
from PyQt6.QtGui import QShowEvent

from cbpos.core.services.dashboard_service import DashboardService
from cbpos.ui.views.dashboard_view import DashboardView, _PeriodicWorker, _YearlyWorker
from cbpos.ui.workers import running_background_jobs

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def real_dashboard_threads():
    """Ensure _YearlyWorker and _PeriodicWorker run on genuine QThreads,
    opting out of conftest's inline start-to-run override.
    """
    orig_yearly_start = _YearlyWorker.__dict__.get("start")
    orig_periodic_start = _PeriodicWorker.__dict__.get("start")
    if orig_yearly_start is not None:
        del _YearlyWorker.start
    if orig_periodic_start is not None:
        del _PeriodicWorker.start
    try:
        yield
    finally:
        if orig_yearly_start is not None:
            _YearlyWorker.start = orig_yearly_start
        elif "start" in _YearlyWorker.__dict__:
            del _YearlyWorker.start

        if orig_periodic_start is not None:
            _PeriodicWorker.start = orig_periodic_start
        elif "start" in _PeriodicWorker.__dict__:
            del _PeriodicWorker.start


def test_issue_846_refresh_twice_during_slow_load_no_crash(db_session, real_dashboard_threads, qtbot):
    """Prove real threads are used, refresh_all called while load in flight does not abort,
    coalesces safely, displays valid results, and leaves no leaked threads.
    """
    view = DashboardView()
    qtbot.addWidget(view)

    started_event = threading.Event()
    release_event = threading.Event()
    worker_threads = []

    def mock_get_monthly_sales(year):
        worker_threads.append(threading.current_thread())
        started_event.set()
        assert release_event.wait(timeout=5.0), "Worker timed out waiting for release"
        return [{"month": m, "label": f"M{m}", "total": 1000.0} for m in range(1, 13)]

    dummy_summary = {
        "total": 12000.0,
        "top_month_name": "Jan",
        "top_month_total": 1000.0,
    }

    with (
        patch.object(DashboardService, "get_monthly_sales", side_effect=mock_get_monthly_sales),
        patch.object(DashboardService, "get_yearly_summary", return_value=dummy_summary),
        patch.object(DashboardService, "get_period_top_products", return_value=[]),
        patch.object(DashboardService, "get_hourly_sales", return_value=[]),
        patch.object(
            DashboardService,
            "get_period_stats",
            return_value={"avg_order": 100.0, "items_sold": 10, "unique_customers": 5, "txn_count": 5},
        ),
        patch.object(DashboardService, "get_top_categories", return_value=[]),
        patch.object(DashboardService, "get_top_customers", return_value=[]),
        patch.object(
            DashboardService, "get_today_tax_summary", return_value={"vat": 0, "sscl": 0, "net_revenue": 1000.0}
        ),
    ):
        try:
            # 1. Trigger initial load via refresh_all
            view.refresh_all()

            # Wait until background worker actually starts
            assert started_event.wait(timeout=5.0), "Background worker failed to start"

            # PROOF: Real background thread is running, not the main UI thread
            assert len(worker_threads) >= 1
            assert worker_threads[0] is not threading.main_thread(), "Must execute on a real background thread"

            # 2. While blocked in flight, trigger a second refresh / re-show
            view.refresh_all()
            view.showEvent(QShowEvent())
        finally:
            # Release worker to complete
            release_event.set()

        # Wait for all background jobs to finish
        qtbot.waitUntil(lambda: len(running_background_jobs()) == 0, timeout=5000)
        qtbot.waitUntil(lambda: not getattr(view, "_yearly_loading", False), timeout=5000)

        # 3. Process is alive and newest valid result is displayed
        assert "12,000" in view.lbl_yearly_total.text() or "12000" in view.lbl_yearly_total.text()
        assert view.lbl_top_month.text() == "JAN"

        # 4. No leaked QThread remains
        assert len(running_background_jobs()) == 0


def test_issue_846_error_path_clears_in_flight_state_and_permits_retry(db_session, real_dashboard_threads, qtbot):
    """Error path must clear in-flight flag and allow subsequent retry."""
    view = DashboardView()
    qtbot.addWidget(view)

    # 1. Failure scenario
    with (
        patch.object(DashboardService, "get_monthly_sales", side_effect=RuntimeError("connection drop")),
        patch.object(DashboardService, "get_yearly_summary", return_value={}),
        patch.object(DashboardService, "get_period_top_products", return_value=[]),
        patch.object(DashboardService, "get_hourly_sales", return_value=[]),
        patch.object(
            DashboardService,
            "get_period_stats",
            return_value={"avg_order": 0, "items_sold": 0, "unique_customers": 0, "txn_count": 0},
        ),
        patch.object(DashboardService, "get_top_categories", return_value=[]),
        patch.object(DashboardService, "get_top_customers", return_value=[]),
        patch.object(DashboardService, "get_today_tax_summary", return_value={"vat": 0, "sscl": 0, "net_revenue": 0}),
    ):
        view.refresh_all()
        qtbot.waitUntil(lambda: not getattr(view, "_yearly_loading", False), timeout=5000)
        qtbot.waitUntil(lambda: len(running_background_jobs()) == 0, timeout=5000)
        assert getattr(view, "_yearly_loading", False) is False
        assert view.btn_prev_year.isEnabled() is True
        assert view.btn_next_year.isEnabled() is True

    # 2. Retry succeeds
    dummy_summary = {
        "total": 5000.0,
        "top_month_name": "Feb",
        "top_month_total": 5000.0,
    }
    with (
        patch.object(DashboardService, "get_monthly_sales", return_value=[]),
        patch.object(DashboardService, "get_yearly_summary", return_value=dummy_summary),
        patch.object(DashboardService, "get_period_top_products", return_value=[]),
        patch.object(DashboardService, "get_hourly_sales", return_value=[]),
        patch.object(
            DashboardService,
            "get_period_stats",
            return_value={"avg_order": 50.0, "items_sold": 5, "unique_customers": 2, "txn_count": 2},
        ),
        patch.object(DashboardService, "get_top_categories", return_value=[]),
        patch.object(DashboardService, "get_top_customers", return_value=[]),
        patch.object(
            DashboardService, "get_today_tax_summary", return_value={"vat": 0, "sscl": 0, "net_revenue": 5000.0}
        ),
    ):
        view.refresh_all()
        qtbot.waitUntil(lambda: not getattr(view, "_yearly_loading", False), timeout=5000)
        qtbot.waitUntil(lambda: len(running_background_jobs()) == 0, timeout=5000)
        assert getattr(view, "_yearly_loading", False) is False
        assert "5,000" in view.lbl_yearly_total.text() or "5000" in view.lbl_yearly_total.text()
