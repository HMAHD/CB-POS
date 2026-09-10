"""
The Yearly Summary panel's big total (QLabel#SummaryBigValue, 32px bold)
had zero safety net -- no word wrap, no elide mode, no minimum width
generous enough for a worst-case total -- so it had nothing to fall back
on if real-device font metrics ever came out even slightly wider than in
an offscreen render. Word wrap can't clip; it can only ever fall back to
a second line the panel already has vertical room for.
"""

import pytest

from cbpos.ui.views.dashboard_view import DashboardView

pytestmark = pytest.mark.usefixtures("qapp")


class TestYearlySummaryHasAClippingSafetyNet:
    def test_yearly_total_label_wraps_instead_of_clipping(self, db_session):
        view = DashboardView()
        assert view.lbl_yearly_total.wordWrap() is True

    def test_summary_panel_has_headroom_beyond_the_shared_panel_floor(self, db_session):
        view = DashboardView()
        panel = view.lbl_yearly_total.parentWidget()
        # 220 is the shared minimum every dashboard panel gets (#203) --
        # this one needs more room for its much larger 32px font.
        assert panel.minimumWidth() > 220
