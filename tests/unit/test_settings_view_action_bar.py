"""
#616: Settings had a 70px Save/Cancel footer spanning under the sidebar
too (stealing its height, #591), empty on the 3 tool pages, and owners
couldn't tell that Save saves all 7 pages while Reset is per page.

Now one ~52px action bar sits over the content area only: "Save all
changes" in the same place on every page, "Changes save automatically"
on tool pages, and an unsaved marker on each sidebar item whose page
changed.

Keeps #317: the bar never hides, so no page's content area jumps in height.
"""

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t
from cbpos.ui.views.settings_view import SettingsView

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)
        self.update_calls: list[dict] = []

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value

    def update_all(self, data):
        self.update_calls.append(dict(data))
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
    v.resize(1366, 728)
    v.show()
    QApplication.processEvents()
    yield v
    v.close()
    v.deleteLater()


TOOL_PAGE = 7  # Payment Methods -- first page after the 7 config pages


class TestActionBarPlacement:
    def test_action_bar_is_not_under_the_sidebar(self, view):
        bar_left = view.action_bar.mapTo(view, view.action_bar.rect().topLeft()).x()
        sidebar_right = view.sidebar.mapTo(view, view.sidebar.rect().topRight()).x()
        assert bar_left > sidebar_right

    def test_sidebar_has_the_full_height(self, view):
        assert view.sidebar.height() == view.height()

    def test_action_bar_is_about_52px(self, view):
        assert 48 <= view.action_bar.height() <= 56

    def test_no_70px_footer_left(self, view):
        assert not hasattr(view, "footer_frame")

    def test_per_page_reset_is_not_in_the_action_bar(self, view):
        for page in view.pages:
            assert not view.action_bar.isAncestorOf(page.btn_reset_defaults)


class TestSaveIsTheSameOnEveryPage:
    def test_save_all_label(self, view):
        assert view.btn_save.text() == _t("settings.btn_save_all")

    @pytest.mark.parametrize("index", [0, 3, 6, TOOL_PAGE, 9])
    def test_save_stays_visible_in_the_same_place(self, view, index):
        view.stack.setCurrentIndex(0)
        QApplication.processEvents()
        first = view.btn_save.mapTo(view, view.btn_save.rect().topLeft())

        view.stack.setCurrentIndex(index)
        QApplication.processEvents()

        assert view.btn_save.isVisible()
        assert view.btn_save.mapTo(view, view.btn_save.rect().topLeft()) == first

    def test_action_bar_never_hides_so_content_height_never_jumps(self, view):
        view.stack.setCurrentIndex(0)
        QApplication.processEvents()
        height = view.stack.height()
        view.stack.setCurrentIndex(TOOL_PAGE)
        QApplication.processEvents()
        assert view.action_bar.isVisible()
        assert view.stack.height() == height


class TestAutoSaveText:
    def test_tool_page_says_changes_save_automatically(self, view):
        view.stack.setCurrentIndex(TOOL_PAGE)
        QApplication.processEvents()
        assert view.lbl_status.isVisible()
        assert view.lbl_status.text() == _t("settings.auto_save_hint")

    def test_config_page_does_not_claim_auto_save(self, view):
        view.stack.setCurrentIndex(0)
        QApplication.processEvents()
        assert view.lbl_status.text() != _t("settings.auto_save_hint")


class TestUnsavedMarkersAndSaveAll:
    def _edit_two_pages(self, view):
        view.pages[0].input_shop_name.setText("Nimal Stores")
        view.pages[1].spin_max_discount.setValue(view.pages[1].spin_max_discount.value() + 5)
        QApplication.processEvents()

    def test_no_markers_before_editing(self, view):
        assert not any(btn.is_unsaved() for btn in view.sidebar.nav_buttons)

    def test_editing_two_pages_marks_both_sidebar_items(self, view):
        self._edit_two_pages(view)
        assert view.btn_shop_info.is_unsaved()
        assert view.btn_sales_tax.is_unsaved()
        assert not view.btn_hardware.is_unsaved()

    def test_status_lists_the_unsaved_pages(self, view):
        self._edit_two_pages(view)
        text = view.lbl_status.text()
        assert _t("settings.sidebar_shop_info") in text
        assert _t("settings.sidebar_sales_tax").replace("&&", "&") in text
        assert "&&" not in text

    def test_undoing_an_edit_clears_its_marker(self, view):
        original = view.pages[0].input_shop_name.text()
        view.pages[0].input_shop_name.setText("Nimal Stores")
        view.pages[0].input_shop_name.setText(original)
        QApplication.processEvents()
        assert not view.btn_shop_info.is_unsaved()

    def test_save_saves_both_pages_and_clears_the_markers(self, view, config_store):
        self._edit_two_pages(view)
        new_discount = view.pages[1].spin_max_discount.value()

        view.btn_save.click()

        saved = config_store.update_calls[-1]
        assert saved["shop_name"] == "Nimal Stores"
        assert saved["max_discount_percent"] == new_discount
        assert not any(btn.is_unsaved() for btn in view.sidebar.nav_buttons)

    def test_reset_to_defaults_does_not_leave_a_stale_marker(self, view, monkeypatch):
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
        view.pages[1].spin_max_discount.setValue(view.pages[1].spin_max_discount.value() + 5)

        view.pages[1].btn_reset_defaults.click()
        QApplication.processEvents()

        assert not view.btn_sales_tax.is_unsaved()


class TestFitsA768Screen:
    def test_settings_never_needs_more_than_728px(self, view):
        """Admin Tools alone needed ~770px, forcing Settings past a 1366x768
        screen and clipping POS/Logout off the bottom (#591)."""
        assert view.minimumSizeHint().height() <= 728
        assert view.height() == 728
