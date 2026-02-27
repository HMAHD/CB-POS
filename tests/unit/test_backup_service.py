"""Tests for BackupService encrypted backup creation."""

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
            path, password = BackupService.create_backup(str(backup_dir))

        assert len(password) == 16
        assert os.path.exists(path)

    def test_create_backup_missing_db_raises(self, tmp_path):
        """Test that missing database file raises FileNotFoundError."""
        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
            with pytest.raises(FileNotFoundError):
                BackupService.create_backup(str(backup_dir))

    def test_create_backup_includes_images(self, tmp_path):
        """Test that product images are included in backup."""
        db_file = tmp_path / "cbpos.db"
        db_file.write_text("mock db")

        images_dir = tmp_path / "cbpos" / "assets" / "products"
        images_dir.mkdir(parents=True)
        (images_dir / "test.jpg").write_text("mock image")

        backup_dir = tmp_path / "backups"

        with patch("cbpos.core.services.backup_service.Config") as mock_config:
            mock_config.BASE_DIR = tmp_path
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
