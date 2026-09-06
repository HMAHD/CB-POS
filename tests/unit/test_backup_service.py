"""Tests for BackupService encrypted backup creation, restore, listing, and cleanup."""

import os
from pathlib import Path
from unittest.mock import patch

import pyzipper
import pytest

from cbpos.core.services.backup_service import BackupService


class TestBackupService:
    """Unit tests for BackupService."""

    def test_generate_password_length(self):
        """Test that generated passwords have correct length."""
        pwd = BackupService._generate_password(length=20)
        assert len(pwd) == 20
        assert pwd.isalnum()

    def test_generate_password_randomness(self):
        """Test that generated passwords are unique."""
        passwords = {BackupService._generate_password() for _ in range(10)}
        assert len(passwords) == 10  # All should be unique

    def test_create_backup_encrypted(self, tmp_path):
        """Test that backup creates an AES-encrypted zip file."""
        # Create mock database and settings
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("mock database content")

        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"shop_name": "test"}')

        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            path, password = BackupService.create_backup(str(backup_dir), password="TestPass123")

        assert os.path.exists(path)
        assert path.endswith(".zip")
        assert password == "TestPass123"

        # Verify it's an encrypted zip that requires password
        with pyzipper.AESZipFile(path, "r") as zf:
            zf.setpassword(b"TestPass123")
            names = zf.namelist()
            assert "cbpos.db" in names
            assert "settings.json" in names

    def test_create_backup_auto_password(self, tmp_path):
        """Test that backup auto-generates password when not provided."""
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("mock database content")

        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            path, password = BackupService.create_backup(str(backup_dir))

        assert len(password) == 16
        assert os.path.exists(path)

    def test_create_backup_missing_db_raises(self, tmp_path):
        """Test that missing database file raises FileNotFoundError."""
        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            with pytest.raises(FileNotFoundError):
                BackupService.create_backup(str(backup_dir))

    def test_create_backup_includes_images(self, tmp_path):
        """Test that product images are included in backup."""
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("mock db")

        images_dir = tmp_path / "product_images"
        images_dir.mkdir(parents=True)
        (images_dir / "test.jpg").write_text("mock image")

        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            path, password = BackupService.create_backup(str(backup_dir), password="test")

        with pyzipper.AESZipFile(path, "r") as zf:
            zf.setpassword(b"test")
            names = zf.namelist()
            assert "products/test.jpg" in names

    def test_get_default_backup_dir(self):
        """Test default backup directory path."""
        result = BackupService.get_default_backup_dir()
        assert "CB-POS-Backups" in result
        assert str(Path.home()) in result

    def test_verify_backup_valid(self, tmp_path):
        """Test verification of a valid backup."""
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("mock db content")
        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            path, password = BackupService.create_backup(str(backup_dir), password="verify123")

        result = BackupService.verify_backup(path, "verify123")
        assert result["valid"] is True
        assert "cbpos.db" in result["files"]
        assert result["error"] is None

    def test_verify_backup_wrong_password(self, tmp_path):
        """Test verification with wrong password."""
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("mock db content")
        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            path, _ = BackupService.create_backup(str(backup_dir), password="correct")

        result = BackupService.verify_backup(path, "wrong")
        assert result["valid"] is False
        assert result["error"] is not None

    def test_verify_backup_not_found(self, tmp_path):
        """Test verification of non-existent file."""
        result = BackupService.verify_backup(str(tmp_path / "nonexistent.zip"), "pwd")
        assert result["valid"] is False
        assert "not found" in result["error"]

    def test_list_backups_empty(self, tmp_path):
        """Test listing backups in empty directory."""
        result = BackupService.list_backups(str(tmp_path))
        assert result == []

    def test_list_backups_sorted(self, tmp_path):
        """Test that backups are listed newest first."""
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("mock db")
        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            BackupService.create_backup(str(backup_dir), password="test")
            import time

            time.sleep(1.1)
            BackupService.create_backup(str(backup_dir), password="test")

        result = BackupService.list_backups(str(backup_dir))
        assert len(result) == 2
        # Newest should be first
        assert result[0]["date"] >= result[1]["date"]

    def test_list_backups_nonexistent_dir(self):
        """Test listing backups in non-existent directory."""
        result = BackupService.list_backups("/nonexistent/path")
        assert result == []

    def test_cleanup_old_backups(self, tmp_path):
        """Test that cleanup deletes oldest backups beyond retention."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create 5 fake backup files with distinct timestamps
        import time

        for i in range(5):
            f = backup_dir / f"cbpos_backup_2026010{i + 1}_120000.zip"
            f.write_bytes(b"fake")
            # Set distinct mtime so sorting is deterministic
            os.utime(f, (time.time() + i, time.time() + i))

        # Keep only 2
        deleted = BackupService.cleanup_old_backups(str(backup_dir), keep_count=2)
        assert deleted == 3
        remaining = list(backup_dir.glob("cbpos_backup_*.zip"))
        assert len(remaining) == 2

    def test_cleanup_empty_dir(self, tmp_path):
        """Test cleanup on empty directory returns 0."""
        deleted = BackupService.cleanup_old_backups(str(tmp_path), keep_count=5)
        assert deleted == 0

    def test_restore_backup(self, tmp_path):
        """Test restoring a backup replaces database and settings."""
        # Setup: create original DB and settings
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("original database")
        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"original": true}')

        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            path, password = BackupService.create_backup(str(backup_dir), password="restore_test")

        # Modify the database to simulate changes
        db_file.write_text("modified database")

        with (
            patch("cbpos.core.services.backup_service.Config") as mock_config,
            # restore_backup() calls Database().engine.dispose() for real to
            # release file locks before overwriting cbpos.db (needed on
            # Windows). Database is a process-wide singleton shared with
            # every other test's db_session fixture via the same test_engine
            # -- disposing the real one here would tear down the shared
            # in-memory schema out from under every test that runs after
            # this one in the same session, however unrelated.
            patch("cbpos.core.database.Database") as mock_database_cls,
        ):
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            result = BackupService.restore_backup(path, "restore_test")

        mock_database_cls.return_value.engine.dispose.assert_called_once()

        assert result is True
        assert db_file.read_text() == "original database"

    def test_restore_backup_wrong_password(self, tmp_path):
        """Test restore with wrong password raises ValueError."""
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("mock db")
        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            path, _ = BackupService.create_backup(str(backup_dir), password="correct")

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            mock_config.DATA_DIR = tmp_path
            with pytest.raises(ValueError):
                BackupService.restore_backup(path, "wrong_password")

    def test_restore_backup_not_found(self, tmp_path):
        """Test restore of non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            BackupService.restore_backup(str(tmp_path / "missing.zip"), "pwd")
