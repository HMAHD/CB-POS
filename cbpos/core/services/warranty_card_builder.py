"""Warranty card builder — generates thermal and PDF warranty certificates (#824).

Implements CAA s.31(g) / owner snapshot truth:
- ESC/POS thermal command list for 58mm / 80mm printers with barcode and stamp box.
- ReportLab vector PDF with text rasterization fallback for Sinhala/Tamil script.
- Independent cut command per warranty unit for multi-unit certificate generation.
"""

import logging
import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from cbpos.core.models.warranty import Warranty
from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.product_service import ProductService
from cbpos.core.utils.barcode import calculate_barcode_width, choose_barcode
from cbpos.core.utils.text_scripts import needs_raster
from cbpos.i18n import translate_in

logger = logging.getLogger(__name__)

_NAVY = colors.HexColor("#0B2545")
_BORDER_GREY = colors.HexColor("#CBD5E1")
_GREY = colors.HexColor("#64748B")
_LIGHT_BG = colors.HexColor("#F8FAFC")


def _styles() -> dict[str, ParagraphStyle]:
    regular = "Helvetica"
    bold = "Helvetica-Bold"
    return {
        "title": ParagraphStyle("Title", fontName=bold, fontSize=16, leading=20, alignment=TA_CENTER, textColor=_NAVY),
        "subtitle": ParagraphStyle(
            "Subtitle", fontName=regular, fontSize=9, leading=12, alignment=TA_CENTER, textColor=_GREY
        ),
        "h2": ParagraphStyle("H2", fontName=bold, fontSize=11, leading=14, textColor=_NAVY),
        "bold": ParagraphStyle("Bold", fontName=bold, fontSize=9, leading=12, textColor=_NAVY),
        "base": ParagraphStyle("Base", fontName=regular, fontSize=9, leading=12, textColor=colors.black),
        "center": ParagraphStyle("Center", fontName=regular, fontSize=9, leading=12, alignment=TA_CENTER),
        "right": ParagraphStyle("Right", fontName=regular, fontSize=9, leading=12, alignment=TA_RIGHT),
        "muted": ParagraphStyle("Muted", fontName=regular, fontSize=8, leading=10, textColor=_GREY),
        "terms": ParagraphStyle("Terms", fontName=regular, fontSize=8, leading=10, textColor=colors.black),
        "stamp_title": ParagraphStyle(
            "StampTitle", fontName=bold, fontSize=8, leading=10, alignment=TA_CENTER, textColor=_GREY
        ),
    }


def _text(text: Any, style: ParagraphStyle, width: float | None = None) -> Flowable:
    """Render paragraph of text, rasterizing Sinhala/Tamil with Qt for proper shaping."""
    val = str(text or "")
    if not needs_raster(val):
        return Paragraph(escape(val), style)

    from cbpos.infrastructure.hardware.text_raster import render_text_png

    align = {TA_CENTER: "center", TA_RIGHT: "right"}.get(style.alignment, "left")
    png, w, h = render_text_png(
        val,
        style.fontSize,
        bold=style.fontName.endswith("Bold"),
        color="#" + style.textColor.hexval()[2:],
        max_width_pt=width,
        align=align,
    )
    image = Image(BytesIO(png), width=w, height=h)
    image.hAlign = align.upper()
    return image


def _draw_branding(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(_GREY)
    canvas.drawString(15 * mm, 10 * mm, "Powered by CB POS • ceybyte.com")
    canvas.drawRightString(doc.pagesize[0] - 15 * mm, 10 * mm, "Free & Open Source POS for Sri Lankan Small Businesses")
    canvas.restoreState()


class WarrantyCardBuilder(BaseReceiptBuilder):
    """Generates thermal ESC/POS and vector PDF warranty certificates (#824)."""

    @classmethod
    def build_escpos(
        cls,
        warranties: list[Warranty],
        config_override: dict[str, Any] | None = None,
        is_reprint: bool = False,
    ) -> list[dict[str, Any]]:
        """Build ESC/POS command stream for thermal printing of warranty cards.

        Multi-unit certificate cuts: each warranty produces an independent certificate
        with its own cut command.
        """
        cls._resolve_receipt_lang(config_override)
        commands: list[dict[str, Any]] = []
        gc = cls._get_conf
        line_chars = 32 if gc("paper_width", "80mm", config_override) == "58mm" else 42

        def _sep() -> dict[str, Any]:
            return {"type": "text", "val": "-" * line_chars, "align": "center"}

        for w in warranties:
            if is_reprint:
                commands.append({"type": "text", "val": cls._rt("duplicate"), "align": "center"})

            # Shop header block
            cls._append_header_block(commands, config_override)
            commands.append(_sep())

            # Document Title
            commands.append(
                {
                    "type": "text",
                    "val": cls._rt("warranty_card_title", default="WARRANTY CERTIFICATE"),
                    "align": "center",
                    "bold": True,
                }
            )
            if is_reprint and w.status in ("VOID", "CANCELLED"):
                commands.append({"type": "text", "val": f"[{w.status}]", "align": "center", "bold": True})
            commands.append(_sep())

            # Barcode of warranty code
            code_str = w.code
            commands.append({"type": "text", "val": code_str, "align": "center", "bold": True})
            bw = calculate_barcode_width(code_str, gc("paper_width", "80mm", config_override))
            if bw is not None:
                chosen_type, payload = choose_barcode(code_str)
                commands.append(
                    {
                        "type": "barcode",
                        "val": payload,
                        "code": chosen_type,
                        "align": "center",
                        "width": bw,
                        "height": 60,
                    }
                )

            commands.append(_sep())

            # Sale ref and date
            sale = getattr(w, "sale", None)
            doc_no = getattr(sale, "document_number", None) or f"INV-{w.sale_id}"
            sale_date = w.start_date.strftime("%Y-%m-%d") if w.start_date else ""
            commands.append(
                cls._split_row(
                    f"{cls._rt('warranty_card_invoice', default='Invoice')}: {doc_no}",
                    sale_date,
                    line_chars,
                )
            )

            # Customer info (from snapshot, falling back to sale customer)
            cust_name = w.customer_name_snapshot or (
                sale.customer.name if (sale and getattr(sale, "customer", None)) else None
            )
            cust_phone = w.customer_phone_snapshot or (
                sale.customer.phone if (sale and getattr(sale, "customer", None)) else None
            )
            if cust_name:
                commands.append({"type": "text", "val": f"{cls._rt('customer')}: {cust_name}", "align": "left"})
            if cust_phone:
                commands.append({"type": "text", "val": f"{cls._rt('phone')}: {cust_phone}", "align": "left"})

            commands.append(_sep())

            # Covered Product details
            prod = getattr(w, "product", None)
            prod_name = ProductService.display_name(prod, cls._receipt_lang) if prod else f"Product #{w.product_id}"
            commands.append({"type": "text", "val": prod_name, "align": "left", "bold": True})

            if w.serial_number:
                sn_text = cls._rt(
                    "warranty_serial",
                    serial=w.serial_number,
                    default=f"S/N: {w.serial_number}",
                )
                commands.append({"type": "text", "val": f"{sn_text}", "align": "left"})

            # Duration and dates
            unit_key = f"warranty_unit_{w.duration_unit.lower()}"
            unit_name = cls._rt(unit_key, default=w.duration_unit.capitalize())
            coverage_text = f"{cls._rt('warranty_label', default='Warranty')}: {w.duration} {unit_name}"
            provider = w.provider_name or cls._rt("warranty_type_shop", default="Shop")
            commands.append(cls._split_row(coverage_text, f"({provider})", line_chars))

            valid_until_str = cls._rt(
                "warranty_until",
                date=w.end_date.strftime("%Y-%m-%d"),
                default=f"until {w.end_date.strftime('%Y-%m-%d')}",
            )
            commands.append({"type": "text", "val": f"   {valid_until_str}", "align": "left"})

            # Remedy
            remedy_key = f"warranty_remedy_{w.remedy.lower()}"
            remedy_name = cls._rt(remedy_key, default=w.remedy.replace("_", " ").title())
            commands.append(
                {
                    "type": "text",
                    "val": f"{cls._rt('warranty_card_remedy', default='Remedy')}: {remedy_name}",
                    "align": "left",
                }
            )

            # Terms & Conditions
            if w.terms_text:
                commands.append(_sep())
                commands.append(
                    {
                        "type": "text",
                        "val": cls._rt("warranty_terms_title", default="TERMS & CONDITIONS"),
                        "align": "left",
                        "bold": True,
                    }
                )
                for line in cls._wrap_free_text(w.terms_text, line_chars):
                    commands.append({"type": "text", "val": line, "align": "left"})

            # Exclusions
            if w.exclusions_text:
                commands.append(
                    {
                        "type": "text",
                        "val": cls._rt("warranty_exclusions_title", default="EXCLUSIONS"),
                        "align": "left",
                        "bold": True,
                    }
                )
                for line in cls._wrap_free_text(w.exclusions_text, line_chars):
                    commands.append({"type": "text", "val": line, "align": "left"})

            # Stamp Box
            commands.append(_sep())
            box_width = min(line_chars - 4, 30)
            commands.append({"type": "text", "val": "+" + "-" * box_width + "+", "align": "center"})
            stamp_title = cls._rt("warranty_stamp_title", default="OFFICIAL SHOP STAMP")[:box_width].center(box_width)
            commands.append({"type": "text", "val": f"|{stamp_title}|", "align": "center"})
            commands.append({"type": "text", "val": "|" + " " * box_width + "|", "align": "center"})
            commands.append({"type": "text", "val": "|" + " " * box_width + "|", "align": "center"})
            commands.append({"type": "text", "val": "+" + "-" * box_width + "+", "align": "center"})

            # Duplicate marking (bottom)
            if is_reprint:
                commands.append({"type": "text", "val": cls._rt("duplicate"), "align": "center"})

            # Branding and Cut per unit
            cls._append_branding(commands)
            commands.append({"type": "cut"})

        return commands

    @classmethod
    def build_pdf(
        cls,
        warranties: list[Warranty],
        filepath: str,
        page_size: Any = A5,
        lang: str | None = None,
    ) -> str:
        """Write vector PDF warranty certificate(s).

        Each warranty produces an independent certificate page with shop header,
        barcode, product details, snapshot terms, and official stamp box.
        """
        if not warranties:
            raise ValueError("No warranties provided for PDF generation")

        st = _styles()
        eff_lang = lang or ConfigService.get("receipt_language") or "en"

        def _lt(key: str, default: str = "", **kwargs) -> str:
            val = translate_in(eff_lang, f"receipt_strings.{key}", **kwargs)
            return default if val == f"receipt_strings.{key}" else val

        page_width, _page_height = page_size
        margin = 15 * mm
        content_width = page_width - 2 * margin

        elements: list[Flowable] = []

        for idx, w in enumerate(warranties):
            if idx > 0:
                elements.append(PageBreak())

            # Header block
            shop_name = ConfigService.get("shop_name") or "CB POS"
            elements.append(_text(shop_name, st["title"], content_width))
            shop_address = ConfigService.get("shop_address") or ""
            shop_phone = ConfigService.get("shop_phone") or ""
            sub_parts = [p for p in (shop_address, shop_phone) if p]
            if sub_parts:
                elements.append(_text(" • ".join(sub_parts), st["subtitle"], content_width))
            elements.append(Spacer(1, 4 * mm))

            # Certificate Title
            elements.append(_text(_lt("warranty_card_title", "WARRANTY CERTIFICATE"), st["h2"], content_width))
            if w.status in ("VOID", "CANCELLED"):
                elements.append(_text(f"[{w.status}]", st["bold"], content_width))
            elements.append(Spacer(1, 2 * mm))

            # Barcode of warranty code
            try:
                bc = code128.Code128(w.code, barHeight=12 * mm, barWidth=1.2)
                bc.hAlign = "CENTER"
                elements.append(bc)
                elements.append(_text(w.code, st["center"], content_width))
            except Exception as e:
                logger.warning("Could not generate barcode for warranty code %s: %s", w.code, e)
                elements.append(_text(w.code, st["bold"], content_width))
            elements.append(Spacer(1, 4 * mm))

            # Details Table
            sale = getattr(w, "sale", None)
            doc_no = getattr(sale, "document_number", None) or f"INV-{w.sale_id}"
            sale_date = w.start_date.strftime("%Y-%m-%d") if w.start_date else ""
            cust_name = w.customer_name_snapshot or (
                sale.customer.name if (sale and getattr(sale, "customer", None)) else "-"
            )
            cust_phone = w.customer_phone_snapshot or (
                sale.customer.phone if (sale and getattr(sale, "customer", None)) else "-"
            )

            prod = getattr(w, "product", None)
            prod_name = ProductService.display_name(prod, eff_lang) if prod else f"Product #{w.product_id}"

            unit_key = f"warranty_unit_{w.duration_unit.lower()}"
            unit_name = _lt(unit_key, w.duration_unit.capitalize())
            coverage_text = f"{w.duration} {unit_name}"
            valid_dates = f"{sale_date} — {w.end_date.strftime('%Y-%m-%d')}"
            provider = w.provider_name or _lt("warranty_type_shop", "Shop")
            remedy_key = f"warranty_remedy_{w.remedy.lower()}"
            remedy_name = _lt(remedy_key, w.remedy.replace("_", " ").title())

            table_data = [
                [
                    _text(f"{_lt('warranty_card_invoice', 'Invoice')}:", st["bold"]),
                    _text(doc_no, st["base"]),
                    _text(f"{_lt('date', 'Date')}:", st["bold"]),
                    _text(sale_date, st["base"]),
                ],
                [
                    _text(f"{_lt('customer', 'Customer')}:", st["bold"]),
                    _text(cust_name, st["base"]),
                    _text(f"{_lt('phone', 'Phone')}:", st["bold"]),
                    _text(cust_phone, st["base"]),
                ],
                [
                    _text(f"{_lt('item', 'Product')}:", st["bold"]),
                    _text(prod_name, st["bold"]),
                    _text("S/N / IMEI:", st["bold"]),
                    _text(w.serial_number or "-", st["base"]),
                ],
                [
                    _text(f"{_lt('warranty_label', 'Warranty')}:", st["bold"]),
                    _text(coverage_text, st["base"]),
                    _text(f"{_lt('provider', 'Provider')}:", st["bold"]),
                    _text(provider, st["base"]),
                ],
                [
                    _text(f"{_lt('valid_until', 'Valid Period')}:", st["bold"]),
                    _text(valid_dates, st["base"]),
                    _text(f"{_lt('warranty_card_remedy', 'Remedy')}:", st["bold"]),
                    _text(remedy_name, st["base"]),
                ],
            ]

            col_w = [26 * mm, 38 * mm, 24 * mm, 38 * mm]
            t = Table(table_data, colWidths=col_w)
            t.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_BG),
                        ("GRID", (0, 0), (-1, -1), 0.5, _BORDER_GREY),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            elements.append(t)
            elements.append(Spacer(1, 4 * mm))

            # Terms & Conditions block
            if w.terms_text:
                elements.append(_text(_lt("warranty_terms_title", "TERMS & CONDITIONS"), st["bold"], content_width))
                elements.append(_text(w.terms_text, st["terms"], content_width))
                elements.append(Spacer(1, 2 * mm))

            # Exclusions block
            if w.exclusions_text:
                elements.append(
                    _text(
                        f"{_lt('warranty_exclusions_title', 'Exclusions')}: {w.exclusions_text}",
                        st["terms"],
                        content_width,
                    )
                )
                elements.append(Spacer(1, 4 * mm))

            # Stamp / Signature Box
            stamp_box = [
                [
                    _text(_lt("warranty_stamp_title", "OFFICIAL SHOP STAMP"), st["stamp_title"]),
                    _text("AUTHORIZED SIGNATURE", st["stamp_title"]),
                ],
                [Spacer(1, 15 * mm), Spacer(1, 15 * mm)],
            ]
            t_stamp = Table(stamp_box, colWidths=[content_width / 2, content_width / 2])
            t_stamp.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (0, 1), 1, _BORDER_GREY),
                        ("BOX", (1, 0), (1, 1), 1, _BORDER_GREY),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            elements.append(t_stamp)

        # Build document atomically
        dest_path = Path(filepath).resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_fd, tmp_path = tempfile.mkstemp(prefix="warranty_card_", suffix=".pdf", dir=str(dest_path.parent))
        os.close(tmp_fd)

        try:
            doc = SimpleDocTemplate(
                tmp_path,
                pagesize=page_size,
                leftMargin=margin,
                rightMargin=margin,
                topMargin=margin,
                bottomMargin=16 * mm,
                title=f"Warranty Certificate {warranties[0].code}",
                author=shop_name,
                creator="CB POS (ceybyte.com)",
            )
            doc.build(elements, onFirstPage=_draw_branding, onLaterPages=_draw_branding)
            os.replace(tmp_path, str(dest_path))
            return str(dest_path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise
