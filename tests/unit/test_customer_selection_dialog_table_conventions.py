"""
Select Customer's table skipped conventions every comparable table in the
app follows: no alternating row colors, the default vertical-header row
gutter left visible and unstyled, no objectName, and NAME/PHONE data
left-aligned under center-aligned (Qt's default) headers -- the same
header/data mismatch already found in the cart table. It also re-parsed
the customer ID from the displayed cell text rather than storing it as
item data, which only worked because the ID column happened to show
nothing but the raw integer.
"""

import pytest
from PyQt6.QtCore import Qt

from cbpos.core.models import Customer
from cbpos.ui.dialogs.customer_selection_dialog import CustomerSelectionDialog

pytestmark = pytest.mark.usefixtures("qapp")

_LEFT = Qt.AlignmentFlag.AlignLeft


def _make_customer(db_session, name, suffix):
    customer = Customer(name=name, phone=f"07{suffix}")
    db_session.add(customer)
    db_session.flush()
    return customer


class TestCustomerSelectTableConventions:
    def test_has_alternating_row_colors(self, db_session):
        dialog = CustomerSelectionDialog()
        assert dialog.table.alternatingRowColors() is True

    def test_vertical_header_is_hidden(self, db_session):
        dialog = CustomerSelectionDialog()
        dialog.show()  # isVisible() reflects real on-screen state, not just
        # the explicit setVisible(False) call, so the dialog must actually
        # be shown for this to distinguish "hidden" from "never shown".
        assert dialog.table.verticalHeader().isVisible() is False

    def test_has_an_object_name(self, db_session):
        dialog = CustomerSelectionDialog()
        assert dialog.table.objectName() == "CustomerSelectTable"

    def test_name_and_phone_headers_are_left_aligned(self, db_session):
        dialog = CustomerSelectionDialog()
        for col in (1, 2):
            header_item = dialog.table.horizontalHeaderItem(col)
            assert header_item.textAlignment() & _LEFT == _LEFT

    def test_id_column_is_hidden(self, db_session):
        dialog = CustomerSelectionDialog()
        assert dialog.table.isColumnHidden(0) is True


class TestCustomerSelectionUsesItemDataNotDisplayText:
    def test_selection_resolves_by_user_role_data_not_displayed_id_text(self, db_session):
        customer = _make_customer(db_session, "Data-Driven Customer", "444")
        dialog = CustomerSelectionDialog()

        row = None
        for r in range(dialog.table.rowCount()):
            if dialog.table.item(r, 1).text() == "Data-Driven Customer":
                row = r
                break
        assert row is not None

        # Even if the ID column's displayed text were something other than
        # a bare integer (a "#" prefix, padding, ...), selection must still
        # resolve correctly since it no longer parses this text at all.
        dialog.table.item(row, 0).setText(f"#{customer.id}-padded")

        dialog.table.setCurrentCell(row, 1)
        dialog.select_customer()

        assert dialog.selected_customer is not None
        assert dialog.selected_customer.id == customer.id
