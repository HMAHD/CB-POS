"""
Data Migration Service for CB-POS
Handles one-click migration from SQLite (Standalone) to PostgreSQL (Network).
"""

from typing import Tuple
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from cbpos.core.database import Base
from cbpos.core.models import (
    User,
    Role,
    Permission,
    Category,
    Customer,
    CustomerContact,
    Supplier,
    Product,
    CompositeItem,
    Sale,
    SaleItem,
    SalePayment,
    Purchase,
    PurchaseItem,
    StockMovement,
    VoidReason,
    PriceList,
    PriceListItem,
    Promotion,
    AuditLog,
    SuspendedTransaction,
    Shift,
    CashMovement,
)


class MigrationService:
    """
    Service to migrate data from SQLite to PostgreSQL.
    Preserves all data, IDs, and relationships.
    """

    # Order matters! Tables with foreign keys must come after their dependencies
    MIGRATION_ORDER = [
        # Auth & Permissions (no dependencies)
        Role,
        Permission,
        User,
        # Master Data
        VoidReason,
        Category,
        Supplier,
        Customer,
        CustomerContact,
        PriceList,
        # Products (depends on Category, Supplier)
        Product,
        PriceListItem,
        CompositeItem,
        # Promotions
        Promotion,
        # Transactions (depend on User, Customer, Product)
        Sale,
        SaleItem,
        SalePayment,
        Purchase,
        PurchaseItem,
        # Inventory
        StockMovement,
        # System
        AuditLog,
        SuspendedTransaction,
        Shift,
        CashMovement,
    ]

    @staticmethod
    def migrate_sqlite_to_postgres(sqlite_url: str, postgres_url: str) -> Tuple[bool, str]:
        """
        Migrate all data from SQLite to PostgreSQL.

        Args:
            sqlite_url: Source SQLite database URL
            postgres_url: Target PostgreSQL database URL

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Initialize engines as None for proper cleanup in finally block
        source_engine = None
        target_engine = None

        try:
            # 1. Create engines
            source_engine = create_engine(sqlite_url, echo=False)
            target_engine = create_engine(postgres_url, echo=False)

            # 2. Test connections
            try:
                with source_engine.connect() as src_conn:
                    src_conn.execute(text("SELECT 1"))
                with target_engine.connect() as tgt_conn:
                    tgt_conn.execute(text("SELECT 1"))
            except Exception as e:
                return False, f"Connection test failed: {str(e)}"

            # 3. Check if target database has data
            inspector = inspect(target_engine)
            existing_tables = inspector.get_table_names()

            if existing_tables:
                # Check if any tables have data
                with target_engine.connect() as conn:
                    for table in existing_tables:
                        if table in ["users", "products", "sales", "customers"]:  # Key tables
                            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                            count = result.scalar()
                            if count and count > 0:
                                return (
                                    False,
                                    f"Target database is not empty. Table '{table}' has {count} rows. "
                                    "Please use an empty database for migration.",
                                )

            # 4. Create schema in PostgreSQL
            Base.metadata.create_all(bind=target_engine)

            # 5. Create sessions
            SourceSession = sessionmaker(bind=source_engine)
            TargetSession = sessionmaker(bind=target_engine)

            src_session = SourceSession()
            tgt_session = TargetSession()

            try:
                total_records = 0

                # 6. Copy data table by table in dependency order
                for model in MigrationService.MIGRATION_ORDER:
                    table_name = model.__tablename__

                    # Stream records in batches to avoid OOM with large datasets
                    query = src_session.query(model)
                    record_count = 0

                    # Process 1000 records at a time to prevent memory exhaustion
                    for record in query.yield_per(1000):
                        # Detach from source session to avoid conflicts
                        src_session.expunge(record)
                        # Merge into target (preserves primary key)
                        tgt_session.merge(record)
                        record_count += 1

                    total_records += record_count

                # Commit all data
                tgt_session.commit()

                # 7. Reset PostgreSQL sequences (critical!)
                # After bulk insert with explicit IDs, sequences are out of sync
                # Use nested transactions (savepoints) to isolate failures
                for model in MigrationService.MIGRATION_ORDER:
                    table_name = model.__tablename__

                    # Check if table has an 'id' column (primary key)
                    if hasattr(model, "id"):
                        try:
                            # Use a nested transaction (savepoint)
                            # If this specific table fails, it won't rollback the whole migration
                            with tgt_session.begin_nested():
                                seq_query = text(
                                    f"SELECT pg_get_serial_sequence('{table_name}', 'id') as seq_name"  # noqa: E501
                                )
                                result = tgt_session.execute(seq_query)
                                seq_name = result.scalar()

                                if seq_name:
                                    # Reset sequence to max(id) + 1
                                    # This ensures the next INSERT gets a valid new ID
                                    reset_query = text(
                                        f"SELECT setval('{seq_name}', "
                                        f"COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1, false)"
                                    )
                                    tgt_session.execute(reset_query)
                        except Exception:
                            # Expected for tables without sequences (like association tables)
                            # The nested transaction handles the rollback automatically
                            pass

                tgt_session.commit()

                return (
                    True,
                    f"✓ Migration completed successfully!\n\n"
                    f"Transferred {total_records} records across {len(MigrationService.MIGRATION_ORDER)} tables.\n"
                    f"Database sequences reset.\n\n"
                    f"You can now switch to Network mode and restart the application.",
                )

            except Exception as e:
                tgt_session.rollback()
                return False, f"Migration failed during data transfer: {str(e)}"
            finally:
                src_session.close()
                tgt_session.close()

        except Exception as e:
            return False, f"Migration setup error: {str(e)}"
        finally:
            # Dispose engines to close all connections
            if source_engine:
                source_engine.dispose()
            if target_engine:
                target_engine.dispose()

    @staticmethod
    def get_table_counts(db_url: str) -> Tuple[bool, dict]:
        """
        Get record counts for all tables in a database.

        Args:
            db_url: Database URL

        Returns:
            Tuple of (success: bool, counts: dict)
        """
        try:
            engine = create_engine(db_url, echo=False)

            with engine.connect() as conn:
                counts = {}
                for model in MigrationService.MIGRATION_ORDER:
                    table_name = model.__tablename__
                    try:
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                        counts[table_name] = result.scalar() or 0
                    except Exception:
                        counts[table_name] = 0

            engine.dispose()
            return True, counts

        except Exception as e:
            return False, {"error": str(e)}
