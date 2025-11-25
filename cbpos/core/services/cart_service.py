from decimal import Decimal
from typing import List, Dict, Any
from cbpos.core.models import Product


class CartService:
    """
    Service to manage the current sale's shopping cart.
    Holds state in memory.
    """

    def __init__(self):
        self.items: List[Dict[str, Any]] = []

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

        # Add new line
        new_item = {
            "product": product,
            "qty": qty,
            "unit_price": product.price,
            "total": Decimal("0.00"),
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

    def _recalculate_line(self, item: Dict[str, Any]):
        """Recalculate the total for a single line item."""
        # Rounding to 2 decimal places for currency
        item["total"] = (item["qty"] * item["unit_price"]).quantize(Decimal("0.01"))

    def get_totals(self) -> Dict[str, Any]:
        """Return the cart totals."""
        subtotal = sum(item["total"] for item in self.items)
        return {
            "subtotal": subtotal,
            "count": len(self.items),
            "item_count": sum(item["qty"] for item in self.items),
        }
