"""Tests for SchemaMigrationService (#837)."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from cbpos.core.models import Base
from cbpos.core.services.schema_migration_service import (
    MigrationError,
    SchemaMigrationService,
)
from tests.fixtures.models_v122 import Base as BaseV122


@pytest.mark.domain
def test_issue_837_empty_db_is_stamped_head(tmp_path):
    """An empty database with no tables is stamped directly at head."""
    db_file = tmp_path / "empty.db"
    # Create empty sqlite file
    create_engine(f"sqlite:///{db_file}").dispose()
    db_uri = f"sqlite:///{db_file}"

    SchemaMigrationService.migrate_to_head(db_uri)

    head = SchemaMigrationService.head_revision(db_uri)
    curr = SchemaMigrationService.current_revision(db_uri)
    assert curr == head
    assert curr is not None


@pytest.mark.domain
def test_issue_837_unstamped_v122_db_upgrades_to_head(tmp_path):
    """An unstamped DB from v1.2.2 models is stamped at v1.2.2 head and upgraded to head."""
    db_file = tmp_path / "v122.db"
    db_uri = f"sqlite:///{db_file}"
    engine = create_engine(db_uri)
    BaseV122.metadata.create_all(engine)
    engine.dispose()

    # Pre-condition: unstamped, has tables
    assert SchemaMigrationService.current_revision(db_uri) is None
    engine = create_engine(db_uri)
    insp = inspect(engine)
    assert "users" in insp.get_table_names()
    user_cols = {c["name"] for c in insp.get_columns("users")}
    assert "failed_login_attempts" not in user_cols
    engine.dispose()

    # Run migration
    SchemaMigrationService.migrate_to_head(db_uri)

    # Post-condition: at head revision and schema matches current Base.metadata
    head = SchemaMigrationService.head_revision(db_uri)
    curr = SchemaMigrationService.current_revision(db_uri)
    assert curr == head

    engine = create_engine(db_uri)
    with engine.connect() as conn:
        mc = MigrationContext.configure(conn)
        diffs = compare_metadata(mc, Base.metadata)
    engine.dispose()

    assert diffs == []


@pytest.mark.domain
def test_issue_837_unstamped_current_schema_is_stamped_head(tmp_path):
    """An unstamped DB created with current Base.metadata.create_all is stamped at head without error."""
    db_file = tmp_path / "current_unstamped.db"
    db_uri = f"sqlite:///{db_file}"
    engine = create_engine(db_uri)
    Base.metadata.create_all(engine)
    engine.dispose()

    assert SchemaMigrationService.current_revision(db_uri) is None

    SchemaMigrationService.migrate_to_head(db_uri)

    head = SchemaMigrationService.head_revision(db_uri)
    curr = SchemaMigrationService.current_revision(db_uri)
    assert curr == head


@pytest.mark.domain
def test_issue_837_unknown_schema_raises(tmp_path):
    """An unrecognised schema with tables missing or altered raises MigrationError('unknown_schema')."""
    db_file = tmp_path / "unknown.db"
    db_uri = f"sqlite:///{db_file}"
    engine = create_engine(db_uri)
    # Create subset of tables so schema does not match current and does not match v1.2.2
    for t in Base.metadata.sorted_tables:
        if t.name in ("users", "products"):
            t.create(engine)
    engine.dispose()

    # Note: users here has current columns like failed_login_attempts, but missing 35+ other tables
    with pytest.raises(MigrationError) as exc_info:
        SchemaMigrationService.migrate_to_head(db_uri)

    assert exc_info.value.code == "unknown_schema"
    # Ensure it did not stamp or modify
    assert SchemaMigrationService.current_revision(db_uri) is None


@pytest.mark.domain
def test_issue_837_newer_version_raises(tmp_path):
    """A database stamped at an unknown (future) revision raises MigrationError('newer_version')."""
    from alembic.config import Config as AlembicConfig

    from cbpos.config import Config

    db_file = tmp_path / "future.db"
    db_uri = f"sqlite:///{db_file}"
    alembic_cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_uri)
    alembic_cfg.attributes["configure_logger"] = False

    # Create alembic_version with future revision
    engine = create_engine(db_uri)
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        conn.exec_driver_sql("INSERT INTO alembic_version (version_num) VALUES ('f9e8d7c6b5a4')")
    engine.dispose()

    with pytest.raises(MigrationError) as exc_info:
        SchemaMigrationService.migrate_to_head(db_uri)

    assert exc_info.value.code == "newer_version"
    assert exc_info.value.detail == "f9e8d7c6b5a4"


@pytest.mark.domain
def test_issue_837_main_run_migrations_wrapper(tmp_path, monkeypatch):
    """main.run_migrations translates MigrationError to code strings."""
    import main
    from cbpos.config import Config

    db_file = tmp_path / "cbpos.db"
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "DB_URI", f"sqlite:///{db_file}")

    # No DB file -> returns None
    assert main.run_migrations() is None

    # Unknown schema -> returns 'unknown_schema'
    engine = create_engine(f"sqlite:///{db_file}")
    for t in Base.metadata.sorted_tables:
        if t.name == "users":
            t.create(engine)
    engine.dispose()

    err = main.run_migrations()
    assert err == "unknown_schema"
