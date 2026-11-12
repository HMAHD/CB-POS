"""Integration tests for Warranty W1 (#821): Multi-terminal catalog sync for warranty policies."""

from decimal import Decimal

import pytest

from cbpos.core.models import Category, Product, WarrantyPolicy
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
