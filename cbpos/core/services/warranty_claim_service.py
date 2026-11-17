"""Warranty claim service for Phase 9 (#826, #820).

Owns claim intake, state machine transitions, resolution, replacement warranty
issuance, collection, and queries.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, joinedload

from cbpos.core.constants.audit import WARRANTY_EVENT
from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import MovementType
from cbpos.core.database import Database
from cbpos.core.models import (
    AuditLog,
    Product,
    Purchase,
    PurchaseItem,
    Supplier,
    Warranty,
    WarrantyClaim,
    WarrantyClaimEvent,
)
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.document_service import DocumentService
from cbpos.core.services.refund_service import RefundLineRequest, RefundResult, RefundService
from cbpos.core.services.stock_service import StockService
from cbpos.core.services.supplier_payable_service import SupplierPayableService
from cbpos.core.services.warranty_dto import WarrantyClaimDTO, WarrantyClaimEventDTO
from cbpos.core.services.warranty_service import WarrantyService, _require_permission, _session_scope

logger = logging.getLogger(__name__)

# State machine transition rules (#826)
VALID_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "INTAKE": frozenset({"IN_INSPECTION", "SUPPLIER_DISPATCHED", "REJECTED"}),
    "IN_INSPECTION": frozenset({"SUPPLIER_DISPATCHED", "RESOLVED", "REJECTED"}),
    "SUPPLIER_DISPATCHED": frozenset({"SUPPLIER_RETURNED", "REJECTED"}),
    "SUPPLIER_RETURNED": frozenset({"IN_INSPECTION", "RESOLVED", "REJECTED"}),
    "RESOLVED": frozenset({"COLLECTED"}),
    "COLLECTED": frozenset(),
    "REJECTED": frozenset(),
    "VOID": frozenset(),
    "CANCELLED": frozenset(),
}

FINAL_STATUSES: frozenset[str] = frozenset({"COLLECTED", "REJECTED", "VOID", "CANCELLED"})

VALID_RESOLUTIONS: frozenset[str] = frozenset(
    {
        "REPAIRED",
        "REPLACED_SAME",
        "REPLACED_DIFFERENT",
        "REFUNDED",
        "REJECTED_UNCOVERED",
    }
)


def _claim_to_dto(claim: WarrantyClaim) -> WarrantyClaimDTO:
    """Map WarrantyClaim ORM model and related entities to immutable WarrantyClaimDTO."""
    w_code = claim.warranty.code if claim.warranty else None

    p_name = ""
    if claim.product:
        p_name = claim.product.name_en or ""
    elif claim.warranty and claim.warranty.product:
        p_name = claim.warranty.product.name_en or ""

    cust_name = claim.customer_name_snapshot
    if not cust_name and claim.customer:
        cust_name = claim.customer.name
    elif not cust_name and claim.warranty and claim.warranty.customer:
        cust_name = claim.warranty.customer.name

    cust_phone = claim.customer_phone_snapshot
    if not cust_phone and claim.customer:
        cust_phone = claim.customer.phone
    elif not cust_phone and claim.warranty and claim.warranty.customer:
        cust_phone = claim.warranty.customer.phone

    resolved_username = claim.resolved_by_user.username if claim.resolved_by_user else None
    refund_doc = claim.refund_sale.document_number if getattr(claim, "refund_sale", None) else None
    supp_name = claim.supplier.company_name if getattr(claim, "supplier", None) else None

    events_dto = tuple(
        WarrantyClaimEventDTO(
            id=e.id,
            claim_id=e.claim_id,
            from_status=e.from_status,
            to_status=e.to_status,
            user_id=e.user_id,
            username=e.user.username if e.user else str(e.user_id),
            event_time=e.event_time,
            notes=e.notes,
        )
        for e in sorted(claim.events, key=lambda ev: ev.event_time or datetime.min)
    )

    return WarrantyClaimDTO(
        id=claim.id,
        document_number=claim.document_number,
        warranty_id=claim.warranty_id,
        warranty_code=w_code,
        product_id=claim.product_id,
        product_name=p_name,
        customer_id=claim.customer_id,
        customer_name=cust_name,
        customer_phone=cust_phone,
        item_serial=claim.item_serial,
        claim_status=claim.claim_status,
        intake_date=claim.intake_date,
        defect_description=claim.defect_description,
        item_condition=claim.item_condition,
        accessories_received=claim.accessories_received,
        is_covered=claim.is_covered,
        resolution=claim.resolution,
        resolution_notes=claim.resolution_notes,
        rejection_reason=claim.rejection_reason,
        replacement_warranty_id=claim.replacement_warranty_id,
        replacement_serial=claim.replacement_serial,
        repair_cost=claim.repair_cost or Decimal("0.00"),
        charge_customer=claim.charge_customer or Decimal("0.00"),
        resolved_by_user_id=claim.resolved_by_user_id,
        resolved_by_username=resolved_username,
        resolved_at=claim.resolved_at,
        collected_by_name=claim.collected_by_name,
        collected_at=claim.collected_at,
        user_id=claim.user_id,
        created_at=claim.date or claim.intake_date,
        defective_unit_status=getattr(claim, "defective_unit_status", "HELD") or "HELD",
        refund_sale_id=getattr(claim, "refund_sale_id", None),
        refund_document_number=refund_doc,
        supplier_id=getattr(claim, "supplier_id", None),
        supplier_name=supp_name,
        supplier_rma_ref=getattr(claim, "supplier_rma_ref", None),
        sent_to_supplier_at=getattr(claim, "sent_to_supplier_at", None),
        returned_from_supplier_at=getattr(claim, "returned_from_supplier_at", None),
        supplier_outcome=getattr(claim, "supplier_outcome", None),
        supplier_credit_amount=getattr(claim, "supplier_credit_amount", Decimal("0.00")) or Decimal("0.00"),
        expected_ready_date=getattr(claim, "expected_ready_date", None),
        replacement_cost_snapshot=getattr(claim, "replacement_cost_snapshot", None),
        events=events_dto,
    )


class WarrantyClaimService:
    """Service owning warranty claim workflows, invariants, and state machine transitions."""

    @classmethod
    def create_claim(
        cls,
        defect_description: str,
        user_id: int,
        warranty_id: int | None = None,
        product_id: int | None = None,
        customer_id: int | None = None,
        customer_name_snapshot: str | None = None,
        customer_phone_snapshot: str | None = None,
        item_serial: str | None = None,
        accessories_received: str | None = None,
        item_condition: str | None = None,
        is_covered: bool | None = None,
        expected_ready_date: date | None = None,
        terminal_id: str | None = None,
        session: Session | None = None,
    ) -> WarrantyClaimDTO:
        """Create a new warranty claim and record initial intake event (#826)."""
        if not defect_description or not defect_description.strip():
            raise ValueError("defect_description_required")

        clean_defect = defect_description.strip()

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_CLAIM_CREATE, user_id)

            resolved_is_covered = is_covered

            # If linked to a warranty, enforce 1 active claim invariant and check coverage
            if warranty_id is not None:
                w = s.get(
                    Warranty,
                    warranty_id,
                    options=[
                        joinedload(Warranty.product),
                        joinedload(Warranty.customer),
                        joinedload(Warranty.policy),
                        joinedload(Warranty.claims),
                    ],
                )
                if not w:
                    raise ValueError(f"Warranty {warranty_id} not found")

                # Invariant: 1 active claim per warranty
                active_claim = cls.get_active_claim_for_warranty(warranty_id, session=s)
                if active_claim:
                    raise ValueError(
                        f"warranty_already_has_active_claim: Claim {active_claim.document_number} (ID {active_claim.id}) is active"
                    )

                # Auto-populate fields from warranty if omitted
                if product_id is None:
                    product_id = w.product_id
                if item_serial is None and w.serial_number:
                    item_serial = w.serial_number
                if customer_id is None:
                    customer_id = w.customer_id
                if not customer_name_snapshot and w.customer:
                    customer_name_snapshot = w.customer.name
                if not customer_phone_snapshot and w.customer:
                    customer_phone_snapshot = w.customer.phone

                # Auto-detect coverage status if not explicitly passed
                eff_status, _ = WarrantyService.calculate_effective_status(w.status, w.end_date)
                warranty_is_active = eff_status in ("ACTIVE", "EXPIRING")

                if resolved_is_covered is None:
                    resolved_is_covered = warranty_is_active
                elif resolved_is_covered and not warranty_is_active:
                    # Overriding an expired or void warranty to covered requires resolve permission
                    _require_permission(s, Permissions.WARRANTY_CLAIM_RESOLVE, user_id)
            else:
                if resolved_is_covered is None:
                    resolved_is_covered = False

            # Generate terminal-scoped document number
            doc_number = DocumentService.generate_number("WARRANTY_CLAIM", session=s)

            now = datetime.now()
            claim = WarrantyClaim(
                document_number=doc_number,
                date=now,
                type="warranty_claim",
                status="INTAKE",
                user_id=user_id,
                terminal_id=terminal_id,
                origin_terminal_id=terminal_id,
                synced=False,
                warranty_id=warranty_id,
                product_id=product_id,
                customer_id=customer_id,
                customer_name_snapshot=customer_name_snapshot.strip() if customer_name_snapshot else None,
                customer_phone_snapshot=customer_phone_snapshot.strip() if customer_phone_snapshot else None,
                item_serial=item_serial.strip().upper() if item_serial else None,
                claim_status="INTAKE",
                intake_date=now,
                expected_ready_date=expected_ready_date,
                defect_description=clean_defect,
                item_condition=item_condition.strip() if item_condition else None,
                accessories_received=accessories_received.strip() if accessories_received else None,
                is_covered=bool(resolved_is_covered),
            )
            s.add(claim)
            s.flush()

            # Record initial intake event
            initial_event = WarrantyClaimEvent(
                claim_id=claim.id,
                from_status=None,
                to_status="INTAKE",
                user_id=user_id,
                event_time=now,
                notes="Claim intake registered",
                synced=False,
            )
            s.add(initial_event)

            # Audit log
            s.add(
                AuditLog(
                    user_id=user_id,
                    action="WARRANTY_CLAIM_CREATE",
                    event_type=WARRANTY_EVENT,
                    details=(
                        f"Warranty claim {claim.document_number} (ID {claim.id}) created for "
                        f"warranty ID {warranty_id}, covered={claim.is_covered}"
                    ),
                )
            )
            s.flush()

            # Reload with relationships for DTO mapping
            refreshed = cls._load_claim(s, claim.id)
            assert refreshed is not None
            return _claim_to_dto(refreshed)

    @classmethod
    def transition_status(
        cls,
        claim_id: int,
        to_status: str,
        user_id: int,
        notes: str | None = None,
        session: Session | None = None,
    ) -> WarrantyClaimDTO:
        """Transition claim status along allowed paths (#826)."""
        clean_status = (to_status or "").strip().upper()

        with _session_scope(session) as s:
            claim = cls._load_claim(s, claim_id)
            if not claim:
                raise ValueError(f"Claim {claim_id} not found")

            current_status = claim.claim_status
            allowed_next = VALID_STATUS_TRANSITIONS.get(current_status, frozenset())
            if clean_status not in allowed_next:
                raise ValueError(f"invalid_transition: Cannot transition claim from {current_status} to {clean_status}")

            # Check permissions
            if clean_status in ("RESOLVED", "REJECTED", "VOID"):
                _require_permission(s, Permissions.WARRANTY_CLAIM_RESOLVE, user_id)
            else:
                _require_permission(s, Permissions.WARRANTY_CLAIM_CREATE, user_id)

            if clean_status == "REJECTED" and not notes and not claim.rejection_reason:
                raise ValueError("rejection_reason_required")

            now = datetime.now()
            claim.claim_status = clean_status
            claim.synced = False
            if clean_status == "REJECTED" and notes:
                claim.rejection_reason = notes.strip()
                claim.resolution = "REJECTED_UNCOVERED"
                claim.resolved_by_user_id = user_id
                claim.resolved_at = now

            event = WarrantyClaimEvent(
                claim_id=claim.id,
                from_status=current_status,
                to_status=clean_status,
                user_id=user_id,
                event_time=now,
                notes=notes.strip() if notes else None,
                synced=False,
            )
            s.add(event)

            s.add(
                AuditLog(
                    user_id=user_id,
                    action="WARRANTY_CLAIM_STATUS_CHANGE",
                    event_type=WARRANTY_EVENT,
                    details=(
                        f"Warranty claim {claim.document_number} (ID {claim.id}) status transitioned "
                        f"from {current_status} to {clean_status}"
                    ),
                )
            )
            s.flush()
            s.expire_all()

            refreshed = cls._load_claim(s, claim.id)
            assert refreshed is not None
            return _claim_to_dto(refreshed)

    @classmethod
    def resolve_claim(
        cls,
        claim_id: int,
        resolution: str,
        user_id: int,
        resolution_notes: str | None = None,
        repair_cost: Decimal = Decimal("0.00"),
        charge_customer: Decimal = Decimal("0.00"),
        replacement_serial: str | None = None,
        session: Session | None = None,
    ) -> WarrantyClaimDTO:
        """Resolve claim with repair, replacement, refund, or uncovered rejection (#826)."""
        clean_res = (resolution or "").strip().upper()
        if clean_res not in VALID_RESOLUTIONS:
            raise ValueError(f"Invalid claim resolution: {resolution}")

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_CLAIM_RESOLVE, user_id)

            claim = cls._load_claim(s, claim_id)
            if not claim:
                raise ValueError(f"Claim {claim_id} not found")

            if claim.claim_status in FINAL_STATUSES:
                raise ValueError(
                    f"cannot_resolve_final_claim: Claim {claim_id} is already in state {claim.claim_status}"
                )

            if claim.claim_status not in ("IN_INSPECTION", "SUPPLIER_RETURNED"):
                raise ValueError(
                    f"claim_must_be_inspected: Current state {claim.claim_status} cannot be resolved directly"
                )

            now = datetime.now()
            from_status = claim.claim_status

            # Handle replacement warranty creation
            if clean_res in ("REPLACED_SAME", "REPLACED_DIFFERENT"):
                if claim.warranty:
                    old_w = claim.warranty
                    old_w.status = "REPLACED"
                    old_w.last_modified = now

                    # Generate replacement warranty code
                    rep_code = f"{old_w.code}-R"
                    existing_code = s.scalar(select(func.count(Warranty.id)).where(Warranty.code == rep_code))
                    if existing_code:
                        rep_code = f"{old_w.code}-R{now.strftime('%m%d%H%M')}"

                    # Compute replacement end date
                    start_date = now.date()
                    if old_w.policy:
                        rep_end_date = WarrantyService.compute_end_date(
                            start_date, old_w.policy.duration, old_w.policy.duration_unit
                        )
                    else:
                        rep_end_date = old_w.end_date

                    clean_sn = replacement_serial.strip().upper() if replacement_serial else None
                    new_w = Warranty(
                        code=rep_code,
                        unit_index=1,
                        sale_id=old_w.sale_id,
                        sale_item_id=old_w.sale_item_id,
                        product_id=old_w.product_id,
                        customer_id=old_w.customer_id,
                        policy_id=old_w.policy_id,
                        warranty_type=old_w.warranty_type,
                        duration=old_w.duration,
                        duration_unit=old_w.duration_unit,
                        remedy=old_w.remedy,
                        provider_name=old_w.provider_name,
                        start_date=start_date,
                        end_date=rep_end_date,
                        serial_number=clean_sn,
                        terms_text=old_w.terms_text,
                        exclusions_text=old_w.exclusions_text,
                        status="ACTIVE",
                        replaces_warranty_id=old_w.id,
                        synced=False,
                    )
                    s.add(new_w)
                    s.flush()

                    claim.replacement_warranty_id = new_w.id
                    claim.replacement_serial = clean_sn

                    s.add(
                        AuditLog(
                            user_id=user_id,
                            action="WARRANTY_REPLACEMENT_ISSUED",
                            event_type=WARRANTY_EVENT,
                            details=(
                                f"Replacement warranty {new_w.code} (ID {new_w.id}) issued for "
                                f"claim {claim.document_number} replacing warranty {old_w.code} (ID {old_w.id})"
                            ),
                        )
                    )

            if clean_res == "REJECTED_UNCOVERED":
                to_status = "REJECTED"
                claim.rejection_reason = (
                    resolution_notes.strip() if resolution_notes else "Defect uncovered by warranty"
                )
            else:
                to_status = "RESOLVED"

            claim.claim_status = to_status
            claim.resolution = clean_res
            claim.resolution_notes = resolution_notes.strip() if resolution_notes else None
            claim.repair_cost = Decimal(str(repair_cost or 0))
            claim.charge_customer = Decimal(str(charge_customer or 0))
            claim.resolved_by_user_id = user_id
            claim.resolved_at = now
            claim.synced = False

            event = WarrantyClaimEvent(
                claim_id=claim.id,
                from_status=from_status,
                to_status=to_status,
                user_id=user_id,
                event_time=now,
                notes=f"Resolved as {clean_res}. {resolution_notes or ''}".strip(),
                synced=False,
            )
            s.add(event)

            s.add(
                AuditLog(
                    user_id=user_id,
                    action="WARRANTY_CLAIM_RESOLVE",
                    event_type=WARRANTY_EVENT,
                    details=(
                        f"Warranty claim {claim.document_number} (ID {claim.id}) resolved as {clean_res} "
                        f"by user {user_id}, charge={claim.charge_customer}, cost={claim.repair_cost}"
                    ),
                )
            )
            s.flush()
            s.expire_all()

            refreshed = cls._load_claim(s, claim.id)
            assert refreshed is not None
            return _claim_to_dto(refreshed)

    @classmethod
    def replace_from_stock(
        cls,
        claim_id: int,
        replacement_product_id: int,
        user_id: int,
        new_serial: str | None = None,
        resolution_notes: str | None = None,
        repair_cost: Decimal = Decimal("0.00"),
        charge_customer: Decimal = Decimal("0.00"),
        session: Session | None = None,
    ) -> WarrantyClaimDTO:
        """Resolve claim by issuing a replacement unit from shop inventory in one atomic transaction (#827)."""
        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_CLAIM_RESOLVE, user_id)

            claim = cls._load_claim(s, claim_id)
            if not claim:
                raise ValueError(f"Claim {claim_id} not found")

            if claim.claim_status not in ("IN_INSPECTION", "SUPPLIER_RETURNED", "SUPPLIER_DISPATCHED"):
                raise ValueError(
                    f"claim_cannot_be_resolved: Current state {claim.claim_status} cannot be replaced from stock"
                )

            if not claim.warranty:
                raise ValueError(f"Claim {claim.document_number} has no linked warranty to replace")

            old_w = claim.warranty
            rep_prod = s.get(Product, replacement_product_id)
            if not rep_prod:
                raise ValueError(f"Replacement product {replacement_product_id} not found")

            now = datetime.now()
            from_status = claim.claim_status

            # Inventory deduction: -1.000 with MovementType.WARRANTY
            StockService.record_movement(
                product_id=replacement_product_id,
                qty_change=Decimal("-1.000"),
                movement_type=MovementType.WARRANTY,
                user_id=user_id,
                document_id=claim.id,
                session=s,
                enforce_non_negative=True,
            )

            # Mark old warranty REPLACED
            old_w.status = "REPLACED"
            old_w.last_modified = now

            # Coverage term determination & db constraint guard
            term_mode = ConfigService.get("warranty_replacement_term") or "REMAINING"
            start_date = now.date()
            if term_mode == "FRESH":
                if old_w.policy:
                    rep_end_date = WarrantyService.compute_end_date(
                        start_date, old_w.policy.duration, old_w.policy.duration_unit
                    )
                else:
                    rep_end_date = WarrantyService.compute_end_date(start_date, old_w.duration, old_w.duration_unit)
            else:  # REMAINING
                rep_end_date = max(start_date, old_w.end_date)

            # Generate replacement warranty code
            rep_code = f"{old_w.code}-R"
            existing_code = s.scalar(select(func.count(Warranty.id)).where(Warranty.code == rep_code))
            if existing_code:
                rep_code = f"{old_w.code}-R{now.strftime('%m%d%H%M')}"

            clean_sn = new_serial.strip().upper() if new_serial else None
            new_w = Warranty(
                code=rep_code,
                unit_index=1,
                sale_id=old_w.sale_id,
                sale_item_id=old_w.sale_item_id,
                product_id=replacement_product_id,
                customer_id=old_w.customer_id,
                policy_id=old_w.policy_id,
                warranty_type=old_w.warranty_type,
                duration=old_w.duration,
                duration_unit=old_w.duration_unit,
                remedy=old_w.remedy,
                provider_name=old_w.provider_name,
                start_date=start_date,
                end_date=rep_end_date,
                serial_number=clean_sn,
                terms_text=old_w.terms_text,
                exclusions_text=old_w.exclusions_text,
                status="ACTIVE",
                replaces_warranty_id=old_w.id,
                synced=False,
            )
            s.add(new_w)
            s.flush()

            # Claim state mutation
            claim.claim_status = "RESOLVED"
            claim.resolution = "REPLACED_SAME" if replacement_product_id == old_w.product_id else "REPLACED_DIFFERENT"
            claim.replacement_warranty_id = new_w.id
            claim.replacement_serial = clean_sn
            claim.replacement_cost_snapshot = Decimal(str(rep_prod.cost)) if rep_prod.cost is not None else None
            if from_status == "SUPPLIER_DISPATCHED":
                claim.defective_unit_status = "SENT_TO_SUPPLIER"
            else:
                claim.defective_unit_status = "HELD"
            claim.resolved_by_user_id = user_id
            claim.resolved_at = now
            claim.resolution_notes = resolution_notes.strip() if resolution_notes else None
            claim.repair_cost = Decimal(str(repair_cost or 0))
            claim.charge_customer = Decimal(str(charge_customer or 0))
            claim.synced = False

            # Add event
            event = WarrantyClaimEvent(
                claim_id=claim.id,
                from_status=from_status,
                to_status="RESOLVED",
                user_id=user_id,
                event_time=now,
                notes=f"Resolved via stock replacement ({claim.resolution}). {resolution_notes or ''}".strip(),
                synced=False,
            )
            s.add(event)

            # Add audit log
            s.add(
                AuditLog(
                    user_id=user_id,
                    action="WARRANTY_REPLACEMENT_FROM_STOCK",
                    event_type=WARRANTY_EVENT,
                    details=(
                        f"Warranty claim {claim.document_number} (ID {claim.id}) resolved via stock replacement "
                        f"with product {rep_prod.name_en} (ID {rep_prod.id}), new warranty {new_w.code} (ID {new_w.id})"
                    ),
                )
            )
            s.flush()
            s.expire_all()

            refreshed = cls._load_claim(s, claim.id)
            assert refreshed is not None
            return _claim_to_dto(refreshed)

    @classmethod
    def refund_claim(
        cls,
        claim_id: int,
        user_id: int,
        reason: str | None = None,
        tender_override: str | None = None,
        override_reason: str | None = None,
        session: Session | None = None,
    ) -> tuple[WarrantyClaimDTO, RefundResult]:
        """Resolve claim by refunding the claimed unit through RefundService.refund (#827)."""
        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_CLAIM_RESOLVE, user_id)

            claim = cls._load_claim(s, claim_id)
            if not claim:
                raise ValueError(f"Claim {claim_id} not found")

            if claim.claim_status in FINAL_STATUSES:
                raise ValueError(f"claim_cannot_be_resolved: Current state {claim.claim_status} cannot be refunded")

            if not claim.warranty:
                raise ValueError(f"Claim {claim.document_number} has no linked warranty to refund")

            old_w = claim.warranty
            if not old_w.sale_id or not old_w.sale_item_id:
                raise ValueError(f"Warranty {old_w.code} has no linked sale item for refund")

            now = datetime.now()
            from_status = claim.claim_status

            # Pre-set claim resolution to "REFUNDED" so WarrantyService.cancel_units_for_refund_in_session
            # recognizes this claim as authorized for refund and transitions matching_claim.claim_status = "COLLECTED"
            claim.resolution = "REFUNDED"
            claim.defective_unit_status = "HELD"
            claim.resolved_by_user_id = user_id
            claim.resolved_at = now
            claim.resolution_notes = reason.strip() if reason else None
            claim.synced = False
            s.flush()

            # Execute refund through RefundService
            clean_reason = (reason or f"Warranty claim {claim.document_number}").strip()
            refund_lines = [
                RefundLineRequest(
                    sale_item_id=old_w.sale_item_id,
                    qty=Decimal("1.000"),
                    reason=clean_reason,
                )
            ]
            selected_serials = {old_w.sale_item_id: [old_w.serial_number]} if old_w.serial_number else None

            refund_result = RefundService.refund(
                sale_id=old_w.sale_id,
                lines=refund_lines,
                reason=clean_reason,
                user_id=user_id,
                tender_override=tender_override,
                override_reason=override_reason,
                selected_serials=selected_serials,
                claim_id=claim.id,
                session=s,
            )

            # Neutralize stock: RefundService recorded MovementType.RETURN (+1).
            # Because the defective unit is broken and cannot be sold, offset with MovementType.ADJUSTMENT (-1).
            StockService.record_movement(
                product_id=old_w.product_id,
                qty_change=Decimal("-1.000"),
                movement_type=MovementType.ADJUSTMENT,
                user_id=user_id,
                document_id=claim.id,
                session=s,
                enforce_non_negative=False,
            )

            # Update claim with refund document linkage
            claim.refund_sale_id = refund_result.refund_sale_id
            claim.claim_status = "COLLECTED"

            # Check if event already created by cancel_units_for_refund_in_session
            existing_event = s.scalar(
                select(func.count(WarrantyClaimEvent.id)).where(
                    WarrantyClaimEvent.claim_id == claim.id,
                    WarrantyClaimEvent.to_status == "COLLECTED",
                )
            )
            if not existing_event:
                event = WarrantyClaimEvent(
                    claim_id=claim.id,
                    from_status=from_status,
                    to_status="COLLECTED",
                    user_id=user_id,
                    event_time=now,
                    notes=f"Resolved via refund {refund_result.refund_document_number}. {reason or ''}".strip(),
                    synced=False,
                )
                s.add(event)

            s.add(
                AuditLog(
                    user_id=user_id,
                    action="WARRANTY_CLAIM_REFUND",
                    event_type=WARRANTY_EVENT,
                    details=(
                        f"Warranty claim {claim.document_number} (ID {claim.id}) resolved via refund "
                        f"{refund_result.refund_document_number} (Sale ID {refund_result.refund_sale_id})"
                    ),
                )
            )
            s.flush()
            s.expire_all()

            refreshed = cls._load_claim(s, claim.id)
            assert refreshed is not None
            return _claim_to_dto(refreshed), refund_result

    @classmethod
    def send_to_supplier(
        cls,
        claim_id: int,
        supplier_id: int,
        user_id: int,
        supplier_rma_ref: str | None = None,
        notes: str | None = None,
        session: Session | None = None,
    ) -> WarrantyClaimDTO:
        """Dispatch defective item to supplier/manufacturer for RMA handling (#828)."""
        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_CLAIM_RESOLVE, user_id)

            claim = cls._load_claim(s, claim_id)
            if not claim:
                raise ValueError(f"Claim {claim_id} not found")

            supplier = s.get(Supplier, supplier_id)
            if not supplier:
                raise ValueError(f"Supplier {supplier_id} not found")

            now = datetime.now()
            from_status = claim.claim_status

            # Status validation
            if claim.claim_status in ("INTAKE", "IN_INSPECTION"):
                claim.claim_status = "SUPPLIER_DISPATCHED"
            elif claim.claim_status in ("RESOLVED", "COLLECTED"):
                # Advance customer resolution: physical unit was HELD and is now dispatched to supplier
                if claim.defective_unit_status != "HELD":
                    raise ValueError(f"defective_unit_not_held: Physical unit status is {claim.defective_unit_status}")
            else:
                raise ValueError(
                    f"claim_cannot_be_dispatched: Current status {claim.claim_status} cannot be sent to supplier"
                )

            clean_ref = supplier_rma_ref.strip() if supplier_rma_ref else None
            claim.supplier_id = supplier_id
            claim.supplier_rma_ref = clean_ref
            claim.sent_to_supplier_at = now
            claim.defective_unit_status = "SENT_TO_SUPPLIER"
            claim.synced = False

            event = WarrantyClaimEvent(
                claim_id=claim.id,
                from_status=from_status,
                to_status=claim.claim_status,
                user_id=user_id,
                event_time=now,
                notes=f"Dispatched to supplier {supplier.company_name} (RMA Ref: {clean_ref or 'N/A'}). {notes or ''}".strip(),
                synced=False,
            )
            s.add(event)

            s.add(
                AuditLog(
                    user_id=user_id,
                    action="WARRANTY_SUPPLIER_DISPATCH",
                    event_type=WARRANTY_EVENT,
                    details=(
                        f"Warranty claim {claim.document_number} (ID {claim.id}) dispatched to supplier "
                        f"{supplier.company_name} (ID {supplier.id}), ref={clean_ref}"
                    ),
                )
            )
            s.flush()
            s.expire_all()

            refreshed = cls._load_claim(s, claim.id)
            assert refreshed is not None
            return _claim_to_dto(refreshed)

    @classmethod
    def receive_from_supplier(
        cls,
        claim_id: int,
        user_id: int,
        to_status: str = "SUPPLIER_RETURNED",
        notes: str | None = None,
        session: Session | None = None,
    ) -> WarrantyClaimDTO:
        """Receive item back from supplier/manufacturer (#828)."""
        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_CLAIM_RESOLVE, user_id)

            claim = cls._load_claim(s, claim_id)
            if not claim:
                raise ValueError(f"Claim {claim_id} not found")

            if claim.defective_unit_status != "SENT_TO_SUPPLIER":
                raise ValueError(f"unit_not_at_supplier: Defective unit status is {claim.defective_unit_status}")

            clean_target = to_status.strip().upper()
            if clean_target not in ("SUPPLIER_RETURNED", "IN_INSPECTION"):
                raise ValueError(f"invalid_return_status: {to_status}")

            now = datetime.now()
            from_status = claim.claim_status

            if claim.claim_status == "SUPPLIER_DISPATCHED":
                claim.claim_status = clean_target
            # If claim was already RESOLVED or COLLECTED prior to RMA dispatch, keep customer status

            claim.returned_from_supplier_at = now
            claim.defective_unit_status = "RETURNED_FROM_SUPPLIER"
            claim.synced = False

            event = WarrantyClaimEvent(
                claim_id=claim.id,
                from_status=from_status,
                to_status=claim.claim_status,
                user_id=user_id,
                event_time=now,
                notes=f"Received back from supplier. {notes or ''}".strip(),
                synced=False,
            )
            s.add(event)

            s.add(
                AuditLog(
                    user_id=user_id,
                    action="WARRANTY_SUPPLIER_RECEIVE",
                    event_type=WARRANTY_EVENT,
                    details=(
                        f"Warranty claim {claim.document_number} (ID {claim.id}) received from supplier "
                        f"(returned_status={claim.claim_status})"
                    ),
                )
            )
            s.flush()
            s.expire_all()

            refreshed = cls._load_claim(s, claim.id)
            assert refreshed is not None
            return _claim_to_dto(refreshed)

    @classmethod
    def record_supplier_outcome(
        cls,
        claim_id: int,
        outcome: str,
        user_id: int,
        credit_amount: Decimal = Decimal("0.00"),
        replacement_serial: str | None = None,
        notes: str | None = None,
        session: Session | None = None,
    ) -> WarrantyClaimDTO:
        """Record the final resolution/disposition provided by the supplier (#828)."""
        clean_outcome = outcome.strip().upper()
        if clean_outcome not in ("REPAIRED", "REPLACED", "CREDIT_NOTE", "REJECTED"):
            raise ValueError(f"invalid_supplier_outcome: {outcome}")

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_CLAIM_RESOLVE, user_id)

            claim = cls._load_claim(s, claim_id)
            if not claim:
                raise ValueError(f"Claim {claim_id} not found")

            if claim.defective_unit_status not in ("SENT_TO_SUPPLIER", "RETURNED_FROM_SUPPLIER"):
                raise ValueError(
                    f"unit_not_in_rma: Cannot record supplier outcome when unit status is {claim.defective_unit_status}"
                )

            now = datetime.now()
            from_status = claim.claim_status

            if clean_outcome == "REPAIRED":
                claim.defective_unit_status = "HELD"

            elif clean_outcome == "REPLACED":
                has_prior_replacement = (
                    claim.resolution in ("REPLACED_SAME", "REPLACED_DIFFERENT")
                    or claim.replacement_warranty_id is not None
                )
                if has_prior_replacement:
                    # Shop had already replaced the unit for the customer from shelf stock.
                    # The replacement unit from the supplier now restocks the shop's sellable inventory!
                    if not claim.product_id:
                        raise ValueError("Claim has no linked product to restock")
                    StockService.record_movement(
                        product_id=claim.product_id,
                        qty_change=Decimal("1.000"),
                        movement_type=MovementType.WARRANTY,
                        user_id=user_id,
                        document_id=claim.id,
                        session=s,
                        enforce_non_negative=False,
                    )
                    claim.defective_unit_status = "SCRAPPED"
                else:
                    # Customer waiting for supplier replacement unit
                    clean_rep_sn = replacement_serial.strip().upper() if replacement_serial else None
                    claim.replacement_serial = clean_rep_sn
                    if claim.replacement_warranty:
                        claim.replacement_warranty.serial_number = clean_rep_sn
                    claim.defective_unit_status = "SCRAPPED"

            elif clean_outcome == "CREDIT_NOTE":
                credit_dec = Decimal(str(credit_amount or 0))
                if credit_dec <= Decimal("0.00"):
                    raise ValueError("credit_note_amount_required: Supplier credit note amount must be positive")
                if not claim.supplier_id:
                    raise ValueError("claim_has_no_supplier: Supplier ID is required to record credit note")

                SupplierPayableService.record_credit_note_in_session(
                    session=s,
                    supplier_id=claim.supplier_id,
                    amount=credit_dec,
                    claim_id=claim.id,
                    claim_number=claim.document_number,
                    user_id=user_id,
                    note=notes or f"Supplier credit note for RMA claim {claim.document_number}",
                )
                claim.supplier_credit_amount = credit_dec
                claim.defective_unit_status = "SCRAPPED"

            elif clean_outcome == "REJECTED":
                # Supplier rejected claim; defective unit returned or held as-is
                pass

            claim.supplier_outcome = clean_outcome
            if claim.claim_status not in FINAL_STATUSES and claim.claim_status != "RESOLVED":
                claim.claim_status = "RESOLVED"
                claim.resolved_at = now
                claim.resolved_by_user_id = user_id

            claim.synced = False

            event = WarrantyClaimEvent(
                claim_id=claim.id,
                from_status=from_status,
                to_status=claim.claim_status,
                user_id=user_id,
                event_time=now,
                notes=f"Supplier RMA outcome recorded: {clean_outcome}. {notes or ''}".strip(),
                synced=False,
            )
            s.add(event)

            s.add(
                AuditLog(
                    user_id=user_id,
                    action="WARRANTY_SUPPLIER_OUTCOME",
                    event_type=WARRANTY_EVENT,
                    details=(
                        f"Supplier outcome for claim {claim.document_number} (ID {claim.id}) recorded as {clean_outcome}, "
                        f"credit={claim.supplier_credit_amount}"
                    ),
                )
            )
            s.flush()
            s.expire_all()

            refreshed = cls._load_claim(s, claim.id)
            assert refreshed is not None
            return _claim_to_dto(refreshed)

    @classmethod
    def estimate_supplier_coverage(
        cls,
        product_id: int,
        supplier_id: int | None = None,
        session: Session | None = None,
    ) -> dict[str, Any]:
        """Estimate supplier warranty validity from latest relevant GRN purchase date (#828)."""
        with _session_scope(session) as s:
            policy = WarrantyService.resolve_policy(product_id, session=s)
            if not policy or not policy.supplier_cover_months or policy.supplier_cover_months <= 0:
                return {
                    "has_estimate": False,
                    "reason": "no_supplier_cover_policy",
                    "supplier_name": None,
                    "grn_date": None,
                    "supplier_cover_months": None,
                    "estimated_expiry": None,
                    "is_valid": False,
                    "days_remaining": 0,
                }

            # Query PurchaseItem joined with Purchase
            stmt = (
                select(PurchaseItem, Purchase)
                .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
                .where(
                    PurchaseItem.product_id == product_id,
                    Purchase.status == "COMPLETED",
                )
            )
            if supplier_id:
                stmt = stmt.where(Purchase.supplier_id == supplier_id)

            stmt = stmt.order_by(desc(Purchase.date)).limit(1)
            row = s.execute(stmt).first()

            if not row:
                return {
                    "has_estimate": False,
                    "reason": "no_grn_found",
                    "supplier_name": None,
                    "grn_date": None,
                    "supplier_cover_months": policy.supplier_cover_months,
                    "estimated_expiry": None,
                    "is_valid": False,
                    "days_remaining": 0,
                }

            _p_item, purchase = row
            grn_date = purchase.date.date() if isinstance(purchase.date, datetime) else purchase.date
            expiry_date = WarrantyService.compute_end_date(grn_date, policy.supplier_cover_months, "MONTHS")
            today = date.today()
            is_valid = expiry_date >= today
            days_remaining = (expiry_date - today).days if is_valid else 0
            supp = s.get(Supplier, purchase.supplier_id)
            supp_name = supp.company_name if supp else None

            return {
                "has_estimate": True,
                "reason": None,
                "supplier_id": purchase.supplier_id,
                "supplier_name": supp_name,
                "grn_date": grn_date,
                "grn_document_number": purchase.document_number,
                "supplier_cover_months": policy.supplier_cover_months,
                "estimated_expiry": expiry_date,
                "is_valid": is_valid,
                "days_remaining": days_remaining,
            }

    @classmethod
    def mark_collected(
        cls,
        claim_id: int,
        collected_by_name: str,
        user_id: int,
        notes: str | None = None,
        session: Session | None = None,
    ) -> WarrantyClaimDTO:
        """Mark resolved claim as collected by customer/representative (#826)."""
        if not collected_by_name or not collected_by_name.strip():
            raise ValueError("collected_by_name_required")

        clean_name = collected_by_name.strip()

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_CLAIM_CREATE, user_id)

            claim = cls._load_claim(s, claim_id)
            if not claim:
                raise ValueError(f"Claim {claim_id} not found")

            if claim.claim_status != "RESOLVED":
                raise ValueError(f"cannot_collect_unresolved_claim: Current status is {claim.claim_status}")

            now = datetime.now()
            from_status = claim.claim_status
            claim.claim_status = "COLLECTED"
            claim.collected_by_name = clean_name
            claim.collected_at = now
            claim.synced = False

            event = WarrantyClaimEvent(
                claim_id=claim.id,
                from_status=from_status,
                to_status="COLLECTED",
                user_id=user_id,
                event_time=now,
                notes=f"Collected by {clean_name}. {notes or ''}".strip(),
                synced=False,
            )
            s.add(event)

            s.add(
                AuditLog(
                    user_id=user_id,
                    action="WARRANTY_CLAIM_COLLECT",
                    event_type=WARRANTY_EVENT,
                    details=f"Warranty claim {claim.document_number} (ID {claim.id}) collected by {clean_name}",
                )
            )
            s.flush()
            s.expire_all()

            refreshed = cls._load_claim(s, claim.id)
            assert refreshed is not None
            return _claim_to_dto(refreshed)

    @classmethod
    def reject_claim(
        cls,
        claim_id: int,
        reason: str,
        user_id: int,
        session: Session | None = None,
    ) -> WarrantyClaimDTO:
        """Reject claim as uncovered or invalid (#826)."""
        if not reason or not reason.strip():
            raise ValueError("rejection_reason_required")

        return cls.transition_status(claim_id, "REJECTED", user_id, notes=reason.strip(), session=session)

    @classmethod
    def void_claim(
        cls,
        claim_id: int,
        reason: str,
        user_id: int,
        session: Session | None = None,
    ) -> WarrantyClaimDTO:
        """Void claim administratively with mandatory reason (#826)."""
        if not reason or not reason.strip():
            raise ValueError("void_reason_required")

        clean_reason = reason.strip()

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_CLAIM_RESOLVE, user_id)

            claim = cls._load_claim(s, claim_id)
            if not claim:
                raise ValueError(f"Claim {claim_id} not found")

            if claim.claim_status in ("COLLECTED", "CANCELLED", "VOID"):
                raise ValueError(f"cannot_void_status: Current status is {claim.claim_status}")

            now = datetime.now()
            from_status = claim.claim_status
            claim.claim_status = "VOID"
            claim.status = "VOID"
            claim.resolution_notes = f"VOID: {clean_reason}"
            claim.synced = False

            event = WarrantyClaimEvent(
                claim_id=claim.id,
                from_status=from_status,
                to_status="VOID",
                user_id=user_id,
                event_time=now,
                notes=f"Voided: {clean_reason}",
                synced=False,
            )
            s.add(event)

            s.add(
                AuditLog(
                    user_id=user_id,
                    action="WARRANTY_CLAIM_VOID",
                    event_type=WARRANTY_EVENT,
                    details=f"Warranty claim {claim.document_number} (ID {claim.id}) voided: {clean_reason}",
                )
            )
            s.flush()
            s.expire_all()

            refreshed = cls._load_claim(s, claim.id)
            assert refreshed is not None
            return _claim_to_dto(refreshed)

    @classmethod
    def get_active_claim_for_warranty(
        cls,
        warranty_id: int,
        session: Session | None = None,
    ) -> WarrantyClaim | None:
        """Return the active claim model for a warranty if one exists."""

        def _query(s: Session) -> WarrantyClaim | None:
            stmt = select(WarrantyClaim).where(
                WarrantyClaim.warranty_id == warranty_id,
                WarrantyClaim.claim_status.not_in(list(FINAL_STATUSES)),
            )
            return s.scalars(stmt).first()

        if session is not None:
            return _query(session)
        db = Database()
        with db.get_session() as s:
            return _query(s)

    @classmethod
    def get_claim(cls, claim_id: int, session: Session | None = None) -> WarrantyClaimDTO | None:
        """Fetch claim by ID as DTO."""
        if session is not None:
            claim = cls._load_claim(session, claim_id)
            return _claim_to_dto(claim) if claim else None
        db = Database()
        with db.get_session() as s:
            claim = cls._load_claim(s, claim_id)
            return _claim_to_dto(claim) if claim else None

    @classmethod
    def get_claim_by_document_number(
        cls,
        doc_number: str,
        session: Session | None = None,
    ) -> WarrantyClaimDTO | None:
        """Fetch claim by document number as DTO."""
        clean = (doc_number or "").strip()
        if not clean:
            return None

        def _query(s: Session) -> WarrantyClaimDTO | None:
            stmt = (
                select(WarrantyClaim)
                .where(WarrantyClaim.document_number == clean)
                .options(
                    joinedload(WarrantyClaim.warranty),
                    joinedload(WarrantyClaim.product),
                    joinedload(WarrantyClaim.customer),
                    joinedload(WarrantyClaim.resolved_by_user),
                    joinedload(WarrantyClaim.events).joinedload(WarrantyClaimEvent.user),
                )
            )
            c = s.scalars(stmt).first()
            return _claim_to_dto(c) if c else None

        if session is not None:
            return _query(session)
        db = Database()
        with db.get_session() as s:
            return _query(s)

    @classmethod
    def list_claims(
        cls,
        status: str | None = None,
        search: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 200,
        session: Session | None = None,
    ) -> list[WarrantyClaimDTO]:
        """Query claims matching criteria ordered by intake_date desc (#826)."""

        def _query(s: Session) -> list[WarrantyClaimDTO]:
            stmt = (
                select(WarrantyClaim)
                .options(
                    joinedload(WarrantyClaim.warranty),
                    joinedload(WarrantyClaim.product),
                    joinedload(WarrantyClaim.customer),
                    joinedload(WarrantyClaim.resolved_by_user),
                    joinedload(WarrantyClaim.supplier),
                    joinedload(WarrantyClaim.refund_sale),
                    joinedload(WarrantyClaim.events).joinedload(WarrantyClaimEvent.user),
                )
                .order_by(desc(WarrantyClaim.intake_date))
                .limit(limit)
            )

            if status and status != "ALL":
                if status == "OVERDUE_SUPPLIER":
                    from datetime import timedelta

                    cutoff = datetime.now() - timedelta(days=14)
                    stmt = stmt.where(
                        WarrantyClaim.defective_unit_status == "SENT_TO_SUPPLIER",
                        WarrantyClaim.sent_to_supplier_at <= cutoff,
                    )
                else:
                    stmt = stmt.where(WarrantyClaim.claim_status == status.strip().upper())

            if start_date:
                stmt = stmt.where(func.date(WarrantyClaim.intake_date) >= start_date)
            if end_date:
                stmt = stmt.where(func.date(WarrantyClaim.intake_date) <= end_date)

            if search and search.strip():
                clean_term = search.strip()
                pattern = f"%{clean_term}%"
                stmt = stmt.where(
                    or_(
                        WarrantyClaim.document_number.ilike(pattern),
                        WarrantyClaim.item_serial.ilike(pattern),
                        WarrantyClaim.customer_name_snapshot.ilike(pattern),
                        WarrantyClaim.customer_phone_snapshot.ilike(pattern),
                        WarrantyClaim.defect_description.ilike(pattern),
                    )
                )

            rows = list(s.scalars(stmt).unique().all())
            return [_claim_to_dto(r) for r in rows]

        if session is not None:
            return _query(session)
        db = Database()
        with db.get_session() as s:
            return _query(s)

    @staticmethod
    def _load_claim(session: Session, claim_id: int) -> WarrantyClaim | None:
        """Internal helper to load a claim with all relevant relationships joined."""
        stmt = (
            select(WarrantyClaim)
            .where(WarrantyClaim.id == claim_id)
            .options(
                joinedload(WarrantyClaim.warranty).joinedload(Warranty.policy),
                joinedload(WarrantyClaim.warranty).joinedload(Warranty.product),
                joinedload(WarrantyClaim.warranty).joinedload(Warranty.customer),
                joinedload(WarrantyClaim.product),
                joinedload(WarrantyClaim.customer),
                joinedload(WarrantyClaim.resolved_by_user),
                joinedload(WarrantyClaim.supplier),
                joinedload(WarrantyClaim.refund_sale),
                joinedload(WarrantyClaim.events).joinedload(WarrantyClaimEvent.user),
            )
        )
        return session.scalars(stmt).unique().first()
