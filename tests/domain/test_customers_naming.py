"""Tests for issue #610 (UI-041): Rename user-facing Credit Book to Customers."""

from cbpos.i18n import _t, set_language


def test_customer_module_labels_in_all_languages():
    """Verify navigation label and page title say 'Customers' in en, si, and ta."""
    expected = {
        "en": "Customers",
        "si": "පාරිභෝගිකයන්",
        "ta": "வாடிக்கையாளர்கள்",
    }

    try:
        for lang, expected_text in expected.items():
            set_language(lang)
            assert _t("management.sidebar_credit_book") == expected_text, (
                f"Expected sidebar_credit_book in {lang} to be {expected_text!r}, got {_t('management.sidebar_credit_book')!r}"
            )
            assert _t("credit_book.title") == expected_text, (
                f"Expected credit_book.title in {lang} to be {expected_text!r}, got {_t('credit_book.title')!r}"
            )
    finally:
        set_language("en")
