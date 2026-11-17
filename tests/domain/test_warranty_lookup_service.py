"""Unit regression tests for Warranty Lookup & Admin Correction (#825)."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.constants.audit import WARRANTY_EVENT
from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import (
    AuditLog,
    Customer,
    Permission,
    Product,
    Role,
    Sale,
    SaleItem,
    User,
    Warranty,
)
from cbpos.core.services.warranty_dto import WarrantyDTO
from cbpos.core.services.warranty_service import WarrantyService


@pytest.fixture
def edit_user(db_session):
    perm_edit = db_session.query(Permission).filter_by(code=Permissions.WARRANTY_EDIT).first()
    if not perm_edit:
        perm_edit = Permission(code=Permissions.WARRANTY_EDIT)
        db_session.add(perm_edit)
    perm_view = db_session.query(Permission).filter_by(code=Permissions.WARRANTY_VIEW).first()
    if not perm_view:
        perm_view = Permission(code=Permissions.WARRANTY_VIEW)
        db_session.add(perm_view)
    role = Role(name="WarrantyEditorRole", permissions=[perm_edit, perm_view])
    user = User(username="warranty_editor", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def view_only_user(db_session):
    perm_view = db_session.query(Permission).filter_by(code=Permissions.WARRANTY_VIEW).first()
    if not perm_view:
        perm_view = Permission(code=Permissions.WARRANTY_VIEW)
        db_session.add(perm_view)
    role = Role(name="WarrantyViewerRole", permissions=[perm_view])
    user = User(username="warranty_viewer", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def sample_warranty_data(db_session, edit_user):
    prod1 = Product(name_en="Smartphone A15", price=Decimal("45000.00"), stock_qty=Decimal("10"), barcode="BAR001")
    prod2 = Product(name_en="Bluetooth Speaker", price=Decimal("8500.00"), stock_qty=Decimal("5"), barcode="BAR002")
    cust1 = Customer(name="Sunil Perera", phone="0771234567")
    cust2 = Customer(name="Kamal Silva", phone="0719876543")
    db_session.add_all([prod1, prod2, cust1, cust2])
    db_session.flush()

    sale1 = Sale(
        document_number="INV-2026-00010",
        date=datetime(2026, 1, 15, 10, 30),
        total_amount=Decimal("45000.00"),
        payment_method="CASH",
        user_id=edit_user.id,
        customer_id=cust1.id,
    )
    item1 = SaleItem(
        product=prod1,
        qty=Decimal("1"),
        unit_price=Decimal("45000.00"),
        subtotal=Decimal("45000.00"),
        original_price=Decimal("45000.00"),
    )
    sale1.items = [item1]

    sale2 = Sale(
        document_number="INV-2026-00020",
        date=datetime(2026, 2, 1, 14, 0),
        total_amount=Decimal("17000.00"),
        payment_method="CASH",
        user_id=edit_user.id,
        customer_id=cust2.id,
    )
    item2 = SaleItem(
        product=prod2,
        qty=Decimal("2"),
        unit_price=Decimal("8500.00"),
        subtotal=Decimal("17000.00"),
        original_price=Decimal("8500.00"),
    )
    sale2.items = [item2]

    db_session.add_all([sale1, item1, sale2, item2])
    db_session.flush()

    # Warranty 1: Smartphone for Sunil
    w1 = Warranty(
        code="INV-2026-00010-01",
        unit_index=1,
        sale_id=sale1.id,
        sale_item_id=item1.id,
        product_id=prod1.id,
        customer_id=cust1.id,
        customer_name_snapshot="Sunil Perera",
        customer_phone_snapshot="0771234567",
        serial_number="IMEI864209012345678",
        warranty_type="SHOP",
        duration=12,
        duration_unit="MONTHS",
        remedy="REPAIR_OR_REPLACE",
        start_date=date(2026, 1, 15),
        end_date=date(2027, 1, 15),
        status="ACTIVE",
    )

    # Warranty 2 & 3: Multi-unit Speaker sale for Kamal
    w2 = Warranty(
        code="INV-2026-00020-01",
        unit_index=1,
        sale_id=sale2.id,
        sale_item_id=item2.id,
        product_id=prod2.id,
        customer_id=cust2.id,
        customer_name_snapshot="Kamal Silva",
        customer_phone_snapshot="0719876543",
        serial_number="SPK-SN-009911",
        warranty_type="SHOP",
        duration=6,
        duration_unit="MONTHS",
        remedy="REPAIR_ONLY",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 8, 1),
        status="ACTIVE",
    )
    w3 = Warranty(
        code="INV-2026-00020-02",
        unit_index=2,
        sale_id=sale2.id,
        sale_item_id=item2.id,
        product_id=prod2.id,
        customer_id=cust2.id,
        customer_name_snapshot="Kamal Silva",
        customer_phone_snapshot="0719876543",
        serial_number="SPK-SN-009922",
        warranty_type="SHOP",
        duration=6,
        duration_unit="MONTHS",
        remedy="REPAIR_ONLY",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 8, 1),
        status="ACTIVE",
    )

    db_session.add_all([w1, w2, w3])
    db_session.commit()
    return {"w1": w1, "w2": w2, "w3": w3, "sale1": sale1, "sale2": sale2, "cust1": cust1}


class TestWarrantyLookupService:
    def test_search_by_exact_warranty_code(self, sample_warranty_data):
        results = WarrantyService.search("INV-2026-00010-01")
        assert len(results) == 1
        dto = results[0]
        assert isinstance(dto, WarrantyDTO)
        assert dto.code == "INV-2026-00010-01"
        assert dto.product_name == "Smartphone A15"
        assert dto.customer_name == "Sunil Perera"

    def test_search_by_receipt_document_number_returns_all_units(self, sample_warranty_data):
        results = WarrantyService.search("INV-2026-00020")
        assert len(results) == 2
        assert [r.code for r in results] == ["INV-2026-00020-01", "INV-2026-00020-02"]
        assert results[0].serial_number == "SPK-SN-009911"
        assert results[1].serial_number == "SPK-SN-009922"

    def test_search_by_serial_number_exact_and_suffix(self, sample_warranty_data):
        # Exact serial
        exact = WarrantyService.search("SPK-SN-009911")
        assert len(exact) == 1
        assert exact[0].code == "INV-2026-00020-01"

        # Suffix >= 6 chars
        suffix = WarrantyService.search("009922")
        assert len(suffix) == 1
        assert suffix[0].code == "INV-2026-00020-02"

        # Suffix < 6 chars should not trigger suffix search
        short_suffix = WarrantyService.search("9922")
        assert len(short_suffix) == 0

    def test_search_by_phone_normalisation_variants(self, sample_warranty_data):
        # Sunil's phone is stored as 0771234567
        # Search variant with leading +94
        res1 = WarrantyService.search("+94771234567")
        assert len(res1) >= 1
        assert res1[0].code == "INV-2026-00010-01"

        # Search variant with 94 without +
        res2 = WarrantyService.search("94771234567")
        assert len(res2) >= 1
        assert res2[0].code == "INV-2026-00010-01"

        # Search variant with 077...
        res3 = WarrantyService.search("0771234567")
        assert len(res3) >= 1
        assert res3[0].code == "INV-2026-00010-01"

    def test_search_by_customer_name(self, sample_warranty_data):
        results = WarrantyService.search("Kamal")
        assert len(results) == 2
        assert all(r.customer_name == "Kamal Silva" for r in results)

    def test_effective_status_boundaries(self):
        # Active (> 30 days remaining)
        ref_today = date(2026, 6, 1)
        end_date = date(2026, 10, 1)
        eff_status, days_left = WarrantyService.calculate_effective_status("ACTIVE", end_date, today=ref_today)
        assert eff_status == "ACTIVE"
        assert days_left == (end_date - ref_today).days

        # Expiring (<= 30 days remaining)
        end_date_expiring = date(2026, 6, 25)
        eff_status, days_left = WarrantyService.calculate_effective_status("ACTIVE", end_date_expiring, today=ref_today)
        assert eff_status == "EXPIRING"
        assert days_left == 24

        # Boundary: today == end_date (last day of coverage)
        eff_status, days_left = WarrantyService.calculate_effective_status("ACTIVE", ref_today, today=ref_today)
        assert eff_status == "EXPIRING"
        assert days_left == 0

        # Expired: today == end_date + 1
        expired_date = ref_today - timedelta(days=1)
        eff_status, days_left = WarrantyService.calculate_effective_status("ACTIVE", expired_date, today=ref_today)
        assert eff_status == "EXPIRED"
        assert days_left < 0

        # Preserves non-active status
        eff_status, _ = WarrantyService.calculate_effective_status("VOID", end_date, today=ref_today)
        assert eff_status == "VOID"
        eff_status, _ = WarrantyService.calculate_effective_status("CANCELLED", end_date, today=ref_today)
        assert eff_status == "CANCELLED"
        eff_status, _ = WarrantyService.calculate_effective_status("REPLACED", end_date, today=ref_today)
        assert eff_status == "REPLACED"


class TestWarrantyAdminCorrection:
    def test_admin_correction_success_updates_record_and_writes_audit(
        self, sample_warranty_data, edit_user, db_session
    ):
        w = sample_warranty_data["w1"]
        new_serial = "IMEI999999999999999"
        new_start = date(2026, 1, 20)
        new_end = date(2027, 1, 20)
        reason = "Corrected IMEI typed incorrectly at checkout and extended 5 days for delivery"

        updated_dto = WarrantyService.update_warranty_admin(
            warranty_id=w.id,
            user_id=edit_user.id,
            reason=reason,
            serial_number=new_serial,
            start_date=new_start,
            end_date=new_end,
        )

        assert updated_dto.serial_number == new_serial
        assert updated_dto.start_date == new_start
        assert updated_dto.end_date == new_end

        # Verify DB persistence
        db = Database()
        with db.get_session() as session:
            persisted = session.get(Warranty, w.id)
            assert persisted.serial_number == new_serial
            assert persisted.start_date == new_start
            assert persisted.end_date == new_end

            audit = (
                session.query(AuditLog)
                .filter(AuditLog.action == "WARRANTY_CORRECTION", AuditLog.user_id == edit_user.id)
                .first()
            )
            assert audit is not None
            assert audit.event_type == WARRANTY_EVENT
            assert reason in audit.details
            assert new_serial in audit.details

    def test_admin_correction_permission_denied(self, sample_warranty_data, view_only_user):
        w = sample_warranty_data["w1"]
        with pytest.raises(PermissionError) as exc_info:
            WarrantyService.update_warranty_admin(
                warranty_id=w.id,
                user_id=view_only_user.id,
                reason="Test unauthorized update",
                serial_number="NEW-SERIAL",
            )
        assert "permission_denied" in str(exc_info.value)

    def test_admin_correction_missing_reason_fails_closed(self, sample_warranty_data, edit_user):
        w = sample_warranty_data["w1"]
        with pytest.raises(ValueError) as exc_info:
            WarrantyService.update_warranty_admin(
                warranty_id=w.id,
                user_id=edit_user.id,
                reason="   ",
                serial_number="NEW-SERIAL",
            )
        assert "reason_required" in str(exc_info.value)

    def test_admin_correction_invalid_date_range_fails_closed(self, sample_warranty_data, edit_user):
        w = sample_warranty_data["w1"]
        with pytest.raises(ValueError) as exc_info:
            WarrantyService.update_warranty_admin(
                warranty_id=w.id,
                user_id=edit_user.id,
                reason="Valid reason",
                start_date=date(2027, 1, 1),
                end_date=date(2026, 1, 1),
            )
        assert "invalid_date_range" in str(exc_info.value)
