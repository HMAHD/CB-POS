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
from PyQt6.QtWidgets import QFrame, QSizePolicy

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


class TestPaymentRowSeparatorIsARealChildWidget:
    """QListWidget::item's own QSS (padding + border-bottom) used to draw
    the row separator. That box model is applied by the view AFTER
    setSizeHint() already reserved a rect -- invisible to the Python
    layout code -- so no fixed pixel buffer added to the sizeHint could
    reliably match it across different fonts/platforms/DPI (confirmed:
    a manually tuned +5px buffer still clipped the fixed 44px remove
    button's bottom border in production). The separator is now a real
    QFrame child of the row widget, so sizeHint() is the complete,
    self-contained truth with nothing external able to eat into it.
    """

    def test_row_size_hint_leaves_room_for_the_44px_button_plus_its_margins(self, dialog):
        dialog.txt_amount.setText("100")
        dialog.add_payment()

        row_height = dialog.list_payments.item(0).sizeHint().height()

        # 44px button + 8px top/bottom layout margins + 1px separator.
        assert row_height >= 44 + 16 + 1

    def test_row_widget_owns_a_real_separator_frame(self, dialog):
        dialog.txt_amount.setText("100")
        dialog.add_payment()

        item_widget = dialog.list_payments.itemWidget(dialog.list_payments.item(0))
        separator = item_widget.findChild(QFrame, "PaymentListItemSeparator")

        assert separator is not None
