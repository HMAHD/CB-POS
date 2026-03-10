import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from cbpos.core.services.config_service import ConfigService
from cbpos.core.models import Sale, SaleItem
from cbpos.i18n import _t, translate_in


from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cbpos.core.models import Customer, CustomerLedgerEntry, Proforma


class ReceiptBuilder:
    """
    Builds a list of command objects for printing or previewing receipts.
    Commands are device-agnostic dictionaries:
    - {'type': 'text', 'val': '...', 'align': 'left|center|right'}
    - {'type': 'image', 'path': '...'}
    - {'type': 'barcode', 'val': '...', 'code': 'CODE39|QR'}
    - {'type': 'feed', 'lines': 1}
    - {'type': 'cut', 'partial': True}
    """

    # Per-build receipt language cache.  Set by build_receipt() and friends
    # so that _rt() doesn't call ConfigService.get() on every invocation.
    _receipt_lang: Optional[str] = None

    @classmethod
    def _rt(cls, key: str, **kwargs) -> str:
        """Shorthand for receipt translation keys.

        Uses the cached ``_receipt_lang`` (set at the start of each build
        method).  Falls back to the current UI language when unset.
        """
        lang = cls._receipt_lang
        if lang:
            return translate_in(lang, f"receipt_strings.{key}", **kwargs)
        return _t(f"receipt_strings.{key}", **kwargs)

    @classmethod
    def _resolve_receipt_lang(cls, config_override: Optional[Dict[str, Any]] = None) -> None:
        """Cache the effective receipt language for the current build call."""
        cls._receipt_lang = cls._get_conf("receipt_language", "", config_override) or None

    @classmethod
    def _get_conf(cls, key: str, default: Any = None, config_override: Optional[Dict[str, Any]] = None) -> Any:
        """Helper to get config value with override support."""
        if config_override and key in config_override:
            return config_override[key]
        val = ConfigService.get(key)
        return val if val is not None else default

    @classmethod
    def _append_branding(cls, commands: List[Dict[str, Any]]) -> None:
        """Append CB POS branding to receipt."""
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": "Powered by CB POS", "align": "center"})
        commands.append({"type": "text", "val": "ceybyte.com", "align": "center"})

    @classmethod
    def _append_cut(cls, commands: List[Dict[str, Any]], config_override: Optional[Dict[str, Any]] = None) -> None:
        """Append configurable feed + cut commands."""
        auto_cut = cls._get_conf("auto_cut_paper", True, config_override)
        feed_lines = cls._get_conf("feed_lines_before_cut", 3, config_override)
        cut_type = cls._get_conf("cut_type", "partial", config_override)

        commands.append({"type": "feed", "lines": feed_lines})
        if auto_cut:
            commands.append({"type": "cut", "partial": cut_type == "partial"})

    @classmethod
    def _append_header_block(
        cls,
        commands: List[Dict[str, Any]],
        config_override: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Append header text, logo, shop info, TIN. Returns line_chars."""
        paper_width = cls._get_conf("paper_width", "80mm", config_override)
        line_chars = 32 if paper_width == "58mm" else 42
        gc = cls._get_conf

        # Custom header text (top — greeting/promo before shop identity)
        header_text = gc("receipt_header", "", config_override)
        if header_text:
            commands.append({"type": "text", "val": header_text, "align": "center"})

        # Logo
        logo_path = gc("receipt_logo_path", "", config_override)
        if logo_path:
            commands.append({"type": "image", "path": logo_path})

        # Shop name (bold, center)
        shop_name = gc("shop_name", "", config_override)
        if shop_name:
            commands.append({"type": "text", "val": shop_name, "align": "center", "bold": True})

        # Shop address + phone on same line if both short, else separate
        shop_address = gc("shop_address", "", config_override)
        if shop_address:
            commands.append({"type": "text", "val": shop_address, "align": "center"})

        shop_phone = gc("shop_phone", "", config_override)
        if shop_phone:
            commands.append({"type": "text", "val": shop_phone, "align": "center"})

        # TIN
        tax_id = gc("company_tax_id", "", config_override)
        if tax_id:
            commands.append({"type": "text", "val": f"{cls._rt('tin')}: {tax_id}", "align": "center"})

        return line_chars

    @classmethod
    def build_receipt(
        cls,
        sale: Sale,
        config_override: Optional[Dict[str, Any]] = None,
        is_reprint: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Generates receipt commands for a given Sale.

        Args:
            sale: The Sale model instance.
            config_override: Optional dictionary to override ConfigService values.
            is_reprint: If True, adds DUPLICATE marking.
        """
        cls._resolve_receipt_lang(config_override)
        commands: List[Dict[str, Any]] = []
        gc = cls._get_conf

        def _sep() -> Dict[str, Any]:
            return {"type": "text", "val": "-" * line_chars, "align": "center"}

        # Duplicate marking (top)
        if is_reprint:
            commands.append({"type": "text", "val": cls._rt("duplicate"), "align": "center"})

        # Header block (header text, logo, shop info, TIN)
        line_chars = cls._append_header_block(commands, config_override)

        # Document title — derive from payment method
        commands.append(_sep())
        doc_title = cls._get_doc_title(sale)
        commands.append({"type": "text", "val": doc_title, "align": "center", "bold": True})
        commands.append(_sep())

        # Invoice number (centered, acts as bill reference — barcode encodes this)
        doc_num = getattr(sale, "document_number", None) or str(sale.id)
        commands.append({"type": "text", "val": doc_num, "align": "center"})

        # Date and time — clean, no labels
        if sale.date:
            commands.append(
                cls._split_row(
                    sale.date.strftime("%Y-%m-%d"),
                    sale.date.strftime("%H:%M"),
                    line_chars,
                )
            )

        cashier_name = ""
        if gc("show_cashier_on_receipt", True, config_override):
            cashier_name = cls._get_current_cashier_name()
        if cashier_name:
            commands.append({"type": "text", "val": f"{cls._rt('cashier')}: {cashier_name}", "align": "left"})

        # Terminal ID
        if gc("show_terminal_on_receipt", False, config_override):
            terminal_id = gc("terminal_id", "", config_override)
            if terminal_id:
                commands.append(
                    {
                        "type": "text",
                        "val": f"{cls._rt('terminal')}: {terminal_id}",
                        "align": "left",
                    }
                )

        # Customer name (shown for credit sales or when customer is linked)
        customer = getattr(sale, "customer", None)
        if customer and hasattr(customer, "name") and customer.name:
            commands.append({"type": "text", "val": f"{cls._rt('customer')}: {customer.name}", "align": "left"})

        # Item column header
        commands.append(_sep())
        commands.append(cls._split_row(cls._rt("sn_description"), cls._rt("amount_label"), line_chars, bold=True))
        commands.append(_sep())

        # Line items with serial numbers
        merge = gc("merge_items", False, config_override)
        display_items = cls._merge_items(sale.items) if merge else sale.items

        for idx, item in enumerate(display_items, 1):
            name = item.product.name_en if hasattr(item, "product") and item.product else item.name
            sn = "{:02d}".format(idx)
            qty = item.qty
            price = item.unit_price
            total = item.subtotal

            # Detect discount by comparing original_price vs unit_price
            orig_price = getattr(item, "original_price", None)
            has_discount = orig_price and orig_price > price

            if has_discount:
                # Show product name with original price struck through
                commands.append({"type": "text", "val": f"{sn} {name}", "align": "left"})
                detail = "   {} x {}".format(qty, format_currency(price))
                commands.append(cls._split_row(detail, format_currency(total), line_chars))
                # Show savings per unit
                saving = orig_price - price
                disc_pct = (saving * Decimal("100") / orig_price).quantize(Decimal("1"))
                commands.append(
                    cls._split_row(
                        "   {}".format(cls._rt("was_price", price=format_currency(orig_price), pct=disc_pct)),
                        "-{}".format(format_currency(saving * qty)),
                        line_chars,
                    )
                )
            else:
                commands.append({"type": "text", "val": f"{sn} {name}", "align": "left"})
                detail = "   {} x {}".format(qty, format_currency(price))
                commands.append(cls._split_row(detail, format_currency(total), line_chars))

        # Items count + totals
        commands.append(_sep())
        item_count = len(display_items)
        total_qty = sum(i.qty for i in display_items)
        commands.append(
            cls._split_row(
                cls._rt("items_count", count=item_count, qty=total_qty),
                "",
                line_chars,
            )
        )

        # Additional (bill-level) discount
        disc_type = getattr(sale, "additional_discount_type", "NONE") or "NONE"
        disc_val = getattr(sale, "additional_discount_value", None)
        if disc_type != "NONE" and disc_val and disc_val > 0:
            if disc_type == "PERCENTAGE":
                items_subtotal = sum(i.subtotal for i in display_items)
                disc_amount = items_subtotal * disc_val / Decimal("100")
                disc_label = cls._rt("discount_pct", pct=disc_val)
                disc_display = "-{}".format(format_currency(disc_amount))
            else:
                disc_label = cls._rt("discount_label")
                disc_display = "-{}".format(format_currency(disc_val))
            commands.append(cls._split_row(disc_label, disc_display, line_chars))

        commands.append(
            cls._split_row(cls._rt("total_amount"), format_currency(sale.total_amount), line_chars, bold=True)
        )

        # Tax — indented under total
        if gc("show_tax_breakdown", False, config_override):
            exempt_amount = getattr(sale, "_exempt_amount", None)
            if exempt_amount and exempt_amount > Decimal("0"):
                taxable_amount = sale.total_amount - exempt_amount
                commands.append(
                    cls._split_row("  {}:".format(cls._rt("taxable")), format_currency(taxable_amount), line_chars)
                )
                commands.append(
                    cls._split_row("  {}:".format(cls._rt("tax_exempt")), format_currency(exempt_amount), line_chars)
                )
            if sale.tax_vat > 0:
                commands.append(
                    cls._split_row("  {}:".format(cls._rt("vat")), format_currency(sale.tax_vat), line_chars)
                )
            if sale.tax_sscl > 0:
                commands.append(
                    cls._split_row("  {}:".format(cls._rt("sscl")), format_currency(sale.tax_sscl), line_chars)
                )
            if sale.net_revenue and sale.net_revenue > 0:
                commands.append(
                    cls._split_row("  {}:".format(cls._rt("net_total")), format_currency(sale.net_revenue), line_chars)
                )

        # Payment block
        if hasattr(sale, "payments") and sale.payments:
            commands.append(_sep())
            for pmt in sale.payments:
                label = cls._rt("paid_label", method=pmt.payment_method.upper())
                commands.append(cls._split_row(label, format_currency(pmt.amount), line_chars))
            total_paid = sum(p.amount for p in sale.payments)
            if total_paid > sale.total_amount:
                change = total_paid - sale.total_amount
                commands.append(cls._split_row(cls._rt("change_label"), format_currency(change), line_chars, bold=True))

        commands.append(_sep())

        # Barcode (encodes invoice number for return scanning)
        show_barcode = gc("show_barcode", True, config_override)
        if show_barcode:
            commands.append({"type": "barcode", "val": doc_num, "code": "CODE39", "align": "center"})

        # Footer text
        footer_text = gc("receipt_footer", "", config_override)
        if footer_text:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": footer_text, "align": "center"})

        # Duplicate marking (bottom)
        if is_reprint:
            commands.append({"type": "text", "val": cls._rt("duplicate"), "align": "center"})

        # Branding + Cut
        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands

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
        gc = cls._get_conf
        if gc("show_tax_breakdown", False, config_override):
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

    @classmethod
    def build_refund_receipt(
        cls,
        sale: Sale,
        refund_amount: Optional[Decimal] = None,
        authorized_by: str = "",
        config_override: Optional[Dict[str, Any]] = None,
        refund_timestamp: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
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
        commands: List[Dict[str, Any]] = []

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
            line = "{} x {} = {}".format(item.qty, format_currency(item.unit_price), format_currency(item.subtotal))
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
        gc = cls._get_conf
        if gc("show_tax_breakdown", False, config_override):
            if sale.tax_vat and sale.tax_vat > 0:
                commands.append(
                    cls._split_row(
                        "  {}".format(cls._rt("vat_refund", vat=cls._rt("vat"))),
                        "-{}".format(format_currency(sale.tax_vat)),
                        line_chars,
                    )
                )
            if sale.tax_sscl and sale.tax_sscl > 0:
                commands.append(
                    cls._split_row(
                        "  {}".format(cls._rt("sscl_refund", sscl=cls._rt("sscl"))),
                        "-{}".format(format_currency(sale.tax_sscl)),
                        line_chars,
                    )
                )

        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})
        commands.append({"type": "text", "val": cls._rt("refund_label"), "align": "center"})
        commands.append({"type": "text", "val": "=" * line_chars, "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands

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

        footer_text = gc("receipt_footer", "", config_override)
        if footer_text:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": footer_text, "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands

    @classmethod
    def build_customer_statement(
        cls,
        customer: "Customer",
        entries: List["CustomerLedgerEntry"],
        period_from: datetime,
        period_to: datetime,
        config_override: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generates receipt commands for a customer credit statement.

        Args:
            customer: The Customer model instance.
            entries: List of CustomerLedgerEntry objects.
            period_from: Statement start date.
            period_to: Statement end date.
            config_override: Optional dictionary to override ConfigService values.
        """
        cls._resolve_receipt_lang(config_override)
        commands: List[Dict[str, Any]] = []
        gc = cls._get_conf

        line_chars = cls._append_header_block(commands, config_override)

        # Title
        commands.append({"type": "text", "val": cls._rt("statement"), "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Customer Info
        commands.append({"type": "text", "val": f"{cls._rt('customer')}: {customer.name}", "align": "left"})
        if customer.phone:
            commands.append({"type": "text", "val": f"{cls._rt('phone')}: {customer.phone}", "align": "left"})

        # Period
        from_str = period_from.strftime("%Y-%m-%d")
        to_str = period_to.strftime("%Y-%m-%d")
        commands.append({"type": "text", "val": f"{cls._rt('period')}: {from_str} to {to_str}", "align": "left"})
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Opening Balance
        if entries:
            opening = entries[0].balance_after - entries[0].amount
        else:
            opening = customer.current_debt

        commands.append(
            {"type": "text", "val": f"{cls._rt('opening_balance')}: {format_currency(opening)}", "align": "left"}
        )
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Entries
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        for entry in entries:
            date_str = entry.timestamp.strftime("%m/%d") if entry.timestamp else ""
            doc = entry.reference_doc or entry.note or entry.entry_type

            if entry.amount > 0:
                line = f"{date_str} {doc:<20} +{entry.amount:.2f}"  # noqa: E231
                total_debit += entry.amount
            else:
                line = f"{date_str} {doc:<20} {entry.amount:.2f}"  # noqa: E231
                total_credit += abs(entry.amount)

            commands.append({"type": "text", "val": line, "align": "left"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Totals
        commands.append(
            {"type": "text", "val": f"{cls._rt('total_sales')}: {format_currency(total_debit)}", "align": "right"}
        )
        commands.append(
            {"type": "text", "val": f"{cls._rt('total_payments')}: {format_currency(total_credit)}", "align": "right"}
        )

        # Closing Balance
        closing = entries[-1].balance_after if entries else customer.current_debt
        commands.append({"type": "feed", "lines": 1})
        commands.append(
            {"type": "text", "val": f"{cls._rt('closing_balance')}: {format_currency(closing)}", "align": "right"}
        )

        # Footer
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": cls._rt("thank_you"), "align": "center"})

        footer_text = gc("receipt_footer", "", config_override)
        if footer_text:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": footer_text, "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands

    @classmethod
    def _get_doc_title(cls, sale: Sale) -> str:
        """Derive document title from payment methods."""
        payments = getattr(sale, "payments", []) or []
        methods = {p.payment_method.strip().upper() for p in payments}

        if "CREDIT" in methods:
            return cls._rt("doc_title_credit")
        elif len(methods) > 1:
            return cls._rt("doc_title_receipt")
        elif methods == {"CARD"}:
            return cls._rt("doc_title_card")

        # Default: cash-only or empty payments
        return cls._rt("doc_title_cash")

    @staticmethod
    def _two_col(left: str, right: str, width: int) -> str:
        """Format two strings into a single line padded to *width* characters."""
        gap = width - len(left) - len(right)
        return "{}{}{}".format(left, " " * max(gap, 1), right)

    @classmethod
    def _split_row(
        cls,
        left: str,
        right: str,
        width: int,
        bold: bool = False,
    ) -> Dict[str, Any]:
        """Build a two-column text command with both printer val and preview split."""
        return {
            "type": "text",
            "val": cls._two_col(left, right, width),
            "align": "left",
            "bold": bold,
            "left_val": left,
            "right_val": right,
        }

    @staticmethod
    def _get_current_cashier_name() -> str:
        """Get current logged-in user's username, or empty string."""
        try:
            from cbpos.core.services.auth_service import AuthService

            user = AuthService.get_current_user()
            return user.username if user else ""
        except Exception as e:
            logger.debug("Could not get current cashier name: %s", e)
            return ""

    @staticmethod
    def _merge_items(items: List[SaleItem]) -> List[Any]:
        """
        Merges SaleItems with the same product_id.
        Returns a list of objects with product, qty, unit_price, subtotal attributes.
        """
        merged = {}
        for item in items:
            pid = item.product_id if item.product_id is not None else id(item.product)
            if pid in merged:
                merged[pid].qty += item.qty
                merged[pid].subtotal += item.subtotal
            else:
                merged[pid] = ItemDisplay(
                    product=item.product,
                    qty=item.qty,
                    unit_price=item.unit_price,
                    subtotal=item.subtotal,
                    name=item.product.name_en,
                    original_price=getattr(item, "original_price", None),
                )
        return list(merged.values())


class ItemDisplay:
    """Helper class for merged items display"""

    def __init__(
        self,
        product: Any,
        qty: Any,
        unit_price: Any,
        subtotal: Any,
        name: str,
        original_price: Any = None,
    ) -> None:
        self.product = product
        self.qty = qty
        self.unit_price = unit_price
        self.subtotal = subtotal
        self.name = name
        self.original_price = original_price
