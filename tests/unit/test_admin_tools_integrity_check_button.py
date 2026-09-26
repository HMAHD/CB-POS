"""
#344: MaintenanceService.integrity_check() (and even IntegrityCheckWorker,
the QThread wrapper for it) already existed and worked -- IntegrityCheckWorker
was already wired up on the Data Safety screen's Maintenance section, but
never called from admin_tools_view.py, confirmed by grep. "Check Database
Integrity" is exactly the button a shop owner troubleshooting a problem on
this specific screen (Settings -> Admin Tools -> Database) would expect,
and the backend work was already done -- just add the button, reusing the
existing worker rather than duplicating it.
"""

from unittest.mock import patch

import pytest

from cbpos.ui.views.admin_tools_view import AdminToolsView

pytestmark = pytest.mark.usefixtures("qapp")


class TestDatabaseTabHasAnIntegrityCheckButton:
    def test_button_exists(self, db_session):
        view = AdminToolsView()
        assert view.btn_check_integrity is not None

    def test_clicking_starts_the_shared_integrity_check_worker(self, db_session):
        view = AdminToolsView()
        with patch("cbpos.ui.workers.IntegrityCheckWorker.start") as mock_start:
            view._check_integrity()
        mock_start.assert_called_once()
        assert view.btn_check_integrity.isEnabled() is False

    def test_passing_result_shows_a_positive_status(self, db_session):
        view = AdminToolsView()
        with patch("cbpos.ui.workers.IntegrityCheckWorker.start"):
            view._check_integrity()
        view._on_integrity_check_finished(True, "ok")
        assert view.btn_check_integrity.isEnabled() is True
        assert view.lbl_integrity_status.text() != ""

    def test_failing_result_shows_the_failure_message(self, db_session):
        view = AdminToolsView()
        with patch("cbpos.ui.workers.IntegrityCheckWorker.start"):
            view._check_integrity()
        view._on_integrity_check_finished(False, "corruption detected")
        assert "corruption detected" in view.lbl_integrity_status.text()
