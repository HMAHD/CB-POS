"""
The customer card had two real defects: a long name/phone string had
no eliding at all (silently clipped by the layout with no way to read
the rest), and the only way to reset to Walk-in Customer was a
right-click context menu on the name -- easy to miss, and there was no
dedicated control for it in the main UI. Separately, retranslate_ui()
unconditionally overwrote the name field with "Walk-in Customer" text
on every language change, even while a real customer was selected.
"""

import pytest

from cbpos.ui.widgets.action_panel import ActionPanel
from cbpos.ui.widgets.elided_label import ElidedLabel

pytestmark = pytest.mark.usefixtures("qapp")


class TestCustomerNameFieldElides:
    def test_lbl_customer_is_an_elided_label(self):
        panel = ActionPanel()
        assert isinstance(panel.lbl_customer, ElidedLabel)

    def test_full_name_and_phone_are_recoverable_even_when_narrow(self):
        panel = ActionPanel()
        panel.show()
        panel.resize(280, 400)

        panel.set_customer_info("Wanninayake Mudiyanselage Dissanayake", "0771234567", 320)

        assert panel.lbl_customer.text() == "Wanninayake Mudiyanselage Dissanayake (0771234567)"
        assert panel.lbl_customer.toolTip() == "Wanninayake Mudiyanselage Dissanayake (0771234567)"


class TestManualClearCustomerButton:
    def test_clear_button_is_hidden_for_walk_in(self):
        panel = ActionPanel()
        assert panel.btn_cust_clear.isVisibleTo(panel) is False

    def test_clear_button_appears_once_a_customer_is_selected(self):
        panel = ActionPanel()
        panel.set_customer_info("Jane Doe", "0771234567", 150)
        assert panel.btn_cust_clear.isVisibleTo(panel) is True

    def test_clear_button_hides_again_after_clear_customer_info(self):
        panel = ActionPanel()
        panel.set_customer_info("Jane Doe", "0771234567", 150)
        panel.clear_customer_info()
        assert panel.btn_cust_clear.isVisibleTo(panel) is False

    def test_clicking_clear_emits_customer_cleared(self):
        panel = ActionPanel()
        panel.set_customer_info("Jane Doe", "0771234567", 150)

        received = []
        panel.customer_cleared.connect(lambda: received.append(True))
        panel.btn_cust_clear.click()

        assert received == [True]


class TestRetranslateDoesNotClobberARealCustomer:
    def test_retranslate_keeps_the_selected_customer_name(self):
        panel = ActionPanel()
        panel.set_customer_info("Jane Doe", "0771234567", 150)

        panel.retranslate_ui()

        assert panel.lbl_customer.text() == "Jane Doe (0771234567)"

    def test_retranslate_still_shows_walk_in_when_no_customer_selected(self):
        panel = ActionPanel()

        panel.retranslate_ui()

        assert "Walk-in" in panel.lbl_customer.text()


class TestPointsBadgeHasAnIcon:
    def test_points_icon_label_has_a_real_pixmap(self):
        panel = ActionPanel()
        assert not panel.lbl_points_icon.pixmap().isNull()

    def test_points_text_no_longer_repeats_the_word_points(self):
        panel = ActionPanel()
        panel.set_customer_info("Jane Doe", "0771234567", 150)
        assert "150" in panel.lbl_points.text()
