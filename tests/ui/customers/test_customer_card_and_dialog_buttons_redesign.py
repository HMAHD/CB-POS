"""Tests for CustomerSelectionDialog button symmetry and ActionPanel customer profile card redesign."""

import pytest

from cbpos.ui.dialogs.customer_selection_dialog import CustomerSelectionDialog
from cbpos.ui.widgets.action_panel import ActionPanel

pytestmark = pytest.mark.usefixtures("qapp")


class TestCustomerSelectionDialogButtonsSymmetry:
    def test_select_and_cancel_buttons_have_identical_dimensions(self, db_session):
        dialog = CustomerSelectionDialog()
        dialog.show()

        # Both buttons must have identical min height (>= 36px) and min width (>= 100px)
        assert dialog.btn_select.minimumHeight() == dialog.btn_cancel.minimumHeight()
        assert dialog.btn_select.minimumHeight() >= 36
        assert dialog.btn_select.minimumWidth() == dialog.btn_cancel.minimumWidth()
        assert dialog.btn_select.minimumWidth() >= 100

    def test_dialog_select_button_does_not_use_action_panel_object_name(self, db_session):
        dialog = CustomerSelectionDialog()
        # Must not be 'BtnCustomerSelect' which carried compact 5px 10px action-panel padding
        assert dialog.btn_select.objectName() != "BtnCustomerSelect"


class TestActionPanelCustomerProfileCard:
    def test_walk_in_state_initials_and_buttons(self):
        panel = ActionPanel()
        panel.show()

        # In walk-in state:
        assert panel._has_customer is False
        assert "Walk-in" in panel.lbl_customer.text()
        assert panel.btn_cust_clear.isVisibleTo(panel) is False
        assert panel.points_row.isVisibleTo(panel) is False
        assert panel.lbl_phone.isVisibleTo(panel) is False
        # Button offers "+ Select" action
        assert "Select" in panel.btn_cust_select.text()

    def test_customer_selected_state_initials_and_meta(self):
        panel = ActionPanel()
        panel.show()

        panel.set_customer_info("Dilini Rathnayake", "0721234567", 200)

        assert panel._has_customer is True
        assert panel.lbl_customer.text() == "Dilini Rathnayake"
        assert panel.lbl_cust_icon.text() == "DR"
        assert panel.btn_cust_clear.isVisibleTo(panel) is True
        assert panel.points_row.isVisibleTo(panel) is True
        assert "200" in panel.lbl_points.text()
        assert panel.lbl_phone.isVisibleTo(panel) is True
        assert panel.lbl_phone.text() == "0721234567"
        # Action button transitions to "Change"
        assert panel.btn_cust_select.property("mode") == "change"

    def test_clearing_customer_resets_to_walk_in(self):
        panel = ActionPanel()
        panel.show()

        panel.set_customer_info("Kasun Perera", "0771234567", 50)
        panel.clear_customer_info()

        assert panel._has_customer is False
        assert panel.lbl_cust_icon.text() == ""
        assert panel.lbl_phone.isVisibleTo(panel) is False
        assert panel.points_row.isVisibleTo(panel) is False
        assert panel.btn_cust_clear.isVisibleTo(panel) is False
        assert panel.btn_cust_select.property("mode") == "select"
