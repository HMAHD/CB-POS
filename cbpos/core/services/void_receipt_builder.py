"""Void receipt builder — generates receipt commands for voided sales."""

from datetime import datetime
from typing import List, Dict, Any, Optional

from cbpos.core.models import Sale
from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.utils.formatters import format_currency


class VoidReceiptBuilder(BaseReceiptBuilder):
    """Builds receipt commands for voided sales."""

    @classmethod
    def build_void_receipt(
        cls,
        sale: Sale,
        void_reason: str = "",
        authorized_by: str = "",
        config_override: Optional[Dict[str, Any]] = None,
        void_timestamp: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generates a VOID receipt with distinct visual treatment.

        Args:
            sale: The voided Sale.
            void_reason: Human-readable void reason.
            authorized_by: Username who authorized the void.
            config_override: Optional config overrides.
            void_timestamp: Timestamp for the void (defaults to now).
        """
        cls._resolve_receipt_lang(config_override)
        commands: List[Dict[str, Any]] = []

        line_chars = cls._append_header_block(commands, config_override)

        # VOID header
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "text", "val": cls._rt("voided"), "align": "center"})
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Original sale reference
        doc_num = getattr(sale, "document_number", None) or str(sale.id)
        commands.append({"type": "text", "val": f"{cls._rt('original_receipt')}: {doc_num}", "align": "left"})
        date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
        commands.append({"type": "text", "val": f"{cls._rt('date')}: {date_str}", "align": "left"})
        commands.append(
            {
                "type": "text",
                "val": "{}: {}".format(cls._rt("total"), format_currency(sale.total_amount)),
                "align": "left",
            }
        )

        # Tax reversal breakdown
        from cbpos.core.services.tax_service import TaxService

        gc = cls._get_conf
        has_stored_tax = (sale.tax_vat and sale.tax_vat > 0) or (sale.tax_sscl and sale.tax_sscl > 0)
        if gc("show_tax_breakdown", False, config_override) and (TaxService.is_vat_active() or has_stored_tax):
            if sale.tax_vat and sale.tax_vat > 0:
                commands.append(
                    cls._split_row(
                        "  {}".format(cls._rt("vat_reversed", vat=cls._rt("vat"))),
                        "-{}".format(format_currency(sale.tax_vat)),
                        line_chars,
                    )
                )
            if sale.tax_sscl and sale.tax_sscl > 0:
                commands.append(
                    cls._split_row(
                        "  {}".format(cls._rt("sscl_reversed", sscl=cls._rt("sscl"))),
                        "-{}".format(format_currency(sale.tax_sscl)),
                        line_chars,
                    )
                )

        if void_reason:
            commands.append({"type": "text", "val": f"{cls._rt('void_reason')}: {void_reason}", "align": "left"})
        if authorized_by:
            commands.append({"type": "text", "val": f"{cls._rt('authorized_by')}: {authorized_by}", "align": "left"})

        void_time_obj = void_timestamp or datetime.now()
        void_time = void_time_obj.strftime("%Y-%m-%d %H:%M")
        commands.append({"type": "text", "val": cls._rt("void_time", time=void_time), "align": "left"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Items (for reference)
        for item in sale.items:
            product_name = item.product.name_en if hasattr(item, "product") and item.product else "Unknown"
            line = "{} x {} = {}".format(item.qty, format_currency(item.unit_price), format_currency(item.subtotal))
            commands.append({"type": "text", "val": product_name, "align": "left"})
            commands.append({"type": "text", "val": line, "align": "right"})

        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "text", "val": cls._rt("voided"), "align": "center"})
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands
