"""
#391: create_backup()'s filename used a second-granularity timestamp
with no collision guard, and opened the target path in AESZipFile "w"
mode -- which truncates/overwrites silently. Two backups created within
the same second (a real scenario: an automatic scheduled backup firing
right as someone manually clicks "Backup Now") destroyed the first
backup's contents without any warning.
"""

from datetime import datetime
from unittest.mock import patch

import pyzipper

from cbpos.core.services.backup_service import BackupService
from tests.helpers.backup_helpers import make_pos_db, read_marker


def _marker_in(zip_path: str, password: bytes, out_dir) -> str:
    with pyzipper.AESZipFile(zip_path, "r") as zf:
        zf.setpassword(password)
        zf.extract("cbpos.db", out_dir)
    return read_marker(out_dir / "cbpos.db")


class TestBackupFilenameCollision:
    def test_two_backups_in_the_same_second_produce_distinct_files(self, tmp_path):
        db_file = tmp_path / "cbpos.db"
        make_pos_db(db_file, marker="first database content")

        backup_dir = tmp_path / "backups"
        frozen_now = datetime(2026, 1, 1, 12, 0, 0)

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            with patch("cbpos.core.services.backup_service.datetime") as mock_datetime:
                mock_datetime.now.return_value = frozen_now
                first_path = BackupService.create_backup(str(backup_dir), password="Pass1")

                db_file.unlink()
                make_pos_db(db_file, marker="second database content -- must not overwrite the first backup")
                second_path = BackupService.create_backup(str(backup_dir), password="Pass2")

        assert first_path != second_path

        (tmp_path / "first").mkdir()
        (tmp_path / "second").mkdir()
        assert _marker_in(first_path, b"Pass1", tmp_path / "first") == "first database content"
        assert (
            _marker_in(second_path, b"Pass2", tmp_path / "second")
            == "second database content -- must not overwrite the first backup"
        )
