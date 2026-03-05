import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from cbpos.core.services.config_service import ConfigService
from cbpos.core.models import Sale, SaleItem


from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cbpos.core.models import Customer, CustomerLedgerEntry, Proforma


RECEIPT_STRINGS = {
    "en": {
        "receipt_no": "Receipt #",
        "date": "Date",
        "total": "Total",
        "tax_breakdown": "Tax Breakdown",
        "vat": "VAT",
        "sscl": "SSCL",
        "quotation": "*** QUOTATION ***",
        "customer": "Customer",
        "valid_until": "Valid Until",
        "statement": "*** CUSTOMER STATEMENT ***",
        "phone": "Phone",
        "period": "Period",
        "opening_balance": "Opening Balance",
        "total_sales": "Total Sales",
        "total_payments": "Total Payments",
        "closing_balance": "Closing Balance",
        "thank_you": "Thank you for your business",
        "cashier": "Cashier",
        "terminal": "Terminal",
        "tin": "TIN",
        "authorized_by": "Authorized by",
        "void_reason": "Reason",
        "original_receipt": "Original Receipt",
    },
    "si": {
        "receipt_no": "\u0dbb\u0dc3\u0dd2\u0daf\u0db4\u0dad #",
        "date": "\u0daf\u0dd2\u0db1\u0dba",
        "total": "\u0d91\u0d9a\u0dad\u0dd4",
        "tax_breakdown": "\u0db6\u0daf\u0dd4 \u0dc0\u0dd2\u0dc3\u0dca\u0dad\u0dbb\u0dba",
        "vat": "\u0dc0\u0dd0\u0da7\u0dca",
        "sscl": "\u0d91\u0dc3\u0dca\u0d91\u0dc3\u0dca\u0dc3\u0dd2\u0d91\u0dca\u0d91\u0dca\u0dbd\u0dca",
        "quotation": "*** \u0db4\u0dca\u200d\u0dbb\u0dc3\u0dca\u0dad\u0dcf\u0dc0\u0db1\u0dba ***",
        "customer": "\u0db4\u0dcf\u0dbb\u0dd2\u0db7\u0ddd\u0d9c\u0dd2\u0d9a\u0dba\u0dcf",
        "valid_until": "\u0dc0\u0dbd\u0d82\u0d9c\u0dd4 \u0daf\u0dd2\u0db1\u0dba",
        "statement": "*** \u0d9c\u0dd2\u0dab\u0dd4\u0db8\u0dca \u0dc0\u0dd2\u0dc0\u0dbb\u0dab\u0dba ***",
        "phone": "\u0daf\u0dd4\u0dbb\u0d9a\u0dae\u0db1",
        "period": "\u0d9a\u0dcf\u0dbd\u0dba",
        "opening_balance": "\u0d86\u0dbb\u0db8\u0dca\u0db7\u0d9a \u0dc3\u0dd2\u0dbd\u0dca\u0dbd",
        "total_sales": "\u0d91\u0d9a\u0dad\u0dd4 \u0dc0\u0dd2\u0d9a\u0dd2\u0dab\u0dd3\u0db8\u0dca",
        "total_payments": "\u0d91\u0d9a\u0dad\u0dd4 \u0d9c\u0dd9\u0dc0\u0dd3\u0db8\u0dca",
        "closing_balance": "\u0d85\u0dc0\u0dc3\u0db1\u0dca \u0dc3\u0dd2\u0dbd\u0dca\u0dbd",
        "thank_you": (  # noqa: E501
            "\u0d94\u0db6\u0d9c\u0dda \u0dc0\u0dca\u200d\u0dba\u0dcf\u0db4\u0dcf\u0dbb\u0dba\u0da7"
            " \u0dc3\u0dca\u0dad\u0dd4\u0dad\u0dd2\u0dba\u0dd2"
        ),
        "cashier": "\u0db8\u0dd4\u0daf\u0dbd\u0dca\u0d9a\u0dbb\u0dd4",
        "terminal": "\u0da7\u0dd6\u0dbb\u0dca\u0db8\u0dd2\u0db1\u0dbd\u0dca",
        "tin": "TIN",
        "authorized_by": "\u0d85\u0db0\u0dd2\u0d9a\u0dcf\u0dbb\u0dba",
        "void_reason": "\u0dc4\u0dda\u0dad\u0dd4\u0dc0",
        "original_receipt": "\u0db8\u0dd6\u0dbd\u0dd2\u0d9a \u0dbb\u0dc3\u0dd2\u0daf\u0db4\u0dad",
    },
    "ta": {
        "receipt_no": "\u0bb0\u0b9a\u0bc0\u0ba4\u0bc1 #",
        "date": "\u0ba4\u0bc7\u0ba4\u0bbf",
        "total": "\u0bae\u0bca\u0ba4\u0bcd\u0ba4\u0bae\u0bcd",
        "tax_breakdown": "\u0bb5\u0bb0\u0bbf \u0bb5\u0bbf\u0baa\u0bb0\u0bae\u0bcd",
        "vat": "\u0bb5\u0bb0\u0bbf",
        "sscl": "\u0b8e\u0bb8\u0bcd\u0b8e\u0bb8\u0bcd\u0b9a\u0bbf\u0b8e\u0bb2\u0bcd",
        "quotation": "*** \u0bae\u0bc7\u0bb1\u0bcd\u0b95\u0bcb\u0bb3\u0bcd ***",
        "customer": "\u0ba8\u0bc1\u0b95\u0bb0\u0bcd\u0bb5\u0bcb\u0bb0\u0bcd",
        "valid_until": "\u0b9a\u0bc6\u0bb2\u0bcd\u0bb2\u0bc1\u0baa\u0b9f\u0bbf \u0ba4\u0bc7\u0ba4\u0bbf",
        "statement": "*** \u0b95\u0ba3\u0b95\u0bcd\u0b95\u0bc1 \u0b85\u0bb1\u0bbf\u0b95\u0bcd\u0b95\u0bc8 ***",
        "phone": "\u0ba4\u0bca\u0bb2\u0bc8\u0baa\u0bcd\u0baa\u0bc7\u0b9a\u0bbf",
        "period": "\u0b95\u0bbe\u0bb2\u0bae\u0bcd",
        "opening_balance": "\u0ba4\u0bca\u0b9f\u0b95\u0bcd\u0b95 \u0b87\u0bb0\u0bc1\u0baa\u0bcd\u0baa\u0bc1",
        "total_sales": "\u0bae\u0bca\u0ba4\u0bcd\u0ba4 \u0bb5\u0bbf\u0bb1\u0bcd\u0baa\u0ba9\u0bc8",
        "total_payments": "\u0bae\u0bca\u0ba4\u0bcd\u0ba4 \u0b9a\u0bc6\u0bb2\u0bc1\u0ba4\u0bcd\u0ba4\u0bb2\u0bcd",
        "closing_balance": "\u0b87\u0bb1\u0bc1\u0ba4\u0bbf \u0b87\u0bb0\u0bc1\u0baa\u0bcd\u0baa\u0bc1",
        "thank_you": "\u0ba8\u0ba9\u0bcd\u0bb1\u0bbf",
        "cashier": "\u0b95\u0bbe\u0b9a\u0bbf\u0baf\u0bb0\u0bcd",
        "terminal": "\u0b9f\u0bc6\u0bb0\u0bcd\u0bae\u0bbf\u0ba9\u0bb2\u0bcd",
        "tin": "TIN",
        "authorized_by": "\u0b85\u0ba9\u0bc1\u0bae\u0ba4\u0bbf",
        "void_reason": "\u0b95\u0bbe\u0bb0\u0ba3\u0bae\u0bcd",
        "original_receipt": "\u0b85\u0b9a\u0bb2\u0bcd \u0bb0\u0b9a\u0bc0\u0ba4\u0bc1",
    },
}


class ReceiptBuilder:
    """
    Builds a list of command objects for printing or previewing receipts.
    Commands are device-agnostic dictionaries:
    - {'type': 'text', 'val': '...', 'align': 'left|center|right'}
    - {'type': 'image', 'path': '...'}
    - {'type': 'barcode', 'val': '...', 'code': 'CODE39|QR'}
    - {'type': 'feed', 'lines': 1}
    - {'type': 'cut', 'partial': True}
    """

    @classmethod
    def _get_strings(cls, config_override: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Get translated receipt strings based on current language."""
        lang = "en"
        if config_override and "language" in config_override:
            lang = config_override["language"]
        else:
            val = ConfigService.get("language")
            if val:
                lang = val
        return RECEIPT_STRINGS.get(lang, RECEIPT_STRINGS["en"])

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
        """Append logo + header + TIN. Returns line_chars for the paper width."""
        paper_width = cls._get_conf("paper_width", "80mm", config_override)
        line_chars = 32 if paper_width == "58mm" else 42

        # Logo
        logo_path = cls._get_conf("receipt_logo_path", "", config_override)
        if logo_path:
            commands.append({"type": "image", "path": logo_path})

        # Header text
        header_text = cls._get_conf("receipt_header", "", config_override)
        if header_text:
            commands.append({"type": "text", "val": header_text, "align": "center"})

        # Shop TIN / VAT number
        tax_id = cls._get_conf("company_tax_id", "", config_override)
        if tax_id:
            t = cls._get_strings(config_override)
            commands.append({"type": "text", "val": f"{t['tin']}: {tax_id}", "align": "center"})

        if header_text or tax_id:
            commands.append({"type": "feed", "lines": 1})

        return line_chars

    @classmethod
    def build_receipt(
        cls,
        sale: Sale,
        config_override: Optional[Dict[str, Any]] = None,
        is_reprint: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Generates receipt commands for a given Sale.

        Args:
            sale: The Sale model instance.
            config_override: Optional dictionary to override ConfigService values.
            is_reprint: If True, adds DUPLICATE marking.
        """
        commands: List[Dict[str, Any]] = []
        gc = cls._get_conf

        # Duplicate marking (top)
        if is_reprint:
            commands.append({"type": "text", "val": "*** DUPLICATE — NOT FOR PAYMENT ***", "align": "center"})
            commands.append({"type": "feed", "lines": 1})

        # Header block (logo, header text, TIN)
        line_chars = cls._append_header_block(commands, config_override)

        # Sale Details
        t = cls._get_strings(config_override)
        doc_num = getattr(sale, "document_number", None) or str(sale.id)
        commands.append({"type": "text", "val": f"{t['receipt_no']}: {doc_num}", "align": "left"})
        date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
        commands.append({"type": "text", "val": f"{t['date']}: {date_str}", "align": "left"})

        # Cashier name
        if gc("show_cashier_on_receipt", True, config_override):
            cashier_name = cls._get_current_cashier_name()
            if cashier_name:
                commands.append({"type": "text", "val": f"{t['cashier']}: {cashier_name}", "align": "left"})

        # Terminal ID
        if gc("show_terminal_on_receipt", False, config_override):
            terminal_id = gc("terminal_id", "", config_override)
            if terminal_id:
                commands.append({"type": "text", "val": f"{t['terminal']}: {terminal_id}", "align": "left"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Items
        merge = gc("merge_items", True, config_override)
        display_items = cls._merge_items(sale.items) if merge else sale.items

        for item in display_items:
            product_name = item.product.name_en if hasattr(item, "product") else item.name
            commands.append({"type": "text", "val": product_name, "align": "left"})

            qty = item.qty
            price = item.unit_price
            total = item.subtotal
            line = "{} x {} = {}".format(qty, format_currency(price), format_currency(total))
            commands.append({"type": "text", "val": line, "align": "right"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Totals
        commands.append(
            {
                "type": "text",
                "val": "{}: {}".format(t["total"], format_currency(sale.total_amount)),
                "align": "right",
            }
        )

        # Tax Breakdown
        if gc("show_tax_breakdown", True, config_override):
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": "{}:".format(t["tax_breakdown"]), "align": "left"})
            if sale.tax_vat > 0:
                commands.append(
                    {
                        "type": "text",
                        "val": "{}: {}".format(t["vat"], format_currency(sale.tax_vat)),
                        "align": "right",
                    }
                )
            if sale.tax_sscl > 0:
                commands.append(
                    {
                        "type": "text",
                        "val": "{}: {}".format(t["sscl"], format_currency(sale.tax_sscl)),
                        "align": "right",
                    }
                )

        # Payment Breakdown
        if hasattr(sale, "payments") and sale.payments:
            commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})
            for pmt in sale.payments:
                label = pmt.payment_method
                amt = format_currency(pmt.amount)
                pad = line_chars - len(label) - len(amt)
                commands.append(
                    {
                        "type": "text",
                        "val": "{}{}{}".format(label, " " * max(pad, 1), amt),
                        "align": "left",
                    }
                )
            # Change
            total_paid = sum(p.amount for p in sale.payments)
            if total_paid > sale.total_amount:
                change = total_paid - sale.total_amount
                label = "Change"
                amt = format_currency(change)
                pad = line_chars - len(label) - len(amt)
                commands.append(
                    {
                        "type": "text",
                        "val": "{}{}{}".format(label, " " * max(pad, 1), amt),
                        "align": "left",
                    }
                )

        # Footer
        commands.append({"type": "feed", "lines": 1})
        footer_text = gc("receipt_footer", "", config_override)
        if footer_text:
            commands.append({"type": "text", "val": footer_text, "align": "center"})

        # Barcode
        if gc("show_barcode", True, config_override):
            commands.append({"type": "feed", "lines": 1})
            commands.append(
                {
                    "type": "barcode",
                    "val": str(sale.id),
                    "code": "CODE39",
                    "align": "center",
                }
            )

        # QR Code
        if gc("show_qr_on_receipt", False, config_override):
            qr_content = gc("receipt_qr_content", "", config_override)
            if qr_content:
                commands.append({"type": "feed", "lines": 1})
                commands.append(
                    {
                        "type": "barcode",
                        "val": qr_content,
                        "code": "QR",
                        "align": "center",
                    }
                )

        # Duplicate marking (bottom)
        if is_reprint:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": "*** DUPLICATE — NOT FOR PAYMENT ***", "align": "center"})

        # Branding + Cut
        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands

    @classmethod
    def build_void_receipt(
        cls,
        sale: Sale,
        void_reason: str = "",
        authorized_by: str = "",
        config_override: Optional[Dict[str, Any]] = None,
        void_timestamp: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generates a VOID receipt with distinct visual treatment.

        Args:
            sale: The voided Sale.
            void_reason: Human-readable void reason.
            authorized_by: Username who authorized the void.
            config_override: Optional config overrides.
            void_timestamp: Timestamp for the void (defaults to now).
        """
        commands: List[Dict[str, Any]] = []
        t = cls._get_strings(config_override)

        line_chars = cls._append_header_block(commands, config_override)

        # VOID header
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "text", "val": "*** VOIDED ***", "align": "center"})
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Original sale reference
        doc_num = getattr(sale, "document_number", None) or str(sale.id)
        commands.append({"type": "text", "val": f"{t['original_receipt']}: {doc_num}", "align": "left"})
        date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
        commands.append({"type": "text", "val": f"{t['date']}: {date_str}", "align": "left"})
        commands.append(
            {
                "type": "text",
                "val": "{}: {}".format(t["total"], format_currency(sale.total_amount)),
                "align": "left",
            }
        )

        if void_reason:
            commands.append({"type": "text", "val": f"{t['void_reason']}: {void_reason}", "align": "left"})
        if authorized_by:
            commands.append({"type": "text", "val": f"{t['authorized_by']}: {authorized_by}", "align": "left"})

        void_time_obj = void_timestamp or datetime.now()
        void_time = void_time_obj.strftime("%Y-%m-%d %H:%M")
        commands.append({"type": "text", "val": f"Void Time: {void_time}", "align": "left"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Items (for reference)
        for item in sale.items:
            product_name = item.product.name_en if hasattr(item, "product") and item.product else "Unknown"
            line = "{} x {} = {}".format(item.qty, format_currency(item.unit_price), format_currency(item.subtotal))
            commands.append({"type": "text", "val": product_name, "align": "left"})
            commands.append({"type": "text", "val": line, "align": "right"})

        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "text", "val": "*** VOIDED ***", "align": "center"})
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands

    @classmethod
    def build_refund_receipt(
        cls,
        sale: Sale,
        refund_amount: Optional[Decimal] = None,
        authorized_by: str = "",
        config_override: Optional[Dict[str, Any]] = None,
        refund_timestamp: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generates a REFUND receipt with distinct visual treatment.

        Args:
            sale: The original Sale being refunded.
            refund_amount: Amount refunded (defaults to sale total).
            authorized_by: Username who authorized the refund.
            config_override: Optional config overrides.
            refund_timestamp: Timestamp for the refund (defaults to now).
        """
        commands: List[Dict[str, Any]] = []
        t = cls._get_strings(config_override)

        line_chars = cls._append_header_block(commands, config_override)

        # REFUND header
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "text", "val": "*** REFUND ***", "align": "center"})
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Original sale reference
        doc_num = getattr(sale, "document_number", None) or str(sale.id)
        commands.append({"type": "text", "val": f"{t['original_receipt']}: {doc_num}", "align": "left"})
        date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
        commands.append({"type": "text", "val": f"{t['date']}: {date_str}", "align": "left"})

        if authorized_by:
            commands.append({"type": "text", "val": f"{t['authorized_by']}: {authorized_by}", "align": "left"})

        refund_time_obj = refund_timestamp or datetime.now()
        refund_time = refund_time_obj.strftime("%Y-%m-%d %H:%M")
        commands.append({"type": "text", "val": f"Refund Time: {refund_time}", "align": "left"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Items
        for item in sale.items:
            product_name = item.product.name_en if hasattr(item, "product") and item.product else "Unknown"
            line = "{} x {} = {}".format(item.qty, format_currency(item.unit_price), format_currency(item.subtotal))
            commands.append({"type": "text", "val": product_name, "align": "left"})
            commands.append({"type": "text", "val": line, "align": "right"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        amount = refund_amount if refund_amount is not None else sale.total_amount
        commands.append(
            {
                "type": "text",
                "val": "Refund {}: {}".format(t["total"], format_currency(amount)),
                "align": "right",
            }
        )

        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "text", "val": "*** REFUND ***", "align": "center"})
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands

    @classmethod
    def build_proforma(
        cls, proforma: "Proforma", config_override: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates receipt commands for a Proforma/Quotation.

        Args:
            proforma: The Proforma model instance with items loaded.
            config_override: Optional dictionary to override ConfigService values.
        """
        commands: List[Dict[str, Any]] = []
        gc = cls._get_conf

        line_chars = cls._append_header_block(commands, config_override)

        # Title
        commands.append({"type": "text", "val": "*** QUOTATION ***", "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Proforma Details
        commands.append({"type": "text", "val": f"Quotation #: {proforma.document_number}", "align": "left"})
        date_str = proforma.date.strftime("%Y-%m-%d %H:%M") if proforma.date else "N/A"
        commands.append({"type": "text", "val": f"Date: {date_str}", "align": "left"})

        if proforma.expiry_date:
            commands.append({"type": "text", "val": f"Valid Until: {proforma.expiry_date}", "align": "left"})

        if proforma.customer:
            commands.append({"type": "text", "val": f"Customer: {proforma.customer.name}", "align": "left"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Items
        for item in proforma.items:
            commands.append({"type": "text", "val": item.product_name, "align": "left"})
            line = "{} x {} = {}".format(
                item.quantity,
                format_currency(item.unit_price),
                format_currency(item.line_total),
            )
            commands.append({"type": "text", "val": line, "align": "right"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Total
        commands.append(
            {
                "type": "text",
                "val": "Total: {}".format(format_currency(proforma.total_amount)),
                "align": "right",
            }
        )

        # Tax Breakdown
        if gc("show_tax_breakdown", True, config_override):
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": "Tax Breakdown:", "align": "left"})
            if proforma.tax_vat and proforma.tax_vat > 0:
                commands.append(
                    {"type": "text", "val": "VAT: {}".format(format_currency(proforma.tax_vat)), "align": "right"}
                )
            if proforma.tax_sscl and proforma.tax_sscl > 0:
                commands.append(
                    {"type": "text", "val": "SSCL: {}".format(format_currency(proforma.tax_sscl)), "align": "right"}
                )

        # Notes
        if proforma.notes:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": f"Notes: {proforma.notes}", "align": "left"})

        # Footer
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": "This is a quotation, not a tax invoice.", "align": "center"})
        commands.append({"type": "text", "val": f"Valid for {proforma.validity_days} days.", "align": "center"})

        footer_text = gc("receipt_footer", "", config_override)
        if footer_text:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": footer_text, "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands

    @classmethod
    def build_customer_statement(
        cls,
        customer: "Customer",
        entries: List["CustomerLedgerEntry"],
        period_from: datetime,
        period_to: datetime,
        config_override: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generates receipt commands for a customer credit statement.

        Args:
            customer: The Customer model instance.
            entries: List of CustomerLedgerEntry objects.
            period_from: Statement start date.
            period_to: Statement end date.
            config_override: Optional dictionary to override ConfigService values.
        """
        commands: List[Dict[str, Any]] = []
        gc = cls._get_conf

        line_chars = cls._append_header_block(commands, config_override)

        # Title
        commands.append({"type": "text", "val": "*** CUSTOMER STATEMENT ***", "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Customer Info
        commands.append({"type": "text", "val": f"Customer: {customer.name}", "align": "left"})
        if customer.phone:
            commands.append({"type": "text", "val": f"Phone: {customer.phone}", "align": "left"})

        # Period
        from_str = period_from.strftime("%Y-%m-%d")
        to_str = period_to.strftime("%Y-%m-%d")
        commands.append({"type": "text", "val": f"Period: {from_str} to {to_str}", "align": "left"})
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Opening Balance
        if entries:
            opening = entries[0].balance_after - entries[0].amount
        else:
            opening = customer.current_debt

        commands.append({"type": "text", "val": f"Opening Balance: {format_currency(opening)}", "align": "left"})
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Entries
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        for entry in entries:
            date_str = entry.timestamp.strftime("%m/%d") if entry.timestamp else ""
            doc = entry.reference_doc or entry.note or entry.entry_type

            if entry.amount > 0:
                line = f"{date_str} {doc:<20} +{entry.amount:.2f}"  # noqa: E231
                total_debit += entry.amount
            else:
                line = f"{date_str} {doc:<20} {entry.amount:.2f}"  # noqa: E231
                total_credit += abs(entry.amount)

            commands.append({"type": "text", "val": line, "align": "left"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Totals
        commands.append({"type": "text", "val": f"Total Sales: {format_currency(total_debit)}", "align": "right"})
        commands.append({"type": "text", "val": f"Total Payments: {format_currency(total_credit)}", "align": "right"})

        # Closing Balance
        closing = entries[-1].balance_after if entries else customer.current_debt
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": f"Closing Balance: {format_currency(closing)}", "align": "right"})

        # Footer
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": "Thank you for your business", "align": "center"})

        footer_text = gc("receipt_footer", "", config_override)
        if footer_text:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": footer_text, "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands

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

    @staticmethod
    def _merge_items(items: List[SaleItem]) -> List[Any]:
        """
        Merges SaleItems with the same product_id.
        Returns a list of objects with product, qty, unit_price, subtotal attributes.
        """
        merged = {}
        for item in items:
            pid = item.product_id
            if pid in merged:
                merged[pid].qty += item.qty
                merged[pid].subtotal += item.subtotal
            else:
                merged[pid] = ItemDisplay(
                    product=item.product,
                    qty=item.qty,
                    unit_price=item.unit_price,
                    subtotal=item.subtotal,
                    name=item.product.name_en,
                )
        return list(merged.values())


class ItemDisplay:
    """Helper class for merged items display"""

    def __init__(self, product: Any, qty: Any, unit_price: Any, subtotal: Any, name: str) -> None:
        self.product = product
        self.qty = qty
        self.unit_price = unit_price
        self.subtotal = subtotal
        self.name = name
