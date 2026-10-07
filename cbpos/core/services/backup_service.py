"""
Backup and restore service for CB-POS data safety.

Provides AES-256 encrypted zip backups of the SQLite database,
product images, and settings. Supports restore with safety snapshot,
backup listing, retention cleanup, and verification.
"""

import logging
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pyzipper

from cbpos.config import Config

logger = logging.getLogger(__name__)

# AES-256 encryption for backup archives
_ZIP_ENCRYPTION = pyzipper.WZ_AES

# Expected files inside a valid backup
_REQUIRED_BACKUP_CONTENTS = {"cbpos.db"}

# Backup kinds and their (filename prefix, extension). Snapshots keep the
# historical "cbpos_backup_*.pre_restore.zip" name so existing ones are
# still recognised.
KIND_MANUAL = "manual"
KIND_AUTO = "auto"
KIND_SNAPSHOT = "snapshot"
_NAME_PATTERNS = {
    KIND_MANUAL: ("cbpos_backup_", ".zip"),
    KIND_AUTO: ("cbpos_auto_", ".zip"),
    KIND_SNAPSHOT: ("cbpos_backup_", ".pre_restore.zip"),
}
_TIMESTAMP_RE = re.compile(r"(\d{8}_\d{6})")


class BackupService:
    """Creates and restores AES-encrypted zip backups of the SQLite database and product images."""

    @staticmethod
    def create_backup(destination_dir: str, password: str | None, kind: str = KIND_MANUAL) -> str:
        """
        Create an AES-encrypted zip backup of the database, images, and settings.

        Args:
            destination_dir: Directory where backup zip will be saved.
            password: Encryption password (normally the shop backup password).
                Required -- a backup nobody knows the password to is useless.
            kind: KIND_MANUAL, KIND_AUTO or KIND_SNAPSHOT; decides the
                filename, and so which retention bucket the file falls into.

        Returns:
            Path of the backup file.

        Raises:
            ValueError: If no password is given or ``kind`` is unknown.
            FileNotFoundError: If database file doesn't exist.
            OSError: If backup directory can't be created.
        """
        if not password:
            raise ValueError("A backup password is required")
        if kind not in _NAME_PATTERNS:
            raise ValueError(f"Unknown backup kind: {kind}")

        db_file = Config.DATA_DIR / "cbpos.db"
        images_dir = Config.DATA_DIR / "product_images"

        if not db_file.exists():
            raise FileNotFoundError(f"Database file not found: {db_file}")

        dest = Path(destination_dir)
        dest.mkdir(parents=True, exist_ok=True)

        prefix, ext = _NAME_PATTERNS[kind]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = dest / f"{prefix}{timestamp}{ext}"

        # AESZipFile opens in "w" mode below, which truncates/overwrites
        # silently -- a second backup within the same second (e.g. a
        # scheduled backup firing right as someone clicks "Backup Now")
        # would otherwise destroy the first one with no warning.
        suffix = 1
        while backup_path.exists():
            backup_path = dest / f"{prefix}{timestamp}_{suffix}{ext}"
            suffix += 1

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
        return str(backup_path)

    @staticmethod
    def run_auto_backup(backup_dir: str, keep_count: int) -> str | None:
        """
        Make the automatic (on close) backup with the shop backup password.

        Auto-backups get their own ``cbpos_auto_*`` name and retention, so
        they can never push manual backups or safety snapshots out.

        Args:
            backup_dir: Directory for the backup.
            keep_count: How many auto-backups to keep.

        Returns:
            The backup path, or None if skipped because no shop backup
            password is set -- an archive nobody can open looks like a
            backup but can't be restored, which is worse than none.
        """
        from cbpos.core.services.config_service import ConfigService

        password = ConfigService.get_backup_password()
        if not password:
            logger.warning("Auto-backup skipped: no shop backup password set")
            return None
        path = BackupService.create_backup(backup_dir, password, kind=KIND_AUTO)
        BackupService.cleanup_old_backups(backup_dir, keep_count, kinds=(KIND_AUTO,))
        return path

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
            from cbpos.core.services.config_service import ConfigService

            if snapshot_dir is None:
                snapshot_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
            snapshot_dir = Path(snapshot_dir)
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            try:
                snapshot_path = BackupService.create_backup(
                    str(snapshot_dir), ConfigService.get_backup_password(), kind=KIND_SNAPSHOT
                )
                logger.info("Pre-restore snapshot saved: %s", snapshot_path)
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
    def backup_kind(filename: str) -> str | None:
        """Return the backup kind (manual/auto/snapshot) for a filename, or None if it isn't one."""
        if not filename.endswith(".zip"):
            return None
        if filename.startswith("cbpos_auto_"):
            return KIND_AUTO
        if filename.startswith("cbpos_backup_"):
            return KIND_SNAPSHOT if ".pre_restore" in filename else KIND_MANUAL
        return None

    @staticmethod
    def _backup_files(backup_path: Path) -> list[Path]:
        """Return every backup archive, of any kind, in a directory."""
        return [f for f in backup_path.glob("cbpos_*.zip") if f.is_file() and BackupService.backup_kind(f.name)]

    @staticmethod
    def list_backups(backup_dir: str) -> list[dict[str, object]]:
        """
        List available backup files in a directory, sorted newest first.

        Args:
            backup_dir: Directory to scan for backup files.

        Returns:
            List of dicts with keys: path, filename, date, size, type
            ("manual", "auto" or "snapshot") and is_pre_restore.
        """
        backups: list[dict[str, object]] = []
        backup_path = Path(backup_dir)

        if not backup_path.exists():
            return backups

        for f in BackupService._backup_files(backup_path):
            stat = f.stat()
            kind = BackupService.backup_kind(f.name)
            # Date from the filename's YYYYMMDD_HHMMSS, else the file time
            match = _TIMESTAMP_RE.search(f.name)
            try:
                date_obj = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S") if match else None
            except ValueError:
                date_obj = None
            if date_obj is None:
                date_obj = datetime.fromtimestamp(stat.st_mtime)
            date_str = date_obj.strftime("%Y-%m-%d %H:%M:%S")

            size_mb = stat.st_size / (1024 * 1024)
            backups.append(
                {
                    "path": str(f),
                    "filename": f.name,
                    "date": date_str,
                    "size": f"{size_mb:.1f} MB",
                    "type": kind,
                    "is_pre_restore": kind == KIND_SNAPSHOT,
                }
            )

        # Sort newest first
        backups.sort(key=lambda x: (x["date"], x["filename"]), reverse=True)
        return backups

    @staticmethod
    def last_backup_status(backups: list[dict[str, object]], password: str | None) -> dict[str, object]:
        """
        Report the newest manual/auto backup and whether the shop password opens it.

        Args:
            backups: Output of :meth:`list_backups` (newest first).
            password: The shop backup password, or None if none is set.

        Returns:
            Dict with ``date`` (str or None) and ``restorable`` (bool).
        """
        newest = next((b for b in backups if b.get("type") in (KIND_MANUAL, KIND_AUTO)), None)
        if newest is None:
            return {"date": None, "restorable": False}
        restorable = bool(password) and BackupService.verify_backup(str(newest["path"]), password)["valid"] is True
        return {"date": newest["date"], "restorable": restorable}

    @staticmethod
    def cleanup_old_backups(
        backup_dir: str,
        keep_count: int = 5,
        kinds: tuple[str, ...] = (KIND_MANUAL, KIND_AUTO, KIND_SNAPSHOT),
    ) -> int:
        """
        Delete oldest backups beyond the retention limit.

        Each kind (manual, auto, pre-restore snapshot) is retained
        separately, keeping up to ``keep_count`` most recent files, so one
        kind can never push another out. Pre-restore snapshots used to be
        excluded from cleanup entirely, so they piled up forever (#341);
        auto-backups used to share the manual bucket and delete them (#619).

        Args:
            backup_dir: Directory containing backup files.
            keep_count: Number of most recent backups to keep, per kind.
            kinds: Which kinds to clean up (auto-backup on close only
                cleans its own).

        Returns:
            Number of backups deleted.
        """
        backup_path = Path(backup_dir)
        if not backup_path.exists():
            return 0

        all_backups = BackupService._backup_files(backup_path)
        to_delete: list[Path] = []
        for kind in kinds:
            of_kind = sorted(
                (f for f in all_backups if BackupService.backup_kind(f.name) == kind),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            to_delete.extend(of_kind[keep_count:])

        deleted = 0
        for old_backup in to_delete:
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
    def verify_backup(backup_path: str, password: str) -> dict[str, object]:
        """
        Verify a backup file without extracting it.

        Args:
            backup_path: Path to the backup zip file.
            password: Decryption password.

        Returns:
            Dict with keys: valid (bool), files (list), size (str), error (str or None).
        """
        result: dict[str, object] = {
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
        result["size"] = f"{size_mb:.1f} MB"

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
