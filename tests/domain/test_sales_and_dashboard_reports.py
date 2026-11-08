"""
Regression tests for Issue #845:
Sales reports, Dashboard, and auto-email count voided sales and count refunds as extra transactions.
Unified sale_filters across reports, dashboard and scheduler.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.status import DocumentStatus, PaymentMethodKind
from cbpos.core.models import Category, Permission, Product, Role, Sale, SaleItem, SalePayment, User
from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport
from cbpos.core.reports.definitions.sales_reports import CashierPerformanceReport, SalesByCategoryReport
from cbpos.core.services.dashboard_service import DashboardService
from cbpos.core.services.report_service import ReportService


@pytest.fixture
def sdr_user(db_session):
    suffix = uuid.uuid4().hex[:8]
    perm = Permission(code=f"sdr_perm_{suffix}")
    role = Role(name=f"SDRRole_{suffix}", permissions=[perm])
    user = User(username=f"cashier_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([perm, role, user])
    db_session.flush()
    return user


@pytest.fixture
def sdr_category(db_session):
    suffix = uuid.uuid4().hex[:8]
    cat = Category(name=f"SDRCat_{suffix}")
    db_session.add(cat)
    db_session.flush()
    return cat


@pytest.fixture
def sdr_products(db_session, sdr_category):
    suffix = uuid.uuid4().hex[:8]
    p1 = Product(
        name_en=f"SDRProd1_{suffix}",
        barcode=f"SDRP1_{suffix}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("100"),
        category_id=sdr_category.id,
    )
    p2 = Product(
        name_en=f"SDRProd2_{suffix}",
        barcode=f"SDRP2_{suffix}",
        price=Decimal("200.00"),
        cost=Decimal("100.00"),
        stock_qty=Decimal("100"),
        category_id=sdr_category.id,
    )
    db_session.add_all([p1, p2])
    db_session.flush()
    return p1, p2


class TestSalesAndDashboardIssue845:
    """Issue #845: Consistent sales totals, transaction counts, and void exclusion."""

    def test_issue_845_void_excluded_daily_sales_and_kpis(self, db_session, sdr_user, sdr_products):
        """Voiding a 3,000 sale leaves true totals (4,200) and count (3), not 7,200 and 4."""
        p1, _ = sdr_products
        today = date.today()
        today_dt = datetime.combine(today, datetime.min.time())

        # 3 completed sales: 1,000, 1,200, 2,000 (total = 4,200)
        for i, amt in enumerate([Decimal("1000.00"), Decimal("1200.00"), Decimal("2000.00")], 1):
            s = Sale(
                document_number=f"REC-845-COMP-{i}",
                date=today_dt.replace(hour=10 + i),
                total_amount=amt,
                net_revenue=amt,
                tax_vat=Decimal("0.00"),
                tax_sscl=Decimal("0.00"),
                user_id=sdr_user.id,
                payment_method="CASH",
                status=DocumentStatus.COMPLETED,
            )
            db_session.add(s)
            db_session.flush()

            it = SaleItem(
                sale_id=s.id,
                product_id=p1.id,
                qty=amt / Decimal("100.00"),
                unit_price=Decimal("100.00"),
                original_price=Decimal("100.00"),
                subtotal=amt,
                unit_cost=Decimal("50.00"),
            )
            pay = SalePayment(
                sale_id=s.id,
                payment_method="CASH",
                method_kind=PaymentMethodKind.CASH,
                amount=amt,
            )
            db_session.add_all([it, pay])

        # 1 voided sale of 3,000
        void_s = Sale(
            document_number="REC-845-VOID-3000",
            date=today_dt.replace(hour=15),
            total_amount=Decimal("3000.00"),
            net_revenue=Decimal("3000.00"),
            tax_vat=Decimal("0.00"),
            tax_sscl=Decimal("0.00"),
            user_id=sdr_user.id,
            payment_method="CASH",
            status=DocumentStatus.VOID,
        )
        db_session.add(void_s)
        db_session.flush()

        void_it = SaleItem(
            sale_id=void_s.id,
            product_id=p1.id,
            qty=Decimal("30.000"),
            unit_price=Decimal("100.00"),
            original_price=Decimal("100.00"),
            subtotal=Decimal("3000.00"),
            unit_cost=Decimal("50.00"),
        )
        void_pay = SalePayment(
            sale_id=void_s.id,
            payment_method="CASH",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("3000.00"),
        )
        db_session.add_all([void_it, void_pay])
        db_session.commit()

        # 1. DailySalesSummaryReport
        today_str = today.strftime("%Y-%m-%d")
        report = DailySalesSummaryReport()
        df = report.generate({"date_range": {"start": today_str, "end": today_str}})

        assert not df.empty
        row = df.iloc[0]
        assert row["Total Sales"] == Decimal("4200.00")
        assert row["Transactions"] == 3

        # 2. Dashboard KPIs
        kpis = DashboardService.get_kpis()
        assert kpis["total_sales"] == Decimal("4200.00")
        assert kpis["txn_count"] == 3

        # 3. Dashboard period stats
        p_stats = DashboardService.get_period_stats(today, today)
        assert p_stats["total_sales"] == Decimal("4200.00")
        assert p_stats["txn_count"] == 3

    def test_issue_845_refund_not_counted_as_transaction(self, db_session, sdr_user, sdr_products):
        """Refunds reduce monetary totals but do NOT increment transaction count."""
        _p1, _ = sdr_products
        test_date = date(2026, 4, 20)
        dt = datetime.combine(test_date, datetime.min.time())

        # 2 completed sales of 100 each
        s1 = Sale(
            document_number="REC-845-R1",
            date=dt.replace(hour=10),
            total_amount=Decimal("100.00"),
            user_id=sdr_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        s2 = Sale(
            document_number="REC-845-R2",
            date=dt.replace(hour=11),
            total_amount=Decimal("100.00"),
            user_id=sdr_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add_all([s1, s2])
        db_session.flush()

        # 1 refund of 40 against s1
        ref = Sale(
            document_number="REF-845-R1",
            date=dt.replace(hour=12),
            total_amount=Decimal("-40.00"),
            user_id=sdr_user.id,
            payment_method="REFUND",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=s1.id,
        )
        db_session.add(ref)
        db_session.commit()

        d_str = test_date.strftime("%Y-%m-%d")
        report = DailySalesSummaryReport()
        df = report.generate({"date_range": {"start": d_str, "end": d_str}})

        row = df.iloc[0]
        # Total sales = 100 + 100 - 40 = 160.00
        assert row["Total Sales"] == Decimal("160.00")
        # Transactions = 2 (not 3!)
        assert row["Transactions"] == 2

    def test_issue_845_cashier_and_category_reports_exclude_voids(
        self, db_session, sdr_user, sdr_category, sdr_products
    ):
        """Cashier performance and sales by category reports exclude voided sales."""
        p1, _ = sdr_products
        test_date = date(2026, 4, 21)
        dt = datetime.combine(test_date, datetime.min.time())

        # 1 Completed sale of 200
        comp_sale = Sale(
            document_number="REC-845-CASHIER-COMP",
            date=dt.replace(hour=10),
            total_amount=Decimal("200.00"),
            user_id=sdr_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(comp_sale)
        db_session.flush()

        comp_item = SaleItem(
            sale_id=comp_sale.id,
            product_id=p1.id,
            qty=Decimal("2.000"),
            unit_price=Decimal("100.00"),
            original_price=Decimal("100.00"),
            subtotal=Decimal("200.00"),
            unit_cost=Decimal("50.00"),
        )
        db_session.add(comp_item)

        # 1 Voided sale of 500
        void_sale = Sale(
            document_number="REC-845-CASHIER-VOID",
            date=dt.replace(hour=11),
            total_amount=Decimal("500.00"),
            user_id=sdr_user.id,
            payment_method="CASH",
            status=DocumentStatus.VOID,
        )
        db_session.add(void_sale)
        db_session.flush()

        void_item = SaleItem(
            sale_id=void_sale.id,
            product_id=p1.id,
            qty=Decimal("5.000"),
            unit_price=Decimal("100.00"),
            original_price=Decimal("100.00"),
            subtotal=Decimal("500.00"),
            unit_cost=Decimal("50.00"),
        )
        db_session.add(void_item)
        db_session.commit()

        d_str = test_date.strftime("%Y-%m-%d")

        # Cashier Performance
        cp_report = CashierPerformanceReport()
        cp_df = cp_report.generate({"date_range": {"start": d_str, "end": d_str}})
        assert not cp_df.empty
        cp_row = cp_df[cp_df["Cashier Name"] == sdr_user.username].iloc[0]
        assert cp_row["Transaction Count"] == 1
        assert cp_row["Total Sales"] == Decimal("200.00")

        # Sales by Category
        cat_report = SalesByCategoryReport()
        cat_df = cat_report.generate({"date_range": {"start": d_str, "end": d_str}})
        assert not cat_df.empty
        cat_row = cat_df[cat_df["Category"] == sdr_category.name].iloc[0]
        assert cat_row["Qty Sold"] == Decimal("2") or cat_row["Qty Sold"] == 2.0
        assert cat_row["Gross Revenue"] == Decimal("200.00")

    def test_issue_845_report_service_daily_sales_excludes_voids(self, db_session, sdr_user):
        """ReportService.get_daily_sales excludes voided sales and uses method_kind."""
        test_date = date(2026, 4, 22)
        dt = datetime.combine(test_date, datetime.min.time())

        # Completed sale of 100 CASH
        s = Sale(
            document_number="REC-845-RS-COMP",
            date=dt.replace(hour=10),
            total_amount=Decimal("100.00"),
            tax_vat=Decimal("15.00"),
            tax_sscl=Decimal("2.50"),
            net_revenue=Decimal("82.50"),
            user_id=sdr_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(s)
        db_session.flush()

        db_session.add(
            SalePayment(
                sale_id=s.id,
                payment_method="CASH",
                method_kind=PaymentMethodKind.CASH,
                amount=Decimal("100.00"),
            )
        )

        # Voided sale of 300 CASH
        void_s = Sale(
            document_number="REC-845-RS-VOID",
            date=dt.replace(hour=11),
            total_amount=Decimal("300.00"),
            tax_vat=Decimal("45.00"),
            tax_sscl=Decimal("7.50"),
            net_revenue=Decimal("247.50"),
            user_id=sdr_user.id,
            payment_method="CASH",
            status=DocumentStatus.VOID,
        )
        db_session.add(void_s)
        db_session.flush()

        db_session.add(
            SalePayment(
                sale_id=void_s.id,
                payment_method="CASH",
                method_kind=PaymentMethodKind.CASH,
                amount=Decimal("300.00"),
            )
        )
        db_session.commit()

        service = ReportService()
        result = service.get_daily_sales(test_date)
        assert result["total_sales"] == Decimal("100.00")
        assert result["total_tax"] == Decimal("17.50")
        assert result["payment_breakdown"].get(PaymentMethodKind.CASH) == Decimal("100.00")

    def test_issue_845_auto_email_report_matches_daily_sales(self, db_session, sdr_user):
        """The report generated by the auto-email scheduler excludes voided sales and matches daily sales."""
        test_date = date.today()
        dt = datetime.combine(test_date, datetime.min.time())

        # 1 valid completed sale
        s = Sale(
            document_number="REC-845-EMAIL-COMP",
            date=dt.replace(hour=9),
            total_amount=Decimal("250.00"),
            user_id=sdr_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        # 1 voided sale
        void_s = Sale(
            document_number="REC-845-EMAIL-VOID",
            date=dt.replace(hour=11),
            total_amount=Decimal("1000.00"),
            user_id=sdr_user.id,
            payment_method="CASH",
            status=DocumentStatus.VOID,
        )
        db_session.add_all([s, void_s])
        db_session.commit()

        # What SchedulerService generates:
        today_str = test_date.strftime("%Y-%m-%d")
        report = DailySalesSummaryReport()
        df = report.generate({"date_range": {"start": today_str, "end": today_str}})

        assert not df.empty
        row = df.iloc[0]
        assert row["Total Sales"] == Decimal("250.00")
        assert row["Transactions"] == 1

        # Matches ReportService
        rs_result = ReportService().get_daily_sales(test_date)
        assert rs_result["total_sales"] == Decimal("250.00")

    def test_issue_845_dashboard_payment_breakdown_uses_method_kind(self, db_session, sdr_user):
        """Dashboard get_payment_breakdown groups by method_kind and excludes voided sales."""
        test_date = date.today()
        dt = datetime.combine(test_date, datetime.min.time())

        # Completed CARD sale
        s1 = Sale(
            document_number="REC-845-PB-COMP",
            date=dt.replace(hour=10),
            total_amount=Decimal("150.00"),
            user_id=sdr_user.id,
            payment_method="VISA_CREDIT",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(s1)
        db_session.flush()

        db_session.add(
            SalePayment(
                sale_id=s1.id,
                payment_method="VISA_CREDIT",
                method_kind=PaymentMethodKind.CARD,
                amount=Decimal("150.00"),
            )
        )

        # Voided CARD sale
        void_s = Sale(
            document_number="REC-845-PB-VOID",
            date=dt.replace(hour=11),
            total_amount=Decimal("400.00"),
            user_id=sdr_user.id,
            payment_method="VISA_CREDIT",
            status=DocumentStatus.VOID,
        )
        db_session.add(void_s)
        db_session.flush()

        db_session.add(
            SalePayment(
                sale_id=void_s.id,
                payment_method="VISA_CREDIT",
                method_kind=PaymentMethodKind.CARD,
                amount=Decimal("400.00"),
            )
        )
        db_session.commit()

        breakdown = DashboardService.get_payment_breakdown()
        b_map = {row["method"]: row["total"] for row in breakdown}
        assert b_map.get(PaymentMethodKind.CARD) == Decimal("150.00")
