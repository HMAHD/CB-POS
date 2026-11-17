"""Warranty DTO models for Phase 9 (#825, #826, #820)."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


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


@dataclass(frozen=True)
class WarrantyClaimEventDTO:
    """Immutable data transfer object representing a claim transition event (#826)."""

    id: int
    claim_id: int
    from_status: str | None
    to_status: str
    user_id: int
    username: str
    event_time: datetime
    notes: str | None


@dataclass(frozen=True)
class WarrantyClaimDTO:
    """Immutable data transfer object representing a warranty claim (#826)."""

    id: int
    document_number: str
    warranty_id: int | None
    warranty_code: str | None
    product_id: int | None
    product_name: str
    customer_id: int | None
    customer_name: str | None
    customer_phone: str | None
    item_serial: str | None
    claim_status: str
    intake_date: datetime
    defect_description: str
    item_condition: str | None
    accessories_received: str | None
    is_covered: bool
    resolution: str | None
    resolution_notes: str | None
    rejection_reason: str | None
    replacement_warranty_id: int | None
    replacement_serial: str | None
    repair_cost: Decimal
    charge_customer: Decimal
    resolved_by_user_id: int | None
    resolved_by_username: str | None
    resolved_at: datetime | None
    collected_by_name: str | None
    collected_at: datetime | None
    user_id: int
    created_at: datetime
    events: tuple[WarrantyClaimEventDTO, ...] = ()
