"""Thermal receipt builder for warranty claim intake and collection slips (#826, #820)."""

import logging
from datetime import datetime
from typing import Any

from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.services.warranty_dto import WarrantyClaimDTO
from cbpos.core.utils.barcode import calculate_barcode_width, choose_barcode
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t, translate_in

logger = logging.getLogger(__name__)


class WarrantyClaimReceiptBuilder(BaseReceiptBuilder):
    """Builds thermal printer commands for warranty claim intake and collection slips."""

    @classmethod
    def _tr(cls, key: str, **kwargs) -> str:
        """Resolve localized text using the resolved receipt language."""
        lang = cls._receipt_lang
        if lang:
            return translate_in(lang, key, **kwargs)
        return _t(key, **kwargs)

    @classmethod
    def build_intake_slip(
        cls,
        claim: WarrantyClaimDTO,
        config_override: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate thermal commands for an intake acknowledgment slip."""
        cls._resolve_receipt_lang(config_override)
        commands: list[dict[str, Any]] = []

        line_chars = cls._append_header_block(commands, config_override)
        paper_width = cls._get_conf("paper_width", "80mm", config_override)

        # Title
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append(
            {
                "type": "text",
                "val": cls._tr("warranty_claim.intake_slip_title", default="WARRANTY CLAIM INTAKE"),
                "align": "center",
                "bold": True,
            }
        )
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Claim number and barcode
        commands.append({"type": "text", "val": f"{claim.document_number}", "align": "center", "bold": True})
        bw = calculate_barcode_width(claim.document_number, paper_width)
        if bw is not None:
            chosen_type, payload = choose_barcode(claim.document_number)
            commands.append(
                {
                    "type": "barcode",
                    "val": payload,
                    "code": chosen_type,
                    "align": "center",
                    "width": bw,
                    "height": 50,
                }
            )
        commands.append({"type": "feed", "lines": 1})

        # Metadata
        date_str = claim.intake_date.strftime("%Y-%m-%d %H:%M") if claim.intake_date else ""
        commands.append(cls._split_row(cls._tr("common.date", default="Date"), date_str, line_chars))
        commands.append(cls._split_row(cls._tr("common.status", default="Status"), claim.claim_status, line_chars))

        covered_str = (
            cls._tr("warranty_claim.covered_yes", default="Yes (Under Warranty)")
            if claim.is_covered
            else cls._tr("warranty_claim.covered_no", default="Out of Warranty / Chargeable")
        )
        commands.append(cls._split_row(cls._tr("warranty_claim.coverage", default="Coverage"), covered_str, line_chars))
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Customer & Item details
        commands.append(
            {
                "type": "text",
                "val": f"{cls._tr('common.customer', default='Customer')}: {claim.customer_name or 'N/A'}",
                "align": "left",
            }
        )
        if claim.customer_phone:
            commands.append(
                {
                    "type": "text",
                    "val": f"{cls._tr('common.phone', default='Phone')}: {claim.customer_phone}",
                    "align": "left",
                }
            )
        commands.append(
            {
                "type": "text",
                "val": f"{cls._tr('common.product', default='Product')}: {claim.product_name}",
                "align": "left",
            }
        )
        if claim.item_serial:
            commands.append(
                {
                    "type": "text",
                    "val": f"{cls._tr('warranty.serial_number', default='Serial')}: {claim.item_serial}",
                    "align": "left",
                }
            )
        if claim.warranty_code:
            commands.append(
                {
                    "type": "text",
                    "val": f"{cls._tr('warranty.title', default='Warranty')}: {claim.warranty_code}",
                    "align": "left",
                }
            )
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Defect & Condition
        commands.append(
            {
                "type": "text",
                "val": f"{cls._tr('warranty_claim.defect', default='Defect')}:",
                "align": "left",
                "bold": True,
            }
        )
        commands.append({"type": "text", "val": f"  {claim.defect_description}", "align": "left"})

        if claim.item_condition:
            commands.append(
                {
                    "type": "text",
                    "val": f"{cls._tr('warranty_claim.condition', default='Condition')}: {claim.item_condition}",
                    "align": "left",
                }
            )
        if claim.accessories_received:
            commands.append(
                {
                    "type": "text",
                    "val": f"{cls._tr('warranty_claim.accessories', default='Accessories')}: {claim.accessories_received}",
                    "align": "left",
                }
            )

        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Terms & Disclaimer
        disclaimer = cls._tr(
            "warranty_claim.intake_disclaimer",
            default="Please retain this slip for collecting your item. Items not collected within 30 days may incur storage fees.",
        )
        commands.append({"type": "text", "val": disclaimer, "align": "center"})
        commands.append({"type": "feed", "lines": 2})

        # Signature lines
        commands.append(
            {
                "type": "text",
                "val": f"{cls._tr('warranty_claim.cust_signature', default='Customer Signature')}: ___________________",
                "align": "left",
            }
        )
        commands.append({"type": "feed", "lines": 1})
        commands.append(
            {
                "type": "text",
                "val": f"{cls._tr('warranty_claim.staff_signature', default='Authorized Staff')}: ___________________",
                "align": "left",
            }
        )

        commands.append({"type": "feed", "lines": 2})
        commands.append({"type": "cut"})
        return commands

    @classmethod
    def build_collection_slip(
        cls,
        claim: WarrantyClaimDTO,
        config_override: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate thermal commands for a completed collection receipt slip."""
        cls._resolve_receipt_lang(config_override)
        commands: list[dict[str, Any]] = []

        line_chars = cls._append_header_block(commands, config_override)

        # Title
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append(
            {
                "type": "text",
                "val": cls._tr("warranty_claim.collection_slip_title", default="WARRANTY CLAIM COLLECTION"),
                "align": "center",
                "bold": True,
            }
        )
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Claim info
        commands.append(
            cls._split_row(cls._tr("warranty_claim.claim_no", default="Claim No"), claim.document_number, line_chars)
        )
        collected_date = claim.collected_at or datetime.now()
        commands.append(
            cls._split_row(
                cls._tr("common.date", default="Date"), collected_date.strftime("%Y-%m-%d %H:%M"), line_chars
            )
        )
        commands.append(
            cls._split_row(cls._tr("common.customer", default="Customer"), claim.customer_name or "N/A", line_chars)
        )
        commands.append(cls._split_row(cls._tr("common.product", default="Product"), claim.product_name, line_chars))
        if claim.item_serial:
            commands.append(
                cls._split_row(cls._tr("warranty.serial_number", default="Serial"), claim.item_serial, line_chars)
            )

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Resolution details
        res_text = claim.resolution or "COMPLETED"
        commands.append(
            cls._split_row(cls._tr("warranty_claim.resolution", default="Resolution"), res_text, line_chars)
        )
        if claim.resolution_notes:
            commands.append(
                {
                    "type": "text",
                    "val": f"{cls._tr('common.notes', default='Notes')}: {claim.resolution_notes}",
                    "align": "left",
                }
            )
        if claim.replacement_serial:
            commands.append(
                cls._split_row(
                    cls._tr("warranty_claim.replacement_serial", default="Replacement Serial"),
                    claim.replacement_serial,
                    line_chars,
                )
            )

        if claim.charge_customer and claim.charge_customer > 0:
            commands.append(
                cls._split_row(
                    cls._tr("warranty_claim.service_charge", default="Service Charge"),
                    format_currency(claim.charge_customer),
                    line_chars,
                )
            )

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})
        commands.append(
            {
                "type": "text",
                "val": f"{cls._tr('warranty_claim.collected_by', default='Collected By')}: {claim.collected_by_name or 'N/A'}",
                "align": "left",
            }
        )
        commands.append({"type": "feed", "lines": 2})

        commands.append(
            {
                "type": "text",
                "val": f"{cls._tr('warranty_claim.received_satisfaction', default='Received in good order')}: ___________________",
                "align": "left",
            }
        )

        commands.append({"type": "feed", "lines": 2})
        commands.append({"type": "cut"})
        return commands

    @classmethod
    def build_supplier_dispatch_receipt(
        cls,
        claim: WarrantyClaimDTO,
        config_override: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate thermal printer commands for dispatching a claim to supplier (RMA) (#828).

        NOTE: Customer PII (name, phone, address) is STRICTLY OMITTED to protect customer privacy.
        """
        cls._resolve_receipt_lang(config_override)
        commands: list[dict[str, Any]] = []

        line_chars = cls._append_header_block(commands, config_override)
        paper_width = cls._get_conf("paper_width", "80mm", config_override)

        # Title
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append(
            {
                "type": "text",
                "val": cls._tr("warranty_claim.supplier_dispatch_slip_title", default="SUPPLIER RMA DISPATCH NOTE"),
                "align": "center",
                "bold": True,
            }
        )
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Claim number and barcode
        commands.append({"type": "text", "val": f"{claim.document_number}", "align": "center", "bold": True})
        bw = calculate_barcode_width(claim.document_number, paper_width)
        if bw is not None:
            chosen_type, payload = choose_barcode(claim.document_number)
            commands.append(
                {
                    "type": "barcode",
                    "val": payload,
                    "code": chosen_type,
                    "align": "center",
                    "width": bw,
                    "height": 50,
                }
            )
        commands.append({"type": "feed", "lines": 1})

        # Metadata
        disp_time = claim.sent_to_supplier_at or datetime.now()
        commands.append(
            cls._split_row(cls._tr("common.date", default="Date"), disp_time.strftime("%Y-%m-%d %H:%M"), line_chars)
        )
        commands.append(
            cls._split_row(
                cls._tr("warranty_claim.supplier_select", default="Supplier"),
                claim.supplier_name or "N/A",
                line_chars,
            )
        )
        if claim.supplier_rma_ref:
            commands.append(
                cls._split_row(
                    cls._tr("warranty_claim.supplier_rma_ref", default="RMA / Waybill Ref"),
                    claim.supplier_rma_ref,
                    line_chars,
                )
            )

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Product details (NO CUSTOMER PII)
        commands.append(cls._split_row(cls._tr("common.product", default="Product"), claim.product_name, line_chars))
        if claim.item_serial:
            commands.append(
                cls._split_row(cls._tr("warranty.serial_number", default="Serial/IMEI"), claim.item_serial, line_chars)
            )
        if claim.item_condition:
            commands.append(
                cls._split_row(
                    cls._tr("warranty_claim.condition", default="Condition"),
                    claim.item_condition,
                    line_chars,
                )
            )
        if claim.accessories_received:
            commands.append(
                cls._split_row(
                    cls._tr("warranty_claim.accessories", default="Accessories"),
                    claim.accessories_received,
                    line_chars,
                )
            )

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Defect details
        commands.append(
            {
                "type": "text",
                "val": f"{cls._tr('warranty_claim.defect', default='Reported Fault')}:",
                "align": "left",
                "bold": True,
            }
        )
        commands.append(
            {
                "type": "text",
                "val": f"{claim.defect_description}",
                "align": "left",
            }
        )

        commands.append({"type": "feed", "lines": 2})

        # Signatures
        commands.append(
            {
                "type": "text",
                "val": f"{cls._tr('warranty_claim.dispatched_by', default='Dispatched By')}: ___________________",
                "align": "left",
            }
        )
        commands.append({"type": "feed", "lines": 1})
        commands.append(
            {
                "type": "text",
                "val": f"{cls._tr('warranty_claim.acknowledged_by', default='Received By Supplier/Courier')}: ___________________",
                "align": "left",
            }
        )

        commands.append({"type": "feed", "lines": 2})
        commands.append({"type": "cut"})
        return commands

    @classmethod
    def build_supplier_dispatch_pdf(
        cls,
        claim: WarrantyClaimDTO,
        output_path: str,
        config_override: dict[str, Any] | None = None,
    ) -> str:
        """Generate A5 vector PDF waybill for dispatching defective item to supplier/manufacturer (#828).

        NOTE: Customer PII is strictly excluded.
        """
        from html import escape
        from io import BytesIO

        from reportlab.graphics.barcode import code128
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A5
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Flowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        from cbpos.core.services.config_service import ConfigService
        from cbpos.core.utils.text_scripts import needs_raster

        navy = colors.HexColor("#0B2545")
        border_grey = colors.HexColor("#CBD5E1")
        grey = colors.HexColor("#64748B")
        light_bg = colors.HexColor("#F8FAFC")

        styles = {
            "title": ParagraphStyle(
                "Title", fontName="Helvetica-Bold", fontSize=15, leading=18, alignment=TA_CENTER, textColor=navy
            ),
            "subtitle": ParagraphStyle(
                "Subtitle", fontName="Helvetica", fontSize=9, leading=12, alignment=TA_CENTER, textColor=grey
            ),
            "h2": ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=navy),
            "bold": ParagraphStyle("Bold", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=navy),
            "base": ParagraphStyle("Base", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.black),
            "right": ParagraphStyle("Right", fontName="Helvetica", fontSize=9, leading=12, alignment=TA_RIGHT),
            "muted": ParagraphStyle("Muted", fontName="Helvetica", fontSize=8, leading=10, textColor=grey),
        }

        def _p(text: Any, style: ParagraphStyle) -> Flowable:
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
                align=align,
            )
            img = Image(BytesIO(png), width=w, height=h)
            img.hAlign = align.upper()
            return img

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A5,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
        )

        elements: list[Flowable] = []

        # Shop Header
        shop_name = ConfigService.get("receipt_header") or ConfigService.get("shop_name") or "CB POS Shop"
        shop_address = ConfigService.get("receipt_sub_header") or ""
        elements.append(_p(shop_name, styles["title"]))
        if shop_address:
            elements.append(_p(shop_address, styles["subtitle"]))
        elements.append(Spacer(1, 4 * mm))

        # Title Block
        elements.append(_p("SUPPLIER RMA DISPATCH WAYBILL", styles["h2"]))
        elements.append(Spacer(1, 2 * mm))

        # Meta Table: Claim #, Date, Supplier, RMA Ref
        disp_time = claim.sent_to_supplier_at or datetime.now()
        meta_data = [
            [
                _p("Claim Number:", styles["bold"]),
                _p(claim.document_number, styles["base"]),
                _p("Dispatch Date:", styles["bold"]),
                _p(disp_time.strftime("%Y-%m-%d %H:%M"), styles["base"]),
            ],
            [
                _p("Supplier:", styles["bold"]),
                _p(claim.supplier_name or "N/A", styles["base"]),
                _p("RMA / Waybill Ref:", styles["bold"]),
                _p(claim.supplier_rma_ref or "N/A", styles["base"]),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[30 * mm, 35 * mm, 30 * mm, 35 * mm])
        meta_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), light_bg),
                    ("BOX", (0, 0), (-1, -1), 0.5, border_grey),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, border_grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(meta_table)
        elements.append(Spacer(1, 4 * mm))

        # Barcode
        barcode_flowable = code128.Code128(claim.document_number, barHeight=14 * mm, barWidth=1.2)
        barcode_flowable.hAlign = "CENTER"
        elements.append(barcode_flowable)
        elements.append(Spacer(1, 4 * mm))

        # Product & Defect Table
        prod_data = [
            [_p("Product Model:", styles["bold"]), _p(claim.product_name, styles["base"])],
            [_p("Serial / IMEI:", styles["bold"]), _p(claim.item_serial or "N/A", styles["base"])],
            [_p("Physical Condition:", styles["bold"]), _p(claim.item_condition or "N/A", styles["base"])],
            [_p("Accessories Included:", styles["bold"]), _p(claim.accessories_received or "None", styles["base"])],
            [_p("Reported Defect:", styles["bold"]), _p(claim.defect_description, styles["base"])],
        ]
        prod_table = Table(prod_data, colWidths=[40 * mm, 90 * mm])
        prod_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, border_grey),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, border_grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        elements.append(prod_table)
        elements.append(Spacer(1, 8 * mm))

        # Signatures
        sig_data = [
            [
                _p("Dispatched By (Shop Staff):", styles["bold"]),
                _p("Received By (Supplier / Courier):", styles["bold"]),
            ],
            [
                _p("Signature: _______________________", styles["base"]),
                _p("Signature: _______________________", styles["base"]),
            ],
            [
                _p("Date: ____________________________", styles["base"]),
                _p("Date: ____________________________", styles["base"]),
            ],
        ]
        sig_table = Table(sig_data, colWidths=[65 * mm, 65 * mm])
        sig_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        elements.append(sig_table)

        doc.build(elements)
        return output_path
