"""
_YearlyWorker.run() and _PeriodicWorker.run() both wrapped their DB calls
in a bare try/except Exception: logger.exception(...) and never emitted
their finished signal on failure. Since _on_yearly_ready()/
_on_periodic_ready() were the only places that hid the loading overlay,
re-enabled the prev/next-year buttons, re-enabled the date pickers, and
reset the refresh button off its hourglass icon, a query failure left
those elements stuck exactly as they were mid-load, permanently, with no
indication anything went wrong.
"""

from datetime import date
from unittest.mock import patch

import pytest

from cbpos.ui.views.dashboard_view import DashboardView, _PeriodicWorker, _YearlyWorker

pytestmark = pytest.mark.usefixtures("qapp")


class TestWorkerEmitsErrorOnFailure:
    def test_yearly_worker_emits_error_occurred_when_service_raises(self, db_session):
        worker = _YearlyWorker(2026)
        received = []
        worker.error_occurred.connect(received.append)

        with patch(
            "cbpos.core.services.dashboard_service.DashboardService.get_monthly_sales",
            side_effect=RuntimeError("db hiccup"),
        ):
            worker.run()

        assert received == ["db hiccup"]

    def test_periodic_worker_emits_error_occurred_when_service_raises(self, db_session):
        worker = _PeriodicWorker(date(2026, 1, 1), date(2026, 1, 31))
        received = []
        worker.error_occurred.connect(received.append)

        with patch(
            "cbpos.core.services.dashboard_service.DashboardService.get_period_top_products",
            side_effect=RuntimeError("db hiccup"),
        ):
            worker.run()

        assert received == ["db hiccup"]


class TestDashboardViewRecoversFromWorkerError:
    def test_yearly_error_re_enables_year_buttons_and_hides_overlay(self, db_session):
        view = DashboardView()
        view.btn_prev_year.setEnabled(False)
        view.btn_next_year.setEnabled(False)
        view._monthly_overlay.show_loading("Loading...")

        view._on_yearly_error("db hiccup")

        assert view.btn_prev_year.isEnabled() is True
        assert view.btn_next_year.isEnabled() is True
        assert view.lbl_yearly_total.text() != ""

    def test_periodic_error_re_enables_refresh_and_date_pickers(self, db_session):
        view = DashboardView()
        view.btn_refresh.setEnabled(False)
        view.date_from.setEnabled(False)
        view.date_to.setEnabled(False)

        view._on_periodic_error("db hiccup")

        assert view.btn_refresh.isEnabled() is True
        assert view.date_from.isEnabled() is True
        assert view.date_to.isEnabled() is True
        assert view.lbl_avg_order.text() != ""
