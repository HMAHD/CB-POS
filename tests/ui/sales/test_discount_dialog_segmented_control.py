"""
The discount type selector was two QRadioButtons -- a radio button's
indicator+text always renders left-anchored inside whatever width the
layout gives it, leaving each segment's text hugging the left edge with
a lopsided gap of empty space on the right instead of looking like an
actual centered segmented control. Switched to checkable QPushButtons
(which center their own text), matching the checkable-button pattern
already used for tab-like toggles elsewhere in this app.
"""

from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QPushButton

from cbpos.ui.dialogs.discount_dialog import DiscountDialog

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def dialog():
    dlg = DiscountDialog(original_amount=Decimal("612.00"))
    yield dlg
    dlg.deleteLater()


class TestSegmentsAreCheckableButtons:
    def test_percent_and_fixed_segments_are_pushbuttons(self, dialog):
        assert isinstance(dialog.rb_percent, QPushButton)
        assert isinstance(dialog.rb_fixed, QPushButton)
        assert dialog.rb_percent.isCheckable()
        assert dialog.rb_fixed.isCheckable()

    def test_percent_segment_is_checked_by_default(self, dialog):
        assert dialog.rb_percent.isChecked()
        assert not dialog.rb_fixed.isChecked()

    def test_segments_are_mutually_exclusive(self, dialog):
        dialog.rb_fixed.click()

        assert dialog.rb_fixed.isChecked()
        assert not dialog.rb_percent.isChecked()

    def test_clicking_fixed_switches_the_discount_type(self, dialog):
        dialog.rb_fixed.click()

        assert dialog.discount_type == "FIXED"

    def test_segments_share_the_frame_equally(self, dialog):
        type_layout = dialog.rb_percent.parentWidget().layout()
        percent_index = type_layout.indexOf(dialog.rb_percent)
        fixed_index = type_layout.indexOf(dialog.rb_fixed)

        assert type_layout.stretch(percent_index) == type_layout.stretch(fixed_index) == 1
