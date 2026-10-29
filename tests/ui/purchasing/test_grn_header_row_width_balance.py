"""
#279: New GRN's header row (Supplier combo, Ref# line edit, Date field)
had no stretch factors and no width constraints at all. QComboBox/
QLineEdit both grow to fill available space by Qt default, but QDateEdit
has no size-policy override, so it rendered at its bare natural
sizeHint -- just wide enough for the date text plus its spin arrows --
next to two widgets stretching to fill the row, making the Date field
look like a tiny afterthought.
"""

import pytest

from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")


class TestGrnHeaderRowStretchFactors:
    def test_supplier_and_ref_get_more_stretch_than_date(self, db_session):
        view = PurchaseView()
        layout = view.grn_form_layout

        supplier_stretch = layout.stretch(layout.indexOf(view.supplier_combo))
        ref_stretch = layout.stretch(layout.indexOf(view.invoice_input))
        date_stretch = layout.stretch(layout.indexOf(view.date_input))

        assert supplier_stretch > date_stretch
        assert ref_stretch > date_stretch

    def test_date_field_still_gets_some_stretch_not_zero(self, db_session):
        view = PurchaseView()
        layout = view.grn_form_layout
        date_stretch = layout.stretch(layout.indexOf(view.date_input))
        assert date_stretch >= 1
