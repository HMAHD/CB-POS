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

import weakref
from collections.abc import Callable
from typing import Any

from cbpos.core.utils.destroy_hooks import call_on_destroyed
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


def t_or(key: str, fallback: str, **kwargs) -> str:
    """Translate key; if no translation exists, return fallback instead (#698)."""
    text = _t(key, **kwargs)
    return fallback if text == key else text


_t_or = t_or


def set_language(lang_code: str) -> None:
    """Switch the active language and notify all registered UI components."""
    _service.set_language(lang_code)


def get_language() -> str:
    """Return the current language code."""
    return _service.current_language


def translate_in(lang_code: str, key: str, **kwargs) -> str:
    """Translate a key in a specific language without switching the active language.

    Used by the receipt system to print in a different language than the UI.
    Falls back to English, then to the raw key, just like ``_t()``.

    Args:
        lang_code: Language to translate into (e.g. ``"si"``).
        key: Dot-notation key, e.g. ``"receipt_strings.total"``.
        **kwargs: Named parameters for interpolation.
    """
    return _service.translate_in(lang_code, key, **kwargs)


def register_language_callback(callback: Callable[[], None], owner: Any = None) -> None:
    """Register a callback to be invoked when language changes.

    Args:
        callback: Called with no arguments after every language switch. Held
            weakly, so a bound method does not keep its widget alive.
        owner: Optional QObject (usually the widget ``callback`` belongs to).
            When it is destroyed, ``callback`` is unregistered. This goes through
            ``call_on_destroyed``; never connect ``owner.destroyed`` to a lambda
            or nested function yourself, since that can segfault.
    """
    _service.register_change_callback(callback)
    if owner is not None:
        call_on_destroyed(owner, _unregister_if_alive, TranslationService._make_ref(callback))


def _unregister_if_alive(callback_ref: "weakref.ref | None") -> None:
    """Unregister the callback behind ``callback_ref`` unless it is already gone."""
    callback = callback_ref() if callback_ref is not None else None
    if callback is not None:
        _service.unregister_change_callback(callback)


def unregister_language_callback(callback: Callable[[], None]) -> None:
    """Unregister a language-change callback."""
    _service.unregister_change_callback(callback)
