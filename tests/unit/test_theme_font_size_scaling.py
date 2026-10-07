"""
The Font Size setting only reached the base ``{{FONT_SIZE}}`` QWidget rule;
the ~220 fixed ``font-size: Npx`` rules in each QSS ignored it (#572).
ThemeService must now scale every px font-size by ``setting / 12`` when it
builds the stylesheet, leaving the stylesheet untouched at the default 12.
"""

import re
from pathlib import Path

import pytest

from cbpos.config import Config
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.theme_service import ThemeService

PX_RE = re.compile(r"font-size\s*:\s*(\d+)px")


def _raw_qss(theme: str) -> str:
    name = "dark.qss" if theme == "Dark" else "light.qss"
    return (Path(Config.BASE_DIR) / "cbpos" / "ui" / "styles" / name).read_text(encoding="utf-8")


@pytest.fixture
def build_stylesheet(monkeypatch):
    """Return a function building the theme's stylesheet at a given font size."""
    saved_theme = ThemeService.current_theme
    saved_handler = ThemeService._set_stylesheet
    saved_callbacks = ThemeService.theme_change_callbacks
    ThemeService.theme_change_callbacks = []

    def _build(theme: str, font_size: int) -> str:
        captured: list[str] = []
        monkeypatch.setattr(ConfigService, "get", lambda key: font_size if key == "font_size" else None)
        ThemeService.set_stylesheet_handler(captured.append)
        ThemeService.apply_theme(theme)
        return captured[-1]

    yield _build
    ThemeService.current_theme = saved_theme
    ThemeService._set_stylesheet = saved_handler
    ThemeService.theme_change_callbacks = saved_callbacks


@pytest.mark.parametrize("theme", ["Dark", "Light"])
def test_size_18_scales_every_px_font_size_by_one_and_a_half(build_stylesheet, theme):
    qss = _raw_qss(theme)
    raw = PX_RE.findall(qss)
    scaled = PX_RE.findall(build_stylesheet(theme, 18))

    # dark.qss's {{FONT_SIZE}} base rule becomes one extra px rule (18px)
    token = [18] if "{{FONT_SIZE}}" in qss else []
    assert len(raw) > 200
    expected = sorted([max(int(int(n) * 1.5 + 0.5), 8) for n in raw] + token)
    assert sorted(int(n) for n in scaled) == expected


@pytest.mark.parametrize("theme", ["Dark", "Light"])
def test_size_12_leaves_every_px_font_size_unchanged(build_stylesheet, theme):
    qss = _raw_qss(theme)
    raw = PX_RE.findall(qss)
    built = PX_RE.findall(build_stylesheet(theme, 12))
    token = [12] if "{{FONT_SIZE}}" in qss else []
    assert sorted(int(n) for n in built) == sorted([int(n) for n in raw] + token)
    assert "{{" not in build_stylesheet(theme, 12)


def test_scaled_sizes_round_and_never_drop_below_8px():
    css = "QLabel { font-size: 9px; } QPushButton { font-size:13px; } QLabel#x { font-size: 7pt; }"
    out = ThemeService.scale_font_sizes(css, 8)
    # 9 * 8/12 = 6 -> clamped to 8; 13 * 8/12 = 8.67 -> 9; pt untouched
    assert "font-size: 8px" in out
    assert "font-size:9px" in out
    assert "font-size: 7pt" in out
