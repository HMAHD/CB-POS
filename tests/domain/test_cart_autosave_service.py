"""Tests for CartAutosaveService (Phase 10B.1 / #932)."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from cbpos.core.database import Database
from cbpos.core.models import (
    Customer,
    Product,
    SuspendedTransaction,
)
from cbpos.core.services.cart_autosave_service import CartAutosaveService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.suspended_transaction_service import SuspendedTransactionService


@pytest.fixture
def clean_autosave_db(db_session):
    """Ensure database is clean before and after test."""
    db = Database()
    with db.get_session() as session:
        session.execute(text("DELETE FROM suspended_transactions"))
        session.execute(
            text(
                "INSERT OR REPLACE INTO feature_flags (name, enabled, last_modified) "
                "VALUES ('power_cut_autosave', 1, CURRENT_TIMESTAMP)"
            )
        )
        session.commit()
    from cbpos.core.services.feature_flags import FeatureFlags

    FeatureFlags.invalidate_cache()
    CartAutosaveService.reset_registry()
    yield db
    with db.get_session() as session:
        session.execute(text("DELETE FROM suspended_transactions"))
        session.commit()
    CartAutosaveService.reset_registry()


@pytest.fixture
def sample_product(clean_autosave_db):
    """Create a sample active product."""
    db = clean_autosave_db
    with db.get_session() as session:
        prod = session.query(Product).filter_by(barcode="AUTOSAVE-01").first()
        if not prod:
            prod = Product(
                name_en="Autosave Test Item",
                barcode="AUTOSAVE-01",
                price=Decimal("250.00"),
                cost=Decimal("150.00"),
                is_active=True,
            )
            session.add(prod)
            session.commit()
            session.refresh(prod)
        return prod


@pytest.mark.domain
def test_issue_932_autosave_save_and_summary(clean_autosave_db, sample_product):
    """CartAutosaveService saves the open cart and extracts an accurate summary."""
    cart = CartService()
    cart.add_item(sample_product, Decimal("2.000"))

    terminal_id = "TERM-TEST-01"
    gen = CartAutosaveService.get_active_generation(terminal_id)
    snapshot = CartAutosaveService.snapshot_cart(cart)

    saved = CartAutosaveService.save(snapshot, terminal_id, gen)
    assert saved is True

    summary = CartAutosaveService.get_autosave_summary(terminal_id)
    assert summary is not None
    assert summary["item_count"] == 1
    assert summary["total_qty"] == Decimal("2.000")
    assert summary["total"] == Decimal("500.00")
    assert summary["terminal_id"] == terminal_id


@pytest.mark.domain
def test_issue_932_autosave_upsert_at_most_one_per_terminal(clean_autosave_db, sample_product):
    """Multiple autosaves on the same terminal update the single existing record."""
    cart = CartService()
    cart.add_item(sample_product, Decimal("1.000"))
    terminal_id = "TERM-TEST-02"

    gen1 = CartAutosaveService.get_active_generation(terminal_id)
    snap1 = CartAutosaveService.snapshot_cart(cart)
    CartAutosaveService.save(snap1, terminal_id, gen1)

    # Mutate cart
    cart.add_item(sample_product, Decimal("2.000"))
    gen2 = CartAutosaveService.advance_generation(terminal_id)
    snap2 = CartAutosaveService.snapshot_cart(cart)
    CartAutosaveService.save(snap2, terminal_id, gen2)

    db = clean_autosave_db
    with db.get_session() as session:
        rows = (
            session.query(SuspendedTransaction)
            .filter(
                SuspendedTransaction.is_autosave.is_(True),
                SuspendedTransaction.terminal_id == terminal_id,
            )
            .all()
        )
        assert len(rows) == 1
        summary = CartAutosaveService.get_autosave_summary(terminal_id)
        assert summary["total_qty"] == Decimal("3.000")
        assert summary["total"] == Decimal("750.00")


@pytest.mark.domain
def test_issue_932_autosave_terminal_isolation(clean_autosave_db, sample_product):
    """Terminals store independent autosaves and never read each other's carts."""
    cart1 = CartService()
    cart1.add_item(sample_product, Decimal("1.000"))

    cart2 = CartService()
    cart2.add_item(sample_product, Decimal("4.000"))

    term_a = "TERM-A"
    term_b = "TERM-B"

    CartAutosaveService.save(
        CartAutosaveService.snapshot_cart(cart1),
        term_a,
        CartAutosaveService.get_active_generation(term_a),
    )
    CartAutosaveService.save(
        CartAutosaveService.snapshot_cart(cart2),
        term_b,
        CartAutosaveService.get_active_generation(term_b),
    )

    summary_a = CartAutosaveService.get_autosave_summary(term_a)
    summary_b = CartAutosaveService.get_autosave_summary(term_b)

    assert summary_a["total_qty"] == Decimal("1.000")
    assert summary_b["total_qty"] == Decimal("4.000")

    # Discarding term_a leaves term_b untouched
    CartAutosaveService.discard_autosave(term_a)
    assert CartAutosaveService.get_autosave_summary(term_a) is None
    assert CartAutosaveService.get_autosave_summary(term_b) is not None


@pytest.mark.domain
def test_issue_932_held_bills_separation(clean_autosave_db, sample_product):
    """Manual held-bill queries never expose or count autosaved carts."""
    cart = CartService()
    cart.add_item(sample_product, Decimal("2.000"))
    term = "TERM-HELD-TEST"

    # Save an autosave
    CartAutosaveService.save(
        CartAutosaveService.snapshot_cart(cart),
        term,
        CartAutosaveService.get_active_generation(term),
    )

    # Manual held bill list and count must be 0
    assert SuspendedTransactionService.get_held_bill_count() == 0
    assert len(SuspendedTransactionService.get_held_bills()) == 0
    assert SuspendedTransactionService.get_latest_suspended() is None

    # Hold a normal bill manually
    held_id = SuspendedTransactionService.hold_bill(cart, note="Manual Hold")
    assert held_id is not None

    # Manual list and count must be exactly 1
    assert SuspendedTransactionService.get_held_bill_count() == 1
    held_bills = SuspendedTransactionService.get_held_bills()
    assert len(held_bills) == 1
    assert held_bills[0].id == held_id
    assert held_bills[0].is_autosave is False

    # Autosave for terminal still exists independently
    assert CartAutosaveService.get_autosave_summary(term) is not None


@pytest.mark.domain
def test_issue_932_generation_token_drops_stale_writes(clean_autosave_db, sample_product):
    """Stale background save with older generation is rejected."""
    cart = CartService()
    cart.add_item(sample_product, Decimal("1.000"))
    term = "TERM-RACE-01"

    stale_gen = CartAutosaveService.get_active_generation(term)
    snap = CartAutosaveService.snapshot_cart(cart)

    # Invalidate generation (simulating clear/hold/new edit)
    CartAutosaveService.invalidate_and_delete(term)

    # Late worker tries to save with stale_gen
    result = CartAutosaveService.save(snap, term, stale_gen)
    assert result is False

    # No row was created
    assert CartAutosaveService.get_autosave_summary(term) is None


@pytest.mark.domain
def test_issue_932_corrupt_payload_fails_closed(clean_autosave_db):
    """Corrupt JSON in autosave row is discarded safely without raising exceptions."""
    db = clean_autosave_db
    term = "TERM-CORRUPT"

    with db.get_session() as session:
        bad_row = SuspendedTransaction(
            is_autosave=True,
            terminal_id=term,
            data="{malformed json: true,",
        )
        session.add(bad_row)
        session.commit()

    # get_autosave_summary should catch error, delete bad row, and return None
    summary = CartAutosaveService.get_autosave_summary(term)
    assert summary is None

    # Row must have been purged
    with db.get_session() as session:
        row = (
            session.query(SuspendedTransaction)
            .filter(
                SuspendedTransaction.is_autosave.is_(True),
                SuspendedTransaction.terminal_id == term,
            )
            .first()
        )
        assert row is None or row.data is None
        assert CartAutosaveService.has_autosave(term) is False


@pytest.mark.domain
def test_issue_932_restore_autosave_full_fidelity(clean_autosave_db, sample_product):
    """Restoring an autosave recovers products, quantities, prices, discounts, serials, and customer."""
    db = clean_autosave_db
    with db.get_session() as session:
        cust = session.query(Customer).filter_by(phone="0771234567").first()
        if not cust:
            cust = Customer(name="Autosave Customer", phone="0771234567")
            session.add(cust)
            session.commit()
            session.refresh(cust)

    cart = CartService()
    cart.set_customer(cust)
    cart.add_item(sample_product, Decimal("2.000"), serials=["SN-1001", "SN-1002"])
    cart.apply_line_discount(0, "PERCENT", Decimal("10.00"))
    cart.items[0]["note"] = "Special request"

    term = "TERM-RESTORE"
    snap = CartAutosaveService.snapshot_cart(cart)
    gen = CartAutosaveService.get_active_generation(term)
    CartAutosaveService.save(snap, term, gen)

    # Empty the cart
    restored_cart = CartService()
    assert len(restored_cart.items) == 0

    # Restore from autosave
    res = CartAutosaveService.restore_autosave(term, restored_cart)
    assert res.ok is True
    assert len(restored_cart.items) == 1
    assert restored_cart.items[0]["qty"] == Decimal("2.000")
    assert restored_cart.items[0]["serials"] == ["SN-1001", "SN-1002"]
    assert restored_cart.items[0]["discount_type"] == "PERCENT"
    assert restored_cart.items[0]["discount_value"] == Decimal("10.00")
    assert restored_cart.items[0]["note"] == "Special request"
    assert restored_cart.get_customer().id == cust.id

    # The autosave record must be deleted upon restoration
    assert CartAutosaveService.get_autosave_summary(term) is None


@pytest.mark.domain
def test_defect_10_structurally_invalid_json_payloads_purged(clean_autosave_db):
    """Defect 10: Structurally invalid JSON (missing/null lines, invalid Decimal strings,
    non-dict root/totals) must be purged/tombstoned and return None from get_autosave_summary.
    """
    db = clean_autosave_db

    invalid_payloads = [
        '{"lines": null}',
        '{"lines": [{"qty": "invalid_number", "unit_price": "100.00"}]}',
        '{"lines": "not_a_list"}',
        '{"totals": "not_a_dict", "lines": []}',
        '["not_a_dict_root"]',
    ]

    for i, payload in enumerate(invalid_payloads):
        term = f"TERM-CORRUPT-{i}"
        with db.get_session() as session:
            row = SuspendedTransaction(
                is_autosave=True,
                terminal_id=term,
                data=payload,
                revision=1,
            )
            session.add(row)
            session.commit()

        # get_autosave_summary must classify as corrupt, tombstone/purge row, and return None
        summary = CartAutosaveService.get_autosave_summary(term)
        assert summary is None, f"Expected None for corrupt payload {payload}"

        # Row in DB must be tombstoned (data is None) so future queries don't keep failing on it
        with db.get_session() as session:
            row_after = (
                session.query(SuspendedTransaction)
                .filter(
                    SuspendedTransaction.is_autosave.is_(True),
                    SuspendedTransaction.terminal_id == term,
                )
                .first()
            )
            assert row_after is None or row_after.data is None, (
                f"Corrupt row for payload {payload} was not purged/tombstoned!"
            )
