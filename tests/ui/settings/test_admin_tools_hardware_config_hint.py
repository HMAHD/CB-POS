"""
#343: Admin Tools' Hardware tab has a real Test Print/Open Drawer
button pair calling the same HardwareTestService methods as Settings ->
Hardware's own test buttons, which reads as duplicated surface area --
but this tab never actually edits printer selection or paper width,
only Settings -> Hardware does. Add a short hint clarifying that
distinction rather than removing the (still genuinely convenient)
duplicate test buttons.
"""

import pytest

from cbpos.ui.views.admin_tools_view import AdminToolsView

pytestmark = pytest.mark.usefixtures("qapp")


class TestHardwareTabClarifiesItIsReadOnly:
    def test_config_hint_label_is_not_empty(self, db_session):
        view = AdminToolsView()
        assert view.lbl_hw_config_hint.text() != ""

    def test_hint_points_to_settings_hardware(self, db_session):
        view = AdminToolsView()
        assert "Settings" in view.lbl_hw_config_hint.text()
        assert "Hardware" in view.lbl_hw_config_hint.text()
