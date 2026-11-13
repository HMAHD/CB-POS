"""Integration tests for Warranty (#821, #822): Multi-terminal catalog and transaction sync."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import Category, Product, Sale, SyncIdMap, User, Warranty, WarrantyPolicy
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.warranty_service import WarrantyService
from cbpos.core.utils.terminal_guard import CatalogReadOnlyError
from tests.helpers.sync_two_machines import Shop, isolated_settings

TILL = "TERM-02"


@pytest.fixture
def shop(tmp_path):
    with isolated_settings(str(tmp_path), terminal_id="MAIN-01", terminal_mode="main"):
        s = Shop(str(tmp_path))
        s.add_till(TILL)
        yield s


def test_issue_821_warranty_policy_syncs_to_till(shop, tmp_path):
    """Warranty policy, product assignment, and category default sync from Main PC to till."""
    # 1. Create policy and assign on Main PC
    with shop.on("main"), shop.session("main") as s:
        policy = WarrantyPolicy(
            name="1 Year Manufacturer",
            name_si="වසර 1ක නිෂ්පාදක වගකීම",
            name_ta="1 வருட உற்பத்தியாளர் உத்தரவாதம்",
            warranty_type="MANUFACTURER",
            duration=1,
            duration_unit="YEARS",
            remedy="REPAIR_OR_REPLACE",
            provider_name="Samsung",
            is_active=True,
        )
        s.add(policy)
        s.flush()
        policy_id = policy.id

        cat = Category(name="Electronics", default_warranty_policy_id=policy_id)
        s.add(cat)
        s.flush()
        cat_id = cat.id

        prod = Product(
            barcode="8901234567890",
            name_en="Samsung Galaxy Phone",
            price=Decimal("99999.00"),
            category_id=cat_id,
            warranty_override="POLICY",
            warranty_policy_id=policy_id,
            serial_mode="OFF",
        )
        s.add(prod)
        s.commit()
        prod_id = prod.id

    # 2. Till pulls catalog
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        pulled = shop.pull(TILL, full=True)
        assert pulled > 0

        with shop.session(TILL) as s:
            till_pol = s.get(WarrantyPolicy, policy_id)
            assert till_pol is not None
            assert till_pol.name == "1 Year Manufacturer"
            assert till_pol.provider_name == "Samsung"
            assert till_pol.duration == 1
            assert till_pol.duration_unit == "YEARS"

            till_cat = s.get(Category, cat_id)
            assert till_cat is not None
            assert till_cat.default_warranty_policy_id == policy_id

            till_prod = s.get(Product, prod_id)
            assert till_prod is not None
            assert till_prod.warranty_policy_id == policy_id
            assert till_prod.warranty_override == "POLICY"
            assert till_prod.serial_mode == "OFF"


def test_issue_821_till_cannot_mutate_warranty_catalog(shop, tmp_path):
    """Secondary till cannot create or modify warranty policies (catalog read-only rule)."""
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        with pytest.raises(CatalogReadOnlyError):
            WarrantyService.create_policy(
                {
                    "name": "Till Created",
                    "warranty_type": "SHOP",
                    "duration": 6,
                    "duration_unit": "MONTHS",
                    "remedy": "REFUND",
                }
            )


def test_issue_822_till_sale_with_warranties_syncs_to_main_pc(shop, tmp_path):
    """Warranties created on a secondary till reach Main PC with remapped IDs and synced=True."""
    # 1. Seed policy, product, and cashier on Main PC
    catalog = shop.seed_catalog()
    with shop.on("main"), shop.session("main") as s:
        policy = WarrantyPolicy(
            name="1 Year Shop",
            warranty_type="SHOP",
            duration=1,
            duration_unit="YEARS",
            remedy="REPAIR_OR_REPLACE",
            is_active=True,
        )
        s.add(policy)
        s.flush()
        policy_id = policy.id

        prod = Product(
            barcode="8901112223334",
            name_en="Gaming Keyboard",
            price=Decimal("15000.00"),
            stock_qty=Decimal("20.0"),
            warranty_override="POLICY",
            warranty_policy_id=policy_id,
            serial_mode="OFF",
        )
        s.add(prod)
        s.commit()
        prod_id = prod.id

    # 2. Till pulls catalog
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        pulled = shop.pull(TILL, full=True)
        assert pulled > 0

        # 3. Sell covered product on till
        with shop.on(TILL), shop.session(TILL) as s:
            till_prod = s.get(Product, prod_id)
            till_user = s.get(User, catalog["user"])

            with patch.object(AuthService, "get_current_user", return_value=till_user):
                cart = CartService()
                cart.add_item(till_prod, qty=Decimal("2.0"))
                payments = [{"method": "Cash", "amount": Decimal("30000.00")}]

                sale = TransactionService.process_sale(cart, payments)
                assert sale is not None
                till_sale_id = sale.id
                till_sale_doc = sale.document_number

            # Verify warranties created on till with synced=False
            till_warranties = s.query(Warranty).filter_by(sale_id=till_sale_id).order_by(Warranty.unit_index).all()
            assert len(till_warranties) == 2
            assert all(w.synced is False for w in till_warranties)
            assert till_warranties[0].code == f"{till_sale_doc}-01"
            assert till_warranties[1].code == f"{till_sale_doc}-02"
            till_w_ids = [w.id for w in till_warranties]

    # 4. Till pushes transactions to Main PC
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        pushed = shop.push(TILL)
        assert pushed > 0

    # 5. Verify Main PC received the warranties with remapped IDs
    with shop.on("main"), shop.session("main") as s:
        main_sale = s.query(Sale).filter_by(document_number=till_sale_doc).one()
        assert main_sale.origin_terminal_id == TILL

        main_warranties = s.query(Warranty).filter_by(sale_id=main_sale.id).order_by(Warranty.unit_index).all()
        assert len(main_warranties) == 2
        assert main_warranties[0].code == f"{till_sale_doc}-01"
        assert main_warranties[1].code == f"{till_sale_doc}-02"
        assert main_warranties[0].product_id == prod_id
        assert main_warranties[0].policy_id == policy_id
        assert main_warranties[0].status == "ACTIVE"

        # Verify sync_id_map entries exist for warranties
        id_map_entries = (
            s.query(SyncIdMap)
            .filter(
                SyncIdMap.origin_terminal_id == TILL,
                SyncIdMap.table_name == "warranties",
            )
            .all()
        )
        assert len(id_map_entries) == 2

    # 6. Verify till marked warranties as synced=True
    with shop.on(TILL), shop.session(TILL) as s:
        refreshed_warranties = s.query(Warranty).filter(Warranty.id.in_(till_w_ids)).all()
        assert len(refreshed_warranties) == 2
        assert all(w.synced is True for w in refreshed_warranties)
