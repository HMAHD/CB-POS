"""
#271: the Periodic Reports date range had no min/max bounds at all and
was never persisted. A range that ends next year or starts before the
shop existed produced a query that's technically "valid" but never
meaningfully correct, and re-picking the same range every day is
needlessly repetitive.
"""

from datetime import date

import pytest
from PyQt6.QtCore import QDate

from cbpos.core.services.config_service import ConfigService
from cbpos.ui.views.dashboard_view import DashboardView

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture
def config_store(monkeypatch):
    store = _FakeConfigStore({})
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "set", store.set)
    return store


class TestDateRangeBounds:
    def test_date_to_cannot_be_set_beyond_today(self, db_session, config_store):
        view = DashboardView()
        assert view.date_to.maximumDate() == QDate.currentDate()

    def test_date_from_cannot_be_set_beyond_today(self, db_session, config_store):
        view = DashboardView()
        assert view.date_from.maximumDate() <= QDate.currentDate()

    def test_moving_date_from_after_date_to_is_structurally_prevented(self, db_session, config_store):
        view = DashboardView()
        view.date_to.setDate(QDate(2026, 3, 15))

        view.date_from.setDate(QDate(2026, 6, 1))

        assert view.date_from.date() <= view.date_to.date()

    def test_moving_date_to_before_date_from_is_structurally_prevented(self, db_session, config_store):
        view = DashboardView()
        view.date_from.setDate(QDate(2026, 6, 1))

        view.date_to.setDate(QDate(2026, 1, 1))

        assert view.date_to.date() >= view.date_from.date()


class TestDateRangePersistence:
    def test_refreshing_saves_the_current_range(self, db_session, config_store):
        view = DashboardView()
        view.date_from.setDate(QDate(2026, 2, 1))
        view.date_to.setDate(QDate(2026, 2, 28))

        view.refresh_periodic()

        assert config_store.get("dashboard_periodic_date_from") == "2026-02-01"
        assert config_store.get("dashboard_periodic_date_to") == "2026-02-28"

    def test_a_saved_range_is_restored_on_construction(self, db_session, config_store):
        config_store.set("dashboard_periodic_date_from", "2026-03-01")
        config_store.set("dashboard_periodic_date_to", "2026-03-15")

        view = DashboardView()

        assert view.date_from.date().toPyDate() == date(2026, 3, 1)
        assert view.date_to.date().toPyDate() == date(2026, 3, 15)

    def test_no_saved_range_falls_back_to_the_existing_default(self, db_session, config_store):
        view = DashboardView()

        assert view.date_from.date().toPyDate() == date(date.today().year, 1, 1)
        assert view.date_to.date() == QDate.currentDate()
