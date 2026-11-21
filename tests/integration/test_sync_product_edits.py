"""Integration tests for issue #836: Product edits on Main PC reaching till."""

import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session, sessionmaker

from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.database import Base
from cbpos.core.models import Product, Role, Sale, SaleItem, StockMovement, User
from cbpos.core.services.price_board_service import PriceBoardService
from cbpos.infrastructure.sync_client import SyncClient
from tests.helpers.sync_two_machines import Shop, isolated_settings

TILL = "TERM-02"


@pytest.fixture
def shop(tmp_path):
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        s = Shop(str(tmp_path))
        s.add_till(TILL)
        yield s


def test_issue_836_main_price_edit_reaches_till_after_both_sold(shop):
    """After a price edit on Main PC, with both PCs having sold the product,

    one sync cycle shows the new price on the till (#836).
    """
    cat = shop.seed_catalog()
    product_id = cat["product"]
    user_id = cat["user"]

    # 1. Till sells 1 unit (bumps local version_id on till)
    with shop.session(TILL) as s:
        till_prod = s.get(Product, product_id)
        till_prod.stock_qty -= Decimal("1.000")
        sale = Sale(
            document_number="TILL02-INV-2026-00001",
            date=datetime.now(),
            user_id=user_id,
            terminal_id=TILL,
            origin_terminal_id=TILL,
            total_amount=Decimal("100"),
            net_revenue=Decimal("100"),
            payment_method="CASH",
        )
        sale.items.append(
            SaleItem(
                product_id=product_id,
                qty=Decimal("1.000"),
                unit_price=Decimal("100"),
                original_price=Decimal("100"),
                subtotal=Decimal("100"),
            )
        )
        s.add(sale)
        s.add(
            StockMovement(
                product_id=product_id,
                user_id=user_id,
                type="SALE",
                qty_change=Decimal("-1.000"),
                balance_after=till_prod.stock_qty,
                terminal_id=TILL,
            )
        )
        s.commit()

    # 2. Main PC sells 1 unit and edits the price to 175.00
    with shop.session("main") as s:
        main_prod = s.get(Product, product_id)
        main_prod.stock_qty -= Decimal("1.000")
        s.commit()

    with shop.session("main") as s:
        main_prod = s.get(Product, product_id)
        main_prod.price = Decimal("175.00")
        main_prod.name_en = "Updated Item Name"
        main_prod.last_modified = datetime.now()
        s.commit()

    # 3. Till pulls catalog
    pulled = shop.pull(TILL)
    assert pulled > 0

    # 4. Till must have the updated price and name
    with shop.session(TILL) as s:
        prod_on_till = s.get(Product, product_id)
        assert prod_on_till.price == Decimal("175.00")
        assert prod_on_till.name_en == "Updated Item Name"


def test_issue_836_failed_record_keeps_watermark(shop, monkeypatch):
    """When a catalog record fails to apply, the previous watermark is kept

    and client transitions to error state (#836, #906).
    """
    shop.seed_catalog()
    client = shop.client(TILL)

    initial_watermark = datetime(2026, 1, 1, 10, 0, 0)
    client._last_catalog_sync = initial_watermark

    # Mock server response to include an invalid record that fails to apply
    bad_result = {
        "status": "success",
        "timestamp": "2026-11-02T12:00:00",
        "total_records": 1,
        "payload": {
            "products": [
                {
                    "id": 99999,
                    "name_en": "Broken Product",
                    # Missing required non-null barcode, or price invalid to cause merge error
                    "price": "not-a-decimal-number",
                }
            ]
        },
    }
    monkeypatch.setattr(client, "_request", lambda method, endpoint, data=None, timeout=10: bad_result)

    with shop.on(TILL):
        client._pull_catalog()

    # Watermark must not have advanced to 2026-11-02T12:00:00
    assert client._last_catalog_sync == initial_watermark
    assert client._state == SyncClient.STATE_ERROR
    assert client.error_code == "catalog_apply_failed"


def _run_price_board_incremental_watermark_test(shop: Shop, barcode: str = "PB-SYNC-WM") -> None:
    """Deterministic regression: Price Board commit after uncommitted pull does not skip sync."""
    # 1. Seed Main PC with admin user and flagged product
    with shop.session("main") as s:
        role = s.query(Role).filter_by(name=ADMIN_ROLE_NAME).first()
        if not role:
            role = Role(name=ADMIN_ROLE_NAME)
            s.add(role)
            s.flush()
        user = s.query(User).filter_by(username="admin_pb_wm").first()
        if not user:
            user = User(username="admin_pb_wm", pin_hash="hash", role_id=role.id, is_active=True)
            s.add(user)
            s.flush()
        prod = s.query(Product).filter_by(barcode=barcode).first()
        if not prod:
            prod = Product(
                barcode=barcode,
                name_en="Watermark Product",
                price=Decimal("100.00"),
                is_active=True,
                price_changes_often=True,
                last_modified=datetime.now() - timedelta(minutes=10),
            )
            s.add(prod)
        s.commit()
        prod_id = prod.id
        user_id = user.id

    # Initial pull on till to populate product at old price
    shop.pull(TILL, full=True)
    with shop.session(TILL) as s:
        p_till = s.get(Product, prod_id)
        assert p_till is not None
        assert p_till.price == Decimal("100.00")

    # 2. Setup PriceBoardService update with deterministic pause before flush
    paused = threading.Event()
    continue_event = threading.Event()

    def before_flush(session, flush_context, instances):
        for obj in session.dirty:
            if isinstance(obj, Product) and obj.id == prod_id:
                paused.set()
                continue_event.wait(timeout=10)

    event.listen(Session, "before_flush", before_flush)

    def run_price_board():
        with shop.on("main"):
            service = PriceBoardService(db=shop.main)
            service.batch_update_prices(
                updates=[{"product_id": prod_id, "expected_version_id": 1, "new_price": Decimal("150.00")}],
                acting_user_id=user_id,
            )

    t = threading.Thread(target=run_price_board)
    t.start()

    try:
        assert paused.wait(timeout=10), "PriceBoard transaction did not pause before flush"

        # While transaction is prepared but uncommitted/paused:
        # Perform incremental catalog pull on till and capture watermark
        time.sleep(0.05)
        shop.pull(TILL)

        # Release PriceBoard transaction to flush and commit
        continue_event.set()
        t.join(timeout=10)
    finally:
        event.remove(Session, "before_flush", before_flush)

    # Next incremental pull on till after that watermark
    time.sleep(0.05)
    shop.pull(TILL)

    # Prove the next pull after that watermark includes the changed product and price
    with shop.session(TILL) as s:
        p_till = s.get(Product, prod_id)
        assert p_till is not None
        assert p_till.price == Decimal("150.00")


def test_price_board_incremental_till_sync_not_skipped_sqlite(tmp_path):
    """Incremental till sync does not skip Price Board updates on SQLite Main PC."""
    with isolated_settings(str(tmp_path), terminal_id="TERM-01", terminal_mode="main"):
        shop = Shop(str(tmp_path))
        shop.add_till(TILL)
        _run_price_board_incremental_watermark_test(shop, barcode="PB-SYNC-SQLITE")


@pytest.mark.postgres
def test_price_board_incremental_till_sync_not_skipped_postgres(tmp_path, pg_engine):
    """Incremental till sync does not skip Price Board updates on PostgreSQL Main PC."""
    import uuid

    from cbpos.core.models import LocalIdentity

    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    Base.metadata.create_all(pg_engine)

    ThreadSession = sessionmaker(bind=pg_engine, expire_on_commit=False)

    class PgMachineDatabase:
        engine = pg_engine
        SessionLocal = ThreadSession

        def get_session(self):
            return ThreadSession()

    pg_db = PgMachineDatabase()
    with ThreadSession() as s:
        s.add(LocalIdentity(db_instance_id=str(uuid.uuid4())))
        s.commit()

    with isolated_settings(str(tmp_path), terminal_id="TERM-01", terminal_mode="main"):
        shop = Shop(str(tmp_path), main_db=pg_db)
        shop.add_till(TILL)
        _run_price_board_incremental_watermark_test(shop, barcode="PB-SYNC-PG")
