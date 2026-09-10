"""
ManagementView is laid out once while still narrow (confirmed: width was
640px right after construction, before the window reaches its final
size) -- a normal, transient moment during startup layout.
handle_resize(640) correctly auto-collapses the sidebar for that instant,
but set_collapsed() called the same toggle() used for a deliberate
manual click, which permanently wrote sidebar_collapsed=true to the
settings file -- treating a transient, automatic, responsive-layout
collapse as if it were the user's own explicit preference. From that
point on, handle_resize()'s own re-expand guard
(`if not ConfigService.get("sidebar_collapsed")`) refused to fire,
because the flag it was checking was the exact one the auto-collapse
had just written -- so even a later, genuinely wide resize could never
re-expand it, and the setting survived every app restart.
"""

import pytest

from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    """In-memory stand-in for ConfigService so these tests never touch
    the real, developer-shared settings.json on disk."""

    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture
def config_store(monkeypatch):
    import cbpos.ui.widgets.collapsible_sidebar as collapsible_sidebar_module

    store = _FakeConfigStore({"sidebar_collapsed": False})
    monkeypatch.setattr(collapsible_sidebar_module.ConfigService, "get", store.get)
    monkeypatch.setattr(collapsible_sidebar_module.ConfigService, "set", store.set)
    return store


class TestResponsiveCollapseDoesNotPersist:
    def test_auto_collapse_from_a_narrow_resize_does_not_write_to_config(self, config_store):
        sidebar = CollapsibleSidebar()
        sidebar.finalize()

        sidebar.handle_resize(640)  # narrow -- e.g. transient startup layout

        assert sidebar.is_collapsed is True
        assert config_store.get("sidebar_collapsed") is False

    def test_widening_back_out_after_an_auto_collapse_re_expands(self, config_store):
        sidebar = CollapsibleSidebar()
        sidebar.finalize()

        sidebar.handle_resize(640)  # transient narrow layout -- auto-collapses
        sidebar.handle_resize(2880)  # genuinely wide window

        assert sidebar.is_collapsed is False

    def test_manual_toggle_still_persists_the_users_real_preference(self, config_store):
        sidebar = CollapsibleSidebar()
        sidebar.finalize()

        sidebar.toggle()  # the actual collapse/expand button

        assert sidebar.is_collapsed is True
        assert config_store.get("sidebar_collapsed") is True

    def test_widening_out_after_a_manual_collapse_stays_collapsed(self, config_store):
        sidebar = CollapsibleSidebar()
        sidebar.finalize()

        sidebar.toggle()  # user deliberately collapses it
        sidebar.handle_resize(2880)  # window later becomes wide

        assert sidebar.is_collapsed is True
