"""Sales receipt builder — generates receipt commands for completed sales."""

from decimal import Decimal
from typing import Any

from cbpos.core.models import Sale, SaleItem
from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.utils.formatters import format_currency, format_quantity, quantity_decimals


class ItemDisplay:
    """Helper class for merged items display."""

    def __init__(
        self,
        product: Any,
        qty: Any,
        unit_price: Any,
        subtotal: Any,
        name: str,
        original_price: Any = None,
    ) -> None:
        """Store the fields needed to render one (possibly merged) receipt line."""
        self.product = product
        self.qty = qty
        self.unit_price = unit_price
        self.subtotal = subtotal
        self.name = name
        self.original_price = original_price


class SalesReceiptBuilder(BaseReceiptBuilder):
    """Builds receipt commands for completed sales."""

    @classmethod
    def build_receipt(
        cls,
        sale: Sale,
        config_override: dict[str, Any] | None = None,
        is_reprint: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Generates receipt commands for a given Sale.

        Args:
            sale: The Sale model instance.
            config_override: Optional dictionary to override ConfigService values.
            is_reprint: If True, adds DUPLICATE marking.
        """
        cls._resolve_receipt_lang(config_override)
        commands: list[dict[str, Any]] = []
        gc = cls._get_conf

        def _sep() -> dict[str, Any]:
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
            cashier_name = cls._get_sale_cashier_name(sale)
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
            sn = f"{idx:02d}"
            qty = item.qty
            qty_text = cls._format_item_qty(item)
            price = item.unit_price
            total = item.subtotal

            # Detect discount by comparing original_price vs unit_price
            orig_price = getattr(item, "original_price", None)
            has_discount = orig_price and orig_price > price

            if has_discount:
                # Show product name with original price struck through
                commands.append({"type": "text", "val": f"{sn} {name}", "align": "left"})
                detail = f"   {qty_text} x {format_currency(price)}"
                commands.append(cls._split_row(detail, format_currency(total), line_chars))
                # Show savings per unit
                saving = orig_price - price
                disc_pct = (saving * Decimal("100") / orig_price).quantize(Decimal("1"))
                commands.append(
                    cls._split_row(
                        "   {}".format(cls._rt("was_price", price=format_currency(orig_price), pct=disc_pct)),
                        f"-{format_currency(saving * qty)}",
                        line_chars,
                    )
                )
            else:
                commands.append({"type": "text", "val": f"{sn} {name}", "align": "left"})
                detail = f"   {qty_text} x {format_currency(price)}"
                commands.append(cls._split_row(detail, format_currency(total), line_chars))

        # Items count + totals
        commands.append(_sep())
        item_count = len(display_items)
        total_qty = sum(i.qty for i in display_items)
        total_decimals = max((cls._item_qty_decimals(i) for i in display_items), default=0)
        commands.append(
            cls._split_row(
                cls._rt("items_count", count=item_count, qty=format_quantity(total_qty, total_decimals)),
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
                disc_display = f"-{format_currency(disc_amount)}"
            else:
                disc_label = cls._rt("discount_label")
                disc_display = f"-{format_currency(disc_val)}"
            commands.append(cls._split_row(disc_label, disc_display, line_chars))

        commands.append(
            cls._split_row(cls._rt("total_amount"), format_currency(sale.total_amount), line_chars, bold=True)
        )

        # Tax — indented under total (skip when VAT off, unless sale has historical tax)
        from cbpos.core.services.tax_service import TaxService

        has_stored_tax = (sale.tax_vat and sale.tax_vat > 0) or (sale.tax_sscl and sale.tax_sscl > 0)
        if gc("show_tax_breakdown", False, config_override) and (TaxService.is_vat_active() or has_stored_tax):
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

        # QR code (shop-configured link -- WhatsApp, website, digital receipt, etc.)
        show_qr = gc("show_qr_on_receipt", False, config_override)
        qr_content = gc("receipt_qr_content", "", config_override)
        if show_qr and qr_content:
            commands.append({"type": "barcode", "val": qr_content, "code": "QR", "align": "center"})

        # Footer text
        cls._append_footer_text(commands, line_chars, config_override)

        # Duplicate marking (bottom)
        if is_reprint:
            commands.append({"type": "text", "val": cls._rt("duplicate"), "align": "center"})

        # Branding + Cut
        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands

    @staticmethod
    def _item_qty_decimals(item: Any) -> int:
        """Decimal places for *item*'s quantity: its unit's, or 0 when it has no unit.

        0 (not the 3-decimal default for an unknown unit) so a plain ``2``
        stays ``2``; ``format_quantity`` still widens to 3 decimals when the
        value is fractional, so nothing is hidden.
        """
        product = getattr(item, "product", None)
        unit = getattr(product, "unit", None) if product is not None else None
        return quantity_decimals(unit) if unit is not None else 0

    @classmethod
    def _format_item_qty(cls, item: Any) -> str:
        """Quantity as printed on the receipt, the same for a fresh sale and a reloaded one (#681).

        A sale reloaded from the database carries ``2.000`` (the column's
        scale) where the cart had ``2``; formatting by unit makes the
        original print and every reprint agree.
        """
        return format_quantity(item.qty, cls._item_qty_decimals(item))

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
    def _merge_items(items: list[SaleItem]) -> list[Any]:
        """
        Merges SaleItems with the same product_id.
        Returns a list of objects with product, qty, unit_price, subtotal attributes.
        """
        merged: dict[Any, ItemDisplay] = {}
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
