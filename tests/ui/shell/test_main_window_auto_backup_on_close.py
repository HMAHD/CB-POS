"""#619: closing the app with auto-backup on goes through
BackupService.run_auto_backup() (shop password, own name and retention),
and says so when it had to skip because no backup password is set --
instead of silently writing an archive nobody can open.

Calls MainWindow._auto_backup_on_close() unbound on a plain QWidget, so
no full MainWindow (and none of its views/timers) is built.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QMessageBox, QWidget

from cbpos.core.services.config_service import ConfigService
from cbpos.ui.main_window import MainWindow

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def parent(qapp, tmp_path, monkeypatch):
    settings = {"backup_dir": str(tmp_path), "backup_retention_count": 3}
    monkeypatch.setattr(ConfigService, "get", staticmethod(lambda key: settings.get(key)))
    w = QWidget()
    yield w
    w.deleteLater()


def test_runs_the_auto_backup_with_configured_dir_and_retention(parent, tmp_path, monkeypatch):
    run = MagicMock(return_value=str(tmp_path / "cbpos_auto_20260101_000000.zip"))
    monkeypatch.setattr("cbpos.core.services.backup_service.BackupService.run_auto_backup", run)
    warning = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(warning))

    MainWindow._auto_backup_on_close(parent)

    run.assert_called_once_with(str(tmp_path), 3)
    warning.assert_not_called()


def test_without_a_backup_password_shows_a_notice(parent, monkeypatch):
    monkeypatch.setattr("cbpos.core.services.backup_service.BackupService.run_auto_backup", lambda d, k: None)
    warning = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(warning))

    MainWindow._auto_backup_on_close(parent)

    warning.assert_called_once()


def test_a_failing_backup_never_blocks_closing(parent, monkeypatch):
    def boom(d, k):
        raise OSError("disk full")

    monkeypatch.setattr("cbpos.core.services.backup_service.BackupService.run_auto_backup", boom)

    MainWindow._auto_backup_on_close(parent)  # must not raise


def test_issue_839_auto_backup_on_close_skipped_in_network_mode(parent, monkeypatch):
    run = MagicMock()
    monkeypatch.setattr("cbpos.core.services.backup_service.BackupService.run_auto_backup", run)
    monkeypatch.setattr("cbpos.core.services.backup_service.BackupService.is_supported", staticmethod(lambda: False))
    warning = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(warning))

    MainWindow._auto_backup_on_close(parent)

    run.assert_not_called()
    warning.assert_not_called()
