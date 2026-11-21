"""Integration tests for two-machine sync feature disable on till autosaves (Issue #932 / Defect 5).

When power_cut_autosave is disabled centrally on the Main PC, sync pushes feature_flags
to tills. Tills must atomically tombstone all local autosaves in the exact same transaction
so obsolete carts cannot be recovered later.
"""

from decimal import Decimal

import pytest

from cbpos.core.constants.features import Features
from cbpos.core.models import FeatureFlag, Product, SuspendedTransaction
from cbpos.core.services.cart_autosave_service import CartAutosaveService
from cbpos.core.services.cart_service import CartService
from tests.helpers.sync_two_machines import Shop


@pytest.mark.integration
def test_two_machine_sync_feature_disable_tombstones_local_till_autosaves(tmp_path):
    """Defect 5: When Main PC disables power_cut_autosave, till catalog sync must
    tombstone all local autosaves in the same transaction. Re-enabling later must not
    resurrect the obsolete cart.
    """
    shop = Shop(str(tmp_path))
    till_id = "TERM-TILL-01"
    shop.add_till(till_id)

    # 1. Main PC has power_cut_autosave enabled
    with shop.session("main") as s:
        flag = FeatureFlag(name=Features.POWER_CUT_AUTOSAVE, enabled=True)
        s.add(flag)
        prod = Product(
            name_en="Sync Bread", barcode="SYNC-01", price=Decimal("100.00"), cost=Decimal("60.00"), is_active=True
        )
        s.add(prod)
        s.commit()

    # Initial pull on till
    shop.pull(till_id, full=True)

    # 2. Till creates a local open cart and autosaves it
    with shop.on(till_id):
        cart = CartService()
        with shop.session(till_id) as s:
            p = s.query(Product).filter_by(barcode="SYNC-01").first()
            cart.add_item(p, Decimal("3.000"))
        snap = CartAutosaveService.snapshot_cart(cart)
        saved = CartAutosaveService.save(snap, till_id, 1)
        assert saved is True
        assert CartAutosaveService.has_autosave(till_id) is True

    # 3. Main PC disables power_cut_autosave
    with shop.session("main") as s:
        flag = s.query(FeatureFlag).filter_by(name=Features.POWER_CUT_AUTOSAVE).first()
        flag.enabled = False
        s.commit()

    # 4. Till pulls catalog update
    applied = shop.pull(till_id)
    assert applied > 0

    # 5. On the till: local autosave row must be TOMBSTONED (data is NULL)
    with shop.on(till_id):
        with shop.session(till_id) as s:
            row = (
                s.query(SuspendedTransaction)
                .filter(
                    SuspendedTransaction.is_autosave.is_(True),
                    SuspendedTransaction.terminal_id == till_id,
                )
                .first()
            )
            assert row is not None
            assert row.data is None, "Till's local autosave must be tombstoned when feature is disabled via sync"

        assert CartAutosaveService.has_autosave(till_id) is False

    # 6. Re-enabling on Main PC and syncing again must NOT resurrect the cart
    with shop.session("main") as s:
        flag = s.query(FeatureFlag).filter_by(name=Features.POWER_CUT_AUTOSAVE).first()
        flag.enabled = True
        s.commit()

    shop.pull(till_id)

    with shop.on(till_id):
        assert CartAutosaveService.has_autosave(till_id) is False, (
            "Obsolete cart must NOT be resurrected on re-enabling"
        )


@pytest.mark.integration
def test_partial_catalog_pull_invalidates_feature_flags_cache_on_commit(tmp_path):
    """P1: When a catalog pull succeeds in applying feature_flags but encounters an error on
    an unrelated catalog record, the transaction commits the feature flags. The FeatureFlags
    cache MUST be invalidated so subsequent feature_visible() calls read the committed OFF value.
    """
    from cbpos.core.services.feature_flags import feature_visible
    from cbpos.core.services.sync_protocol import EP_PULL_CATALOG

    shop = Shop(str(tmp_path))
    till_id = "TERM-TILL-CACHE"
    shop.add_till(till_id)

    # 1. Main and Till initially have power_cut_autosave enabled
    with shop.session("main") as s:
        flag = FeatureFlag(name=Features.POWER_CUT_AUTOSAVE, enabled=True)
        s.add(flag)
        s.commit()

    shop.pull(till_id, full=True)

    # Warm up till's cache so feature_visible is True in memory
    with shop.on(till_id):
        assert feature_visible(Features.POWER_CUT_AUTOSAVE) is True

    # 2. Main PC serves a payload with valid power_cut_autosave=False AND an invalid product record
    client = shop.client(till_id)
    real_request = client._request

    def mock_pull_request(method, endpoint, data=None, timeout=10):
        if EP_PULL_CATALOG in endpoint:
            return {
                "timestamp": "2026-11-20T12:00:00",
                "total_records": 2,
                "payload": {
                    "feature_flags": [
                        {
                            "name": Features.POWER_CUT_AUTOSAVE,
                            "enabled": False,
                            "last_modified": "2026-11-20T12:00:00",
                        }
                    ],
                    "products": [
                        {
                            "id": 9999,
                            "name_en": "Corrupt Product",
                            # Missing required fields like barcode/price or invalid type to trigger exception
                            "price": "not_a_valid_decimal",
                        }
                    ],
                },
            }
        return real_request(method, endpoint, data, timeout)

    client._request = mock_pull_request

    # 3. Pull catalog on till (partial apply: feature flag succeeds, product fails)
    with shop.on(till_id):
        applied = client._pull_catalog()
        assert applied >= 1
        assert client._error_code == "catalog_apply_failed", "Watermark must not advance due to product failure"

        # 4. feature_visible() must immediately reflect the committed OFF value (cache must not be stale)
        assert feature_visible(Features.POWER_CUT_AUTOSAVE) is False, (
            "FeatureFlags cache was not invalidated after partial catalog pull committed flag update"
        )
