"""
The Applied Payments list had a hard setMaximumHeight(160) ceiling, not a
starting size, despite the comment above it saying "compact, grows only
as needed". At ~55-60px per row, 160px only ever fit ~2.5 rows, so a 3rd+
split payment forced internal scrolling -- and the row sitting right at
that cutoff was visually clipped mid-render, its remove button's border
cut off exactly where the list's viewport ended. A trailing addStretch()
right after the list also meant any leftover vertical space in that
column went to empty space below the list instead of the list itself.
"""

from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QSizePolicy

from cbpos.core.models import PaymentMethod
from cbpos.ui.dialogs.payment_dialog import PaymentDialog


@pytest.fixture
def cash_method(db_session):
    cash = db_session.query(PaymentMethod).filter_by(name="Cash").first()
    if cash is None:
        cash = PaymentMethod(name="Cash", is_cash=True, is_active=True, shortcut="F12")
        db_session.add(cash)
        db_session.commit()
    return cash


@pytest.fixture
def dialog(qapp, cash_method):
    dlg = PaymentDialog(Decimal("600.00"))
    yield dlg
    dlg.deleteLater()


class TestAppliedPaymentsListSize:
    def test_max_height_fits_at_least_four_typical_rows(self, dialog):
        # ~55-60px per row (per the reported measurement) -- 4 rows need
        # roughly 220-240px; the old 160px cap only fit ~2.5.
        assert dialog.list_payments.maximumHeight() >= 220

    def test_list_has_a_layout_stretch_factor_instead_of_a_trailing_stretch(self, dialog):
        left_layout = dialog.list_payments.parentWidget().layout()
        list_index = left_layout.indexOf(dialog.list_payments)
        assert left_layout.stretch(list_index) > 0

    def test_list_is_the_last_item_in_its_column_layout(self, dialog):
        # The old trailing addStretch() meant the list wasn't the last
        # real item -- confirming there's no separate stretch item after
        # it is what proves the list itself now claims the leftover space.
        left_layout = dialog.list_payments.parentWidget().layout()
        list_index = left_layout.indexOf(dialog.list_payments)
        assert list_index == left_layout.count() - 1

    def test_size_policy_lets_the_list_grow_vertically(self, dialog):
        assert dialog.list_payments.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
