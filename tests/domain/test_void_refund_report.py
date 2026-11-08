"""
Regression tests for Issue #843:
Refunds never appear in the Void/Refund report.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import AuditLog, Permission, Product, Role, Sale, SaleItem, User
from cbpos.core.reports.definitions.void_refund_report import VoidRefundReport
from cbpos.i18n import _t


@pytest.fixture
def vr_users(db_session):
    suffix = uuid.uuid4().hex[:8]
    perm = Permission(code=f"vr_perm_{suffix}")
    role = Role(name=f"VRRole_{suffix}", permissions=[perm])
    cashier = User(username=f"cashier_{suffix}", pin_hash="hash", role=role)
    manager = User(username=f"manager_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([perm, role, cashier, manager])
    db_session.flush()
    return cashier, manager


@pytest.fixture
def vr_product(db_session):
    suffix = uuid.uuid4().hex[:8]
    product = Product(
        name_en=f"VRProduct_{suffix}",
        barcode=f"VRP{suffix}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("100"),
    )
    db_session.add(product)
    db_session.flush()
    return product


class TestVoidRefundReportIssue843:
    """Issue #843: Void/Refund report includes both voids and completed refunds with accurate metadata."""

    def test_issue_843_refund_listed_with_user_and_negative_amount(self, db_session, vr_users, vr_product):
        cashier, manager = vr_users

        # 1. Ordinary completed sale (should NOT appear in report)
        sale = Sale(
            document_number="REC-843-001",
            date=datetime(2026, 4, 1, 10, 0, 0),
            total_amount=Decimal("200.00"),
            user_id=cashier.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=vr_product.id,
            qty=Decimal("2.000"),
            unit_price=Decimal("100.00"),
            original_price=Decimal("100.00"),
            subtotal=Decimal("200.00"),
            unit_cost=Decimal("50.00"),
        )
        db_session.add(item)

        # 2. Voided sale (should appear in report)
        void_sale = Sale(
            document_number="REC-843-VOID",
            date=datetime(2026, 4, 1, 11, 0, 0),
            total_amount=Decimal("150.00"),
            user_id=cashier.id,
            payment_method="CASH",
            status=DocumentStatus.VOID,
        )
        db_session.add(void_sale)
        db_session.flush()

        audit_void = AuditLog(
            user_id=manager.id,
            action="VOID_SALE",
            event_type="TRANSACTION",
            details="Voided sale REC-843-VOID. Reason: Customer changed mind",
        )
        db_session.add(audit_void)

        # 3. Partial refund (should appear in report as Part with negative amount)
        refund_sale_part = Sale(
            document_number="REF-843-PART",
            date=datetime(2026, 4, 1, 12, 0, 0),
            total_amount=Decimal("-100.00"),
            user_id=cashier.id,
            payment_method="REFUND",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=sale.id,
        )
        db_session.add(refund_sale_part)
        db_session.flush()

        item.refunded_qty = Decimal("1.000")

        refund_item_part = SaleItem(
            sale_id=refund_sale_part.id,
            product_id=vr_product.id,
            qty=Decimal("-1.000"),
            unit_price=Decimal("100.00"),
            original_price=Decimal("100.00"),
            subtotal=Decimal("-100.00"),
            unit_cost=Decimal("50.00"),
            refund_of_item_id=item.id,
            refund_reason="Damaged item",
        )
        db_session.add(refund_item_part)

        audit_refund_part = AuditLog(
            user_id=manager.id,
            action="REFUND",
            event_type="TRANSACTION",
            details="Refunded sale REC-843-001 as REF-843-PART. Total: 100.00. Reason: Damaged item",
        )
        # Duplicate audit entry (e.g. override or multiple actions) must not duplicate row
        audit_refund_part_override = AuditLog(
            user_id=manager.id,
            action="REFUND_TENDER_OVERRIDE",
            event_type="PERMISSION_OVERRIDE",
            details="Refund REF-843-PART tender overridden to CASH. Reason: Cashier requested cash",
        )
        db_session.add_all([audit_refund_part, audit_refund_part_override])
        db_session.commit()

        report = VoidRefundReport()
        df = report.generate({"date_range": {"start": "2026-04-01", "end": "2026-04-01"}})

        doc_numbers = list(df["Document #"])
        # Ordinary sale excluded
        assert "REC-843-001" not in doc_numbers
        # Void included
        assert "REC-843-VOID" in doc_numbers
        # Refund included
        assert "REF-843-PART" in doc_numbers

        # Verify no duplicate rows
        assert doc_numbers.count("REF-843-PART") == 1

        # Check refund row details
        rf_row = df[df["Document #"] == "REF-843-PART"].iloc[0]
        assert rf_row["Amount"] == Decimal("-100.00")
        assert rf_row["Type"] == _t("reports.type_refund")
        assert rf_row["Scope"] == _t("reports.scope_part")
        assert rf_row["Original Receipt"] == "REC-843-001"
        assert rf_row["User"] == cashier.username
        assert rf_row["Approver"] == manager.username
        assert "Damaged item" in rf_row["Reason"]

        # Check void row details
        vd_row = df[df["Document #"] == "REC-843-VOID"].iloc[0]
        assert vd_row["Amount"] == Decimal("150.00")
        assert vd_row["Type"] == _t("reports.type_void")
        assert vd_row["User"] == cashier.username
        assert vd_row["Approver"] == manager.username
        assert "Customer changed mind" in vd_row["Reason"]

    def test_issue_843_full_refund_scope(self, db_session, vr_users, vr_product):
        cashier, _manager = vr_users

        sale = Sale(
            document_number="REC-843-002",
            date=datetime(2026, 4, 2, 10, 0, 0),
            total_amount=Decimal("100.00"),
            user_id=cashier.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=vr_product.id,
            qty=Decimal("1.000"),
            unit_price=Decimal("100.00"),
            original_price=Decimal("100.00"),
            subtotal=Decimal("100.00"),
            unit_cost=Decimal("50.00"),
        )
        db_session.add(item)

        refund_sale_full = Sale(
            document_number="REF-843-FULL",
            date=datetime(2026, 4, 2, 11, 0, 0),
            total_amount=Decimal("-100.00"),
            user_id=cashier.id,
            payment_method="REFUND",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=sale.id,
        )
        db_session.add(refund_sale_full)
        db_session.flush()

        item.refunded_qty = Decimal("1.000")
        refund_item_full = SaleItem(
            sale_id=refund_sale_full.id,
            product_id=vr_product.id,
            qty=Decimal("-1.000"),
            unit_price=Decimal("100.00"),
            original_price=Decimal("100.00"),
            subtotal=Decimal("-100.00"),
            unit_cost=Decimal("50.00"),
            refund_of_item_id=item.id,
            refund_reason="Defective",
        )
        db_session.add(refund_item_full)
        db_session.commit()

        report = VoidRefundReport()
        df = report.generate({"date_range": {"start": "2026-04-02", "end": "2026-04-02"}})

        rf_row = df[df["Document #"] == "REF-843-FULL"].iloc[0]
        assert rf_row["Scope"] == _t("reports.scope_full")
        assert rf_row["Original Receipt"] == "REC-843-002"
        # When no separate AuditLog approver exists, fall back to acting user
        assert rf_row["Approver"] == cashier.username
