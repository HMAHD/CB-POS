"""Shared helpers for backup/restore tests.

Everything here works inside a pytest ``tmp_path`` -- never the real
DATA_DIR, the repo's cbpos.db, or the user's Documents folder.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from cbpos.core.services.config_service import ConfigService


def make_pos_db(path: Path, marker: str = "original") -> Path:
    """Create a small, real SQLite DB with the tables a CB POS database has."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
        conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, document_number TEXT)")
        conn.execute("CREATE TABLE sales (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO products (name) VALUES (?)", (marker,))
        conn.commit()
    finally:
        conn.close()
    return path


def read_marker(path: Path) -> str:
    """Return the marker product name written by make_pos_db()."""
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT name FROM products ORDER BY id LIMIT 1").fetchone()[0]
    finally:
        conn.close()


@contextmanager
def data_dir(tmp_path: Path):
    """Point BackupService at tmp_path and stub out the real Database singleton.

    restore_backup() disposes the real engine to release file locks;
    disposing the shared test engine would break every later test.
    """
    with (
        patch("cbpos.core.services.backup_service.Config") as mock_config,
        patch("cbpos.core.database.Database"),
    ):
        mock_config.BASE_DIR = tmp_path
        mock_config.DATA_DIR = tmp_path
        yield


def isolate_config_service(monkeypatch, tmp_path: Path) -> None:
    """Redirect ConfigService's settings, key and backup-password files into tmp_path."""
    monkeypatch.setattr(ConfigService, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(ConfigService, "_KEY_FILE", str(tmp_path / ".encryption_key"))
    monkeypatch.setattr(ConfigService, "_BACKUP_PASSWORD_FILE", str(tmp_path / ".backup_password"), raising=False)
    monkeypatch.setattr(ConfigService, "_fernet", None)
    monkeypatch.setattr(ConfigService, "_settings", {})
