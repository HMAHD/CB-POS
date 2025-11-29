from decimal import Decimal
from typing import List, Dict, Any, Optional
from cbpos.core.models import Product, Customer
from cbpos.core.services.pricing_service import PricingService


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

    def apply_line_discount(self, index: int, type: str, value: float):
        """Apply discount to a specific line item."""
        if 0 <= index < len(self.items):
            item = self.items[index]
            item["discount_type"] = type
            item["discount_value"] = Decimal(str(value))
            self._recalculate_line(item)

    def apply_cart_discount(self, type: str, value: float):
        """Apply discount to the entire cart."""
        self.cart_discount_type = type
        self.cart_discount_value = Decimal(str(value))
        # No line recalculation needed, just totals

    def override_price(self, index: int, new_price: float, user: Any):
        """
        Override the price of a specific line item.
        Requires permission check (handled by caller or decorator).
        """
        if 0 <= index < len(self.items):
            item = self.items[index]
            item["unit_price"] = Decimal(str(new_price))
            item["is_manual_price"] = True
            # Reset discount if price is manually overridden?
            # Strategy: Keep discount, apply on new price.
            self._recalculate_line(item)

            # TODO: Log to AuditLog (Infrastructure required)
            print(
                f"AUDIT: Price Override by {user.username} - Item {item['product'].name_en} to {new_price}"
            )

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

        item["subtotal"] = gross_line.quantize(Decimal("0.01"))
        item["total"] = net_line.quantize(Decimal("0.01"))

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

    def get_totals(self) -> Dict[str, Any]:
        """Return the cart totals."""
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

        return {
            "subtotal": subtotal.quantize(Decimal("0.01")),
            "cart_discount": cart_discount_amt.quantize(Decimal("0.01")),
            "final_total": final_total.quantize(Decimal("0.01")),
            "count": len(self.items),
            "item_count": sum(item["qty"] for item in self.items),
        }
