"""Tests for warranty reports, dashboard alerts, and reminders (#830).

Verifies:
1. Category and report registration in ReportRegistry.
2. Dual-permission gating on report execution and discovery.
3. Hand-computed fixtures for Active Warranties, Expiring Warranties,
   Claims Register, Claims by Product/Supplier (Claim Rate %), and Claim Cost.
4. Visibility of unknown replacement cost snapshots as '-' (never 0.00 or current cost).
5. Exact count parity between WarrantyClaimService.get_claims_summary() and list_claims().
6. SchedulerService overdue reminders derivation and daily deduplication.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import (
    Category,
    Customer,
    Permission,
    Product,
    Role,
    Sale,
    SaleItem,
    Supplier,
    User,
    Warranty,
    WarrantyClaim,
    WarrantyPolicy,
)
from cbpos.core.reports import register_all_reports
from cbpos.core.reports.base_report import (
    CATEGORY_ORDER,
    CATEGORY_WARRANTY,
    DATE,
    INT,
    MONEY,
    PERCENT,
    QTY,
    TEXT,
)
from cbpos.core.reports.definitions.warranty_reports import (
    ActiveWarrantiesReport,
    ClaimCostReport,
    ClaimsByProductSupplierReport,
    ClaimsRegisterReport,
    ExpiringWarrantiesReport,
)
from cbpos.core.reports.registry import ReportRegistry
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.report_service import ReportService
from cbpos.core.services.scheduler_service import SchedulerService
from cbpos.core.services.warranty_claim_service import WarrantyClaimService


@pytest.fixture(autouse=True)
def _reset_registry():
    """Ensure report registry has standard reports registered."""
    register_all_reports()


def _create_user_with_permissions(session: Session, username: str, permissions: list[str]) -> User:
    """Helper to create a user and assign role permissions."""
    perm_objs = []
    for code in permissions:
        p = session.query(Permission).filter_by(code=code).first()
        if not p:
            p = Permission(code=code, description=code)
            session.add(p)
            session.flush()
        perm_objs.append(p)

    role = Role(name=f"role_{username}", permissions=perm_objs)
    session.add(role)
    session.flush()

    user = User(
        username=username,
        pin_hash="dummy_hash",
        role_id=role.id,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _get_default_user(session: Session) -> User:
    """Get or create default user for document FK user_id."""
    u = session.query(User).filter_by(username="test_admin").first()
    if not u:
        u = _create_user_with_permissions(
            session, "test_admin", [Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW]
        )
    return u


def test_warranty_reports_registration_and_hints(db_session: Session):
    """Verify CATEGORY_WARRANTY is in CATEGORY_ORDER and all 5 reports are registered."""
    assert CATEGORY_WARRANTY in CATEGORY_ORDER

    registry = ReportRegistry()
    active_rep = registry.get("warranty_active")
    expiring_rep = registry.get("warranty_expiring")
    claims_reg = registry.get("warranty_claims_register")
    claims_rate = registry.get("warranty_claims_by_product_supplier")
    claim_cost = registry.get("warranty_claim_cost")

    assert active_rep is not None
    assert expiring_rep is not None
    assert claims_reg is not None
    assert claims_rate is not None
    assert claim_cost is not None

    for rep in (active_rep, expiring_rep, claims_reg, claims_rate, claim_cost):
        assert rep.category == CATEGORY_WARRANTY

    # Verify column render hints
    active_hints = active_rep.get_render_hints()["columns"]
    assert active_hints["Warranty Code"]["type"] == TEXT
    assert active_hints["Plan Revenue"]["type"] == MONEY
    assert active_hints["Valid Until"]["type"] == DATE

    expiring_hints = expiring_rep.get_render_hints()["columns"]
    assert expiring_hints["Days Remaining"]["type"] == INT

    rate_hints = claims_rate.get_render_hints()["columns"]
    assert rate_hints["Net Units Sold"]["type"] == QTY
    assert rate_hints["Claim Rate"]["type"] == PERCENT

    cost_hints = claim_cost.get_render_hints()["columns"]
    assert cost_hints["Repair Cost"]["type"] == MONEY
    assert cost_hints["Replacement Cost"]["type"] == TEXT
    assert cost_hints["Net Cost"]["type"] == TEXT


def test_warranty_reports_dual_permissions(db_session: Session):
    """Verify reporting permissions seam: sales reports require sales+warranty, cost requires profit+warranty."""
    user_sales_only = _create_user_with_permissions(db_session, "sales_only", [Permissions.REPORTS_VIEW_SALES])
    user_warranty_only = _create_user_with_permissions(db_session, "warranty_only", [Permissions.WARRANTY_VIEW])
    user_sales_warranty = _create_user_with_permissions(
        db_session, "sales_warranty", [Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW]
    )
    user_all_warranty = _create_user_with_permissions(
        db_session,
        "all_warranty",
        [Permissions.REPORTS_VIEW_SALES, Permissions.REPORTS_VIEW_PROFIT, Permissions.WARRANTY_VIEW],
    )

    # 1. Available reports list
    reports_sales_only = ReportService.get_reports_for_user(user_sales_only)
    warranty_ids_sales_only = {r.id for r in reports_sales_only if r.category == CATEGORY_WARRANTY}
    assert len(warranty_ids_sales_only) == 0

    reports_warranty_only = ReportService.get_reports_for_user(user_warranty_only)
    warranty_ids_warranty_only = {r.id for r in reports_warranty_only if r.category == CATEGORY_WARRANTY}
    assert len(warranty_ids_warranty_only) == 0

    reports_sales_w = ReportService.get_reports_for_user(user_sales_warranty)
    warranty_ids_sales_w = {r.id for r in reports_sales_w if r.category == CATEGORY_WARRANTY}
    assert warranty_ids_sales_w == {
        "warranty_active",
        "warranty_expiring",
        "warranty_claims_register",
        "warranty_claims_by_product_supplier",
    }
    assert "warranty_claim_cost" not in warranty_ids_sales_w

    reports_all = ReportService.get_reports_for_user(user_all_warranty)
    warranty_ids_all = {r.id for r in reports_all if r.category == CATEGORY_WARRANTY}
    assert warranty_ids_all == {
        "warranty_active",
        "warranty_expiring",
        "warranty_claims_register",
        "warranty_claims_by_product_supplier",
        "warranty_claim_cost",
    }

    # 2. Execution gating
    with pytest.raises(PermissionError):
        ReportService.run("warranty_active", {}, user=user_sales_only)

    with pytest.raises(PermissionError):
        ReportService.run("warranty_claim_cost", {}, user=user_sales_warranty)

    df_ok = ReportService.run("warranty_active", {}, user=user_sales_warranty)
    assert df_ok is not None


def test_active_and_expiring_warranties_reports(db_session: Session):
    """Test ActiveWarrantiesReport and ExpiringWarrantiesReport with derived statuses and plan revenue."""
    today = date.today()
    user = _get_default_user(db_session)

    cat = Category(name="Electronics")
    db_session.add(cat)
    db_session.flush()

    prod = Product(name_en="Phone A", barcode="BAR-PH-A", price=Decimal("100000.00"), category_id=cat.id)
    plan_prod = Product(
        name_en="Care Plan 1Y",
        barcode="BAR-CARE-1Y",
        price=Decimal("5000.00"),
        is_warranty_plan=True,
    )
    cust = Customer(name="Amara Silva", phone="0771234567")
    db_session.add_all([prod, plan_prod, cust])
    db_session.flush()

    policy_base = WarrantyPolicy(
        name="1Y Base", duration=12, duration_unit="MONTHS", warranty_type="SHOP", remedy="REPAIR_OR_REPLACE"
    )
    policy_ext = WarrantyPolicy(
        name="1Y Ext",
        duration=12,
        duration_unit="MONTHS",
        warranty_type="EXTENDED",
        remedy="REPAIR_OR_REPLACE",
        extended_starts="AFTER_BASE",
    )
    db_session.add_all([policy_base, policy_ext])
    db_session.flush()

    # Sale with base item and plan item
    sale = Sale(
        document_number="SAL-830-01",
        date=datetime.now(),
        status=DocumentStatus.COMPLETED,
        user_id=user.id,
        total_amount=Decimal("105000.00"),
        payment_method="CASH",
    )
    db_session.add(sale)
    db_session.flush()

    item_base = SaleItem(
        sale_id=sale.id,
        product_id=prod.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("100000.00"),
        original_price=Decimal("100000.00"),
        subtotal=Decimal("100000.00"),
    )
    item_plan = SaleItem(
        sale_id=sale.id,
        product_id=plan_prod.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("5000.00"),
        original_price=Decimal("5000.00"),
        subtotal=Decimal("5000.00"),
    )
    db_session.add_all([item_base, item_plan])
    db_session.flush()

    # Base warranty (expires in 10 days -> EXPIRING)
    w_base = Warranty(
        code="SAL-830-01-01",
        sale_id=sale.id,
        sale_item_id=item_base.id,
        product_id=prod.id,
        customer_id=cust.id,
        policy_id=policy_base.id,
        serial_number="IMEI-001",
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        start_date=today - timedelta(days=355),
        end_date=today + timedelta(days=10),
        status="ACTIVE",
    )
    # Extended warranty (valid until next year -> ACTIVE, linked to plan sale item)
    w_ext = Warranty(
        code="SAL-830-01-01E",
        sale_id=sale.id,
        sale_item_id=item_base.id,
        plan_sale_item_id=item_plan.id,
        product_id=prod.id,
        customer_id=cust.id,
        policy_id=policy_ext.id,
        serial_number="IMEI-001",
        warranty_type="EXTENDED",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        start_date=today + timedelta(days=11),
        end_date=today + timedelta(days=375),
        status="ACTIVE",
    )
    # Expired warranty (ended 30 days ago)
    w_old = Warranty(
        code="SAL-830-OLD-01",
        sale_id=sale.id,
        sale_item_id=item_base.id,
        product_id=prod.id,
        customer_id=cust.id,
        policy_id=policy_base.id,
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        start_date=today - timedelta(days=400),
        end_date=today - timedelta(days=30),
        status="ACTIVE",  # not yet updated in DB, must derive EXPIRED
    )
    # Voided warranty
    w_void = Warranty(
        code="SAL-830-VOID-01",
        sale_id=sale.id,
        sale_item_id=item_base.id,
        product_id=prod.id,
        customer_id=cust.id,
        policy_id=policy_base.id,
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        start_date=today - timedelta(days=50),
        end_date=today + timedelta(days=300),
        status="VOID",
    )
    db_session.add_all([w_base, w_ext, w_old, w_void])
    db_session.commit()

    # 1. ActiveWarrantiesReport
    active_rep = ActiveWarrantiesReport()

    # Filter: ALL
    df_all = active_rep.generate({"status": "ALL"})
    codes_all = set(df_all["Warranty Code"].tolist())
    assert "SAL-830-01-01" in codes_all
    assert "SAL-830-01-01E" in codes_all
    assert "SAL-830-OLD-01" in codes_all
    assert "SAL-830-VOID-01" in codes_all

    # Check Plan Revenue column
    row_ext = df_all[df_all["Warranty Code"] == "SAL-830-01-01E"].iloc[0]
    assert row_ext["Plan Revenue"] == Decimal("5000.00")
    row_base = df_all[df_all["Warranty Code"] == "SAL-830-01-01"].iloc[0]
    assert row_base["Plan Revenue"] == Decimal("0.00")

    # Filter: ACTIVE (must include active & expiring, exclude expired & void)
    df_active = active_rep.generate({"status": "ACTIVE"})
    codes_active = set(df_active["Warranty Code"].tolist())
    assert "SAL-830-01-01" in codes_active  # expiring in 10 days is currently active
    assert "SAL-830-01-01E" in codes_active
    assert "SAL-830-OLD-01" not in codes_active
    assert "SAL-830-VOID-01" not in codes_active

    # Filter: EXPIRED
    df_expired = active_rep.generate({"status": "EXPIRED"})
    codes_expired = set(df_expired["Warranty Code"].tolist())
    assert "SAL-830-OLD-01" in codes_expired
    assert "SAL-830-01-01" not in codes_expired

    # 2. ExpiringWarrantiesReport
    expiring_rep = ExpiringWarrantiesReport()
    df_exp_14 = expiring_rep.generate({"days_ahead": 14})
    codes_exp = set(df_exp_14["Warranty Code"].tolist())
    assert "SAL-830-01-01" in codes_exp
    assert "SAL-830-01-01E" not in codes_exp  # expires in 375 days
    assert "SAL-830-OLD-01" not in codes_exp  # already expired

    row_exp = df_exp_14[df_exp_14["Warranty Code"] == "SAL-830-01-01"].iloc[0]
    assert row_exp["Days Remaining"] == 10
    assert row_exp["Customer"] == "Amara Silva"
    assert row_exp["Phone"] == "0771234567"


def test_claims_register_and_cost_hand_computed_fixture(db_session: Session):
    """Test ClaimsRegisterReport and ClaimCostReport with exact hand-computed values.

    Specifically verifies that unknown replacement_cost_snapshot renders as '-'
    and net cost renders as '-', never 0 or current product cost.
    """
    today = date.today()
    user = _get_default_user(db_session)

    cat = Category(name="Appliances")
    supp = Supplier(company_name="Apex Importers")
    cust = Customer(name="Bimal Perera", phone="0719876543")
    prod = Product(
        name_en="Blender 500W",
        barcode="BAR-BLD-500",
        price=Decimal("15000.00"),
        cost=Decimal("9000.00"),
        default_supplier_id=supp.id,
        category=cat,
    )
    db_session.add_all([cat, supp, cust, prod])
    db_session.flush()

    policy = WarrantyPolicy(
        name="Shop Warranty", duration=12, duration_unit="MONTHS", warranty_type="SHOP", remedy="REPAIR_OR_REPLACE"
    )
    db_session.add(policy)
    db_session.flush()

    sale = Sale(
        document_number="SAL-830-BLD",
        date=datetime.now() - timedelta(days=60),
        status=DocumentStatus.COMPLETED,
        user_id=user.id,
        total_amount=Decimal("15000.00"),
        payment_method="CASH",
    )
    db_session.add(sale)
    db_session.flush()

    item = SaleItem(
        sale_id=sale.id,
        product_id=prod.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("15000.00"),
        original_price=Decimal("15000.00"),
        subtotal=Decimal("15000.00"),
    )
    db_session.add(item)
    db_session.flush()

    w1 = Warranty(
        code="SAL-830-BLD-01",
        sale_id=sale.id,
        sale_item_id=item.id,
        product_id=prod.id,
        customer_id=cust.id,
        policy_id=policy.id,
        serial_number="BLD-SN-101",
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        start_date=today - timedelta(days=60),
        end_date=today + timedelta(days=300),
        status="ACTIVE",
    )
    w2 = Warranty(
        code="SAL-830-BLD-02",
        sale_id=sale.id,
        sale_item_id=item.id,
        product_id=prod.id,
        customer_id=cust.id,
        policy_id=policy.id,
        serial_number="BLD-SN-102",
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        start_date=today - timedelta(days=60),
        end_date=today + timedelta(days=300),
        status="ACTIVE",
    )
    w3 = Warranty(
        code="SAL-830-BLD-03",
        sale_id=sale.id,
        sale_item_id=item.id,
        product_id=prod.id,
        customer_id=cust.id,
        policy_id=policy.id,
        serial_number="BLD-SN-103",
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        start_date=today - timedelta(days=60),
        end_date=today + timedelta(days=300),
        status="ACTIVE",
    )
    db_session.add_all([w1, w2, w3])
    db_session.flush()

    # Claim 1: Replaced from stock with known snapshot cost = 9000.00
    # Repair cost = 1500.00, Customer charge = 500.00, Supplier credit = 6000.00
    # Hand-computed Net Cost: 9000 + 1500 - 500 - 6000 = 4000.00
    c1 = WarrantyClaim(
        document_number="WC-830-001",
        warranty_id=w1.id,
        product_id=prod.id,
        customer_id=cust.id,
        customer_name_snapshot="Bimal Perera",
        customer_phone_snapshot="0719876543",
        supplier_id=supp.id,
        user_id=user.id,
        intake_date=datetime.now() - timedelta(days=5),
        expected_ready_date=today + timedelta(days=2),
        defect_description="Motor smoking",
        claim_status="RESOLVED",
        resolution="REPLACED_SAME",
        resolved_at=datetime.now() - timedelta(days=1),
        replacement_cost_snapshot=Decimal("9000.00"),
        repair_cost=Decimal("1500.00"),
        charge_customer=Decimal("500.00"),
        supplier_credit_amount=Decimal("6000.00"),
    )

    # Claim 2: Replaced from stock with UNKNOWN snapshot cost (None)
    # Repair cost = 500.00. Hand-computed Net Cost must be '-' (unknown)
    c2 = WarrantyClaim(
        document_number="WC-830-002",
        warranty_id=w2.id,
        product_id=prod.id,
        customer_id=cust.id,
        supplier_id=supp.id,
        user_id=user.id,
        intake_date=datetime.now() - timedelta(days=4),
        expected_ready_date=today - timedelta(days=1),  # OVERDUE!
        defect_description="Blade broken",
        claim_status="RESOLVED",
        resolution="REPLACED_DIFFERENT",
        resolved_at=datetime.now(),
        replacement_cost_snapshot=None,  # unknown historical cost
        repair_cost=Decimal("500.00"),
        charge_customer=Decimal("0.00"),
        supplier_credit_amount=Decimal("0.00"),
    )

    # Claim 3: Open claim in INTAKE
    c3 = WarrantyClaim(
        document_number="WC-830-003",
        warranty_id=w3.id,
        product_id=prod.id,
        customer_id=cust.id,
        supplier_id=supp.id,
        user_id=user.id,
        intake_date=datetime.now() - timedelta(days=2),
        expected_ready_date=today + timedelta(days=5),
        defect_description="Button jammed",
        claim_status="INTAKE",
    )

    db_session.add_all([c1, c2, c3])
    db_session.commit()

    # 1. ClaimsRegisterReport
    reg_rep = ClaimsRegisterReport()
    df_reg = reg_rep.generate({})
    assert len(df_reg) == 3
    claim_nums = set(df_reg["Claim Number"].tolist())
    assert {"WC-830-001", "WC-830-002", "WC-830-003"}.issubset(claim_nums)

    row_c1 = df_reg[df_reg["Claim Number"] == "WC-830-001"].iloc[0]
    assert row_c1["Status"] == "RESOLVED"
    assert row_c1["Resolution"] == "REPLACED_SAME"
    assert row_c1["Days Open"] == 4  # intake 5 days ago, resolved 1 day ago

    # 2. ClaimCostReport
    cost_rep = ClaimCostReport()
    df_cost = cost_rep.generate({})
    assert len(df_cost) == 2  # c1 and c2 are resolved

    row_cost1 = df_cost[df_cost["Claim Number"] == "WC-830-001"].iloc[0]
    assert row_cost1["Replacement Cost"] == "9,000.00"
    assert row_cost1["Repair Cost"] == Decimal("1500.00")
    assert row_cost1["Customer Charge"] == Decimal("500.00")
    assert row_cost1["Supplier Credit"] == Decimal("6000.00")
    assert row_cost1["Net Cost"] == "4,000.00"

    row_cost2 = df_cost[df_cost["Claim Number"] == "WC-830-002"].iloc[0]
    assert row_cost2["Replacement Cost"] == "-"
    assert row_cost2["Net Cost"] == "-"  # visibly unknown, never 0.00 or current cost!


def test_claims_by_product_supplier_claim_rate_hand_computed(db_session: Session):
    """Test ClaimsByProductSupplierReport with exact hand-computed Claim Rate %.

    Fixture:
    - Product A: 10 sold, 2 refunded -> Net units sold = 8.
                 2 claims filed (1 replacement, 1 rejection).
                 Turnaround: 4 days.
                 Claim Rate = 2 / 8 * 100 = 25.00%.
    - Product B: 4 sold, 4 refunded -> Net units sold = 0.
                 1 claim filed.
                 Claim Rate = 0.00% (safe against zero division).
    """
    now = datetime.now()
    start_dt = now - timedelta(days=10)
    end_dt = now + timedelta(days=1)
    user = _get_default_user(db_session)

    supp = Supplier(company_name="Tech Distributors")
    cat = Category(name="Gadgets")
    db_session.add_all([supp, cat])
    db_session.flush()

    p_a = Product(
        name_en="Gadget A", barcode="BAR-GA", price=Decimal("1000.00"), default_supplier_id=supp.id, category_id=cat.id
    )
    p_b = Product(
        name_en="Gadget B", barcode="BAR-GB", price=Decimal("2000.00"), default_supplier_id=supp.id, category_id=cat.id
    )
    db_session.add_all([p_a, p_b])
    db_session.flush()

    # Sale for Product A: 10 units
    sale_a = Sale(
        document_number="SAL-GA-01",
        date=now - timedelta(days=5),
        status=DocumentStatus.COMPLETED,
        user_id=user.id,
        total_amount=Decimal("10000.00"),
        payment_method="CASH",
    )
    db_session.add(sale_a)
    db_session.flush()
    item_a = SaleItem(
        sale_id=sale_a.id,
        product_id=p_a.id,
        qty=Decimal("10.000"),
        unit_price=Decimal("1000.00"),
        original_price=Decimal("1000.00"),
        subtotal=Decimal("10000.00"),
    )
    db_session.add(item_a)

    # Refund for Product A: 2 units
    ref_a = Sale(
        document_number="REF-GA-01",
        date=now - timedelta(days=3),
        status=DocumentStatus.COMPLETED,
        refund_of_sale_id=sale_a.id,
        payment_method="REFUND",
        total_amount=Decimal("2000.00"),
        user_id=user.id,
    )
    db_session.add(ref_a)
    db_session.flush()
    item_ref_a = SaleItem(
        sale_id=ref_a.id,
        product_id=p_a.id,
        qty=Decimal("2.000"),
        unit_price=Decimal("1000.00"),
        original_price=Decimal("1000.00"),
        subtotal=Decimal("2000.00"),
    )
    db_session.add(item_ref_a)

    # Sale for Product B: 4 units
    sale_b = Sale(
        document_number="SAL-GB-01",
        date=now - timedelta(days=4),
        status=DocumentStatus.COMPLETED,
        user_id=user.id,
        total_amount=Decimal("8000.00"),
        payment_method="CASH",
    )
    db_session.add(sale_b)
    db_session.flush()
    item_b = SaleItem(
        sale_id=sale_b.id,
        product_id=p_b.id,
        qty=Decimal("4.000"),
        unit_price=Decimal("2000.00"),
        original_price=Decimal("2000.00"),
        subtotal=Decimal("8000.00"),
    )
    db_session.add(item_b)

    # Full refund for Product B: 4 units
    ref_b = Sale(
        document_number="REF-GB-01",
        date=now - timedelta(days=2),
        status=DocumentStatus.COMPLETED,
        refund_of_sale_id=sale_b.id,
        payment_method="REFUND",
        total_amount=Decimal("8000.00"),
        user_id=user.id,
    )
    db_session.add(ref_b)
    db_session.flush()
    item_ref_b = SaleItem(
        sale_id=ref_b.id,
        product_id=p_b.id,
        qty=Decimal("4.000"),
        unit_price=Decimal("2000.00"),
        original_price=Decimal("2000.00"),
        subtotal=Decimal("8000.00"),
    )
    db_session.add(item_ref_b)

    # Claims for Product A
    c_a1 = WarrantyClaim(
        document_number="WC-RATE-01",
        product_id=p_a.id,
        supplier_id=supp.id,
        user_id=user.id,
        intake_date=now - timedelta(days=5),
        defect_description="Broken port",
        claim_status="RESOLVED",
        resolution="REPLACED_SAME",
        resolved_at=now - timedelta(days=1),  # turnaround 4 days
    )
    c_a2 = WarrantyClaim(
        document_number="WC-RATE-02",
        product_id=p_a.id,
        supplier_id=supp.id,
        user_id=user.id,
        intake_date=now - timedelta(days=4),
        defect_description="Water damage",
        claim_status="REJECTED",
        resolution="REJECTED_UNCOVERED",
    )

    # Claim for Product B
    c_b1 = WarrantyClaim(
        document_number="WC-RATE-03",
        product_id=p_b.id,
        supplier_id=supp.id,
        user_id=user.id,
        intake_date=now - timedelta(days=3),
        defect_description="No power",
        claim_status="INTAKE",
    )

    db_session.add_all([c_a1, c_a2, c_b1])
    db_session.commit()

    report = ClaimsByProductSupplierReport()

    # 1. Group by Product
    df_prod = report.generate(
        {
            "group_by": "product",
            "date_range": {"start": start_dt.strftime("%Y-%m-%d"), "end": end_dt.strftime("%Y-%m-%d")},
        }
    )
    assert len(df_prod) >= 2
    row_a = df_prod[df_prod["Name"] == "Gadget A"].iloc[0]
    assert row_a["Net Units Sold"] == Decimal("8.000")
    assert row_a["Total Claims"] == 2
    assert row_a["Replacements"] == 1
    assert row_a["Rejections"] == 1
    assert row_a["Claim Rate"] == "25.00%"
    assert row_a["Avg Turnaround Days"] == 4

    row_b = df_prod[df_prod["Name"] == "Gadget B"].iloc[0]
    assert row_b["Net Units Sold"] == Decimal("0.000")
    assert row_b["Total Claims"] == 1
    assert row_b["Claim Rate"] == "0.00%"

    # 2. Group by Supplier
    df_supp = report.generate(
        {
            "group_by": "supplier",
            "date_range": {"start": start_dt.strftime("%Y-%m-%d"), "end": end_dt.strftime("%Y-%m-%d")},
        }
    )
    row_supp = df_supp[df_supp["Name"] == "Tech Distributors"].iloc[0]
    # Total net units = 8 + 0 = 8. Total claims = 2 + 1 = 3.
    # Claim rate = 3 / 8 * 100 = 37.50%
    assert row_supp["Net Units Sold"] == Decimal("8.000")
    assert row_supp["Total Claims"] == 3
    assert row_supp["Claim Rate"] == "37.50%"


def test_dashboard_tile_and_claims_board_count_parity(db_session: Session):
    """Verify exact count parity between WarrantyClaimService.get_claims_summary() and list_claims()."""
    now = datetime.now()
    user = _get_default_user(db_session)

    prod = Product(name_en="Widget X", barcode="BAR-WX", price=Decimal("500.00"))
    db_session.add(prod)
    db_session.flush()

    # 3 Open claims: INTAKE, IN_INSPECTION, SUPPLIER_DISPATCHED
    c_open1 = WarrantyClaim(
        document_number="WC-PAR-01",
        product_id=prod.id,
        user_id=user.id,
        intake_date=now - timedelta(days=2),
        defect_description="Open defect 1",
        claim_status="INTAKE",
    )
    c_open2 = WarrantyClaim(
        document_number="WC-PAR-02",
        product_id=prod.id,
        user_id=user.id,
        intake_date=now - timedelta(days=3),
        defect_description="Open defect 2",
        claim_status="IN_INSPECTION",
    )
    c_open3 = WarrantyClaim(
        document_number="WC-PAR-03",
        product_id=prod.id,
        user_id=user.id,
        intake_date=now - timedelta(days=20),
        defect_description="Open defect 3",
        claim_status="SUPPLIER_DISPATCHED",
        defective_unit_status="SENT_TO_SUPPLIER",
        sent_to_supplier_at=now - timedelta(days=16),  # > 14 days overdue!
    )

    # 2 Ready for pickup: RESOLVED
    c_res1 = WarrantyClaim(
        document_number="WC-PAR-04",
        product_id=prod.id,
        user_id=user.id,
        intake_date=now - timedelta(days=5),
        defect_description="Ready defect 1",
        claim_status="RESOLVED",
        resolution="REPAIRED",
    )
    c_res2 = WarrantyClaim(
        document_number="WC-PAR-05",
        product_id=prod.id,
        user_id=user.id,
        intake_date=now - timedelta(days=6),
        defect_description="Ready defect 2",
        claim_status="RESOLVED",
        resolution="REPLACED_SAME",
    )

    # 1 Closed claim: COLLECTED
    c_col = WarrantyClaim(
        document_number="WC-PAR-06",
        product_id=prod.id,
        user_id=user.id,
        intake_date=now - timedelta(days=10),
        defect_description="Closed defect",
        claim_status="COLLECTED",
        resolution="REPAIRED",
    )

    db_session.add_all([c_open1, c_open2, c_open3, c_res1, c_res2, c_col])
    db_session.commit()

    summary = WarrantyClaimService.get_claims_summary(session=db_session, supplier_threshold_days=14)

    open_board_claims = WarrantyClaimService.list_claims(status="OPEN", session=db_session)
    resolved_board_claims = WarrantyClaimService.list_claims(status="RESOLVED", session=db_session)
    overdue_board_claims = WarrantyClaimService.list_claims(status="OVERDUE_SUPPLIER", session=db_session)

    assert summary["open_claims"] == len(open_board_claims) == 3
    assert summary["ready_for_pickup"] == len(resolved_board_claims) == 2
    assert summary["overdue_supplier"] == len(overdue_board_claims) == 1


def test_scheduler_reminders_derivation_and_deduplication(db_session: Session):
    """Verify SchedulerService daily warranty reminders derivation and deduplication."""
    today = date.today()
    now = datetime.now()
    user = _get_default_user(db_session)

    prod = Product(name_en="Gadget Y", barcode="BAR-GY", price=Decimal("1500.00"))
    supp = Supplier(company_name="Mega Supplies")
    cust = Customer(name="Sunil Fernando", phone="0779998888")
    db_session.add_all([prod, supp, cust])
    db_session.flush()

    # Overdue claim (expected_ready_date was 2 days ago, still open)
    c_overdue = WarrantyClaim(
        document_number="WC-SCHED-01",
        product_id=prod.id,
        customer_id=cust.id,
        user_id=user.id,
        customer_name_snapshot="Sunil Fernando",
        customer_phone_snapshot="0779998888",
        intake_date=now - timedelta(days=7),
        expected_ready_date=today - timedelta(days=2),
        defect_description="Overdue defect",
        claim_status="INTAKE",
    )
    # On-time open claim (expected_ready_date in 3 days)
    c_ontime = WarrantyClaim(
        document_number="WC-SCHED-02",
        product_id=prod.id,
        user_id=user.id,
        intake_date=now - timedelta(days=1),
        expected_ready_date=today + timedelta(days=3),
        defect_description="On-time defect",
        claim_status="INTAKE",
    )
    # Overdue RMA (> 14 days at supplier)
    c_rma = WarrantyClaim(
        document_number="WC-SCHED-03",
        product_id=prod.id,
        supplier_id=supp.id,
        user_id=user.id,
        intake_date=now - timedelta(days=25),
        defect_description="RMA defect",
        claim_status="SUPPLIER_DISPATCHED",
        defective_unit_status="SENT_TO_SUPPLIER",
        sent_to_supplier_at=now - timedelta(days=18),
    )

    db_session.add_all([c_overdue, c_ontime, c_rma])
    db_session.commit()

    overdue_summary = WarrantyClaimService.get_overdue_claims_summary(session=db_session, supplier_threshold_days=14)
    assert overdue_summary["overdue_claims_count"] == 1
    assert overdue_summary["overdue_claims"][0]["document_number"] == "WC-SCHED-01"
    assert overdue_summary["overdue_claims"][0]["phone"] == "0779998888"

    assert overdue_summary["overdue_rmas_count"] == 1
    assert overdue_summary["overdue_rmas"][0]["document_number"] == "WC-SCHED-03"

    # Reset last run config
    ConfigService.set("warranty_reminders_last_run", "")

    # Execute scheduler check
    SchedulerService.check_automation()

    today_str = today.strftime("%Y-%m-%d")
    assert ConfigService.get("warranty_reminders_last_run") == today_str

    # Second check on same day should skip without errors (deduplicated)
    SchedulerService.check_automation()
    assert ConfigService.get("warranty_reminders_last_run") == today_str
