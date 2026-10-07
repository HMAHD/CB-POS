"""
Backup and restore service for CB-POS data safety.

Provides AES-256 encrypted zip backups of the SQLite database,
product images, and settings. Supports restore with safety snapshot,
backup listing, retention cleanup, and verification.
"""

import logging
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import pyzipper

from cbpos.config import Config
from cbpos.core.utils.formatters import format_bytes

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

# Tables every CB POS database has; a cbpos.db without them came from
# something else and must never replace the shop's data.
_EXPECTED_TABLES = {"users", "products", "documents", "sales"}


class BackupError(ValueError):
    """A backup can't be used, with a stable ``code`` the UI can translate.

    Codes: ``no_password``, ``not_a_backup``, ``wrong_password``,
    ``db_invalid``, ``snapshot_failed``, ``db_in_use``.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        """Store the code; ``detail`` is for logs only."""
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


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

        try:
            with (
                tempfile.TemporaryDirectory() as tmp_dir,
                pyzipper.AESZipFile(
                    backup_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=_ZIP_ENCRYPTION
                ) as zf,
            ):
                zf.setpassword(password_bytes)

                # Add database -- a consistent copy, never the live file (#629)
                db_copy = Path(tmp_dir) / "cbpos.db"
                BackupService._copy_database(db_file, db_copy)
                zf.write(db_copy, "cbpos.db")
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
        except BaseException:
            # Never leave a half-written archive that looks like a backup
            backup_path.unlink(missing_ok=True)
            raise

        logger.info("Encrypted backup created: %s", backup_path)
        return str(backup_path)

    @staticmethod
    def _copy_database(db_file: Path, dest: Path) -> None:
        """Copy the live database with SQLite's online backup API.

        Zipping the live file could catch it mid-write, and misses
        committed data still in the WAL. The backup API gives a
        consistent snapshot while the app keeps selling. The copy is
        switched to a plain rollback journal so it is one self-contained
        file.
        """
        src = sqlite3.connect(str(db_file), timeout=30)
        try:
            dst = sqlite3.connect(str(dest))
            try:
                src.backup(dst)
                dst.execute("PRAGMA journal_mode=DELETE")
            finally:
                dst.close()
        finally:
            src.close()

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

        Nothing is replaced until the archive has been extracted and its
        database passed ``PRAGMA integrity_check`` and has the CB POS
        tables, and a safety snapshot of the current data -- locked with
        the shop backup password, so it can itself be restored -- has been
        written. If any of that fails the restore is aborted (#628).

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
            BackupError: If the archive isn't a usable CB POS backup, the
                password is wrong, no shop backup password is set, the
                safety snapshot can't be written, or the database is in use.
                Nothing has been changed when this is raised.
        """
        from cbpos.core.services.config_service import ConfigService

        backup_file = Path(backup_path)
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        db_file = Config.DATA_DIR / "cbpos.db"

        # Extract to temp directory first and validate before touching anything
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            BackupService._open_archive(backup_file, password, extract_to=tmp_path)
            extracted_db = tmp_path / "cbpos.db"
            BackupService._validate_database(extracted_db)

            # Safety snapshot of the current data -- no snapshot, no restore
            if db_file.exists():
                snapshot_password = ConfigService.get_backup_password()
                if not snapshot_password:
                    raise BackupError("no_password", "a shop backup password is needed for the safety snapshot")
                if snapshot_dir is None:
                    snapshot_dir = ConfigService.get("backup_dir") or BackupService.get_default_backup_dir()
                try:
                    Path(snapshot_dir).mkdir(parents=True, exist_ok=True)
                    snapshot_path = BackupService.create_backup(
                        str(snapshot_dir), snapshot_password, kind=KIND_SNAPSHOT
                    )
                except Exception as e:
                    raise BackupError("snapshot_failed", str(e)) from e
                logger.info("Pre-restore snapshot saved: %s", snapshot_path)

            # Dispose database engine to release file locks
            from cbpos.core.database import Database

            try:
                db = Database()
                db.engine.dispose()
            except Exception as e:
                logger.error("Could not dispose database engine — restore may fail on Windows: %s", e)

            BackupService._replace_database(extracted_db, db_file)
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
    def _open_archive(
        backup_file: Path, password: str, extract_to: Path | None = None, members: list[str] | None = None
    ) -> list[str]:
        """Open a backup archive, check it has cbpos.db and its members read back.

        Args:
            backup_file: The archive.
            password: Its password.
            extract_to: If given, extract there (which also checks what is
                extracted); otherwise only test every member.
            members: With ``extract_to``, extract only these (default all).

        Returns:
            The archive's member names.

        Raises:
            BackupError: ``not_a_backup``, ``wrong_password`` or ``corrupt``.
        """
        opened = False
        try:
            with pyzipper.AESZipFile(backup_file, "r") as zf:
                opened = True
                zf.setpassword(password.encode("utf-8"))
                names = zf.namelist()
                if not _REQUIRED_BACKUP_CONTENTS.issubset(names):
                    raise BackupError("not_a_backup", "no cbpos.db in archive")
                if extract_to is not None:
                    zf.extractall(extract_to, members=members)
                else:
                    bad_file = zf.testzip()
                    if bad_file is not None:
                        raise BackupError("corrupt", f"bad member {bad_file}")
                return names
        except BackupError:
            raise
        except RuntimeError as e:
            # pyzipper reports a wrong password as RuntimeError
            raise BackupError("wrong_password", str(e)) from e
        except (pyzipper.BadZipFile, zipfile.BadZipFile, OSError, EOFError, ValueError) as e:
            # Failing to even open it: not a zip at all. Failing while
            # reading members: a damaged archive.
            raise BackupError("corrupt" if opened else "not_a_backup", str(e)) from e

    @staticmethod
    def _validate_database(db_path: Path) -> None:
        """Check an extracted database is healthy and really a CB POS database.

        Raises:
            BackupError: ``db_invalid`` (not SQLite, or integrity_check
                fails) or ``not_a_backup`` (missing CB POS tables).
        """
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                rows = conn.execute("PRAGMA integrity_check").fetchall()
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            finally:
                conn.close()
        except sqlite3.DatabaseError as e:
            raise BackupError("db_invalid", str(e)) from e
        if rows != [("ok",)]:
            raise BackupError("db_invalid", "; ".join(str(r[0]) for r in rows[:5]))
        missing = _EXPECTED_TABLES - tables
        if missing:
            raise BackupError("not_a_backup", f"missing tables: {sorted(missing)}")

    @staticmethod
    def _replace_database(new_db: Path, db_file: Path) -> None:
        """Swap ``new_db`` in as ``db_file`` without leaving a stale WAL behind.

        The live database runs in WAL mode. A leftover ``-wal`` file next to
        the new database would be replayed onto it and corrupt it, but it
        may also hold committed data, so it is checkpointed (never just
        deleted). If it can't be cleared, something still has the database
        open and the restore is aborted with nothing changed.

        Raises:
            BackupError: ``db_in_use``.
        """
        wal = db_file.with_name(db_file.name + "-wal")
        shm = db_file.with_name(db_file.name + "-shm")
        if wal.exists():
            try:
                conn = sqlite3.connect(str(db_file))
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    conn.close()
            except sqlite3.Error as e:
                raise BackupError("db_in_use", str(e)) from e
            if wal.exists():
                raise BackupError("db_in_use", "write-ahead log still in use")
        for side in (wal, shm):
            try:
                side.unlink(missing_ok=True)
            except OSError as e:
                raise BackupError("db_in_use", str(e)) from e

        staged = db_file.with_name(db_file.name + ".restoring")
        try:
            shutil.copy2(str(new_db), str(staged))
            os.replace(staged, db_file)
        except OSError as e:
            staged.unlink(missing_ok=True)
            raise BackupError("db_in_use", str(e)) from e

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

            backups.append(
                {
                    "path": str(f),
                    "filename": f.name,
                    "date": date_str,
                    "size": format_bytes(stat.st_size),
                    "original_size": BackupService._original_size(f),
                    "type": kind,
                    "is_pre_restore": kind == KIND_SNAPSHOT,
                }
            )

        # Sort newest first
        backups.sort(key=lambda x: (x["date"], x["filename"]), reverse=True)
        return backups

    @staticmethod
    def _original_size(backup_file: Path) -> str | None:
        """Uncompressed size of an archive's contents ("compressed from ..."), or None if unreadable.

        Read from the zip directory, which isn't encrypted, so no password is needed.
        """
        try:
            with pyzipper.AESZipFile(backup_file, "r") as zf:
                return format_bytes(sum(info.file_size for info in zf.infolist()))
        except Exception:
            return None

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
        restorable = (
            bool(password) and BackupService.verify_backup(str(newest["path"]), password, deep=False)["valid"] is True
        )
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
    def verify_backup(backup_path: str, password: str, deep: bool = True) -> dict[str, object]:
        """
        Verify a backup file without restoring it.

        Args:
            backup_path: Path to the backup zip file.
            password: Decryption password.
            deep: Also extract cbpos.db to a temp folder and run the same
                database checks a restore does (integrity_check, CB POS
                tables). False only checks the archive opens and reads back.

        Returns:
            Dict with keys: valid (bool), files (list), size (str),
            error (str or None) and error_code (BackupError code or None).
        """
        result: dict[str, object] = {
            "valid": False,
            "files": [],
            "size": "0 KB",
            "error": None,
            "error_code": None,
        }

        backup_file = Path(backup_path)
        if not backup_file.exists():
            result["error"] = "File not found"
            result["error_code"] = "not_found"
            return result

        result["size"] = format_bytes(backup_file.stat().st_size)

        try:
            result["files"] = BackupService._open_archive(backup_file, password)
            if deep:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    BackupService._open_archive(backup_file, password, Path(tmp_dir), members=["cbpos.db"])
                    BackupService._validate_database(Path(tmp_dir) / "cbpos.db")
            result["valid"] = True
        except BackupError as e:
            result["error"] = str(e)
            result["error_code"] = e.code

        return result

    @staticmethod
    def get_default_backup_dir() -> str:
        """Return default backup directory (user's Documents/CB-POS-Backups)."""
        return str(Path.home() / "Documents" / "CB-POS-Backups")
