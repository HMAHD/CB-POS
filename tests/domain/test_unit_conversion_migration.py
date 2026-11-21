from sqlalchemy import create_engine, inspect

from alembic import command
from cbpos.core.models import Base
from cbpos.core.services.schema_migration_service import SchemaMigrationService


def test_issue_937_migration_adds_and_drops_columns(tmp_path):
    """Test upgrade and downgrade of purchase unit conversion migration on SQLite."""
    db_file = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_file}"

    # 1. Create base schema at head revision
    alembic_cfg = SchemaMigrationService._get_alembic_config(db_url)
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    engine.dispose()

    # Stamp at head
    command.stamp(alembic_cfg, "head")
    assert SchemaMigrationService.current_revision(db_url) == "a2b3c4d5e6f7"

    # 2. Downgrade to previous revision (f1a2b3c4d5e6)
    command.downgrade(alembic_cfg, "f1a2b3c4d5e6")
    assert SchemaMigrationService.current_revision(db_url) == "f1a2b3c4d5e6"

    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        prod_cols = {c["name"] for c in insp.get_columns("products")}
        assert "purchase_unit_id" not in prod_cols
        assert "purchase_factor" not in prod_cols

        item_cols = {c["name"] for c in insp.get_columns("purchase_items")}
        assert "purchase_unit_id" not in item_cols
        assert "purchase_factor" not in item_cols
        assert "purchase_qty" not in item_cols
        assert "purchase_unit_cost" not in item_cols
    finally:
        engine.dispose()

    # 3. Upgrade back to head (a2b3c4d5e6f7)
    command.upgrade(alembic_cfg, "head")
    assert SchemaMigrationService.current_revision(db_url) == "a2b3c4d5e6f7"

    engine = create_engine(db_url)
    try:
        insp_up = inspect(engine)
        prod_cols_up = {c["name"] for c in insp_up.get_columns("products")}
        assert "purchase_unit_id" in prod_cols_up
        assert "purchase_factor" in prod_cols_up

        item_cols_up = {c["name"] for c in insp_up.get_columns("purchase_items")}
        assert "purchase_unit_id" in item_cols_up
        assert "purchase_factor" in item_cols_up
        assert "purchase_qty" in item_cols_up
        assert "purchase_unit_cost" in item_cols_up
    finally:
        engine.dispose()

    # 4. Downgrade again
    command.downgrade(alembic_cfg, "f1a2b3c4d5e6")
    assert SchemaMigrationService.current_revision(db_url) == "f1a2b3c4d5e6"
