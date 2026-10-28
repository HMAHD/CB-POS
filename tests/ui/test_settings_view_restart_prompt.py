"""
Settings used to apply theme and language live on Save, leaving any screen
whose retranslate_ui()/theme colors are incomplete half-switched (#581).
Save must now only persist those settings and ask "Restart now / Apply next
launch" -- and never offer Restart now while a sale is in progress. Font
size and db/terminal mode changes go through the same prompt.
"""

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import translate_in
from cbpos.ui.views.settings_view import SettingsView

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    """In-memory ConfigService stand-in so the real settings.json is never touched."""

    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value

    def update_all(self, data, **_kwargs):
        self._data.update(data)


@pytest.fixture
def calls(monkeypatch):
    store = _FakeConfigStore({"auto_report_enabled": False, "language": "en", "theme": "Dark", "font_size": 12})
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    monkeypatch.setattr(ConfigService, "set", store.set)
    monkeypatch.setattr(ConfigService, "update_all", store.update_all)
    monkeypatch.setattr(
        "cbpos.core.utils.permission_helper.check_permission_with_override",
        lambda perm, parent: True,
    )

    rec: dict = {"store": store, "set_language": [], "apply_theme": [], "info": [], "ask": [], "restart": []}
    monkeypatch.setattr("cbpos.i18n.set_language", lambda lang: rec["set_language"].append(lang))
    monkeypatch.setattr(ThemeService, "apply_theme", staticmethod(lambda name: rec["apply_theme"].append(name)))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: rec["info"].append(a))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(
        "cbpos.ui.views.settings_view.restart_application",
        lambda window: rec["restart"].append(window) or True,
        raising=False,
    )
    rec["answer"] = False

    def _ask(self, title, text, restart_label, later_label):
        rec["ask"].append(text)
        return rec["answer"]

    monkeypatch.setattr(SettingsView, "_ask_restart_now", _ask, raising=False)
    return rec


@pytest.fixture
def view(calls, db_session):
    v = SettingsView()
    yield v
    v.deleteLater()


def _shop_page(view):
    return next(p for p in view.pages if hasattr(p, "combo_language"))


def _pick_language(view, code: str) -> None:
    combo = _shop_page(view).combo_language
    combo.setCurrentIndex(combo.findData(code))


class TestAppearanceChangesPromptForRestart:
    def test_language_change_is_saved_but_not_applied_live(self, view, calls):
        _pick_language(view, "si")
        view.save_all()

        assert calls["store"].get("language") == "si"
        assert calls["set_language"] == []
        assert calls["apply_theme"] == []
        assert len(calls["ask"]) == 1
        assert calls["restart"] == []

    def test_prompt_is_shown_in_old_and_new_language(self, view, calls):
        _pick_language(view, "si")
        view.save_all()

        text = calls["ask"][0]
        assert translate_in("en", "settings.restart_prompt.message") in text
        assert translate_in("si", "settings.restart_prompt.message") in text

    def test_theme_change_is_saved_but_not_applied_live(self, view, calls):
        _shop_page(view).combo_theme.setCurrentIndex(1)
        view.save_all()

        assert calls["store"].get("theme") == "Light"
        assert calls["apply_theme"] == []
        assert len(calls["ask"]) == 1

    def test_font_size_change_uses_the_same_prompt(self, view, calls):
        _shop_page(view).spin_font_size.setText("18")
        view.save_all()

        assert calls["store"].get("font_size") == 18
        assert calls["apply_theme"] == []
        assert len(calls["ask"]) == 1

    def test_choosing_restart_now_restarts_the_app(self, view, calls):
        calls["answer"] = True
        _pick_language(view, "ta")
        view.save_all()

        assert calls["restart"] == [view.window()]

    def test_no_appearance_change_just_says_saved(self, view, calls):
        view.save_all()

        assert calls["ask"] == []
        assert calls["apply_theme"] == []
        assert len(calls["info"]) == 1


class TestNoRestartDuringASale:
    def test_cart_with_items_only_offers_next_launch(self, view, calls):
        # Unparented, view.window() is the view itself -- stand in a sales view on it
        view.sales_view = SimpleNamespace(cart_service=SimpleNamespace(items=[object()]))
        _pick_language(view, "si")
        view.save_all()

        assert calls["ask"] == []
        assert calls["restart"] == []
        assert len(calls["info"]) == 1
        assert translate_in("en", "settings.restart_prompt.busy_message") in calls["info"][0][2]
        assert calls["set_language"] == []

    def test_empty_cart_still_offers_restart(self, view, calls):
        view.sales_view = SimpleNamespace(cart_service=SimpleNamespace(items=[]))
        _pick_language(view, "si")
        view.save_all()

        assert len(calls["ask"]) == 1
