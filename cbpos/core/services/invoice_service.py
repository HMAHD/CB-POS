"""A4 (Tax) Invoice PDF for a completed sale.

Printed automatically for VAT-registered customers (``PrinterService``) and
saved from Receipt Options -> Save PDF. Built after the sale's session has
closed, so it reads only what the receipt reads: the sale, its lines and
their products (with unit), its payments and its customer (#733, #740).
"""

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from cbpos.core.models import Sale
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.tax_service import TaxService
from cbpos.core.utils.formatters import format_currency, format_quantity, quantity_decimals
from cbpos.core.utils.money import round_money
from cbpos.core.utils.text_scripts import needs_raster
from cbpos.i18n import get_language, translate_in

_NAVY = colors.HexColor("#003366")
_GREY = colors.HexColor("#666666")
_SHADE = colors.HexColor("#F0F0F0")
_MARGIN = 15 * mm
_WIDTH = A4[0] - 2 * _MARGIN  # 180 mm of usable width
_BRANDING = "Powered by CB POS — ceybyte.com"


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    """One line of the invoice, as printed.

    Attributes:
        description: Product name in the invoice language.
        qty: Quantity with the unit's decimals ("2", "1.250").
        unit_price: Price per unit before the line discount (the MRP).
        discount: The line's total discount; zero when none.
        amount: What the line charged.
    """

    description: str
    qty: str
    unit_price: Decimal
    discount: Decimal
    amount: Decimal


@dataclass(frozen=True, slots=True)
class InvoiceTotals:
    """The invoice's totals block.

    Attributes:
        subtotal: Sum of the Amount column (line discounts already off).
        bill_discount: The bill-level discount; zero when none.
        total: What the sale charged (subtotal - bill_discount), taxes included.
        saved: Line discounts plus the bill discount.
    """

    subtotal: Decimal
    bill_discount: Decimal
    total: Decimal
    saved: Decimal


def _dec(value: Any) -> Decimal:
    """``value`` as a Decimal; None (an unsaved column default) is zero."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value)) if value is not None else Decimal("0")


def _pct(value: Any, default: str) -> str:
    """A rate for a label: 18.0 -> "18", 2.5 -> "2.5"."""
    rate = _dec(value if value not in (None, "") else default).normalize()
    return f"{rate:f}"


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("InvBase", fontName="Helvetica", fontSize=9, leading=12)
    bold = ParagraphStyle("InvBold", parent=base, fontName="Helvetica-Bold")
    return {
        "base": base,
        "bold": bold,
        "right": ParagraphStyle("InvRight", parent=base, alignment=TA_RIGHT),
        "right_bold": ParagraphStyle("InvRightBold", parent=bold, alignment=TA_RIGHT, fontSize=10.5, leading=14),
        "shop": ParagraphStyle("InvShop", parent=bold, fontSize=15, leading=19),
        "title": ParagraphStyle(
            "InvTitle", parent=bold, fontSize=18, leading=22, alignment=TA_RIGHT, textColor=colors.HexColor("#001F3F")
        ),
        "th": ParagraphStyle("InvTh", parent=bold, alignment=TA_CENTER, textColor=colors.whitesmoke),
        "muted": ParagraphStyle("InvMuted", parent=base, textColor=_GREY),
        "muted_right": ParagraphStyle("InvMutedRight", parent=base, textColor=_GREY, alignment=TA_RIGHT),
    }


def _text(text: Any, style: ParagraphStyle, width: float | None = None) -> Flowable:
    """A paragraph of *text*; Sinhala/Tamil is drawn by Qt so it is shaped correctly.

    Args:
        text: What to show.
        style: Font, size, colour and alignment.
        width: Wrap width in points for Sinhala/Tamil text.
    """
    text = str(text or "")
    if not needs_raster(text):
        return Paragraph(escape(text), style)
    # Qt only when there is Sinhala/Tamil to draw: the service itself imports no PyQt.
    from cbpos.infrastructure.hardware.text_raster import render_text_png

    align = {TA_CENTER: "center", TA_RIGHT: "right"}.get(style.alignment, "left")
    png, w, h = render_text_png(
        text,
        style.fontSize,
        bold=style.fontName.endswith("Bold"),
        color="#" + style.textColor.hexval()[2:],
        max_width_pt=width,
        align=align,
    )
    image = Image(BytesIO(png), width=w, height=h)
    image.hAlign = align.upper()
    return image


def _pairs(rows: list[tuple[str, str]], st: dict[str, ParagraphStyle], widths: tuple[float, float]) -> Table:
    """A borderless label/value block (label and value kept apart so values stay selectable text)."""
    table = Table(
        [[_text(label, st["muted"], widths[0] - 3 * mm), _text(value, st["bold"], widths[1])] for label, value in rows],
        colWidths=list(widths),
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    return table


def _draw_branding(canvas: Any, _doc: Any) -> None:
    """CB POS branding at the foot of every page."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_GREY)
    canvas.drawCentredString(A4[0] / 2, 10 * mm, _BRANDING)
    canvas.restoreState()


class InvoiceService:
    """Builds the A4 Tax Invoice PDF for a sale (Sri Lankan MRP pricing: taxes are inside the price)."""

    @staticmethod
    def invoice_language() -> str:
        """The invoice's language: the receipt language, else the UI language."""
        return ConfigService.get("receipt_language") or get_language() or "en"

    @staticmethod
    def bank_detail_lines(lang: str | None = None) -> list[str]:
        """Return the invoice's bank-detail lines from Settings -> Shop Info.

        Reads the keys the Shop Info page saves (it used to read bank_name /
        bank_account / bank_branch, which nothing wrote, so it never printed).
        Empty when neither a bank name nor an account number is set.

        Args:
            lang: Language of the labels; defaults to the invoice language.
        """
        bank_name = ConfigService.get("company_bank_name") or ""
        bank_account = ConfigService.get("company_account_number") or ""
        bank_branch = ConfigService.get("company_bank_branch") or ""
        if not (bank_name or bank_account):
            return []
        lang = lang or InvoiceService.invoice_language()
        lines = []
        if bank_name:
            lines.append(translate_in(lang, "invoice.bank_name", name=bank_name))
        if bank_account:
            lines.append(translate_in(lang, "invoice.bank_account", number=bank_account))
        if bank_branch:
            lines.append(translate_in(lang, "invoice.bank_branch", name=bank_branch))
        return lines

    @staticmethod
    def invoice_lines(sale: Sale, lang: str) -> list[InvoiceLine]:
        """The sale's lines as the invoice prints them.

        The discount is what the line came down from its MRP (the same rule
        the receipt uses); a manual price above the MRP is not a discount.

        Args:
            sale: The sale (lines and their products loaded).
            lang: Language for the product names.
        """
        lines = []
        for item in sale.items:
            qty = _dec(item.qty)
            charged = _dec(item.unit_price)
            listed = max(_dec(item.original_price) if item.original_price is not None else charged, charged)
            unit = item.product.unit
            lines.append(
                InvoiceLine(
                    description=ProductService.display_name(item.product, lang),
                    qty=format_quantity(qty, quantity_decimals(unit) if unit is not None else 0),
                    unit_price=listed,
                    discount=round_money((listed - charged) * qty),
                    amount=_dec(item.subtotal),
                )
            )
        return lines

    @staticmethod
    def invoice_totals(sale: Sale, lines: list[InvoiceLine]) -> InvoiceTotals:
        """The totals block, reconciling with the Amount column.

        Line discounts are already inside each line's amount (and shown in
        its Discount column), so the sub total is the Amount column's sum
        and only the bill discount comes off it: sub total - bill discount
        = total.

        Args:
            sale: The sale.
            lines: ``invoice_lines(sale, ...)``.
        """
        subtotal = sum((line.amount for line in lines), Decimal("0"))
        total = _dec(sale.total_amount)
        bill_discount = max(subtotal - total, Decimal("0"))
        line_discounts = sum((line.discount for line in lines), Decimal("0"))
        return InvoiceTotals(
            subtotal=subtotal, bill_discount=bill_discount, total=total, saved=line_discounts + bill_discount
        )

    @staticmethod
    def _shows_vat(sale: Sale) -> bool:
        """A tax invoice (VAT rows, VAT numbers) when the shop is VAT registered or the sale carried VAT."""
        return TaxService.is_vat_active() or _dec(sale.tax_vat) > 0

    @staticmethod
    def generate_pdf(sale: Sale, filepath: str) -> str:
        """Write the A4 (Tax) Invoice PDF for *sale*.

        In the receipt language. A VAT-registered shop (or a sale that
        carried tax) gets a TAX INVOICE with both VAT numbers and the VAT /
        SSCL inside the MRP total, as stored on the sale; otherwise a plain
        INVOICE. Every page carries the CB POS branding.

        Args:
            sale: The sale; may be detached (lines with products, payments and customer loaded).
            filepath: Where to write the PDF; missing folders are created.

        Returns:
            The path written.

        Raises:
            Exception: If the PDF can't be built or written; callers tell the cashier.
        """
        lang = InvoiceService.invoice_language()

        def t(key: str, **kwargs: Any) -> str:
            return translate_in(lang, f"invoice.{key}", **kwargs)

        st = _styles()
        show_vat = InvoiceService._shows_vat(sale)
        lines = InvoiceService.invoice_lines(sale, lang)
        # Ordinary commercial invoices must always be titled "INVOICE", never "TAX INVOICE" (#814)
        title = t("title")

        elements: list[Flowable] = [
            InvoiceService._header(sale, title, show_vat, t, st),
            Spacer(1, 6 * mm),
            InvoiceService._bill_to(sale, t, st),
            Spacer(1, 6 * mm),
            InvoiceService._items_table(lines, t, st),
            Spacer(1, 3 * mm),
            InvoiceService._totals(sale, lines, show_vat, t, st),
        ]
        bank_lines = InvoiceService.bank_detail_lines(lang)
        if bank_lines:
            elements.append(Spacer(1, 6 * mm))
            elements.append(_text(t("bank_details"), st["bold"], _WIDTH))
            elements.extend(_text(line, st["base"], _WIDTH) for line in bank_lines)
        elements.append(Spacer(1, 18 * mm))
        elements.append(InvoiceService._signatures(t, st))

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            leftMargin=_MARGIN,
            rightMargin=_MARGIN,
            topMargin=_MARGIN,
            bottomMargin=20 * mm,
            title=f"{title} {sale.document_number or ''}".strip(),
            author=ConfigService.get("shop_name") or "",
            creator="CB POS (ceybyte.com)",
        )
        doc.build(elements, onFirstPage=_draw_branding, onLaterPages=_draw_branding)
        return filepath

    @staticmethod
    def _header(sale: Sale, title: str, show_vat: bool, t: Any, st: dict[str, ParagraphStyle]) -> Table:
        """Shop identity (left) and the title with invoice number, date and payment (right)."""
        shop: list[Flowable] = [_text(ConfigService.get("shop_name") or "", st["shop"], 100 * mm)]
        for line in (ConfigService.get("shop_address"), ConfigService.get("shop_phone")):
            if line:
                shop.append(_text(line, st["base"], 100 * mm))
        ids = []
        if ConfigService.get("company_tax_id"):
            ids.append((t("tin"), ConfigService.get("company_tax_id")))
        if show_vat and ConfigService.get("vat_number"):
            ids.append((t("vat_no"), ConfigService.get("vat_number")))
        if ids:
            shop.append(Spacer(1, 2 * mm))
            shop.append(_pairs(ids, st, (35 * mm, 60 * mm)))

        methods = [p.payment_method for p in (sale.payments or [])] or [sale.payment_method or ""]
        meta = [
            (t("invoice_no"), sale.document_number or ""),
            (t("date"), sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else ""),
            (t("payment"), ", ".join(dict.fromkeys(m.upper() for m in methods if m))),
        ]
        right: list[Flowable] = [_text(title, st["title"], 80 * mm), Spacer(1, 3 * mm)]
        meta_table = _pairs(meta, st, (38 * mm, 42 * mm))
        meta_table.hAlign = "RIGHT"
        right.append(meta_table)

        header = Table([[shop, right]], colWidths=[100 * mm, 80 * mm])
        header.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, 0), (-1, 0), 1, _NAVY),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 4 * mm),
                ]
            )
        )
        return header

    @staticmethod
    def _bill_to(sale: Sale, t: Any, st: dict[str, ParagraphStyle]) -> Table:
        """The buyer: name, company, address, phone, TIN and VAT number."""
        width = 100 * mm
        block: list[Flowable] = [_text(t("bill_to"), st["muted"], width)]
        customer = sale.customer
        if customer is None:
            block.append(_text(t("walk_in"), st["bold"], width))
        else:
            block.append(_text(customer.name, st["bold"], width))
            for line in (customer.company_name, customer.address, customer.phone):
                if line and line != customer.name:
                    block.append(_text(line, st["base"], width))
            ids = []
            if customer.tax_id:
                ids.append((t("tin"), customer.tax_id))
            if customer.vat_number:
                ids.append((t("vat_no"), customer.vat_number))
            if ids:
                block.append(_pairs(ids, st, (35 * mm, 60 * mm)))
        table = Table([[block]], colWidths=[width], hAlign="LEFT")
        table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        return table

    @staticmethod
    def _items_table(lines: list[InvoiceLine], t: Any, st: dict[str, ParagraphStyle]) -> Table:
        """# | Description | Qty | Unit Price | Discount | Amount."""
        widths = [8 * mm, 72 * mm, 18 * mm, 28 * mm, 26 * mm, 28 * mm]
        header = ["#", "col_description", "col_qty", "col_unit_price", "col_discount", "col_amount"]
        data: list[list[Any]] = [
            [_text(key if key == "#" else t(key), st["th"], w - 4 * mm) for key, w in zip(header, widths, strict=True)]
        ]
        for idx, line in enumerate(lines, start=1):
            data.append(
                [
                    str(idx),
                    _text(line.description, st["base"], widths[1] - 4 * mm),
                    line.qty,
                    format_currency(line.unit_price),
                    format_currency(line.discount) if line.discount else "-",
                    format_currency(line.amount),
                ]
            )
        table = Table(data, colWidths=widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("ALIGN", (0, 1), (0, -1), "CENTER"),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
                ]
            )
        )
        return table

    @staticmethod
    def _totals(sale: Sale, lines: list[InvoiceLine], show_vat: bool, t: Any, st: dict[str, ParagraphStyle]) -> Table:
        """Sub total, discounts and the total; then the VAT / SSCL already inside it (MRP back-calculation).

        The tax figures are the ones stored on the sale when it was rung up
        (``TaxService.calculate_taxes``), so a reprint after a rate change
        still matches what was charged: net + VAT + SSCL = total.
        """
        label_w, value_w = 130 * mm, 50 * mm
        totals = InvoiceService.invoice_totals(sale, lines)
        total = totals.total

        rows: list[tuple[str, str]] = [(t("subtotal"), format_currency(totals.subtotal))]
        if totals.bill_discount > 0:
            if (sale.additional_discount_type or "NONE") == "PERCENTAGE":
                label = t("bill_discount_pct", pct=_pct(sale.additional_discount_value, "0"))
            else:
                label = t("bill_discount")
            rows.append((label, f"-{format_currency(totals.bill_discount)}"))
        total_row = len(rows)
        rows.append((t("total"), format_currency(total)))
        saved_row = None
        if totals.saved > 0:
            saved_row = len(rows)
            rows.append((t("you_saved", amount=format_currency(totals.saved)), ""))

        if show_vat:
            rows.append((t("taxes_included"), ""))
            exempt = _dec(
                sale.vat_exempt_amount if sale.vat_exempt_amount is not None else getattr(sale, "_exempt_amount", None)
            )
            taxable = _dec(sale.taxable_amount) if sale.taxable_amount is not None else (total - exempt)
            if exempt > 0:
                rows.append((t("taxable"), format_currency(taxable)))
                rows.append((t("exempt"), format_currency(exempt)))
            # SSCL is a business levy hidden from customer invoices (D9/D25, #831); customer net value is gross minus customer-facing VAT
            net_val = total - _dec(sale.tax_vat)
            rows.append((t("net_value"), format_currency(net_val)))
            vat_rate = TaxService.resolve_historical_vat_rate(sale)
            vat_rate_str = TaxService.format_rate(vat_rate)
            rows.append((t("vat", rate=vat_rate_str), format_currency(sale.tax_vat)))

        data = []
        for i, (label, value) in enumerate(rows):
            if i == saved_row:  # one muted line across both columns, under the total
                data.append([_text(label, st["muted_right"], label_w + value_w - 6 * mm), ""])
                continue
            style = st["right_bold"] if i == total_row else st["right"]
            data.append([_text(label, style, label_w - 6 * mm), _text(value, style)])
        tax_row = (saved_row if saved_row is not None else total_row) + 1
        commands = [
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LINEABOVE", (1, total_row), (1, total_row), 1, colors.black),
            ("BACKGROUND", (1, total_row), (1, total_row), _SHADE),
            ("TOPPADDING", (0, tax_row), (-1, tax_row), 3 * mm),
        ]
        if saved_row is not None:
            commands.append(("SPAN", (0, saved_row), (1, saved_row)))
        table = Table(data, colWidths=[label_w, value_w])
        table.setStyle(TableStyle(commands))
        return table

    @staticmethod
    def _signatures(t: Any, st: dict[str, ParagraphStyle]) -> Table:
        """Signature lines: the shop's authorized signature and the buyer's."""
        table = Table(
            [
                ["", "", ""],
                [
                    _text(t("authorized_signature"), st["muted"], 65 * mm),
                    "",
                    _text(t("received_by"), st["muted"], 65 * mm),
                ],
            ],
            colWidths=[70 * mm, 40 * mm, 70 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("LINEABOVE", (0, 1), (0, 1), 0.5, colors.black),
                    ("LINEABOVE", (2, 1), (2, 1), 0.5, colors.black),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return table
