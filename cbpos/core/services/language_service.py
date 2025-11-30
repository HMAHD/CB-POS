import os
from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QApplication


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

        # Path to translations: cbpos/ui/resources/translations/
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        translations_dir = os.path.join(base_dir, "ui", "resources", "translations")

        # Extract language code (e.g., 'si' from 'si_LK')
        lang_code = locale_code.split("_")[0] if "_" in locale_code else locale_code

        filename = f"cbpos_{lang_code}.qm"
        path = os.path.join(translations_dir, filename)

        if cls._translator.load(path):
            app.installTranslator(cls._translator)
        else:
            print(f"Warning: Could not load translation file: {path}")

    @staticmethod
    def get_available_languages() -> dict:
        """
        Returns available languages.

        Returns:
            dict: Dictionary of language codes and names.
        """
        return {"en": "English", "si": "Sinhala", "ta": "Tamil"}
