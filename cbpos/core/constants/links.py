"""Canonical Web and Documentation Links for CB POS.

Single source of truth for external URLs, localized link generation,
and safe external browser navigation via QDesktopServices.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from cbpos.config import Config
from cbpos.i18n import _t

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES: tuple[str, ...] = ("en", "si", "ta")
DEFAULT_LOCALE: str = "en"

# URL Templates (fixed HTTPS targets only)
WEBSITE_URL_TEMPLATE: str = "https://ceybyte.com/{lang}/"
DOCS_URL_TEMPLATE: str = "https://ceybyte.com/{lang}/docs/"
REPORT_BUG_URL_TEMPLATE: str = "https://ceybyte.com/{lang}/feedback/?type=bug"
SUGGEST_FEATURE_URL_TEMPLATE: str = "https://ceybyte.com/{lang}/feedback/?type=feature"
PRIVACY_URL_TEMPLATE: str = "https://ceybyte.com/{lang}/legal/privacy/"
TERMS_URL_TEMPLATE: str = "https://ceybyte.com/{lang}/legal/terms/"
SOURCE_URL_TEMPLATE: str = "https://github.com/HMAHD/CB-POS/tree/v{version}"
SOURCE_REPO_URL: str = "https://github.com/HMAHD/CB-POS"
RELEASES_ISSUES_URL: str = "https://github.com/ceybyte/cbpos-releases/issues"


def resolve_locale(locale: str | None = None) -> str:
    """Resolve locale to one of ('en', 'si', 'ta'), falling back to 'en'.

    If locale is None, attempts to inspect the active translation service language.
    """
    if locale is None:
        try:
            from cbpos.i18n import get_current_language

            lang = get_current_language()
            if lang and str(lang).lower() in SUPPORTED_LOCALES:
                return str(lang).lower()
        except Exception:
            pass
        return DEFAULT_LOCALE

    norm = str(locale).strip().lower()
    if norm in SUPPORTED_LOCALES:
        return norm
    return DEFAULT_LOCALE


def get_website_url(locale: str | None = None) -> str:
    """Return canonical CeyByte website URL for locale."""
    lang = resolve_locale(locale)
    return WEBSITE_URL_TEMPLATE.format(lang=lang)


def get_docs_url(locale: str | None = None) -> str:
    """Return canonical User Guide documentation URL for locale."""
    lang = resolve_locale(locale)
    return DOCS_URL_TEMPLATE.format(lang=lang)


def get_report_bug_url(locale: str | None = None) -> str:
    """Return canonical Report a Problem feedback URL with fixed routing parameter."""
    lang = resolve_locale(locale)
    return REPORT_BUG_URL_TEMPLATE.format(lang=lang)


def get_suggest_feature_url(locale: str | None = None) -> str:
    """Return canonical Suggest a Feature feedback URL with fixed routing parameter."""
    lang = resolve_locale(locale)
    return SUGGEST_FEATURE_URL_TEMPLATE.format(lang=lang)


def get_privacy_url(locale: str | None = None) -> str:
    """Return canonical Website Privacy policy URL for locale."""
    lang = resolve_locale(locale)
    return PRIVACY_URL_TEMPLATE.format(lang=lang)


def get_terms_url(locale: str | None = None) -> str:
    """Return canonical Website Terms of Service URL for locale."""
    lang = resolve_locale(locale)
    return TERMS_URL_TEMPLATE.format(lang=lang)


def get_source_url(version: str | None = None) -> str:
    """Return durable GitHub source repository URL pinned to the exact release version tag.

    If version is not provided, defaults to Config.VERSION.
    """
    ver = (version or Config.VERSION or "").strip()
    if ver:
        return SOURCE_URL_TEMPLATE.format(version=ver)
    return SOURCE_REPO_URL


def open_external_url(url: str, parent: QWidget | None = None) -> bool:
    """Safely open an external HTTPS URL in the user's default desktop web browser.

    Shows a localized fallback dialog with the copyable URL if opening fails.
    Returns True if successfully launched, False otherwise.
    """
    if not url.startswith("https://"):
        raise ValueError(f"Only HTTPS URLs are permitted, got: {url!r}")

    try:
        opened = QDesktopServices.openUrl(QUrl(url))
    except Exception as exc:
        logger.warning("Exception launching external URL %s: %s", url, exc)
        opened = False

    if not opened:
        logger.warning("Could not launch browser for URL: %s", url)
        _show_url_fallback_dialog(url, parent)
        return False

    return True


def _show_url_fallback_dialog(url: str, parent: QWidget | None = None) -> None:
    """Display an informative fallback dialog allowing the user to copy the URL."""
    box = QMessageBox(parent)
    box.setObjectName("OpenUrlFailedDialog")
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(_t("about.title"))
    box.setText(_t("about.open_url_failed", url=url))

    btn_copy = box.addButton(_t("common.copy"), QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Close)

    box.exec()

    if box.clickedButton() == btn_copy:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(url)
