"""
Regression tests for Issue #798:
Profit & Loss report uses VAT-inclusive revenue, current cost and float math.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Permission, Product, Role, Sale, SaleItem, User
from cbpos.core.reports.definitions.financial_reports import ProfitLossReport


@pytest.fixture
def pl_user(db_session):
    suffix = uuid.uuid4().hex[:8]
    permission = Permission(code=f"pl_perm_{suffix}")
    role = Role(name=f"PLRole_{suffix}", permissions=[permission])
    user = User(username=f"pl_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def pl_product(db_session):
    suffix = uuid.uuid4().hex[:8]
    product = Product(
        name_en=f"PLProduct_{suffix}",
        barcode=f"PLP{suffix}",
        price=Decimal("118.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("100"),
    )
    db_session.add(product)
    db_session.flush()
    return product


class TestProfitLossReportIssue798:
    """Issue #798: P&L revenue net of VAT, stored historical COGS, SSCL expense, Decimal precision."""

    def test_issue_798_cost_change_between_sales_keeps_history(self, db_session, pl_user, pl_product):
        """Historical COGS must use SaleItem.unit_cost captured at sale time, not current Product.cost."""
        # Sale 1 when product cost was 50.00
        sale1 = Sale(
            document_number="REC-798-001",
            date=datetime(2026, 3, 1, 10, 0, 0),
            total_amount=Decimal("118.00"),
            user_id=pl_user.id,
            tax_vat=Decimal("18.00"),
            tax_sscl=Decimal("2.50"),
            net_revenue=Decimal("97.50"),  # 118 - 18 - 2.50 = 97.50
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            vat_rate=Decimal("18.00"),
            sscl_rate=Decimal("2.50"),
        )
        db_session.add(sale1)
        db_session.flush()

        item1 = SaleItem(
            sale_id=sale1.id,
            product_id=pl_product.id,
            qty=Decimal("1.000"),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("118.00"),
            unit_cost=Decimal("50.00"),
        )
        db_session.add(item1)

        # Later, product cost changes to 80.00
        pl_product.cost = Decimal("80.00")

        # Sale 2 when product cost was 80.00
        sale2 = Sale(
            document_number="REC-798-002",
            date=datetime(2026, 3, 2, 10, 0, 0),
            total_amount=Decimal("118.00"),
            user_id=pl_user.id,
            tax_vat=Decimal("18.00"),
            tax_sscl=Decimal("2.50"),
            net_revenue=Decimal("97.50"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            vat_rate=Decimal("18.00"),
            sscl_rate=Decimal("2.50"),
        )
        db_session.add(sale2)
        db_session.flush()

        item2 = SaleItem(
            sale_id=sale2.id,
            product_id=pl_product.id,
            qty=Decimal("1.000"),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("118.00"),
            unit_cost=Decimal("80.00"),
        )
        db_session.add(item2)

        # After both sales, product cost changes again to 95.00
        pl_product.cost = Decimal("95.00")
        db_session.commit()

        report = ProfitLossReport()
        df = report.generate({"date_range": {"start": "2026-03-01", "end": "2026-03-05"}})

        row1 = df[df["Invoice #"] == "REC-798-001"].iloc[0]
        row2 = df[df["Invoice #"] == "REC-798-002"].iloc[0]

        # COGS must match captured cost (50.00 and 80.00), NEVER current cost (95.00)
        assert row1["Cost (COGS)"] == Decimal("50.00")
        assert row2["Cost (COGS)"] == Decimal("80.00")

    def test_issue_798_revenue_excludes_vat(self, db_session, pl_user, pl_product):
        """Revenue in P&L is net of VAT (VAT-exclusive turnover = net_revenue + tax_sscl)."""
        sale = Sale(
            document_number="REC-798-003",
            date=datetime(2026, 3, 3, 10, 0, 0),
            total_amount=Decimal("118.00"),
            user_id=pl_user.id,
            tax_vat=Decimal("18.00"),
            tax_sscl=Decimal("2.50"),
            net_revenue=Decimal("97.50"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            vat_rate=Decimal("18.00"),
            sscl_rate=Decimal("2.50"),
        )
        db_session.add(sale)
        db_session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=pl_product.id,
            qty=Decimal("1.000"),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("118.00"),
            unit_cost=Decimal("60.00"),
        )
        db_session.add(item)
        db_session.commit()

        report = ProfitLossReport()
        df = report.generate({"date_range": {"start": "2026-03-01", "end": "2026-03-05"}})

        row = df[df["Invoice #"] == "REC-798-003"].iloc[0]
        # Revenue must be net_revenue + tax_sscl = 97.50 + 2.50 = 100.00 (NOT 118.00 MRP)
        assert row["Revenue"] == Decimal("100.00")
        assert row["SSCL Expense"] == Decimal("2.50")
        assert row["Cost (COGS)"] == Decimal("60.00")
        # Gross profit = 100.00 - 60.00 - 2.50 = 37.50
        assert row["Gross Profit"] == Decimal("37.50")
        assert row["Margin %"] == "37.50%"

    def test_issue_798_refund_reverses_cogs(self, db_session, pl_user, pl_product):
        """Refund documents reverse revenue, COGS and SSCL."""
        sale = Sale(
            document_number="REC-798-004",
            date=datetime(2026, 3, 4, 10, 0, 0),
            total_amount=Decimal("118.00"),
            user_id=pl_user.id,
            tax_vat=Decimal("18.00"),
            tax_sscl=Decimal("2.50"),
            net_revenue=Decimal("97.50"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=pl_product.id,
            qty=Decimal("1.000"),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("118.00"),
            unit_cost=Decimal("60.00"),
        )
        db_session.add(item)

        # Full refund document
        refund_sale = Sale(
            document_number="REF-798-004",
            date=datetime(2026, 3, 4, 11, 0, 0),
            total_amount=Decimal("-118.00"),
            user_id=pl_user.id,
            tax_vat=Decimal("-18.00"),
            tax_sscl=Decimal("-2.50"),
            net_revenue=Decimal("-97.50"),
            payment_method="REFUND",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=sale.id,
        )
        db_session.add(refund_sale)
        db_session.flush()

        refund_item = SaleItem(
            sale_id=refund_sale.id,
            product_id=pl_product.id,
            qty=Decimal("-1.000"),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("-118.00"),
            unit_cost=Decimal("60.00"),
            refund_of_item_id=item.id,
        )
        db_session.add(refund_item)
        db_session.commit()

        report = ProfitLossReport()
        df = report.generate({"date_range": {"start": "2026-03-01", "end": "2026-03-05"}})

        # The refund row itself
        refund_row = df[df["Invoice #"] == "REF-798-004"].iloc[0]
        assert refund_row["Revenue"] == Decimal("-100.00")
        assert refund_row["Cost (COGS)"] == Decimal("-60.00")
        assert refund_row["SSCL Expense"] == Decimal("-2.50")
        assert refund_row["Gross Profit"] == Decimal("-37.50")

        # Summary total row: 100 - 100 = 0, 60 - 60 = 0, 2.50 - 2.50 = 0, GP = 0
        total_row = df[df["Invoice #"] == "TOTAL"].iloc[0]
        assert total_row["Revenue"] == Decimal("0.00")
        assert total_row["Cost (COGS)"] == Decimal("0.00")
        assert total_row["SSCL Expense"] == Decimal("0.00")
        assert total_row["Gross Profit"] == Decimal("0.00")
        assert total_row["Margin %"] == "0.00%"

    def test_issue_798_void_excluded(self, db_session, pl_user, pl_product):
        """Voided sales must be completely excluded from P&L."""
        sale_void = Sale(
            document_number="REC-798-VOID",
            date=datetime(2026, 3, 5, 10, 0, 0),
            total_amount=Decimal("118.00"),
            user_id=pl_user.id,
            tax_vat=Decimal("18.00"),
            tax_sscl=Decimal("2.50"),
            net_revenue=Decimal("97.50"),
            payment_method="CASH",
            status=DocumentStatus.VOID,
        )
        db_session.add(sale_void)
        db_session.flush()

        item_void = SaleItem(
            sale_id=sale_void.id,
            product_id=pl_product.id,
            qty=Decimal("1.000"),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("118.00"),
            unit_cost=Decimal("60.00"),
        )
        db_session.add(item_void)
        db_session.commit()

        report = ProfitLossReport()
        df = report.generate({"date_range": {"start": "2026-03-01", "end": "2026-03-06"}})

        invoices = list(df["Invoice #"])
        assert "REC-798-VOID" not in invoices

    def test_issue_798_zero_revenue_margin_does_not_crash(self, db_session, pl_user, pl_product):
        """Zero revenue sale (e.g. 100% discount or promotional sample) should return 0.00% without ZeroDivisionError."""
        sale = Sale(
            document_number="REC-798-FREE",
            date=datetime(2026, 3, 6, 10, 0, 0),
            total_amount=Decimal("0.00"),
            user_id=pl_user.id,
            tax_vat=Decimal("0.00"),
            tax_sscl=Decimal("0.00"),
            net_revenue=Decimal("0.00"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=pl_product.id,
            qty=Decimal("1.000"),
            unit_price=Decimal("0.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("0.00"),
            unit_cost=Decimal("50.00"),
        )
        db_session.add(item)
        db_session.commit()

        report = ProfitLossReport()
        df = report.generate({"date_range": {"start": "2026-03-06", "end": "2026-03-06"}})

        row = df[df["Invoice #"] == "REC-798-FREE"].iloc[0]
        assert row["Revenue"] == Decimal("0.00")
        assert row["Cost (COGS)"] == Decimal("50.00")
        assert row["SSCL Expense"] == Decimal("0.00")
        assert row["Gross Profit"] == Decimal("-50.00")
        assert row["Margin %"] == "0.00%"

    def test_issue_798_decimal_types_survive_until_output(self, db_session, pl_user, pl_product):
        """Ensure all monetary outputs in DataFrame remain pure Decimal instances."""
        sale = Sale(
            document_number="REC-798-DECIMAL",
            date=datetime(2026, 3, 7, 10, 0, 0),
            total_amount=Decimal("236.00"),
            user_id=pl_user.id,
            tax_vat=Decimal("36.00"),
            tax_sscl=Decimal("5.00"),
            net_revenue=Decimal("195.00"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=pl_product.id,
            qty=Decimal("2.000"),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("236.00"),
            unit_cost=Decimal("45.50"),
        )
        db_session.add(item)
        db_session.commit()

        report = ProfitLossReport()
        df = report.generate({"date_range": {"start": "2026-03-07", "end": "2026-03-07"}})

        row = df[df["Invoice #"] == "REC-798-DECIMAL"].iloc[0]
        assert isinstance(row["Revenue"], Decimal)
        assert isinstance(row["Cost (COGS)"], Decimal)
        assert isinstance(row["SSCL Expense"], Decimal)
        assert isinstance(row["Gross Profit"], Decimal)
        assert row["Revenue"] == Decimal("200.00")  # 195.00 + 5.00
        assert row["Cost (COGS)"] == Decimal("91.00")  # 45.50 * 2
        assert row["SSCL Expense"] == Decimal("5.00")
        assert row["Gross Profit"] == Decimal("104.00")  # 200 - 91 - 5
