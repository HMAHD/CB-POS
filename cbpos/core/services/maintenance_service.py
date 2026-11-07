"""
Database maintenance service for CB-POS.

Provides VACUUM, integrity checking, and database info
for the Data Safety dialog and Admin Tools view.
"""

import logging
import sqlite3
from datetime import datetime

from sqlalchemy import func, select, table, text
from sqlalchemy.orm import joinedload

from cbpos.config import Config
from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.utils.formatters import format_bytes

logger = logging.getLogger(__name__)


class MaintenanceError(RuntimeError):
    """Raised when a maintenance operation cannot be performed."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class MaintenanceService:
    """Database maintenance operations: vacuum, integrity check, info."""

    @staticmethod
    def _require_standalone() -> None:
        from cbpos.core.services.backup_service import BackupService

        if not BackupService.is_supported():
            raise MaintenanceError("network_mode", "Maintenance operations are not supported in network database mode")

    @staticmethod
    def vacuum_database(acting_user_id: int | None = None) -> dict[str, str]:
        """
        Run VACUUM on the SQLite database to reclaim unused space.

        VACUUM requires AUTOCOMMIT isolation — it cannot run inside a transaction.

        Returns:
            Dict with size_before, size_after, saved (human-readable).
        """
        MaintenanceService._require_standalone()

        effective_actor_id = acting_user_id
        if effective_actor_id is None:
            curr = AuthService.get_current_user()
            if curr:
                effective_actor_id = curr.id

        if effective_actor_id is not None:
            db_auth = Database()
            with db_auth.get_session() as auth_session:
                user = auth_session.get(
                    User, effective_actor_id, options=[joinedload(User.role).joinedload(Role.permissions)]
                )
                if not user or not PermissionService.user_has_permission(user, Permissions.DATA_SAFETY_MAINTENANCE):
                    raise PermissionError("Permission denied: data_safety.maintenance required")

        db_path = Config.DATA_DIR / "cbpos.db"
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

        return {
            "size_before": format_bytes(size_before),
            "size_after": format_bytes(size_after),
            "saved": format_bytes(max(saved, 0)),
        }

    @staticmethod
    def get_database_info() -> dict[str, object]:
        """
        Get database file size and record counts.

        Returns:
            Dict with size, products, customers, sales counts.
        """
        MaintenanceService._require_standalone()

        db_path = Config.DATA_DIR / "cbpos.db"
        size = db_path.stat().st_size if db_path.exists() else 0

        size_str = format_bytes(size)

        info: dict[str, object] = {"size": size_str, "products": 0, "customers": 0, "sales": 0}

        db = Database()
        try:
            with db.get_session() as session:
                try:
                    row = session.execute(
                        text(
                            "SELECT (SELECT COUNT(*) FROM products), "
                            "(SELECT COUNT(*) FROM customers), "
                            "(SELECT COUNT(*) FROM sales)"
                        )
                    ).fetchone()
                    if row:
                        info["products"] = row[0] or 0
                        info["customers"] = row[1] or 0
                        info["sales"] = row[2] or 0
                except Exception as batch_e:
                    logger.debug("Batch count query failed, falling back to individual queries: %s", batch_e)
                    for key, tbl_name in [("products", "products"), ("customers", "customers"), ("sales", "sales")]:
                        try:
                            val = session.execute(text(f"SELECT COUNT(*) FROM {tbl_name}")).scalar()
                            info[key] = val or 0
                        except Exception as e:
                            logger.warning("Could not count records for table '%s': %s", tbl_name, e)
        except Exception as e:
            logger.warning("Could not query database info: %s", e)

        return info

    @staticmethod
    def get_full_database_info() -> dict[str, object]:
        """
        Get comprehensive database information for Admin Tools view.

        Returns:
            Dict with path, size, last_modified, sqlite_version,
            and tables (list of {name, rows}).
        """
        MaintenanceService._require_standalone()

        db_path = Config.DATA_DIR / "cbpos.db"
        size = db_path.stat().st_size if db_path.exists() else 0

        size_str = format_bytes(size)

        last_modified = ""
        if db_path.exists():
            mtime = db_path.stat().st_mtime
            last_modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

        sqlite_version = sqlite3.sqlite_version

        tables: list[dict[str, object]] = []
        db = Database()
        try:
            with db.get_session() as session:
                rows = session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                ).fetchall()
                non_system_tables = [r[0] for r in rows if r[0] and not r[0].startswith("sqlite_")]
                counts_by_table: dict[str, int | str] = {}
                if non_system_tables:
                    try:
                        union_sql = " UNION ALL ".join(
                            f"SELECT '{t}' AS tbl, COUNT(*) AS cnt FROM \"{t}\"" for t in non_system_tables
                        )
                        counts_by_table = dict(session.execute(text(union_sql)).fetchall())
                    except Exception as batch_e:
                        logger.debug("Batch table count failed, falling back: %s", batch_e)

                for (table_name,) in rows:
                    if table_name in counts_by_table:
                        tables.append({"name": table_name, "rows": counts_by_table[table_name] or 0})
                    else:
                        try:
                            tbl = table(table_name)
                            count = session.execute(select(func.count()).select_from(tbl)).scalar()
                            tables.append({"name": table_name, "rows": count or 0})
                        except Exception as e:
                            logger.debug("Could not count rows for table '%s': %s", table_name, e)
                            tables.append({"name": table_name, "rows": "?"})
        except Exception as e:
            logger.warning("Could not query table info: %s", e)

        return {
            "path": str(db_path),
            "size": size_str,
            "last_modified": last_modified,
            "sqlite_version": sqlite_version,
            "tables": tables,
        }

    @staticmethod
    def integrity_check(acting_user_id: int | None = None) -> tuple[bool, str]:
        """
        Run PRAGMA integrity_check on the database.

        Returns:
            Tuple of (is_ok: bool, message: str).
        """
        MaintenanceService._require_standalone()

        effective_actor_id = acting_user_id
        if effective_actor_id is None:
            curr = AuthService.get_current_user()
            if curr:
                effective_actor_id = curr.id

        if effective_actor_id is not None:
            db_auth = Database()
            with db_auth.get_session() as auth_session:
                user = auth_session.get(
                    User, effective_actor_id, options=[joinedload(User.role).joinedload(Role.permissions)]
                )
                allowed = PermissionService.user_has_any_permission(
                    user, [Permissions.DATA_SAFETY_MAINTENANCE, Permissions.ADMIN_TOOLS]
                )
                if not user or not allowed:
                    raise PermissionError("Permission denied: data_safety.maintenance or admin.tools required")

        db = Database()
        try:
            with db.get_session() as session:
                result = session.execute(text("PRAGMA integrity_check")).scalar()
                is_ok = result == "ok"
                return is_ok, result
        except Exception as e:
            return False, str(e)
