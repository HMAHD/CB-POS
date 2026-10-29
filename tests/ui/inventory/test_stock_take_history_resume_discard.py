"""
on_history_double_click only ever opened the read-only
StockCountReportDialog -- there was no edit, resume, void, or delete
action reachable from a History row at all. void_count() only acted on
self.current_stock_count, the in-memory count from the active session --
once that session ended (app restart, navigating away), a DRAFT count
sitting in History had no way back into an editable state and no way to
be discarded either. It just accumulated as permanent, unfinishable
clutter.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import StockCount, User
from cbpos.ui.views.stock_take_view import StockTakeView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_username() -> str:
    global _counter
    _counter += 1
    return f"stocktake_resume_test_user_{_counter}"


@pytest.fixture
def test_user(db_session):
    user = User(username=_next_username(), pin_hash="hash")
    db_session.add(user)
    db_session.flush()
    return user


def _make_draft_stock_count(db_session, test_user, doc_number):
    stock_count = StockCount(
        document_number=doc_number,
        type="stock_count",
        date=datetime.now(),
        user_id=test_user.id,
        status=DocumentStatus.DRAFT,
        note="test",
        total_variance_value=Decimal("0.00"),
    )
    db_session.add(stock_count)
    db_session.commit()
    stock_count_id = stock_count.id
    db_session.expunge(stock_count)
    return stock_count_id


class TestResumeDraftCount:
    def test_resume_loads_the_draft_as_the_active_count_and_switches_tabs(self, db_session, test_user):
        stock_count_id = _make_draft_stock_count(db_session, test_user, "STK-RESUME-1")
        view = StockTakeView()
        view.tabs.setCurrentIndex(1)

        view.resume_draft_count(stock_count_id)

        assert view.current_stock_count is not None
        assert view.current_stock_count.id == stock_count_id
        assert view.tabs.currentIndex() == 0

    def test_resume_on_a_non_draft_count_shows_an_error_and_does_not_load_it(self, db_session, test_user, monkeypatch):
        stock_count_id = _make_draft_stock_count(db_session, test_user, "STK-RESUME-2")
        from cbpos.core.services.stock_count_service import StockCountService

        StockCountService.void_stock_count(stock_count_id)

        view = StockTakeView()
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

        view.resume_draft_count(stock_count_id)

        assert view.current_stock_count is None


class TestDiscardDraftCount:
    def test_discard_voids_the_stock_count_when_confirmed(self, db_session, test_user, monkeypatch):
        stock_count_id = _make_draft_stock_count(db_session, test_user, "STK-DISCARD-1")
        view = StockTakeView()
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

        view.discard_draft_count(stock_count_id)

        from cbpos.core.services.stock_count_service import StockCountService

        refreshed = StockCountService.get_stock_count(stock_count_id)
        assert refreshed.status == DocumentStatus.VOID

    def test_discard_does_nothing_when_not_confirmed(self, db_session, test_user, monkeypatch):
        stock_count_id = _make_draft_stock_count(db_session, test_user, "STK-DISCARD-2")
        view = StockTakeView()
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)

        view.discard_draft_count(stock_count_id)

        from cbpos.core.services.stock_count_service import StockCountService

        refreshed = StockCountService.get_stock_count(stock_count_id)
        assert refreshed.status == DocumentStatus.DRAFT

    def test_discarding_the_currently_loaded_draft_resets_the_new_count_form(self, db_session, test_user, monkeypatch):
        stock_count_id = _make_draft_stock_count(db_session, test_user, "STK-DISCARD-3")
        view = StockTakeView()
        view.resume_draft_count(stock_count_id)
        assert view.current_stock_count.id == stock_count_id

        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
        view.discard_draft_count(stock_count_id)

        assert view.current_stock_count is None
