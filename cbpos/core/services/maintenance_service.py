"""
Database maintenance service for CB-POS.

Provides VACUUM, integrity checking, and database info
for the Data Safety dialog.
"""

import logging
from typing import Dict, Tuple

from sqlalchemy import text

from cbpos.config import Config
from cbpos.core.database import Database

logger = logging.getLogger(__name__)


class MaintenanceService:
    """Database maintenance operations: vacuum, integrity check, info."""

    @staticmethod
    def vacuum_database() -> Dict[str, str]:
        """
        Run VACUUM on the SQLite database to reclaim unused space.

        VACUUM requires AUTOCOMMIT isolation — it cannot run inside a transaction.

        Returns:
            Dict with size_before, size_after, saved (human-readable).
        """
        db_path = Config.BASE_DIR / "cbpos.db"
        size_before = db_path.stat().st_size if db_path.exists() else 0

        db = Database()
        # VACUUM must run outside a transaction — use raw connection with autocommit
        raw_conn = db.engine.raw_connection()
        try:
            raw_conn.execute("VACUUM")
        finally:
            raw_conn.close()

        size_after = db_path.stat().st_size if db_path.exists() else 0
        saved = size_before - size_after

        def _fmt(size: int) -> str:
            if size >= 1024 * 1024:
                return f"{size / (1024 * 1024):.1f} MB"
            return f"{size / 1024:.1f} KB"

        return {
            "size_before": _fmt(size_before),
            "size_after": _fmt(size_after),
            "saved": _fmt(max(saved, 0)),
        }

    @staticmethod
    def get_database_info() -> Dict[str, object]:
        """
        Get database file size and record counts.

        Returns:
            Dict with size, products, customers, sales counts.
        """
        db_path = Config.BASE_DIR / "cbpos.db"
        size = db_path.stat().st_size if db_path.exists() else 0

        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{size / 1024:.1f} KB"

        info: Dict[str, object] = {"size": size_str, "products": 0, "customers": 0, "sales": 0}

        db = Database()
        try:
            with db.get_session() as session:
                # Use raw SQL for speed — these tables always exist
                for key, table in [("products", "products"), ("customers", "customers"), ("sales", "sales")]:
                    try:
                        row = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                        info[key] = row or 0
                    except Exception as e:
                        logger.warning("Could not count records for table '%s': %s", table, e)
        except Exception as e:
            logger.warning("Could not query database info: %s", e)

        return info

    @staticmethod
    def integrity_check() -> Tuple[bool, str]:
        """
        Run PRAGMA integrity_check on the database.

        Returns:
            Tuple of (is_ok: bool, message: str).
        """
        db = Database()
        try:
            with db.get_session() as session:
                result = session.execute(text("PRAGMA integrity_check")).scalar()
                is_ok = result == "ok"
                return is_ok, result
        except Exception as e:
            return False, str(e)
