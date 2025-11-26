import json
import os
from typing import Dict, Any
from cbpos.config import Config


class ConfigService:
    """
    Service to manage persistent application settings.
    Stores settings in a 'settings.json' file in the project root.
    """

    SETTINGS_FILE = os.path.join(Config.BASE_DIR, "settings.json")

    DEFAULTS = {
        "shop_name": "Ceylon Byte POS",
        "shop_address": "123, Tech Street, Colombo",
        "shop_phone": "+94 77 123 4567",
        "vat_number": "",
        "printer_type": "USB",  # USB, NETWORK, MOCK
        "printer_path": "",  # e.g., COM3, 192.168.1.100, or empty for auto-USB
        "language": "en",  # en, si, ta
        "receipt_header": "Welcome to Ceylon Byte",
        "receipt_footer": "Thank You! Come Again.",
    }

    _settings: Dict[str, Any] = {}

    @classmethod
    def load(cls):
        """Load settings from file, or create with defaults if not exists."""
        if os.path.exists(cls.SETTINGS_FILE):
            try:
                with open(cls.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    cls._settings = json.load(f)
            except Exception as e:
                print(f"Error loading settings: {e}. Using defaults.")
                cls._settings = cls.DEFAULTS.copy()
        else:
            cls._settings = cls.DEFAULTS.copy()
            cls.save()

    @classmethod
    def save(cls):
        """Save current settings to file."""
        try:
            with open(cls.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(cls._settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving settings: {e}")

    @classmethod
    def get(cls, key: str) -> Any:
        """Get a setting value."""
        if not cls._settings:
            cls.load()
        return cls._settings.get(key, cls.DEFAULTS.get(key))

    @classmethod
    def set(cls, key: str, value: Any):
        """Set a setting value and save."""
        if not cls._settings:
            cls.load()
        cls._settings[key] = value
        cls.save()

    @classmethod
    def get_all(cls) -> Dict[str, Any]:
        """Get all settings."""
        if not cls._settings:
            cls.load()
        return cls._settings.copy()

    @classmethod
    def update_all(cls, data: Dict[str, Any]):
        """Update multiple settings at once."""
        if not cls._settings:
            cls.load()
        cls._settings.update(data)
        cls.save()
