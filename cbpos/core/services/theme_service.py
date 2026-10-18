import logging
import os
import re

from cbpos.config import Config
from cbpos.core.services.config_service import ConfigService
from cbpos.infrastructure.resource_loader import ResourceLoader

logger = logging.getLogger(__name__)

BASE_FONT_SIZE = 12  # the size every fixed px font-size in the QSS was designed at
MIN_FONT_SIZE = 8
_PX_FONT_SIZE_RE = re.compile(r"(font-size\s*:\s*)(\d+(?:\.\d+)?)px")


class ThemeService:
    """
    Service to handle application theme switching.
    Single Source of Truth for theme-dependent assets (logos, icon colors).
    """

    current_theme = "Dark"
    theme_change_callbacks = []  # List of callbacks to call when theme changes

    # Injected callable: set_stylesheet(css_string) -> None
    _set_stylesheet = None

    @classmethod
    def set_stylesheet_handler(cls, handler):
        """Inject the function used to apply stylesheets (avoids PyQt import in service)."""
        cls._set_stylesheet = handler

    @staticmethod
    def apply_theme(theme_name: str):
        """
        Applies the specified theme to the application.

        Args:
            theme_name (str): The name of the theme ('Dark' or 'Light').
        """
        ThemeService.current_theme = theme_name
        theme_file = "dark.qss" if theme_name.lower() == "dark" else "light.qss"

        style_path = os.path.join(str(Config.BASE_DIR), "cbpos", "ui", "styles", theme_file)

        try:
            with open(style_path, encoding="utf-8") as f:
                style_content = f.read()

            # Variable Injection
            font_family = ResourceLoader.get_primary_font()
            raw_size = ConfigService.get("font_size")

            # Security: Validate font_size to prevent CSS injection
            try:
                font_size_int = int(str(raw_size))
                if not (8 <= font_size_int <= 36):
                    raise ValueError("Font size out of bounds")
                font_size = f"{font_size_int}px"
            except (ValueError, TypeError):
                font_size_int = BASE_FONT_SIZE
                font_size = "12px"  # Safe fallback

            # Scale every fixed px font-size by the setting (#572) *before*
            # {{FONT_SIZE}} is substituted, so the base size isn't scaled twice.
            style_content = ThemeService.scale_font_sizes(style_content, font_size_int)

            # Resolve asset paths for icons (works in dev and packaged exe)
            assets_path = os.path.join(str(Config.BASE_DIR), "cbpos", "assets").replace("\\", "/")
            style_content = style_content.replace("url(cbpos/assets/", f"url({assets_path}/")

            style_content = style_content.replace("{{FONT_FAMILY}}", font_family)
            style_content = style_content.replace("{{FONT_SIZE}}", font_size)

            # A leftover "{{...}}" placeholder (a typo'd token, an unhandled
            # variable, anything the two replace() calls above didn't match)
            # is invalid CSS that Qt silently ignores, falling back to the
            # system default font for the *entire app*. A regex catch-all
            # guarantees no such token ever reaches the stylesheet, whatever
            # its exact contents — re-running the same two replace() calls
            # again would not help, since if they didn't match the first
            # time they won't match the second.
            if "{{" in style_content:
                logger.error(
                    "Unsubstituted template placeholder remained in %s after variable "
                    "injection — forcing safe fallback font-size.",
                    theme_file,
                )
                style_content = re.sub(r"\{\{[^}]*\}\}", "14px", style_content)

            if ThemeService._set_stylesheet:
                ThemeService._set_stylesheet(style_content)
            else:
                logger.warning("No stylesheet handler registered; theme not applied to UI")

            # Notify all registered callbacks that theme has changed
            for callback in ThemeService.theme_change_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error("Error in theme change callback: %s", e)

        except FileNotFoundError:
            logger.error("Theme file not found at %s", style_path)
        except Exception as e:
            logger.error("Error applying theme: %s", e)

    @staticmethod
    def scale_font_sizes(style_content: str, font_size: int) -> str:
        """Scale every ``font-size: Npx`` in a stylesheet by ``font_size / 12``.

        The QSS hardcodes its px sizes for the default 12px base, so without
        this the Font Size setting only reached unstyled widgets (#572).
        Results are rounded to the nearest px and never go below 8px.

        Args:
            style_content: Raw QSS text.
            font_size: The configured base font size in px.

        Returns:
            str: The QSS with every px font-size scaled (unchanged at 12).
        """
        if font_size == BASE_FONT_SIZE:
            return style_content

        def _scale(match: re.Match) -> str:
            scaled = int(float(match.group(2)) * font_size / BASE_FONT_SIZE + 0.5)
            return f"{match.group(1)}{max(scaled, MIN_FONT_SIZE)}px"

        return _PX_FONT_SIZE_RE.sub(_scale, style_content)

    @staticmethod
    def register_theme_callback(callback):
        """
        Register a callback to be called when theme changes.

        Args:
            callback: A callable that takes no arguments
        """
        if callback not in ThemeService.theme_change_callbacks:
            ThemeService.theme_change_callbacks.append(callback)

    @staticmethod
    def unregister_theme_callback(callback):
        """
        Remove a callback registered with ``register_theme_callback``.

        Args:
            callback: The callable to remove; ignored if not registered.
        """
        if callback in ThemeService.theme_change_callbacks:
            ThemeService.theme_change_callbacks.remove(callback)

    @staticmethod
    def get_available_themes() -> list:
        """
        Returns a list of available themes.

        Returns:
            list: List of theme names.
        """
        return ["Dark", "Light"]

    @staticmethod
    def get_logo_path() -> str:
        """
        Returns the correct logo file path based on the current theme.

        LOGO LOGIC:
        - Dark Theme → White Text Logo (visible on dark backgrounds)
        - Light Theme → Black Text Logo (visible on light backgrounds)

        Returns:
            str: Absolute path to the appropriate logo file
        """
        # Use current_theme as the single source of truth
        if ThemeService.current_theme.lower() == "light":
            # Light theme needs BLACK text logo
            logo_file = "cover_black.png"
        else:
            # Dark theme (default) needs WHITE text logo
            logo_file = "cover_white.png"

        return str(Config.BASE_DIR / "cbpos" / "assets" / "logo" / logo_file)

    @staticmethod
    def get_collapsed_logo_path() -> str:
        """Returns the correct collapsed icon logo file path based on the current theme.

        - Light Theme → 01.png
        - Dark Theme → 02.png

        Returns:
            str: Absolute path to the appropriate collapsed logo file
        """
        if ThemeService.current_theme.lower() == "light":
            logo_file = "01.png"
        else:
            logo_file = "02.png"

        return str(Config.BASE_DIR / "cbpos" / "assets" / "logo" / logo_file)

    @staticmethod
    def get_icon_color() -> str:
        """
        Returns the hex color string for icons based on the current theme.

        ICON LOGIC:
        - Dark Theme → White Icons (visible on dark backgrounds)
        - Light Theme → Black Icons (visible on light backgrounds)

        Returns:
            str: Color string ("white", "black", or hex code)
        """
        if ThemeService.current_theme.lower() == "light":
            # Light theme needs BLACK icons
            return "black"  # Pure black for maximum contrast
        else:
            # Dark theme needs WHITE icons
            return "white"  # Strict white for Dark Mode

    @staticmethod
    def get_accent_color() -> str:
        """
        Returns the hex color string for the current theme's accent color.

        Matches the ``:checked``/``[active="true"]`` QSS accent already
        used for active-state text and borders (dark.qss/light.qss), so
        Python-side icon recoloring (e.g. a sidebar item's active icon
        glyph) stays in sync with the stylesheet instead of hardcoding
        its own copy of the accent value.

        Returns:
            str: Hex color string.
        """
        if ThemeService.current_theme.lower() == "light":
            return "#0D6EFD"
        else:
            return "#00BCEB"
