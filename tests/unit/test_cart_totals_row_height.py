"""
The cart's totals row (Items/Subtotal/Disc/Tax/Exempt, stacked above the
48px grand total) could grow to 5 full lines when every optional piece
was visible at once (VAT active, a tax breakdown shown, and an exempt
amount present) -- on a compact POS-hardware screen this sat
uncomfortably close to (and, at some resolutions, could clip against)
the window's bottom edge, since the container only reserved a bare
10px of bottom margin. Sharing the tax and exempt lines in one row
caps the worst case at 4 lines instead of 5.
"""

import pytest
from PyQt6.QtWidgets import QHBoxLayout

from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session):
    v = SalesView()
    yield v
    v.deleteLater()


def _find_total_widget(view):
    node = view.lbl_discount.parent()
    while node is not None and node.objectName() != "TotalWidget":
        node = node.parent()
    return node


class TestTaxAndExemptShareOneRowInsteadOfTwo:
    def test_tax_and_exempt_labels_are_siblings_in_the_same_sub_layout(self, view):
        total_widget = _find_total_widget(view)
        subtotal_layout = total_widget.layout().itemAt(0).layout()

        tax_row = None
        for i in range(subtotal_layout.count()):
            item = subtotal_layout.itemAt(i)
            child_layout = item.layout()
            if isinstance(child_layout, QHBoxLayout):
                widgets = [child_layout.itemAt(j).widget() for j in range(child_layout.count())]
                if view.lbl_tax in widgets and view.lbl_exempt in widgets:
                    tax_row = child_layout
        assert tax_row is not None, "lbl_tax and lbl_exempt must share one row"

    def test_worst_case_all_five_pieces_of_info_still_fits_comfortably(self, view, qapp):
        view.resize(1280, 720)
        view.show()

        # Force the worst case: item count, subtotal, discount, tax
        # breakdown, and an exempt amount all visible at once.
        view.lbl_item_count.setText("Items: 3")
        view.lbl_subtotal.setText("Subtotal: Rs. 1,450.00")
        view.lbl_discount.setText("Disc: Rs. 50.00")
        view.lbl_tax.setVisible(True)
        view.lbl_tax.setText("VAT: Rs. 180.00  SSCL: Rs. 25.00")
        view.lbl_exempt.setVisible(True)
        view.lbl_exempt.setText("Tax-Exempt: Rs. 100.00")
        qapp.processEvents()

        total_widget = _find_total_widget(view)
        bottom_in_view = total_widget.mapTo(view, total_widget.rect().bottomLeft())
        margin_below = view.height() - bottom_in_view.y()

        assert margin_below >= 14


class TestTotalsRowHasBreathingRoomAtTheBottom:
    def test_cart_container_reserves_more_than_the_bare_minimum_bottom_margin(self, view):
        _, _, _, bottom = view.container_left.layout().getContentsMargins()
        assert bottom >= 16
