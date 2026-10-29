"""
#288: retranslate_pos_logout() used to do
self.btn_pos.setText("   " + _t("management.sidebar_pos")) -- three
literal space characters faking icon-text spacing, on the two buttons
at the bottom of every sidebar, while every other nav button already
got real spacing from SidebarButton's baked-in icon padding (#314).

By the time this was investigated for #288, the sidebar redesign
(commit 1e8728f) had already rewritten retranslate_pos_logout() and
dropped the hack as a byproduct -- btn_pos/btn_logout are now plain
SidebarButton instances built exactly like every regular nav button.
This test locks that in so the hack can't quietly come back.
"""

import pytest

from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar

pytestmark = pytest.mark.usefixtures("qapp")


class TestPosAndLogoutRemovedFromSidebar:
    def test_sidebar_has_no_bottom_exit_buttons(self):
        sidebar = CollapsibleSidebar()
        sidebar.finalize()
        assert not hasattr(sidebar, "btn_pos")
        assert not hasattr(sidebar, "btn_logout")
        assert not hasattr(sidebar, "_bottom_widget")

    def test_nav_buttons_have_no_leading_spaces(self):
        sidebar = CollapsibleSidebar()
        btn = sidebar.add_nav_button("Inventory", "fa5s.boxes", 1)
        sidebar.finalize()
        assert not btn.text().startswith(" ")
