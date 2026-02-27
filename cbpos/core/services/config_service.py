import base64
import json
import logging
import os
from typing import Dict, Any
from cbpos.config import Config

logger = logging.getLogger(__name__)


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
        "company_tax_id": "",
        "currency_symbol": "Rs.",
        "date_format": "YYYY-MM-DD",
        # Tax Configuration
        "tax_vat_rate": 18.0,
        "tax_sscl_rate": 2.5,
        "tax_sscl_turnover_pct": 50.0,
        "printer_type": "USB",  # USB, NETWORK, MOCK
        "printer_path": "",  # e.g., COM3, 192.168.1.100, or empty for auto-USB
        "language": "en",  # en, si, ta
        "receipt_header": "Welcome to Ceylon Byte",
        "receipt_footer": "Thank You! Come Again.",
        "receipt_logo_path": "",  # Path to logo image
        "show_barcode": True,
        "show_tax_breakdown": True,
        "merge_items": True,  # Merge duplicate items
        # Sales Configuration
        "default_search_mode": "ALL",  # ALL, BARCODE, NAME
        "quick_pay_enabled": True,
        "require_void_reason": True,
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
        "auto_generate_barcodes": True,
        # Feature Flags
        "enable_loyalty": True,
        "enable_touch_mode": True,
        "enable_visual_search": True,
        "auto_select_barcode_match": True,
        # Appearance
        "theme": "Dark",
        "font_size": 12,
        # Document Numbering
        "doc_format_sale": "INV-{Y}-{seq:05d}",
        "doc_format_purchase": "GRN-{Y}-{seq:05d}",
        "doc_format_return": "CN-{Y}-{seq:05d}",
        "doc_reset_period": "YEARLY",
        "show_receipt_dialog": True,
        # Network Database Configuration
        "db_mode": "standalone",  # standalone (SQLite) or network (PostgreSQL)
        "network_db_host": "localhost",
        "network_db_port": 5432,
        "network_db_name": "cbpos",
        "network_db_user": "postgres",
        "network_db_password": "",
        "network_db_sslmode": "prefer",  # disable, allow, prefer, require, verify-full
        # Transaction timeout in seconds (0 = no timeout)
        "db_statement_timeout": 30,
        # System / Security
        "session_timeout_minutes": 0,  # 0 = disabled (no auto-lock), 1-60 = minutes
        "auto_select_barcode_match": True,
        # Terminal Identification
        "terminal_id": "TERM-01",
        # Automation / Email
        "auto_report_enabled": False,
        "auto_report_time": "22:00",
        "admin_email": "",
        "smtp_host": "",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_pass": "",
    }

    _settings: Dict[str, Any] = {}

    # Keys that should be obfuscated (base64-encoded) in the settings file
    _SENSITIVE_KEYS = {"network_db_password", "smtp_pass"}

    @classmethod
    def _encode_sensitive(cls, value: str) -> str:
        """Encode a sensitive value for storage."""
        if not value:
            return ""
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    @classmethod
    def _decode_sensitive(cls, value: str) -> str:
        """Decode a sensitive value from storage."""
        if not value:
            return ""
        try:
            return base64.b64decode(value.encode("ascii")).decode("utf-8")
        except Exception:
            # If decoding fails, treat as plaintext (migration from old format)
            return value

    @classmethod
    def load(cls):
        """Load settings from file, or create with defaults if not exists."""
        if os.path.exists(cls.SETTINGS_FILE):
            try:
                with open(cls.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    cls._settings = json.load(f)
                # Decode sensitive values after loading
                for key in cls._SENSITIVE_KEYS:
                    if key in cls._settings and cls._settings[key]:
                        cls._settings[key] = cls._decode_sensitive(cls._settings[key])
            except Exception as e:
                logger.error("Error loading settings: %s. Using defaults.", e)
                cls._settings = cls.DEFAULTS.copy()
        else:
            cls._settings = cls.DEFAULTS.copy()
            cls.save()

    @classmethod
    def save(cls):
        """Save current settings to file with sensitive values encoded."""
        try:
            # Create a copy with sensitive values encoded
            save_data = cls._settings.copy()
            for key in cls._SENSITIVE_KEYS:
                if key in save_data and save_data[key]:
                    save_data[key] = cls._encode_sensitive(save_data[key])
            with open(cls.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(save_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error("Error saving settings: %s", e)

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
