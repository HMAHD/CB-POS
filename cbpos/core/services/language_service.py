import logging
import os
from cbpos.config import Config

logger = logging.getLogger(__name__)


class LanguageService:
    """
    Service to manage application translations.
    """

    _translator = None

    # Injected callables to avoid PyQt imports in the service layer
    _install_translator = None  # (translator) -> None
    _remove_translator = None  # (translator) -> None
    _create_translator = None  # () -> translator object

    @classmethod
    def set_translator_handlers(cls, create, install, remove):
        """Inject Qt translator functions to keep service layer free of PyQt imports."""
        cls._create_translator = create
        cls._install_translator = install
        cls._remove_translator = remove

    @classmethod
    def load_language(cls, locale_code: str):
        """
        Loads the translation for the specified locale.

        Args:
            locale_code (str): The locale code (e.g., 'si_LK', 'ta_LK', 'en_US').
        """
        if not cls._create_translator:
            logger.warning("Translator handlers not registered; skipping language load")
            return

        # Remove existing translator if any
        if cls._translator and cls._remove_translator:
            cls._remove_translator(cls._translator)

        # English is the default, so we just remove the translator
        if locale_code.startswith("en"):
            cls._translator = None
            return

        # Load new translator
        cls._translator = cls._create_translator()

        translations_dir = os.path.join(str(Config.BASE_DIR), "cbpos", "ui", "resources", "translations")

        # Extract language code (e.g., 'si' from 'si_LK')
        lang_code = locale_code.split("_")[0] if "_" in locale_code else locale_code

        filename = f"cbpos_{lang_code}.qm"
        path = os.path.join(translations_dir, filename)

        if cls._translator.load(path):
            cls._install_translator(cls._translator)
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
