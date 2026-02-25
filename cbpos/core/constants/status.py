"""
Constants for document status, shift status, and numeric precision used across the application.
Centralizes magic strings and values to prevent typos and enable IDE auto-complete.
"""

from decimal import Decimal


class DocumentStatus:
    COMPLETED = "COMPLETED"
    VOID = "VOID"
    DRAFT = "DRAFT"
    SUSPENDED = "SUSPENDED"


class ShiftStatus:
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class MovementType:
    SALE = "SALE"
    PURCHASE = "PURCHASE"
    ADJUSTMENT = "ADJUSTMENT"
    RETURN = "RETURN"
    VOID = "VOID"


class PaymentMethodType:
    CASH = "Cash"
    CARD = "Card"
    CREDIT = "Credit"
    REFUND = "REFUND"


class Precision:
    """Standard quantization constants for money and quantities."""

    MONEY = Decimal("0.01")  # 2 decimal places for currency
    QUANTITY = Decimal("0.001")  # 3 decimal places for weights/quantities
