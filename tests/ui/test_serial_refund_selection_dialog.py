"""UI tests for SerialRefundSelectionDialog (#823, #824)."""

import pytest

from cbpos.ui.dialogs.serial_refund_selection_dialog import SerialRefundSelectionDialog

pytestmark = pytest.mark.usefixtures("qapp")


class TestSerialRefundSelectionDialogUI:
    def test_initial_state_and_counter(self, qtbot):
        serials = ["SN-001", "SN-002", "SN-003"]
        dlg = SerialRefundSelectionDialog(
            product_name="Television 4K",
            active_serials=serials,
            required_count=2,
        )
        qtbot.addWidget(dlg)
        dlg.show()

        assert len(dlg._checkboxes) == 3
        assert dlg.btn_confirm.isEnabled() is False  # 0 selected, 2 required
        assert "0" in dlg.lbl_counter.text()
        assert "2" in dlg.lbl_counter.text()

    def test_selection_enables_confirm_when_exact_count_met(self, qtbot):
        serials = ["SN-001", "SN-002", "SN-003"]
        dlg = SerialRefundSelectionDialog(
            product_name="Television 4K",
            active_serials=serials,
            required_count=2,
        )
        qtbot.addWidget(dlg)
        dlg.show()

        # Select first
        dlg._checkboxes[0].setChecked(True)
        assert dlg.btn_confirm.isEnabled() is False

        # Select second -> exactly 2
        dlg._checkboxes[1].setChecked(True)
        assert dlg.btn_confirm.isEnabled() is True
        assert dlg.get_selected_serials() == ["SN-001", "SN-002"]

        # Select third -> 3 selected, exceeding required 2 -> should be disabled
        dlg._checkboxes[2].setChecked(True)
        assert dlg.btn_confirm.isEnabled() is False

        # Uncheck third -> back to 2 -> enabled
        dlg._checkboxes[2].setChecked(False)
        assert dlg.btn_confirm.isEnabled() is True
