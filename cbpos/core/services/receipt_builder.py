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
            lines.append(
                f"{name:<20} {item.qty:>5.0f} {item.unit_price:>7.2f} {item.subtotal:>8.2f}"  # noqa: E231
            )

        lines.append("-" * ReceiptBuilder.WIDTH)

        # 4. Totals
        lines.append(f"{'TOTAL':<20} {sale.total_amount:>21.2f}")  # noqa: E231
        lines.append("-" * ReceiptBuilder.WIDTH)

        # 5. Tax Breakdown (Backward Calc)
        # Assuming sale.tax_vat and sale.tax_sscl are populated
        lines.append(ReceiptBuilder._center("*** TAX BREAKDOWN ***"))
        lines.append(f"{'VAT (18%)':<20} {sale.tax_vat:>21.2f}")  # noqa: E231
        lines.append(f"{'SSCL (2.5%)':<20} {sale.tax_sscl:>21.2f}")  # noqa: E231
        lines.append(f"{'Net Revenue':<20} {sale.net_revenue:>21.2f}")  # noqa: E231
        lines.append("-" * ReceiptBuilder.WIDTH)

        # 6. Footer
        lines.append(ReceiptBuilder._center("Thank You! Come Again."))
        lines.append(ReceiptBuilder._center("Software by Ceylon Byte"))
        lines.append("\n\n")  # Feed

        return "\n".join(lines)

    @staticmethod
    def _center(text: str) -> str:
        return text.center(ReceiptBuilder.WIDTH)
