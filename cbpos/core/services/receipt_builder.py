from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from cbpos.core.services.config_service import ConfigService
from cbpos.core.models import Sale, SaleItem


from cbpos.core.utils.formatters import format_currency

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
        "thank_you": "\u0d94\u0db6\u0d9c\u0dda \u0dc0\u0dca\u200d\u0dba\u0dcf\u0db4\u0dcf\u0dbb\u0dba\u0da7 \u0dc3\u0dca\u0dad\u0dd4\u0dad\u0dd2\u0dba\u0dd2",
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
    - {'type': 'cut'}
    """

    @classmethod
    def _get_strings(cls, config_override=None):
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
    def build_receipt(cls, sale: Sale, config_override: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Generates receipt commands for a given Sale.

        Args:
            sale: The Sale model instance.
            config_override: Optional dictionary to override ConfigService values.
        """
        commands = []

        # Helper to get config value with override support
        def get_conf(key, default=None):
            if config_override and key in config_override:
                return config_override[key]
            val = ConfigService.get(key)
            return val if val is not None else default

        # Determine line width from paper_width config
        paper_width = get_conf("paper_width", "80mm")
        line_chars = 32 if paper_width == "58mm" else 42

        # 1. Logo
        logo_path = get_conf("receipt_logo_path", "")
        if logo_path:
            commands.append({"type": "image", "path": logo_path})

        # 2. Header
        header_text = get_conf("receipt_header", "")
        if header_text:
            commands.append({"type": "text", "val": header_text, "align": "center"})
            commands.append({"type": "feed", "lines": 1})

        # 3. Sale Details
        t = cls._get_strings(config_override)
        commands.append({"type": "text", "val": f"{t['receipt_no']}: {sale.id}", "align": "left"})
        date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
        commands.append(
            {
                "type": "text",
                "val": f"{t['date']}: {date_str}",
                "align": "left",
            }
        )
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # 4. Items
        merge = get_conf("merge_items", True)
        display_items = cls._merge_items(sale.items) if merge else sale.items

        for item in display_items:
            # Name line
            product_name = item.product.name_en if hasattr(item, "product") else item.name
            commands.append({"type": "text", "val": product_name, "align": "left"})

            # Qty x Price = Total line
            qty = item.qty
            price = item.unit_price
            total = item.subtotal
            line = "{} x {} = {}".format(qty, format_currency(price), format_currency(total))
            commands.append({"type": "text", "val": line, "align": "right"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # 5. Totals
        commands.append(
            {
                "type": "text",
                "val": "{}: {}".format(t["total"], format_currency(sale.total_amount)),
                "align": "right",
            }
        )

        # Tax Breakdown
        if get_conf("show_tax_breakdown", True):
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

        # 6. Footer
        commands.append({"type": "feed", "lines": 1})
        footer_text = get_conf("receipt_footer", "")
        if footer_text:
            commands.append({"type": "text", "val": footer_text, "align": "center"})

        # 7. Barcode
        if get_conf("show_barcode", True):
            commands.append({"type": "feed", "lines": 1})
            commands.append(
                {
                    "type": "barcode",
                    "val": str(sale.id),
                    "code": "CODE39",
                    "align": "center",
                }
            )

        # 8. Branding
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": "Powered by CB POS", "align": "center"})
        commands.append({"type": "text", "val": "ceybyte.com", "align": "center"})

        # 9. Cut
        commands.append({"type": "feed", "lines": 2})
        commands.append({"type": "cut"})

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

        def get_conf(key: str, default: Any = None) -> Any:
            if config_override and key in config_override:
                return config_override[key]
            val = ConfigService.get(key)
            return val if val is not None else default

        paper_width = get_conf("paper_width", "80mm")
        line_chars = 32 if paper_width == "58mm" else 42

        # Logo
        logo_path = get_conf("receipt_logo_path", "")
        if logo_path:
            commands.append({"type": "image", "path": logo_path})

        # Header
        header_text = get_conf("receipt_header", "")
        if header_text:
            commands.append({"type": "text", "val": header_text, "align": "center"})
            commands.append({"type": "feed", "lines": 1})

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
        if get_conf("show_tax_breakdown", True):
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

        footer_text = get_conf("receipt_footer", "")
        if footer_text:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": footer_text, "align": "center"})

        # Branding
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": "Powered by CB POS", "align": "center"})
        commands.append({"type": "text", "val": "ceybyte.com", "align": "center"})

        commands.append({"type": "feed", "lines": 2})
        commands.append({"type": "cut"})

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

        def get_conf(key: str, default: Any = None) -> Any:
            if config_override and key in config_override:
                return config_override[key]
            val = ConfigService.get(key)
            return val if val is not None else default

        paper_width = get_conf("paper_width", "80mm")
        line_chars = 32 if paper_width == "58mm" else 42

        # Logo
        logo_path = get_conf("receipt_logo_path", "")
        if logo_path:
            commands.append({"type": "image", "path": logo_path})

        # Header
        header_text = get_conf("receipt_header", "")
        if header_text:
            commands.append({"type": "text", "val": header_text, "align": "center"})
            commands.append({"type": "feed", "lines": 1})

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

        # Opening Balance (balance before first entry, or 0)
        if entries:
            opening = entries[0].balance_after - entries[0].amount
        else:
            opening = customer.current_debt

        commands.append({"type": "text", "val": f"Opening Balance: {format_currency(opening)}", "align": "left"})
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Entries
        total_debit = 0
        total_credit = 0
        for entry in entries:
            date_str = entry.timestamp.strftime("%m/%d") if entry.timestamp else ""
            doc = entry.reference_doc or entry.note or entry.entry_type

            if entry.amount > 0:
                line = f"{date_str} {doc:<20} +{entry.amount:.2f}"
                total_debit += float(entry.amount)
            else:
                line = f"{date_str} {doc:<20} {entry.amount:.2f}"
                total_credit += abs(float(entry.amount))

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

        footer_text = get_conf("receipt_footer", "")
        if footer_text:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": footer_text, "align": "center"})

        # Branding
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": "Powered by CB POS", "align": "center"})
        commands.append({"type": "text", "val": "ceybyte.com", "align": "center"})

        commands.append({"type": "feed", "lines": 2})
        commands.append({"type": "cut"})

        return commands

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
                # Create a simple object or clone to avoid modifying original SaleItems
                # We use a simple class or dict wrapper for display
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

    def __init__(self, product, qty, unit_price, subtotal, name):
        self.product = product
        self.qty = qty
        self.unit_price = unit_price
        self.subtotal = subtotal
        self.name = name
