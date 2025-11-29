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
        "shop_phone": "+94767378901",
        "vat_number": "",
        "printer_type": "USB",  # USB, NETWORK, MOCK
        "printer_path": "",  # e.g., COM3, 192.168.1.100, or empty for auto-USB
        "language": "en",  # en, si, ta
        "receipt_header": "Welcome to Ceylon Byte",
        "receipt_footer": "Thank You! Come Again.",
        # Hardware Configuration
        "receipt_printer_name": "",  # System printer name for thermal receipts
        "a4_printer_name": "",  # System printer name for A4 invoices
        "receipt_copies": 1,  # Number of receipt copies to print
        "paper_width": "80mm",  # 58mm or 80mm
        "auto_print_receipt": True,  # Auto-print receipt after sale
        # Scale Barcode Configuration
        "scale_barcode_prefix": "20",  # Prefix for scale barcodes
        "scale_decimal_places": 3,  # Decimal places for weight
        # Banking Details (for invoices)
        "company_bank_name": "Commercial Bank of Ceylon",
        "company_account_number": "1234567890",
        "company_bank_branch": "Colombo Fort",
        # Inventory Control
        "allow_negative_stock": False,  # Allow overselling
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
