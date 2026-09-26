"""
Constants for document status, shift status, and numeric precision used across the application.
Centralizes magic strings and values to prevent typos and enable IDE auto-complete.
"""

from decimal import Decimal


class DocumentStatus:
    """Lifecycle states for `Document`-derived records (Sale, Purchase, Proforma, StockCount).

    Not every status applies to every document type: SUSPENDED/CONVERTED are
    sale-and-proforma specific (held carts, proforma-to-sale conversion),
    QUOTE/EXPIRED apply to proformas, and COUNTED applies to stock counts.
    """

    COMPLETED = "COMPLETED"
    VOID = "VOID"
    DRAFT = "DRAFT"
    SUSPENDED = "SUSPENDED"
    QUOTE = "QUOTE"
    EXPIRED = "EXPIRED"
    CONVERTED = "CONVERTED"
    COUNTED = "COUNTED"


class DocumentType:
    """The `type` discriminator for `Document`'s joined-table-inheritance hierarchy."""

    SALE = "SALE"
    PURCHASE = "PURCHASE"
    RETURN = "RETURN"
    PROFORMA = "PROFORMA"
    STOCK_COUNT = "STOCK_COUNT"
    ADJUSTMENT = "ADJUSTMENT"


class ShiftStatus:
    """State of a cashier's cash-drawer shift (opening float through closing reconciliation)."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class MovementType:
    """Reason code recorded on every `StockMovement` row, per CLAUDE.md's inventory-costing rules."""

    SALE = "SALE"
    PURCHASE = "PURCHASE"
    ADJUSTMENT = "ADJUSTMENT"
    RETURN = "RETURN"
    VOID = "VOID"


class PaymentMethodType:
    """Built-in payment method identifiers; shops can also define custom methods in settings."""

    CASH = "Cash"
    CARD = "Card"
    CREDIT = "Credit"
    QR_MOBILE = "QR/Mobile"
    CHEQUE = "Cheque"
    BANK_TRANSFER = "Transfer"
    REFUND = "REFUND"


class Precision:
    """Standard quantization constants for money and quantities."""

    MONEY = Decimal("0.01")  # 2 decimal places for currency
    QUANTITY = Decimal("0.001")  # 3 decimal places for weights/quantities
