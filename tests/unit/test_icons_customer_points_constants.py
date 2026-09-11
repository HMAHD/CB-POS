"""
#266: action_panel.py's customer card passed a raw qtawesome string
literal ("fa5s.user-circle") instead of a registered Icons constant --
the only place in the codebase still doing that for an icon in active
use. Register Icons.CUSTOMER (and Icons.POINTS, needed for a future
points badge) and route action_panel.py through it.
"""

from cbpos.ui.resources.icons import Icons


class TestCustomerAndPointsIconsAreRegistered:
    def test_customer_icon_constant_exists(self):
        assert Icons.CUSTOMER == "fa5s.user-circle"

    def test_points_icon_constant_exists(self):
        assert Icons.POINTS == "fa5s.star"
