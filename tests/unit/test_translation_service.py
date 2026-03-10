"""
Unit tests for TranslationService — fallback chain, interpolation,
translate_in(), and callback registration/unregistration.
"""

import json

import pytest

from cbpos.i18n.translation_service import TranslationService


@pytest.fixture
def i18n_dir(tmp_path):
    """Create a temporary i18n directory with test translation files."""
    en_data = {
        "login": {"title": "Login", "greeting": "Hello, {name}!"},
        "common": {"save": "Save", "cancel": "Cancel"},
        "receipt_strings": {"total": "Total", "change": "Change"},
    }
    si_data = {
        "login": {"title": "පිවිසුම", "greeting": "ආයුබෝවන්, {name}!"},
        "common": {"save": "සුරකින්න"},
        # "cancel" intentionally missing — tests fallback
    }
    ta_data = {
        "login": {"title": "உள்நுழைவு"},
    }

    (tmp_path / "en.json").write_text(json.dumps(en_data), encoding="utf-8")
    (tmp_path / "si.json").write_text(json.dumps(si_data), encoding="utf-8")
    (tmp_path / "ta.json").write_text(json.dumps(ta_data), encoding="utf-8")
    return tmp_path


@pytest.fixture
def svc(i18n_dir):
    """Create a TranslationService pointed at the test i18n directory."""
    service = TranslationService()
    service._i18n_dir = i18n_dir
    service._translations.clear()
    service._load_language("en")
    return service


class TestFallbackChain:
    """Test translation lookup with fallback: current → English → raw key."""

    def test_english_key_found(self, svc):
        assert svc.translate("login.title") == "Login"

    def test_current_language_key_found(self, svc):
        svc.set_language("si")
        assert svc.translate("login.title") == "පිවිසුම"

    def test_fallback_to_english_when_key_missing_in_current(self, svc):
        svc.set_language("si")
        # "cancel" is missing in si.json, should fall back to English
        assert svc.translate("common.cancel") == "Cancel"

    def test_fallback_to_raw_key_when_missing_everywhere(self, svc):
        result = svc.translate("nonexistent.key")
        assert result == "nonexistent.key"

    def test_fallback_chain_with_tamil(self, svc):
        svc.set_language("ta")
        # "common.save" missing in ta.json → falls back to English
        assert svc.translate("common.save") == "Save"


class TestInterpolation:
    """Test parameter substitution in translated strings."""

    def test_basic_interpolation(self, svc):
        result = svc.translate("login.greeting", name="Akash")
        assert result == "Hello, Akash!"

    def test_interpolation_in_non_english(self, svc):
        svc.set_language("si")
        result = svc.translate("login.greeting", name="Akash")
        assert result == "ආයුබෝවන්, Akash!"

    def test_missing_param_returns_string_without_crash(self, svc):
        # Should not raise — just logs warning and returns unformatted
        result = svc.translate("login.greeting")
        assert "{name}" in result

    def test_extra_params_ignored(self, svc):
        result = svc.translate("login.title", extra="unused")
        assert result == "Login"


class TestTranslateIn:
    """Test translate_in() for language-specific lookup without switching."""

    def test_translate_in_different_language(self, svc):
        # Active language is English, but translate in Sinhala
        assert svc.current_language == "en"
        result = svc.translate_in("si", "login.title")
        assert result == "පිවිසුම"
        # Active language should not change
        assert svc.current_language == "en"

    def test_translate_in_with_fallback(self, svc):
        # "common.cancel" missing in si → falls back to English
        result = svc.translate_in("si", "common.cancel")
        assert result == "Cancel"

    def test_translate_in_with_interpolation(self, svc):
        result = svc.translate_in("si", "login.greeting", name="User")
        assert result == "ආයුබෝවන්, User!"

    def test_translate_in_missing_key_returns_raw(self, svc):
        result = svc.translate_in("si", "nonexistent.key")
        assert result == "nonexistent.key"


class TestCallbackRegistration:
    """Test language change callback registration and unregistration."""

    def test_callback_called_on_language_change(self, svc):
        called = []

        class Holder:
            def on_change(self):
                called.append(True)

        holder = Holder()
        svc.register_change_callback(holder.on_change)
        svc.set_language("si")
        assert len(called) == 1

    def test_callback_not_called_after_unregister(self, svc):
        called = []

        class Holder:
            def on_change(self):
                called.append(True)

        holder = Holder()
        svc.register_change_callback(holder.on_change)
        svc.unregister_change_callback(holder.on_change)
        svc.set_language("si")
        assert len(called) == 0

    def test_dead_callback_pruned_automatically(self, svc):
        """When the object owning a bound method is deleted, callback is pruned."""
        called = []

        class Holder:
            def on_change(self):
                called.append(True)

        holder = Holder()
        svc.register_change_callback(holder.on_change)
        del holder  # Should make the weak reference dead

        svc.set_language("si")
        assert len(called) == 0
        # Dead ref should be pruned
        assert len(svc._change_callbacks) == 0


class TestSetLanguage:
    """Test set_language() behavior."""

    def test_set_supported_language(self, svc):
        svc.set_language("si")
        assert svc.current_language == "si"

    def test_set_unsupported_language_falls_back_to_english(self, svc):
        svc.set_language("fr")
        assert svc.current_language == "en"

    def test_language_file_loaded_on_demand(self, svc):
        assert "ta" not in svc._translations
        svc.set_language("ta")
        assert "ta" in svc._translations


class TestUtilityMethods:
    """Test get_missing_keys, get_all_keys, reload."""

    def test_get_all_keys(self, svc):
        keys = svc.get_all_keys()
        assert "login.title" in keys
        assert "common.save" in keys

    def test_get_missing_keys(self, svc):
        svc._load_language("si")
        missing = svc.get_missing_keys("si")
        assert "common.cancel" in missing
        assert "login.title" not in missing

    def test_reload_refreshes_data(self, svc, i18n_dir):
        # Modify the English file
        en_data = {"login": {"title": "Updated Login"}}
        (i18n_dir / "en.json").write_text(json.dumps(en_data), encoding="utf-8")

        svc.reload()
        assert svc.translate("login.title") == "Updated Login"


class TestFlatten:
    """Test the static _flatten helper."""

    def test_nested_dict(self):
        data = {"a": {"b": {"c": "value"}}}
        result = TranslationService._flatten(data)
        assert result == {"a.b.c": "value"}

    def test_skips_underscore_keys(self):
        data = {"_meta": "skip", "visible": "keep"}
        result = TranslationService._flatten(data)
        assert "_meta" not in result
        assert "visible" in result

    def test_flat_dict(self):
        data = {"key": "value"}
        result = TranslationService._flatten(data)
        assert result == {"key": "value"}
