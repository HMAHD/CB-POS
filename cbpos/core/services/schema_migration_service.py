"""Database schema migration service (#837).

Provides engine-agnostic schema migration and version tracking via Alembic,
with evidence-based fingerprinting for legacy unversioned databases and safety
guards against corrupt or newer schemas.
"""

import logging
from collections.abc import Callable
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.config import Config as AlembicConfig
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from cbpos.config import Config
from cbpos.core.models import Base

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Raised when a schema migration cannot proceed safely."""

    def __init__(self, code: str, detail: Any = None):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class SchemaMigrationService:
    """Manages database schema migrations and version checks."""

    # Head revision when v1.2.2 shipped (b41b19d9b69a_add_tax_id_to_customer.py).
    # v1.2.2 created tables with create_all() and no alembic_version table.
    V1_2_2_HEAD = "b41b19d9b69a"

    @classmethod
    def _get_alembic_config(cls, db_uri: str) -> AlembicConfig:
        alembic_cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_uri)
        alembic_cfg.attributes["configure_logger"] = False
        return alembic_cfg

    @classmethod
    def known_revisions(cls, db_uri: str | None = None) -> set[str]:
        """Return the set of all Alembic revision identifiers known to this codebase."""
        cfg = cls._get_alembic_config(db_uri or Config.DB_URI)
        script = ScriptDirectory.from_config(cfg)
        return {rev.revision for rev in script.walk_revisions()}

    @classmethod
    def head_revision(cls, db_uri: str | None = None) -> str | None:
        """Return the current head revision identifier in the migration scripts."""
        cfg = cls._get_alembic_config(db_uri or Config.DB_URI)
        script = ScriptDirectory.from_config(cfg)
        return script.get_current_head()

    @classmethod
    def current_revision(cls, db_uri: str) -> str | None:
        """Return the database's current stamped Alembic revision, or None if unversioned."""
        engine = create_engine(db_uri)
        try:
            inspector = inspect(engine)
            if "alembic_version" not in inspector.get_table_names():
                return None
            with engine.connect() as conn:
                context = MigrationContext.configure(conn)
                heads = context.get_current_heads()
                return heads[0] if heads else None
        finally:
            engine.dispose()

    @classmethod
    def migrate_to_head(
        cls,
        db_uri: str,
        status: Callable[[str], None] | None = None,
    ) -> None:
        """Migrate the database at db_uri to head, fingerprinting unstamped databases.

        Args:
            db_uri: SQLAlchemy connection string.
            status: Optional callback for splash status updates.

        Raises:
            MigrationError: On unsupported, corrupt, or newer database schemas.
        """
        alembic_cfg = cls._get_alembic_config(db_uri)

        try:
            engine = create_engine(db_uri)
            try:
                inspector = inspect(engine)
                table_names = set(inspector.get_table_names())
                has_version_table = "alembic_version" in table_names
                business_tables = table_names - {"alembic_version", "sqlite_sequence"}
            finally:
                engine.dispose()

            if not has_version_table:
                if not business_tables:
                    # Case 1: Brand-new empty database.
                    # create_all() is handled elsewhere; stamp at head so subsequent
                    # migrations apply cleanly.
                    command.stamp(alembic_cfg, "head")
                    logger.info("Empty database stamped at migration head.")
                    return

                # Case 2: Business tables exist, but no alembic_version table.
                # Evidence-based baseline detection.
                engine = create_engine(db_uri)
                try:
                    inspector = inspect(engine)
                    user_cols = (
                        {c["name"] for c in inspector.get_columns("users")} if "users" in business_tables else set()
                    )
                    sales_cols = (
                        {c["name"] for c in inspector.get_columns("sales")} if "sales" in business_tables else set()
                    )
                finally:
                    engine.dispose()

                # v1.2.2 fingerprint: users exists, lacks failed_login_attempts,
                # and sales lacks loyalty_points_earned.
                is_v122 = (
                    "users" in business_tables
                    and "failed_login_attempts" not in user_cols
                    and "loyalty_points_earned" not in sales_cols
                )
                if is_v122:
                    logger.info("Detected unstamped v1.2.2 database. Stamping baseline %s...", cls.V1_2_2_HEAD)
                    command.stamp(alembic_cfg, cls.V1_2_2_HEAD)
                    if status is not None:
                        status("startup.updating_data")
                    command.upgrade(alembic_cfg, "head")
                    logger.info("Database upgraded from v1.2.2 baseline to head.")
                    return

                # Check if schema matches current head Base.metadata exactly
                engine = create_engine(db_uri)
                try:
                    with engine.connect() as conn:
                        mc = MigrationContext.configure(conn)
                        diffs = compare_metadata(mc, Base.metadata)
                finally:
                    engine.dispose()

                if not diffs:
                    command.stamp(alembic_cfg, "head")
                    logger.info("Unstamped database matches current metadata; stamped at head.")
                    return

                # Unknown schema: fail closed
                logger.error("Unknown database schema with diffs: %s", diffs[:5])
                raise MigrationError("unknown_schema", diffs[:5])

            # Case 3: alembic_version table exists.
            engine = create_engine(db_uri)
            try:
                with engine.connect() as conn:
                    context = MigrationContext.configure(conn)
                    current_revs = context.get_current_heads()
            finally:
                engine.dispose()

            known = cls.known_revisions(db_uri)
            for rev in current_revs:
                if rev not in known:
                    logger.error("Database revision %s is newer than known revisions.", rev)
                    raise MigrationError("newer_version", rev)

            script = ScriptDirectory.from_config(alembic_cfg)
            head_rev = script.get_current_head()

            if not current_revs or head_rev not in current_revs:
                if status is not None:
                    status("startup.updating_data")
                command.upgrade(alembic_cfg, "head")
                logger.info("Database migrated to latest schema head.")

        except MigrationError:
            raise
        except Exception as e:
            logger.exception("Auto-migration failed: %s", e)
            raise MigrationError("migration_failed", str(e)) from e

    @classmethod
    def stamp_head(cls, db_uri: str) -> None:
        """Stamp the database at db_uri with the latest Alembic head revision."""
        alembic_cfg = cls._get_alembic_config(str(db_uri))
        command.stamp(alembic_cfg, "head")
        logger.info("Database %s stamped at head revision.", db_uri)

    @classmethod
    def pending(cls, db_uri: str) -> bool:
        """Return True if the database at db_uri requires a schema migration."""
        cur = cls.current_revision(str(db_uri))
        head = cls.head_revision(str(db_uri))
        if cur is None:
            engine = create_engine(str(db_uri))
            try:
                tables = inspect(engine).get_table_names()
                business_tables = set(tables) - {"alembic_version", "sqlite_sequence"}
                return bool(business_tables)
            finally:
                engine.dispose()
        return cur != head

    @classmethod
    def upgrade_with_lock(
        cls,
        db_uri: str,
        user_id: int | None = None,
        status: Callable[[str], None] | None = None,
    ) -> None:
        """Run schema migration to head holding an advisory lock on PostgreSQL (#799).

        On PostgreSQL: acquires session-level pg_advisory_lock(727001) on a dedicated connection,
        runs migrate_to_head, releases the lock, and logs to AuditLog.
        On SQLite: runs migrate_to_head directly and logs to AuditLog.
        """
        engine = create_engine(str(db_uri))
        is_pg = engine.dialect.name == "postgresql"

        from_rev = cls.current_revision(str(db_uri))
        head_rev = cls.head_revision(str(db_uri))

        if from_rev == head_rev and from_rev is not None:
            logger.info("Database at %s is already at head revision %s.", db_uri, head_rev)
            engine.dispose()
            return

        if is_pg:
            lock_conn = engine.connect()
            try:
                logger.info("Acquiring PostgreSQL advisory lock 727001 on %s...", db_uri)
                lock_conn.execute(text("SELECT pg_advisory_lock(727001)"))
                logger.info("Advisory lock 727001 acquired. Checking current revision under lock...")

                cur_under_lock = cls.current_revision(str(db_uri))
                if cur_under_lock == head_rev and cur_under_lock is not None:
                    logger.info("Database was already upgraded by another process to %s.", head_rev)
                    return

                cls.migrate_to_head(str(db_uri), status=status)
                to_rev = cls.current_revision(str(db_uri))
                cls._record_upgrade_audit(str(db_uri), cur_under_lock, to_rev, user_id=user_id)
            finally:
                try:
                    lock_conn.execute(text("SELECT pg_advisory_unlock(727001)"))
                    logger.info("Released PostgreSQL advisory lock 727001.")
                except Exception as e:
                    logger.warning("Error releasing pg_advisory_lock 727001: %s", e)
                lock_conn.close()
                engine.dispose()
        else:
            try:
                cls.migrate_to_head(str(db_uri), status=status)
                to_rev = cls.current_revision(str(db_uri))
                cls._record_upgrade_audit(str(db_uri), from_rev, to_rev, user_id=user_id)
            finally:
                engine.dispose()

    @classmethod
    def _record_upgrade_audit(
        cls,
        db_uri: str,
        from_rev: str | None,
        to_rev: str | None,
        user_id: int | None = None,
    ) -> None:
        """Record an AuditLog entry for a schema upgrade."""
        if from_rev == to_rev:
            return
        try:
            from cbpos.core.models import AuditLog
            from cbpos.core.services.config_service import ConfigService

            engine = create_engine(str(db_uri))
            SessionMaker = sessionmaker(bind=engine)
            with SessionMaker() as session:
                log = AuditLog(
                    user_id=user_id,
                    action="SCHEMA_UPGRADE",
                    event_type="SCHEMA",
                    terminal_id=ConfigService.get("terminal_id") or "TERM-01",
                    details=f"Upgraded schema from {from_rev} to {to_rev}",
                )
                session.add(log)
                session.commit()
            engine.dispose()
            logger.info("Recorded SCHEMA_UPGRADE audit log from %s to %s.", from_rev, to_rev)
        except Exception as e:
            logger.warning("Could not record SCHEMA_UPGRADE audit log: %s", e)

    @classmethod
    def get_schema_owner_host(cls, db_uri: str) -> str | None:
        """Query shop_meta for the designated schema owner hostname."""
        try:
            from cbpos.core.models import ShopMeta

            engine = create_engine(str(db_uri))
            inspector = inspect(engine)
            if "shop_meta" not in inspector.get_table_names():
                engine.dispose()
                return None
            SessionMaker = sessionmaker(bind=engine)
            with SessionMaker() as session:
                meta = session.get(ShopMeta, "schema_owner_host")
                host = meta.value if meta else None
            engine.dispose()
            return host
        except Exception as e:
            logger.warning("Could not query schema_owner_host from %s: %s", db_uri, e)
            return None

    @classmethod
    def set_schema_owner_host(cls, db_uri: str, host: str) -> None:
        """Persist the designated schema owner hostname to shop_meta."""
        try:
            from cbpos.core.models import ShopMeta

            engine = create_engine(str(db_uri))
            inspector = inspect(engine)
            if "shop_meta" not in inspector.get_table_names():
                from cbpos.core.models import Base

                Base.metadata.create_all(engine)
            SessionMaker = sessionmaker(bind=engine)
            with SessionMaker() as session:
                meta = session.get(ShopMeta, "schema_owner_host")
                if meta:
                    meta.value = host
                else:
                    meta = ShopMeta(key="schema_owner_host", value=host)
                    session.add(meta)
                session.commit()
            engine.dispose()
            logger.info("Updated schema_owner_host to '%s' in shop_meta.", host)
        except Exception as e:
            logger.error("Could not set schema_owner_host in %s: %s", db_uri, e)
            raise
