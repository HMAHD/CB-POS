import os
from typing import List, Dict, Any
from cbpos.core.models import Sale, SaleItem
from cbpos.core.services.config_service import ConfigService


class ReceiptBuilder:
    """
    Builds the receipt content as a list of commands for the printer driver.
    Commands:
    - {'type': 'text', 'val': '...', 'align': 'left|center|right'}
    - {'type': 'image', 'path': '...'}
    - {'type': 'barcode', 'val': '...', 'type': 'CODE39|QR'}
    - {'type': 'feed', 'lines': 1}
    - {'type': 'cut'}
    """

    WIDTH = 42  # Standard 80mm thermal printer width (approx 42-48 chars)

    @staticmethod
    def build_receipt(sale: Sale) -> List[Dict[str, Any]]:
        """
        Generate the receipt commands.
        """
        commands = []
        config = ConfigService.get_all()

        # 1. Logo
        logo_path = config.get("receipt_logo_path")
        if logo_path and os.path.exists(logo_path):
            commands.append({"type": "image", "path": logo_path})

        # 2. Header
        header_text = config.get("receipt_header", "Welcome to Ceylon Byte")
        if header_text:
            for line in header_text.split("\n"):
                commands.append({"type": "text", "val": line, "align": "center"})

        commands.append(
            {"type": "text", "val": "-" * ReceiptBuilder.WIDTH, "align": "center"}
        )

        # 3. Items
        merge_items = config.get("merge_items", True)
        items = ReceiptBuilder._merge_items(sale.items) if merge_items else sale.items

        for item in items:
            # Truncate name if too long
            name = item.product.name_en[:20]
            name_col = "{:<20}".format(name)
            qty_col = "{:>5.0f}".format(item.qty)
            price_col = "{:>7.2f}".format(item.unit_price)
            total_col = "{:>8.2f}".format(item.subtotal)
            line = "{} {} {} {}".format(name_col, qty_col, price_col, total_col)
            commands.append({"type": "text", "val": line, "align": "left"})

        commands.append(
            {"type": "text", "val": "-" * ReceiptBuilder.WIDTH, "align": "center"}
        )

        # 4. Totals
        commands.append(
            {
                "type": "text",
                "val": "{:<20} {:>21.2f}".format("TOTAL", sale.total_amount),
                "align": "left",
            }
        )
        commands.append(
            {"type": "text", "val": "-" * ReceiptBuilder.WIDTH, "align": "center"}
        )

        # 5. Tax Breakdown
        if config.get("show_tax_breakdown", True):
            commands.append(
                {"type": "text", "val": "*** TAX BREAKDOWN ***", "align": "center"}
            )
            commands.append(
                {
                    "type": "text",
                    "val": "{:<20} {:>21.2f}".format("VAT (18%)", sale.tax_vat or 0),
                    "align": "left",
                }
            )
            commands.append(
                {
                    "type": "text",
                    "val": "{:<20} {:>21.2f}".format("SSCL (2.5%)", sale.tax_sscl or 0),
                    "align": "left",
                }
            )
            commands.append(
                {
                    "type": "text",
                    "val": "{:<20} {:>21.2f}".format(
                        "Net Revenue", sale.net_revenue or 0
                    ),
                    "align": "left",
                }
            )
            commands.append(
                {"type": "text", "val": "-" * ReceiptBuilder.WIDTH, "align": "center"}
            )

        # 6. Footer
        footer_text = config.get("receipt_footer", "Thank You! Come Again.")
        if footer_text:
            for line in footer_text.split("\n"):
                commands.append({"type": "text", "val": line, "align": "center"})

        commands.append(
            {"type": "text", "val": "Software by Ceylon Byte", "align": "center"}
        )

        # 7. Barcode
        if config.get("show_barcode", True) and sale.id:
            # Use sale ID or a document number if available
            doc_num = str(sale.id).zfill(8)
            commands.append({"type": "barcode", "val": doc_num, "code": "CODE39"})

        commands.append({"type": "feed", "lines": 3})
        commands.append({"type": "cut"})

        return commands

    @staticmethod
    def _merge_items(items: List[SaleItem]) -> List[SaleItem]:
        """
        Merge duplicate items (same product_id) for display.
        Returns a list of temporary SaleItem-like objects or modifies them.
        Since SaleItem is an SQLAlchemy model, we shouldn't modify the actual instances attached to session.
        We'll create simple objects or dictionaries for display.
        Actually, to keep it simple and type-safe, let's return a list of objects that have the necessary attributes.
        """
        merged = {}
        for item in items:
            pid = item.product_id
            if pid in merged:
                merged[pid].qty += item.qty
                merged[pid].subtotal += item.subtotal
            else:
                # Create a copy or a simple object
                # We can't easily clone SQLAlchemy objects that are attached to a session without issues.
                # So we'll use a simple class or just modify the first occurrence if we are careful not to commit.
                # Better: Create a dummy object.
                merged[pid] = ItemDisplay(
                    product=item.product,
                    qty=item.qty,
                    unit_price=item.unit_price,
                    subtotal=item.subtotal,
                )
        return list(merged.values())


class ItemDisplay:
    def __init__(self, product, qty, unit_price, subtotal):
        self.product = product
        self.qty = qty
        self.unit_price = unit_price
        self.subtotal = subtotal
