"""Refund receipt builder — generates receipt commands for refunded sales."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from cbpos.core.models import Sale
from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.services.refund_breakdown import refund_cash_back
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
        credit_reversed: Decimal | None = None,
        is_reprint: bool = False,
        original_document_number: str = "",
    ) -> list[dict[str, Any]]:
        """
        Generates a REFUND receipt with distinct visual treatment.

        Args:
            sale: The original Sale being refunded, or the refund Sale document.
            refund_amount: Amount refunded (defaults to sale total).
            authorized_by: Username who authorized the refund.
            config_override: Optional config overrides.
            refund_timestamp: Timestamp for the refund (defaults to now).
            credit_reversed: Part of the refund taken off the customer's credit
                instead of handed back (#715). When non-zero the voucher shows
                both parts, so a credit sale isn't paid back in cash too.
            is_reprint: Whether to add DUPLICATE markers.
            original_document_number: Document number of the original sale if known.
        """
        cls._resolve_receipt_lang(config_override)
        commands: list[dict[str, Any]] = []

        # Duplicate marking (top)
        if is_reprint:
            commands.append({"type": "text", "val": cls._rt("duplicate"), "align": "center"})

        line_chars = cls._append_header_block(commands, config_override)

        # REFUND header
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "text", "val": cls._rt("refund_label"), "align": "center"})
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Resolve document and original sale reference
        orig_doc = original_document_number
        if not orig_doc and getattr(sale, "refund_of_sale_id", None):
            try:
                from cbpos.core.database import Database

                with Database().get_session() as s:
                    parent_sale = s.get(Sale, sale.refund_of_sale_id)
                    if parent_sale:
                        orig_doc = parent_sale.document_number or str(parent_sale.id)
            except Exception:
                pass

        doc_num = getattr(sale, "document_number", None) or str(sale.id)
        is_credit_note_doc = bool(
            getattr(sale, "refund_of_sale_id", None)
            or getattr(sale, "payment_method", "") == "REFUND"
            or doc_num.startswith("CN-")
        )

        if is_credit_note_doc:
            commands.append({"type": "text", "val": doc_num, "align": "center"})
            if orig_doc:
                commands.append({"type": "text", "val": f"{cls._rt('original_receipt')}: {orig_doc}", "align": "left"})
        else:
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
            qty_str = cls._format_item_qty(item).lstrip("-")
            unit_price = abs(item.unit_price) if item.unit_price is not None else Decimal("0.00")
            subtotal = abs(item.subtotal) if item.subtotal is not None else Decimal("0.00")
            line = f"{qty_str} x {format_currency(unit_price)} = {format_currency(subtotal)}"
            commands.append({"type": "text", "val": product_name, "align": "left"})
            commands.append({"type": "text", "val": line, "align": "right"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        amount = refund_amount if refund_amount is not None else abs(sale.total_amount)
        commands.append(
            {
                "type": "text",
                "val": cls._rt("refund_total", total_label=cls._rt("total"), amount=format_currency(amount)),
                "align": "right",
            }
        )
        if credit_reversed and credit_reversed > 0:
            given_back = refund_cash_back(Decimal(str(amount)), credit_reversed)
            commands.append(
                {
                    "type": "text",
                    "val": cls._rt("refund_given_back", amount=format_currency(given_back)),
                    "align": "right",
                }
            )
            commands.append(
                {
                    "type": "text",
                    "val": cls._rt("refund_off_credit", amount=format_currency(credit_reversed)),
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

        # Duplicate marking (bottom)
        if is_reprint:
            commands.append({"type": "text", "val": cls._rt("duplicate"), "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands
