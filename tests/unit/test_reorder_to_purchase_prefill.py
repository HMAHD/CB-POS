"""
#506: ReorderView was fully built (a real, working low-stock list) but had
no sidebar entry, and its "Create Purchase Order" button emitted a signal
nothing received -- clicking it showed a false "Purchase order created"
message while doing nothing. Wires ReorderView into ManagementView's
sidebar and makes the button actually pre-fill a new GRN in PurchaseView.
"""

from decimal import Decimal

import pytest

from cbpos.core.models import Product
from cbpos.ui.views.management_view import ManagementView
from cbpos.ui.views.purchase_view import PurchaseView
from cbpos.ui.views.reorder_view import ReorderView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def low_stock_product(db_session):
    product = Product(
        name_en="Test Reorder Product",
        barcode="RORD0001",
        price=Decimal("100.00"),
        cost=Decimal("60.00"),
        stock_qty=Decimal("2.000"),
        reorder_point=Decimal("5.000"),
        preferred_qty=Decimal("20.000"),
    )
    db_session.add(product)
    db_session.commit()
    return product


class TestReorderSidebarEntry:
    def test_nav_index_10_creates_a_reorder_view(self, db_session):
        view = ManagementView()
        widget = view._get_or_create_view(10)

        assert isinstance(widget, ReorderView)


class TestReorderNavigatesToPurchaseWithPrefill:
    def test_selected_items_pre_fill_a_new_grn_and_switch_tabs(self, db_session, low_stock_product):
        management_view = ManagementView()

        items = [
            {
                "product_id": low_stock_product.id,
                "product_name": low_stock_product.name_en,
                "barcode": low_stock_product.barcode,
                "current_stock": low_stock_product.stock_qty,
                "order_qty": Decimal("18.000"),
                "supplier": "",
            }
        ]

        management_view._handle_reorder_navigation(items)
        purchase_view = management_view.purchase_view

        assert isinstance(purchase_view, PurchaseView)
        assert management_view.stack.currentWidget() is purchase_view
        assert purchase_view.tabs.currentWidget() is purchase_view.grn_tab
        assert len(purchase_view.grn_items) == 1
        assert purchase_view.grn_items[0]["product"].id == low_stock_product.id
        assert purchase_view.grn_items[0]["qty"] == Decimal("18.000")

    def test_unresolvable_barcode_is_skipped_not_fatal(self, db_session, low_stock_product):
        management_view = ManagementView()

        items = [
            {
                "product_id": 999999,
                "product_name": "Deleted Product",
                "barcode": "DOES-NOT-EXIST",
                "current_stock": Decimal("0"),
                "order_qty": Decimal("5.000"),
                "supplier": "",
            }
        ]

        management_view._handle_reorder_navigation(items)
        purchase_view = management_view.purchase_view

        assert purchase_view.grn_items == []
