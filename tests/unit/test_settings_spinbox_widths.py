"""
#322/#332: neither issue could confirm an actual rendering bug on this
platform (spin_copies renders "1" clearly headless; the System Security
fields all showed their full text at a normal window width) -- both
explicitly flagged this as needing a real screenshot from the Windows
target before deciding anything further. Applying the same
setFixedWidth(200) house convention already proven for the Sales Tax
tab's spinboxes (#371) here too is a safe, established-pattern
preventative measure regardless: it can't make a real narrow-rendering
bug worse, and removes the "bare QSpinBox, no width call" gap these two
issues both point at as the shared root pattern.
"""

import pytest

from cbpos.ui.views.settings_pages import HardwarePage, SystemPage

pytestmark = pytest.mark.usefixtures("qapp")

FIELD_WIDTH = 200


class TestCopiesFieldWidth:
    def test_spin_copies_has_the_shared_field_width(self):
        page = HardwarePage()
        assert page.spin_copies.maximumWidth() == FIELD_WIDTH


class TestSystemSecurityFieldWidths:
    def test_spin_timeout_is_wide_enough_for_its_special_value_text(self):
        # Wider than the usual 200px: its special-value text ("Disabled
        # (no auto-lock)") clips at 200px, reproducing the exact
        # truncation #332 described.
        page = SystemPage()
        assert page.spin_timeout.maximumWidth() >= 250

    def test_spin_max_login_has_the_shared_field_width(self):
        page = SystemPage()
        assert page.spin_max_login.maximumWidth() == FIELD_WIDTH

    def test_spin_lockout_has_the_shared_field_width(self):
        page = SystemPage()
        assert page.spin_lockout.maximumWidth() == FIELD_WIDTH
