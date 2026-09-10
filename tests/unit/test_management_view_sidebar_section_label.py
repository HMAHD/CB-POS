"""
#315: ManagementView's 10 nav items now get a section break between the
day-to-day operational screens (Dashboard, Inventory, Purchasing, Credit
Book) and the management/admin ones (Reports onward).
"""

import pytest

from cbpos.i18n import _t
from cbpos.ui.views.management_view import ManagementView

pytestmark = pytest.mark.usefixtures("qapp")


class TestManagementViewSidebarSectionLabel:
    def test_section_label_shows_the_translated_management_text(self, db_session):
        view = ManagementView()
        assert view.lbl_sidebar_section_management.text() == _t("management.sidebar_section_management").upper()

    def test_section_label_sits_between_credit_book_and_reports(self, db_session):
        view = ManagementView()
        layout = view.sidebar._layout

        index_of = {}
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget()
            if widget is None:
                continue
            if widget is view.btn_customers:
                index_of["credit_book"] = i
            elif widget is view.btn_reports:
                index_of["reports"] = i
            elif view.lbl_sidebar_section_management in widget.findChildren(type(view.lbl_sidebar_section_management)):
                index_of["section_label"] = i

        assert index_of["credit_book"] < index_of["section_label"] < index_of["reports"]
