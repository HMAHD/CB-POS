"""Domain tests for Warranty W4 (#824): Warranty details on receipt,
A4 invoice, standalone thermal and PDF warranty cards, reprint flow, and audit logging.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from cbpos.core.constants.audit import WARRANTY_EVENT
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import (
    AuditLog,
    Permission,
    Product,
    Role,
    Sale,
    SaleItem,
    User,
    Warranty,
    WarrantyPolicy,
)
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.receipt_reprint_service import ReceiptReprintService
from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder
from cbpos.core.services.warranty_card_builder import WarrantyCardBuilder

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def user_and_policy(db_session):
    role = Role(name="CashierRole")
    db_session.add(role)
    db_session.flush()

    for code in [
        Permissions.SALES_REPRINT,
        Permissions.WARRANTY_VIEW,
        Permissions.WARRANTY_EDIT,
    ]:
        perm = db_session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if not perm:
            perm = Permission(code=code, description=code, group="Sales")
            db_session.add(perm)
            db_session.flush()
        role.permissions.append(perm)

    user = User(
        username="cashier_test",
        pin_hash="fake",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)

    policy = WarrantyPolicy(
        name="2 Year Manufacturer Cover",
        name_si="වසර 2 ක නිෂ්පාදක වගකීම",
        name_ta="2 வருட உற்பத்தியாளர் உத்தரவாதம்",
        warranty_type="MANUFACTURER",
        duration=2,
        duration_unit="YEARS",
        remedy="REPAIR_OR_REPLACE",
        provider_name="Apple Inc",
        terms_text="Standard hardware warranty covering manufacturer defects.",
        exclusions_text="Water damage, cracked screens, unauthorized repairs.",
        is_active=True,
    )
    db_session.add(policy)
    db_session.commit()

    return {"user": user, "policy": policy}


def _make_mock_sale(
    sale_id: int = 100,
    doc_num: str = "INV-2026-00100",
    total: Decimal = Decimal("500.00"),
    status: str = "COMPLETED",
) -> MagicMock:
    sale = MagicMock()
    sale.id = sale_id
    sale.document_number = doc_num
    sale.date = datetime(2026, 11, 13, 10, 30)
    sale.total_amount = total
    sale.tax_vat = Decimal("0.00")
    sale.status = status
    sale.additional_discount_type = "NONE"
    sale.additional_discount_value = None
    sale.payment_method = "CASH"
    sale.refund_of_sale_id = None
    sale.customer = None
    sale.customer_id = None
    pmt = MagicMock()
    pmt.payment_method = "CASH"
    pmt.amount = total
    pmt.tendered_amount = total
    sale.payments = [pmt]
    sale.warranties = []
    sale.items = []
    return sale


class TestReceiptWarrantyPrinting:
    def test_golden_non_warranty_sale_produces_identical_commands(self):
        sale = _make_mock_sale(sale_id=100, total=Decimal("500.00"))

        item = MagicMock()
        item.product_id = 1
        item.product = MagicMock(id=1, name_en="Normal Soap", name_si=None, name_ta=None)
        item.product.get_display_name = lambda lang=None: "Normal Soap"
        item.qty = Decimal("2")
        item.unit_price = Decimal("250.00")
        item.original_price = Decimal("250.00")
        item.subtotal = Decimal("500.00")
        item.is_manual_price = False
        item.warranties = []
        sale.items = [item]

        # Call with show_warranty_on_receipt=True vs False
        commands_on = SalesReceiptBuilder.build_receipt(
            sale,
            config_override={"show_warranty_on_receipt": True, "enable_loyalty": False, "show_barcode": False},
        )
        commands_off = SalesReceiptBuilder.build_receipt(
            sale,
            config_override={"show_warranty_on_receipt": False, "enable_loyalty": False, "show_barcode": False},
        )

        assert commands_on == commands_off

    def test_warranty_line_and_serial_printing_on_receipt(self):
        sale = _make_mock_sale(sale_id=101, total=Decimal("120000.00"))

        w1 = MagicMock()
        w1.duration = 12
        w1.duration_unit = "MONTHS"
        w1.provider_name = "TechZone"
        w1.end_date = date(2027, 11, 13)
        w1.status = "ACTIVE"
        w1.serial_number = "SN-IPHONE-001"
        w1.terms_text = "Free labor and parts for 1 year."
        w1.exclusions_text = "Physical damage."

        item = MagicMock()
        item.product_id = 5
        item.product = MagicMock(id=5, name_en="Smartphone X", name_si=None, name_ta=None)
        item.product.get_display_name = lambda lang=None: "Smartphone X"
        item.qty = Decimal("1")
        item.unit_price = Decimal("120000.00")
        item.original_price = Decimal("120000.00")
        item.subtotal = Decimal("120000.00")
        item.is_manual_price = False
        item.warranties = [w1]

        sale.items = [item]
        sale.warranties = [w1]

        commands = SalesReceiptBuilder.build_receipt(
            sale,
            config_override={"show_warranty_on_receipt": True, "enable_loyalty": False, "show_barcode": False},
        )

        texts = [c["val"] for c in commands if c.get("type") == "text"]

        # Check warranty sub-row under item
        w_line = [t for t in texts if "Warranty: 12 Months (TechZone) until 2027-11-13" in t]
        assert len(w_line) == 1

        # Check serial number under item
        sn_line = [t for t in texts if "S/N: SN-IPHONE-001" in t]
        assert len(sn_line) == 1

        # Check terms block
        terms_header = [t for t in texts if "WARRANTY TERMS & CONDITIONS" in t]
        assert len(terms_header) == 1
        assert any("Free labor and parts" in t for t in texts)
        assert any("Physical damage." in t for t in texts)

    def test_merged_line_serials_aggregation(self):
        sale = _make_mock_sale(sale_id=102, total=Decimal("20000.00"))

        w1 = MagicMock(
            duration=6,
            duration_unit="MONTHS",
            provider_name=None,
            end_date=date(2027, 5, 13),
            status="ACTIVE",
            serial_number="KB-001",
            terms_text=None,
            exclusions_text=None,
        )
        w2 = MagicMock(
            duration=6,
            duration_unit="MONTHS",
            provider_name=None,
            end_date=date(2027, 5, 13),
            status="ACTIVE",
            serial_number="KB-002",
            terms_text=None,
            exclusions_text=None,
        )

        prod = MagicMock(id=10, name_en="Mechanical Keyboard", name_si=None, name_ta=None)
        prod.get_display_name = lambda lang=None: "Mechanical Keyboard"

        item1 = MagicMock(
            product_id=10,
            product=prod,
            qty=Decimal("1"),
            unit_price=Decimal("10000.00"),
            original_price=Decimal("10000.00"),
            subtotal=Decimal("10000.00"),
            is_manual_price=False,
            warranties=[w1],
        )
        item2 = MagicMock(
            product_id=10,
            product=prod,
            qty=Decimal("1"),
            unit_price=Decimal("10000.00"),
            original_price=Decimal("10000.00"),
            subtotal=Decimal("10000.00"),
            is_manual_price=False,
            warranties=[w2],
        )

        sale.items = [item1, item2]
        sale.warranties = [w1, w2]

        # With merge_items=True
        commands = SalesReceiptBuilder.build_receipt(
            sale,
            config_override={
                "merge_items": True,
                "show_warranty_on_receipt": True,
                "enable_loyalty": False,
                "show_barcode": False,
            },
        )

        texts = [c["val"] for c in commands if c.get("type") == "text"]

        # Merged line item count should show 1 line item
        assert any("2.0 x" in t for t in texts)
        # Both serial numbers must be present
        assert any("S/N: KB-001" in t for t in texts)
        assert any("S/N: KB-002" in t for t in texts)

    def test_reprint_status_tags_on_void_or_cancelled_warranties(self):
        sale = _make_mock_sale(sale_id=103, total=Decimal("50000.00"))

        w_void = MagicMock(
            duration=1,
            duration_unit="YEARS",
            provider_name="Shop",
            end_date=date(2027, 11, 13),
            status="CANCELLED",
            serial_number="CANCELLED-SN",
            terms_text=None,
            exclusions_text=None,
        )

        item = MagicMock(
            product_id=8,
            product=MagicMock(id=8, name_en="Tablet", get_display_name=lambda lang=None: "Tablet"),
            qty=Decimal("1"),
            unit_price=Decimal("50000.00"),
            original_price=Decimal("50000.00"),
            subtotal=Decimal("50000.00"),
            is_manual_price=False,
            warranties=[w_void],
        )
        sale.items = [item]
        sale.warranties = [w_void]

        # Original print does not show CANCELLED tag
        commands_orig = SalesReceiptBuilder.build_receipt(
            sale, is_reprint=False, config_override={"show_warranty_on_receipt": True}
        )
        texts_orig = [c["val"] for c in commands_orig if c.get("type") == "text"]
        assert not any("[CANCELLED]" in t for t in texts_orig)

        # Reprint shows [CANCELLED] tag
        commands_reprint = SalesReceiptBuilder.build_receipt(
            sale, is_reprint=True, config_override={"show_warranty_on_receipt": True}
        )
        texts_reprint = [c["val"] for c in commands_reprint if c.get("type") == "text"]
        assert any("[CANCELLED]" in t for t in texts_reprint)


class TestWarrantyCardBuilder:
    def test_thermal_escpos_commands_structure_and_cut_per_unit(self):
        w1 = MagicMock(
            code="WAR-2026-00001-01",
            duration=12,
            duration_unit="MONTHS",
            provider_name="Apple Inc",
            remedy="REPAIR_OR_REPLACE",
            start_date=date(2026, 11, 13),
            end_date=date(2027, 11, 13),
            status="ACTIVE",
            serial_number="SN-UNIT-1",
            customer_name_snapshot="Kamal Perera",
            customer_phone_snapshot="0771234567",
            terms_text="Covered against factory defects.",
            exclusions_text="No water damage.",
            product=MagicMock(name_en="iPhone 15", get_display_name=lambda lang=None: "iPhone 15"),
            sale=MagicMock(document_number="INV-2026-00001"),
        )
        w2 = MagicMock(
            code="WAR-2026-00001-02",
            duration=12,
            duration_unit="MONTHS",
            provider_name="Apple Inc",
            remedy="REPAIR_OR_REPLACE",
            start_date=date(2026, 11, 13),
            end_date=date(2027, 11, 13),
            status="ACTIVE",
            serial_number="SN-UNIT-2",
            customer_name_snapshot="Kamal Perera",
            customer_phone_snapshot="0771234567",
            terms_text="Covered against factory defects.",
            exclusions_text="No water damage.",
            product=MagicMock(name_en="iPhone 15", get_display_name=lambda lang=None: "iPhone 15"),
            sale=MagicMock(document_number="INV-2026-00001"),
        )

        commands = WarrantyCardBuilder.build_escpos([w1, w2])

        # Cuts must equal unit count (2 independent certificates)
        cuts = [c for c in commands if c.get("type") == "cut"]
        assert len(cuts) == 2

        # Both barcodes present
        barcodes = [c for c in commands if c.get("type") == "barcode"]
        assert len(barcodes) == 2

        # Titles and stamp boxes present
        texts = [c["val"] for c in commands if c.get("type") == "text"]
        assert texts.count("WARRANTY CERTIFICATE") == 2
        assert any("OFFICIAL SHOP STAMP" in t for t in texts)
        assert any("Kamal Perera" in t for t in texts)
        assert any("SN-UNIT-1" in t for t in texts)
        assert any("SN-UNIT-2" in t for t in texts)

    def test_pdf_generation_smoke_multilingual(self, tmp_path):
        w = MagicMock(
            code="WAR-2026-00099-01",
            duration=2,
            duration_unit="YEARS",
            provider_name="Samsung",
            remedy="REPAIR_OR_REPLACE",
            start_date=date(2026, 11, 13),
            end_date=date(2028, 11, 13),
            status="ACTIVE",
            serial_number="358765091234567",
            customer_name_snapshot="නිමල් ප්‍රනාන්දු",
            customer_phone_snapshot="0712345678",
            terms_text="නිෂ්පාදන දෝෂ සඳහා සම්පූර්ණ අලුත්වැඩියාව.",
            exclusions_text="භෞතික හානි ආවරණය නොවේ.",
            product=MagicMock(name_en="Galaxy S24", get_display_name=lambda lang=None: "ගැලැක්සි S24"),
            sale=MagicMock(document_number="INV-2026-00099"),
        )

        for lang in ["en", "si", "ta"]:
            pdf_path = tmp_path / f"warranty_{lang}.pdf"
            out_file = WarrantyCardBuilder.build_pdf([w], str(pdf_path), lang=lang)
            assert out_file == str(pdf_path)
            assert pdf_path.exists()
            assert pdf_path.stat().st_size > 500  # Non-trivial PDF generated


class TestReceiptReprintWarrantyCards:
    def test_reprint_warranty_cards_service_flow_and_audit_log(self, db_session, user_and_policy):
        user = user_and_policy["user"]
        policy = user_and_policy["policy"]

        prod = Product(
            name_en="Microwave Oven",
            barcode="7890123456789",
            price=Decimal("35000.00"),
            stock_qty=Decimal("5"),
            warranty_policy_id=policy.id,
            serial_mode="REQUIRED",
        )
        db_session.add(prod)
        db_session.flush()

        sale = Sale(
            document_number="INV-2026-00500",
            total_amount=Decimal("35000.00"),
            payment_method="CASH",
            tax_vat=Decimal("0.00"),
            user_id=user.id,
            status="COMPLETED",
        )
        db_session.add(sale)
        db_session.flush()

        si = SaleItem(
            sale_id=sale.id,
            product_id=prod.id,
            qty=Decimal("1"),
            unit_price=Decimal("35000.00"),
            original_price=Decimal("35000.00"),
            subtotal=Decimal("35000.00"),
        )
        db_session.add(si)
        db_session.flush()

        w = Warranty(
            code="WAR-2026-00500-01",
            unit_index=1,
            sale_id=sale.id,
            sale_item_id=si.id,
            product_id=prod.id,
            serial_number="MW-998877",
            warranty_type=policy.warranty_type,
            duration=policy.duration,
            duration_unit=policy.duration_unit,
            remedy=policy.remedy,
            provider_name=policy.provider_name,
            terms_text=policy.terms_text,
            exclusions_text=policy.exclusions_text,
            start_date=date(2026, 11, 13),
            end_date=date(2028, 11, 13),
            status="ACTIVE",
        )
        db_session.add(w)
        db_session.commit()

        # Execute reprint
        commands = ReceiptReprintService.reprint_warranty_cards(
            sale.id,
            user_id=user.id,
        )

        assert len(commands) > 0
        assert any(c.get("type") == "cut" for c in commands)

        # AuditLog recorded
        audit = db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "REPRINT_WARRANTY_CARD",
                AuditLog.user_id == user.id,
            )
        ).scalar_one()

        assert audit.event_type == WARRANTY_EVENT
        assert "INV-2026-00500" in audit.details

    def test_reprint_warranty_cards_refuses_void_and_no_warranties(self, db_session, user_and_policy):
        user = user_and_policy["user"]

        sale_void = Sale(
            document_number="INV-VOID-1",
            total_amount=Decimal("100.00"),
            payment_method="CASH",
            user_id=user.id,
            status="VOID",
        )
        sale_no_w = Sale(
            document_number="INV-NOWAR-1",
            total_amount=Decimal("200.00"),
            payment_method="CASH",
            user_id=user.id,
            status="COMPLETED",
        )
        db_session.add_all([sale_void, sale_no_w])
        db_session.commit()

        with pytest.raises(ValueError, match="reprint_void"):
            ReceiptReprintService.reprint_warranty_cards(sale_void.id, user_id=user.id)

        with pytest.raises(ValueError, match="no_warranties"):
            ReceiptReprintService.reprint_warranty_cards(sale_no_w.id, user_id=user.id)


class TestA4InvoiceWarrantyIntegration:
    def test_invoice_service_generates_pdf_with_warranty_rows_and_terms(self, tmp_path):
        w = MagicMock(
            product_id=20,
            sale_item_id=1,
            duration=1,
            duration_unit="YEARS",
            serial_number="INV-SN-12345",
            end_date=date(2027, 11, 13),
            terms_text="Comprehensive 1-year coverage.",
            exclusions_text="Customer neglect.",
            status="ACTIVE",
        )

        prod = MagicMock(
            id=20,
            name_en="Laser Printer Pro",
            name_si=None,
            name_ta=None,
            unit="pcs",
            price=Decimal("45000.00"),
            is_weighted=False,
            get_display_name=lambda lang=None: "Laser Printer Pro",
        )

        item = MagicMock(
            id=1,
            product_id=20,
            product=prod,
            qty=Decimal("1"),
            unit_price=Decimal("45000.00"),
            original_price=Decimal("45000.00"),
            subtotal=Decimal("45000.00"),
            warranties=[w],
        )

        pmt = MagicMock()
        pmt.payment_method = "CASH"
        pmt.amount = Decimal("45000.00")

        sale = MagicMock(
            document_number="INV-2026-00999",
            total_amount=Decimal("45000.00"),
            tax_vat=Decimal("0.00"),
            tax_sscl=Decimal("0.00"),
            vat_rate=Decimal("0.00"),
            taxable_amount=Decimal("45000.00"),
            vat_exempt_amount=Decimal("0.00"),
            payment_method="CASH",
            payments=[pmt],
            additional_discount_type="NONE",
            additional_discount_value=None,
            date=datetime(2026, 11, 13, 14, 0),
            customer=None,
            customer_id=None,
            items=[item],
            warranties=[w],
        )

        pdf_path = tmp_path / "invoice_with_warranty.pdf"
        out_file = InvoiceService.generate_pdf(sale, str(pdf_path))

        assert out_file == str(pdf_path)
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 1000
