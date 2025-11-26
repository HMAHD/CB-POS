from cbpos.core.models import Sale


class ReceiptBuilder:
    """
    Builds the text content for receipts.
    """

    WIDTH = 42  # Standard 80mm thermal printer width (approx 42-48 chars)

    @staticmethod
    def build_receipt(sale: Sale) -> str:
        """
        Generate the complete receipt text.
        """
        lines = []

        # 1. Header
        lines.append(ReceiptBuilder._center("CEYLON BYTE POS"))
        lines.append("-" * ReceiptBuilder.WIDTH)

        for item in sale.items:
            # Truncate name if too long
            name = item.product.name_en[:20]
            name_col = "{:<20}".format(name)
            qty_col = "{:>5.0f}".format(item.qty)
            price_col = "{:>7.2f}".format(item.unit_price)
            total_col = "{:>8.2f}".format(item.subtotal)
            lines.append("{} {} {} {}".format(name_col, qty_col, price_col, total_col))

        lines.append("-" * ReceiptBuilder.WIDTH)

        # 4. Totals
        lines.append("{:<20} {:>21.2f}".format("TOTAL", sale.total_amount))
        lines.append("-" * ReceiptBuilder.WIDTH)

        # 5. Tax Breakdown (Backward Calc)
        # Assuming sale.tax_vat and sale.tax_sscl are populated
        lines.append(ReceiptBuilder._center("*** TAX BREAKDOWN ***"))
        lines.append("{:<20} {:>21.2f}".format("VAT (18%)", sale.tax_vat))
        lines.append("{:<20} {:>21.2f}".format("SSCL (2.5%)", sale.tax_sscl))
        lines.append("{:<20} {:>21.2f}".format("Net Revenue", sale.net_revenue))
        lines.append("-" * ReceiptBuilder.WIDTH)

        # 6. Footer
        lines.append(ReceiptBuilder._center("Thank You! Come Again."))
        lines.append(ReceiptBuilder._center("Software by Ceylon Byte"))
        lines.append("\n\n")  # Feed

        return "\n".join(lines)

    @staticmethod
    def _center(text: str) -> str:
        return text.center(ReceiptBuilder.WIDTH)
