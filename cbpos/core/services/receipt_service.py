from PIL import Image, ImageDraw, ImageFont
from cbpos.core.models import Sale
from cbpos.core.services.config_service import ConfigService


class ReceiptService:
    """
    Generates receipt content.
    Supports text-based generation for ASCII and image-based generation
    for Unicode.
    """

    WIDTH_CHARS = 42  # Standard 80mm thermal printer width
    # (approx 42-48 chars)
    WIDTH_PIXELS = 576  # Standard 80mm width in pixels (approx)
    FONT_SIZE = 24
    LINE_HEIGHT = 30

    _ROW_FMT = "{:<20} {:>21}"

    @staticmethod
    def build_receipt_text(sale: Sale) -> str:
        """
        Generate text-based receipt (for English only).
        """
        settings = ConfigService.get_all()
        lines = []

        # 1. Header
        lines.append(ReceiptService._center(settings.get("shop_name", "CB POS")))
        address = settings.get("shop_address")
        if address:
            lines.append(ReceiptService._center(address))
        phone = settings.get("shop_phone")
        if phone:
            lines.append(ReceiptService._center(f"Phone: {phone}"))
        vat_number = settings.get("shop_vat_number")
        if vat_number:
            lines.append(ReceiptService._center(f"VAT Reg: {vat_number}"))
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        lines.append(f"Date: {sale.date.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Receipt No: {sale.document_number}")
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 2. Items
        lines.append("{:<20} {:>5} {:>7} {:>8}".format("Item", "Qty", "Price", "Total"))
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        for item in sale.items:
            name = item.product.name_en[:20]
            lines.append(
                "{:<20} {:>5.0f} {:>7.2f} {:>8.2f}".format(
                    name, item.qty, item.unit_price, item.subtotal
                )
            )

        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 3. Totals
        lines.append("{:<20} {:>21.2f}".format("TOTAL", sale.total_amount))
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 4. Tax Breakdown
        lines.append(ReceiptService._center("*** TAX BREAKDOWN ***"))
        lines.append("{:<20} {:>21.2f}".format("VAT (18%)", sale.tax_vat))
        lines.append("{:<20} {:>21.2f}".format("SSCL (2.5%)", sale.tax_sscl))
        lines.append("{:<20} {:>21.2f}".format("Net Revenue", sale.net_revenue))
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 5. Footer
        lines.append(
            ReceiptService._center(settings.get("receipt_footer", "Thank You!"))
        )
        lines.append("\n\n")

        return "\n".join(lines)

    @staticmethod
    def build_receipt_image(sale: Sale) -> Image.Image:
        """
        Generate image-based receipt (for Unicode support).
        """
        # For simplicity, we'll use the text content and render it to an image
        # In a real implementation, we would draw each element for better control
        text_content = ReceiptService.build_receipt_text(sale)

        # Create image
        # Estimate height
        num_lines = text_content.count("\n") + 5
        height = num_lines * ReceiptService.LINE_HEIGHT

        image = Image.new("RGB", (ReceiptService.WIDTH_PIXELS, height), "white")
        draw = ImageDraw.Draw(image)

        # Load Font (Try to load a Unicode font, fallback to default)
        try:
            # Windows usually has Arial or Segoe UI
            font = ImageFont.truetype("arial.ttf", ReceiptService.FONT_SIZE)
        except IOError:
            font = ImageFont.load_default()

        draw.text((10, 10), text_content, fill="black", font=font)

        return image

    @staticmethod
    def _center(text: str) -> str:
        return text.center(ReceiptService.WIDTH_CHARS)

    @staticmethod
    def print_z_report(summary: dict) -> str:
        """
        Generate Z-Report text.
        """
        settings = ConfigService.get_all()
        lines = []

        # 1. Header
        lines.append(ReceiptService._center("Z-REPORT (End of Day)"))
        lines.append(ReceiptService._center(settings.get("shop_name", "CB POS")))
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 2. Shift Info
        lines.append(f"User: {summary.get('user_name', 'Unknown')}")
        start_time = summary.get("start_time")
        if start_time:
            lines.append(f"Start: {start_time.strftime('%Y-%m-%d %H:%M')}")
        end_time = summary.get("end_time")
        if end_time:
            lines.append(f"End: {end_time.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Shift ID: {summary.get('shift_id')}")
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 3. Sales Breakdown
        lines.append("SALES BREAKDOWN")
        lines.append(ReceiptService._ROW_FMT.format("Method", "Amount"))
        for method, amount in summary.get("sales_by_method", {}).items():
            lines.append(
                ReceiptService._ROW_FMT.format(method, "{:.2f}".format(amount))
            )
        lines.append("-" * ReceiptService.WIDTH_CHARS)
        lines.append(
            ReceiptService._ROW_FMT.format(
                "TOTAL SALES", "{:.2f}".format(summary.get("total_sales", 0))
            )
        )
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 4. Cash Control
        lines.append("CASH CONTROL")
        lines.append(
            ReceiptService._ROW_FMT.format(
                "Opening Float", "{:.2f}".format(summary.get("starting_cash", 0))
            )
        )
        lines.append(
            ReceiptService._ROW_FMT.format(
                "Cash Sales", "{:.2f}".format(summary.get("cash_sales", 0))
            )
        )
        lines.append(
            ReceiptService._ROW_FMT.format(
                "Cash In", "{:.2f}".format(summary.get("cash_in", 0))
            )
        )
        lines.append(
            ReceiptService._ROW_FMT.format(
                "Cash Out", "{:.2f}".format(summary.get("cash_out", 0))
            )
        )
        lines.append("-" * ReceiptService.WIDTH_CHARS)
        lines.append(
            ReceiptService._ROW_FMT.format(
                "Expected Cash", "{:.2f}".format(summary.get("expected_cash", 0))
            )
        )
        lines.append(
            ReceiptService._ROW_FMT.format(
                "Actual Cash", "{:.2f}".format(summary.get("actual_cash", 0))
            )
        )

        variance = summary.get("variance", 0)
        var_label = "VARIANCE"
        lines.append(
            ReceiptService._ROW_FMT.format(var_label, "{:.2f}".format(variance))
        )
        if summary.get("notes"):
            lines.append(f"Note: {summary['notes']}")

        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 5. Audit
        lines.append("AUDIT")
        lines.append(
            ReceiptService._ROW_FMT.format(
                "Transactions", str(summary.get("txn_count", 0))
            )
        )
        lines.append(
            ReceiptService._ROW_FMT.format(
                "Void Count", str(summary.get("void_count", 0))
            )
        )
        lines.append(
            ReceiptService._ROW_FMT.format(
                "Void Value", "{:.2f}".format(summary.get("void_value", 0))
            )
        )

        lines.append("-" * ReceiptService.WIDTH_CHARS)
        lines.append(ReceiptService._center("*** END OF REPORT ***"))
        lines.append("\n\n")

        return "\n".join(lines)
