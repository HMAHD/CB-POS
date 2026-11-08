import base64
import contextlib
import hashlib
import json
import logging
import os
import platform
import stat
import tempfile
from datetime import datetime
from typing import Any

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
        "sscl_registered": False,  # Whether business is SSCL-registered (#831)
        "sscl_turnover_preset": "RETAIL",  # RETAIL, MANUFACTURER, DISTRIBUTOR, CUSTOM (#831)
        "item_tax_exemptions": False,  # Enable item-level tax exemptions (#797)
        "tax_vat_rate": 18.0,
        "tax_sscl_rate": 2.5,
        "tax_sscl_turnover_pct": 50.0,
        "printer_type": "NONE",  # WIN32, NETWORK, USB, or NONE (see constants.hardware.PrinterType)
        "printer_path": "",  # WIN32: Windows printer name, NETWORK: IP[:port], USB: VID:PID
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
        "promotion_stack_with_price_lists": False,  # False: best-of (cheapest), True: stack on price list
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
        "drawer_pin": 2,  # Drawer kick pin: 2 or 5 (depends on the drawer cable)
        # Scale Barcode Configuration
        "scale_barcode_prefix": "20",  # Prefix for scale barcodes
        "scale_decimal_places": 3,  # Decimal places for weight
        # Banking Details (printed on A4 invoices -- blank until the shop sets them)
        "company_bank_name": "",
        "company_account_number": "",
        "company_bank_branch": "",
        # Inventory Control
        "allow_negative_stock": False,  # Allow overselling
        "auto_generate_barcodes": True,
        # Feature Flags
        "enable_loyalty": True,
        "enable_sounds": True,
        "auto_select_barcode_match": True,
        # Appearance
        "theme": "Dark",
        "font_size": 12,
        # Reports
        "favorite_reports": [],
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
        # Loyalty Program
        "loyalty_points_ratio": 100,
        "loyalty_point_value": 1.0,
        "loyalty_min_redeem_points": 100,
        "show_loyalty_on_receipt": True,
        # Terminal Identification
        "terminal_id": "TERM-01",
        # Multi-Terminal LAN Sync
        "terminal_mode": "standalone",  # standalone, main, or terminal
        "sync_server_port": 5555,  # Port for sync server (Main PC)
        "main_pc_address": "",  # IP:port of Main PC (Terminal mode)
        "sync_interval_seconds": 3,  # How often terminals push/pull (seconds)
        "sync_shared_secret": "",  # Shared token — same value required on Main PC and every Terminal
        "sync_pinned_cert_pem": "",  # Pinned Main PC TLS certificate (PEM) for LAN Sync (#800)
        "sync_pinned_cert_fp": "",  # Canonical fingerprint of pinned certificate for display (#800)
        "main_pc_instance_id": "",  # This machine's Main PC identity — generated on first "Main PC" start
        "sync_known_main_instance_id": "",  # (Terminal mode) instance_id of the Main PC first synced with
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
        # Setup / First Run
        "setup_completed": False,
    }

    _settings: dict[str, Any] = {}
    _loaded_from_defaults_after_failure: bool = False
    _recovery_reason: str | None = None
    _corrupt_filename: str | None = None
    _rename_failed: bool = False
    _undecryptable_keys: set[str] = set()
    _frozen: bool = False

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
            "drawer_pin",
            "language",
            "theme",
            "enable_sounds",
            "sidebar_collapsed",
            "terminal_mode",
            "main_pc_address",
        }
    )

    # Keys that should be encrypted in the settings file
    _SENSITIVE_KEYS = {"network_db_password", "smtp_pass", "sync_shared_secret", "sync_pinned_cert_pem"}
    _fernet: Fernet | None = None

    _KEY_FILE = os.path.join(Config.DATA_DIR, ".encryption_key")

    # The shop backup password lives in its own file, not settings.json:
    # settings.json is copied into every backup and overwritten by every
    # restore, which would roll the password back or (on another PC, with
    # another .encryption_key) leave an undecryptable value behind.
    _BACKUP_PASSWORD_FILE = os.path.join(Config.DATA_DIR, ".backup_password")
    MIN_BACKUP_PASSWORD_LENGTH = 6

    @classmethod
    def recovery_notice(cls) -> str | None:
        """Return 'restored_from_backup' or 'defaults_after_corruption' once, or None."""
        notice = cls._recovery_reason
        cls._recovery_reason = None
        return notice

    @classmethod
    def corrupt_filename(cls) -> str | None:
        """Return the quarantined corrupt filename, if any."""
        return cls._corrupt_filename

    @classmethod
    def secrets_needing_reentry(cls) -> list[str]:
        """Return the list of sensitive keys that could not be decrypted (#875)."""
        return sorted(cls._undecryptable_keys)

    @classmethod
    def reload(cls) -> None:
        """Reload settings from disk, resetting cached state and unfreezing writes (#873)."""
        cls._settings = {}
        cls._fernet = None
        cls._loaded_from_defaults_after_failure = False
        cls._rename_failed = False
        cls._recovery_reason = None
        cls._corrupt_filename = None
        cls._undecryptable_keys.clear()
        cls._frozen = False
        cls.load()

    @classmethod
    def freeze_writes(cls) -> None:
        """Freeze settings writes until application restarts or unfreeze_writes is called (#873)."""
        cls._frozen = True

    @classmethod
    def unfreeze_writes(cls) -> None:
        """Unfreeze settings writes (primarily for test teardowns, #873)."""
        cls._frozen = False

    @staticmethod
    def _write_restricted(path: str, content: str, encoding: str = "utf-8") -> None:
        """Write *content* to *path* with owner-only permissions (0600), atomically.

        Writes to a temp file in the same directory first, flushes and fsyncs,
        then renames it onto *path* with ``os.replace()`` -- atomic on the same
        filesystem on both POSIX and Windows, so a crash or power cut mid-write
        can never leave *path* truncated or half-written.

        On Windows ``os.chmod`` sets the read-only attribute which is not
        equivalent to POSIX permissions, but it is the best we can do
        without pulling in ``pywin32``.  The file is still protected by
        the per-user AppData directory ACL set by the OS.
        """
        directory = os.path.dirname(path) or "."
        # Use mkstemp with explicit mode bits so the file is never
        # world-readable even for a brief instant, and lives on the same
        # filesystem as *path* so the final rename is atomic.
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=f".{os.path.basename(path)}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding=encoding) as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            # Belt-and-suspenders: chmod again in case the OS ignored the
            # mode in mkstemp (Windows does).
            with contextlib.suppress(OSError):
                os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(tmp_path, path)
            if os.name == "posix":
                with contextlib.suppress(OSError):
                    dir_fd = os.open(directory, os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
        except BaseException:
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
            raise

    @classmethod
    def _derive_legacy_hostname_key(cls) -> bytes:
        """Derive legacy encryption key from machine identity. Strictly for legacy migration."""
        seed = f"cbpos-{platform.node()}-{platform.system()}".encode()
        return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())

    @classmethod
    def _wrap_key(cls, key_bytes: bytes) -> str:
        """Wrap a Fernet key for persistent storage at rest."""
        if platform.system() == "Windows":
            try:
                import win32crypt

                blob = win32crypt.CryptProtectData(key_bytes, "CB POS", None, None, None, 1)
                return f"dpapi:{base64.b64encode(blob).decode('ascii')}"
            except Exception as e:
                logger.warning("Could not protect encryption key with DPAPI; falling back to raw: %s", e)
        return f"raw:{key_bytes.decode('ascii')}"

    @classmethod
    def _unwrap_key(cls, stored_content: str) -> bytes:
        """Unwrap a stored encryption key string to Fernet key bytes.

        Raises:
            ValueError, OSError, Exception on unwrap or format failure.
        """
        raw_str = stored_content.strip()
        if not raw_str:
            raise ValueError("Encryption key file is empty")

        if raw_str.startswith("dpapi:"):
            payload = raw_str[6:].strip()
            blob = base64.b64decode(payload.encode("ascii"))
            if platform.system() == "Windows":
                import win32crypt

                _, key_bytes = win32crypt.CryptUnprotectData(blob, None, None, None, 1)
                return key_bytes
            else:
                raise OSError("DPAPI encrypted key cannot be unwrapped on non-Windows platform")
        elif raw_str.startswith("raw:"):
            return raw_str[4:].strip().encode("ascii")
        else:
            raise ValueError("Stored key does not have a valid prefix")

    @classmethod
    def _ensure_encryption_initialized(cls) -> None:
        """Ensure encryption key is initialized and legacy data migrated if necessary."""
        if cls._fernet is not None:
            return

        key_file_exists = os.path.exists(cls._KEY_FILE)
        raw_content = ""
        if key_file_exists:
            try:
                with open(cls._KEY_FILE, encoding="ascii") as f:
                    raw_content = f.read().strip()
            except Exception as e:
                logger.warning("Could not read encryption key file: %s", e)

        # Check if legacy migration is needed:
        # 1. key file exists but has no prefix (legacy format)
        # 2. key file is missing, but settings.json has sensitive values decryptable with hostname key
        needs_migration = False
        legacy_key_bytes: bytes | None = None

        if key_file_exists and raw_content and not raw_content.startswith(("raw:", "dpapi:")):
            needs_migration = True
            legacy_key_bytes = raw_content.encode("ascii")
        elif not key_file_exists and os.path.exists(cls.SETTINGS_FILE):
            try:
                with open(cls.SETTINGS_FILE, encoding="utf-8") as f:
                    stored_settings = json.load(f)
                candidate_key = cls._derive_legacy_hostname_key()
                candidate_fernet = Fernet(candidate_key)
                for k in cls._SENSITIVE_KEYS:
                    val = stored_settings.get(k)
                    if val and isinstance(val, str) and val.startswith("gAAAAA"):
                        candidate_fernet.decrypt(val.encode("ascii"))
                        needs_migration = True
                        legacy_key_bytes = candidate_key
                        break
            except Exception:
                pass

        if needs_migration and legacy_key_bytes:
            cls._migrate_legacy_encryption(legacy_key_bytes)
            return

        if key_file_exists and raw_content:
            try:
                key_bytes = cls._unwrap_key(raw_content)
                cls._fernet = Fernet(key_bytes)
                return
            except Exception as e:
                logger.warning("Failed to unwrap encryption key (%s); quarantining key file.", e)
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                corrupt_name = f"{os.path.basename(cls._KEY_FILE)}.corrupt-{timestamp}"
                corrupt_path = os.path.join(os.path.dirname(cls._KEY_FILE) or ".", corrupt_name)
                with contextlib.suppress(OSError):
                    os.replace(cls._KEY_FILE, corrupt_path)

        # Fresh install or replaced unreadable key: generate new random Fernet key
        new_key = Fernet.generate_key()
        wrapped = cls._wrap_key(new_key)
        try:
            cls._write_restricted(cls._KEY_FILE, wrapped, encoding="ascii")
        except OSError as e:
            logger.warning("Could not persist encryption key: %s", e)
        cls._fernet = Fernet(new_key)

    @classmethod
    def _migrate_legacy_encryption(cls, legacy_key: bytes) -> None:
        """Migrate legacy encryption key to cryptographically random key with DPAPI/raw protection."""
        try:
            legacy_fernet = Fernet(legacy_key)
        except Exception as e:
            logger.warning("Invalid legacy encryption key format: %s; generating new random key", e)
            new_key = Fernet.generate_key()
            wrapped = cls._wrap_key(new_key)
            cls._write_restricted(cls._KEY_FILE, wrapped, encoding="ascii")
            cls._fernet = Fernet(new_key)
            return

        # Decrypt sensitive settings
        raw_settings: dict[str, Any] = {}
        if os.path.exists(cls.SETTINGS_FILE):
            try:
                with open(cls.SETTINGS_FILE, encoding="utf-8") as f:
                    raw_settings = json.load(f)
            except Exception:
                raw_settings = {}

        decrypted_sensitive: dict[str, str] = {}
        for k in cls._SENSITIVE_KEYS:
            val = raw_settings.get(k)
            if val and isinstance(val, str):
                try:
                    decrypted_sensitive[k] = legacy_fernet.decrypt(val.encode("ascii")).decode("utf-8")
                except Exception:
                    pass

        # Decrypt backup password if present
        decrypted_backup_pw: str | None = None
        if os.path.exists(cls._BACKUP_PASSWORD_FILE):
            try:
                with open(cls._BACKUP_PASSWORD_FILE, encoding="ascii") as f:
                    token = f.read().strip()
                if token:
                    decrypted_backup_pw = legacy_fernet.decrypt(token.encode("ascii")).decode("utf-8")
            except Exception:
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                corrupt_pw = f"{os.path.basename(cls._BACKUP_PASSWORD_FILE)}.corrupt-{timestamp}"
                corrupt_path = os.path.join(os.path.dirname(cls._BACKUP_PASSWORD_FILE) or ".", corrupt_pw)
                with contextlib.suppress(OSError):
                    os.replace(cls._BACKUP_PASSWORD_FILE, corrupt_path)
                logger.warning("Quarantined unreadable backup password during migration")

        # Generate new random key
        new_key = Fernet.generate_key()
        new_fernet = Fernet(new_key)
        wrapped_key = cls._wrap_key(new_key)

        # Re-encrypt sensitive settings
        for k, plain_val in decrypted_sensitive.items():
            raw_settings[k] = new_fernet.encrypt(plain_val.encode("utf-8")).decode("ascii")

        # Re-encrypt and persist backup password if it existed
        if decrypted_backup_pw is not None:
            new_pw_token = new_fernet.encrypt(decrypted_backup_pw.encode("utf-8")).decode("ascii")
            cls._write_restricted(cls._BACKUP_PASSWORD_FILE, new_pw_token, encoding="ascii")

        # Write new protected key
        cls._write_restricted(cls._KEY_FILE, wrapped_key, encoding="ascii")

        # Atomically write updated settings.json and settings.json.bak
        if os.path.exists(cls.SETTINGS_FILE):
            content = json.dumps(raw_settings, indent=4, ensure_ascii=False)
            cls._write_restricted(cls.SETTINGS_FILE, content)
            bak_file = f"{cls.SETTINGS_FILE}.bak"
            if os.path.exists(bak_file):
                try:
                    with open(bak_file, encoding="utf-8") as f_bak:
                        bak_settings = json.load(f_bak)
                    for k, plain_val in decrypted_sensitive.items():
                        if bak_settings.get(k):
                            bak_settings[k] = new_fernet.encrypt(plain_val.encode("utf-8")).decode("ascii")
                    cls._write_restricted(bak_file, json.dumps(bak_settings, indent=4, ensure_ascii=False))
                except Exception:
                    pass

        cls._fernet = new_fernet
        logger.info("Settings encryption key upgraded")

    @classmethod
    def _get_fernet(cls) -> Fernet:
        """Return a Fernet instance using a persistent key file."""
        if cls._fernet is None:
            cls._ensure_encryption_initialized()
        return cls._fernet

    @classmethod
    def _encode_sensitive(cls, value: str) -> str:
        """Encrypt a sensitive value for storage."""
        if not value:
            return ""
        return cls._get_fernet().encrypt(value.encode("utf-8")).decode("ascii")

    @classmethod
    def _decode_sensitive(cls, value: str, key_name: str | None = None) -> str:
        """Decrypt a sensitive value from storage."""
        if not value:
            return ""
        try:
            return cls._get_fernet().decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken:
            # Fernet tokens start with 'gAAAAA'. If decryption failed with InvalidToken,
            # it was encrypted with another machine's key (e.g. restored backup, #875).
            # Never return ciphertext as plaintext or it will be double-encrypted on save!
            if value.startswith("gAAAAA"):
                if key_name:
                    cls._undecryptable_keys.add(key_name)
                logger.warning(
                    "Encrypted secret '%s' could not be decrypted with current key; resetting to empty.",
                    key_name or "unknown",
                )
                return ""
            # Try legacy base64 decode for old pre-Fernet plain settings
            try:
                return base64.b64decode(value.encode("ascii")).decode("utf-8")
            except Exception:
                if key_name:
                    cls._undecryptable_keys.add(key_name)
                return ""
        except Exception as e:
            logger.error("Failed to decrypt sensitive value for '%s': %s", key_name or "unknown", e)
            if key_name:
                cls._undecryptable_keys.add(key_name)
            return ""

    @classmethod
    def get_backup_password(cls) -> str | None:
        """Return the shop backup password, or None if none is set.

        The password is stored Fernet-encrypted with the app encryption key.
        A value that can't be decrypted (e.g. the key file changed) counts
        as "not set" so callers ask for a new one instead of silently
        encrypting backups with a password nobody knows.
        """
        try:
            with open(cls._BACKUP_PASSWORD_FILE, encoding="ascii") as f:
                token = f.read().strip()
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError) as e:
            logger.error("Could not read the backup password file: %s", e)
            return None
        if not token:
            return None
        try:
            return cls._get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            logger.error("Stored backup password could not be decrypted; treating it as not set")
            return None

    @classmethod
    def has_backup_password(cls) -> bool:
        """Return True if a usable shop backup password is set."""
        return cls.get_backup_password() is not None

    @classmethod
    def set_backup_password(cls, password: str) -> None:
        """Store the shop backup password, encrypted with the app encryption key.

        Args:
            password: The new password. Affects backups made from now on only.

        Raises:
            ValueError: If the password is shorter than MIN_BACKUP_PASSWORD_LENGTH.
            OSError: If the password file can't be written.
        """
        if not password or len(password) < cls.MIN_BACKUP_PASSWORD_LENGTH:
            raise ValueError(f"Backup password must be at least {cls.MIN_BACKUP_PASSWORD_LENGTH} characters")
        token = cls._get_fernet().encrypt(password.encode("utf-8")).decode("ascii")
        cls._write_restricted(cls._BACKUP_PASSWORD_FILE, token, encoding="ascii")
        logger.info("Shop backup password updated")

    @classmethod
    def load(cls):
        """Load settings from file, or create with defaults if not exists."""
        cls._undecryptable_keys.clear()
        cls._ensure_encryption_initialized()
        if os.path.exists(cls.SETTINGS_FILE):
            try:
                with open(cls.SETTINGS_FILE, encoding="utf-8") as f:
                    content = f.read()
                if not content.strip():
                    raise json.JSONDecodeError("Settings file is empty", "", 0)
                cls._settings = json.loads(content)
                # Decode sensitive values after loading
                for key in cls._SENSITIVE_KEYS:
                    if cls._settings.get(key):
                        cls._settings[key] = cls._decode_sensitive(cls._settings[key], key_name=key)
                changed = cls._migrate_receipt_printer(cls._settings)
                changed = cls._clear_demo_bank_details(cls._settings) or changed
                changed = cls._migrate_loyalty_keys(cls._settings) or changed
                changed = cls._migrate_sscl_keys(cls._settings) or changed
                if "setup_completed" not in cls._settings:
                    cls._settings["setup_completed"] = True
                    changed = True
                if changed:
                    cls.save()
                return
            except Exception as e:
                logger.error("Error loading settings: %s. Quarantining file.", e)
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                corrupt_name = f"{os.path.basename(cls.SETTINGS_FILE)}.corrupt-{timestamp}"
                corrupt_path = os.path.join(os.path.dirname(cls.SETTINGS_FILE) or ".", corrupt_name)
                try:
                    os.replace(cls.SETTINGS_FILE, corrupt_path)
                    cls._corrupt_filename = corrupt_name
                except OSError as rename_err:
                    logger.error("Failed to quarantine corrupt settings file %s: %s", cls.SETTINGS_FILE, rename_err)
                    cls._rename_failed = True

                bak_file = f"{cls.SETTINGS_FILE}.bak"
                if os.path.exists(bak_file):
                    try:
                        with open(bak_file, encoding="utf-8") as f_bak:
                            bak_content = f_bak.read()
                        if not bak_content.strip():
                            raise json.JSONDecodeError("Backup file is empty", "", 0)
                        cls._settings = json.loads(bak_content)
                        for key in cls._SENSITIVE_KEYS:
                            if cls._settings.get(key):
                                cls._settings[key] = cls._decode_sensitive(cls._settings[key], key_name=key)
                        cls._migrate_receipt_printer(cls._settings)
                        cls._clear_demo_bank_details(cls._settings)
                        cls._migrate_loyalty_keys(cls._settings)
                        cls._migrate_sscl_keys(cls._settings)
                        if "setup_completed" not in cls._settings:
                            cls._settings["setup_completed"] = True
                        cls._recovery_reason = "restored_from_backup"
                        logger.warning("Corrupt settings quarantined as %s. Restored from %s.", corrupt_name, bak_file)
                        cls.save()
                        return
                    except Exception as bak_err:
                        logger.error("Settings backup file %s was also invalid: %s", bak_file, bak_err)

                cls._settings = cls.DEFAULTS.copy()
                cls._loaded_from_defaults_after_failure = True
                cls._recovery_reason = "defaults_after_corruption"
                logger.warning("No valid backup found. Starting with default settings. Quarantine: %s", corrupt_name)
        else:
            cls._settings = cls.DEFAULTS.copy()
            cls.save()

    # Demo bank details the old defaults wrote into every new settings.json.
    _DEMO_BANK_DETAILS = {
        "company_bank_name": "Commercial Bank of Ceylon",
        "company_account_number": "1234567890",
        "company_bank_branch": "Colombo Fort",
    }

    @classmethod
    def _clear_demo_bank_details(cls, settings: dict[str, Any]) -> bool:
        """Blank the old demo bank details, so they never print on an invoice (#641).

        Shop Info's bank fields used to be ignored by the invoice, and their
        defaults were demo values saved into every settings.json on first run.
        Now that the invoice prints them, only that exact trio is cleared --
        any value the shop typed is kept.

        Args:
            settings: The loaded settings dict; updated in place.

        Returns:
            True if anything changed (the caller saves the file).
        """
        if any(settings.get(k) != v for k, v in cls._DEMO_BANK_DETAILS.items()):
            return False
        for key in cls._DEMO_BANK_DETAILS:
            settings[key] = ""
        return True

    # Virtual printers Windows installs by default. The old Hardware page
    # saved whatever its printer combo showed first -- often one of these --
    # so they are no evidence the shop chose a receipt printer.
    _VIRTUAL_PRINTER_MARKERS = ("pdf", "xps", "onenote", "fax")

    @classmethod
    def _migrate_receipt_printer(cls, settings: dict[str, Any]) -> bool:
        """Turn a legacy ``receipt_printer_name`` into a Windows printer setting (#622).

        Before #622 the Hardware page and Setup Wizard saved only
        ``receipt_printer_name``, which nothing read, so ``printer_type``
        stayed NONE. An install with a real printer name there but no
        printer type now becomes ``printer_type`` WIN32 with that name.
        Placeholder texts ("No printers found") and virtual printers
        (PDF/XPS/OneNote/Fax) are skipped. Terminal-prefixed keys
        (network mode) are migrated the same way.

        Args:
            settings: The loaded settings dict; updated in place.

        Returns:
            True if anything changed (the caller saves the file).
        """
        from cbpos.i18n import translate_in

        placeholders = {
            translate_in(lang, key)
            for lang in ("en", "si", "ta")
            for key in ("settings.hardware.no_printers", "setup_wizard.none_detected", "setup_wizard.printer_none")
        }
        changed = False
        for key in [k for k in settings if k == "receipt_printer_name" or k.endswith(".receipt_printer_name")]:
            prefix = key[: -len("receipt_printer_name")]
            name = (settings.get(key) or "").strip()
            if not name or name in placeholders:
                continue
            if any(marker in name.lower() for marker in cls._VIRTUAL_PRINTER_MARKERS):
                continue
            type_key = f"{prefix}printer_type"
            current_type = settings.get(type_key, settings.get("printer_type", "NONE") if prefix else "NONE")
            if current_type not in (None, "", "NONE"):
                continue
            settings[type_key] = "WIN32"
            settings[f"{prefix}printer_path"] = name
            changed = True
            logger.info("Migrated receipt printer '%s' to a Windows printer setting (%s).", name, type_key)
        return changed

    @classmethod
    def _migrate_loyalty_keys(cls, settings: dict[str, Any]) -> bool:
        """Migrate legacy loyalty setting keys to standard names (#801).

        - 'loyalty_minimum_redeem' or 'min_redeem_points' -> 'loyalty_min_redeem_points'
        """
        changed = False
        legacy_keys = ("loyalty_minimum_redeem", "min_redeem_points")
        for key in legacy_keys:
            if key in settings:
                if "loyalty_min_redeem_points" not in settings:
                    settings["loyalty_min_redeem_points"] = settings[key]
                del settings[key]
                changed = True
        return changed

    @classmethod
    def _migrate_sscl_keys(cls, settings: dict[str, Any]) -> bool:
        """Migrate SSCL registration setting (#831).

        When 'sscl_registered' is not explicitly present, initialize it from
        'vat_registered' so existing behavior doesn't change on upgrade.
        """
        if "sscl_registered" not in settings:
            settings["sscl_registered"] = bool(settings.get("vat_registered", False))
            return True
        return False

    @classmethod
    def save(cls, *, raise_errors: bool = False):
        """Save current settings to file with sensitive values encoded.

        Args:
            raise_errors: Re-raise a failed write instead of only logging it.
        """
        if cls._frozen:
            logger.warning("ConfigService writes are frozen (pending application restart); save skipped")
            return

        if cls._loaded_from_defaults_after_failure and cls._rename_failed:
            logger.warning(
                "Skipping save because settings are in defaults-after-failure state and quarantine rename failed."
            )
            return

        try:
            # Create a copy with sensitive values encoded
            save_data = cls._settings.copy()
            for key in cls._SENSITIVE_KEYS:
                if save_data.get(key):
                    save_data[key] = cls._encode_sensitive(save_data[key])
            encoded_content = json.dumps(save_data, indent=4, ensure_ascii=False)
            cls._write_restricted(
                cls.SETTINGS_FILE,
                encoded_content,
            )
            # Last-good copy: only if not running with defaults after corruption failure
            if not cls._loaded_from_defaults_after_failure:
                cls._write_restricted(f"{cls.SETTINGS_FILE}.bak", encoded_content)
        except Exception as e:
            logger.error("Error saving settings: %s", e)
            if raise_errors:
                raise

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
        if key in ("loyalty_minimum_redeem", "min_redeem_points"):
            key = "loyalty_min_redeem_points"
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
        if key in ("loyalty_minimum_redeem", "min_redeem_points"):
            key = "loyalty_min_redeem_points"
        store_key = key
        if key in cls._PER_TERMINAL_KEYS:
            db_mode = cls._settings.get("db_mode", "standalone")
            if db_mode == "network":
                tid = cls._settings.get("terminal_id", "TERM-01")
                store_key = f"{tid}.{key}"
        cls._settings[store_key] = value
        if key in cls._undecryptable_keys and value:
            cls._undecryptable_keys.discard(key)
        cls.save()

    @classmethod
    def get_all(cls) -> dict[str, Any]:
        """Get all settings."""
        if not cls._settings:
            cls.load()
        return cls._settings.copy()

    @classmethod
    def update_all(cls, data: dict[str, Any], *, raise_errors: bool = False):
        """Update multiple settings at once and save them.

        Args:
            data: Settings to change.
            raise_errors: If the write fails, put the previous values back and
                re-raise, so nothing changed (Settings save, #729). By default
                a failed write is only logged and the new values stay in memory.
        """
        if not cls._settings:
            cls.load()
        previous = cls._settings.copy()
        cls._settings.update(data)
        for k, v in data.items():
            if k in cls._undecryptable_keys and v:
                cls._undecryptable_keys.discard(k)
        try:
            cls.save(raise_errors=raise_errors)
        except Exception:
            cls._settings.clear()
            cls._settings.update(previous)
            raise

    @classmethod
    def get_postgres_uri(cls) -> str:
        """Construct PostgreSQL database URL from saved network configuration."""
        from sqlalchemy.engine import URL

        host = cls.get("network_db_host") or "localhost"
        port = int(cls.get("network_db_port") or 5432)
        dbname = cls.get("network_db_name") or "cbpos"
        user = cls.get("network_db_user") or "postgres"
        password = cls.get("network_db_password") or ""
        sslmode = cls.get("network_db_sslmode") or "prefer"

        query = {}
        if sslmode and sslmode != "disable":
            query["sslmode"] = sslmode

        url_obj = URL.create(
            drivername="postgresql+psycopg2",
            username=user,
            password=password,
            host=host,
            port=port,
            database=dbname,
            query=query,
        )
        return str(url_obj)
