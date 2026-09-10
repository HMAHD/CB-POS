import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional
from cbpos.core.models import Product, Customer
from cbpos.core.constants.status import Precision
from cbpos.core.services.pricing_service import PricingService

logger = logging.getLogger(__name__)


class CartService:
    """
    Service to manage the current sale's shopping cart.
    Holds state in memory.
    """

    def __init__(self):
        self.items: List[Dict[str, Any]] = []
        self._customer: Optional[Customer] = None
        self.cart_discount_type = "NONE"
        self.cart_discount_value = Decimal("0.00")

    def set_customer(self, customer: Optional[Customer]):
        """
        Set the customer for the current cart and recalculate prices.
        """
        self._customer = customer
        self._recalculate_all_prices()

    def get_customer(self) -> Optional[Customer]:
        return self._customer

    def add_item(self, product: Product, qty: Decimal = Decimal("1.000")):
        """
        Add a product to the cart.
        If product exists, update quantity.
        """
        if qty <= Decimal("0"):
            raise ValueError("Quantity must be positive")

        # Check if product already in cart
        for item in self.items:
            if item["product"].id == product.id:
                item["qty"] += qty
                self._recalculate_line(item)
                return

        # Calculate price using Pricing Engine
        pricing = PricingService.calculate_price(product, self._customer)

        # Add new line
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
        }
        self._recalculate_line(new_item)
        self.items.append(new_item)

    def update_quantity(self, index: int, qty: Decimal):
        """Change a line's quantity, keeping any existing discount applied.

        Setting item["qty"]/item["total"] directly (as the UI used to)
        skipped _recalculate_line(), so a discount already on the line
        stopped being reflected in the charged total the moment the
        quantity changed, even though the Disc column kept displaying it.
        """
        if 0 <= index < len(self.items):
            item = self.items[index]
            item["qty"] = Decimal(str(qty))
            self._recalculate_line(item)

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

    def apply_line_discount(self, index: int, type: str, value: Decimal):
        """Apply discount to a specific line item."""
        if 0 <= index < len(self.items):
            item = self.items[index]
            gross_line = item["qty"] * item["unit_price"]
            self._validate_discount_cap(type, value, reference_amount=gross_line)
            item["discount_type"] = type
            item["discount_value"] = Decimal(str(value))
            self._recalculate_line(item)

    def apply_cart_discount(self, type: str, value: Decimal):
        """Apply discount to the entire cart."""
        self._validate_discount_cap(type, value)
        self.cart_discount_type = type
        self.cart_discount_value = Decimal(str(value))
        # No line recalculation needed, just totals

    def override_price(self, index: int, new_price: Decimal, user: Any):
        """
        Override the price of a specific line item.
        Requires permission check (handled by caller or decorator).
        """
        if new_price < Decimal("0"):
            raise ValueError("Price cannot be negative")

        if 0 <= index < len(self.items):
            item = self.items[index]
            item["unit_price"] = Decimal(str(new_price))
            item["is_manual_price"] = True
            # Reset discount if price is manually overridden?
            # Strategy: Keep discount, apply on new price.
            self._recalculate_line(item)

            logger.info("Price override by %s - Item %s to %s", user.username, item["product"].name_en, new_price)

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

    def _recalculate_line(self, item: Dict[str, Any]):
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

        item["subtotal"] = gross_line.quantize(Precision.MONEY)
        item["total"] = net_line.quantize(Precision.MONEY)

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

    def _is_item_tax_exempt(self, item: Dict[str, Any]) -> bool:
        """Check if a cart item is tax exempt via its category."""
        try:
            product = item.get("product")
            if product and hasattr(product, "category") and product.category:
                return bool(getattr(product.category, "tax_exempt", False))
        except Exception:
            # Guard against DetachedInstanceError if category wasn't eager-loaded
            pass
        return False

    def get_totals(self) -> Dict[str, Any]:
        """Return the cart totals."""
        from cbpos.core.services.tax_service import TaxService
        from cbpos.core.services.config_service import ConfigService

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

        final_total = subtotal - cart_discount_amt

        # 3. Split into taxable vs exempt amounts when item-level exemptions enabled
        taxable_amount = None
        if ConfigService.get("item_tax_exemptions") and subtotal > Decimal("0"):
            taxable_sub = Decimal("0.00")
            exempt_sub = Decimal("0.00")
            for item in self.items:
                if self._is_item_tax_exempt(item):
                    exempt_sub += item["total"]
                else:
                    taxable_sub += item["total"]

            # Distribute cart discount proportionally
            if cart_discount_amt > Decimal("0") and subtotal > Decimal("0"):
                discount_ratio = cart_discount_amt / subtotal
                taxable_discount = (taxable_sub * discount_ratio).quantize(Precision.MONEY)
                taxable_amount = (taxable_sub - taxable_discount).quantize(Precision.MONEY)
            else:
                taxable_amount = taxable_sub.quantize(Precision.MONEY)

        # Calculate tax breakdown from the final (post-discount) amount
        tax_info = TaxService.calculate_taxes(
            final_total.quantize(Precision.MONEY),
            taxable_amount=taxable_amount,
        )

        return {
            "subtotal": subtotal.quantize(Precision.MONEY),
            "cart_discount": cart_discount_amt.quantize(Precision.MONEY),
            "final_total": final_total.quantize(Precision.MONEY),
            "tax_vat": tax_info["vat"],
            "tax_sscl": tax_info["sscl"],
            "tax": tax_info["vat"] + tax_info["sscl"],
            "net_revenue": tax_info["net"],
            "exempt_amount": tax_info.get("exempt_amount", Decimal("0.00")),
            "count": len(self.items),
            "item_count": sum(item["qty"] for item in self.items),
        }
