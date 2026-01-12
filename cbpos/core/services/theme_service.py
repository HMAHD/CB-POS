import os
from PyQt6.QtWidgets import QApplication
from cbpos.infrastructure.resource_loader import ResourceLoader
from cbpos.core.services.config_service import ConfigService


class ThemeService:
    """
    Service to handle application theme switching.
    """

    current_theme = "Dark"

    @staticmethod
    def apply_theme(theme_name: str):
        """
        Applies the specified theme to the application.

        Args:
            theme_name (str): The name of the theme ('Dark' or 'Light').
        """
        ThemeService.current_theme = theme_name
        theme_file = "dark.qss" if theme_name.lower() == "dark" else "light.qss"

        # Resolve path relative to this file
        # cbpos/core/services/theme_service.py -> cbpos/ui/styles/
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        style_path = os.path.join(base_dir, "ui", "styles", theme_file)

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

            app = QApplication.instance()
            if app:
                app.setStyleSheet(style_content)

        except FileNotFoundError:
            print(f"Error: Theme file not found at {style_path}")
        except Exception as e:
            print(f"Error applying theme: {e}")

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
        Returns the path to the logo based on the current theme.
        """
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        if ThemeService.current_theme.lower() == "light":
            return os.path.join(base_dir, "assets", "logo", "cover_black.png")
        else:
            return os.path.join(base_dir, "assets", "logo", "cover_white.png")

    @staticmethod
    def get_icon_color() -> str:
        """
        Returns the icon color based on the current theme.
        """
        if ThemeService.current_theme.lower() == "light":
            return "#333333"
        else:
            return "white"
