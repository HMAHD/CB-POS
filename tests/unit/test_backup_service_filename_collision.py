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


class TestBackupFilenameCollision:
    def test_two_backups_in_the_same_second_produce_distinct_files(self, tmp_path):
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("first database content")

        backup_dir = tmp_path / "backups"
        frozen_now = datetime(2026, 1, 1, 12, 0, 0)

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            with patch("cbpos.core.services.backup_service.datetime") as mock_datetime:
                mock_datetime.now.return_value = frozen_now
                first_path, first_password = BackupService.create_backup(str(backup_dir), password="Pass1")

                db_file.write_text("second database content -- must not overwrite the first backup")
                second_path, second_password = BackupService.create_backup(str(backup_dir), password="Pass2")

        assert first_path != second_path

        with pyzipper.AESZipFile(first_path, "r") as zf:
            zf.setpassword(b"Pass1")
            with zf.open("cbpos.db") as f:
                assert f.read() == b"first database content"

        with pyzipper.AESZipFile(second_path, "r") as zf:
            zf.setpassword(b"Pass2")
            with zf.open("cbpos.db") as f:
                assert f.read() == b"second database content -- must not overwrite the first backup"
