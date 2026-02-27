from typing import List, Dict, Any, Optional
from cbpos.core.services.config_service import ConfigService
from cbpos.core.models import Sale, SaleItem


from cbpos.core.utils.formatters import format_currency


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

        # 8. Cut
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
