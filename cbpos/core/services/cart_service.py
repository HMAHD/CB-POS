import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select

from cbpos.core.models import Customer, Product
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.logging_service import LoggingService
from cbpos.core.services.pricing_service import PricingService
from cbpos.core.utils.money import round_money
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class CartService:
    """
    Service to manage the current sale's shopping cart.
    Holds state in memory.
    """

    def __init__(self):
        """Start an empty cart with no customer and no cart-level discount."""
        self.items: list[dict[str, Any]] = []
        self._customer: Customer | None = None
        self.cart_discount_type = "NONE"
        self.cart_discount_value = Decimal("0.00")
        self.loyalty_points_redeemed = 0

    def set_customer(self, customer: Customer | None):
        """Set the customer for the current cart and recalculate prices."""
        self._customer = customer
        if customer is None:
            self.loyalty_points_redeemed = 0
        self._recalculate_all_prices()

    def get_customer(self) -> Customer | None:
        """Return the customer currently attached to the cart, if any."""
        return self._customer

    def add_item(self, product: Product, qty: Decimal = Decimal("1.000")):
        """
        Add a product to the cart.
        If product exists, update quantity.
        """
        if qty <= Decimal("0"):
            raise ValueError("Quantity must be positive")

        # Check if product already in cart
        for idx, item in enumerate(self.items):
            if item["product"].id == product.id:
                self.update_quantity(idx, item["qty"] + qty)
                return

        # Calculate price using Pricing Engine
        pricing = PricingService.calculate_price(product, self._customer)

        flags = self._resolve_effective_flags(product)
        new_item = {
            "product": product,
            "qty": qty,
            "unit_price": pricing["final_price"],
            "original_price": pricing["original_price"],
            "applied_rule": pricing["applied_rule"],
            "discount_type": "NONE",
            "discount_value": Decimal("0.00"),
            "is_manual_price": False,
            "total": Decimal("0.00"),
            "subtotal": Decimal("0.00"),  # Gross line total
            # Captured now, not at totals time: by then nothing guarantees
            # the detached product can still reach its category (#701, #797).
            "tax_exempt": flags["vat_exempt"],
            "vat_exempt": flags["vat_exempt"],
            "sscl_exempt": flags["sscl_exempt"],
            "note": None,
            "override_approved_by": None,
        }
        self._recalculate_line(new_item)
        self.items.append(new_item)

    def update_quantity(self, index: int, qty: Decimal) -> str | None:
        """Change a line's quantity, keeping any existing discount applied.

        Quantity reduction is permission-gated (SALES_VOID) and audited in SalesView (#893).
        """
        if not (0 <= index < len(self.items)):
            return None

        item = self.items[index]
        old_qty = item["qty"]
        new_qty = Decimal(str(qty))
        if new_qty <= Decimal("0"):
            raise ValueError("Quantity must be positive")

        item["qty"] = new_qty
        notice = None

        if item.get("discount_type") == "FIXED" and old_qty > Decimal("0"):
            old_discount = item["discount_value"]
            scaled_discount = round_money(old_discount * new_qty / old_qty)
            gross_line = new_qty * item["unit_price"]

            try:
                self._validate_discount_cap("FIXED", scaled_discount, reference_amount=gross_line)
                item["discount_value"] = scaled_discount
            except ValueError:
                item["discount_type"] = "NONE"
                item["discount_value"] = Decimal("0.00")
                product_name = getattr(item.get("product"), "name_en", "")
                notice = _t("cart.discount_removed_qty", name=product_name)

        self._recalculate_line(item)
        return notice

    def remove_item(self, index: int):
        """Remove an item by its index in the list."""
        if 0 <= index < len(self.items):
            self.items.pop(index)

    def clear(self):
        """Empty the cart."""
        self.items = []
        self._customer = None
        self.cart_discount_type = "NONE"
        self.cart_discount_value = Decimal("0.00")
        self.loyalty_points_redeemed = 0

    def set_loyalty_redemption(self, points: int):
        """Set loyalty points to redeem as a rupee discount on checkout (ADR-0002)."""
        self.loyalty_points_redeemed = max(0, int(points or 0))

    def apply_line_discount(self, index: int, type: str, value: Decimal, user: Any = None):
        """Apply discount to a specific line item.

        `user` is the manager/cashier who authorized this discount
        (from check_permission_with_override) -- when given, the override
        is written to AuditLog the same way every other permission-gated
        action in the app already is (refund, void, permission change).
        """
        if 0 <= index < len(self.items):
            item = self.items[index]
            gross_line = item["qty"] * item["unit_price"]
            self._validate_discount_cap(type, value, reference_amount=gross_line)
            item["discount_type"] = type
            item["discount_value"] = Decimal(str(value))
            self._recalculate_line(item)

            if user is not None:
                LoggingService.log_action(
                    user_id=user.id,
                    action="LINE_DISCOUNT",
                    event_type="TRANSACTION",
                    details=f"Applied {type} discount ({value}) to '{item['product'].name_en}'",
                )

    def apply_cart_discount(self, type: str, value: Decimal, user: Any = None):
        """Apply discount to the entire cart."""
        if user is None:
            self._validate_discount_cap(type, value)
        self.cart_discount_type = type
        self.cart_discount_value = Decimal(str(value))
        if user is not None:
            LoggingService.log_action(
                user_id=user.id,
                action="BILL_DISCOUNT",
                event_type="TRANSACTION",
                details=f"Applied bill discount {type} {value}",
            )

    def remove_cart_discount(self):
        """Remove any bill-level discount from the cart."""
        self.cart_discount_type = "NONE"
        self.cart_discount_value = Decimal("0.00")

    def override_price(self, index: int, new_price: Decimal, user: Any) -> bool:
        """
        Override the price of a specific line item.

        Requires permission check (handled by caller or decorator). Also
        blocked outright if the product has `price_change_allowed=False`
        (e.g. a regulated/fixed-price item) -- that's a per-product lock
        beneath the permission check, not something an authorized user can
        override (#490).

        Returns:
            True if the price was changed, False if blocked because this
            product doesn't allow price changes.
        """
        if new_price < Decimal("0"):
            raise ValueError("Price cannot be negative")

        if 0 <= index < len(self.items):
            item = self.items[index]

            if not item["product"].price_change_allowed:
                return False

            original_price = item["unit_price"]
            item["unit_price"] = Decimal(str(new_price))
            item["is_manual_price"] = True
            item["override_approved_by"] = getattr(user, "id", user) if user else None
            # Reset discount if price is manually overridden?
            # Strategy: Keep discount, apply on new price.
            self._recalculate_line(item)

            LoggingService.log_action(
                user_id=user.id,
                action="PRICE_OVERRIDE",
                event_type="TRANSACTION",
                details=(f"Overrode price of '{item['product'].name_en}' from {original_price} to {new_price}"),
            )
            return True
        return False

    def restore_line_override(self, index: int, new_price: Decimal, approved_by: Any = None) -> bool:
        """Restore a previously approved price override without re-prompting or logging as a new override."""
        if 0 <= index < len(self.items):
            item = self.items[index]
            item["unit_price"] = Decimal(str(new_price))
            item["is_manual_price"] = True
            item["override_approved_by"] = approved_by
            self._recalculate_line(item)
            return True
        return False

    def restore_line_discount(self, index: int, type: str, value: Decimal):
        """Restore an already approved line discount without re-validating the cap."""
        if 0 <= index < len(self.items):
            item = self.items[index]
            item["discount_type"] = type
            item["discount_value"] = Decimal(str(value))
            self._recalculate_line(item)

    def restore_cart_discount(self, type: str, value: Decimal):
        """Restore an already approved cart discount without re-validating the cap."""
        self.cart_discount_type = type
        self.cart_discount_value = Decimal(str(value))

    def set_line_note(self, index: int, note: str | None):
        """Set or clear a note for a specific line item."""
        if 0 <= index < len(self.items):
            self.items[index]["note"] = (note or "").strip() or None

    def _validate_discount_cap(
        self, discount_type: str, discount_value: Decimal, reference_amount: Decimal = None
    ) -> None:
        """Validate discount does not exceed the configured max_discount_percent.

        A FIXED discount is checked against the same cap by converting it to
        its equivalent percentage of reference_amount -- otherwise the cap
        only ever gated PERCENTAGE discounts, letting anyone with discount
        permission zero out a line via a large enough fixed amount.
        """
        try:
            from cbpos.core.services.config_service import ConfigService

            max_pct = Decimal(str(ConfigService.get("max_discount_percent") or 0))
        except Exception as e:
            logger.debug("Could not read 'max_discount_percent' from config, skipping validation. Error: %s", e)
            return  # Config not available (e.g. test environment)

        if max_pct <= 0:
            return  # No cap configured (0 = unlimited)

        if discount_type == "PERCENTAGE" and Decimal(str(discount_value)) > max_pct:
            raise ValueError(f"Discount cannot exceed {max_pct}%. Manager override required.")

        if discount_type == "FIXED" and reference_amount:
            reference_amount = Decimal(str(reference_amount))
            if reference_amount > 0:
                effective_pct = (Decimal(str(discount_value)) / reference_amount) * Decimal("100")
                if effective_pct > max_pct:
                    raise ValueError(f"Discount cannot exceed {max_pct}%. Manager override required.")

    def _recalculate_line(self, item: dict[str, Any]):
        """Recalculate the total for a single line item."""
        # 1. Gross Line Total
        gross_line = item["qty"] * item["unit_price"]

        # 2. Line Discount
        discount_amount = Decimal("0.00")
        if item["discount_type"] == "PERCENTAGE":
            discount_amount = gross_line * (item["discount_value"] / Decimal("100"))
        elif item["discount_type"] == "FIXED":
            discount_amount = item["discount_value"]

        # Cap discount at gross line value (no negative totals)
        discount_amount = min(discount_amount, gross_line)

        # 3. Net Line Total
        net_line = gross_line - discount_amount

        item["subtotal"] = round_money(gross_line)
        item["total"] = round_money(net_line)

    def _recalculate_all_prices(self):
        """Recalculate prices for all items (e.g., when customer changes)."""
        for item in self.items:
            # Only update price if not manually overridden
            if not item["is_manual_price"]:
                product = item["product"]
                pricing = PricingService.calculate_price(product, self._customer)
                item["unit_price"] = pricing["final_price"]
                item["original_price"] = pricing["original_price"]
                item["applied_rule"] = pricing["applied_rule"]

            self._recalculate_line(item)

    def _is_item_tax_exempt(self, item: dict[str, Any]) -> bool:
        """Check if a cart item is tax exempt via its category.

        Uses the flag captured when the line was added; a line built some
        other way (e.g. by hand in a test) is resolved once and cached.
        """
        if "tax_exempt" not in item:
            item["tax_exempt"] = self._resolve_tax_exempt(item.get("product"))
        return item["tax_exempt"]

    @staticmethod
    def _resolve_effective_flags(product: Any) -> dict[str, bool]:
        """Return effective exemption flags (vat_exempt, sscl_exempt) for product's category (#701, #797)."""
        from cbpos.core.database import Database
        from cbpos.core.services.category_service import CategoryService

        if product is None:
            return {"vat_exempt": False, "sscl_exempt": False}

        category_id = None
        state = sa_inspect(product, raiseerr=False)
        if state is None:
            category = getattr(product, "category", None)
            if category is not None:
                cat_id = getattr(category, "id", None)
                if isinstance(cat_id, int):
                    category_id = cat_id
                elif hasattr(category, "tax_exempt") and isinstance(category.tax_exempt, bool):
                    return {
                        "vat_exempt": bool(category.tax_exempt),
                        "sscl_exempt": bool(getattr(category, "sscl_exempt", False)),
                    }
            if category_id is None:
                p_cat_id = getattr(product, "category_id", None)
                if isinstance(p_cat_id, int):
                    category_id = p_cat_id
        else:
            category_id = state.dict.get("category_id")
            if category_id is None and "category" not in state.unloaded:
                cat = state.dict.get("category")
                if cat is not None:
                    category_id = getattr(cat, "id", None)
            if category_id is None and state.identity:
                with Database().get_session() as s:
                    category_id = s.scalar(select(Product.category_id).where(Product.id == state.identity[0]))

        if not isinstance(category_id, int):
            return {"vat_exempt": False, "sscl_exempt": False}

        return CategoryService.effective_flags(category_id)

    def get_totals(self, loyalty_points: int | None = None, has_customer: bool | None = None) -> dict[str, Any]:
        """Return the cart totals."""
        from cbpos.core.services.tax_service import TaxService

        # 1. Sum Net Lines
        subtotal = sum((item["total"] for item in self.items), Decimal("0.00"))

        # 2. Apply Cart Discount
        cart_discount_amt = Decimal("0.00")
        if self.cart_discount_type == "PERCENTAGE":
            cart_discount_amt = subtotal * (self.cart_discount_value / Decimal("100"))
        elif self.cart_discount_type == "FIXED":
            cart_discount_amt = self.cart_discount_value

        # Cap discount
        cart_discount_amt = min(cart_discount_amt, subtotal)
        after_cart_discount = subtotal - cart_discount_amt

        # 2b. Apply Loyalty Redemption Discount (ADR-0002)
        # Loyalty redemption only applies when a customer is attached
        customer_present = (self._customer is not None) if has_customer is None else has_customer
        points_to_redeem = self.loyalty_points_redeemed if loyalty_points is None else max(0, int(loyalty_points or 0))
        loyalty_discount_amt = Decimal("0.00")
        if customer_present and points_to_redeem > 0:
            from cbpos.core.services.loyalty_service import LoyaltyService

            redeem_val = LoyaltyService.calculate_redeem_value(points_to_redeem)
            loyalty_discount_amt = min(redeem_val, after_cart_discount)
        else:
            points_to_redeem = 0

        final_total = after_cart_discount - loyalty_discount_amt

        # 3. Build tax lines with per-line exemptions and distributed discounts (#797, #831)
        from cbpos.core.services.tax_service import TaxLine

        tax_exemptions_enabled = bool(ConfigService.get("item_tax_exemptions"))
        total_discount_amt = cart_discount_amt + loyalty_discount_amt
        raw_amounts = [item["total"] for item in self.items]
        line_discounted_amounts = TaxService.distribute_bill_discount(raw_amounts, total_discount_amt)

        tax_lines = [
            TaxLine(
                amount=amt,
                vat_exempt=bool(item.get("vat_exempt", item.get("tax_exempt", False)))
                if tax_exemptions_enabled
                else False,
                sscl_exempt=bool(item.get("sscl_exempt", False)) if tax_exemptions_enabled else False,
            )
            for item, amt in zip(self.items, line_discounted_amounts, strict=True)
        ]

        # Calculate tax breakdown from the final (post-discount) amount
        tax_info = TaxService.calculate_taxes(
            total_mrp=round_money(final_total),
            lines=tax_lines,
        )

        vat = tax_info.get("vat", Decimal("0.00"))
        sscl = tax_info.get("sscl", Decimal("0.00"))

        return {
            "subtotal": round_money(subtotal),
            "cart_discount": round_money(cart_discount_amt),
            "cart_discount_type": self.cart_discount_type,
            "cart_discount_value": self.cart_discount_value,
            "loyalty_discount": round_money(loyalty_discount_amt),
            "loyalty_points_redeemed": points_to_redeem,
            "final_total": round_money(final_total),
            "taxable_amount": tax_info.get("taxable_amount", Decimal("0.00")),
            "tax_vat": vat,
            "tax_sscl": sscl,
            "tax": vat + sscl,
            "net_revenue": tax_info.get("net", Decimal("0.00")),
            "exempt_amount": tax_info.get("exempt_amount", Decimal("0.00")),
            "sscl_base": tax_info.get("sscl_base", Decimal("0.00")),
            "count": len(self.items),
            "item_count": sum(item["qty"] for item in self.items),
        }
