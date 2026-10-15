"""#629: backups copy the database with SQLite's online backup API (a
consistent snapshot, including committed data still in the WAL) instead
of zipping the live file, and Verify Backup runs off the UI thread.
"""

import sqlite3
import threading
from unittest.mock import MagicMock, patch

import pytest
import pyzipper

from cbpos.core.services.backup_service import BackupService
from cbpos.ui.views.data_safety_view import DataSafetyView
from cbpos.ui.workers import VerifyBackupWorker
from tests.unit.backup_helpers import data_dir, make_pos_db

PASSWORD = "shop-secret-42"

pytestmark = pytest.mark.usefixtures("qapp")


def _extract_db(zip_path: str, dest_dir) -> str:
    with pyzipper.AESZipFile(zip_path, "r") as zf:
        zf.setpassword(PASSWORD.encode())
        zf.extract("cbpos.db", dest_dir)
    return str(dest_dir / "cbpos.db")


def _integrity(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


class TestBackupUsesSqliteBackupApi:
    def test_committed_data_still_in_the_wal_is_in_the_backup(self, tmp_path):
        db = make_pos_db(tmp_path / "cbpos.db")
        live = sqlite3.connect(db)
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("PRAGMA wal_autocheckpoint=0")  # keep the sale in the WAL
        live.execute("INSERT INTO sales DEFAULT VALUES")
        live.commit()
        try:
            with data_dir(tmp_path):
                path = BackupService.create_backup(str(tmp_path / "backups"), PASSWORD)
        finally:
            live.close()

        out = tmp_path / "out"
        out.mkdir()
        extracted = _extract_db(path, out)
        assert _integrity(extracted) == "ok"
        conn = sqlite3.connect(extracted)
        try:
            assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 1
        finally:
            conn.close()

    def test_backup_taken_while_sales_are_being_saved_passes_integrity_check(self, tmp_path):
        db = make_pos_db(tmp_path / "cbpos.db")
        setup = sqlite3.connect(db)
        setup.execute("PRAGMA journal_mode=WAL")
        setup.close()
        stop = threading.Event()

        def write_sales() -> None:
            conn = sqlite3.connect(db, timeout=30)
            try:
                while not stop.is_set():
                    conn.execute("INSERT INTO sales DEFAULT VALUES")
                    conn.execute("INSERT INTO documents (document_number) VALUES ('INV')")
                    conn.commit()
            finally:
                conn.close()

        writer = threading.Thread(target=write_sales)
        writer.start()
        try:
            with data_dir(tmp_path):
                path = BackupService.create_backup(str(tmp_path / "backups"), PASSWORD)
        finally:
            stop.set()
            writer.join(10)

        out = tmp_path / "out"
        out.mkdir()
        assert _integrity(_extract_db(path, out)) == "ok"

    def test_no_temp_copy_left_behind(self, tmp_path):
        make_pos_db(tmp_path / "cbpos.db")
        before = set(tmp_path.iterdir())
        with data_dir(tmp_path):
            BackupService.create_backup(str(tmp_path / "backups"), PASSWORD)
        assert set(tmp_path.iterdir()) - before == {tmp_path / "backups"}


class TestVerifyRunsInAWorker:
    def test_worker_emits_the_verify_result(self, tmp_path):
        worker = VerifyBackupWorker("some.zip", PASSWORD)
        received = []
        worker.result.connect(received.append)

        with patch(
            "cbpos.core.services.backup_service.BackupService.verify_backup", return_value={"valid": True}
        ) as verify:
            worker.run()

        verify.assert_called_once_with("some.zip", PASSWORD)
        assert received == [{"valid": True}]

    @pytest.fixture
    def view(self, qapp, db_session, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "cbpos.core.services.config_service.ConfigService.get",
            lambda key: str(tmp_path) if key == "backup_dir" else None,
        )
        v = DataSafetyView()
        yield v
        v.deleteLater()

    def test_verify_starts_a_worker_and_shows_the_overlay(self, view, monkeypatch):
        worker_cls = MagicMock()
        monkeypatch.setattr("cbpos.ui.views.data_safety.restore_tab.VerifyBackupWorker", worker_cls)
        sync_verify = MagicMock()
        monkeypatch.setattr("cbpos.ui.views.data_safety.restore_tab.BackupService.verify_backup", sync_verify)
        view.restore_tab.input_restore_path.setText("/backups/cbpos_backup_20260101_000000.zip")
        view.restore_tab.input_restore_password.setText(PASSWORD)

        view.restore_tab._verify_backup()

        sync_verify.assert_not_called()
        worker_cls.assert_called_once_with("/backups/cbpos_backup_20260101_000000.zip", PASSWORD)
        worker_cls.return_value.start.assert_called_once()
        assert view._overlay.isVisibleTo(view) is True

    def test_verify_result_hides_the_overlay_and_shows_the_outcome(self, view):
        view._overlay.show_loading("...")

        view.restore_tab._on_verify_finished(
            {"valid": False, "files": [], "size": "1 MB", "error": "x", "error_code": "corrupt"}
        )

        assert view._overlay.isVisibleTo(view) is False
        assert view.restore_tab.lbl_verify_result.text()
        assert view.restore_tab.btn_verify.isEnabled()
