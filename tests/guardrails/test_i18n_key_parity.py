"""Guardrail test ensuring i18n key and parameter parity across en, si, and ta.

Enforces that:
1. Every translation key in en.json exists in si.json and ta.json (no missing keys).
2. No extraneous keys exist in si.json or ta.json (no orphan keys).
3. Every {param} format parameter in en.json exists identically in si and ta strings.
4. No malformed braces ({ or }) exist in any translation string.
"""

from scripts.validate_translations import (
    check_malformed_braces,
    check_params,
    load_flat,
)


def test_i18n_key_parity():
    """Verify en, si, and ta have identical key sets, parameters, and valid braces."""
    en = load_flat("en")
    si = load_flat("si")
    ta = load_flat("ta")

    # 1. Key set equality
    en_keys = set(en.keys())
    si_keys = set(si.keys())
    ta_keys = set(ta.keys())

    missing_in_si = en_keys - si_keys
    extra_in_si = si_keys - en_keys
    assert not missing_in_si, f"Keys in en.json missing from si.json: {sorted(missing_in_si)}"
    assert not extra_in_si, f"Keys in si.json not present in en.json: {sorted(extra_in_si)}"

    missing_in_ta = en_keys - ta_keys
    extra_in_ta = ta_keys - en_keys
    assert not missing_in_ta, f"Keys in en.json missing from ta.json: {sorted(missing_in_ta)}"
    assert not extra_in_ta, f"Keys in ta.json not present in en.json: {sorted(extra_in_ta)}"

    # 2. Format parameters parity
    for lang, trans in [("si", si), ("ta", ta)]:
        param_issues = check_params(en, lang, trans)
        assert not param_issues, f"Format parameter issues in {lang.upper()}: {param_issues}"

    # 3. No malformed braces
    for lang, trans in [("en", en), ("si", si), ("ta", ta)]:
        brace_issues = check_malformed_braces(lang, trans)
        assert not brace_issues, f"Malformed braces in {lang.upper()}: {brace_issues}"
