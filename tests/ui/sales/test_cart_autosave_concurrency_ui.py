"""UI-level regression tests for Phase 10B.1 review defects (#932).

Covers:
- Defect 2: Unsafe QThread ownership / serialized autosave pipeline coalescing mutations
- Defect 4: Payment dialog cancellation/failure preserves autosave
- Defect 5: Customer-only mutations schedule autosave
- Defect 7: Failed hold does not delete recovery copy
- Defect 8: Recovery prompted across later login sessions after Esc
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.constants.features import Features
from cbpos.core.constants.permissions import ADMIN_ROLE_NAME
from cbpos.core.models import Customer, Product, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.cart_autosave_service import CartAutosaveService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.feature_flags import FeatureFlags
from cbpos.core.services.suspended_transaction_service import SuspendedTransactionService
from cbpos.ui.dialogs.autosave_recovery_dialog import AutosaveAction, AutosaveRecoveryDialog
from cbpos.ui.dialogs.payment_dialog import PaymentDialog
from cbpos.ui.views.sales_view import SalesView


@pytest.fixture
def cashier_user(db_session):
    """Create test cashier user."""
    role = db_session.query(Role).filter_by(name=ADMIN_ROLE_NAME).first()
    if not role:
        role = Role(name=ADMIN_ROLE_NAME)
        db_session.add(role)
        db_session.commit()

    user = db_session.query(User).filter_by(username="cashier_ui_conc").first()
    if not user:
        user = User(username="cashier_ui_conc", pin_hash="hash", role_id=role.id, is_active=True)
        db_session.add(user)
        db_session.commit()

    AuthService._current_user = user
    FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, True, acting_user_id=user.id)
    yield user
    AuthService._current_user = None


@pytest.fixture
def sample_product(db_session):
    """Create test product."""
    prod = db_session.query(Product).filter_by(barcode="UI-DEFECT-PROD").first()
    if not prod:
        prod = Product(
            name_en="Defect Test Product",
            barcode="UI-DEFECT-PROD",
            price=Decimal("150.00"),
            cost=Decimal("90.00"),
            stock_qty=Decimal("100.000"),
            is_active=True,
        )
        db_session.add(prod)
        db_session.commit()
    return prod


@pytest.fixture
def sample_customer(db_session):
    """Create test customer."""
    cust = db_session.query(Customer).filter_by(phone="0771234567").first()
    if not cust:
        cust = Customer(
            name="Test Customer",
            phone="0771234567",
            loyalty_points=50,
        )
        db_session.add(cust)
        db_session.commit()
    return cust


@pytest.mark.ui
def test_defect_2_sales_view_serializes_workers_and_coalesces_mutations(
    qtbot, db_session, cashier_user, sample_product
):
    """Defect 2: At most one worker runs at a time; mutations while busy are coalesced into a single pending save."""
    terminal_id = "TERM-UI-SERIAL"
    ConfigService.set("terminal_id", terminal_id)

    view = SalesView()
    qtbot.addWidget(view)

    # Add first item
    view.cart_service.add_item(sample_product, Decimal("1.000"))
    view.update_cart_display()

    # Worker should be running or dispatachable
    assert view._autosave_timer.isActive() is True

    # Simulate busy worker
    mock_running_worker = MagicMock()
    mock_running_worker.isRunning.return_value = True
    view._autosave_worker = mock_running_worker

    # Timer fires while worker is busy -> must coalesce without spawning new worker
    view._on_autosave_timer_fired()

    assert view._pending_autosave is True
    # The worker must not be replaced
    assert view._autosave_worker is mock_running_worker


@pytest.mark.ui
def test_defect_4_cancelled_payment_preserves_autosave(qtbot, db_session, cashier_user, sample_product):
    """Defect 4: Cancelling PaymentDialog preserves autosave; pending timer is flushed before dialog and preserved on cancel."""
    terminal_id = "TERM-UI-PAY-CANCEL"
    ConfigService.set("terminal_id", terminal_id)

    view = SalesView()
    qtbot.addWidget(view)

    # Add item - timer is now pending (debouncing)
    view.cart_service.add_item(sample_product, Decimal("2.000"))
    view.update_cart_display()
    assert view._autosave_timer.isActive() is True

    # User presses Pay (F5) while autosave was still debouncing, and cancels payment
    with patch.object(PaymentDialog, "exec", return_value=0):
        view.process_payment()

    # Cart must still have items AND the autosave MUST be present in DB (not discarded or lost by stopping timer)
    assert len(view.cart_service.items) == 1
    assert CartAutosaveService.has_autosave(terminal_id) is True, (
        "Autosave must be saved and preserved on payment cancel"
    )
    summary = CartAutosaveService.get_autosave_summary(terminal_id)
    assert summary is not None
    assert summary["item_count"] == 1
    assert summary["total"] == Decimal("300.00")


@pytest.mark.ui
def test_defect_5_customer_mutations_schedule_autosave(
    qtbot, db_session, cashier_user, sample_product, sample_customer
):
    """Defect 5: Selecting and clearing customer schedules autosave."""
    terminal_id = "TERM-UI-CUST"
    ConfigService.set("terminal_id", terminal_id)

    view = SalesView()
    qtbot.addWidget(view)

    # Add item
    view.cart_service.add_item(sample_product, Decimal("1.000"))
    view.update_cart_display()

    # Save initial state without customer
    view._autosave_timer.stop()
    view._on_autosave_timer_fired()

    summary = CartAutosaveService.get_autosave_summary(terminal_id)
    assert summary is not None
    assert summary["customer_id"] is None

    # Select customer
    view.set_customer(sample_customer)

    # Timer must be scheduled
    assert view._autosave_timer.isActive() is True, "set_customer must schedule autosave debounce"
    view._autosave_timer.stop()
    view._on_autosave_timer_fired()

    summary = CartAutosaveService.get_autosave_summary(terminal_id)
    assert summary is not None
    assert summary["customer_id"] == sample_customer.id, "Autosave must include selected customer"

    # Clear customer
    view.clear_customer()
    assert view._autosave_timer.isActive() is True, "clear_customer must schedule autosave debounce"
    view._autosave_timer.stop()
    view._on_autosave_timer_fired()

    summary = CartAutosaveService.get_autosave_summary(terminal_id)
    assert summary is not None
    assert summary["customer_id"] is None, "Autosave must reflect cleared customer"


@pytest.mark.ui
def test_defect_7_failed_hold_preserves_autosave(qtbot, db_session, cashier_user, sample_product):
    """Defect 7: If hold_bill fails, autosave is NOT deleted and remains recoverable."""
    terminal_id = "TERM-UI-HOLD-FAIL"
    ConfigService.set("terminal_id", terminal_id)

    view = SalesView()
    qtbot.addWidget(view)

    # Add item and persist autosave
    view.cart_service.add_item(sample_product, Decimal("3.000"))
    view.update_cart_display()
    view._autosave_timer.stop()
    view._on_autosave_timer_fired()

    assert CartAutosaveService.has_autosave(terminal_id) is True

    # Simulate hold_bill failing (returns None)
    from PyQt6.QtWidgets import QMessageBox

    with (
        patch.object(SuspendedTransactionService, "hold_bill", return_value=None),
        patch.object(SuspendedTransactionService, "hold_bill_and_consume_autosave", return_value=None),
        patch.object(QMessageBox, "critical"),
    ):
        view.hold_bill()

    # Cart remains and autosave MUST still be present
    assert len(view.cart_service.items) == 1
    assert CartAutosaveService.has_autosave(terminal_id) is True, "Failed hold must NOT delete autosave"


@pytest.mark.ui
def test_defect_8_recovery_prompted_across_logins_after_esc(qtbot, db_session, cashier_user, sample_product):
    """Defect 8: If user presses Esc on recovery dialog, subsequent login sessions prompt again."""
    terminal_id = "TERM-UI-LOGIN-ESC"
    ConfigService.set("terminal_id", terminal_id)

    # Pre-save an autosave
    cart = CartService()
    cart.add_item(sample_product, Decimal("2.000"))
    snap = CartAutosaveService.snapshot_cart(cart)
    CartAutosaveService.save(snap, terminal_id, 1)

    view = SalesView()
    qtbot.addWidget(view)

    prompt_count = 0

    def mock_exec_esc(dlg_self):
        nonlocal prompt_count
        prompt_count += 1
        dlg_self.action = AutosaveAction.IGNORE
        return False

    # First login triggers showEvent
    with patch.object(AutosaveRecoveryDialog, "exec", mock_exec_esc):
        view.showEvent(None)

    assert prompt_count == 1
    # Autosave must still be on disk
    assert CartAutosaveService.has_autosave(terminal_id) is True

    # User logs out
    view.end_session()

    # Next login: showEvent must prompt again!
    with patch.object(AutosaveRecoveryDialog, "exec", mock_exec_esc):
        view.showEvent(None)

    assert prompt_count == 2, "New session after logout must re-check autosave recovery"


@pytest.mark.ui
def test_defect_3_failed_logout_hold_and_autosave_aborts_logout_and_preserves_cart(
    qtbot, db_session, cashier_user, sample_product
):
    """Defect 3: If both auto-hold and autosave fail on logout, end_session must return False,
    show an actionable error dialog in _t(), and NOT clear the cart items or customer.
    MainWindow.logout must abort logout and keep user on POS with cart intact.
    """
    from PyQt6.QtWidgets import QMessageBox

    view = SalesView()
    qtbot.addWidget(view)
    view.cart_service.add_item(sample_product, Decimal("2.000"))
    assert len(view.cart_service.items) == 1

    # Simulate database failure for both hold and autosave
    with (
        patch.object(SuspendedTransactionService, "hold_bill", return_value=None),
        patch.object(SuspendedTransactionService, "hold_bill_and_consume_autosave", return_value=None, create=True),
        patch.object(CartAutosaveService, "save", return_value=False),
        patch.object(QMessageBox, "critical") as mock_critical,
    ):
        res = view.end_session(reason="MANUAL")

        # Actionable error message displayed
        mock_critical.assert_called_once()

        # end_session must return False to signal failure
        assert res is False

        # Cart items and customer NOT lost!
        assert len(view.cart_service.items) == 1


@pytest.mark.ui
def test_defect_6_failed_background_save_retries_with_backoff_and_shows_warning(
    qtbot, db_session, cashier_user, sample_product
):
    """Defect 6: Failed background save retries up to 3 times with backoff, surfaces a warning
    notice on exhaustion, and keeps the cart dirty.
    """
    terminal_id = "TERM-UI-RETRY"
    ConfigService.set("terminal_id", terminal_id)

    view = SalesView()
    qtbot.addWidget(view)
    view.cart_service.add_item(sample_product, Decimal("1.000"))

    with patch.object(view, "_show_status_message") as mock_status:
        # 1st failure: retry scheduled
        view._on_autosave_worker_finished(False, terminal_id, 1)
        assert getattr(view, "_autosave_retry_count", 0) == 1
        assert hasattr(view, "_autosave_retry_timer")
        assert view._autosave_retry_timer.isActive() is True

        # 2nd failure
        view._on_autosave_worker_finished(False, terminal_id, 1)
        assert getattr(view, "_autosave_retry_count", 0) == 2

        # 3rd failure: retries exhausted -> show warning notice
        view._on_autosave_worker_finished(False, terminal_id, 1)
        assert getattr(view, "_autosave_retry_count", 0) == 0  # reset for future
        assert view._pending_autosave is True  # cart remains dirty for next attempt
        mock_status.assert_called_once()


@pytest.mark.ui
def test_defect_7_timed_wait_transfers_running_worker_to_background_registry(
    qtbot, db_session, cashier_user, sample_product
):
    """Defect 7: When closeEvent waits on a worker that doesn't finish within timeout,
    the worker must NOT be dropped or set to None; it must be retained in the application-level
    background job registry until it finishes so Qt/Python does not abort.
    """
    import threading

    from PyQt6.QtCore import QThread
    from PyQt6.QtGui import QCloseEvent

    from cbpos.ui.workers import running_background_jobs

    terminal_id = "TERM-UI-CLOSE-WORKER"
    ConfigService.set("terminal_id", terminal_id)

    view = SalesView()
    qtbot.addWidget(view)

    stopped = threading.Event()

    class SlowWorker(QThread):
        def run(self):
            stopped.wait(timeout=2.0)

    slow_worker = SlowWorker()
    slow_worker.start()

    view._autosave_worker = slow_worker

    orig_wait = slow_worker.wait
    slow_worker.wait = lambda timeout=None: False

    close_event = QCloseEvent()
    view.closeEvent(close_event)

    try:
        assert slow_worker in running_background_jobs()
    finally:
        stopped.set()
        slow_worker.wait = orig_wait
        slow_worker.wait(2000)


@pytest.mark.ui
def test_defect_11_sales_view_collectible_via_weakref_no_closure_leak(qtbot, db_session, cashier_user):
    """Defect 11: SalesView must not leak via strong closure captures in call_on_destroyed.
    Weak reference to destroyed SalesView must clear after garbage collection.
    """
    import gc
    import weakref

    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication

    view = SalesView()
    ref = weakref.ref(view)

    # Close and remove Qt widget
    view.close()
    view.deleteLater()
    del view

    # Process events and trigger gc
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()
    gc.collect()

    assert ref() is None, "SalesView leaked in memory (cycle retained via destroy hooks closure)"
