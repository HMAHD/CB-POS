import logging
import os
from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QApplication
from cbpos.config import Config

logger = logging.getLogger(__name__)


class LanguageService:
    """
    Service to manage application translations.
    """

    _translator = None

    @classmethod
    def load_language(cls, locale_code: str):
        """
        Loads the translation for the specified locale.

        Args:
            locale_code (str): The locale code (e.g., 'si_LK', 'ta_LK', 'en_US').
        """
        app = QApplication.instance()
        if not app:
            return

        # Remove existing translator if any
        if cls._translator:
            app.removeTranslator(cls._translator)

        # English is the default, so we just remove the translator
        if locale_code.startswith("en"):
            cls._translator = None
            return

        # Load new translator
        cls._translator = QTranslator()

        translations_dir = os.path.join(str(Config.BASE_DIR), "cbpos", "ui", "resources", "translations")

        # Extract language code (e.g., 'si' from 'si_LK')
        lang_code = locale_code.split("_")[0] if "_" in locale_code else locale_code

        filename = f"cbpos_{lang_code}.qm"
        path = os.path.join(translations_dir, filename)

        if cls._translator.load(path):
            app.installTranslator(cls._translator)
        else:
            logger.warning("Could not load translation file: %s", path)

    @staticmethod
    def get_available_languages() -> dict:
        """
        Returns available languages.

        Returns:
            dict: Dictionary of language codes and names.
        """
        return {"en": "English", "si": "Sinhala", "ta": "Tamil"}
