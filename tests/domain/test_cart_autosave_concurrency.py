"""Concurrency, transactional integrity, and race condition tests for CartAutosaveService (Issue #932).

Covers:
- Defect 1: Stale writes cannot overwrite or resurrect carts (monotonic revision/tombstone)
- Defect 3: No process lock held across DB I/O (no lock inversion deadlock with DB transactions)
- Defect 6: Feature-disable race blocks in-flight worker, and re-enabling does not restore discarded rows
"""

import threading
from decimal import Decimal

import pytest
from sqlalchemy import text

from cbpos.core.constants.features import Features
from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.database import Database
from cbpos.core.models import Product, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_autosave_service import CartAutosaveService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.feature_flags import FeatureFlags


@pytest.fixture
def admin_user(db_session):
    """Admin user for feature flag modifications."""
    role = db_session.query(Role).filter_by(name=ADMIN_ROLE_NAME).first()
    if not role:
        role = Role(name=ADMIN_ROLE_NAME)
        db_session.add(role)
        db_session.commit()

    user = db_session.query(User).filter_by(username="admin_conc").first()
    if not user:
        user = User(username="admin_conc", pin_hash="hash", role_id=role.id, is_active=True)
        db_session.add(user)
        db_session.commit()

    AuthService._current_user = user
    yield user
    AuthService._current_user = None


@pytest.fixture
def clean_concurrency_db(db_session, admin_user):
    """Ensure clean database and registry for concurrency tests."""
    db = Database()
    with db.get_session() as session:
        session.execute(text("DELETE FROM suspended_transactions"))
        session.commit()
    CartAutosaveService.reset_registry()
    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, True, acting_user_id=admin_user.id)
    yield db
    with db.get_session() as session:
        session.execute(text("DELETE FROM suspended_transactions"))
        session.commit()
    CartAutosaveService.reset_registry()


@pytest.fixture
def product_a(clean_concurrency_db):
    """Product A."""
    db = clean_concurrency_db
    with db.get_session() as session:
        prod = session.query(Product).filter_by(barcode="CONC-PROD-A").first()
        if not prod:
            prod = Product(
                name_en="Concurrency Product A",
                barcode="CONC-PROD-A",
                price=Decimal("100.00"),
                cost=Decimal("60.00"),
                is_active=True,
            )
            session.add(prod)
            session.commit()
            session.refresh(prod)
        return prod


@pytest.fixture
def product_b(clean_concurrency_db):
    """Product B."""
    db = clean_concurrency_db
    with db.get_session() as session:
        prod = session.query(Product).filter_by(barcode="CONC-PROD-B").first()
        if not prod:
            prod = Product(
                name_en="Concurrency Product B",
                barcode="CONC-PROD-B",
                price=Decimal("200.00"),
                cost=Decimal("120.00"),
                is_active=True,
            )
            session.add(prod)
            session.commit()
            session.refresh(prod)
        return prod


@pytest.mark.domain
def test_defect_1_stale_generation_cannot_overwrite_newer_autosave(clean_concurrency_db, product_a, product_b):
    """Defect 1: An older generation worker finishing late must NOT overwrite a newer generation save."""
    terminal_id = "TERM-CONC-01"
    cart1 = CartService()
    cart1.add_item(product_a, Decimal("1.000"))
    snap1 = CartAutosaveService.snapshot_cart(cart1)

    cart2 = CartService()
    cart2.add_item(product_b, Decimal("5.000"))
    snap2 = CartAutosaveService.snapshot_cart(cart2)

    gen1 = 1
    gen2 = 2

    # Deterministic sequence: Worker 2 (newer) commits first!
    saved2 = CartAutosaveService.save(snap2, terminal_id, gen2)
    assert saved2 is True

    # Worker 1 (older) attempts to save afterwards
    saved1 = CartAutosaveService.save(snap1, terminal_id, gen1)
    assert saved1 is False, "Stale save with older generation must be rejected"

    # Newest snapshot MUST win
    summary = CartAutosaveService.get_autosave_summary(terminal_id)
    assert summary is not None
    assert summary["total"] == Decimal("1000.00"), "Newer snapshot total (5 * 200) must remain"
    assert summary["item_count"] == 1


@pytest.mark.domain
def test_defect_1_in_flight_worker_cannot_resurrect_cart_after_sale_commits(clean_concurrency_db, product_a):
    """Defect 1: A worker that already checked generation cannot resurrect cart after sale commits."""
    terminal_id = "TERM-CONC-02B"
    cart = CartService()
    cart.add_item(product_a, Decimal("1.000"))
    snap = CartAutosaveService.snapshot_cart(cart)
    gen = 1

    # Save initial cart
    assert CartAutosaveService.save(snap, terminal_id, gen) is True
    assert CartAutosaveService.has_autosave(terminal_id) is True

    # Sale commits and deletes/tombstones autosave
    db = clean_concurrency_db
    with db.get_session() as session:
        CartAutosaveService.delete_autosave_in_session(session, terminal_id)
        session.commit()

    # Reset in-memory active generation to simulate race where worker already passed check or process restarted
    CartAutosaveService.reset_registry()

    # Worker attempts to write to DB
    saved = CartAutosaveService.save(snap, terminal_id, gen)
    assert saved is False, "Persisted revision must block stale worker from recreating row"
    assert CartAutosaveService.has_autosave(terminal_id) is False, "Cart must not be resurrected in DB"


@pytest.mark.domain
def test_defect_1_process_restart_monotonic_revision(clean_concurrency_db, product_a):
    """Defect 1: Process restart reads persisted revision and guarantees monotonic increase."""
    terminal_id = "TERM-CONC-03"
    cart = CartService()
    cart.add_item(product_a, Decimal("2.000"))
    snap = CartAutosaveService.snapshot_cart(cart)

    # Initial save at revision 5
    CartAutosaveService.save(snap, terminal_id, 5)

    # Simulate restart by resetting in-memory registry
    CartAutosaveService.reset_registry()

    # Next generation must be > 5
    next_gen = CartAutosaveService.get_next_generation(terminal_id)
    assert next_gen >= 6, f"Expected next generation > 5 after restart, got {next_gen}"

    # Stale write with gen 5 or below must fail
    assert CartAutosaveService.save(snap, terminal_id, 5) is False

    # Write with next_gen must succeed
    assert CartAutosaveService.save(snap, terminal_id, next_gen) is True


@pytest.mark.domain
def test_defect_3_no_deadlock_between_sale_transaction_and_autosave(monkeypatch, tmp_path):
    """Defect 3: No Python process lock held across DB I/O prevents deadlock with concurrent DB transactions."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from cbpos.core.models import Base

    db_path = tmp_path / "test_conc.db"
    file_engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(file_engine)

    ThreadSession = sessionmaker(bind=file_engine)

    class ThreadSafeDatabase:
        def get_session(self):
            return ThreadSession()

    monkeypatch.setattr("cbpos.core.services.cart_autosave_service.Database", ThreadSafeDatabase)

    terminal_id = "TERM-CONC-DEADLOCK"
    snap = {"json_data": '{"lines": []}', "customer_id": None}
    CartAutosaveService.save(snap, terminal_id, 1)

    barrier = threading.Barrier(2)
    errors = []

    def sale_thread():
        try:
            with ThreadSession() as session:
                # Hold DB transaction
                session.execute(text("SELECT 1"))
                barrier.wait(timeout=3)
                # Call delete_autosave_in_session inside DB transaction
                CartAutosaveService.delete_autosave_in_session(session, terminal_id)
                session.commit()
        except Exception as e:
            errors.append(f"sale_thread error: {e}")

    def save_thread():
        try:
            barrier.wait(timeout=3)
            # Call save concurrently
            CartAutosaveService.save(snap, terminal_id, 2)
        except Exception as e:
            errors.append(f"save_thread error: {e}")

    t1 = threading.Thread(target=sale_thread)
    t2 = threading.Thread(target=save_thread)
    t1.start()
    t2.start()
    t1.join(timeout=4)
    t2.join(timeout=4)

    assert not t1.is_alive(), "Sale thread deadlocked!"
    assert not t2.is_alive(), "Save thread deadlocked!"
    assert not errors, f"Threads encountered errors: {errors}"


@pytest.mark.domain
def test_defect_6_feature_disable_race_blocks_worker_and_no_resurrect_on_reenable(
    clean_concurrency_db, admin_user, product_a
):
    """Defect 6: Disabling feature blocks in-flight worker, and re-enabling flag later does not restore discarded rows."""
    terminal_id = "TERM-CONC-FLAG"
    cart = CartService()
    cart.add_item(product_a, Decimal("1.000"))
    snap = CartAutosaveService.snapshot_cart(cart)

    CartAutosaveService.save(snap, terminal_id, 1)
    assert CartAutosaveService.has_autosave(terminal_id) is True

    # Disable feature flag
    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, False, acting_user_id=admin_user.id)

    # In-flight worker tries to save
    saved = CartAutosaveService.save(snap, terminal_id, 2)
    assert saved is False, "Worker must be blocked from writing when feature is disabled"

    # Re-enable feature flag
    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, True, acting_user_id=admin_user.id)

    # Must NOT have restored the discarded row
    assert CartAutosaveService.has_autosave(terminal_id) is False, "Re-enabling flag must NOT restore discarded cart"


@pytest.mark.domain
def test_defect_1_tombstone_invalidates_all_issued_generations_high_watermark(clean_concurrency_db, product_a):
    """Defect 1: Consuming transaction (sale/hold/clear) must invalidate all generations already issued
    in memory even if they were not yet persisted in DB. An older worker with generation <= watermark
    must not resurrect the cart.
    """
    terminal_id = "TERM-HIGH-WATERMARK"
    cart = CartService()
    cart.add_item(product_a, Decimal("1.000"))
    snap = CartAutosaveService.snapshot_cart(cart)

    # Persist initial cart at generation 1
    assert CartAutosaveService.save(snap, terminal_id, 1) is True

    # Simulate issuing generations 2 through 10 in memory without saving yet (e.g. rapid keystrokes/mutations)
    for _ in range(9):
        gen_issued = (
            CartAutosaveService.issue_generation(terminal_id)
            if hasattr(CartAutosaveService, "issue_generation")
            else CartAutosaveService.advance_generation(terminal_id)
        )

    assert gen_issued >= 10

    # Consuming transaction occurs (sale/clear/discard)
    db = clean_concurrency_db
    with db.get_session() as session:
        CartAutosaveService.delete_autosave_in_session(session, terminal_id)
        session.commit()

    # Now a delayed worker with generation 10 wakes up and attempts to save
    saved = CartAutosaveService.save(snap, terminal_id, 10)
    assert saved is False, "Worker with issued generation 10 must be blocked by the high-watermark tombstone"
    assert CartAutosaveService.has_autosave(terminal_id) is False, (
        "Cart must not be resurrected after consuming transaction"
    )


@pytest.mark.domain
def test_defect_1_zero_database_queries_on_generation_issuance(clean_concurrency_db):
    """Defect 1 / Architectural Directive: Zero database queries may run on the Qt UI thread
    during generation issuance on cart mutations.
    """
    from sqlalchemy import event

    terminal_id = "TERM-ZERO-QUERY"
    db = clean_concurrency_db
    query_count = 0

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db.engine
    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        # Issue 5 generations
        for _ in range(5):
            if hasattr(CartAutosaveService, "issue_generation"):
                CartAutosaveService.issue_generation(terminal_id)
            else:
                CartAutosaveService.advance_generation(terminal_id)

        assert query_count == 0, (
            f"Expected 0 database queries on UI thread during generation issuance, got {query_count}"
        )
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


@pytest.mark.domain
def test_defect_2_failed_recall_preserves_autosave_row_and_rolls_back_cart(clean_concurrency_db, product_a):
    """Defect 2: Failed recall must NOT delete or tombstone the autosave row, and must preserve/revert
    the cart state so the bill remains restorable.
    """
    terminal_id = "TERM-RECALL-FAIL"
    cart = CartService()
    cart.add_item(product_a, Decimal("3.000"))
    snap = CartAutosaveService.snapshot_cart(cart)
    CartAutosaveService.save(snap, terminal_id, 1)

    restoring_cart = CartService()

    # Simulate failure during restore by patching add_item to raise an error
    with pytest.MonkeyPatch.context() as mp:

        def failing_add_item(*args, **kwargs):
            raise RuntimeError("Injected failure during restore replay")

        mp.setattr(restoring_cart, "add_item", failing_add_item)

        res = CartAutosaveService.restore_autosave(terminal_id, restoring_cart)
        assert res.ok is False, "Restore must report failure when item restore fails"

    # Cart must be clean (no partial corrupted items)
    assert len(restoring_cart.items) == 0

    # Autosave row in DB must STILL BE ACTIVE and RESTORABLE!
    summary = CartAutosaveService.get_autosave_summary(terminal_id)
    assert summary is not None, "Autosave row must NOT be deleted/tombstoned when recall fails!"
    assert summary["item_count"] == 1
    assert summary["total_qty"] == Decimal("3.000")


@pytest.mark.domain
def test_defect_4_manual_hold_and_autosave_tombstone_atomic(clean_concurrency_db, product_a):
    """Defect 4: Manual hold and autosave tombstone must execute atomically in a single transaction."""
    from cbpos.core.models import SuspendedTransaction
    from cbpos.core.services.suspended_transaction_service import SuspendedTransactionService

    terminal_id = "TERM-HOLD-ATOMIC"
    cart = CartService()
    cart.add_item(product_a, Decimal("2.000"))
    snap = CartAutosaveService.snapshot_cart(cart)
    CartAutosaveService.save(snap, terminal_id, 1)

    assert CartAutosaveService.has_autosave(terminal_id) is True

    # Call atomic hold_bill_and_consume_autosave
    held_id = SuspendedTransactionService.hold_bill_and_consume_autosave(cart, terminal_id, note="Test Hold")
    assert held_id is not None

    db = clean_concurrency_db
    with db.get_session() as session:
        # Held bill exists
        held_row = session.get(SuspendedTransaction, held_id)
        assert held_row is not None
        assert held_row.is_autosave is False
        assert held_row.data is not None

        # Autosave is tombstoned
        autosave_row = (
            session.query(SuspendedTransaction)
            .filter(
                SuspendedTransaction.is_autosave.is_(True),
                SuspendedTransaction.terminal_id == terminal_id,
            )
            .first()
        )
        assert autosave_row is not None
        assert autosave_row.data is None, "Autosave row must be tombstoned (data=None)"
