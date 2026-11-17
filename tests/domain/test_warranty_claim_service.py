"""Domain unit tests for Warranty Claim Service (#826, #820)."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import (
    Customer,
    Permission,
    Product,
    Role,
    Sale,
    SaleItem,
    User,
    Warranty,
    WarrantyPolicy,
)
from cbpos.core.services.warranty_claim_receipt_builder import WarrantyClaimReceiptBuilder
from cbpos.core.services.warranty_claim_service import WarrantyClaimService
from cbpos.core.services.warranty_service import WarrantyService


@pytest.fixture
def claim_users(db_session):
    def get_or_create_perm(code):
        p = db_session.query(Permission).filter_by(code=code).first()
        if not p:
            p = Permission(code=code)
            db_session.add(p)
        return p

    p_create = get_or_create_perm(Permissions.WARRANTY_CLAIM_CREATE)
    p_resolve = get_or_create_perm(Permissions.WARRANTY_CLAIM_RESOLVE)
    p_view = get_or_create_perm(Permissions.WARRANTY_VIEW)

    role_mgr = Role(name="ClaimManagerRole", permissions=[p_create, p_resolve, p_view])
    role_cashier = Role(name="ClaimCashierRole", permissions=[p_create, p_view])
    role_none = Role(name="NoClaimRole", permissions=[p_view])

    mgr = User(username="claim_manager", pin_hash="h1", role=role_mgr)
    cashier = User(username="claim_cashier", pin_hash="h2", role=role_cashier)
    unauthorized = User(username="unauth_user", pin_hash="h3", role=role_none)

    db_session.add_all([role_mgr, role_cashier, role_none, mgr, cashier, unauthorized])
    db_session.flush()
    return {"manager": mgr, "cashier": cashier, "unauthorized": unauthorized}


@pytest.fixture
def sample_claim_environment(db_session, claim_users):
    prod = Product(name_en="Laptop Pro 14", price=Decimal("150000.00"), stock_qty=Decimal("5"), barcode="LAP001")
    cust = Customer(name="Kamal Silva", phone="0712345678")
    policy = WarrantyPolicy(
        name="1 Year Comprehensive",
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_ONLY",
        is_active=True,
    )
    db_session.add_all([prod, cust, policy])
    db_session.flush()

    sale = Sale(
        document_number="INV-2026-0001",
        date=datetime.now(),
        type="sale",
        status="COMPLETED",
        user_id=claim_users["cashier"].id,
        customer_id=cust.id,
        payment_method="CASH",
        total_amount=Decimal("150000.00"),
    )
    db_session.add(sale)
    db_session.flush()

    sale_item = SaleItem(
        sale_id=sale.id,
        product=prod,
        qty=Decimal("1.000"),
        unit_price=Decimal("150000.00"),
        subtotal=Decimal("150000.00"),
        original_price=Decimal("150000.00"),
    )
    db_session.add(sale_item)
    db_session.flush()

    w = Warranty(
        code=f"{sale.document_number}-01",
        unit_index=1,
        sale_id=sale.id,
        sale_item_id=sale_item.id,
        product_id=prod.id,
        customer_id=cust.id,
        policy_id=policy.id,
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_ONLY",
        start_date=datetime.now().date(),
        end_date=datetime.now().date() + timedelta(days=365),
        serial_number="LAP-SN-9988",
        status="ACTIVE",
        terms_text="Comprehensive coverage",
        exclusions_text="Water damage",
    )
    db_session.add(w)
    db_session.flush()

    return {"prod": prod, "cust": cust, "policy": policy, "sale": sale, "sale_item": sale_item, "warranty": w}


@pytest.mark.domain
def test_claim_creation_success(db_session, claim_users, sample_claim_environment):
    cashier = claim_users["cashier"]
    w = sample_claim_environment["warranty"]

    claim = WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="Display flickering and vertical lines",
        accessories_received="Power Adapter",
        item_condition="Minor scratches",
        user_id=cashier.id,
        session=db_session,
    )

    assert claim.id is not None
    assert claim.document_number.startswith("WC-")
    assert claim.claim_status == "INTAKE"
    assert claim.is_covered is True
    assert claim.defect_description == "Display flickering and vertical lines"
    assert claim.item_serial == "LAP-SN-9988"
    assert claim.customer_name == "Kamal Silva"
    assert claim.customer_phone == "0712345678"
    assert len(claim.events) == 1
    assert claim.events[0].to_status == "INTAKE"


@pytest.mark.domain
def test_claim_creation_requires_defect(db_session, claim_users, sample_claim_environment):
    cashier = claim_users["cashier"]
    w = sample_claim_environment["warranty"]

    with pytest.raises(ValueError, match="defect_description_required"):
        WarrantyClaimService.create_claim(
            warranty_id=w.id,
            defect_description="   ",
            user_id=cashier.id,
            session=db_session,
        )


@pytest.mark.domain
def test_claim_creation_permission_denied(db_session, claim_users, sample_claim_environment):
    unauth = claim_users["unauthorized"]
    w = sample_claim_environment["warranty"]

    with pytest.raises(PermissionError, match=r"warranty\.claim_create required"):
        WarrantyClaimService.create_claim(
            warranty_id=w.id,
            defect_description="Motherboard failure",
            user_id=unauth.id,
            session=db_session,
        )


@pytest.mark.domain
def test_single_active_claim_invariant(db_session, claim_users, sample_claim_environment):
    cashier = claim_users["cashier"]
    w = sample_claim_environment["warranty"]

    # First claim succeeds
    WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="Battery draining fast",
        user_id=cashier.id,
        session=db_session,
    )

    # Second claim on same warranty while first is active fails
    with pytest.raises(ValueError, match="warranty_already_has_active_claim"):
        WarrantyClaimService.create_claim(
            warranty_id=w.id,
            defect_description="Keyboard keys stuck",
            user_id=cashier.id,
            session=db_session,
        )


@pytest.mark.domain
def test_coverage_auto_detection(db_session, claim_users, sample_claim_environment):
    cashier = claim_users["cashier"]
    w = sample_claim_environment["warranty"]

    # Expire warranty cleanly maintaining start_date <= end_date
    w.start_date = datetime.now().date() - timedelta(days=400)
    w.end_date = datetime.now().date() - timedelta(days=10)
    db_session.flush()

    claim = WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="No power",
        user_id=cashier.id,
        session=db_session,
    )
    assert claim.is_covered is False


@pytest.mark.domain
def test_state_machine_happy_path(db_session, claim_users, sample_claim_environment):
    cashier = claim_users["cashier"]
    mgr = claim_users["manager"]
    w = sample_claim_environment["warranty"]

    claim = WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="Hinge loose",
        user_id=cashier.id,
        session=db_session,
    )
    assert claim.claim_status == "INTAKE"

    # INTAKE -> IN_INSPECTION
    claim = WarrantyClaimService.transition_status(
        claim_id=claim.id,
        to_status="IN_INSPECTION",
        user_id=cashier.id,
        notes="Inspecting hinge bracket",
        session=db_session,
    )
    assert claim.claim_status == "IN_INSPECTION"

    # IN_INSPECTION -> SUPPLIER_DISPATCHED
    claim = WarrantyClaimService.transition_status(
        claim_id=claim.id,
        to_status="SUPPLIER_DISPATCHED",
        user_id=cashier.id,
        notes="Dispatched to authorized service center",
        session=db_session,
    )
    assert claim.claim_status == "SUPPLIER_DISPATCHED"

    # SUPPLIER_DISPATCHED -> SUPPLIER_RETURNED
    claim = WarrantyClaimService.transition_status(
        claim_id=claim.id,
        to_status="SUPPLIER_RETURNED",
        user_id=cashier.id,
        notes="Returned with new hinge assembly",
        session=db_session,
    )
    assert claim.claim_status == "SUPPLIER_RETURNED"

    # SUPPLIER_RETURNED -> RESOLVED
    claim = WarrantyClaimService.resolve_claim(
        claim_id=claim.id,
        resolution="REPAIRED",
        user_id=mgr.id,
        resolution_notes="Hinge replaced under warranty",
        repair_cost=Decimal("4500.00"),
        charge_customer=Decimal("0.00"),
        session=db_session,
    )
    assert claim.claim_status == "RESOLVED"
    assert claim.resolution == "REPAIRED"
    assert claim.repair_cost == Decimal("4500.00")
    assert claim.charge_customer == Decimal("0.00")

    # RESOLVED -> COLLECTED
    claim = WarrantyClaimService.mark_collected(
        claim_id=claim.id,
        collected_by_name="Kamal Silva",
        user_id=cashier.id,
        session=db_session,
    )
    assert claim.claim_status == "COLLECTED"
    assert claim.collected_by_name == "Kamal Silva"
    assert claim.collected_at is not None
    assert len(claim.events) == 6


@pytest.mark.domain
def test_invalid_status_transitions(db_session, claim_users, sample_claim_environment):
    cashier = claim_users["cashier"]
    w = sample_claim_environment["warranty"]

    claim = WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="Overheating",
        user_id=cashier.id,
        session=db_session,
    )

    # Cannot transition directly from INTAKE to COLLECTED
    with pytest.raises(ValueError, match="invalid_transition"):
        WarrantyClaimService.transition_status(
            claim_id=claim.id,
            to_status="COLLECTED",
            user_id=cashier.id,
            session=db_session,
        )


@pytest.mark.domain
def test_rejection_requires_reason(db_session, claim_users, sample_claim_environment):
    mgr = claim_users["manager"]
    cashier = claim_users["cashier"]
    w = sample_claim_environment["warranty"]

    claim = WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="Screen cracked",
        user_id=cashier.id,
        session=db_session,
    )

    # Reject without reason fails
    with pytest.raises(ValueError, match="rejection_reason_required"):
        WarrantyClaimService.reject_claim(
            claim_id=claim.id,
            reason="   ",
            user_id=mgr.id,
            session=db_session,
        )

    # Reject with valid reason succeeds
    rejected = WarrantyClaimService.reject_claim(
        claim_id=claim.id,
        reason="Physical accidental drop damage not covered",
        user_id=mgr.id,
        session=db_session,
    )
    assert rejected.claim_status == "REJECTED"
    assert rejected.rejection_reason == "Physical accidental drop damage not covered"


@pytest.mark.domain
def test_resolution_replaced_same_creates_warranty(db_session, claim_users, sample_claim_environment):
    mgr = claim_users["manager"]
    cashier = claim_users["cashier"]
    w = sample_claim_environment["warranty"]

    claim = WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="Dead on arrival",
        user_id=cashier.id,
        session=db_session,
    )
    WarrantyClaimService.transition_status(claim.id, "IN_INSPECTION", user_id=cashier.id, session=db_session)

    resolved = WarrantyClaimService.resolve_claim(
        claim_id=claim.id,
        resolution="REPLACED_SAME",
        user_id=mgr.id,
        resolution_notes="Unit replaced with fresh stock",
        replacement_serial="LAP-SN-NEW-101",
        session=db_session,
    )

    assert resolved.claim_status == "RESOLVED"
    assert resolved.resolution == "REPLACED_SAME"
    assert resolved.replacement_warranty_id is not None
    assert resolved.replacement_serial == "LAP-SN-NEW-101"

    # Verify old warranty is marked REPLACED
    db_session.refresh(w)
    assert w.status == "REPLACED"

    # Verify replacement warranty exists and is active
    new_w = db_session.get(Warranty, resolved.replacement_warranty_id)
    assert new_w is not None
    assert new_w.status == "ACTIVE"
    assert new_w.serial_number == "LAP-SN-NEW-101"
    assert new_w.replaces_warranty_id == w.id


@pytest.mark.domain
def test_void_claim_workflow(db_session, claim_users, sample_claim_environment):
    mgr = claim_users["manager"]
    cashier = claim_users["cashier"]
    w = sample_claim_environment["warranty"]

    claim = WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="Mistaken entry",
        user_id=cashier.id,
        session=db_session,
    )

    voided = WarrantyClaimService.void_claim(
        claim_id=claim.id,
        reason="Customer brought wrong unit",
        user_id=mgr.id,
        session=db_session,
    )
    assert voided.claim_status == "VOID"

    # Cannot transition a VOID claim
    with pytest.raises(ValueError, match="invalid_transition"):
        WarrantyClaimService.transition_status(
            claim_id=claim.id,
            to_status="IN_INSPECTION",
            user_id=cashier.id,
            session=db_session,
        )


@pytest.mark.domain
def test_void_sale_fails_with_active_claim(db_session, claim_users, sample_claim_environment):
    cashier = claim_users["cashier"]
    sale = sample_claim_environment["sale"]
    w = sample_claim_environment["warranty"]

    # Open a claim on the warranty
    WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="Defective keyboard",
        user_id=cashier.id,
        session=db_session,
    )

    # Attempting to void the sale must fail closed
    with pytest.raises(ValueError, match="cannot_void_sale_with_open_claim"):
        WarrantyService.void_sale_warranties_in_session(
            session=db_session,
            sale_id=sale.id,
            actor_id=cashier.id,
        )


@pytest.mark.domain
def test_refund_guard_with_active_claim(db_session, claim_users, sample_claim_environment):
    cashier = claim_users["cashier"]
    mgr = claim_users["manager"]
    sale_item = sample_claim_environment["sale_item"]
    w = sample_claim_environment["warranty"]

    claim = WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="Trackpad unresponsive",
        user_id=cashier.id,
        session=db_session,
    )

    refund_sale = Sale(
        document_number="REF-2026-0001",
        date=datetime.now(),
        type="refund",
        status="COMPLETED",
        user_id=cashier.id,
        payment_method="CASH",
        total_amount=Decimal("-150000.00"),
    )
    db_session.add(refund_sale)
    db_session.flush()

    # Normal refund without matching resolved claim fails
    with pytest.raises(ValueError, match="cannot_refund_unit_with_open_claim"):
        WarrantyService.cancel_units_for_refund_in_session(
            session=db_session,
            refund_sale=refund_sale,
            refund_lines=[(sale_item.id, Decimal("1.000"))],
            actor_id=cashier.id,
        )

    # Resolve claim with resolution == "REFUNDED"
    WarrantyClaimService.transition_status(claim.id, "IN_INSPECTION", user_id=cashier.id, session=db_session)
    WarrantyClaimService.resolve_claim(
        claim_id=claim.id,
        resolution="REFUNDED",
        user_id=mgr.id,
        resolution_notes="Approved full refund",
        session=db_session,
    )

    # Refund passing claim_id succeeds and marks claim COLLECTED
    cancelled = WarrantyService.cancel_units_for_refund_in_session(
        session=db_session,
        refund_sale=refund_sale,
        refund_lines=[(sale_item.id, Decimal("1.000"))],
        actor_id=cashier.id,
        claim_id=claim.id,
    )
    assert len(cancelled) == 1
    assert cancelled[0].status == "CANCELLED"

    updated_claim = WarrantyClaimService.get_claim(claim.id, session=db_session)
    assert updated_claim.claim_status == "COLLECTED"


@pytest.mark.domain
def test_thermal_slips_generation(db_session, claim_users, sample_claim_environment):
    cashier = claim_users["cashier"]
    w = sample_claim_environment["warranty"]

    claim = WarrantyClaimService.create_claim(
        warranty_id=w.id,
        defect_description="Thermal test defect",
        user_id=cashier.id,
        session=db_session,
    )

    # Intake slip
    intake_cmds = WarrantyClaimReceiptBuilder.build_intake_slip(claim)
    assert any(c.get("type") == "barcode" for c in intake_cmds)
    assert any(c.get("type") == "cut" for c in intake_cmds)
    assert any("INTAKE" in c.get("val", "") for c in intake_cmds)

    # Collection slip
    col_cmds = WarrantyClaimReceiptBuilder.build_collection_slip(claim)
    assert any(c.get("type") == "cut" for c in col_cmds)
    assert any("COLLECTION" in c.get("val", "") for c in col_cmds)
