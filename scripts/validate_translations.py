#!/usr/bin/env python3
"""
Validate translation files for CB-POS i18n system.

Checks:
1. All {param} format parameters in English exist in translated strings
2. No malformed braces (mismatched { and })
3. All language files have the same keys as English
4. Reports summary of translation progress

Usage:
    python scripts/validate_translations.py          # Run all checks
    python scripts/validate_translations.py --strict  # Exit code 1 on any missing params
"""

import json
import re
import sys
from pathlib import Path

I18N_DIR = Path(__file__).parent.parent / "cbpos" / "i18n"
LANGUAGES = ("si", "ta")
PARAM_RE = re.compile(r"\{(\w+)\}")


def flatten(data: dict, prefix: str = "") -> dict:
    """Flatten nested JSON into dot-notation keys."""
    result = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        full_key = f"{prefix}{key}" if prefix else key
        if isinstance(value, dict):
            result.update(flatten(value, f"{full_key}."))
        else:
            result[full_key] = str(value)
    return result


def load_flat(lang_code: str) -> dict:
    """Load and flatten a language file."""
    path = I18N_DIR / f"{lang_code}.json"
    with open(path, encoding="utf-8") as f:
        return flatten(json.load(f))


def check_params(en: dict, lang_code: str, trans: dict) -> list:
    """Find translated strings where format parameters were dropped."""
    issues = []
    for key, en_val in en.items():
        en_params = set(PARAM_RE.findall(en_val))
        if not en_params:
            continue

        if key not in trans:
            continue

        # Skip untranslated (still English) — params are intact
        if trans[key] == en_val:
            continue

        trans_params = set(PARAM_RE.findall(trans[key]))
        missing = en_params - trans_params
        extra = trans_params - en_params

        if missing:
            issues.append(
                {
                    "type": "missing_param",
                    "lang": lang_code,
                    "key": key,
                    "missing": missing,
                    "en": en_val,
                    "translated": trans[key],
                }
            )
        if extra:
            issues.append(
                {
                    "type": "extra_param",
                    "lang": lang_code,
                    "key": key,
                    "extra": extra,
                    "en": en_val,
                    "translated": trans[key],
                }
            )
    return issues


def check_malformed_braces(lang_code: str, trans: dict) -> list:
    """Find strings with mismatched curly braces."""
    issues = []
    for key, val in trans.items():
        if "{" in val or "}" in val:
            opens = val.count("{")
            closes = val.count("}")
            if opens != closes:
                issues.append(
                    {
                        "type": "malformed_braces",
                        "lang": lang_code,
                        "key": key,
                        "value": val,
                        "opens": opens,
                        "closes": closes,
                    }
                )
    return issues


def check_missing_keys(en: dict, lang_code: str, trans: dict) -> list:
    """Find keys present in English but missing in translation file."""
    missing = set(en.keys()) - set(trans.keys())
    return [{"type": "missing_key", "lang": lang_code, "key": k} for k in sorted(missing)]


def check_extra_keys(en: dict, lang_code: str, trans: dict) -> list:
    """Find keys present in translation file but absent in English."""
    extra = set(trans.keys()) - set(en.keys())
    return [{"type": "extra_key", "lang": lang_code, "key": k} for k in sorted(extra)]


def main():
    strict = "--strict" in sys.argv
    en = load_flat("en")
    all_issues = []

    for lang in LANGUAGES:
        trans = load_flat(lang)

        # Check format parameters
        param_issues = check_params(en, lang, trans)
        all_issues.extend(param_issues)

        # Check malformed braces
        brace_issues = check_malformed_braces(lang, trans)
        all_issues.extend(brace_issues)

        # Check missing & extra keys
        key_issues = check_missing_keys(en, lang, trans)
        all_issues.extend(key_issues)
        extra_key_issues = check_extra_keys(en, lang, trans)
        all_issues.extend(extra_key_issues)

        # Translation progress
        translated = sum(1 for k in en if k in trans and trans[k] != en[k])
        untranslated = sum(1 for k in en if k in trans and trans[k] == en[k])
        total = len(en)

        print(f"\n{'=' * 50}")
        print(f"  {lang.upper()} — {translated}/{total} translated ({100 * translated // total}%)")
        print(f"  {untranslated} still English, {len(key_issues)} missing keys, {len(extra_key_issues)} extra keys")
        print(f"{'=' * 50}")

        if key_issues:
            print(f"\n  MISSING KEYS ({len(key_issues)}):")
            for issue in key_issues:
                print(f"    MISSING {issue['key']}")

        if extra_key_issues:
            print(f"\n  EXTRA KEYS ({len(extra_key_issues)}):")
            for issue in extra_key_issues:
                print(f"    EXTRA {issue['key']}")

        if param_issues:
            print(f"\n  FORMAT PARAMETER ISSUES ({len(param_issues)}):")
            for issue in param_issues:
                if issue["type"] == "missing_param":
                    print(f"    MISSING {issue['key']}: {issue['missing']}")
                    print(f"      EN: {issue['en']}")
                    print(f"      {lang.upper()}: {issue['translated']}")
                elif issue["type"] == "extra_param":
                    print(f"    EXTRA {issue['key']}: {issue['extra']}")

        if brace_issues:
            print(f"\n  MALFORMED BRACES ({len(brace_issues)}):")
            for issue in brace_issues:
                opens = issue["opens"]
                closes = issue["closes"]
                print(f"    {issue['key']}: {opens}x open vs {closes}x close")
                print(f"      Value: {issue['value']}")

        if not param_issues and not brace_issues and not key_issues and not extra_key_issues:
            print("\n  All format parameters and keys OK!")

    # Summary
    critical = [i for i in all_issues if i["type"] in ("missing_param", "malformed_braces", "missing_key", "extra_key")]
    print(f"\n{'=' * 50}")
    print(f"  TOTAL: {len(critical)} critical issues")
    print(f"{'=' * 50}")

    if critical and strict:
        print("\n  FAILED (--strict mode): Fix translation issues above.")
        sys.exit(1)
    elif critical:
        print("\n  WARNING: Translation issues found. Run with --strict to fail.")
        sys.exit(0)
    else:
        print("\n  PASSED: All translations valid.")
        sys.exit(0)


if __name__ == "__main__":
    main()
