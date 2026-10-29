"""Colour tokens: the only place theme colours are defined (D20).

``dark.qss`` and ``light.qss`` refer to colours as ``{{TOKEN}}`` placeholders;
``ThemeService`` substitutes them from the active theme's table below. To
change a colour everywhere, change it here.

Roles:
    SURFACE_0..3   app background → panels → raised controls → hover
    BORDER(_STRONG) hairlines and input borders
    TEXT…          primary, soft, secondary, disabled; ON_ACCENT is text on
                   a filled accent/semantic button
    ACCENT…        primary actions, focus, links, selection
    SUCCESS/WARNING/DANGER (+ _BG tints) only for status and money meaning
"""

THEME_TOKENS: dict[str, dict[str, str]] = {
    "Dark": {
        "SURFACE_0": "#1E1E1E",
        "SURFACE_1": "#252526",
        "SURFACE_2": "#2D2D30",
        "SURFACE_3": "#333333",
        "BORDER": "#3E3E42",
        "BORDER_STRONG": "#555555",
        "TEXT": "#FFFFFF",
        "TEXT_SOFT": "#E0E0E0",
        "TEXT_SECONDARY": "#AAAAAA",
        "TEXT_DISABLED": "#6E6E6E",
        "ON_ACCENT": "#001F3F",
        "ACCENT": "#00BCEB",
        "ACCENT_HOVER": "#33CCF2",
        "SELECTION": "#003366",
        "ACCENT_BG": "#0E3A47",
        "SUCCESS": "#39FF14",
        "SUCCESS_BG": "#163A12",
        "WARNING": "#FFDC00",
        "WARNING_BG": "#3D3510",
        "DANGER": "#FF4136",
        "DANGER_BG": "#3D1A18",
    },
    "Light": {
        "SURFACE_0": "#F8F9FA",
        "SURFACE_1": "#FFFFFF",
        "SURFACE_2": "#E9ECEF",
        "SURFACE_3": "#DEE2E6",
        "BORDER": "#DEE2E6",
        "BORDER_STRONG": "#CED4DA",
        "TEXT": "#212529",
        "TEXT_SOFT": "#495057",
        "TEXT_SECONDARY": "#6C757D",
        "TEXT_DISABLED": "#ADB5BD",
        "ON_ACCENT": "#FFFFFF",
        "ACCENT": "#0D6EFD",
        "ACCENT_HOVER": "#0B5ED7",
        "SELECTION": "#CFE2FF",
        "ACCENT_BG": "#E7F1FF",
        "SUCCESS": "#198754",
        "SUCCESS_BG": "#D1E7DD",
        "WARNING": "#B58105",
        "WARNING_BG": "#FFF3CD",
        "DANGER": "#DC3545",
        "DANGER_BG": "#F8D7DA",
    },
}


def apply_tokens(style: str, theme: str) -> str:
    """Replace every ``{{TOKEN}}`` in *style* with the active theme's colour."""
    tokens = THEME_TOKENS.get(theme, THEME_TOKENS["Dark"])
    for name, value in tokens.items():
        style = style.replace("{{" + name + "}}", value)
    return style
