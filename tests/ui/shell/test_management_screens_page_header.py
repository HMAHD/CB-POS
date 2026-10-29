"""Management views no longer contain redundant PageHeader strips; screen titles
and breadcrumbs are managed persistently by ManagementHeader in ManagementView.
"""

import pytest

from cbpos.i18n import _t
from cbpos.ui.views.credit_book_view import CreditBookView
from cbpos.ui.views.dashboard_view import DashboardView
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.views.inventory_view import InventoryView
from cbpos.ui.views.management_view import ManagementView
from cbpos.ui.views.pricelist_view import PriceListView
from cbpos.ui.views.promotion_view import PromotionView
from cbpos.ui.views.purchase_view import PurchaseView
from cbpos.ui.views.reports.report_viewer import ReportViewer
from cbpos.ui.views.stock_take_view import StockTakeView
from cbpos.ui.views.user_view import UserView

pytestmark = pytest.mark.usefixtures("qapp")


class TestManagementScreensNoPageHeader:
    def test_management_screens_do_not_have_page_header(self, db_session):
        views = [
            DashboardView(),
            InventoryView(),
            PurchaseView(),
            UserView(),
            StockTakeView(),
            ReportViewer(),
            PriceListView(),
            DocumentBrowserView(),
            CreditBookView(),
            PromotionView(),
        ]
        for view in views:
            assert not hasattr(view, "_page_header"), f"{type(view).__name__} should not have _page_header"

    def test_management_header_displays_section_and_screen_titles(self, db_session):
        mgmt = ManagementView()
        # Initial view is dashboard (index 0)
        assert _t("management.sidebar_section_management") in mgmt.lbl_header_title.text()
        assert _t("management.sidebar_dashboard") in mgmt.lbl_header_title.text()

        # Switch to Inventory (index 1)
        mgmt.switch_tab(1)
        assert _t("management.sidebar_inventory") in mgmt.lbl_header_title.text()
