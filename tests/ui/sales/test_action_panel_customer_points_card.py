"""
The customer name/phone row sat inside a bordered card (QFrame#CustomerPanel),
but "Points: 150" rendered as a separate QLabel added as a sibling *after*
that frame, not as a child inside it -- no shared background/border, its
own independent center alignment, and never hidden (just cleared to an
empty string) for Walk-in Customer, so it still reserved a blank line of
vertical space by default.
"""

import pytest

from cbpos.ui.widgets.action_panel import ActionPanel

pytestmark = pytest.mark.usefixtures("qapp")


class TestPointsLabelLivesInsideTheCustomerCard:
    def test_points_label_is_a_descendant_of_the_customer_panel_frame(self):
        panel = ActionPanel()

        node = panel.lbl_points
        while node is not None:
            if node.objectName() == "CustomerPanel":
                break
            node = node.parent()

        assert node is not None, "lbl_points must be nested inside QFrame#CustomerPanel"

    def test_points_divider_is_also_inside_the_customer_panel_frame(self):
        panel = ActionPanel()

        node = panel.points_divider
        while node is not None:
            if node.objectName() == "CustomerPanel":
                break
            node = node.parent()

        assert node is not None


class TestPointsRowVisibility:
    def test_points_row_and_divider_are_hidden_by_default(self):
        panel = ActionPanel()
        panel.show()

        assert panel.points_row.isVisible() is False
        assert panel.points_divider.isVisible() is False

    def test_setting_customer_info_shows_the_points_row_and_divider(self):
        panel = ActionPanel()
        panel.show()

        panel.set_customer_info("Jane Doe", "0771234567", 150)

        assert panel.points_row.isVisible() is True
        assert panel.points_divider.isVisible() is True
        assert "150" in panel.lbl_points.text()

    def test_clearing_customer_info_hides_the_points_row_and_divider_again(self):
        panel = ActionPanel()
        panel.show()
        panel.set_customer_info("Jane Doe", "0771234567", 150)

        panel.clear_customer_info()

        assert panel.points_row.isVisible() is False
        assert panel.points_divider.isVisible() is False
        assert panel.lbl_points.text() == ""
