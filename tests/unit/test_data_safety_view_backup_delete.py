"""
No per-row delete action existed anywhere in the backup list -- the only
deletion path was the bulk "Clean Old Backups" action, which explicitly
excludes pre-restore snapshots from consideration. Combined, pre-restore
snapshots could never be removed by any means built into the app.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.ui.views.data_safety_view import DataSafetyView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def view(qapp, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cbpos.core.services.config_service.ConfigService.get",
        lambda key: str(tmp_path) if key == "backup_dir" else None,
    )
    v = DataSafetyView()
    v.backup_tab._backup_data = [
        {"path": str(tmp_path / "cbpos_backup_20260101_000000.zip"), "filename": "cbpos_backup_20260101_000000.zip"},
        {
            "path": str(tmp_path / "cbpos_backup_20260102_000000.pre_restore.zip"),
            "filename": "cbpos_backup_20260102_000000.pre_restore.zip",
        },
    ]
    yield v
    v.deleteLater()


class TestDeleteBackupRow:
    def test_confirmed_delete_calls_backup_service_and_refreshes(self, view, monkeypatch):
        monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
        delete_mock = MagicMock(return_value=True)
        monkeypatch.setattr("cbpos.ui.views.data_safety.backup_tab.BackupService.delete_backup", delete_mock)
        refresh_mock = MagicMock()
        monkeypatch.setattr(view.backup_tab, "_refresh_backup_list", refresh_mock)

        view.backup_tab._delete_backup_row(0)

        delete_mock.assert_called_once_with(view.backup_tab._backup_data[0]["path"])
        refresh_mock.assert_called_once()

    def test_cancelled_confirmation_does_not_delete(self, view, monkeypatch):
        monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
        delete_mock = MagicMock()
        monkeypatch.setattr("cbpos.ui.views.data_safety.backup_tab.BackupService.delete_backup", delete_mock)

        view.backup_tab._delete_backup_row(0)

        delete_mock.assert_not_called()

    def test_works_on_a_pre_restore_row_too(self, view, monkeypatch):
        # This is the actual bug: pre-restore snapshots had no removal
        # path anywhere in the app. Row 1 in the fixture is a pre-restore
        # snapshot -- confirming this path works for it too is the point.
        monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
        delete_mock = MagicMock(return_value=True)
        monkeypatch.setattr("cbpos.ui.views.data_safety.backup_tab.BackupService.delete_backup", delete_mock)
        monkeypatch.setattr(view.backup_tab, "_refresh_backup_list", MagicMock())

        view.backup_tab._delete_backup_row(1)

        delete_mock.assert_called_once_with(view.backup_tab._backup_data[1]["path"])

    def test_failed_deletion_shows_an_error_and_does_not_crash(self, view, monkeypatch):
        monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
        monkeypatch.setattr("cbpos.ui.views.data_safety.backup_tab.BackupService.delete_backup", lambda path: False)
        critical_mock = MagicMock()
        monkeypatch.setattr(QMessageBox, "critical", staticmethod(critical_mock))

        view.backup_tab._delete_backup_row(0)

        critical_mock.assert_called_once()
