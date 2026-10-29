"""
#524: SideMenu applied a QGraphicsDropShadowEffect to the whole panel for a
soft depth cue. Because it sits on the panel (the parent of every nav
button), Qt must run the *entire* panel through an offscreen blur-composite
pass on every repaint of any single child -- including a plain hover/pressed
state change on one button. Measured at a ~35x repaint-cost increase
(0.06ms -> 2.05ms per repaint, offscreen headless) versus no effect, which
is the most likely cause of the reported "side menu hover feels laggy"
behavior. The QSS border-left on #POSSideMenu still gives a visible edge.
"""

import pytest

from cbpos.ui.widgets.side_menu import SideMenu

pytestmark = pytest.mark.usefixtures("qapp")


def test_side_menu_has_no_graphics_effect(qapp):
    menu = SideMenu()
    assert menu.graphicsEffect() is None
