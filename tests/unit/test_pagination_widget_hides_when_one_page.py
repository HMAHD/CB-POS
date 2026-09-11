"""
#291: PaginationWidget only hid itself entirely when total == 0 --
with any data at all, even a single page, it rendered the full
Previous / "Page 1 of 1" / Next row regardless of whether paging was
actually possible. A disabled-looking-but-not-disabled Previous/Next
pair for a 4-row report is UI noise; hide the whole control whenever
there's nothing to actually page through.
"""

import pytest

from cbpos.ui.widgets.pagination_widget import PaginationWidget

pytestmark = pytest.mark.usefixtures("qapp")


class TestPaginationHidesWithOnlyOnePage:
    # These widgets have no parent, so they're effectively their own
    # top-level window -- isVisible() reflects the explicit setVisible()
    # call directly, with none of the "unshown ancestor" gotcha that
    # applies to widgets embedded in a larger, unshown view.

    def test_hidden_when_zero_items(self):
        widget = PaginationWidget(page_size=50)
        widget.set_total(0)
        assert widget.isVisible() is False

    def test_hidden_when_items_fit_on_a_single_page(self):
        widget = PaginationWidget(page_size=50)
        widget.set_total(4)
        assert widget.total_pages == 1
        assert widget.isVisible() is False

    def test_visible_when_more_than_one_page_exists(self):
        widget = PaginationWidget(page_size=50)
        widget.set_total(120)
        assert widget.total_pages == 3
        assert widget.isVisible() is True
