"""#619: one shop backup password for every backup, and auto-backups that
are actually restorable and never delete manual backups.

Auto-backup on close used to call create_backup() with no password and
drop the returned random one, so no auto-backup could ever be restored --
and it shared the manual backups' name and keep-5 retention, so after a
few closes the restorable manual backups were deleted too.
"""

import os
from pathlib import Path

import pytest

from cbpos.core.services.backup_service import BackupService
from cbpos.core.services.config_service import ConfigService
from tests.unit.backup_helpers import data_dir, isolate_config_service, make_pos_db, read_marker

SHOP_PASSWORD = "shop-secret-42"


@pytest.fixture
def env(tmp_path, monkeypatch):
    isolate_config_service(monkeypatch, tmp_path)
    make_pos_db(tmp_path / "cbpos.db", marker="before close")
    return tmp_path


class TestCreateBackupNeedsAPassword:
    def test_no_password_creates_no_file(self, env):
        backup_dir = env / "backups"
        with data_dir(env), pytest.raises(ValueError):
            BackupService.create_backup(str(backup_dir), password=None)
        assert not backup_dir.exists() or not any(backup_dir.iterdir())


class TestAutoBackupOnClose:
    def test_auto_backup_is_restorable_with_the_shop_password(self, env):
        ConfigService.set_backup_password(SHOP_PASSWORD)
        backup_dir = env / "backups"

        with data_dir(env):
            path = BackupService.run_auto_backup(str(backup_dir), keep_count=5)

        assert path is not None
        assert Path(path).name.startswith("cbpos_auto_")
        assert BackupService.verify_backup(path, SHOP_PASSWORD)["valid"] is True

        # And it really restores.
        (env / "cbpos.db").unlink()
        make_pos_db(env / "cbpos.db", marker="after close")
        with data_dir(env):
            BackupService.restore_backup(path, SHOP_PASSWORD, snapshot_dir=str(env / "snapshots"))
        assert read_marker(env / "cbpos.db") == "before close"

    def test_no_password_set_skips_and_creates_no_file(self, env):
        backup_dir = env / "backups"

        with data_dir(env):
            path = BackupService.run_auto_backup(str(backup_dir), keep_count=5)

        assert path is None
        assert not backup_dir.exists() or not any(backup_dir.iterdir())

    def test_ten_auto_backups_never_delete_manual_backups(self, env):
        ConfigService.set_backup_password(SHOP_PASSWORD)
        backup_dir = env / "backups"

        with data_dir(env):
            manual = [BackupService.create_backup(str(backup_dir), SHOP_PASSWORD) for _ in range(2)]
            for _ in range(10):
                BackupService.run_auto_backup(str(backup_dir), keep_count=5)

        for p in manual:
            assert os.path.exists(p)
        autos = list(backup_dir.glob("cbpos_auto_*.zip"))
        assert len(autos) == 5


class TestBackupTypes:
    def test_list_backups_labels_each_type(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        for name in (
            "cbpos_backup_20260101_120000.zip",
            "cbpos_auto_20260102_120000.zip",
            "cbpos_backup_20260103_120000.pre_restore.zip",
        ):
            (backup_dir / name).write_bytes(b"x")

        types = {b["filename"]: b["type"] for b in BackupService.list_backups(str(backup_dir))}

        assert types == {
            "cbpos_backup_20260101_120000.zip": "manual",
            "cbpos_auto_20260102_120000.zip": "auto",
            "cbpos_backup_20260103_120000.pre_restore.zip": "snapshot",
        }


class TestLastBackupStatus:
    def test_newest_backup_restorable_with_shop_password(self, env):
        ConfigService.set_backup_password(SHOP_PASSWORD)
        backup_dir = env / "backups"
        with data_dir(env):
            BackupService.run_auto_backup(str(backup_dir), keep_count=5)

        backups = BackupService.list_backups(str(backup_dir))
        status = BackupService.last_backup_status(backups, SHOP_PASSWORD)

        assert status["date"] == backups[0]["date"]
        assert status["restorable"] is True

    def test_backup_made_with_another_password_is_not_reported_restorable(self, env):
        backup_dir = env / "backups"
        with data_dir(env):
            BackupService.create_backup(str(backup_dir), "an-old-password")

        backups = BackupService.list_backups(str(backup_dir))
        status = BackupService.last_backup_status(backups, SHOP_PASSWORD)

        assert status["restorable"] is False

    def test_no_backups(self):
        assert BackupService.last_backup_status([], SHOP_PASSWORD) == {"date": None, "restorable": False}
