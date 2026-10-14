"""Base receipt builder with shared helpers for all receipt types."""

import logging
import textwrap
from typing import Any

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_logo_service import resolve_receipt_logo
from cbpos.core.utils.formatters import format_quantity, quantity_decimals
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
    _receipt_lang: str | None = None

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
    def _resolve_receipt_lang(cls, config_override: dict[str, Any] | None = None) -> None:
        """Cache the effective receipt language for the current build call."""
        cls._receipt_lang = cls._get_conf("receipt_language", "", config_override) or None

    @classmethod
    def _get_conf(cls, key: str, default: Any = None, config_override: dict[str, Any] | None = None) -> Any:
        """Helper to get config value with override support."""
        if config_override and key in config_override:
            return config_override[key]
        val = ConfigService.get(key)
        return val if val is not None else default

    @classmethod
    def _append_branding(cls, commands: list[dict[str, Any]]) -> None:
        """Append CB POS branding to receipt."""
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": "Powered by CB POS", "align": "center"})
        commands.append({"type": "text", "val": "ceybyte.com", "align": "center"})

    @classmethod
    def _append_cut(cls, commands: list[dict[str, Any]], config_override: dict[str, Any] | None = None) -> None:
        """Append configurable feed + cut commands."""
        auto_cut = cls._get_conf("auto_cut_paper", True, config_override)
        feed_lines = cls._get_conf("feed_lines_before_cut", 3, config_override)
        cut_type = cls._get_conf("cut_type", "partial", config_override)

        commands.append({"type": "feed", "lines": feed_lines})
        if auto_cut:
            commands.append({"type": "cut", "partial": cut_type == "partial"})

    @staticmethod
    def _wrap_free_text(text: str, width: int) -> list[str]:
        """Wrap free-form (shop-entered) text to *width* characters per line.

        Preserves the author's own explicit line breaks (each is wrapped
        independently) rather than collapsing them into one paragraph, so
        a shop's multi-line greeting keeps its intended paragraph shape.

        Pre-wrapping here -- once, in the shared builder -- is what lets
        the preview widget and the real ESC/POS printer agree on exactly
        where a long header/footer breaks: each receives the identical
        list of already-line-broken strings instead of independently
        deciding where to wrap (Qt's HTML engine vs. the printer
        firmware's own font metrics, which never agreed).
        """
        if not text:
            return []
        lines: list[str] = []
        for paragraph in text.split("\n"):
            if not paragraph.strip():
                lines.append("")
                continue
            lines.extend(textwrap.wrap(paragraph, width=width) or [""])
        return lines

    @classmethod
    def _append_footer_text(
        cls,
        commands: list[dict[str, Any]],
        line_chars: int,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        """Append the shop's custom footer text, pre-wrapped to *line_chars*."""
        footer_text = cls._get_conf("receipt_footer", "", config_override)
        if not footer_text:
            return
        commands.append({"type": "feed", "lines": 1})
        for line in cls._wrap_free_text(footer_text, line_chars):
            commands.append({"type": "text", "val": line, "align": "center"})

    @classmethod
    def _append_header_block(
        cls,
        commands: list[dict[str, Any]],
        config_override: dict[str, Any] | None = None,
    ) -> int:
        """Append header text, logo, shop info, TIN. Returns line_chars."""
        paper_width = cls._get_conf("paper_width", "80mm", config_override)
        line_chars = 32 if paper_width == "58mm" else 42
        gc = cls._get_conf

        # Custom header text (top — greeting/promo before shop identity)
        header_text = gc("receipt_header", "", config_override)
        if header_text:
            for line in cls._wrap_free_text(header_text, line_chars):
                commands.append({"type": "text", "val": line, "align": "center"})

        # Logo
        # Stored relative to the data folder since #626; resolve to a real path.
        logo_path = resolve_receipt_logo(gc("receipt_logo_path", "", config_override))
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
    def _item_qty_decimals(item: Any) -> int:
        """Decimal places for *item*'s quantity: its unit's, or 0 when it has no unit.

        0 (not the 3-decimal default for an unknown unit) so a plain ``2``
        stays ``2``; ``format_quantity`` still widens to 3 decimals when the
        value is fractional, so nothing is hidden.
        """
        product = getattr(item, "product", None)
        unit = getattr(product, "unit", None) if product is not None else None
        return quantity_decimals(unit) if unit is not None else 0

    @classmethod
    def _format_item_qty(cls, item: Any) -> str:
        """Quantity as printed on the receipt, the same for a fresh sale and a reloaded one (#681).

        A sale reloaded from the database carries ``2.000`` (the column's
        scale) where the cart had ``2``; formatting by unit makes the
        original print and every reprint agree.
        """
        return format_quantity(item.qty, cls._item_qty_decimals(item))

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
    ) -> dict[str, Any]:
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

    @classmethod
    def _get_sale_cashier_name(cls, sale: Any) -> str:
        """Username of the cashier who made *sale*, for its receipt (#681).

        A reprint must show the sale's own cashier, not whoever is logged in
        now. Only an unsaved sale (the Settings preview, no ``user_id``)
        falls back to the current user. A saved sale whose user wasn't
        loaded prints no cashier rather than the wrong one.
        """
        try:
            user = getattr(sale, "user", None)
        except Exception as e:  # detached sale, relationship not eager-loaded
            logger.warning("Receipt for %s: cashier not loaded (%s)", getattr(sale, "document_number", "?"), e)
            return ""
        if user is not None:
            return getattr(user, "username", "") or ""
        if getattr(sale, "user_id", None) is None:
            return cls._get_current_cashier_name()
        return ""
