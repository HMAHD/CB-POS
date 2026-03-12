from decimal import Decimal
from pathlib import Path
from cbpos.core.services.config_service import ConfigService
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
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from cbpos.core.models import Sale
from cbpos.core.services.tax_service import TaxService
from cbpos.core.utils.formatters import format_currency
from cbpos.core.utils.amount_to_words import amount_to_words
from cbpos.core.services.document_service import DocumentService


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

        header_style = ParagraphStyle("Header", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER)

        # === HEADER SECTION ===
        # Logo (if exists)
        logo_path = Path(__file__).resolve().parent.parent.parent / "assets" / "logo" / "cover_black.png"
        if logo_path.exists():
            logo = Image(str(logo_path), width=60 * mm, height=20 * mm)
            logo.hAlign = "CENTER"
            elements.append(logo)
            elements.append(Spacer(1, 5 * mm))

        # Company Details (from ConfigService)
        shop_name = ConfigService.get("shop_name") or "Ceylon Byte POS"
        shop_address = ConfigService.get("shop_address") or ""
        shop_phone = ConfigService.get("shop_phone") or ""
        shop_email = ConfigService.get("shop_email") or ""
        vat_number = ConfigService.get("vat_number") or ""
        company_tax_id = ConfigService.get("company_tax_id") or ""

        elements.append(Paragraph(shop_name, header_style))
        if shop_address:
            elements.append(Paragraph(shop_address, header_style))
        contact_parts = []
        if shop_phone:
            contact_parts.append(f"Tel: {shop_phone}")
        if shop_email:
            contact_parts.append(f"Email: {shop_email}")
        if contact_parts:
            elements.append(Paragraph(" | ".join(contact_parts), header_style))
        reg_parts = []
        if vat_number and TaxService.is_vat_active():
            reg_parts.append(f"VAT Reg: {vat_number}")
        if company_tax_id:
            reg_parts.append(f"Tax ID: {company_tax_id}")
        if reg_parts:
            elements.append(Paragraph(" | ".join(reg_parts), header_style))
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
                (sale.customer.vat_number if sale.customer and sale.customer.vat_number else "N/A"),
            ],
        ]

        invoice_table = Table(invoice_data, colWidths=[30 * mm, 60 * mm, 30 * mm, 60 * mm])
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
            qty = "{0: .3f}".format(item.quantity) if item.quantity % 1 != 0 else "{0}".format(int(item.quantity))
            unit_price = format_currency(item.unit_price)
            discount = format_currency(item.discount) if item.discount else format_currency(Decimal("0.00"))
            net_amount = format_currency(item.unit_price * item.quantity - item.discount)

            items_data.append([item_name, qty, unit_price, discount, net_amount])

        items_table = Table(items_data, colWidths=[80 * mm, 20 * mm, 30 * mm, 25 * mm, 30 * mm])
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
        vat_amount = sale.tax_vat or Decimal("0.00")
        sscl_amount = sale.tax_sscl or Decimal("0.00")
        grand_total = sale.total_amount

        totals_data = [
            ["Subtotal:", format_currency(subtotal)],
            ["Total Discount:", format_currency(total_discount)],
        ]
        # Only show tax rows if VAT is active or the sale actually has tax values
        if TaxService.is_vat_active() or vat_amount > 0:
            totals_data.append(
                [
                    "VAT ({}%):".format(ConfigService.get("tax_vat_rate") or 18),
                    format_currency(vat_amount),
                ]
            )
            totals_data.append(
                [
                    "SSCL ({}%):".format(ConfigService.get("tax_sscl_rate") or 2.5),
                    format_currency(sscl_amount),
                ]
            )
        totals_data.append(["Grand Total:", format_currency(grand_total)])

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
        footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=9, alignment=TA_LEFT)

        # Banking details (from config)
        bank_name = ConfigService.get("bank_name") or ""
        bank_account = ConfigService.get("bank_account") or ""
        bank_branch = ConfigService.get("bank_branch") or ""
        if bank_name or bank_account:
            elements.append(Paragraph("<b>Banking Details:</b>", footer_style))
            if bank_name:
                elements.append(Paragraph(f"Bank: {bank_name}", footer_style))
            if bank_account:
                elements.append(Paragraph(f"Account No: {bank_account}", footer_style))
            if bank_branch:
                elements.append(Paragraph(f"Branch: {bank_branch}", footer_style))
            elements.append(Spacer(1, 10 * mm))

        signature_data = [["Authorized Signature:", "_" * 30, "Company Stamp:", "[STAMP]"]]
        signature_table = Table(signature_data, colWidths=[40 * mm, 50 * mm, 40 * mm, 55 * mm])
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

        # Branding footer
        elements.append(Spacer(1, 5 * mm))
        branding_style = ParagraphStyle(
            "Branding",
            parent=styles["Normal"],
            fontSize=8,
            alignment=TA_CENTER,
            textColor=colors.grey,
        )
        elements.append(Paragraph("Powered by CB POS — ceybyte.com", branding_style))

        # Build PDF
        doc.build(elements)
        return filepath

    @staticmethod
    def generate_tax_invoice(
        sale: Sale,
        filepath: str,
        copy_type: str = "ORIGINAL",
        language: str = "en",
        serial_number: str = "",
    ) -> str:
        """
        Generate a Sri Lankan tax-compliant A4 invoice PDF (Jan 2026 mandate).

        Args:
            sale: The sale transaction to invoice.
            filepath: Absolute path where PDF should be saved.
            copy_type: 'ORIGINAL' or 'DUPLICATE' watermark text.
            language: Language for amount-in-words ('en', 'si', 'ta').
            serial_number: Pre-generated serial number. If empty, one is generated.
                Pass the same serial for ORIGINAL and DUPLICATE copies.

        Returns:
            Path to the generated PDF file.
        """
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        # Watermark callback
        watermark_text = copy_type.upper() if copy_type else "ORIGINAL"

        def _draw_watermark(canvas, doc) -> None:
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 60)
            canvas.setFillColor(colors.Color(0.85, 0.85, 0.85, alpha=0.3))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, watermark_text)
            canvas.restoreState()

        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )

        elements: list = []
        styles = getSampleStyleSheet()

        # --- Styles ---
        title_style = ParagraphStyle(
            "TaxInvTitle",
            parent=styles["Heading1"],
            fontSize=22,
            textColor=colors.HexColor("#001F3F"),
            alignment=TA_CENTER,
            spaceAfter=8,
            spaceBefore=4,
        )
        label_style = ParagraphStyle(
            "TILabel",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
        )
        value_style = ParagraphStyle(
            "TIValue",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            fontName="Helvetica-Bold",
        )
        small_style = ParagraphStyle(
            "TISmall",
            parent=styles["Normal"],
            fontSize=8,
            alignment=TA_CENTER,
            textColor=colors.grey,
        )

        # --- Config ---
        shop_name = ConfigService.get("shop_name") or "Ceylon Byte POS"
        shop_address = ConfigService.get("shop_address") or ""
        shop_phone = ConfigService.get("shop_phone") or ""
        shop_tin = ConfigService.get("company_tax_id") or ""
        shop_vat = ConfigService.get("vat_number") or ""

        # --- Tax Invoice Serial Number ---
        if not serial_number:
            serial_number = DocumentService.generate_tax_invoice_number()

        # === TITLE ===
        elements.append(Paragraph("<b>TAX INVOICE</b>", title_style))
        elements.append(Spacer(1, 4 * mm))

        # === SUPPLIER / BUYER INFO (side by side) ===
        buyer_name = sale.customer.name if sale.customer else "Walk-in Customer"
        buyer_tin = ""
        buyer_address = ""
        buyer_phone = ""
        if sale.customer:
            buyer_tin = sale.customer.tax_id or sale.customer.vat_number or ""
            buyer_address = sale.customer.address or ""
            buyer_phone = sale.customer.phone or ""

        show_vat = TaxService.is_vat_active() or (
            (sale.tax_vat and sale.tax_vat > 0) or (sale.tax_sscl and sale.tax_sscl > 0)
        )
        supplier_lines = [
            [Paragraph("<b>Supplier</b>", label_style), ""],
            [Paragraph("Name:", label_style), Paragraph(shop_name, value_style)],
            [Paragraph("TIN:", label_style), Paragraph(shop_tin, value_style)],
        ]
        if show_vat and shop_vat:
            supplier_lines.append([Paragraph("VAT Reg:", label_style), Paragraph(shop_vat, value_style)])
        supplier_lines.extend(
            [
                [Paragraph("Address:", label_style), Paragraph(shop_address, value_style)],
                [Paragraph("Phone:", label_style), Paragraph(shop_phone, value_style)],
            ]
        )
        buyer_lines = [
            [Paragraph("<b>Buyer</b>", label_style), ""],
            [Paragraph("Name:", label_style), Paragraph(buyer_name, value_style)],
            [Paragraph("TIN:", label_style), Paragraph(buyer_tin or "N/A", value_style)],
            [Paragraph("Address:", label_style), Paragraph(buyer_address, value_style)],
            [Paragraph("Phone:", label_style), Paragraph(buyer_phone, value_style)],
            [Paragraph("", label_style), Paragraph("", value_style)],
        ]

        supplier_table = Table(supplier_lines, colWidths=[20 * mm, 65 * mm])
        supplier_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        buyer_table = Table(buyer_lines, colWidths=[20 * mm, 65 * mm])
        buyer_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )

        header_table = Table(
            [[supplier_table, buyer_table]],
            colWidths=[90 * mm, 90 * mm],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elements.append(header_table)
        elements.append(Spacer(1, 4 * mm))

        # === INVOICE META ===
        meta_data = [
            [
                Paragraph("<b>Serial No:</b>", label_style),
                Paragraph(serial_number, value_style),
                Paragraph("<b>Date:</b>", label_style),
                Paragraph(sale.date.strftime("%Y-%m-%d"), value_style),
            ],
            [
                Paragraph("<b>Payment:</b>", label_style),
                Paragraph(sale.payment_method or "N/A", value_style),
                Paragraph("<b>Doc Ref:</b>", label_style),
                Paragraph(sale.document_number or "", value_style),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[25 * mm, 60 * mm, 25 * mm, 60 * mm])
        meta_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.append(meta_table)
        elements.append(Spacer(1, 6 * mm))

        # === ITEMS TABLE ===
        items_header = ["#", "Description", "Qty", "Unit Price (Rs.)", "Amount (Rs.)"]
        items_data = [items_header]

        def _whole_lkr(value: Decimal) -> str:
            """Format amount as whole LKR (no cents) with comma separators."""
            return "{:,.0f}".format(int(value))

        for idx, item in enumerate(sale.items, start=1):
            item_name = item.product.name_en if item.product else "Unknown Item"
            qty_str = "{:.3f}".format(item.qty) if item.qty % 1 != 0 else str(int(item.qty))
            items_data.append(
                [
                    str(idx),
                    item_name,
                    qty_str,
                    _whole_lkr(item.unit_price),
                    _whole_lkr(item.subtotal),
                ]
            )

        items_table = Table(
            items_data,
            colWidths=[10 * mm, 80 * mm, 20 * mm, 30 * mm, 30 * mm],
        )
        items_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("ALIGN", (0, 1), (0, -1), "CENTER"),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                    ("ALIGN", (1, 1), (1, -1), "LEFT"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 1), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
                ]
            )
        )
        elements.append(items_table)
        elements.append(Spacer(1, 5 * mm))

        # === TOTALS ===
        net_amount = sale.net_revenue or Decimal("0")
        vat_amount = sale.tax_vat or Decimal("0")
        sscl_amount = sale.tax_sscl or Decimal("0")
        grand_total = sale.total_amount

        right_style = ParagraphStyle("TIRight", parent=label_style, alignment=TA_RIGHT)
        right_bold = ParagraphStyle("TIRightBold", parent=value_style, alignment=TA_RIGHT)

        totals_data = []
        if show_vat:
            totals_data.append(
                [
                    Paragraph("Net Amount:", right_style),
                    Paragraph(f"Rs. {_whole_lkr(net_amount)}", right_style),
                ]
            )
            totals_data.append(
                [
                    Paragraph("VAT ({}%):".format(ConfigService.get("tax_vat_rate") or 18), right_style),
                    Paragraph(f"Rs. {_whole_lkr(vat_amount)}", right_style),
                ]
            )
            totals_data.append(
                [
                    Paragraph("SSCL ({}%):".format(ConfigService.get("tax_sscl_rate") or 2.5), right_style),
                    Paragraph(f"Rs. {_whole_lkr(sscl_amount)}", right_style),
                ]
            )
        totals_data.append(
            [
                Paragraph("<b>Total:</b>", right_bold),
                Paragraph(f"<b>Rs. {_whole_lkr(grand_total)}</b>", right_bold),
            ]
        )
        totals_table = Table(totals_data, colWidths=[130 * mm, 40 * mm])
        totals_table.setStyle(
            TableStyle(
                [
                    ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0F0F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        elements.append(totals_table)
        elements.append(Spacer(1, 4 * mm))

        # === AMOUNT IN WORDS ===
        words = amount_to_words(grand_total, language)
        words_style = ParagraphStyle(
            "TIWords",
            parent=styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Oblique",
        )
        words_label = "<b>Amount in Words:</b> {}".format(words)
        elements.append(Paragraph(words_label, words_style))
        elements.append(Spacer(1, 8 * mm))

        # === SIGNATURES ===
        sig_data = [
            ["Authorized Signature:", "_" * 30, "Company Stamp:", "[STAMP]"],
        ]
        sig_table = Table(sig_data, colWidths=[35 * mm, 55 * mm, 35 * mm, 45 * mm])
        sig_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ]
            )
        )
        elements.append(sig_table)

        # === BRANDING ===
        elements.append(Spacer(1, 5 * mm))
        elements.append(Paragraph("Powered by CB POS \u2014 ceybyte.com", small_style))

        # Build with watermark
        doc.build(elements, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)
        return filepath
