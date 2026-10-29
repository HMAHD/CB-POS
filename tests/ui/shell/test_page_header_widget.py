"""
#316: a third of Management's screens (Users, Stock Take, Purchasing)
showed nothing identifying the screen beyond the sidebar's own
highlighted nav button; the rest used three different ad-hoc title
conventions. PageHeader is the one shared, compact icon+title widget
every Management screen now places at the top of its own layout.
"""

import pytest

from cbpos.ui.widgets.page_header import PageHeader

pytestmark = pytest.mark.usefixtures("qapp")


class TestPageHeader:
    def test_sets_title_text_at_construction(self, qapp):
        header = PageHeader(icon_name="fa5s.tachometer-alt", title="Dashboard")
        assert header._title_label.text() == "Dashboard"

    def test_set_title_updates_the_label(self, qapp):
        header = PageHeader()
        header.set_title("Inventory")
        assert header._title_label.text() == "Inventory"

    def test_set_icon_renders_a_pixmap(self, qapp):
        header = PageHeader()
        header.set_icon("fa5s.boxes")
        assert not header._icon_label.pixmap().isNull()

    def test_no_icon_leaves_the_icon_label_empty(self, qapp):
        header = PageHeader(title="Reports")
        assert header._icon_label.pixmap() is None or header._icon_label.pixmap().isNull()
