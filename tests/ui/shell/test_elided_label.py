"""
The action panel's customer name/phone label had no truncation at all --
a long name pushed the phone number past the card's edge with a hard
clip and no way to read the rest. ElidedLabel keeps the full string
available (via text() and a tooltip) while only ever painting what
fits its current width.
"""

import pytest

from cbpos.ui.widgets.elided_label import ElidedLabel

pytestmark = pytest.mark.usefixtures("qapp")


class TestElidedLabel:
    def test_text_returns_the_full_unelided_string(self):
        label = ElidedLabel()
        label.resize(50, 20)
        label.setText("Wanninayake Mudiyanselage Dissanayake (0771234567)")

        assert label.text() == "Wanninayake Mudiyanselage Dissanayake (0771234567)"

    def test_tooltip_shows_the_full_string(self):
        label = ElidedLabel()
        label.resize(50, 20)
        label.setText("Wanninayake Mudiyanselage Dissanayake (0771234567)")

        assert label.toolTip() == "Wanninayake Mudiyanselage Dissanayake (0771234567)"

    def test_displayed_text_is_shorter_than_the_full_string_when_too_narrow(self):
        label = ElidedLabel()
        label.resize(50, 20)
        label.setText("Wanninayake Mudiyanselage Dissanayake (0771234567)")

        displayed = super(ElidedLabel, label).text()
        assert len(displayed) < len("Wanninayake Mudiyanselage Dissanayake (0771234567)")

    def test_short_text_that_fits_is_not_truncated(self):
        label = ElidedLabel()
        label.resize(400, 20)
        label.setText("Short")

        displayed = super(ElidedLabel, label).text()
        assert displayed == "Short"

    def test_resizing_narrower_re_elides_the_displayed_text(self, qapp):
        # resizeEvent is only dispatched once a widget has actually been
        # shown -- a parentless, unshown widget's resize() updates its
        # geometry but never fires the event, so re-eliding needs .show()
        # + a pumped event loop to actually observe here.
        label = ElidedLabel()
        label.show()
        label.resize(400, 20)
        qapp.processEvents()
        label.setText("Wanninayake Mudiyanselage Dissanayake (0771234567)")
        wide_displayed = super(ElidedLabel, label).text()

        label.resize(50, 20)
        qapp.processEvents()
        narrow_displayed = super(ElidedLabel, label).text()

        assert narrow_displayed != wide_displayed
