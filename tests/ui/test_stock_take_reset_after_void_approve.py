"""
UI-047 (#615): after Void or Approve & Apply, the finished count stayed
loaded with Load Products disabled -- and even "New Count" left it
disabled, because _update_stats() returned early for "no count" without
touching any button. A finished count now resets the form so Load
Products works straight away.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Product, User
from cbpos.core.services.stock_count_service import StockCountService
from cbpos.ui.views.stock_take_view import StockTakeView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def fresh_reads(db_session, monkeypatch):
    """Give get_stock_count a clean identity map, like production's session-per-call.

    The test fixture shares one Session across every service call, so a
    StockCount created earlier stays identity-mapped and session.get()
    ignores the joinedload of its items.
    """
    original = StockCountService.get_stock_count

    def _get(stock_count_id):
        db_session.expunge_all()
        return original(stock_count_id)

    monkeypatch.setattr(StockCountService, "get_stock_count", staticmethod(_get))


@pytest.fixture
def view_with_draft(db_session, monkeypatch, fresh_reads):
    user = User(username="stk_reset_user", pin_hash="hash")
    product = Product(barcode="4790000000301", name_en="Reset Rice", price=Decimal("10.00"), stock_qty=Decimal("2"))
    db_session.add_all([user, product])
    db_session.flush()

    for name in ("information", "warning"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda *a, **k: user)

    view = StockTakeView()
    # A plain id holder: fresh_reads detaches the ORM User mid-test.
    view.set_user(SimpleNamespace(id=user.id))
    view.current_stock_count = StockCountService.create_stock_count(user_id=user.id)
    item = StockCountService.add_single_item(view.current_stock_count.id, product.id)
    StockCountService.update_count(item.id, Decimal("2"))
    view._reload_items()
    yield view
    view.hide()


def test_void_resets_the_form_and_enables_load_products(view_with_draft):
    view = view_with_draft
    stock_count_id = view.current_stock_count.id

    view.void_count()

    assert StockCountService.get_stock_count(stock_count_id).status == DocumentStatus.VOID
    assert view.current_stock_count is None
    assert view.item_model.rowCount() == 0
    assert view.btn_load.isEnabled()
    assert not view.btn_void.isEnabled()


def test_approve_resets_the_form_and_enables_load_products(view_with_draft):
    view = view_with_draft
    view.finalize_count()
    assert view.current_stock_count.status == DocumentStatus.COUNTED

    view.approve_and_apply()

    assert view.current_stock_count is None
    assert view.btn_load.isEnabled()
    assert not view.btn_approve.isEnabled()


def test_new_count_after_a_void_reenables_load_products(view_with_draft):
    view = view_with_draft
    StockCountService.void_stock_count(view.current_stock_count.id)
    view._reload_items()
    assert not view.btn_load.isEnabled()

    view.reset_form()

    assert view.btn_load.isEnabled()
