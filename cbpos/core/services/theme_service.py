import logging
import os
from cbpos.infrastructure.resource_loader import ResourceLoader
from cbpos.core.services.config_service import ConfigService
from cbpos.config import Config

logger = logging.getLogger(__name__)


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
            with open(style_path, "r", encoding="utf-8") as f:
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
                font_size = "12px"  # Safe fallback

            style_content = style_content.replace("{{FONT_FAMILY}}", font_family)
            style_content = style_content.replace("{{FONT_SIZE}}", font_size)

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
    def register_theme_callback(callback):
        """
        Register a callback to be called when theme changes.

        Args:
            callback: A callable that takes no arguments
        """
        if callback not in ThemeService.theme_change_callbacks:
            ThemeService.theme_change_callbacks.append(callback)

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

        return str(Config.BASE_DIR / "cbpos" / "ui" / "assets" / "logo" / logo_file)

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
