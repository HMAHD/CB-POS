"""
Reports' date-range filter fields had no fixed display format, so they fell
back to the locale default instead of the unambiguous format shown
elsewhere in the app -- and with no setReadOnly()/input mask either, free
typing could drift into an invalid or unintended date.
"""

import pytest

from cbpos.ui.views.reports.filter_widget import FilterWidget

pytestmark = pytest.mark.usefixtures("qapp")


class TestDateRangeDisplayFormat:
    def test_start_and_end_date_fields_use_a_fixed_unambiguous_format(self):
        widget = FilterWidget()
        widget.build_filters([{"type": "date_range", "name": "period", "label": "Period"}])

        fields = widget.inputs["period"]

        assert fields["start"].displayFormat() == "yyyy-MM-dd"
        assert fields["end"].displayFormat() == "yyyy-MM-dd"
