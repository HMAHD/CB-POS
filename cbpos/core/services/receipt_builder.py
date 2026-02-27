from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from cbpos.core.services.config_service import ConfigService
from cbpos.core.models import Sale, SaleItem


from cbpos.core.utils.formatters import format_currency

if TYPE_CHECKING:
    from cbpos.core.models import Customer, CustomerLedgerEntry, Proforma


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
        commands.append({"type": "text", "val": f"Receipt #: {sale.id}", "align": "left"})
        date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
        commands.append(
            {
                "type": "text",
                "val": f"Date: {date_str}",
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
                "val": "Total: {}".format(format_currency(sale.total_amount)),
                "align": "right",
            }
        )

        # Tax Breakdown
        if get_conf("show_tax_breakdown", True):
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": "Tax Breakdown:", "align": "left"})
            if sale.tax_vat > 0:
                commands.append(
                    {
                        "type": "text",
                        "val": "VAT: {}".format(format_currency(sale.tax_vat)),
                        "align": "right",
                    }
                )
            if sale.tax_sscl > 0:
                commands.append(
                    {
                        "type": "text",
                        "val": "SSCL: {}".format(format_currency(sale.tax_sscl)),
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
