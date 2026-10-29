"""Stylesheets as the app applies them: colour tokens, fonts and sizes filled in."""

from pathlib import Path

from cbpos.core.services.theme_service import ThemeService


def rendered_qss(name: str | Path) -> str:
    """Rendered QSS for ``dark.qss`` / ``light.qss`` (or a path ending in one).

    Assert on this, not the raw file: the raw file holds ``{{TOKEN}}`` names.
    """
    return ThemeService.render_stylesheet("Dark" if "dark" in str(name).lower() else "Light")
