"""
#317: footer_frame (70px, holding Save/Cancel) was hidden entirely via
setVisible(False) on Payment Methods/Data Safety/Admin Tools (the 3
"operational" pages with no load/save). Since Qt reclaims a hidden
widget's space, this made those 3 pages render ~70px taller in their
content area than the other 7 -- a real, visible height jump depending
on which sidebar item is selected. Keep the frame's 70px always
reserved; only the Save/Cancel buttons themselves hide on pages with
nothing to save.
"""

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.services.config_service import ConfigService
from cbpos.ui.views.settings_view import SettingsView

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value

    def update_all(self, data):
        self._data.update(data)


@pytest.fixture
def config_store(monkeypatch):
    store = _FakeConfigStore({"auto_report_enabled": False, "language": "en", "theme": "Dark", "font_size": 12})
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    monkeypatch.setattr(ConfigService, "set", store.set)
    monkeypatch.setattr(ConfigService, "update_all", store.update_all)
    return store


@pytest.fixture
def view(qapp, db_session, config_store, monkeypatch):
    monkeypatch.setattr(
        "cbpos.core.utils.permission_helper.check_permission_with_override",
        lambda perm, parent: True,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    v = SettingsView()
    v.show()
    yield v
    v.deleteLater()


class TestFooterFrameStaysReservedOnOperationalPages:
    def test_footer_frame_visible_on_a_config_page(self, view):
        view.stack.setCurrentIndex(0)
        assert view.footer_frame.isVisible() is True

    def test_footer_frame_still_visible_on_an_operational_page(self, view):
        operational_index = len(view.pages)  # Payment Methods
        view.stack.setCurrentIndex(operational_index)
        assert view.footer_frame.isVisible() is True

    def test_save_and_cancel_buttons_hide_on_operational_pages(self, view):
        operational_index = len(view.pages)
        view.stack.setCurrentIndex(operational_index)
        assert view.btn_save.isVisible() is False
        assert view.btn_cancel.isVisible() is False

    def test_save_and_cancel_buttons_show_on_config_pages(self, view):
        view.stack.setCurrentIndex(0)
        assert view.btn_save.isVisible() is True
        assert view.btn_cancel.isVisible() is True
