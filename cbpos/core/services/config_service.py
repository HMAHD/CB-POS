import base64
import hashlib
import json
import logging
import os
import platform
import stat
from typing import Dict, Any

from cryptography.fernet import Fernet, InvalidToken

from cbpos.config import Config

logger = logging.getLogger(__name__)


class ConfigService:
    """
    Service to manage persistent application settings.
    Stores settings in a 'settings.json' file located in the application
    data directory (Config.DATA_DIR).
    """

    SETTINGS_FILE = os.path.join(Config.DATA_DIR, "settings.json")

    DEFAULTS = {
        "shop_name": "Ceylon Byte POS",
        "shop_address": "123, Tech Street, Colombo",
        "shop_phone": "+94767378901",
        "vat_number": "",
        "company_tax_id": "",
        "currency_symbol": "Rs.",
        "date_format": "YYYY-MM-DD",
        # Tax Configuration
        "vat_registered": False,  # Whether business is VAT-registered
        "tax_vat_rate": 18.0,
        "tax_sscl_rate": 2.5,
        "tax_sscl_turnover_pct": 50.0,
        "printer_type": "NONE",  # USB, NETWORK, or NONE
        "printer_path": "",  # e.g., COM3, 192.168.1.100, or empty for auto-USB
        "language": "en",  # en, si, ta
        "receipt_header": "Welcome to Ceylon Byte",
        "receipt_footer": "Thank You! Come Again.",
        "receipt_logo_path": "",  # Path to logo image
        "show_barcode": False,
        "show_tax_breakdown": False,
        "merge_items": False,  # Merge duplicate items on receipt
        # Sales Configuration
        "default_search_mode": "ALL",  # ALL, BARCODE, NAME
        "quick_pay_enabled": True,
        "require_void_reason": True,
        "max_discount_percent": 15.0,
        # Hardware Configuration
        "receipt_printer_name": "",  # System printer name for thermal receipts
        "a4_printer_name": "",  # System printer name for A4 invoices
        "receipt_copies": 1,  # Number of receipt copies to print
        "paper_width": "80mm",  # 58mm or 80mm
        "auto_print_receipt": True,  # Auto-print receipt after sale
        "auto_cut_paper": True,  # Disable for tear-bar printers
        "cut_type": "partial",  # "full" or "partial"
        "feed_lines_before_cut": 3,  # 1-8 lines feed before cut
        "drawer_on_cash_only": True,  # Only kick drawer for cash payments
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
        "enable_sounds": True,
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
        "show_receipt_dialog": False,
        "show_cashier_on_receipt": False,
        "show_terminal_on_receipt": False,
        "show_qr_on_receipt": False,
        "receipt_qr_content": "",  # Shop WhatsApp/website URL for QR
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
        "max_login_attempts": 5,  # Failed attempts before lockout
        "lockout_duration_seconds": 300,  # Lockout duration in seconds (5 min default)
        # Customer Defaults
        "default_credit_limit": 0,  # Default credit limit for new customers (0 = no credit)
        "loyalty_points_ratio": 100,  # Spend this much to earn 1 loyalty point
        "auto_select_barcode_match": True,
        # Terminal Identification
        "terminal_id": "TERM-01",
        # Multi-Terminal LAN Sync
        "terminal_mode": "standalone",  # standalone, main, or terminal
        "sync_server_port": 5555,  # Port for sync server (Main PC)
        "main_pc_address": "",  # IP:port of Main PC (Terminal mode)
        "sync_interval_seconds": 3,  # How often terminals push/pull (seconds)
        # Automation / Email
        "auto_report_enabled": False,
        "auto_report_time": "22:00",
        "admin_email": "",
        "smtp_host": "",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_pass": "",
        # Data Safety / Backup
        "auto_backup_on_close": True,
        "backup_retention_count": 5,
        "backup_dir": "",
        # UI Preferences
        "sidebar_collapsed": False,
    }

    _settings: Dict[str, Any] = {}

    # Keys that are per-terminal in network mode.  When ``db_mode`` is
    # ``"network"`` these are stored under a terminal-prefixed key
    # (e.g. ``"TERM-01.printer_type"``) so each terminal can have its
    # own printer, language, theme, etc. without overwriting other terminals.
    _PER_TERMINAL_KEYS = frozenset(
        {
            "printer_type",
            "printer_path",
            "receipt_printer_name",
            "a4_printer_name",
            "language",
            "theme",
            "enable_sounds",
            "enable_touch_mode",
            "sidebar_collapsed",
            "terminal_mode",
            "main_pc_address",
        }
    )

    # Keys that should be encrypted in the settings file
    _SENSITIVE_KEYS = {"network_db_password", "smtp_pass"}
    _fernet: Fernet | None = None

    _KEY_FILE = os.path.join(Config.DATA_DIR, ".encryption_key")

    @staticmethod
    def _write_restricted(path: str, content: str, encoding: str = "utf-8") -> None:
        """Write *content* to *path* with owner-only permissions (0600).

        On Windows ``os.chmod`` sets the read-only attribute which is not
        equivalent to POSIX permissions, but it is the best we can do
        without pulling in ``pywin32``.  The file is still protected by
        the per-user AppData directory ACL set by the OS.
        """
        # Use os.open with explicit mode bits so the file is never
        # world-readable even for a brief instant.
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        try:
            with os.fdopen(fd, "w", encoding=encoding) as f:
                f.write(content)
        except BaseException:
            # fd is already closed by os.fdopen on success; on error we
            # must NOT close it twice — os.fdopen takes ownership.
            raise
        # Belt-and-suspenders: chmod again in case the OS ignored the
        # mode in os.open (Windows does).
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    @classmethod
    def _get_fernet(cls) -> Fernet:
        """Return a Fernet instance using a persistent key file.

        The key is stored in a file so it survives hostname changes and
        machine migrations.  On first run the key is derived from machine
        identity for backwards compatibility with existing encrypted values.
        """
        if cls._fernet is None:
            if os.path.exists(cls._KEY_FILE):
                with open(cls._KEY_FILE, "r", encoding="ascii") as f:
                    key = f.read().strip().encode("ascii")
            else:
                # First run — derive from machine identity (matches old behaviour)
                seed = f"cbpos-{platform.node()}-{platform.system()}".encode()
                key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
                # Persist the key so it stays stable across hostname changes
                try:
                    cls._write_restricted(cls._KEY_FILE, key.decode("ascii"), encoding="ascii")
                except OSError as e:
                    logger.warning("Could not persist encryption key: %s", e)
            cls._fernet = Fernet(key)
        return cls._fernet

    @classmethod
    def _encode_sensitive(cls, value: str) -> str:
        """Encrypt a sensitive value for storage."""
        if not value:
            return ""
        return cls._get_fernet().encrypt(value.encode("utf-8")).decode("ascii")

    @classmethod
    def _decode_sensitive(cls, value: str) -> str:
        """Decrypt a sensitive value from storage."""
        if not value:
            return ""
        try:
            return cls._get_fernet().decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken:
            # Try legacy base64 decode for migration
            try:
                return base64.b64decode(value.encode("ascii")).decode("utf-8")
            except Exception:
                return value
        except Exception as e:
            logger.error("Failed to decrypt sensitive value: %s. Returning empty string for security.", e)
            return ""

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
            cls._write_restricted(
                cls.SETTINGS_FILE,
                json.dumps(save_data, indent=4, ensure_ascii=False),
            )
        except Exception as e:
            logger.error("Error saving settings: %s", e)

    @classmethod
    def _terminal_key(cls, key: str) -> str:
        """Return a terminal-prefixed key when running in network mode."""
        if key in cls._PER_TERMINAL_KEYS:
            db_mode = cls._settings.get("db_mode", "standalone")
            if db_mode == "network":
                tid = cls._settings.get("terminal_id", "TERM-01")
                prefixed = f"{tid}.{key}"
                # Only use prefixed key if it exists; fall through to
                # global key for backwards compatibility.
                if prefixed in cls._settings:
                    return prefixed
        return key

    @classmethod
    def get(cls, key: str) -> Any:
        """Get a setting value.

        In network mode, per-terminal keys (printer, language, theme, etc.)
        are looked up under a terminal-prefixed key first, falling back to
        the global default if no terminal-specific value exists.
        """
        if not cls._settings:
            cls.load()
        resolved = cls._terminal_key(key)
        return cls._settings.get(resolved, cls.DEFAULTS.get(key))

    @classmethod
    def set(cls, key: str, value: Any):
        """Set a setting value and save.

        In network mode, per-terminal keys are stored under a
        terminal-prefixed key (e.g. ``TERM-01.printer_type``).
        """
        if not cls._settings:
            cls.load()
        store_key = key
        if key in cls._PER_TERMINAL_KEYS:
            db_mode = cls._settings.get("db_mode", "standalone")
            if db_mode == "network":
                tid = cls._settings.get("terminal_id", "TERM-01")
                store_key = f"{tid}.{key}"
        cls._settings[store_key] = value
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
