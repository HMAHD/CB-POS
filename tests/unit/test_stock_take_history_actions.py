"""
UI-028-B (#594): Stock Take History was empty until Refresh was pressed,
rows opened only by double-click, and Resume/Discard lived only in the
right-click menu, so new users thought there were no counts and couldn't
find how to resume a draft.

History now loads when the tab is shown, and an action row under the
table (Open, Resume, Discard) follows the selected row's status: Resume
and Discard only for a DRAFT. Enter opens the selected row.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import StockCount, User
from cbpos.core.services.stock_count_service import StockCountService
from cbpos.ui.views import stock_take_view
from cbpos.ui.views.stock_take_view import StockTakeView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def user(db_session):
    user = User(username="stk_history_actions_user", pin_hash="hash")
    db_session.add(user)
    db_session.flush()
    return user


def _make_count(db_session, user, number: str, status: str) -> int:
    stock_count = StockCount(
        document_number=number,
        type="stock_count",
        date=datetime.now(),
        user_id=user.id,
        status=status,
        total_variance_value=Decimal("0.00"),
    )
    db_session.add(stock_count)
    db_session.flush()
    return stock_count.id


@pytest.fixture
def opened(monkeypatch):
    """Record which stock count the report dialog was opened for, without showing it."""
    ids: list[int] = []

    class _Report:
        def __init__(self, stock_count_id, parent=None):
            ids.append(stock_count_id)

        def exec(self):
            return 0

    monkeypatch.setattr(stock_take_view, "StockCountReportDialog", _Report)
    return ids


@pytest.fixture
def view():
    widget = StockTakeView()
    yield widget
    widget.hide()
    widget.deleteLater()


def _row_of(view, number: str) -> int:
    return next(r for r in range(view.history_table.rowCount()) if view.history_table.item(r, 0).text() == number)


def _actions(view) -> tuple[bool, bool, bool]:
    return (
        view.btn_hist_open.isEnabled(),
        view.btn_hist_resume.isEnabled(),
        view.btn_hist_discard.isEnabled(),
    )


class TestHistoryLoadsOnOpen:
    def test_showing_the_history_tab_lists_counts_without_refresh(self, db_session, user, view):
        _make_count(db_session, user, "STK-HIST-LOAD-1", DocumentStatus.DRAFT)

        view.tabs.setCurrentWidget(view.history_tab)

        assert view.history_table.rowCount() == 1
        assert view.history_table.item(0, 0).text() == "STK-HIST-LOAD-1"

    def test_reopening_the_view_on_history_picks_up_new_counts(self, db_session, user, view):
        view.tabs.setCurrentWidget(view.history_tab)
        view.show()
        _make_count(db_session, user, "STK-HIST-LOAD-2", DocumentStatus.COMPLETED)

        view.hide()
        view.show()

        assert view.history_table.item(0, 0).text() == "STK-HIST-LOAD-2"


class TestActionRow:
    def test_actions_are_disabled_with_no_selection(self, db_session, user, view):
        _make_count(db_session, user, "STK-HIST-ACT-0", DocumentStatus.DRAFT)
        view.tabs.setCurrentWidget(view.history_tab)

        assert _actions(view) == (False, False, False)

    def test_draft_row_enables_open_resume_and_discard(self, db_session, user, view):
        _make_count(db_session, user, "STK-HIST-ACT-1", DocumentStatus.DRAFT)
        view.tabs.setCurrentWidget(view.history_tab)

        view.history_table.selectRow(_row_of(view, "STK-HIST-ACT-1"))

        assert _actions(view) == (True, True, True)

    @pytest.mark.parametrize("status", [DocumentStatus.COMPLETED, DocumentStatus.COUNTED, DocumentStatus.VOID])
    def test_non_draft_row_enables_only_open(self, db_session, user, view, status):
        _make_count(db_session, user, "STK-HIST-ACT-2", status)
        view.tabs.setCurrentWidget(view.history_tab)

        view.history_table.selectRow(_row_of(view, "STK-HIST-ACT-2"))

        assert _actions(view) == (True, False, False)

    def test_empty_history_keeps_actions_disabled(self, view):
        view.tabs.setCurrentWidget(view.history_tab)
        view.history_table.selectRow(0)  # the "no records" placeholder row

        assert _actions(view) == (False, False, False)

    def test_open_button_opens_the_selected_report(self, db_session, user, view, opened):
        count_id = _make_count(db_session, user, "STK-HIST-ACT-3", DocumentStatus.COMPLETED)
        view.tabs.setCurrentWidget(view.history_tab)
        view.history_table.selectRow(_row_of(view, "STK-HIST-ACT-3"))

        view.btn_hist_open.click()

        assert opened == [count_id]

    def test_resume_button_loads_the_draft(self, db_session, user, view):
        count_id = _make_count(db_session, user, "STK-HIST-ACT-4", DocumentStatus.DRAFT)
        view.tabs.setCurrentWidget(view.history_tab)
        view.history_table.selectRow(_row_of(view, "STK-HIST-ACT-4"))

        view.btn_hist_resume.click()

        assert view.current_stock_count.id == count_id
        assert view.tabs.currentWidget() is view.new_count_tab

    def test_discard_button_asks_first_and_voids_on_yes(self, db_session, user, view, monkeypatch):
        count_id = _make_count(db_session, user, "STK-HIST-ACT-5", DocumentStatus.DRAFT)
        asked: list[str] = []

        def _question(*args, **kwargs):
            asked.append(args[1])
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr(QMessageBox, "question", _question)
        view.tabs.setCurrentWidget(view.history_tab)
        view.history_table.selectRow(_row_of(view, "STK-HIST-ACT-5"))

        view.btn_hist_discard.click()

        assert len(asked) == 1
        assert StockCountService.get_stock_count(count_id).status == DocumentStatus.VOID
        # The list reloads and the voided row no longer offers Resume/Discard
        view.history_table.selectRow(_row_of(view, "STK-HIST-ACT-5"))
        assert _actions(view) == (True, False, False)

    def test_discard_button_keeps_the_draft_on_no(self, db_session, user, view, monkeypatch):
        count_id = _make_count(db_session, user, "STK-HIST-ACT-6", DocumentStatus.DRAFT)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
        view.tabs.setCurrentWidget(view.history_tab)
        view.history_table.selectRow(_row_of(view, "STK-HIST-ACT-6"))

        view.btn_hist_discard.click()

        assert StockCountService.get_stock_count(count_id).status == DocumentStatus.DRAFT


class TestEnterOpens:
    @pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
    def test_enter_on_the_table_opens_the_selected_row(self, db_session, user, view, opened, key):
        count_id = _make_count(db_session, user, "STK-HIST-ENTER-1", DocumentStatus.COMPLETED)
        view.tabs.setCurrentWidget(view.history_tab)
        view.show()
        view.activateWindow()
        QTest.qWaitForWindowActive(view)
        view.history_table.selectRow(_row_of(view, "STK-HIST-ENTER-1"))
        view.history_table.setFocus()

        QTest.keyClick(view.history_table, key)

        assert opened == [count_id]

    def test_double_click_still_opens(self, db_session, user, view, opened):
        count_id = _make_count(db_session, user, "STK-HIST-ENTER-2", DocumentStatus.COMPLETED)
        view.tabs.setCurrentWidget(view.history_tab)

        view.on_history_double_click(view.history_table.model().index(_row_of(view, "STK-HIST-ENTER-2"), 0))

        assert opened == [count_id]
