"""Proforma/quotation receipt builder — generates receipt commands for proformas."""

from typing import List, Dict, Any, Optional, TYPE_CHECKING

from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.utils.formatters import format_currency

if TYPE_CHECKING:
    from cbpos.core.models import Proforma


class ProformaReceiptBuilder(BaseReceiptBuilder):
    """Builds receipt commands for proforma invoices / quotations."""

    @classmethod
    def build_proforma(
        cls, proforma: "Proforma", config_override: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates receipt commands for a Proforma/Quotation.

        Args:
            proforma: The Proforma model instance with items loaded.
            config_override: Optional dictionary to override ConfigService values.
        """
        cls._resolve_receipt_lang(config_override)
        commands: List[Dict[str, Any]] = []
        gc = cls._get_conf

        line_chars = cls._append_header_block(commands, config_override)

        # Title
        commands.append({"type": "text", "val": cls._rt("quotation"), "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Proforma Details
        commands.append(
            {"type": "text", "val": cls._rt("quotation_number", number=proforma.document_number), "align": "left"}
        )
        date_str = proforma.date.strftime("%Y-%m-%d %H:%M") if proforma.date else "N/A"
        commands.append({"type": "text", "val": cls._rt("quotation_date", date=date_str), "align": "left"})

        if proforma.expiry_date:
            commands.append(
                {"type": "text", "val": f"{cls._rt('valid_until')}: {proforma.expiry_date}", "align": "left"}
            )

        if proforma.customer:
            commands.append(
                {"type": "text", "val": f"{cls._rt('customer')}: {proforma.customer.name}", "align": "left"}
            )

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Items
        for item in proforma.items:
            commands.append({"type": "text", "val": item.product_name, "align": "left"})
            line = "{} x {} = {}".format(
                item.quantity,
                format_currency(item.unit_price),
                format_currency(item.line_total),
            )
            commands.append({"type": "text", "val": line, "align": "right"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Total
        commands.append(
            {
                "type": "text",
                "val": "{}: {}".format(cls._rt("total"), format_currency(proforma.total_amount)),
                "align": "right",
            }
        )

        # Tax Breakdown
        if gc("show_tax_breakdown", False, config_override):
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": "{}:".format(cls._rt("tax_breakdown")), "align": "left"})
            if proforma.tax_vat and proforma.tax_vat > 0:
                commands.append(
                    {
                        "type": "text",
                        "val": "{}: {}".format(cls._rt("vat"), format_currency(proforma.tax_vat)),
                        "align": "right",
                    }
                )
            if proforma.tax_sscl and proforma.tax_sscl > 0:
                commands.append(
                    {
                        "type": "text",
                        "val": "{}: {}".format(cls._rt("sscl"), format_currency(proforma.tax_sscl)),
                        "align": "right",
                    }
                )

        # Notes
        if proforma.notes:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": cls._rt("notes", notes=proforma.notes), "align": "left"})

        # Footer
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": cls._rt("quotation_not_invoice"), "align": "center"})
        commands.append(
            {"type": "text", "val": cls._rt("quotation_valid_days", days=proforma.validity_days), "align": "center"}
        )

        cls._append_footer_text(commands, line_chars, config_override)

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands
