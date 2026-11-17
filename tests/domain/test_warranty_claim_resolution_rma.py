"""Domain unit tests for Warranty Claim Resolution & Supplier RMA (#827, #828, #820)."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import MovementType
from cbpos.core.models import (
    Customer,
    Permission,
    Product,
    Role,
    Sale,
    SaleItem,
    StockMovement,
    Supplier,
    User,
    Warranty,
    WarrantyClaim,
    WarrantyPolicy,
)
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.stock_service import StockService
from cbpos.core.services.warranty_claim_service import WarrantyClaimService


@pytest.fixture
def rma_setup(db_session):
    def get_or_create_perm(code):
        p = db_session.query(Permission).filter_by(code=code).first()
        if not p:
            p = Permission(code=code)
            db_session.add(p)
        return p

    p_create = get_or_create_perm(Permissions.WARRANTY_CLAIM_CREATE)
    p_resolve = get_or_create_perm(Permissions.WARRANTY_CLAIM_RESOLVE)
    p_view = get_or_create_perm(Permissions.WARRANTY_VIEW)
    p_refund = get_or_create_perm(Permissions.SALES_REFUND)
    p_manage_pol = get_or_create_perm(Permissions.WARRANTY_MANAGE_POLICIES)

    role_admin = Role(name="RMAAdminRole", permissions=[p_create, p_resolve, p_view, p_refund, p_manage_pol])
    role_cashier = Role(name="RMACashierRole", permissions=[p_create, p_view])

    admin = User(username="rma_admin", pin_hash="h_admin", role=role_admin)
    cashier = User(username="rma_cashier", pin_hash="h_cashier", role=role_cashier)

    supplier = Supplier(
        company_name="Global Electronics Lanka",
        contact_person="Sunil Perera",
        phone="0771234567",
        current_payable=Decimal("50000.00"),
        is_active=True,
    )

    policy = WarrantyPolicy(
        name="Standard Phone Warranty",
        name_si="සම්මත දුරකථන වගකීම",
        name_ta="நிலையான தொலைபேசி உத்தரவாதம்",
        duration=12,
        duration_unit="MONTHS",
        warranty_type="MANUFACTURER",
        remedy="REPLACE_ONLY",
        supplier_cover_months=12,
        is_active=True,
    )

    db_session.add_all([role_admin, role_cashier, admin, cashier, supplier, policy])
    db_session.flush()

    product = Product(
        name_en="Galaxy Smartphone",
        name_si="Galaxy ස්මාර්ට්ෆෝනය",
        name_ta="Galaxy ஸ்மார்ட்போன்",
        barcode="8806091234567",
        price=Decimal("45000.00"),
        cost=Decimal("35000.00"),
        stock_qty=Decimal("10.000"),
        is_active=True,
        default_supplier_id=supplier.id,
        warranty_policy=policy,
    )

    replacement_product = Product(
        name_en="Galaxy Smartphone Replacement Unit",
        barcode="8806091234568",
        price=Decimal("45000.00"),
        cost=Decimal("35000.00"),
        stock_qty=Decimal("5.000"),
        is_active=True,
        default_supplier_id=supplier.id,
        warranty_policy=policy,
    )

    customer = Customer(
        name="Kamal Jayasuriya",
        phone="0719876543",
    )

    db_session.add_all([product, replacement_product, customer])
    db_session.flush()

    # Create a Sale with 1 unit
    sale = Sale(
        document_number="INV-2026-0001",
        date=datetime.now() - timedelta(days=30),
        total_amount=Decimal("45000.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("45000.00"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=admin.id,
        customer_id=customer.id,
    )
    db_session.add(sale)
    db_session.flush()

    sale_item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("45000.00"),
        original_price=Decimal("45000.00"),
        subtotal=Decimal("45000.00"),
    )
    db_session.add(sale_item)
    db_session.flush()

    # Create Warranty for sold unit
    warranty = Warranty(
        code="INV-2026-0001-01",
        unit_index=1,
        sale_id=sale.id,
        sale_item_id=sale_item.id,
        product_id=product.id,
        customer_id=customer.id,
        policy_id=policy.id,
        warranty_type="MANUFACTURER",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPLACE_ONLY",
        start_date=sale.date.date(),
        end_date=sale.date.date() + timedelta(days=365),
        serial_number="IMEI990011223344",
        status="ACTIVE",
    )
    db_session.add(warranty)
    db_session.flush()

    # Create Claim on warranty
    claim_dto = WarrantyClaimService.create_claim(
        defect_description="Display flickering and touch unresponsive",
        user_id=admin.id,
        warranty_id=warranty.id,
        session=db_session,
    )

    # Transition claim to IN_INSPECTION
    claim_dto = WarrantyClaimService.transition_status(
        claim_id=claim_dto.id,
        to_status="IN_INSPECTION",
        user_id=admin.id,
        session=db_session,
    )

    return {
        "admin": admin,
        "cashier": cashier,
        "supplier": supplier,
        "policy": policy,
        "product": product,
        "replacement_product": replacement_product,
        "customer": customer,
        "sale": sale,
        "sale_item": sale_item,
        "warranty": warranty,
        "claim_dto": claim_dto,
    }


class TestIssue827ClaimReplacement:
    """Test suite for Issue #827 replacement from stock."""

    def test_movement_type_warranty_accepted_by_stock_service(self, db_session, rma_setup):
        """Verify MovementType.WARRANTY is accepted and recorded by StockService."""
        admin = rma_setup["admin"]
        prod = rma_setup["product"]
        initial_stock = prod.stock_qty

        assert hasattr(MovementType, "WARRANTY")
        assert MovementType.WARRANTY == "WARRANTY"

        m = StockService.record_movement(
            product_id=prod.id,
            qty_change=Decimal("-1.000"),
            movement_type=MovementType.WARRANTY,
            user_id=admin.id,
            session=db_session,
        )
        assert m is not None
        assert m.type == MovementType.WARRANTY
        assert prod.stock_qty == initial_stock - Decimal("1.000")

    def test_replace_from_stock_atomic_remaining_term(self, db_session, rma_setup):
        """Verify replace_from_stock creates new warranty, decrements stock, and updates statuses."""
        ConfigService.set("warranty_replacement_term", "REMAINING")
        admin = rma_setup["admin"]
        claim_dto = rma_setup["claim_dto"]
        rep_prod = rma_setup["replacement_product"]
        old_w = rma_setup["warranty"]
        initial_rep_stock = rep_prod.stock_qty

        resolved_dto = WarrantyClaimService.replace_from_stock(
            claim_id=claim_dto.id,
            replacement_product_id=rep_prod.id,
            user_id=admin.id,
            new_serial="IMEI990099887766",
            resolution_notes="Customer provided with new replacement unit from shelf",
            session=db_session,
        )

        assert resolved_dto.claim_status == "RESOLVED"
        assert resolved_dto.resolution in ("REPLACED_SAME", "REPLACED_DIFFERENT")
        assert resolved_dto.defective_unit_status == "HELD"
        assert resolved_dto.replacement_warranty_id is not None
        assert resolved_dto.replacement_serial == "IMEI990099887766"

        # Check replacement product stock decremented with WARRANTY movement
        db_session.refresh(rep_prod)
        assert rep_prod.stock_qty == initial_rep_stock - Decimal("1.000")
        mv = (
            db_session.query(StockMovement)
            .filter_by(product_id=rep_prod.id, document_id=claim_dto.id, type=MovementType.WARRANTY)
            .first()
        )
        assert mv is not None
        assert mv.qty_change == Decimal("-1.000")

        # Check old warranty marked REPLACED
        db_session.refresh(old_w)
        assert old_w.status == "REPLACED"

        # Check new replacement warranty created
        new_w = db_session.get(Warranty, resolved_dto.replacement_warranty_id)
        assert new_w is not None
        assert new_w.replaces_warranty_id == old_w.id
        assert new_w.status == "ACTIVE"
        assert new_w.serial_number == "IMEI990099887766"
        assert new_w.end_date == old_w.end_date

    def test_replace_from_stock_fresh_term(self, db_session, rma_setup):
        """Verify replace_from_stock with FRESH term computes new full duration."""
        ConfigService.set("warranty_replacement_term", "FRESH")
        admin = rma_setup["admin"]
        claim_dto = rma_setup["claim_dto"]
        rep_prod = rma_setup["replacement_product"]

        resolved_dto = WarrantyClaimService.replace_from_stock(
            claim_id=claim_dto.id,
            replacement_product_id=rep_prod.id,
            user_id=admin.id,
            session=db_session,
        )

        new_w = db_session.get(Warranty, resolved_dto.replacement_warranty_id)
        assert new_w is not None
        today = date.today()
        # 12 months from today
        expected_min_end = today + timedelta(days=360)
        assert new_w.end_date >= expected_min_end

    def test_replace_from_stock_insufficient_stock_aborts(self, db_session, rma_setup):
        """Verify replace_from_stock aborts and leaves no partial state when out of stock."""
        admin = rma_setup["admin"]
        claim_dto = rma_setup["claim_dto"]
        rep_prod = rma_setup["replacement_product"]
        rep_prod.stock_qty = Decimal("0.000")
        db_session.flush()

        old_w = rma_setup["warranty"]

        with pytest.raises(ValueError):
            WarrantyClaimService.replace_from_stock(
                claim_id=claim_dto.id,
                replacement_product_id=rep_prod.id,
                user_id=admin.id,
                session=db_session,
            )

        db_session.refresh(old_w)
        assert old_w.status == "ACTIVE"
        claim_model = db_session.get(WarrantyClaim, claim_dto.id)
        assert claim_model.claim_status == "IN_INSPECTION"


class TestIssue827ClaimRefund:
    """Test suite for Issue #827 refund resolution and defective stock neutrality."""

    def test_refund_claim_exact_unit_and_stock_neutrality(self, db_session, rma_setup):
        """Verify refund_claim cancels warranty, creates CN, and neutralizes stock return."""
        admin = rma_setup["admin"]
        claim_dto = rma_setup["claim_dto"]
        product = rma_setup["product"]
        initial_stock = product.stock_qty
        old_w = rma_setup["warranty"]

        claim_res, refund_res = WarrantyClaimService.refund_claim(
            claim_id=claim_dto.id,
            user_id=admin.id,
            reason="Major unrepairable board failure",
            session=db_session,
        )

        assert claim_res.claim_status == "COLLECTED"
        assert claim_res.resolution == "REFUNDED"
        assert claim_res.refund_sale_id == refund_res.refund_sale_id
        assert claim_res.defective_unit_status == "HELD"

        # Check warranty cancelled
        db_session.refresh(old_w)
        assert old_w.status == "CANCELLED"
        assert old_w.cancelled_by_sale_id == refund_res.refund_sale_id

        # Check stock neutrality: initial stock must remain unchanged!
        db_session.refresh(product)
        assert product.stock_qty == initial_stock

        # Verify movements: exactly 1 RETURN (+1) and 1 ADJUSTMENT (-1)
        movements = (
            db_session.query(StockMovement)
            .filter_by(product_id=product.id)
            .order_by(StockMovement.id.desc())
            .limit(2)
            .all()
        )
        types = {m.type for m in movements}
        assert MovementType.RETURN in types
        assert MovementType.ADJUSTMENT in types

    def test_refund_claim_unauthorized_fails(self, db_session, rma_setup):
        """Cashier without claim resolve permission cannot refund claim."""
        cashier = rma_setup["cashier"]
        claim_dto = rma_setup["claim_dto"]

        with pytest.raises(PermissionError):
            WarrantyClaimService.refund_claim(
                claim_id=claim_dto.id,
                user_id=cashier.id,
                session=db_session,
            )
