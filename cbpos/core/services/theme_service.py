import os
from PyQt6.QtWidgets import QApplication
from cbpos.infrastructure.resource_loader import ResourceLoader


class ThemeService:
    """
    Service to handle application theme switching.
    """

    @staticmethod
    def apply_theme(theme_name: str):
        """
        Applies the specified theme to the application.

        Args:
            theme_name (str): The name of the theme ('Dark' or 'Light').
        """
        theme_file = "dark.qss" if theme_name.lower() == "dark" else "light.qss"

        # Resolve path relative to this file
        # cbpos/core/services/theme_service.py -> cbpos/ui/styles/
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        style_path = os.path.join(base_dir, "ui", "styles", theme_file)

        try:
            with open(style_path, "r", encoding="utf-8") as f:
                style_content = f.read()

            # Variable Injection
            from cbpos.core.services.config_service import ConfigService

            font_family = ResourceLoader.get_primary_font()
            font_size = str(ConfigService.get("font_size")) + "px"

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
