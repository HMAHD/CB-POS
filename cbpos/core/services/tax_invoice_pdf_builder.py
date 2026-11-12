"""ReportLab PDF builder for compliant Sri Lankan VAT Tax Invoices (#814).

Adheres to:
- VAT Act No. 14 of 2002 Section 20
- Gazette Extraordinary No. 2481/22 and No. 2500/106
- ORIGINAL vs COPY ONLY statutory marking rules
"""

import os
from decimal import Decimal
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from cbpos.core.models.tax_invoice import TaxInvoice
from cbpos.core.utils.formatters import format_currency, format_quantity
from cbpos.core.utils.text_scripts import needs_raster

_NAVY = colors.HexColor("#003366")
_NAVY_DARK = colors.HexColor("#001F3F")
_GREY = colors.HexColor("#666666")
_LIGHT_GREY = colors.HexColor("#F8F9FA")
_BORDER_GREY = colors.HexColor("#DEE2E6")
_RED_ALERT = colors.HexColor("#B02A37")
_GREEN_TAG = colors.HexColor("#198754")
_MARGIN = 15 * mm
_WIDTH = A4[0] - 2 * _MARGIN  # 180 mm
_BRANDING = "Powered by CB POS — ceybyte.com"


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("TIBase", fontName="Helvetica", fontSize=8.5, leading=11)
    bold = ParagraphStyle("TIBold", parent=base, fontName="Helvetica-Bold")
    return {
        "base": base,
        "bold": bold,
        "right": ParagraphStyle("TIRight", parent=base, alignment=TA_RIGHT),
        "right_bold": ParagraphStyle("TIRightBold", parent=bold, alignment=TA_RIGHT),
        "center": ParagraphStyle("TICenter", parent=base, alignment=TA_CENTER),
        "center_bold": ParagraphStyle("TICenterBold", parent=bold, alignment=TA_CENTER),
        "title": ParagraphStyle(
            "TITitle",
            parent=bold,
            fontSize=20,
            leading=24,
            alignment=TA_RIGHT,
            textColor=_NAVY_DARK,
        ),
        "title_left": ParagraphStyle(
            "TITitleLeft",
            parent=bold,
            fontSize=18,
            leading=22,
            alignment=TA_LEFT,
            textColor=_NAVY_DARK,
        ),
        "badge_orig": ParagraphStyle(
            "TIBadgeOrig",
            parent=bold,
            fontSize=11,
            leading=14,
            alignment=TA_RIGHT,
            textColor=_GREEN_TAG,
        ),
        "badge_copy": ParagraphStyle(
            "TIBadgeCopy",
            parent=bold,
            fontSize=11,
            leading=14,
            alignment=TA_RIGHT,
            textColor=_RED_ALERT,
        ),
        "th": ParagraphStyle(
            "TITh",
            parent=bold,
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=colors.whitesmoke,
        ),
        "muted": ParagraphStyle("TIMuted", parent=base, textColor=_GREY),
        "muted_right": ParagraphStyle("TIMutedRight", parent=base, textColor=_GREY, alignment=TA_RIGHT),
    }


def _text(text: Any, style: ParagraphStyle, width: float | None = None) -> Flowable:
    """Format text with Qt rasterization fallback for Sinhala/Tamil scripts.

    Preserves numeric 0 and converts newlines to <br/>.
    """
    text_str = "" if text is None else str(text)
    if not needs_raster(text_str):
        html_escaped = escape(text_str).replace("\n", "<br/>")
        return Paragraph(html_escaped, style)

    from cbpos.infrastructure.hardware.text_raster import render_text_png

    align = {TA_CENTER: "center", TA_RIGHT: "right"}.get(style.alignment, "left")
    png, w, h = render_text_png(
        text_str,
        style.fontSize,
        bold=style.fontName.endswith("Bold"),
        color="#" + style.textColor.hexval()[2:],
        max_width_pt=width,
        align=align,
    )
    image = Image(BytesIO(png), width=w, height=h)
    image.hAlign = align.upper()
    return image


def _draw_branding(canvas: Any, _doc: Any) -> None:
    """Draw footer notice and CB POS branding at the foot of each page."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(_GREY)
    notice = "Issued in terms of Section 20 of Value Added Tax Act No. 14 of 2002 · Retain for a minimum of 5 years"
    canvas.drawCentredString(A4[0] / 2, 13 * mm, notice)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(A4[0] / 2, 8 * mm, _BRANDING)
    canvas.restoreState()


class TaxInvoicePDFBuilder:
    """Builder generating statutory A4 VAT Tax Invoices."""

    @staticmethod
    def generate_pdf(
        invoice: TaxInvoice,
        filepath: str,
        is_copy: bool | None = None,
    ) -> str:
        """Render the given TaxInvoice as an A4 PDF document.

        Args:
            invoice: The TaxInvoice database record (with lines loaded).
            filepath: Destination file path.
            is_copy: Explicit override for copy marking; defaults to True if print_count > 0.
        """
        out_dir = os.path.dirname(filepath)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        if is_copy is None:
            # First print is ORIGINAL; subsequent reprints are COPY ONLY
            is_copy = bool(invoice.print_count > 0 or invoice.original_printed_at is not None)

        st = _styles()
        elements: list[Flowable] = []

        # 1. Header: Shop Identity (Left) vs TAX INVOICE & Badge (Right)
        elements.append(TaxInvoicePDFBuilder._build_header(invoice, is_copy, st))
        elements.append(Spacer(1, 4 * mm))

        # 2. Metadata Bar: Serial, Issue Date, Supply Date, Payment Method
        elements.append(TaxInvoicePDFBuilder._build_metadata_bar(invoice, st))
        elements.append(Spacer(1, 4 * mm))

        # 3. Parties Block: Supplier (Seller) & Buyer (Customer) with 9-digit TINs
        elements.append(TaxInvoicePDFBuilder._build_parties_block(invoice, st))
        elements.append(Spacer(1, 5 * mm))

        # 4. Line Items Table
        elements.append(TaxInvoicePDFBuilder._build_items_table(invoice, st))
        elements.append(Spacer(1, 4 * mm))

        # 5. Totals & Consideration in Words
        elements.append(TaxInvoicePDFBuilder._build_totals_and_words(invoice, st))
        elements.append(Spacer(1, 6 * mm))

        # 6. Signatures & Declarations
        elements.append(TaxInvoicePDFBuilder._build_signature_block(st))

        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            leftMargin=_MARGIN,
            rightMargin=_MARGIN,
            topMargin=_MARGIN,
            bottomMargin=18 * mm,
        )
        doc.build(elements, onFirstPage=_draw_branding, onLaterPages=_draw_branding)
        return filepath

    @staticmethod
    def _build_header(invoice: TaxInvoice, is_copy: bool, st: dict[str, ParagraphStyle]) -> Table:
        badge_style = st["badge_copy"] if is_copy else st["badge_orig"]
        badge_label = "[ COPY ONLY ]" if is_copy else "[ ORIGINAL ]"

        left_flowables = [
            _text(invoice.supplier_name, st["title_left"], 95 * mm),
        ]
        right_flowables = [
            _text("TAX INVOICE", st["title"], 85 * mm),
            Spacer(1, 1 * mm),
            _text(badge_label, badge_style, 85 * mm),
        ]

        table = Table([[left_flowables, right_flowables]], colWidths=[95 * mm, 85 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return table

    @staticmethod
    def _build_metadata_bar(invoice: TaxInvoice, st: dict[str, ParagraphStyle]) -> Table:
        issue_date_str = invoice.issued_at.strftime("%Y-%m-%d %H:%M") if invoice.issued_at else ""
        supply_date_str = invoice.supply_date.strftime("%Y-%m-%d") if invoice.supply_date else ""

        headers = ["Invoice Serial", "Date of Issue", "Date of Supply", "Payment Method"]
        values = [invoice.serial, issue_date_str, supply_date_str, invoice.payment_method]

        row_h = [_text(h, st["muted"], 45 * mm) for h in headers]
        row_v = [_text(v, st["bold"], 45 * mm) for v in values]

        table = Table([row_h, row_v], colWidths=[45 * mm, 45 * mm, 45 * mm, 45 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_GREY),
                    ("BOX", (0, 0), (-1, -1), 0.5, _BORDER_GREY),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, _BORDER_GREY),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    @staticmethod
    def _build_parties_block(invoice: TaxInvoice, st: dict[str, ParagraphStyle]) -> Table:
        # Supplier Box
        supp_lines = [
            _text("SUPPLIER (SELLER)", st["bold"], 88 * mm),
            _text(invoice.supplier_name, st["bold"], 88 * mm),
            _text(invoice.supplier_address, st["base"], 88 * mm),
        ]
        if invoice.supplier_phone:
            supp_lines.append(_text(f"Tel: {invoice.supplier_phone}", st["base"], 88 * mm))
        supp_lines.extend(
            [
                Spacer(1, 1 * mm),
                _text(f"VAT / TIN No: {invoice.supplier_tin}", st["bold"], 88 * mm),
            ]
        )

        # Buyer Box
        buyer_lines = [
            _text("BUYER (CUSTOMER)", st["bold"], 88 * mm),
            _text(invoice.buyer_name, st["bold"], 88 * mm),
            _text(invoice.buyer_address, st["base"], 88 * mm),
        ]
        if invoice.buyer_phone:
            buyer_lines.append(_text(f"Tel: {invoice.buyer_phone}", st["base"], 88 * mm))
        buyer_lines.extend(
            [
                Spacer(1, 1 * mm),
                _text(f"Taxpayer ID (TIN): {invoice.buyer_tin}", st["bold"], 88 * mm),
            ]
        )

        table = Table([[supp_lines, buyer_lines]], colWidths=[90 * mm, 90 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (0, 0), 0.5, _BORDER_GREY),
                    ("BOX", (1, 0), (1, 0), 0.5, _BORDER_GREY),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return table

    @staticmethod
    def _build_items_table(invoice: TaxInvoice, st: dict[str, ParagraphStyle]) -> Table:
        col_widths = [
            10 * mm,
            50 * mm,
            20 * mm,
            20 * mm,
            15 * mm,
            20 * mm,
            15 * mm,
            15 * mm,
            15 * mm,
        ]
        headers = [
            "#",
            "Description",
            "Qty & Unit",
            "Unit Price",
            "Discount",
            "Net Amount",
            "VAT %",
            "VAT",
            "Total",
        ]
        header_row = [_text(h, st["th"]) for h in headers]
        table_rows = [header_row]

        for line in invoice.lines or []:
            desc_text = line.product_name_snapshot or ""
            if line.item_code_snapshot:
                desc_text = f"[{line.item_code_snapshot}] {desc_text}"

            unit = line.unit_snapshot or "pcs"
            qty_str = f"{format_quantity(line.quantity)} {unit}"
            v_rate = line.vat_rate if line.vat_rate is not None else Decimal("0.00")
            vat_rate_str = f"{int(v_rate)}%" if v_rate == int(v_rate) else f"{v_rate}%"

            table_rows.append(
                [
                    _text(str(line.item_number), st["center"]),
                    _text(desc_text, st["base"], 48 * mm),
                    _text(qty_str, st["center"]),
                    _text(format_currency(line.unit_price or Decimal("0.00")), st["right"]),
                    _text(format_currency(line.discount_amount or Decimal("0.00")), st["right"]),
                    _text(format_currency(line.net_amount or Decimal("0.00")), st["right"]),
                    _text(vat_rate_str, st["center"]),
                    _text(format_currency(line.vat_amount or Decimal("0.00")), st["right"]),
                    _text(format_currency(line.total_amount or Decimal("0.00")), st["right_bold"]),
                ]
            )

        table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, _BORDER_GREY),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return table

    @staticmethod
    def _build_totals_and_words(invoice: TaxInvoice, st: dict[str, ParagraphStyle]) -> Table:
        # Left side: Amount in words
        words_block = [
            _text("TOTAL CONSIDERATION IN WORDS:", st["bold"], 95 * mm),
            Spacer(1, 1 * mm),
            _text(invoice.amount_in_words, st["base"], 95 * mm),
        ]

        # Right side: Totals breakdown
        summary_rows = [
            ("Subtotal (Gross):", format_currency(invoice.subtotal_amount or Decimal("0.00"))),
        ]
        disc = invoice.discount_amount or Decimal("0.00")
        if disc > Decimal("0.00"):
            summary_rows.append(("Bill Discount:", f"-{format_currency(disc)}"))

        summary_rows.append(("Net Liable (Excl. VAT):", format_currency(invoice.net_amount or Decimal("0.00"))))

        vat_groups: dict[Decimal, Decimal] = {}
        for line in invoice.lines or []:
            r = line.vat_rate if line.vat_rate is not None else Decimal("0.00")
            a = line.vat_amount if line.vat_amount is not None else Decimal("0.00")
            vat_groups[r] = vat_groups.get(r, Decimal("0.00")) + a

        taxable_groups = {r: a for r, a in vat_groups.items() if r > Decimal("0.00")}
        if taxable_groups:
            for r in sorted(taxable_groups.keys()):
                r_str = f"{int(r)}%" if r == int(r) else f"{r}%"
                summary_rows.append((f"Output VAT ({r_str}):", format_currency(taxable_groups[r])))
        else:
            summary_rows.append(("Output VAT:", format_currency(invoice.tax_vat or Decimal("0.00"))))

        summary_rows.append(("TOTAL AMOUNT DUE:", format_currency(invoice.total_amount or Decimal("0.00"))))

        sum_table_data = []
        for label, val in summary_rows:
            is_grand = label.startswith("TOTAL AMOUNT")
            l_style = st["bold"] if is_grand else st["muted"]
            v_style = st["right_bold"] if is_grand else st["right"]
            sum_table_data.append([_text(label, l_style, 45 * mm), _text(val, v_style, 35 * mm)])

        sum_table = Table(sum_table_data, colWidths=[45 * mm, 35 * mm])
        sum_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBELOW", (0, -1), (-1, -1), 1, _NAVY_DARK),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        outer = Table([[words_block, sum_table]], colWidths=[100 * mm, 80 * mm])
        outer.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return outer

    @staticmethod
    def _build_signature_block(st: dict[str, ParagraphStyle]) -> Table:
        sig_data = [
            [
                _text("__________________________________\nAuthorized Signatory (Supplier)", st["center"], 85 * mm),
                _text("__________________________________\nReceived & Accepted By (Buyer)", st["center"], 85 * mm),
            ]
        ]
        table = Table(sig_data, colWidths=[90 * mm, 90 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return table
