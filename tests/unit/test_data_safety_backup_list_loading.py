"""
#339: _refresh_backup_list() called BackupService.list_backups()
synchronously on the main UI thread -- the one call site on this page
that skipped the QThread/LoadingOverlay pattern already used for every
other operation here (create backup, restore, vacuum, integrity check,
export). The UI appeared to freeze with zero feedback while it scanned.

Following the same testing approach already used for this page's other
background workers (test_dashboard_worker_error_handling.py): test the
worker's run() logic directly (no real thread needed), and test the
view's finished/error callbacks directly, rather than waiting on an
actual QThread to complete in the test.
"""

from unittest.mock import MagicMock, patch

import pytest

from cbpos.ui.views.data_safety_view import DataSafetyView
from cbpos.ui.workers import BackupListWorker

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def view(qapp, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cbpos.core.services.config_service.ConfigService.get",
        lambda key: str(tmp_path) if key == "backup_dir" else None,
    )
    v = DataSafetyView()
    yield v
    v.deleteLater()


class TestBackupListWorkerRun:
    def test_run_emits_result_with_the_backup_list(self, tmp_path):
        worker = BackupListWorker(str(tmp_path))
        received = []
        worker.result.connect(lambda backups: received.append(backups))

        with patch("cbpos.core.services.backup_service.BackupService.list_backups", return_value=[{"a": 1}]):
            worker.run()

        assert received == [[{"a": 1}]]

    def test_run_emits_error_on_exception(self, tmp_path):
        worker = BackupListWorker(str(tmp_path))
        received = []
        worker.error.connect(lambda message: received.append(message))

        with patch(
            "cbpos.core.services.backup_service.BackupService.list_backups", side_effect=OSError("disk unplugged")
        ):
            worker.run()

        assert received == ["disk unplugged"]


class TestRefreshBackupListShowsLoadingOverlay:
    def test_refresh_shows_the_loading_overlay_immediately(self, view):
        view._overlay.hide_loading()

        with patch("cbpos.ui.views.data_safety_view.BackupListWorker") as mock_worker_cls:
            mock_worker_cls.return_value = MagicMock()
            view._refresh_backup_list()

        assert view._overlay.isVisibleTo(view) is True

    def test_refresh_starts_a_worker_with_the_configured_backup_dir(self, view, tmp_path):
        with patch("cbpos.ui.views.data_safety_view.BackupListWorker") as mock_worker_cls:
            fake_worker = MagicMock()
            mock_worker_cls.return_value = fake_worker
            view._refresh_backup_list()

        mock_worker_cls.assert_called_once_with(str(tmp_path))
        fake_worker.start.assert_called_once()


class TestBackupListLoadedCallback:
    def test_populates_the_table_and_hides_the_overlay(self, view):
        view._overlay.show_loading("Loading...")
        backups = [
            {"filename": "cbpos_backup_20260101_000000.zip", "date": "2026-01-01", "size": "1 MB"},
        ]

        view._on_backup_list_loaded(backups)

        assert view.backup_table.rowCount() == 1
        assert view.backup_table.item(0, 0).text() == "cbpos_backup_20260101_000000.zip"
        assert view._overlay.isVisibleTo(view) is False


class TestBackupListErrorCallback:
    def test_hides_the_overlay_without_crashing(self, view):
        view._overlay.show_loading("Loading...")

        view._on_backup_list_error("disk unplugged")

        assert view._overlay.isVisibleTo(view) is False
