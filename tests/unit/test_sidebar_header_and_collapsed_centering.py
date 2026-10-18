"""Tests for issue #608 (UI-039): Management shell header spacing, icon alignment, and collapsed sidebar centering."""

import re
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture
def config_store(monkeypatch):
    import cbpos.ui.widgets.collapsible_sidebar as module

    store = _FakeConfigStore({"sidebar_collapsed": False})
    monkeypatch.setattr(module.ConfigService, "get", store.get)
    monkeypatch.setattr(module.ConfigService, "set", store.set)
    return store


def test_sidebar_header_spacing_and_vertical_alignment(config_store):
    """Header should have 16-20px horizontal margins and vertically centered logo."""
    sidebar = CollapsibleSidebar()
    margins = sidebar._header_layout.contentsMargins()
    assert 16 <= margins.left() <= 20
    assert 16 <= margins.right() <= 20

    # Verify vertical alignment of logo (item 0 in header layout)
    logo_align = sidebar._header_layout.itemAt(0).alignment()
    assert bool(logo_align & Qt.AlignmentFlag.AlignVCenter)

    # Verify hamburger toggle is removed from the header layout
    for i in range(sidebar._header_layout.count()):
        widget = sidebar._header_layout.itemAt(i).widget()
        if widget is not None:
            assert widget.objectName() != "SidebarToggle"

    sidebar.close()
    sidebar.deleteLater()


def test_sidebar_collapsed_toggle_is_centered(config_store):
    """When collapsed, C3 logo mark should be horizontally centered in the 70px rail."""
    sidebar = CollapsibleSidebar()
    sidebar.finalize()
    sidebar.set_collapsed(True)
    sidebar._anim_min.stop()
    sidebar._anim_max.stop()
    sidebar.setFixedWidth(70)

    # In collapsed state, header layout margins should be symmetric or 0
    # and logo mark should be centered
    assert sidebar.is_collapsed
    assert sidebar._is_toggle_centered_when_collapsed()

    sidebar.close()
    sidebar.deleteLater()


def test_qss_collapsed_buttons_have_symmetric_padding():
    """Verify dark.qss and light.qss have symmetric horizontal padding for collapsed buttons."""
    styles_dir = Path("cbpos/ui/styles")
    for qss_file in (styles_dir / "dark.qss", styles_dir / "light.qss"):
        content = qss_file.read_text(encoding="utf-8")
        # Check BtnPos[collapsed="true"]
        pos_match = re.search(r"QToolButton#BtnPos\[collapsed=\"true\"\]\s*\{([^}]+)\}", content)
        assert pos_match, f"BtnPos collapsed rule missing in {qss_file}"
        pos_body = pos_match.group(1)
        assert "padding-left: 0px;" in pos_body
        assert "padding-right: 0px;" in pos_body or "padding: 0" in pos_body

        # Check BtnLogout[collapsed="true"]
        logout_match = re.search(r"QToolButton#BtnLogout\[collapsed=\"true\"\]\s*\{([^}]+)\}", content)
        assert logout_match, f"BtnLogout collapsed rule missing in {qss_file}"
        logout_body = logout_match.group(1)
        assert "padding-left: 0px;" in logout_body
        assert "padding-right: 0px;" in logout_body or "padding: 0" in logout_body
