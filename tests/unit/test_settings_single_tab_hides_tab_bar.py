"""#571: a Settings page with a single tab shows no tab bar.

The Documents page only has a "Numbering" tab; a lone tab implies there is
hidden content. Pages with two or more tabs keep their tab bar.
"""

import pytest

from cbpos.ui.views.settings_pages import DocumentPage, SalesTaxPage

pytestmark = pytest.mark.usefixtures("qapp")


def test_single_tab_page_hides_tab_bar(qtbot):
    page = DocumentPage()
    qtbot.addWidget(page)
    page.show()
    assert page.tabs.count() == 1
    assert page.tabs.tabBar().isVisible() is False


def test_multi_tab_page_keeps_tab_bar(qtbot):
    page = SalesTaxPage()
    qtbot.addWidget(page)
    page.show()
    assert page.tabs.count() > 1
    assert page.tabs.tabBar().isVisible() is True
