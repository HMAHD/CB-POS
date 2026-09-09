"""
Stock Take's item_table, history_table, and StockCountReportDialog's table
share the same family of bug (UX-077/#261). item_table/history_table already
had a resize mode set per column, but no minimum width -- so a ResizeToContents
column computed while empty at load time (COUNTED, on the very screen a
warehouse worker types into) could collapse to almost nothing, and its own
transient text editor then had to render inside that too-narrow column.
StockCountReportDialog's table had the more familiar shape: only 1 of 6
columns got a resize mode at all.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QHeaderView, QTableWidget

from cbpos.core.models import StockCount, User
from cbpos.ui.views.stock_take_view import StockCountReportDialog, StockTakeView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_username() -> str:
    global _counter
    _counter += 1
    return f"stocktake_test_user_{_counter}"


@pytest.fixture
def test_user(db_session):
    user = User(username=_next_username(), pin_hash="hash")
    db_session.add(user)
    db_session.flush()
    return user


class TestNewCountItemTableColumns:
    def test_counted_column_has_a_minimum_width_floor(self, db_session):
        view = StockTakeView()
        header = view.item_table.horizontalHeader()

        assert header.minimumSectionSize() == 70
        assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch  # Product
        for col in (0, 2, 3, 4, 5):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents


class TestHistoryTableColumns:
    def test_stk_and_date_columns_have_a_minimum_width_floor(self, db_session):
        view = StockTakeView()
        header = view.history_table.horizontalHeader()

        assert header.minimumSectionSize() == 70
        assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch  # User
        for col in (0, 1, 3, 4, 5):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents


class TestStockCountReportDialogColumns:
    def test_product_column_stretches_others_size_to_contents(self, db_session, test_user):
        # Built directly via the ORM (not StockCountService.create_stock_count())
        # so this test's only interaction with the row is the dialog's own
        # get_stock_count() call. The test harness shares one Session across
        # a whole test (unlike production, where every db.get_session() call
        # gets a genuinely fresh Session/identity map -- see Database.__init__'s
        # sessionmaker()) -- session.get()'s joinedload options aren't reliably
        # re-applied to an instance already present in the identity map, so
        # creating-then-immediately-re-fetching the same object in one test
        # doesn't reflect how this code behaves in real, separate sessions.
        stock_count = StockCount(
            document_number="STK-TEST-001",
            type="stock_count",
            date=datetime.now(),
            user_id=test_user.id,
            status="DRAFT",
            note="test",
            total_variance_value=Decimal("0.00"),
        )
        db_session.add(stock_count)
        db_session.commit()
        stock_count_id = stock_count.id
        db_session.expunge(stock_count)

        dialog = StockCountReportDialog(stock_count_id)
        table = dialog.findChild(QTableWidget)
        header = table.horizontalHeader()

        assert header.minimumSectionSize() == 70
        assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch  # Product
        for col in (0, 2, 3, 4, 5):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents
