"""Integration tests for Issue #903: Till audit logs and inventory logs push to Main PC."""

from decimal import Decimal

import pytest

from cbpos.core.models import AuditLog, InventoryLog, Product, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.user_service import UserService
from tests.helpers.sync_two_machines import Shop, isolated_settings

TILL = "TERM-02"


@pytest.fixture
def shop(tmp_path):
    with isolated_settings(str(tmp_path), terminal_id="MAIN-01", terminal_mode="main"):
        s = Shop(str(tmp_path))
        s.add_till(TILL)
        yield s


def test_issue_903_till_login_audit_reaches_main(shop, tmp_path):
    """A till login audit row appears on the Main PC after one push cycle (#903)."""
    # 1. Setup user on Main and sync catalog to till
    with shop.on("main"), shop.session("main") as s:
        role = Role(name="Cashier", access_level=1)
        s.add(role)
        s.flush()
        user = User(username="cashier1", pin_hash=AuthService.hash_pin("1234"), role=role)
        s.add(user)
        s.commit()
        user_id = user.id

    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        shop.pull(TILL, full=True)

    # 2. Login on till -> writes local AuditLog row
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"), shop.on(TILL):
        logged_in = AuthService.login("1234")
        assert logged_in is not None

        # Verify unsynced audit log exists on till
        with shop.session(TILL) as s:
            till_log = s.query(AuditLog).filter_by(user_id=user_id, event_type="LOGIN").first()
            assert till_log is not None
            assert till_log.synced is False
            assert till_log.terminal_id == TILL

        # 3. Push transactions from till to Main PC
        pushed = shop.push(TILL)
        assert pushed > 0

        # Verify till marked audit log as synced
        with shop.session(TILL) as s:
            till_log = s.query(AuditLog).filter_by(user_id=user_id, event_type="LOGIN").first()
            assert till_log.synced is True

    # 4. Verify audit log reached Main PC with terminal_id preserved
    with shop.on("main"), shop.session("main") as s:
        main_log = s.query(AuditLog).filter_by(user_id=user_id, event_type="LOGIN").first()
        assert main_log is not None
        assert main_log.terminal_id == TILL
        assert main_log.synced is True

        # Verify UserService filtering by terminal works on Main PC
        logs = UserService.get_recent_activity(terminal_id=TILL)
        assert len(logs) == 1
        assert logs[0].terminal_id == TILL
        assert logs[0].action == "User Login"

        # Verify distinct terminals includes the till
        terminals = UserService.get_distinct_terminals()
        assert TILL in terminals


def test_issue_903_inventory_log_pushed_once(shop, tmp_path):
    """Inventory logs created on a till reach Main PC and are pushed only once (#903)."""
    # 1. Setup user and product on Main PC and sync to till
    with shop.on("main"), shop.session("main") as s:
        role = Role(name="StockManager", access_level=2)
        s.add(role)
        s.flush()
        user = User(username="manager1", pin_hash=AuthService.hash_pin("5678"), role=role)
        s.add(user)
        product = Product(name_en="Milk 1L", barcode="890123456", price=Decimal("450.00"), stock_qty=Decimal("10"))
        s.add(product)
        s.commit()
        user_id = user.id
        prod_id = product.id

    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        shop.pull(TILL, full=True)

    # 2. Create manual inventory adjustment log on till
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"), shop.on(TILL):
        with shop.session(TILL) as s:
            inv_log = InventoryLog(
                product_id=prod_id,
                qty_change=Decimal("5.000"),
                new_qty=Decimal("15.000"),
                reason="Damaged goods write-off",
                user_id=user_id,
                synced=False,
            )
            s.add(inv_log)
            s.commit()
            local_log_id = inv_log.id

        # 3. Push to Main PC
        pushed = shop.push(TILL)
        assert pushed > 0

        # Verify till marked log as synced
        with shop.session(TILL) as s:
            till_inv = s.get(InventoryLog, local_log_id)
            assert till_inv is not None
            assert till_inv.synced is True

    # 4. Verify log reached Main PC
    with shop.on("main"), shop.session("main") as s:
        main_inv = s.query(InventoryLog).filter_by(product_id=prod_id).first()
        assert main_inv is not None
        assert main_inv.qty_change == Decimal("5.000")
        assert main_inv.reason == "Damaged goods write-off"
        assert main_inv.synced is True

    # 5. Push again from till -> must be a no-op (pushed once)
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"), shop.on(TILL):
        pushed_again = shop.push(TILL)
        assert pushed_again == 0

    with shop.on("main"), shop.session("main") as s:
        count = s.query(InventoryLog).filter_by(product_id=prod_id).count()
        assert count == 1
