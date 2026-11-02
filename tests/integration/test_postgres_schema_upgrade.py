"""PostgreSQL integration tests for schema migration and advisory lock (#799)."""

import os

import pytest
from sqlalchemy import create_engine, text

from cbpos.core.models import Base
from cbpos.core.services.migration_service import MigrationService
from cbpos.core.services.schema_migration_service import SchemaMigrationService


@pytest.mark.postgres
@pytest.mark.integration
def test_issue_799_upgrade_runs_on_postgres(pg_engine):
    """Verify that SchemaMigrationService can inspect, stamp, and upgrade PostgreSQL."""
    pg_url = os.environ.get("CBPOS_TEST_PG_URL")
    assert pg_url

    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))

    Base.metadata.create_all(pg_engine)
    SchemaMigrationService.stamp_head(pg_url)

    head = SchemaMigrationService.head_revision(pg_url)
    curr = SchemaMigrationService.current_revision(pg_url)
    assert curr == head
    assert SchemaMigrationService.pending(pg_url) is False

    SchemaMigrationService.set_schema_owner_host(pg_url, "terminal-alpha")
    assert SchemaMigrationService.get_schema_owner_host(pg_url) == "terminal-alpha"

    # Upgrading when already at head under lock succeeds smoothly
    SchemaMigrationService.upgrade_with_lock(pg_url, user_id=1)


@pytest.mark.postgres
@pytest.mark.integration
def test_issue_799_copy_flow_stamps_head(pg_engine, tmp_path):
    """Verify that copying SQLite to PostgreSQL stamps alembic head on target."""
    pg_url = os.environ.get("CBPOS_TEST_PG_URL")
    assert pg_url

    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))

    sqlite_file = tmp_path / "source.db"
    sqlite_url = f"sqlite:///{sqlite_file}"
    sqlite_engine = create_engine(sqlite_url)
    Base.metadata.create_all(sqlite_engine)
    sqlite_engine.dispose()

    # Perform migration
    success, msg = MigrationService.migrate_sqlite_to_postgres(sqlite_url, pg_url)
    assert success is True, msg

    # Check stamped head
    head = SchemaMigrationService.head_revision(pg_url)
    curr = SchemaMigrationService.current_revision(pg_url)
    assert curr == head
    assert SchemaMigrationService.pending(pg_url) is False


@pytest.mark.postgres
@pytest.mark.integration
def test_issue_799_advisory_lock_serialises(pg_engine):
    """Verify PostgreSQL advisory lock 727001 blocks concurrent migration attempts."""
    pg_url = os.environ.get("CBPOS_TEST_PG_URL")
    assert pg_url

    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    Base.metadata.create_all(pg_engine)
    SchemaMigrationService.stamp_head(pg_url)

    # Open a connection holding advisory lock 727001
    holding_engine = create_engine(pg_url)
    holding_conn = holding_engine.connect()
    try:
        locked = holding_conn.execute(text("SELECT pg_try_advisory_lock(727001)")).scalar()
        assert locked is True

        # Now, trying to acquire advisory lock from another connection should fail with lock timeout
        second_engine = create_engine(pg_url)
        with second_engine.connect() as second_conn:
            # pg_try_advisory_lock from second connection returns False
            try_second = second_conn.execute(text("SELECT pg_try_advisory_lock(727001)")).scalar()
            assert try_second is False
        second_engine.dispose()

    finally:
        holding_conn.execute(text("SELECT pg_advisory_unlock(727001)"))
        holding_conn.close()
        holding_engine.dispose()
