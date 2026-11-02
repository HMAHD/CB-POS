"""Integration tests for issue #836: Product edits on Main PC reaching till."""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.models import Product, Sale, SaleItem, StockMovement
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
