"""Refund receipt builder — generates receipt commands for refunded sales."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from cbpos.core.models import Sale
from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.utils.formatters import format_currency


class RefundReceiptBuilder(BaseReceiptBuilder):
    """Builds receipt commands for refunded sales."""

    @classmethod
    def build_refund_receipt(
        cls,
        sale: Sale,
        refund_amount: Decimal | None = None,
        authorized_by: str = "",
        config_override: dict[str, Any] | None = None,
        refund_timestamp: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Generates a REFUND receipt with distinct visual treatment.

        Args:
            sale: The original Sale being refunded.
            refund_amount: Amount refunded (defaults to sale total).
            authorized_by: Username who authorized the refund.
            config_override: Optional config overrides.
            refund_timestamp: Timestamp for the refund (defaults to now).
        """
        cls._resolve_receipt_lang(config_override)
        commands: list[dict[str, Any]] = []

        line_chars = cls._append_header_block(commands, config_override)

        # REFUND header
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "text", "val": cls._rt("refund_label"), "align": "center"})
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Original sale reference
        doc_num = getattr(sale, "document_number", None) or str(sale.id)
        commands.append({"type": "text", "val": f"{cls._rt('original_receipt')}: {doc_num}", "align": "left"})
        date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
        commands.append({"type": "text", "val": f"{cls._rt('date')}: {date_str}", "align": "left"})

        if authorized_by:
            commands.append({"type": "text", "val": f"{cls._rt('authorized_by')}: {authorized_by}", "align": "left"})

        refund_time_obj = refund_timestamp or datetime.now()
        refund_time = refund_time_obj.strftime("%Y-%m-%d %H:%M")
        commands.append({"type": "text", "val": cls._rt("refund_time", time=refund_time), "align": "left"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Items
        for item in sale.items:
            product_name = item.product.name_en if hasattr(item, "product") and item.product else "Unknown"
            line = (
                f"{cls._format_item_qty(item)} x {format_currency(item.unit_price)} = {format_currency(item.subtotal)}"
            )
            commands.append({"type": "text", "val": product_name, "align": "left"})
            commands.append({"type": "text", "val": line, "align": "right"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        amount = refund_amount if refund_amount is not None else sale.total_amount
        commands.append(
            {
                "type": "text",
                "val": cls._rt("refund_total", total_label=cls._rt("total"), amount=format_currency(amount)),
                "align": "right",
            }
        )

        # Tax breakdown on refund
        from cbpos.core.services.tax_service import TaxService

        gc = cls._get_conf
        has_stored_tax = (sale.tax_vat and sale.tax_vat > 0) or (sale.tax_sscl and sale.tax_sscl > 0)
        if gc("show_tax_breakdown", False, config_override) and (TaxService.is_vat_active() or has_stored_tax):
            if sale.tax_vat and sale.tax_vat > 0:
                commands.append(
                    cls._split_row(
                        "  {}".format(cls._rt("vat_refund", vat=cls._rt("vat"))),
                        f"-{format_currency(sale.tax_vat)}",
                        line_chars,
                    )
                )
            if sale.tax_sscl and sale.tax_sscl > 0:
                commands.append(
                    cls._split_row(
                        "  {}".format(cls._rt("sscl_refund", sscl=cls._rt("sscl"))),
                        f"-{format_currency(sale.tax_sscl)}",
                        line_chars,
                    )
                )

        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "text", "val": cls._rt("refund_label"), "align": "center"})
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands
