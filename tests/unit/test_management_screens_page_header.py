"""
#316: 3 of ManagementView's 10 screens (Users, Stock Take, Purchasing)
showed nothing identifying which screen was open beyond the sidebar's
own highlighted nav button; the other 7 used three different ad-hoc
title conventions (a 22px blue objectName-styled QLabel, a generic
"dialog-title" class QLabel, or a small-caps sidebar-only label with no
top-level title at all). Every one of the 10 now places one shared
PageHeader (icon + screen name) at the top of its own layout, so
"where am I" no longer depends on which secondary navigation pattern
(tabs, a sidebar, or none) that screen happens to use for its content.
"""

import pytest

from cbpos.i18n import _t
from cbpos.ui.views.credit_book_view import CreditBookView
from cbpos.ui.views.dashboard_view import DashboardView
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.views.inventory_view import InventoryView
from cbpos.ui.views.pricelist_view import PriceListView
from cbpos.ui.views.promotion_view import PromotionView
from cbpos.ui.views.purchase_view import PurchaseView
from cbpos.ui.views.reports.report_viewer import ReportViewer
from cbpos.ui.views.stock_take_view import StockTakeView
from cbpos.ui.views.user_view import UserView
from cbpos.ui.widgets.page_header import PageHeader

pytestmark = pytest.mark.usefixtures("qapp")


class TestDashboardHasAPageHeader:
    def test_page_header_exists_with_the_right_title(self, db_session):
        view = DashboardView()
        assert isinstance(view._page_header, PageHeader)
        assert view._page_header._title_label.text() == _t("management.sidebar_dashboard")


class TestInventoryHasAPageHeader:
    def test_page_header_exists_with_the_right_title(self, db_session):
        view = InventoryView()
        assert isinstance(view._page_header, PageHeader)
        assert view._page_header._title_label.text() == _t("management.sidebar_inventory")


class TestPurchaseHasAPageHeader:
    def test_page_header_exists_with_the_right_title(self, db_session):
        view = PurchaseView()
        assert isinstance(view._page_header, PageHeader)
        assert view._page_header._title_label.text() == _t("management.sidebar_purchasing")


class TestUsersHasAPageHeader:
    def test_page_header_exists_with_the_right_title(self, db_session):
        view = UserView()
        assert isinstance(view._page_header, PageHeader)
        assert view._page_header._title_label.text() == _t("management.sidebar_users")


class TestStockTakeHasAPageHeader:
    def test_page_header_exists_with_the_right_title(self, db_session):
        view = StockTakeView()
        assert isinstance(view._page_header, PageHeader)
        assert view._page_header._title_label.text() == _t("management.sidebar_stock_take")


class TestReportsHasAPageHeaderAboveTheSidebar:
    def test_page_header_exists_with_the_right_title(self, db_session):
        view = ReportViewer()
        assert isinstance(view._page_header, PageHeader)
        assert view._page_header._title_label.text() == _t("management.sidebar_reports")
        # The sidebar's own compact label stays as a secondary element.
        assert view.sidebar_title.text() == _t("report_viewer.sidebar_title")


class TestPriceListHasAPageHeaderAboveTheSidebar:
    def test_page_header_exists_with_the_right_title(self, db_session):
        view = PriceListView()
        assert isinstance(view._page_header, PageHeader)
        assert view._page_header._title_label.text() == _t("management.sidebar_price_lists")
        assert view.sidebar_title.text() == _t("pricelist.sidebar_title")


class TestDocumentBrowserUsesTheSharedPageHeader:
    def test_page_header_replaces_the_old_ad_hoc_title_label(self, db_session):
        view = DocumentBrowserView()
        assert isinstance(view._page_header, PageHeader)
        assert view._page_header._title_label.text() == _t("document_browser.title")
        assert not hasattr(view, "title_label")


class TestCreditBookUsesTheSharedPageHeader:
    def test_page_header_replaces_the_old_ad_hoc_title_label(self, db_session):
        view = CreditBookView()
        assert isinstance(view._page_header, PageHeader)
        assert view._page_header._title_label.text() == _t("credit_book.title")
        assert not hasattr(view, "title_label")


class TestPromotionsUsesTheSharedPageHeader:
    def test_page_header_replaces_the_old_ad_hoc_title_label(self, db_session):
        view = PromotionView()
        assert isinstance(view._page_header, PageHeader)
        assert view._page_header._title_label.text() == _t("promotion.title")
        assert not hasattr(view, "lbl_title")
