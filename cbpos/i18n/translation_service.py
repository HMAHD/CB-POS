"""
Centralized translation service for CB-POS multilingual support.

Loads translations from JSON files and provides a fast key-based lookup
with automatic fallback to English when a translation is missing.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Callable

logger = logging.getLogger(__name__)


class TranslationService:
    """Manages loading and retrieving translations from JSON files."""

    SUPPORTED_LANGUAGES = ("en", "si", "ta")

    def __init__(self) -> None:
        self.current_language: str = "en"
        self._translations: Dict[str, Dict[str, str]] = {}
        self._change_callbacks: List[Callable] = []
        self._i18n_dir = Path(__file__).parent

        # Always load English as the fallback language
        self._load_language("en")

    def _load_language(self, lang_code: str) -> None:
        """Load a language JSON file into memory."""
        json_path = self._i18n_dir / f"{lang_code}.json"
        if not json_path.exists():
            logger.warning("Translation file not found: %s", json_path)
            return
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Flatten nested JSON into dot-notation keys
            self._translations[lang_code] = self._flatten(data)
            logger.debug(
                "Loaded %d translation keys for '%s'",
                len(self._translations[lang_code]),
                lang_code,
            )
        except Exception as e:
            logger.error("Failed to load translations for %s: %s", lang_code, e)

    def set_language(self, lang_code: str) -> None:
        """Switch active language. Loads file if not already cached."""
        if lang_code not in self.SUPPORTED_LANGUAGES:
            logger.warning("Unsupported language code: %s", lang_code)
            lang_code = "en"

        if lang_code not in self._translations:
            self._load_language(lang_code)

        self.current_language = lang_code

        # Notify all registered UI components to retranslate
        for callback in list(self._change_callbacks):
            try:
                callback()
            except Exception as e:
                logger.error("Error in language change callback: %s", e)

    def translate(self, key: str, **kwargs) -> str:
        """Look up a translation key with optional parameter substitution.

        Fallback chain: current_language -> English -> raw key.

        Args:
            key: Dot-notation key like ``"login.enter_pin"``.
            **kwargs: Named parameters for ``str.format()`` interpolation.

        Returns:
            Translated string with parameters substituted.
        """
        # Try current language
        text = self._translations.get(self.current_language, {}).get(key)

        # Fallback to English
        if text is None and self.current_language != "en":
            text = self._translations.get("en", {}).get(key)

        # Fallback to key itself (makes missing translations obvious in UI)
        if text is None:
            if self.current_language != "en":
                logger.debug("Missing translation: %s [%s]", key, self.current_language)
            return key

        # Parameter substitution
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError, ValueError) as e:
                logger.warning("Translation format error for '%s': %s", key, e)

        return text

    def register_change_callback(self, callback: Callable) -> None:
        """Register a callable to be invoked when language changes."""
        if callback not in self._change_callbacks:
            self._change_callbacks.append(callback)

    def unregister_change_callback(self, callback: Callable) -> None:
        """Remove a language-change callback."""
        try:
            self._change_callbacks.remove(callback)
        except ValueError:
            pass

    def get_missing_keys(self, lang_code: str) -> List[str]:
        """Return keys present in English but missing in the given language."""
        en_keys = set(self._translations.get("en", {}).keys())
        lang_keys = set(self._translations.get(lang_code, {}).keys())
        return sorted(en_keys - lang_keys)

    def get_all_keys(self) -> List[str]:
        """Return all known English translation keys."""
        return sorted(self._translations.get("en", {}).keys())

    def reload(self) -> None:
        """Reload all cached translation files from disk."""
        for lang_code in list(self._translations.keys()):
            self._load_language(lang_code)

    @staticmethod
    def _flatten(data: Dict, prefix: str = "") -> Dict[str, str]:
        """Flatten nested JSON into dot-notation keys.

        Example: ``{"login": {"title": "Hi"}}`` → ``{"login.title": "Hi"}``
        Skips keys starting with ``_`` (metadata).
        """
        result: Dict[str, str] = {}
        for key, value in data.items():
            if key.startswith("_"):
                continue
            full_key = f"{prefix}{key}" if prefix else key
            if isinstance(value, dict):
                result.update(TranslationService._flatten(value, f"{full_key}."))
            else:
                result[full_key] = str(value)
        return result
