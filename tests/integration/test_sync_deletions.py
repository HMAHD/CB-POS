"""Integration tests for issue #871: Catalog deletions propagating to tills."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.database import Database
from cbpos.core.models import Category, PriceListItem, Product, Promotion, SyncDeletion
from cbpos.core.services.category_service import CategoryService
from cbpos.core.services.price_list_service import PriceListService
from cbpos.core.services.promotion_service import PromotionService
from cbpos.core.services.sync_change_tracking import SKIP_CHANGE_TRACKING
from tests.helpers.sync_two_machines import Shop, isolated_settings, make_machine_db

TILL = "TERM-02"


@pytest.fixture
def shop(tmp_path):
    with isolated_settings(str(tmp_path), terminal_id="MAIN-01", terminal_mode="main"):
        s = Shop(str(tmp_path))
        s.add_till(TILL)
        yield s


def test_issue_871_service_deletion_creates_sync_deletion_row(tmp_path):
    """Deleting a catalog entity via service creates a SyncDeletion tombstone,

    unless SKIP_CHANGE_TRACKING is set (#871).
    """
    with isolated_settings(str(tmp_path), terminal_mode="main"):
        db = make_machine_db()
        previous = Database._instance
        Database._instance = db
        try:
            promo_svc = PromotionService()
            promo = promo_svc.create_promotion(
                "Temporary Discount",
                "PERCENTAGE",
                Decimal("10.00"),
                datetime(2026, 1, 1),
                datetime(2026, 12, 31),
            )
            promo_id = promo.id

            promo_svc.delete_promotion(promo_id)

            with db.get_session() as session:
                tombstone = session.query(SyncDeletion).filter_by(table_name="promotions", row_id=promo_id).first()
                assert tombstone is not None
                assert tombstone.table_name == "promotions"
                assert tombstone.row_id == promo_id

            # 2. Deletion with SKIP_CHANGE_TRACKING does not write a tombstone
            with db.get_session() as session:
                count_before = session.query(SyncDeletion).count()

            promo2 = promo_svc.create_promotion(
                "Internal Promo",
                "PERCENTAGE",
                Decimal("5.00"),
                datetime(2026, 1, 1),
                datetime(2026, 12, 31),
            )
            promo2_id = promo2.id

            with db.get_session() as session:
                session.info[SKIP_CHANGE_TRACKING] = True
                p = session.get(Promotion, promo2_id)
                session.delete(p)
                session.commit()

            with db.get_session() as session:
                count_after = session.query(SyncDeletion).count()
                assert count_after == count_before
        finally:
            Database._instance = previous


def test_issue_871_deleted_promotion_and_override_gone_on_till(shop, tmp_path):
    """Deleted promotion and price-list override on Main PC are deleted on till (#871)."""
    cat = shop.seed_catalog()
    product_id = cat["product"]

    # 1. Create Promotion and PriceList with override on Main PC
    with shop.on("main"):
        promo = PromotionService().create_promotion(
            "Summer Discount",
            "PERCENTAGE",
            Decimal("20.00"),
            datetime(2026, 1, 1),
            datetime(2026, 12, 31),
        )
        promo_id = promo.id

        plist = PriceListService().create_price_list("VIP Wholesale")
        plist_id = plist.id
        item = PriceListService().set_item_price(plist_id, product_id, Decimal("85.00"))
        item_id = item.id

    # 2. Sync to till
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        pulled = shop.pull(TILL, full=True)
        assert pulled > 0

        # Verify both exist on till
        with shop.session(TILL) as s:
            assert s.get(Promotion, promo_id) is not None
            assert s.get(PriceListItem, item_id) is not None

    # 3. Delete Promotion and delete PriceListItem override on Main PC
    with shop.on("main"):
        PromotionService().delete_promotion(promo_id)
        PriceListService().delete_item_price(plist_id, product_id)

    # 4. Till pulls catalog
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        shop.pull(TILL)

        # 5. Verify both are gone on till
        with shop.session(TILL) as s:
            assert s.get(Promotion, promo_id) is None
            assert s.get(PriceListItem, item_id) is None


def test_issue_871_recreate_same_name_after_delete_syncs(shop, tmp_path):
    """Recreating a category with the same unique name after deleting syncs cleanly (#871)."""
    # 1. Create Base Category and "Summer Deals" on Main
    with shop.on("main"):
        CategoryService.create("Base Category", color="#111111")
        cat1 = CategoryService.create("Summer Deals", color="#FF0000")
        cat1_id = cat1.id

    # 2. Sync to till
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        shop.pull(TILL, full=True)
        with shop.session(TILL) as s:
            assert s.get(Category, cat1_id) is not None

    # 3. Delete on Main
    with shop.on("main"):
        CategoryService.delete(cat1_id)

    # 4. Sync deletion to till
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        shop.pull(TILL)
        with shop.session(TILL) as s:
            assert s.get(Category, cat1_id) is None

    # 5. Re-create category with same name on Main (with higher ID)
    with shop.on("main"):
        CategoryService.create("Filler Category", color="#222222")
        cat2 = CategoryService.create("Summer Deals", color="#00FF00")
        cat2_id = cat2.id
        assert cat2_id != cat1_id

    # 6. Sync to till -> must succeed without UNIQUE constraint error
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        shop.pull(TILL)
        with shop.session(TILL) as s:
            till_cat = s.get(Category, cat2_id)
            assert till_cat is not None
            assert till_cat.name == "Summer Deals"
            assert till_cat.color == "#00FF00"


def test_issue_871_stale_till_triggers_full_replace(shop, tmp_path):
    """A till whose watermark is older than 180 days triggers full replace (#871)."""
    cat = shop.seed_catalog()
    product_id = cat["product"]

    # Delete product on main
    with shop.session("main") as s:
        p = s.get(Product, product_id)
        s.delete(p)
        s.commit()

    # Set till watermark to 200 days ago
    client = shop.client(TILL)
    client._last_catalog_sync = datetime.now() - timedelta(days=200)

    # Pull
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"), shop.on(TILL):
        client._pull_catalog()

    # Till should have run full replace, so the deleted product is gone on till
    with shop.session(TILL) as s:
        assert s.get(Product, product_id) is None


def test_issue_871_referenced_product_soft_deletes(shop, tmp_path):
    """If a deleted catalog row is referenced by local sales on till, it is soft-deleted (#871)."""
    cat = shop.seed_catalog()
    product_id = cat["product"]
    user_id = cat["user"]

    # 1. Create a sale on till referencing this product
    with shop.session(TILL) as s:
        from cbpos.core.models import Sale, SaleItem, SalePayment

        sale = Sale(
            document_number="S-DEL-01",
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
                qty=Decimal("1"),
                unit_price=Decimal("100"),
                original_price=Decimal("100"),
                subtotal=Decimal("100"),
            )
        )
        sale.payments.append(SalePayment(payment_method="CASH", amount=Decimal("100")))
        s.add(sale)
        s.commit()

    # 2. Main PC deletes the Product
    with shop.session("main") as s:
        p = s.get(Product, product_id)
        s.delete(p)
        s.commit()

    # 3. Till pulls catalog: hard delete fails due to FK from sale_items, falls back to soft-delete
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        pulled = shop.pull(TILL)
        assert pulled >= 0

        with shop.session(TILL) as s:
            p_till = s.get(Product, product_id)
            assert p_till is not None
            assert p_till.is_active is False
