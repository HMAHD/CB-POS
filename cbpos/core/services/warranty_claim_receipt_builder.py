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
