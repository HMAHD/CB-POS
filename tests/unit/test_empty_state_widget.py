"""
#254: Reports, the POS cart, and other screens each hand-built their
own empty-state visual with no shared component. EmptyStateWidget is
the one reusable icon+title+optional-subtitle widget every screen can
now use instead.
"""

import pytest

from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.empty_state_widget import EmptyStateWidget

pytestmark = pytest.mark.usefixtures("qapp")


class TestEmptyStateWidgetBasics:
    def test_icon_is_rendered(self):
        widget = EmptyStateWidget(Icons.SALES)
        assert not widget._icon_label.pixmap().isNull()

    def test_title_can_be_set(self):
        widget = EmptyStateWidget(Icons.SALES)
        widget.set_title("Cart is Empty")
        assert widget._title_label.text() == "Cart is Empty"

    def test_subtitle_is_hidden_by_default(self):
        widget = EmptyStateWidget(Icons.SALES)
        assert widget._subtitle_label.isVisibleTo(widget) is False

    def test_setting_a_subtitle_shows_it(self):
        widget = EmptyStateWidget(Icons.SALES)
        widget.set_subtitle("Scan a barcode or search to add items")
        assert widget._subtitle_label.isVisibleTo(widget) is True
        assert widget._subtitle_label.text() == "Scan a barcode or search to add items"

    def test_clearing_the_subtitle_hides_it_again(self):
        widget = EmptyStateWidget(Icons.SALES)
        widget.set_subtitle("something")
        widget.set_subtitle("")
        assert widget._subtitle_label.isVisibleTo(widget) is False
