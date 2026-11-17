"""Warranty DTO models for Phase 9 (#825, #826, #820)."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class WarrantyDTO:
    """Immutable data transfer object representing a warranty for UI and search callers (#825)."""

    id: int
    code: str
    serial_number: str | None
    product_id: int
    product_name: str
    customer_id: int | None
    customer_name: str | None
    customer_phone: str | None
    sale_id: int
    sale_document_number: str
    sold_date: datetime
    start_date: date
    end_date: date
    duration: int
    duration_unit: str
    warranty_type: str
    remedy: str
    terms_snapshot: str | None
    exclusions_snapshot: str | None
    status: str
    effective_status: str
    days_remaining: int
    has_active_claim: bool = False
    active_claim_id: int | None = None
