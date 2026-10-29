"""
#306: the sidebar's only nav-item styling was `padding: 10px 12px;` with
2px between buttons, and each label was a single plain string like
"Wholesale  [Active]" -- no icon, no badge, no breathing room. Fine at
3 items, but it already reads as an afterthought next to Reports'
sidebar, and won't scale to 8-10 price lists. Give each item a colored
status dot (matching the header badge's colors), drop the bracketed
text from the label, and open up padding/spacing.
"""

from datetime import datetime
from pathlib import Path

import pytest

from cbpos.ui.views.pricelist_view import PriceListView

pytestmark = pytest.mark.usefixtures("qapp")

STYLE_DIR = Path(__file__).resolve().parents[3] / "cbpos" / "ui" / "styles"

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def _make_price_list(view, name="Wholesale"):
    return view.price_list_service.create_price_list(
        f"{name}_{_next_suffix()}",
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 12, 31),
    )


class TestNavItemLabelIsJustTheName:
    def test_button_text_has_no_bracketed_status(self, db_session):
        view = PriceListView()
        pl = _make_price_list(view)
        view.load_lists()

        btn = view._nav_buttons[pl.id]
        assert "[" not in btn.text()
        assert btn.text() == pl.name


class TestNavItemHasAStatusIndicator:
    def test_button_carries_a_non_null_status_icon(self, db_session):
        view = PriceListView()
        pl = _make_price_list(view)
        view.load_lists()

        btn = view._nav_buttons[pl.id]
        assert not btn.icon().isNull()


class TestSidebarHasMoreBreathingRoom:
    def test_nav_layout_spacing_is_wider_than_the_old_2px(self, db_session):
        view = PriceListView()
        assert view.nav_layout.spacing() >= 6
