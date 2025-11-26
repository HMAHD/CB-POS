from PIL import Image, ImageDraw, ImageFont
from cbpos.core.models import Sale
from cbpos.core.services.config_service import ConfigService


class ReceiptService:
    """
    Generates receipt content.
    Supports text-based generation for ASCII and image-based generation for Unicode.
    """

    WIDTH_CHARS = 42  # Standard 80mm thermal printer width (approx 42-48 chars)
    WIDTH_PIXELS = 576  # Standard 80mm width in pixels (approx)
    FONT_SIZE = 24
    LINE_HEIGHT = 30

    @staticmethod
    def build_receipt_text(sale: Sale) -> str:
        """
        Generate text-based receipt (for English only).
        """
        settings = ConfigService.get_all()
        lines = []

        # 1. Header
        lines.append(ReceiptService._center(settings.get("shop_name", "CB POS")))
        lines.append(ReceiptService._center(settings.get("shop_address", "")))
        lines.append(ReceiptService._center(settings.get("shop_phone", "")))
        if settings.get("vat_number"):
            lines.append(ReceiptService._center(f"VAT: {settings.get('vat_number')}"))

        lines.append("-" * ReceiptService.WIDTH_CHARS)

        if sale.customer and sale.customer.vat_number:
            lines.append(ReceiptService._center("*** TAX INVOICE ***"))
            lines.append(f"Customer: {sale.customer.name}")
            lines.append(f"VAT: {sale.customer.vat_number}")
            lines.append("-" * ReceiptService.WIDTH_CHARS)

        lines.append(f"Date: {sale.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Receipt No: {sale.receipt_no}")
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
