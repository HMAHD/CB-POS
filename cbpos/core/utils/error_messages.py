"""
Utility for translating service-layer error messages to the user's language.

Service methods raise ValueError with English messages. This module maps
known error patterns to i18n keys so the UI can display translated text.
"""

from sqlalchemy.exc import OperationalError

from cbpos.i18n import _t

# Map known service error substrings to i18n keys.
# Order matters: more specific patterns should come before generic ones.
_ERROR_MAP = [
    ("already exists", "errors.already_exists"),
    ("not found", "errors.not_found"),
    ("Cannot delete", "errors.cannot_delete_in_use"),
    ("was modified by another user", "errors.concurrent_modification"),
    ("cannot be its own parent", "errors.circular_reference"),
    ("Payment amount must be greater than zero", "errors.payment_amount_zero"),
    ("Customer not found", "errors.customer_not_found"),
    ("OperationalError", "errors.db_connection_lost"),
    ("could not connect to server", "errors.db_connection_lost"),
    ("connection to server was lost", "errors.db_connection_lost"),
    ("server closed the connection", "errors.db_connection_lost"),
    ("connection refused", "errors.db_connection_lost"),
]


def translate_error(error_msg: str | Exception) -> str:
    """Attempt to translate a service error message using i18n keys.

    Checks the error message against known patterns and returns the
    translated version if a match is found. Falls back to the original
    English message if no match or no translation is available.

    Args:
        error_msg: The English error message or Exception instance.

    Returns:
        Translated error message, or the original if no translation found.
    """
    if isinstance(error_msg, OperationalError):
        translated = _t("errors.db_connection_lost")
        if translated != "errors.db_connection_lost":
            return translated

    msg_str = str(error_msg)
    for pattern, key in _ERROR_MAP:
        if pattern in msg_str:
            translated = _t(key)
            if translated != key:  # Translation exists
                return translated
    return msg_str
