"""
#281: GRN History's Status filter combo's default row and the Supplier
filter combo's default row both called the exact same _t("purchase.all_suppliers")
key -- a copy-paste bug, since there's no purchase.all_statuses key at
all. The Status combo showed "All Suppliers" instead of "All Statuses".
"""

import pytest

from cbpos.i18n import _t
from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")


class TestGrnHistoryStatusFilterLabel:
    def test_status_combo_first_item_says_all_statuses_not_all_suppliers(self, db_session):
        view = PurchaseView()
        assert view.history_status_combo.itemText(0) == _t("purchase.all_statuses")
        assert view.history_status_combo.itemText(0) != _t("purchase.all_suppliers")

    def test_supplier_combo_first_item_still_says_all_suppliers(self, db_session):
        view = PurchaseView()
        assert view.history_supplier_combo.itemText(0) == _t("purchase.all_suppliers")
