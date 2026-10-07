"""Regression tests for the single app-wide table header style (#554).

Every table used to fork its own QHeaderView::section rule (about four
different looks, some 10px and faint). Each theme now has one generic
rule plus a short list of deliberate exceptions; these checks stop a
per-table header rule from creeping back in.
"""

import re
from pathlib import Path

import pytest

STYLES_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"
THEMES = ("dark.qss", "light.qss")
COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")

GENERIC = "QHeaderView::section"
# Deliberate exceptions: the calendar popup's compact day-name row, and
# row-number headers (an accent underline under every row is noise).
EXCEPTIONS = {"QCalendarWidget QHeaderView::section", "QHeaderView::section:vertical"}


def _rules(theme_file: str) -> list[tuple[list[str], str]]:
    css = COMMENT_RE.sub("", (STYLES_DIR / theme_file).read_text(encoding="utf-8"))
    return [([" ".join(s.split()) for s in sel_list.split(",")], body) for sel_list, body in RULE_RE.findall(css)]


def _props(body: str) -> dict[str, str]:
    props = {}
    for decl in body.split(";"):
        if ":" in decl:
            key, value = decl.split(":", 1)
            props[key.strip()] = value.strip()
    return props


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(fg: str, bg: str) -> float:
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("theme_file", THEMES)
def test_only_generic_header_rule_and_documented_exceptions(theme_file):
    header_selectors = [s for sels, _ in _rules(theme_file) for s in sels if "QHeaderView" in s]
    assert header_selectors.count(GENERIC) == 1
    assert set(header_selectors) - {GENERIC} <= EXCEPTIONS, "per-table header rule found"


@pytest.mark.parametrize("theme_file", THEMES)
def test_generic_header_is_readable(theme_file):
    """At least 12px and WCAG AA (4.5:1) text contrast."""
    [body] = [body for sels, body in _rules(theme_file) if GENERIC in sels]
    props = _props(body)
    assert int(props["font-size"].removesuffix("px")) >= 12
    assert _contrast(props["color"], props["background-color"]) >= 4.5
    assert "text-transform" not in props
