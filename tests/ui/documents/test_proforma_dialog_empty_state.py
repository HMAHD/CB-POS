"""
#259: before any product is added, the Proforma dialog's line-items
table rendered as a blank dark rectangle under the headers -- no
placeholder row or message, unlike the established convention used in
customer_view.py/pricelist_view.py/inventory_view.py/report_viewer.py
(a single spanning, centered, gray placeholder row).
"""

import pytest

from cbpos.i18n import _t
from cbpos.ui.dialogs.proforma_dialog import ProformaDialog

pytestmark = pytest.mark.usefixtures("qapp")


class TestProformaItemsTableEmptyState:
    def test_shows_a_spanning_placeholder_row_when_no_items(self, db_session):
        dialog = ProformaDialog()

        assert dialog.items_table.rowCount() == 1
        item = dialog.items_table.item(0, 0)
        assert item.text() == _t("proforma.items_empty_state")
        assert dialog.items_table.columnSpan(0, 0) == dialog.items_table.columnCount()

    def test_placeholder_disappears_once_an_item_is_added(self, db_session):
        dialog = ProformaDialog()
        dialog.items.append(
            {
                "product_id": 1,
                "product_name": "Test Product",
                "quantity": 1,
                "unit_price": 100,
                "discount_type": "NONE",
                "discount_value": 0,
                "line_total": 100,
            }
        )
        dialog.refresh_table()

        assert dialog.items_table.rowCount() == 1
        assert dialog.items_table.item(0, 0).text() == "Test Product"
