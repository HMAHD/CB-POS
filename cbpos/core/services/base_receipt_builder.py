"""Base receipt builder with shared helpers for all receipt types."""

import logging
from typing import List, Dict, Any, Optional

from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t, translate_in

logger = logging.getLogger(__name__)


class BaseReceiptBuilder:
    """
    Base class for all receipt builders.

    Provides shared helpers: config access, receipt translation,
    header/branding/cut blocks, and two-column formatting.

    Commands are device-agnostic dictionaries:
    - {'type': 'text', 'val': '...', 'align': 'left|center|right'}
    - {'type': 'image', 'path': '...'}
    - {'type': 'barcode', 'val': '...', 'code': 'CODE39|QR'}
    - {'type': 'feed', 'lines': 1}
    - {'type': 'cut', 'partial': True}
    """

    # Per-build receipt language cache.  Set by _resolve_receipt_lang()
    # so that _rt() doesn't call ConfigService.get() on every invocation.
    _receipt_lang: Optional[str] = None

    @classmethod
    def _rt(cls, key: str, **kwargs) -> str:
        """Shorthand for receipt translation keys.

        Uses the cached ``_receipt_lang`` (set at the start of each build
        method).  Falls back to the current UI language when unset.
        """
        lang = cls._receipt_lang
        if lang:
            return translate_in(lang, f"receipt_strings.{key}", **kwargs)
        return _t(f"receipt_strings.{key}", **kwargs)

    @classmethod
    def _resolve_receipt_lang(cls, config_override: Optional[Dict[str, Any]] = None) -> None:
        """Cache the effective receipt language for the current build call."""
        cls._receipt_lang = cls._get_conf("receipt_language", "", config_override) or None

    @classmethod
    def _get_conf(cls, key: str, default: Any = None, config_override: Optional[Dict[str, Any]] = None) -> Any:
        """Helper to get config value with override support."""
        if config_override and key in config_override:
            return config_override[key]
        val = ConfigService.get(key)
        return val if val is not None else default

    @classmethod
    def _append_branding(cls, commands: List[Dict[str, Any]]) -> None:
        """Append CB POS branding to receipt."""
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": "Powered by CB POS", "align": "center"})
        commands.append({"type": "text", "val": "ceybyte.com", "align": "center"})

    @classmethod
    def _append_cut(cls, commands: List[Dict[str, Any]], config_override: Optional[Dict[str, Any]] = None) -> None:
        """Append configurable feed + cut commands."""
        auto_cut = cls._get_conf("auto_cut_paper", True, config_override)
        feed_lines = cls._get_conf("feed_lines_before_cut", 3, config_override)
        cut_type = cls._get_conf("cut_type", "partial", config_override)

        commands.append({"type": "feed", "lines": feed_lines})
        if auto_cut:
            commands.append({"type": "cut", "partial": cut_type == "partial"})

    @classmethod
    def _append_header_block(
        cls,
        commands: List[Dict[str, Any]],
        config_override: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Append header text, logo, shop info, TIN. Returns line_chars."""
        paper_width = cls._get_conf("paper_width", "80mm", config_override)
        line_chars = 32 if paper_width == "58mm" else 42
        gc = cls._get_conf

        # Custom header text (top — greeting/promo before shop identity)
        header_text = gc("receipt_header", "", config_override)
        if header_text:
            commands.append({"type": "text", "val": header_text, "align": "center"})

        # Logo
        logo_path = gc("receipt_logo_path", "", config_override)
        if logo_path:
            commands.append({"type": "image", "path": logo_path})

        # Shop name (bold, center)
        shop_name = gc("shop_name", "", config_override)
        if shop_name:
            commands.append({"type": "text", "val": shop_name, "align": "center", "bold": True})

        # Shop address + phone on same line if both short, else separate
        shop_address = gc("shop_address", "", config_override)
        if shop_address:
            commands.append({"type": "text", "val": shop_address, "align": "center"})

        shop_phone = gc("shop_phone", "", config_override)
        if shop_phone:
            commands.append({"type": "text", "val": shop_phone, "align": "center"})

        # TIN
        tax_id = gc("company_tax_id", "", config_override)
        if tax_id:
            commands.append({"type": "text", "val": f"{cls._rt('tin')}: {tax_id}", "align": "center"})

        return line_chars

    @staticmethod
    def _two_col(left: str, right: str, width: int) -> str:
        """Format two strings into a single line padded to *width* characters."""
        gap = width - len(left) - len(right)
        return "{}{}{}".format(left, " " * max(gap, 1), right)

    @classmethod
    def _split_row(
        cls,
        left: str,
        right: str,
        width: int,
        bold: bool = False,
    ) -> Dict[str, Any]:
        """Build a two-column text command with both printer val and preview split."""
        return {
            "type": "text",
            "val": cls._two_col(left, right, width),
            "align": "left",
            "bold": bold,
            "left_val": left,
            "right_val": right,
        }

    @staticmethod
    def _get_current_cashier_name() -> str:
        """Get current logged-in user's username, or empty string."""
        try:
            from cbpos.core.services.auth_service import AuthService

            user = AuthService.get_current_user()
            return user.username if user else ""
        except Exception as e:
            logger.debug("Could not get current cashier name: %s", e)
            return ""
