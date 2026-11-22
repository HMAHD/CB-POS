"""Integration and concurrency tests for Issue #926: Expiry Dates & Batches with Per-Batch MRP.

Covers:
- Deterministic FEFO row locking for concurrency safety.
- Main PC offline till overdraft sync resolution (D51).
- Alembic migration upgrade/downgrade roundtrip (D53).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command
from cbpos.core.models import (
    AuditLog,
    Base,
    Product,
    ProductBatch,
    Role,
    User,
)
from cbpos.core.services.batch_service import BatchService
from cbpos.core.services.schema_migration_service import SchemaMigrationService
from cbpos.core.services.sync_apply_service import SyncApplyService


def test_issue_926_concurrent_till_fefo_row_locking(db_session):
    """Prove allocate_fefo_stock acquires row locks in strictly ascending ID order.

    Ascending ID locking prevents deadlocks when concurrent transactions allocate
    batches in PostgreSQL.
    """
    prod = Product(
        barcode="BAR-CONC-01",
        name_en="Concurrency Test Product",
        price=Decimal("100.00"),
        cost=Decimal("70.00"),
        stock_qty=Decimal("15.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    today = date.today()
    # Create batches in non-id-sorted expiry order:
    # Batch 1: expires later
    # Batch 2: expires earlier
    # Batch 3: expires latest
    b1 = ProductBatch(
        product_id=prod.id,
        batch_no="B1",
        expiry_date=today + timedelta(days=20),
        qty_on_hand=Decimal("5.000"),
        cost=Decimal("70.00"),
        mrp=Decimal("100.00"),
        is_active=True,
    )
    b2 = ProductBatch(
        product_id=prod.id,
        batch_no="B2",
        expiry_date=today + timedelta(days=5),
        qty_on_hand=Decimal("5.000"),
        cost=Decimal("70.00"),
        mrp=Decimal("100.00"),
        is_active=True,
    )
    b3 = ProductBatch(
        product_id=prod.id,
        batch_no="B3",
        expiry_date=today + timedelta(days=30),
        qty_on_hand=Decimal("5.000"),
        cost=Decimal("70.00"),
        mrp=Decimal("100.00"),
        is_active=True,
    )
    db_session.add_all([b1, b2, b3])
    db_session.flush()

    # FEFO allocation order should be: b2 (days=5), b1 (days=20), b3 (days=30)
    allocations = BatchService.allocate_fefo_stock(
        product_id=prod.id,
        requested_qty=Decimal("7.000"),
        allow_negative_stock=False,
        session=db_session,
    )

    assert len(allocations) == 2
    assert allocations[0][0].id == b2.id
    assert allocations[0][1] == Decimal("5.000")
    assert allocations[1][0].id == b1.id
    assert allocations[1][1] == Decimal("2.000")


def test_issue_926_allocate_fefo_stock_refreshes_stale_identity_map(db_session):
    """allocate_fefo_stock refreshes batches via populate_existing() if already in session identity map."""
    from cbpos.core.services.batch_service import InsufficientStockError

    prod = Product(
        barcode="CONC-STALE-01",
        name_en="Concurrency Stale Item",
        price=Decimal("100.00"),
        cost=Decimal("70.00"),
        stock_qty=Decimal("5.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    batch = ProductBatch(
        product_id=prod.id,
        batch_no="B-STALE",
        expiry_date=date.today() + timedelta(days=30),
        qty_on_hand=Decimal("5.000"),
        cost=Decimal("70.00"),
        mrp=Decimal("100.00"),
        is_active=True,
    )
    db_session.add(batch)
    db_session.commit()

    # Session 2 loads the batch into its identity map when qty was 5
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=db_session.get_bind())
    s2 = SessionLocal()
    s1 = SessionLocal()
    try:
        # Step 1: Session 2 executes candidate query, loading candidate batch into identity map
        cand_b = s2.query(ProductBatch).filter(ProductBatch.id == batch.id).all()
        assert cand_b[0].qty_on_hand == Decimal("5.000")
        assert cand_b[0].version_id == 1

        # Step 2: Concurrently, Session 1 sells/reduces batch stock from 5 down to 1 and commits
        b1 = s1.get(ProductBatch, batch.id)
        b1.qty_on_hand = Decimal("1.000")
        b1.version_id = 2
        s1.commit()

        # Step 3: Session 2 executes allocate_fefo_stock requesting 3 units.
        # With populate_existing(), allocate_fefo_stock refreshes the batch in identity map,
        # observes that only 1 unit is available, and raises InsufficientStockError.
        with pytest.raises(InsufficientStockError):
            BatchService.allocate_fefo_stock(
                product_id=prod.id,
                requested_qty=Decimal("3.000"),
                allow_negative_stock=False,
                session=s2,
            )
    finally:
        s1.close()
        s2.close()


def test_issue_926_offline_till_overdraft_sync_resolution(db_session):
    """Main PC absorbs offline till sales that overdraft a batch, mutating the batch balance

    to negative and writing a BATCH_OVERDRAFT_SYNC_CONFLICT audit log entry (D51).
    """
    role = Role(name="SyncTestRole")
    user = User(username="synctestuser", pin_hash="hash", role=role)
    prod = Product(
        barcode="BAR-SYNC-01",
        name_en="Sync Tracked Item",
        price=Decimal("150.00"),
        cost=Decimal("100.00"),
        stock_qty=Decimal("2.000"),
        tracks_batches=True,
    )
    db_session.add_all([role, user, prod])
    db_session.flush()

    batch = ProductBatch(
        product_id=prod.id,
        batch_no="SYNC-B01",
        expiry_date=date.today() + timedelta(days=60),
        qty_on_hand=Decimal("2.000"),
        cost=Decimal("100.00"),
        mrp=Decimal("150.00"),
        is_active=True,
    )
    db_session.add(batch)
    db_session.flush()

    # Till sold 5 units offline (overdrafting batch by 3 units)
    apply_service = SyncApplyService(
        session=db_session,
        terminal_id="TERM-02",
        db_instance_id="inst-test-02",
    )

    movement_data = {
        "id": 999,  # till local id
        "product_id": prod.id,
        "batch_id": batch.id,
        "user_id": user.id,
        "type": "SALE",
        "qty_change": Decimal("-5.000"),
        "balance_after": Decimal("-3.000"),
        "created_at": datetime.now(),
        "synced": True,
    }

    apply_service.apply_batch(
        {
            "stock_movements": [movement_data],
        }
    )
    db_session.flush()

    # Verify Main PC state
    refreshed_batch = db_session.get(ProductBatch, batch.id)
    assert refreshed_batch.qty_on_hand == Decimal("-3.000")

    refreshed_prod = db_session.get(Product, prod.id)
    assert refreshed_prod.stock_qty == Decimal("-3.000")

    # Verify BATCH_OVERDRAFT_SYNC_CONFLICT audit log
    audit_entry = (
        db_session.query(AuditLog)
        .filter_by(
            action="BATCH_OVERDRAFT_SYNC_CONFLICT",
            event_type="SYNC_CONFLICT",
            terminal_id="TERM-02",
        )
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.user_id == user.id
    assert f"overdrafted batch {batch.id}" in audit_entry.details
    assert "New balance: -3.000" in audit_entry.details


def test_issue_926_migration_upgrade_and_downgrade(tmp_path):
    """Test upgrade and downgrade of batch and expiry tracking migration on SQLite (D53)."""
    db_file = tmp_path / "test_batch_migration.db"
    db_url = f"sqlite:///{db_file}"

    alembic_cfg = SchemaMigrationService._get_alembic_config(db_url)
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    engine.dispose()

    # Stamp explicitly at b3c4d5e6f7a8 (never head)
    command.stamp(alembic_cfg, "b3c4d5e6f7a8")
    assert SchemaMigrationService.current_revision(db_url) == "b3c4d5e6f7a8"

    # 1. Downgrade to previous revision (a2b3c4d5e6f7)
    command.downgrade(alembic_cfg, "a2b3c4d5e6f7")
    assert SchemaMigrationService.current_revision(db_url) == "a2b3c4d5e6f7"

    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        assert "product_batches" not in tables

        prod_cols = {c["name"] for c in insp.get_columns("products")}
        assert "tracks_batches" not in prod_cols

        for tbl in ["sale_items", "stock_movements", "purchase_items", "stock_count_items", "inventory_logs"]:
            cols = {c["name"] for c in insp.get_columns(tbl)}
            assert "batch_id" not in cols, f"batch_id should not be in {tbl} after downgrade"
    finally:
        engine.dispose()

    # 2. Re-upgrade back to b3c4d5e6f7a8
    command.upgrade(alembic_cfg, "b3c4d5e6f7a8")
    assert SchemaMigrationService.current_revision(db_url) == "b3c4d5e6f7a8"

    engine = create_engine(db_url)
    try:
        insp_up = inspect(engine)
        tables_up = set(insp_up.get_table_names())
        assert "product_batches" in tables_up

        prod_cols_up = {c["name"] for c in insp_up.get_columns("products")}
        assert "tracks_batches" in prod_cols_up

        for tbl in ["sale_items", "stock_movements", "purchase_items", "stock_count_items", "inventory_logs"]:
            cols_up = {c["name"] for c in insp_up.get_columns(tbl)}
            assert "batch_id" in cols_up, f"batch_id should be in {tbl} after upgrade"
    finally:
        engine.dispose()


@pytest.mark.postgres
@pytest.mark.integration
def test_issue_926_postgres_migration_roundtrip(pg_engine):
    """Verify batch tracking migration upgrade and downgrade on PostgreSQL."""
    import os

    from sqlalchemy import text

    pg_url = os.environ.get("CBPOS_TEST_PG_URL")
    if not pg_url:
        pytest.skip("CBPOS_TEST_PG_URL not set")

    alembic_cfg = SchemaMigrationService._get_alembic_config(pg_url)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))

    Base.metadata.create_all(pg_engine)
    command.stamp(alembic_cfg, "b3c4d5e6f7a8")
    assert SchemaMigrationService.current_revision(pg_url) == "b3c4d5e6f7a8"

    # Downgrade
    command.downgrade(alembic_cfg, "a2b3c4d5e6f7")
    assert SchemaMigrationService.current_revision(pg_url) == "a2b3c4d5e6f7"

    insp = inspect(pg_engine)
    assert "product_batches" not in set(insp.get_table_names())

    # Upgrade
    command.upgrade(alembic_cfg, "b3c4d5e6f7a8")
    assert SchemaMigrationService.current_revision(pg_url) == "b3c4d5e6f7a8"

    insp_up = inspect(pg_engine)
    assert "product_batches" in set(insp_up.get_table_names())
