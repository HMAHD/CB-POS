"""
The value field never received focus on open, so a cashier had to click
into it before typing a custom discount -- a real gap for a
keyboard-first, one-field dialog whose whole job is entering one number
fast. Matches the same showEvent-focus pattern already used by
ManagerOverrideDialog for its PIN field.
"""

from decimal import Decimal

import pytest

from cbpos.ui.dialogs.discount_dialog import DiscountDialog

pytestmark = pytest.mark.usefixtures("qapp")


class TestValueFieldGetsInitialFocus:
    def test_value_field_has_focus_after_show(self, qtbot):
        dlg = DiscountDialog(original_amount=Decimal("612.00"))
        qtbot.addWidget(dlg)
        dlg.show()

        # hasFocus() requires the top-level window to be OS-activated,
        # which an offscreen/headless test run never grants -- Qt's own
        # notion of "which widget would receive keystrokes right now"
        # within this dialog is focusWidget(), independent of that.
        assert dlg.focusWidget() is dlg.spin_value

    def test_value_text_is_selected_after_show(self, qtbot):
        dlg = DiscountDialog(original_amount=Decimal("612.00"))
        qtbot.addWidget(dlg)
        dlg.show()

        assert dlg.spin_value.lineEdit().selectedText() != ""
