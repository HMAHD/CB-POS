"""
Regression test for a segfault in DenominationWidget.

setProperty("lbl_total", QLabel()) stored a parentless QLabel as a dynamic
Qt property with no Python reference keeping it alive; PyQt6 garbage-collected
the underlying C++ object, and the next .property("lbl_total") access
dereferenced a dangling pointer, crashing the whole process (segfault, not a
catchable Python exception). Found while wiring the shift-open/close feature
into the UI for the first time -- this widget backs both ShiftClosingDialog
and StartShiftDialog and had apparently never been constructed by the running
app before, since the entire shift feature was unwired.
"""

from decimal import Decimal

from cbpos.ui.widgets.denomination_widget import DenominationWidget


def test_building_and_counting_denominations_does_not_crash(qapp):
    """Constructing the widget and entering counts must not segfault."""
    widget = DenominationWidget(denominations=[5000, 1000, 500, 100])

    widget.counts[5000].setValue(2)
    widget.counts[100].setValue(3)

    assert widget._current_total == Decimal("10300")
    assert widget._row_totals[5000].text() == "10,000.00"
    assert widget._row_totals[100].text() == "300.00"
