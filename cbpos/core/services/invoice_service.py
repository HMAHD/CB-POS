from decimal import Decimal
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from cbpos.core.models import Sale


class InvoiceService:
    """
    Service for generating professional A4 Tax Invoices for B2B customers.
    Uses ReportLab for PDF generation with Sri Lankan tax compliance.
    """

    @staticmethod
    def generate_pdf(sale: Sale, filepath: str) -> str:
        """
        Generate a professional A4 Tax Invoice PDF.

        Args:
            sale (Sale): The sale transaction to invoice
            filepath (str): Absolute path where PDF should be saved

        Returns:
            str: Path to the generated PDF file
        """
        # Ensure directory exists
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        # Create PDF document
        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            rightMargin=20 * mm,
            leftMargin=20 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )

        # Container for flowables
        elements = []
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=colors.HexColor("#001F3F"),
            alignment=TA_CENTER,
            spaceAfter=12,
        )

        header_style = ParagraphStyle(
            "Header", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER
        )

        # === HEADER SECTION ===
        # Logo (if exists)
        logo_path = (
            Path(__file__).resolve().parent.parent.parent
            / "assets"
            / "logo"
            / "cover_black.png"
        )
        if logo_path.exists():
            logo = Image(str(logo_path), width=60 * mm, height=20 * mm)
            logo.hAlign = "CENTER"
            elements.append(logo)
            elements.append(Spacer(1, 5 * mm))

        # Company Details
        elements.append(Paragraph("CEYLON BYTE POS SYSTEM", header_style))
        elements.append(
            Paragraph("123 Main Street, Colombo 00700, Sri Lanka", header_style)
        )
        elements.append(
            Paragraph("Tel: +94 11 234 5678 | Email: info@ceylonbyte.lk", header_style)
        )
        elements.append(
            Paragraph("VAT Reg: 123456789V | SSCL Reg: SSCL/2024/001", header_style)
        )
        elements.append(Spacer(1, 10 * mm))

        # Invoice Title
        elements.append(Paragraph("TAX INVOICE", title_style))
        elements.append(Spacer(1, 5 * mm))

        # === INVOICE INFO & CUSTOMER SECTION ===
        invoice_data = [
            [
                "Invoice No:",
                "INV-{0: 06d}".format(sale.id),
                "Date:",
                sale.date.strftime("%Y-%m-%d"),
            ],
            [
                "Customer:",
                sale.customer.name if sale.customer else "Walk-in Customer",
                "VAT No:",
                (
                    sale.customer.vat_number
                    if sale.customer and sale.customer.vat_number
                    else "N/A"
                ),
            ],
        ]

        invoice_table = Table(
            invoice_data, colWidths=[30 * mm, 60 * mm, 30 * mm, 60 * mm]
        )
        invoice_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ]
            )
        )
        elements.append(invoice_table)
        elements.append(Spacer(1, 10 * mm))

        # === ITEMS TABLE ===
        items_data = [["Item", "Qty", "Unit Price", "Discount", "Net Amount"]]

        for item in sale.items:
            item_name = item.product.name if item.product else "Unknown Item"
            qty = (
                "{0: .3f}".format(item.quantity)
                if item.quantity % 1 != 0
                else "{0}".format(int(item.quantity))
            )
            unit_price = "Rs. {0: ,.2f}".format(item.unit_price)
            discount = (
                "Rs. {0: ,.2f}".format(item.discount) if item.discount else "Rs. 0.00"
            )
            net_amount = "Rs. {0: ,.2f}".format(
                item.unit_price * item.quantity - item.discount
            )

            items_data.append([item_name, qty, unit_price, discount, net_amount])

        items_table = Table(
            items_data, colWidths=[80 * mm, 20 * mm, 30 * mm, 25 * mm, 30 * mm]
        )
        items_table.setStyle(
            TableStyle(
                [
                    # Header row
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    # Data rows
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("ALIGN", (0, 1), (0, -1), "LEFT"),
                    # Grid
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        elements.append(items_table)
        elements.append(Spacer(1, 5 * mm))

        # === TOTALS SECTION ===
        subtotal = sum(item.unit_price * item.quantity for item in sale.items)
        total_discount = sum(item.discount for item in sale.items)
        vat_amount = sale.tax_amount or Decimal("0.00")
        sscl_amount = Decimal("0.00")  # Calculate if needed
        grand_total = sale.total_amount

        totals_data = [
            ["Subtotal:", "Rs. {0: ,.2f}".format(subtotal)],
            ["Total Discount:", "Rs. {0: ,.2f}".format(total_discount)],
            ["VAT (15%):", "Rs. {0: ,.2f}".format(vat_amount)],
            ["SSCL (2.5%):", "Rs. {0: ,.2f}".format(sscl_amount)],
            ["Grand Total:", "Rs. {0: ,.2f}".format(grand_total)],
        ]

        totals_table = Table(totals_data, colWidths=[140 * mm, 45 * mm])
        totals_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0F0F0")),
                ]
            )
        )
        elements.append(totals_table)
        elements.append(Spacer(1, 10 * mm))

        # === FOOTER SECTION ===
        footer_style = ParagraphStyle(
            "Footer", parent=styles["Normal"], fontSize=9, alignment=TA_LEFT
        )

        elements.append(Paragraph("<b>Banking Details:</b>", footer_style))
        elements.append(Paragraph("Bank: Commercial Bank of Ceylon", footer_style))
        elements.append(Paragraph("Account No: 1234567890", footer_style))
        elements.append(Paragraph("Branch: Colombo Fort", footer_style))
        elements.append(Spacer(1, 10 * mm))

        signature_data = [
            ["Authorized Signature:", "_" * 30, "Company Stamp:", "[STAMP]"]
        ]
        signature_table = Table(
            signature_data, colWidths=[40 * mm, 50 * mm, 40 * mm, 55 * mm]
        )
        signature_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ]
            )
        )
        elements.append(signature_table)

        # Build PDF
        doc.build(elements)
        return filepath
