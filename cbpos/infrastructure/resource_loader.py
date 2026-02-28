"""
Resource Loader for CB POS.

Handles loading of application resources such as fonts, icons, and other assets.
This module provides centralized resource management to ensure fonts are properly
registered with Qt before any UI components are initialized.
"""

import os
from pathlib import Path
from typing import List, Optional
from PyQt6.QtGui import QFontDatabase


class ResourceLoader:
    """
    Centralized resource loader for application assets.

    Provides methods for loading fonts, icons, and other resources
    required by the application. Ensures resources are loaded in the
    correct order and handles errors gracefully.
    """

    _loaded_font_families: List[str] = []
    _primary_font: Optional[str] = None

    @classmethod
    def load_fonts(cls) -> str:
        """
        Recursively load all TrueType and OpenType fonts from the assets directory.

        This method walks through the cbpos/assets/fonts directory tree and registers
        all .ttf and .otf files with Qt's font database. It retrieves the actual
        font family names from Qt and logs them for verification.

        Returns:
            str: The name of the primary font family to use as application default.
                 Prefers "Noto Sans" if found, otherwise returns the first loaded font.
                 Returns "Arial" as fallback if no fonts are loaded.

        Note:
            The returned family name is the EXACT string as registered by Qt,
            which should be used in QSS and QFont constructors.
        """
        # Determine the base directory (project root)
        base_dir = Path(__file__).parent.parent.parent
        fonts_dir = base_dir / "cbpos" / "assets" / "fonts"

        if not fonts_dir.exists():
            print(f"WARNING: Fonts directory not found: {fonts_dir}")
            return "Arial"

        print(f"[ResourceLoader] Loading fonts from: {fonts_dir}")

        loaded_count = 0
        failed_count = 0

        # Walk through the fonts directory recursively
        for root, dirs, files in os.walk(fonts_dir):
            for filename in files:
                if filename.lower().endswith((".ttf", ".otf")):
                    font_path = os.path.join(root, filename)

                    # Register the font with Qt (static method, no instantiation needed)
                    font_id = QFontDatabase.addApplicationFont(str(font_path))

                    if font_id == -1:
                        failed_count += 1
                    else:
                        # Retrieve the actual family name(s) registered (static method)
                        families = QFontDatabase.applicationFontFamilies(font_id)
                        if families:
                            for family_name in families:
                                cls._loaded_font_families.append(family_name)
                            loaded_count += 1

        # Summary logging only
        print(f"[ResourceLoader] Fonts loaded: {loaded_count} files")
        if failed_count > 0:
            print(f"[ResourceLoader] Failed to load: {failed_count} files")

        # Determine the primary font to use
        # Priority: Noto Sans > First loaded > Segoe UI (fallback)
        if "Noto Sans" in cls._loaded_font_families:
            cls._primary_font = "Noto Sans"
        elif cls._loaded_font_families:
            cls._primary_font = cls._loaded_font_families[0]
        else:
            cls._primary_font = "Arial"

        print(f"[ResourceLoader] Primary font: '{cls._primary_font}'")

        return cls._primary_font

    @classmethod
    def get_primary_font(cls) -> str:
        """
        Get the primary font family name.

        Returns:
            str: The name of the primary font family, or "Arial" if not yet loaded.
        """
        return cls._primary_font or "Arial"

    @classmethod
    def get_loaded_families(cls) -> List[str]:
        """
        Get list of all loaded font families.

        Returns:
            List[str]: List of registered font family names.
        """
        return cls._loaded_font_families.copy()
