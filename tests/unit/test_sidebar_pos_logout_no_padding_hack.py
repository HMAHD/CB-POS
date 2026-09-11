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


class TestPosAndLogoutHaveNoStringPaddingHack:
    def test_pos_button_text_has_no_leading_spaces(self):
        sidebar = CollapsibleSidebar()
        sidebar.retranslate_pos_logout()
        assert not sidebar.btn_pos.text().startswith(" ")

    def test_logout_button_text_has_no_leading_spaces(self):
        sidebar = CollapsibleSidebar()
        sidebar.retranslate_pos_logout()
        assert not sidebar.btn_logout.text().startswith(" ")
