"""
#285: the filter row (From/To/Refresh) only inherited the dialog's
blanket layout.setSpacing(10) -- nothing about it was tuned for its own
content -- and the summary line packed 4 differently-styled labels
left-to-right with a stretch but no column/grid alignment, so nothing
lined up into a predictable visual rhythm.
"""

import pytest
from PyQt6.QtWidgets import QGridLayout

from cbpos.core.models import Customer
from cbpos.ui.dialogs.customer_statement_dialog import CustomerStatementDialog

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def _make_customer(db_session):
    customer = Customer(name="Test Customer", phone=f"077{_next_suffix()}")
    db_session.add(customer)
    db_session.flush()
    return customer


class TestFilterRowHasTunedSpacing:
    def test_filter_row_sets_its_own_contents_margins(self, db_session):
        dialog = CustomerStatementDialog(_make_customer(db_session))
        margins = dialog.filter_layout.contentsMargins()
        # An untouched QHBoxLayout nested in another layout defaults to
        # all-zero margins -- asserting a non-zero top/bottom margin is
        # what actually proves this row was given its own breathing room.
        assert margins.top() > 0 or margins.bottom() > 0


class TestSummaryLineUsesAGridForAlignment:
    def test_summary_layout_is_a_grid(self, db_session):
        dialog = CustomerStatementDialog(_make_customer(db_session))
        assert isinstance(dialog.summary_layout, QGridLayout)

    def test_opening_and_sales_share_the_top_row(self, db_session):
        dialog = CustomerStatementDialog(_make_customer(db_session))
        layout = dialog.summary_layout
        assert layout.indexOf(dialog.lbl_opening) == layout.indexOf(dialog.lbl_opening)  # sanity
        opening_pos = layout.getItemPosition(layout.indexOf(dialog.lbl_opening))
        sales_pos = layout.getItemPosition(layout.indexOf(dialog.lbl_total_debit))
        assert opening_pos[0] == sales_pos[0]  # same row
        assert opening_pos[1] != sales_pos[1]  # different column

    def test_payments_and_closing_share_the_bottom_row(self, db_session):
        dialog = CustomerStatementDialog(_make_customer(db_session))
        layout = dialog.summary_layout
        payments_pos = layout.getItemPosition(layout.indexOf(dialog.lbl_total_credit))
        closing_pos = layout.getItemPosition(layout.indexOf(dialog.lbl_closing))
        assert payments_pos[0] == closing_pos[0]
        assert payments_pos[0] != layout.getItemPosition(layout.indexOf(dialog.lbl_opening))[0]
        assert payments_pos[1] != closing_pos[1]
