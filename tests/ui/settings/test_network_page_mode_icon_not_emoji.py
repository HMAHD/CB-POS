"""
#333: NetworkPage's mode status icon was a literal Unicode emoji
character in a plain QLabel (swapped between the computer and globe
emoji), the only place in the app that departs from the qtawesome-based
Icons.get() icon system. Emoji glyphs render via the OS's own
fallback font, ignoring the app's theme colors entirely -- which is
what actually produced the "black background" the user saw.
"""

import pytest

from cbpos.ui.views.settings_pages import NetworkPage

pytestmark = pytest.mark.usefixtures("qapp")


class TestModeIconIsARealIconNotAnEmoji:
    def test_standalone_icon_has_no_text_and_a_real_pixmap(self):
        page = NetworkPage()
        assert page.lbl_mode_icon.text() == ""
        assert not page.lbl_mode_icon.pixmap().isNull()

    def test_switching_to_network_mode_keeps_a_pixmap_not_an_emoji(self):
        page = NetworkPage()
        page._on_mode_changed("Network")
        assert page.lbl_mode_icon.text() == ""
        assert not page.lbl_mode_icon.pixmap().isNull()

    def test_switching_back_to_standalone_keeps_a_pixmap(self):
        page = NetworkPage()
        page._on_mode_changed("Network")
        page._on_mode_changed("Standalone")
        assert page.lbl_mode_icon.text() == ""
        assert not page.lbl_mode_icon.pixmap().isNull()
