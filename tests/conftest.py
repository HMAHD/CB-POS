import gc
import os
import sys
import threading
import traceback

import pytest

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from sqlalchemy import event
from sqlalchemy.orm import Session

from cbpos.config import Config
from cbpos.core.database import Base, Database

# Force in-memory DB for tests
# We import Config from cbpos.core.database to ensure we patch the exact object
# used there
from cbpos.core.database import Config as DBConfig

DBConfig.DB_URI = "sqlite:///:memory:"
Config.DB_URI = "sqlite:///:memory:"  # Patch global config too just in case


@pytest.fixture(scope="session")
def app_fixture(qapp):
    """
    Fixture to manage QApplication instance.
    pytest-qt provides 'qapp' fixture.
    """
    return qapp


@pytest.fixture(scope="session")
def test_engine():
    """
    Create a single engine for the test session.
    """
    # Reset Database singleton to ensure it uses our config
    Database._instance = None
    db = Database()

    # Create tables
    Base.metadata.create_all(bind=db.engine)

    return db.engine


@pytest.fixture(autouse=True)
def _autocomplete_preload_runs_inline():
    """Run SalesView's AutocompleteLoadWorker synchronously instead of on a QThread.

    ``SalesView.setup_autocomplete()`` starts the worker mid-``__init__``;
    its ``run()`` queries products via ``Database().get_session()`` on a
    background thread while the main thread keeps building the view --
    ``OrderBar``'s ``refresh_tabs()`` -> ``get_held_bills()`` right after.
    In production each call gets its own Session, but under ``db_session``
    both threads get the *same* Session, so every SalesView build raced
    two threads on one Session: #501's random "session is provisioning a
    new connection; concurrent operations are not permitted" /
    "commit() already in progress" errors in whichever cart/sales test
    lost the race. Running ``run()`` inline keeps the completer populated
    (``result`` fires as a direct call) with no second thread.

    Patched by hand rather than via ``monkeypatch``: requesting
    ``monkeypatch`` from an autouse fixture sets it up ahead of
    ``_collect_garbage_after_each_test``, so every test's own monkeypatches
    would be undone only *after* that fixture's gc/thread-drain pass instead
    of before it -- which reorders teardown enough to segfault later tests.
    """
    from cbpos.ui.workers import AutocompleteLoadWorker

    AutocompleteLoadWorker.start = AutocompleteLoadWorker.run
    try:
        yield
    finally:
        del AutocompleteLoadWorker.start


@pytest.fixture(autouse=True)
def _collect_garbage_after_each_test():
    """Force a GC pass after every test, then wait out any background thread left running.

    Views/dialogs following the register_language_callback pattern used to
    leak forever via a reference cycle (self -> destroyed-connection ->
    lambda -> self) that only a full gc.collect() could break -- fixed
    across 26 files in #392. Any surviving cycle of that shape (or a
    similar one not yet found) keeps a widget, and anything it owns (a
    debounce QTimer, etc.), alive past its test. A leaked timer can then
    fire during a *later*, unrelated test and touch the shared db_session
    fixture concurrently with that test's own DB activity -- the exact
    mechanism behind #389's and #501's intermittent, always-a-different-
    test failures (observed error:
    ``IllegalStateChangeError: rollback() can't be called here; commit()
    already in progress``).

    That covers leaked *widgets*, but #501 kept recurring after #392/#389
    because a second, distinct source produces the identical symptom: a
    genuine background ``QThread`` (dashboard's ``_PeriodicWorker`` /
    ``_YearlyWorker``, which call ``DashboardService`` -- real DB queries
    -- straight from ``run()``) started by a test via ``.start()`` and
    never waited on. That thread keeps executing on a real OS thread after
    its own test returns, and whichever *later* test happens to be running
    when it eventually calls ``Database().get_session()`` gets raced --
    hence a different unrelated test failing every run (observed directly
    as ``SAWarning: nested transaction already deassociated from
    connection`` in test_dashboard_periodic_date_bounds.py, which calls
    ``DashboardView.refresh_periodic()`` and never joins the worker it
    starts). ``PrintWorker`` is the other realistic offender, but it's a
    documented infinite loop until ``.stop()`` -- waiting on it here
    without stopping it first would hang the suite, so it gets its own
    explicit, idempotent shutdown (safe even when no instance exists).
    Any other QThread (CSV import, backup, etc.) is bounded and self-
    deletes on ``finished``, so a plain ``.wait()`` is enough to drain it
    before the next test's db_session takes over Database.SessionLocal.
    EmailService is the same hazard via a plain ``threading.Thread``
    instead of QThread (its own docstring: "no PyQt dependency"), so
    ``threading.enumerate()`` -- the one registry covering every live
    thread regardless of kind -- gets the same treatment.

    Placed textually before ``db_session`` so it tears down *after*
    db_session's own cleanup (autouse fixtures set up before, and tear
    down after, other fixtures of the same scope) -- any stray callback
    this collection pass triggers hits a fresh, non-test session via the
    already-restored original SessionLocal factory, not a session
    mid-rollback.
    """
    yield
    gc.collect()

    from PyQt6.QtCore import QThread

    from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

    PrintWorker.shutdown()

    for obj in gc.get_objects():
        try:
            if isinstance(obj, QThread) and obj.isRunning():
                obj.wait(2000)
        except RuntimeError:
            # The Python wrapper is still gc-tracked but its underlying
            # C++ QObject was already destroyed (deleteLater() fired) --
            # nothing to wait on.
            continue

    # EmailService uses a plain threading.Thread, not QThread (see its own
    # docstring: "no PyQt dependency") -- invisible to the QThread sweep
    # above but the same hazard: it can still be running when a later
    # test's db_session takes over. threading.enumerate() is the one
    # registry that covers every live thread regardless of kind.
    for thread in threading.enumerate():
        if thread is threading.main_thread() or not thread.is_alive():
            continue
        try:
            thread.join(timeout=2)
        except AssertionError:
            # A "dummy thread" -- Python's placeholder for a foreign
            # (non-Python-created) OS thread calling back into the
            # interpreter, e.g. Qt's own thread pool. Not ours to join.
            continue


@pytest.fixture
def db_session(test_engine):
    """
    Transactional fixture that rolls back after each test.
    Patches Database.SessionLocal to return this session.

    Uses SQLAlchemy 2.0's documented "join a Session into an external
    transaction" recipe: the SAVEPOINT is tracked as a Core-level
    ``connection.begin_nested()`` handle, not a ``session.begin_nested()``
    one. The previous version tracked it at the ORM/session level, which
    let a service's ``session.commit()`` (e.g. any read-only
    ``get_session()`` call) collapse the SAVEPOINT into the connection's
    real outer transaction -- so anything written earlier in the same
    test via a bare ``db_session.add(...); db_session.flush()`` (no
    commit) silently survived this fixture's rollback and leaked into
    every later test sharing the same in-memory database.
    """
    connection = test_engine.connect()
    transaction = connection.begin()

    # Bind session to the connection
    session = Session(bind=connection)

    # Patch Database.SessionLocal to return our test session
    # Services call db.SessionLocal(), so we mock it to return our session
    db = Database()
    original_factory = db.SessionLocal

    # We mock the factory to return our existing session
    # We also need to prevent session.close() from actually closing the connection
    # inside the service, as we want to control the transaction here.
    # We can mock close() on the session object itself.
    original_close = session.close
    session.close = lambda: None

    # A Session is not thread-safe, and this one is shared by every
    # get_session() call in the test. A background thread reaching it
    # races the test thread and surfaces as a random SQLAlchemy state
    # error in some unrelated test (#501), so refuse it outright and fail
    # the test at teardown, naming the offending thread and call site.
    owner_thread = threading.get_ident()
    cross_thread_uses: list[str] = []

    def _session_for_owner_thread_only():
        if threading.get_ident() != owner_thread:
            name = threading.current_thread().name
            cross_thread_uses.append(f"thread {name!r}:\n" + "".join(traceback.format_stack(limit=10)))
            raise RuntimeError(
                f"db_session's shared Session requested from background thread {name!r}. "
                "Sessions are not thread-safe; run that work inline in tests (see "
                "_autocomplete_preload_runs_inline in tests/conftest.py)."
            )
        return session

    db.SessionLocal = _session_for_owner_thread_only

    # Core-level SAVEPOINT, restarted whenever it ends (e.g. a service's
    # own session.commit()/rollback() releases it) so writes always stay
    # nested inside `transaction`, the one this fixture actually rolls
    # back at teardown.
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, _transaction):
        nonlocal nested
        if not nested.is_active:
            session.expire_all()
            nested = connection.begin_nested()

    yield session

    # Cleanup
    # Restore close so we can actually close it
    session.close = original_close
    session.close()
    transaction.rollback()
    connection.close()

    # Restore original factory
    db.SessionLocal = original_factory

    if cross_thread_uses:
        pytest.fail(
            "db_session's shared Session was requested from a background thread (#501):\n\n"
            + "\n".join(cross_thread_uses),
            pytrace=False,
        )
