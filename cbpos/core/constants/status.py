"""
Constants for document and shift status values used across the application.
Centralizes magic strings to prevent typos and enable IDE auto-complete.
"""


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
