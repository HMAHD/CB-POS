"""Theme colours come only from cbpos/ui/styles/tokens.py (D20).

The QSS files may reference colours only as {{TOKEN}}; hex values inside
attribute selectors (e.g. [btnColor="#FFDC00"]) match values set in code
and are allowed.
"""

import re
from pathlib import Path

from cbpos.ui.styles.tokens import THEME_TOKENS

STYLES = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"
_NON_COLOUR_PLACEHOLDERS = {"FONT_FAMILY", "FONT_SIZE"}


def _declarations(name: str) -> str:
    text = (STYLES / name).read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"\[[^\]]*\]", "", text)  # attribute selectors


def test_qss_has_no_raw_hex_colours():
    for name in ("dark.qss", "light.qss"):
        assert re.findall(r"#[0-9A-Fa-f]{3,8}\b", _declarations(name)) == [], f"{name}: use a {{{{TOKEN}}}}"


def test_every_placeholder_is_a_defined_token():
    for name in ("dark.qss", "light.qss"):
        used = set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", (STYLES / name).read_text(encoding="utf-8")))
        unknown = used - _NON_COLOUR_PLACEHOLDERS - set(THEME_TOKENS["Dark"])
        assert unknown == set(), f"{name} uses undefined tokens: {sorted(unknown)}"


def test_both_themes_define_the_same_tokens():
    assert set(THEME_TOKENS["Dark"]) == set(THEME_TOKENS["Light"])


def test_token_values_are_hex_colours():
    for theme, tokens in THEME_TOKENS.items():
        for name, value in tokens.items():
            assert re.fullmatch(r"#[0-9A-F]{6}", value), f"{theme}.{name} = {value!r}"
