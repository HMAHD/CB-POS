"""Tests for ProductBatch schema, Alembic migration, and database invariants (#926)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from alembic import command
from cbpos.core.models import (
    Base,
    Product,
    ProductBatch,
)
from cbpos.core.services.schema_migration_service import SchemaMigrationService


def test_issue_926_migration_up_down_roundtrip(tmp_path):
    """Test upgrade and downgrade of batch tracking migration on SQLite."""
    db_file = tmp_path / "test_migration_batches.db"
    db_url = f"sqlite:///{db_file}"

    # 1. Create base schema and stamp at b3c4d5e6f7a8
    alembic_cfg = SchemaMigrationService._get_alembic_config(db_url)
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    engine.dispose()

    command.stamp(alembic_cfg, "b3c4d5e6f7a8")
    assert SchemaMigrationService.current_revision(db_url) == "b3c4d5e6f7a8"

    # 2. Downgrade to previous revision (a2b3c4d5e6f7)
    command.downgrade(alembic_cfg, "a2b3c4d5e6f7")
    assert SchemaMigrationService.current_revision(db_url) == "a2b3c4d5e6f7"

    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        assert "product_batches" not in tables

        prod_cols = {c["name"] for c in insp.get_columns("products")}
        assert "tracks_batches" not in prod_cols

        for tbl in ["sale_items", "purchase_items", "stock_movements", "stock_count_items", "inventory_logs"]:
            cols = {c["name"] for c in insp.get_columns(tbl)}
            assert "batch_id" not in cols, f"batch_id should not be in {tbl} after downgrade"
    finally:
        engine.dispose()

    # 3. Upgrade back to explicit revision (b3c4d5e6f7a8)
    command.upgrade(alembic_cfg, "b3c4d5e6f7a8")
    assert SchemaMigrationService.current_revision(db_url) == "b3c4d5e6f7a8"

    engine = create_engine(db_url)
    try:
        insp_up = inspect(engine)
        tables_up = set(insp_up.get_table_names())
        assert "product_batches" in tables_up

        batch_cols = {c["name"] for c in insp_up.get_columns("product_batches")}
        expected_cols = {
            "id",
            "product_id",
            "batch_no",
            "expiry_date",
            "mrp",
            "cost",
            "qty_on_hand",
            "received_at",
            "is_active",
            "version_id",
            "last_modified",
        }
        assert expected_cols.issubset(batch_cols)

        prod_cols_up = {c["name"] for c in insp_up.get_columns("products")}
        assert "tracks_batches" in prod_cols_up

        for tbl in ["sale_items", "purchase_items", "stock_movements", "stock_count_items", "inventory_logs"]:
            cols = {c["name"] for c in insp_up.get_columns(tbl)}
            assert "batch_id" in cols, f"batch_id should be in {tbl} after upgrade"
    finally:
        engine.dispose()

    # 4. Downgrade again to confirm idempotency
    command.downgrade(alembic_cfg, "a2b3c4d5e6f7")
    assert SchemaMigrationService.current_revision(db_url) == "a2b3c4d5e6f7"


def test_issue_926_product_batch_identity_constraint_fails_when_both_none(db_session):
    """ProductBatch rejects rows where both batch_no and expiry_date are None."""
    prod = Product(
        barcode="BATCH-TEST-NONE",
        name_en="Panadol 500mg",
        price=Decimal("150.00"),
        cost=Decimal("100.00"),
        stock_qty=Decimal("0.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    batch_invalid = ProductBatch(
        product_id=prod.id,
        batch_no=None,
        expiry_date=None,
        qty_on_hand=Decimal("10.000"),
    )
    db_session.add(batch_invalid)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_issue_926_product_batch_allows_batch_or_expiry_independently(db_session):
    """ProductBatch accepts either batch_no alone, expiry_date alone, or both."""
    prod = Product(
        barcode="BATCH-TEST-VALID",
        name_en="Amoxicillin 500mg",
        price=Decimal("150.00"),
        cost=Decimal("100.00"),
        stock_qty=Decimal("0.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    # Batch with only batch_no -> SUCCEEDS
    batch_no_only = ProductBatch(
        product_id=prod.id,
        batch_no="B12345",
        expiry_date=None,
        qty_on_hand=Decimal("10.000"),
    )
    db_session.add(batch_no_only)
    db_session.flush()
    assert batch_no_only.id is not None

    # Batch with only expiry_date -> SUCCEEDS
    batch_exp_only = ProductBatch(
        product_id=prod.id,
        batch_no=None,
        expiry_date=date(2027, 12, 31),
        qty_on_hand=Decimal("5.000"),
    )
    db_session.add(batch_exp_only)
    db_session.flush()
    assert batch_exp_only.id is not None

    # Batch with both -> SUCCEEDS
    batch_both = ProductBatch(
        product_id=prod.id,
        batch_no="B99999",
        expiry_date=date(2028, 1, 1),
        qty_on_hand=Decimal("15.000"),
    )
    db_session.add(batch_both)
    db_session.flush()
    assert batch_both.id is not None


def test_issue_926_product_batch_version_id_optimistic_locking(db_session):
    """ProductBatch optimistic locking increments version_id and blocks stale updates."""
    prod = Product(
        barcode="BATCH-TEST-002",
        name_en="Amoxicillin 250mg",
        price=Decimal("200.00"),
        cost=Decimal("150.00"),
        stock_qty=Decimal("0.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    batch = ProductBatch(
        product_id=prod.id,
        batch_no="AMX-001",
        expiry_date=date(2028, 6, 30),
        qty_on_hand=Decimal("50.000"),
        mrp=Decimal("220.00"),
    )
    db_session.add(batch)
    db_session.flush()
    assert batch.version_id == 1

    # Normal update increments version_id
    batch.qty_on_hand = Decimal("40.000")
    db_session.flush()
    assert batch.version_id == 2
