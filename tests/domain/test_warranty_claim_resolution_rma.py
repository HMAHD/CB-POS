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
    Purchase,
    PurchaseItem,
    Role,
    Sale,
    SaleItem,
    StockMovement,
    Supplier,
    SupplierLedgerEntry,
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
        warranty_policy_id=policy.id,
        warranty_override="POLICY",
    )

    replacement_product = Product(
        name_en="Galaxy Smartphone Replacement Unit",
        barcode="8806091234568",
        price=Decimal("45000.00"),
        cost=Decimal("35000.00"),
        stock_qty=Decimal("5.000"),
        is_active=True,
        default_supplier_id=supplier.id,
        warranty_policy_id=policy.id,
        warranty_override="POLICY",
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


class TestIssue828SupplierRMA:
    """Test suite for Issue #828 Supplier and Manufacturer RMA tracking."""

    def test_send_to_supplier_and_receive(self, db_session, rma_setup):
        """Verify send_to_supplier transitions status and receive_from_supplier returns it."""
        admin = rma_setup["admin"]
        claim_dto = rma_setup["claim_dto"]
        supplier = rma_setup["supplier"]

        # Send to supplier
        dispatched_dto = WarrantyClaimService.send_to_supplier(
            claim_id=claim_dto.id,
            supplier_id=supplier.id,
            user_id=admin.id,
            supplier_rma_ref="RMA-LANKA-9988",
            notes="Sent via Prompt Express courier",
            session=db_session,
        )

        assert dispatched_dto.claim_status == "SUPPLIER_DISPATCHED"
        assert dispatched_dto.defective_unit_status == "SENT_TO_SUPPLIER"
        assert dispatched_dto.supplier_id == supplier.id
        assert dispatched_dto.supplier_name == supplier.company_name
        assert dispatched_dto.supplier_rma_ref == "RMA-LANKA-9988"
        assert dispatched_dto.sent_to_supplier_at is not None

        # Receive back from supplier
        returned_dto = WarrantyClaimService.receive_from_supplier(
            claim_id=claim_dto.id,
            user_id=admin.id,
            to_status="SUPPLIER_RETURNED",
            notes="Courier delivered back to shop",
            session=db_session,
        )

        assert returned_dto.claim_status == "SUPPLIER_RETURNED"
        assert returned_dto.defective_unit_status == "RETURNED_FROM_SUPPLIER"
        assert returned_dto.returned_from_supplier_at is not None

    def test_send_to_supplier_advance_resolution_preserves_status(self, db_session, rma_setup):
        """Verify dispatching defective unit after customer replacement preserves resolved state."""
        admin = rma_setup["admin"]
        claim_dto = rma_setup["claim_dto"]
        rep_prod = rma_setup["replacement_product"]
        supplier = rma_setup["supplier"]

        # Advance replacement to customer
        resolved = WarrantyClaimService.replace_from_stock(
            claim_id=claim_dto.id,
            replacement_product_id=rep_prod.id,
            user_id=admin.id,
            session=db_session,
        )
        assert resolved.claim_status == "RESOLVED"
        assert resolved.defective_unit_status == "HELD"

        # Now dispatch defective unit to supplier
        dispatched = WarrantyClaimService.send_to_supplier(
            claim_id=claim_dto.id,
            supplier_id=supplier.id,
            user_id=admin.id,
            supplier_rma_ref="RMA-ADV-001",
            session=db_session,
        )
        # Customer status stays RESOLVED!
        assert dispatched.claim_status == "RESOLVED"
        assert dispatched.defective_unit_status == "SENT_TO_SUPPLIER"

    def test_supplier_outcome_credit_note_updates_ledger_and_aging(self, db_session, rma_setup):
        """Verify CREDIT_NOTE outcome decrements supplier payable and writes ledger entry."""
        admin = rma_setup["admin"]
        claim_dto = rma_setup["claim_dto"]
        supplier = rma_setup["supplier"]
        initial_payable = supplier.current_payable

        # Dispatch first
        WarrantyClaimService.send_to_supplier(
            claim_id=claim_dto.id,
            supplier_id=supplier.id,
            user_id=admin.id,
            session=db_session,
        )

        # Record supplier credit note of 35000.00
        credit_amt = Decimal("35000.00")
        outcome_dto = WarrantyClaimService.record_supplier_outcome(
            claim_id=claim_dto.id,
            outcome="CREDIT_NOTE",
            user_id=admin.id,
            credit_amount=credit_amt,
            notes="Credit note issued per RMA credit agreement",
            session=db_session,
        )

        assert outcome_dto.supplier_outcome == "CREDIT_NOTE"
        assert outcome_dto.supplier_credit_amount == credit_amt
        assert outcome_dto.defective_unit_status == "SCRAPPED"

        # Verify supplier payable balance decremented
        db_session.refresh(supplier)
        assert supplier.current_payable == initial_payable - credit_amt

        # Verify ledger entry written
        entry = (
            db_session.query(SupplierLedgerEntry)
            .filter_by(supplier_id=supplier.id, reference_id=claim_dto.id, entry_type="CREDIT_NOTE")
            .first()
        )
        assert entry is not None
        assert entry.amount == -credit_amt
        assert entry.balance_after == initial_payable - credit_amt

    def test_supplier_outcome_replacement_restocks_shop_after_advance_replacement(self, db_session, rma_setup):
        """Supplier replacement unit restocks shop inventory when shop gave advance replacement."""
        admin = rma_setup["admin"]
        claim_dto = rma_setup["claim_dto"]
        prod = rma_setup["product"]
        rep_prod = rma_setup["replacement_product"]
        supplier = rma_setup["supplier"]

        # Step 1: Shop gives replacement from shelf
        WarrantyClaimService.replace_from_stock(
            claim_id=claim_dto.id,
            replacement_product_id=rep_prod.id,
            user_id=admin.id,
            session=db_session,
        )

        # Step 2: Send defective unit to supplier
        WarrantyClaimService.send_to_supplier(
            claim_id=claim_dto.id,
            supplier_id=supplier.id,
            user_id=admin.id,
            session=db_session,
        )

        # Step 3: Receive back
        WarrantyClaimService.receive_from_supplier(
            claim_id=claim_dto.id,
            user_id=admin.id,
            session=db_session,
        )

        # Record initial stock of product
        initial_stock = prod.stock_qty

        # Step 4: Record supplier replaced unit
        outcome_dto = WarrantyClaimService.record_supplier_outcome(
            claim_id=claim_dto.id,
            outcome="REPLACED",
            user_id=admin.id,
            replacement_serial="SUPP-REPLACEMENT-SN-001",
            session=db_session,
        )
        assert outcome_dto.supplier_outcome == "REPLACED"

        # Verify product stock incremented by 1 with WARRANTY movement
        db_session.refresh(prod)
        assert prod.stock_qty == initial_stock + Decimal("1.000")

        mv = (
            db_session.query(StockMovement)
            .filter_by(product_id=prod.id, document_id=claim_dto.id, type=MovementType.WARRANTY)
            .order_by(StockMovement.id.desc())
            .first()
        )
        assert mv is not None
        assert mv.qty_change == Decimal("1.000")

    def test_estimate_supplier_coverage(self, db_session, rma_setup):
        """Verify estimate_supplier_coverage calculates validity from latest purchase GRN."""
        admin = rma_setup["admin"]
        supplier = rma_setup["supplier"]
        product = rma_setup["product"]

        # Create a purchase 60 days ago
        purchase = Purchase(
            document_number="GRN-2026-0005",
            date=datetime.now() - timedelta(days=60),
            status="COMPLETED",
            supplier_id=supplier.id,
            user_id=admin.id,
        )
        db_session.add(purchase)
        db_session.flush()

        p_item = PurchaseItem(
            purchase_id=purchase.id,
            product_id=product.id,
            qty_received=Decimal("10.000"),
            unit_cost=Decimal("35000.00"),
        )
        db_session.add(p_item)
        db_session.flush()

        estimate = WarrantyClaimService.estimate_supplier_coverage(
            product_id=product.id,
            supplier_id=supplier.id,
            session=db_session,
        )

        assert estimate["has_estimate"] is True
        assert estimate["supplier_name"] == supplier.company_name
        assert estimate["supplier_cover_months"] == 12
        assert estimate["is_valid"] is True
        assert estimate["days_remaining"] > 290

    def test_supplier_dispatch_receipt_omits_customer_pii(self, rma_setup):
        """Verify thermal RMA dispatch receipt strictly omits customer name and phone."""
        from cbpos.core.services.warranty_claim_receipt_builder import WarrantyClaimReceiptBuilder

        claim_dto = rma_setup["claim_dto"]
        # Ensure customer data exists on DTO
        assert claim_dto.customer_name == "Kamal Jayasuriya"
        assert claim_dto.customer_phone == "0719876543"

        commands = WarrantyClaimReceiptBuilder.build_supplier_dispatch_receipt(claim_dto)
        all_text = " ".join(c.get("val", "") for c in commands if isinstance(c.get("val"), str))

        # PII Check: Customer Name and Phone MUST NOT BE IN TEXT!
        assert "Kamal" not in all_text
        assert "Jayasuriya" not in all_text
        assert "0719876543" not in all_text

        # RMA Information must be in text
        assert claim_dto.document_number in all_text

    def test_supplier_dispatch_pdf_omits_customer_pii(self, tmp_path, rma_setup):
        """Verify vector PDF dispatch waybill strictly omits customer name and phone."""
        from cbpos.core.services.warranty_claim_receipt_builder import WarrantyClaimReceiptBuilder

        claim_dto = rma_setup["claim_dto"]
        pdf_path = str(tmp_path / "supplier_rma.pdf")

        result_path = WarrantyClaimReceiptBuilder.build_supplier_dispatch_pdf(claim_dto, pdf_path)
        assert result_path == pdf_path

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        assert len(pdf_bytes) > 1000
        # Check PII not in PDF raw text stream
        assert b"Kamal" not in pdf_bytes
        assert b"Jayasuriya" not in pdf_bytes
        assert b"0719876543" not in pdf_bytes
