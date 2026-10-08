"""Theme-aware semantic colours for status, variance and price text (#559).

Colours set from Python (``setForeground``, model ``ForegroundRole``) are
not reachable from QSS, so they used to be dark-theme neon values used in
both themes -- ``#39FF14`` on white is about 1.4:1. Every such colour now
comes from here, picked by *meaning*, with one value per theme.

Each value is at least 4.5:1 (WCAG AA, normal text) against its theme's
table background, alternate row, light-theme selected row and the pill
fill below (verified in tests/unit/test_status_colors.py). Dark-theme
selected rows don't need it: dark.qss paints selected text white.
"""

from PyQt6.QtGui import QColor

from cbpos.core.services.theme_service import ThemeService

SUCCESS = "success"  # completed, active, surplus, paid
DANGER = "danger"  # void, shortage, overdue, error
WARNING = "warning"  # suspended, near a limit, warning log
INFO = "info"  # quote, upcoming
NEUTRAL = "neutral"  # draft, expired, inactive, zero

# meaning -> (dark theme, light theme)
PALETTE: dict[str, tuple[str, str]] = {
    SUCCESS: ("#39FF14", "#146C43"),
    DANGER: ("#FF8080", "#B02A37"),
    WARNING: ("#E5C07B", "#8A5A00"),
    INFO: ("#4FC3F7", "#0A58CA"),
    NEUTRAL: ("#AAAAAA", "#5C636A"),
}

# Table surface each theme's pills are tinted against (dark.qss/light.qss).
SURFACE = {"dark": "#252526", "light": "#FFFFFF"}
# How much of the status colour a pill's fill takes; the rest is surface.
PILL_TINT = 0.15


def is_light_theme() -> bool:
    """True when the Light theme is active."""
    return ThemeService.current_theme.lower() == "light"


def status_hex(meaning: str) -> str:
    """Hex colour for a meaning in the current theme (unknown meaning -> neutral)."""
    dark, light = PALETTE.get(meaning, PALETTE[NEUTRAL])
    return light if is_light_theme() else dark


def status_color(meaning: str) -> QColor:
    """QColor for a meaning in the current theme: success/danger/warning/info/neutral."""
    return QColor(status_hex(meaning))


def pill_colors(meaning: str) -> tuple[QColor, QColor]:
    """(text, fill) for a status pill: the status colour on an opaque tint of it.

    The fill is opaque, so the pill reads the same on any row -- plain,
    alternate or selected.
    """
    text = status_color(meaning)
    surface = QColor(SURFACE["light" if is_light_theme() else "dark"])
    fill = QColor(
        *(
            round(c * PILL_TINT + s * (1 - PILL_TINT))
            for c, s in zip(text.getRgb()[:3], surface.getRgb()[:3], strict=True)
        )
    )
    return text, fill
