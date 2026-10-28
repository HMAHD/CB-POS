"""Tests for t_or helper canonicalization (#698)."""

import cbpos.core.utils.audit_format as af
import cbpos.core.utils.display_labels as dl
from cbpos.i18n import _t, get_language, set_language, t_or


def test_t_or_returns_translation_when_key_exists():
    original = get_language()
    try:
        set_language("en")
        translated = _t("common.save")
        assert translated != "common.save"
        assert t_or("common.save", "Fallback") == translated
    finally:
        set_language(original)


def test_t_or_returns_fallback_when_key_missing():
    assert t_or("missing.key.12345", "Fallback") == "Fallback"


def test_display_labels_uses_canonical_t_or():
    assert dl._t_or is t_or or getattr(dl, "t_or", None) is t_or


def test_audit_format_uses_canonical_t_or():
    assert af._t_or is t_or or getattr(af, "t_or", None) is t_or
