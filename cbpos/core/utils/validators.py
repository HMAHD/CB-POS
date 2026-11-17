"""Validation helpers for CB POS."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str | None) -> bool:
    """Return True if email matches a valid email address format."""
    if not email:
        return False
    return bool(_RE_EMAIL.match(email.strip()))


class ProductValidator:
    """Validates product fields for pricing, cost, stock, and names."""

    @staticmethod
    def validate_price(price: Any) -> str | None:
        """Return error message if price is invalid or <= 0, else None."""
        if price is None:
            return "Selling price is required."
        try:
            val = Decimal(str(price))
            if val <= 0:
                return "Selling price must be greater than 0."
        except (InvalidOperation, ValueError, TypeError):
            return "Invalid selling price."
        return None

    @staticmethod
    def validate_cost(cost: Any) -> str | None:
        """Return error message if cost is invalid or < 0, else None."""
        if cost is None:
            return None
        try:
            val = Decimal(str(cost))
            if val < 0:
                return "Cost cannot be negative."
        except (InvalidOperation, ValueError, TypeError):
            return "Invalid cost."
        return None

    @staticmethod
    def validate_stock(stock: Any, allow_negative_stock: bool | None = None) -> str | None:
        """Return error message if stock quantity is invalid or negative (when disallowed), else None."""
        if stock is None:
            return None
        if allow_negative_stock is None:
            try:
                from cbpos.core.services.config_service import ConfigService

                allow_negative_stock = bool(ConfigService.get("allow_negative_stock"))
            except Exception:
                allow_negative_stock = False

        try:
            val = Decimal(str(stock))
            if not allow_negative_stock and val < 0:
                return "Stock quantity cannot be negative."
        except (InvalidOperation, ValueError, TypeError):
            return "Invalid stock quantity."
        return None

    @classmethod
    def validate_product_data(
        cls,
        data: dict[str, Any],
        allow_negative_stock: bool | None = None,
    ) -> list[str]:
        """Validate product data dictionary and return list of error messages (empty if valid)."""
        errors = []
        name_en = data.get("name_en")
        if not name_en or not str(name_en).strip():
            errors.append("Product name is required.")

        price_err = cls.validate_price(data.get("price"))
        if price_err:
            errors.append(price_err)

        cost_err = cls.validate_cost(data.get("cost"))
        if cost_err:
            errors.append(cost_err)

        stock_err = cls.validate_stock(data.get("stock_qty"), allow_negative_stock=allow_negative_stock)
        if stock_err:
            errors.append(stock_err)

        return errors


def validate_imei_luhn(serial: str | None) -> bool:
    """Validate 15-digit IMEI checksum using the Luhn algorithm.

    Returns True if valid or if not a 15-digit numeric string (bypassing
    advisory warnings for non-IMEI serials). Returns False only when a
    15-digit numeric IMEI fails its Luhn checksum.
    """
    if not serial:
        return True
    s = str(serial).strip()
    if len(s) != 15 or not s.isdigit():
        return True

    digits = [int(c) for c in s]
    total = 0
    for idx, d in enumerate(digits):
        # Odd indices (1, 3, 5, 7, 9, 11, 13) are doubled
        if idx % 2 == 1:
            doubled = d * 2
            total += (doubled // 10) + (doubled % 10)
        else:
            total += d
    return total % 10 == 0
