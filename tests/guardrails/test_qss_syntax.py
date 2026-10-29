"""
Regression tests for a QSS syntax bug: Qt Style Sheets do not support the
CSS :not() pseudo-class. A `QPushButton:not(#Id):not(#Id2)...` selector
chain is invalid and is silently dropped by Qt's parser, which logs
"Could not parse application stylesheet" the first time any QPushButton is
polished and never applies the rule at all.

Both dark.qss and light.qss had a second, redundant generic button rule
block (base, :hover, :pressed, :disabled) using this invalid selector,
duplicating the real, always-valid generic QPushButton rule near the top
of each file. Since the broken block never actually parsed, deleting it
(rather than converting it to a valid selector) is what makes it a
no-visual-change fix: converting it to valid CSS would have made it start
winning the cascade over the real rule (both being plain-type selectors of
equal specificity, so the later one in the file wins), silently reskinning
every plain button in the app that has no more-specific ID/class rule.
"""

import re
from pathlib import Path

from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtWidgets import QPushButton

STYLES_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"

# Strips /* ... */ comments (which may mention ":not(" in prose explaining
# this very bug) before checking for an actual, live :not(...) selector.
COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(css: str) -> str:
    return COMMENT_RE.sub("", css)


def _load(theme_file: str) -> str:
    """The stylesheet exactly as the app applies it (tokens, fonts and sizes filled in)."""
    from cbpos.core.services.theme_service import ThemeService

    return ThemeService.render_stylesheet("Dark" if theme_file == "dark.qss" else "Light")


class TestNoUnsupportedNotSelector:
    def test_dark_qss_has_no_not_selector(self):
        assert ":not(" not in _strip_comments(_load("dark.qss"))

    def test_light_qss_has_no_not_selector(self):
        assert ":not(" not in _strip_comments(_load("light.qss"))


class TestStylesheetParsesCleanly:
    def _assert_parses_without_warning(self, qapp, theme_file: str):
        messages = []
        qInstallMessageHandler(lambda msg_type, ctx, msg: messages.append((msg_type, msg)))
        try:
            qapp.setStyleSheet(_load(theme_file))
            btn = QPushButton("test")
            btn.show()
            btn.ensurePolished()
        finally:
            qInstallMessageHandler(None)
            qapp.setStyleSheet("")

        parse_warnings = [m for _, m in messages if "parse" in m.lower()]
        assert parse_warnings == [], f"Stylesheet failed to parse: {parse_warnings}"

    def test_dark_qss_parses_without_warning(self, qapp):
        self._assert_parses_without_warning(qapp, "dark.qss")

    def test_light_qss_parses_without_warning(self, qapp):
        self._assert_parses_without_warning(qapp, "light.qss")


class TestGenericButtonRuleUnaffected:
    """The whole point of *deleting* the broken block rather than fixing
    its selector: nothing about how a plain button looks should change."""

    def test_unstyled_button_keeps_the_established_dark_background(self, qapp):
        qapp.setStyleSheet(_load("dark.qss"))
        try:
            btn = QPushButton("test")
            btn.show()
            btn.ensurePolished()
            # #2D2D30 is the one real, always-valid generic QPushButton
            # rule -- the color every plain button has always rendered
            # with, parse bug or no parse bug.
            assert btn.palette().button().color().name() == "#2d2d30"
        finally:
            qapp.setStyleSheet("")

    def test_unstyled_button_keeps_the_established_light_background(self, qapp):
        qapp.setStyleSheet(_load("light.qss"))
        try:
            btn = QPushButton("test")
            btn.show()
            btn.ensurePolished()
            assert btn.palette().button().color().name() == "#ffffff"
        finally:
            qapp.setStyleSheet("")

    def test_excluded_ids_keep_their_own_look(self, qapp):
        """NumpadBtn etc. must keep their own specific look, not the
        generic one -- this is the whole reason the original code reached
        for :not() in the first place. Checks font size (NumpadBtn: 24px)
        rather than background-color, since the generic rule and NumpadBtn
        happen to share the same #2A2A2A background."""
        qapp.setStyleSheet(_load("dark.qss"))
        try:
            btn = QPushButton("7")
            btn.setObjectName("NumpadBtn")
            btn.show()
            btn.ensurePolished()
            assert btn.font().pixelSize() == 24
        finally:
            qapp.setStyleSheet("")
