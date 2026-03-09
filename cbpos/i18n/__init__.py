"""
CB-POS Internationalization (i18n) Module.

Usage::

    from cbpos.i18n import _t

    label.setText(_t("login.enter_pin"))
    msg = _t("errors.insufficient_stock", product="Rice")

To switch language at runtime::

    from cbpos.i18n import set_language
    set_language("si")  # Sinhala
"""

from cbpos.i18n.translation_service import TranslationService

# Singleton instance — shared across the entire application
_service = TranslationService()


def _t(key: str, **kwargs) -> str:
    """Translate a key with optional parameter substitution.

    Args:
        key: Dot-notation key, e.g. ``"login.enter_pin"``.
        **kwargs: Named parameters for interpolation.

    Returns:
        Translated string, falling back to English, then the raw key.
    """
    return _service.translate(key, **kwargs)


def set_language(lang_code: str) -> None:
    """Switch the active language and notify all registered UI components."""
    _service.set_language(lang_code)


def get_language() -> str:
    """Return the current language code."""
    return _service.current_language


def register_language_callback(callback) -> None:
    """Register a callback to be invoked when language changes."""
    _service.register_change_callback(callback)


def unregister_language_callback(callback) -> None:
    """Unregister a language-change callback."""
    _service.unregister_change_callback(callback)
