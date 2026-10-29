"""
#257: the empty cart was just gray text centered in a large black
rectangle -- functionally fine, but the least-designed part of the
whole POS screen. Pair the existing text with the shared
EmptyStateWidget's large muted icon (Icons.SALES, already registered
and in use elsewhere) instead of type alone on black.
"""

import pytest

from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView
from cbpos.ui.widgets.empty_state_widget import EmptyStateWidget

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


class TestEmptyCartHasAVisualAnchor:
    def test_empty_cart_overlay_is_an_empty_state_widget(self, view):
        assert isinstance(view.empty_cart_label, EmptyStateWidget)

    def test_empty_cart_overlay_has_a_real_icon(self, view):
        assert not view.empty_cart_label._icon_label.pixmap().isNull()

    def test_empty_cart_overlay_still_has_its_title_text(self, view):
        view.retranslate_ui()
        assert view.empty_cart_label._title_label.text() != ""
