"""Integration tests for terminal identity, collision rejection, and reinstall/restore handling (#867, #866)."""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.models import Sale, SaleItem, SyncIdMap
from cbpos.core.services.local_identity_service import LocalIdentityService
from cbpos.core.services.sync_apply_service import PushApplyError, SyncApplyService
from cbpos.core.services.sync_terminal_service import SyncTerminalService
from tests.helpers.sync_two_machines import Shop, isolated_settings, make_machine_db

MAIN_ID = "TERM-01"
TILL_ID = "TILL-01"


@pytest.fixture
def shop(tmp_path):
    with isolated_settings(str(tmp_path), terminal_id=MAIN_ID, terminal_mode="main"):
        s = Shop(str(tmp_path))
        yield s


def test_issue_867_register_with_main_id_rejected(shop):
    """Sync server rejects registration if the till attempts to use the Main PC's own terminal ID."""
    shop.add_till(MAIN_ID)
    with shop.on(MAIN_ID):
        res = shop.client(MAIN_ID)._try_register()
    assert res is False
    assert shop.last_status == 409
    assert shop.last_response["error"] == "terminal_id_is_main"


def test_issue_867_register_same_id_other_instance_rejected(shop):
    """Sync server rejects registration if the terminal ID is already bound to another database instance."""
    # First machine registers successfully
    shop.add_till(TILL_ID)
    with shop.on(TILL_ID):
        assert shop.client(TILL_ID)._try_register() is True
    assert shop.last_status == 200
    assert shop.last_response["status"] == "registered"

    # Second machine with same terminal ID but new database instance ID
    new_db = make_machine_db()
    shop.tills[TILL_ID] = (new_db, shop.client(TILL_ID))

    with shop.on(TILL_ID):
        res = shop.client(TILL_ID)._try_register()
    assert res is False
    assert shop.last_status == 409
    assert shop.last_response["error"] == "terminal_id_taken"


def test_issue_867_register_released_id_accepted(shop):
    """Releasing a terminal ID allows a new database instance to claim it."""
    shop.add_till(TILL_ID)
    with shop.on(TILL_ID):
        assert shop.client(TILL_ID)._try_register() is True

    # Recreate DB on till
    new_db = make_machine_db()
    shop.tills[TILL_ID] = (new_db, shop.client(TILL_ID))

    # Before release: rejected
    with shop.on(TILL_ID):
        assert shop.client(TILL_ID)._try_register() is False
    assert shop.last_status == 409

    # Admin releases terminal ID
    with shop.on("main"):
        assert SyncTerminalService.release_terminal(TILL_ID) is True

    # After release: accepted
    with shop.on(TILL_ID):
        assert shop.client(TILL_ID)._try_register() is True
    assert shop.last_status == 200
    assert shop.last_response["status"] == "registered"


def test_issue_866_recreated_till_keeps_both_sales(shop):
    """When a till database is reinstalled / starts over, new sale local IDs do not overwrite old sales."""
    shop.add_till(TILL_ID)
    cat = shop.seed_catalog()
    product_id = cat["product"]

    # Sell sale #1 on till (instance 1)
    sale_date = datetime(2026, 11, 2, 10, 0, 0)
    with shop.session(TILL_ID) as s:
        sale1 = Sale(
            document_number="TILL01-INV-2026-00001",
            date=sale_date,
            user_id=cat["user"],
            terminal_id=TILL_ID,
            origin_terminal_id=TILL_ID,
            total_amount=Decimal("100"),
            net_revenue=Decimal("100"),
            payment_method="CASH",
        )
        sale1.items.append(
            SaleItem(
                product_id=product_id,
                qty=Decimal("1"),
                unit_price=Decimal("100"),
                original_price=Decimal("100"),
                subtotal=Decimal("100"),
            )
        )
        s.add(sale1)

    # Push sale #1 to Main PC
    pushed = shop.push(TILL_ID)
    assert pushed > 0

    # Verify on Main PC: 1 sale
    with shop.session("main") as s:
        sales = s.query(Sale).all()
        assert len(sales) == 1
        assert sales[0].document_number == "TILL01-INV-2026-00001"
        assert sales[0].total_amount == Decimal("100")

    # Now simulate till reinstall / recreated database:
    # 1. New DB instance on till
    new_db = make_machine_db()
    shop.tills[TILL_ID] = (new_db, shop.client(TILL_ID))

    # 2. Release terminal ID on Main PC so new instance can connect
    with shop.on("main"):
        SyncTerminalService.release_terminal(TILL_ID)

    # 3. Pull catalog to fresh till DB
    shop.pull(TILL_ID, full=True)

    # 4. Sell sale #2 on new till DB (it gets local id = 1, but new document number)
    with shop.session(TILL_ID) as s:
        sale2 = Sale(
            document_number="TILL01-INV-2026-00002",
            date=datetime(2026, 11, 2, 11, 0, 0),
            user_id=cat["user"],
            terminal_id=TILL_ID,
            origin_terminal_id=TILL_ID,
            total_amount=Decimal("200"),
            net_revenue=Decimal("200"),
            payment_method="CASH",
        )
        sale2.items.append(
            SaleItem(
                product_id=product_id,
                qty=Decimal("2"),
                unit_price=Decimal("100"),
                original_price=Decimal("100"),
                subtotal=Decimal("200"),
            )
        )
        s.add(sale2)

    # 5. Push sale #2 from new till DB
    pushed2 = shop.push(TILL_ID)
    assert pushed2 > 0

    # 6. Verify on Main PC: BOTH sales exist, neither was overwritten!
    with shop.session("main") as s:
        sales = s.query(Sale).order_by(Sale.id.asc()).all()
        assert len(sales) == 2
        assert sales[0].document_number == "TILL01-INV-2026-00001"
        assert sales[0].total_amount == Decimal("100")
        assert sales[1].document_number == "TILL01-INV-2026-00002"
        assert sales[1].total_amount == Decimal("200")

        # Two sales exist
        assert s.query(SaleItem).count() == 2


def test_issue_866_restored_till_resend_is_idempotent(shop):
    """When a restored till re-sends an already synced sale, it is mapped idempotently without duplicating rows."""
    shop.add_till(TILL_ID)
    cat = shop.seed_catalog()
    product_id = cat["product"]

    sale_date = datetime(2026, 11, 2, 10, 0, 0)
    with shop.session(TILL_ID) as s:
        sale = Sale(
            document_number="TILL01-INV-2026-00001",
            date=sale_date,
            user_id=cat["user"],
            terminal_id=TILL_ID,
            origin_terminal_id=TILL_ID,
            total_amount=Decimal("100"),
            net_revenue=Decimal("100"),
            payment_method="CASH",
        )
        sale.items.append(
            SaleItem(
                product_id=product_id,
                qty=Decimal("1"),
                unit_price=Decimal("100"),
                original_price=Decimal("100"),
                subtotal=Decimal("100"),
            )
        )
        s.add(sale)

    pushed = shop.push(TILL_ID)
    assert pushed > 0

    with shop.session("main") as s:
        assert s.query(Sale).count() == 1
        assert s.query(SaleItem).count() == 1

    # Now till restores backup: new instance UUID
    with shop.on(TILL_ID):
        new_inst = LocalIdentityService.regenerate()

    # Re-release on Main PC
    with shop.on("main"):
        SyncTerminalService.release_terminal(TILL_ID)

    # Re-send the exact same sale under new instance ID
    with shop.session(TILL_ID) as s:
        sale = s.query(Sale).one()
        sale.synced = False  # Mark unsynced as in restored backup
        for it in sale.items:
            it.synced = False

    shop.push(TILL_ID)

    # Main PC still has exactly 1 sale, 1 item
    with shop.session("main") as s:
        assert s.query(Sale).count() == 1
        assert s.query(SaleItem).count() == 1

        # And sync_id_map now maps the new instance
        mapping = (
            s.query(SyncIdMap)
            .filter_by(
                origin_terminal_id=TILL_ID,
                origin_db_instance_id=new_inst,
                table_name="documents",
            )
            .first()
        )
        assert mapping is not None


def test_issue_866_mapped_resend_with_different_number_rejected(shop):
    """_update raises PushApplyError('mapped_row_mismatch') if mapped document differs in number or date."""
    cat = shop.seed_catalog()
    with shop.on("main") as db, db.get_session() as session:
        service = SyncApplyService(session=session, terminal_id="TILL-01", db_instance_id="inst-1")
        sale = Sale(
            document_number="TILL01-INV-2026-00001",
            date=datetime(2026, 11, 2, 10, 0, 0),
            user_id=cat["user"],
            total_amount=Decimal("100"),
            payment_method="CASH",
        )
        session.add(sale)
        session.flush()

        # Update with differing document_number must raise PushApplyError
        with pytest.raises(PushApplyError) as excinfo:
            service._update(
                row=sale,
                table_name="sales",
                values={
                    "document_number": "TILL01-INV-2026-99999",
                    "date": sale.date,
                    "total_amount": Decimal("100"),
                },
            )
        assert "mapped_row_mismatch" in str(excinfo.value)
