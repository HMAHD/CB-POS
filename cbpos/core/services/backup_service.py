"""
Backup and restore service for CB-POS data safety.

Provides AES-256 encrypted zip backups of the SQLite database,
product images, and settings. Supports restore with safety snapshot,
backup listing, retention cleanup, and verification.
"""

import logging
import os
import secrets
import shutil
import string
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pyzipper

from cbpos.config import Config

logger = logging.getLogger(__name__)

# AES-256 encryption for backup archives
_ZIP_ENCRYPTION = pyzipper.WZ_AES

# Expected files inside a valid backup
_REQUIRED_BACKUP_CONTENTS = {"cbpos.db"}


class BackupService:
    """Creates and restores AES-encrypted zip backups of the SQLite database and product images."""

    @staticmethod
    def _generate_password(length: int = 16) -> str:
        """Generate a random password for backup encryption."""
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def create_backup(destination_dir: str, password: str = None) -> Tuple[str, str]:
        """
        Create an AES-encrypted zip backup of the database, images, and settings.

        Args:
            destination_dir: Directory where backup zip will be saved.
            password: Optional encryption password. If None, one is auto-generated.

        Returns:
            Tuple of (backup_file_path, password_used).

        Raises:
            FileNotFoundError: If database file doesn't exist.
            OSError: If backup directory can't be created.
        """
        dest = Path(destination_dir)
        dest.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"cbpos_backup_{timestamp}.zip"
        backup_path = dest / backup_name

        # AESZipFile opens in "w" mode below, which truncates/overwrites
        # silently -- a second backup within the same second (e.g. a
        # scheduled backup firing right as someone clicks "Backup Now")
        # would otherwise destroy the first one with no warning.
        suffix = 1
        while backup_path.exists():
            backup_name = f"cbpos_backup_{timestamp}_{suffix}.zip"
            backup_path = dest / backup_name
            suffix += 1

        db_file = Config.DATA_DIR / "cbpos.db"
        images_dir = Config.DATA_DIR / "product_images"

        if not db_file.exists():
            raise FileNotFoundError(f"Database file not found: {db_file}")

        if password is None:
            password = BackupService._generate_password()

        password_bytes = password.encode("utf-8")

        with pyzipper.AESZipFile(backup_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=_ZIP_ENCRYPTION) as zf:
            zf.setpassword(password_bytes)

            # Add database
            zf.write(db_file, "cbpos.db")
            logger.info("Added database to backup: %s", db_file)

            # Add product images (if directory exists)
            if images_dir.exists():
                for img_file in images_dir.rglob("*"):
                    if img_file.is_file():
                        arcname = f"products/{img_file.relative_to(images_dir)}"
                        zf.write(img_file, arcname)

            # Add settings.json
            settings_file = Config.DATA_DIR / "settings.json"
            if settings_file.exists():
                zf.write(settings_file, "settings.json")

        logger.info("Encrypted backup created: %s", backup_path)
        return str(backup_path), password

    @staticmethod
    def restore_backup(backup_path: str, password: str, snapshot_dir: str = None) -> bool:
        """
        Restore a backup by extracting and replacing the current database and assets.

        Creates a pre-restore safety snapshot before replacing files.

        Args:
            backup_path: Path to the encrypted backup zip file.
            password: Decryption password.
            snapshot_dir: Directory for the pre-restore safety snapshot.
                Defaults to the same configured backup directory every UI
                call site already resolves (``ConfigService`` override, or
                :meth:`get_default_backup_dir`). Callers should not normally
                need to pass this explicitly -- it exists mainly so tests
                can pin the snapshot to a temp directory instead of it
                silently falling back to the real default.

        Returns:
            True if restore succeeded.

        Raises:
            FileNotFoundError: If backup file doesn't exist.
            ValueError: If backup is invalid or password is wrong.
        """
        backup_file = Path(backup_path)
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        password_bytes = password.encode("utf-8")

        # Verify backup contents before extracting
        try:
            with pyzipper.AESZipFile(backup_file, "r") as zf:
                zf.setpassword(password_bytes)
                names = set(zf.namelist())
                if not _REQUIRED_BACKUP_CONTENTS.issubset(names):
                    raise ValueError("Invalid backup: missing required files (cbpos.db)")
                # Test extraction to verify password
                zf.testzip()
        except RuntimeError as e:
            raise ValueError(f"Cannot open backup — wrong password or corrupt file: {e}")

        # Create safety snapshot before restoring
        db_file = Config.DATA_DIR / "cbpos.db"
        if db_file.exists():
            if snapshot_dir is None:
                from cbpos.core.services.config_service import ConfigService

                snapshot_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
            snapshot_dir = Path(snapshot_dir)
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            try:
                snapshot_path, snapshot_pwd = BackupService.create_backup(str(snapshot_dir), password=None)
                # Rename to mark as pre-restore snapshot
                pre_restore_path = snapshot_path.replace(".zip", ".pre_restore.zip")
                os.rename(snapshot_path, pre_restore_path)
                logger.info("Pre-restore snapshot saved: %s", pre_restore_path)
            except Exception as e:
                logger.warning("Could not create pre-restore snapshot: %s", e)

        # Dispose database engine to release file locks
        from cbpos.core.database import Database

        try:
            db = Database()
            db.engine.dispose()
        except Exception as e:
            logger.error("Could not dispose database engine — restore may fail on Windows: %s", e)

        # Extract to temp directory first, then copy
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with pyzipper.AESZipFile(backup_file, "r") as zf:
                zf.setpassword(password_bytes)
                zf.extractall(tmp_path)

            # Restore database
            extracted_db = tmp_path / "cbpos.db"
            if extracted_db.exists():
                shutil.copy2(str(extracted_db), str(db_file))
                logger.info("Database restored from backup")

            # Restore settings.json
            extracted_settings = tmp_path / "settings.json"
            settings_file = Config.DATA_DIR / "settings.json"
            if extracted_settings.exists():
                shutil.copy2(str(extracted_settings), str(settings_file))
                logger.info("Settings restored from backup")

            # Restore product images
            extracted_images = tmp_path / "products"
            if extracted_images.exists():
                images_dir = Config.DATA_DIR / "product_images"
                images_dir.mkdir(parents=True, exist_ok=True)
                for img_file in extracted_images.rglob("*"):
                    if img_file.is_file():
                        dest_file = images_dir / img_file.relative_to(extracted_images)
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(img_file), str(dest_file))

        logger.info("Backup restored successfully from: %s", backup_path)
        return True

    @staticmethod
    def list_backups(backup_dir: str) -> List[Dict[str, str]]:
        """
        List available backup files in a directory, sorted newest first.

        Args:
            backup_dir: Directory to scan for backup files.

        Returns:
            List of dicts with keys: path, filename, date, size.
        """
        backups: List[Dict[str, str]] = []
        backup_path = Path(backup_dir)

        if not backup_path.exists():
            return backups

        for f in backup_path.glob("cbpos_backup_*.zip"):
            if not f.is_file():
                continue
            stat = f.stat()
            # Parse date from filename: cbpos_backup_YYYYMMDD_HHMMSS.zip
            name = f.stem  # cbpos_backup_YYYYMMDD_HHMMSS or .pre_restore
            try:
                # Handle both regular and pre_restore filenames
                date_part = name.replace("cbpos_backup_", "").split(".")[0]
                date_obj = datetime.strptime(date_part, "%Y%m%d_%H%M%S")
                date_str = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                date_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

            size_mb = stat.st_size / (1024 * 1024)
            backups.append(
                {
                    "path": str(f),
                    "filename": f.name,
                    "date": date_str,
                    "size": f"{size_mb:.1f} MB",  # noqa: E231
                    "is_pre_restore": ".pre_restore" in f.name,
                }
            )

        # Sort newest first
        backups.sort(key=lambda x: x["date"], reverse=True)
        return backups

    @staticmethod
    def cleanup_old_backups(backup_dir: str, keep_count: int = 5) -> int:
        """
        Delete oldest backups beyond the retention limit.

        Regular backups and pre-restore snapshots are retained separately,
        each keeping up to ``keep_count`` most recent files. Pre-restore
        snapshots used to be excluded from cleanup entirely, so a shop
        that ever restored from backup would accumulate them forever,
        with no way in the app to remove them (#341).

        Args:
            backup_dir: Directory containing backup files.
            keep_count: Number of most recent backups to keep, per type.

        Returns:
            Number of backups deleted.
        """
        backup_path = Path(backup_dir)
        if not backup_path.exists():
            return 0

        all_backups = list(backup_path.glob("cbpos_backup_*.zip"))
        regular_backups = sorted(
            [f for f in all_backups if ".pre_restore" not in f.name],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        pre_restore_backups = sorted(
            [f for f in all_backups if ".pre_restore" in f.name],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        deleted = 0
        for old_backup in regular_backups[keep_count:] + pre_restore_backups[keep_count:]:
            try:
                old_backup.unlink()
                logger.info("Deleted old backup: %s", old_backup)
                deleted += 1
            except OSError as e:
                logger.warning("Could not delete old backup %s: %s", old_backup, e)

        return deleted

    @staticmethod
    def delete_backup(backup_path: str) -> bool:
        """
        Permanently delete a single backup file.

        Args:
            backup_path: Full path to the backup file to delete.

        Returns:
            True if the file was deleted, False if it didn't exist or
            couldn't be removed.
        """
        path = Path(backup_path)
        if not path.exists():
            return False
        try:
            path.unlink()
            logger.info("Deleted backup: %s", path)
            return True
        except OSError as e:
            logger.warning("Could not delete backup %s: %s", path, e)
            return False

    @staticmethod
    def verify_backup(backup_path: str, password: str) -> Dict[str, object]:
        """
        Verify a backup file without extracting it.

        Args:
            backup_path: Path to the backup zip file.
            password: Decryption password.

        Returns:
            Dict with keys: valid (bool), files (list), size (str), error (str or None).
        """
        result: Dict[str, object] = {
            "valid": False,
            "files": [],
            "size": "0 MB",
            "error": None,
        }

        backup_file = Path(backup_path)
        if not backup_file.exists():
            result["error"] = "File not found"
            return result

        size_mb = backup_file.stat().st_size / (1024 * 1024)
        result["size"] = f"{size_mb:.1f} MB"  # noqa: E231

        try:
            with pyzipper.AESZipFile(backup_file, "r") as zf:
                zf.setpassword(password.encode("utf-8"))
                names = zf.namelist()
                result["files"] = names

                # Check for required files
                if not _REQUIRED_BACKUP_CONTENTS.issubset(set(names)):
                    result["error"] = "Missing required files (cbpos.db)"
                    return result

                # Test integrity
                bad_file = zf.testzip()
                if bad_file is not None:
                    result["error"] = f"Corrupt file in archive: {bad_file}"
                    return result

                result["valid"] = True
        except RuntimeError as e:
            result["error"] = f"Wrong password or corrupt archive: {e}"
        except Exception as e:
            result["error"] = f"Cannot read backup: {e}"

        return result

    @staticmethod
    def get_default_backup_dir() -> str:
        """Return default backup directory (user's Documents/CB-POS-Backups)."""
        return str(Path.home() / "Documents" / "CB-POS-Backups")
