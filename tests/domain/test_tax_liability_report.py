from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Permission, Product, Role, Sale, Supplier, User
from cbpos.core.reports.definitions.financial_reports import TaxLiabilityReport
from cbpos.core.services.purchase_service import PurchaseService
from cbpos.i18n import _t

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"tax_liab_test_{suffix}")
    role = Role(name=f"TaxLiabRole_{suffix}", permissions=[permission])
    user = User(username=f"tax_liab_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"Tax Supplier {_counter}")
    db_session.add(supplier)
    db_session.flush()
    return supplier


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(
        name_en=f"TaxProduct_{_counter}",
        barcode=f"TXP{_counter:04d}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("100"),
    )
    db_session.add(product)
    db_session.flush()
    return product


class TestTaxLiabilityReportIssue795:
    """Issue #795: Tax Liability Report truth - exclude voids, separate refunds, dynamic headers, per-rate breakdown."""

    def test_issue_795_column_headers_without_fixed_rates(self):
        hints = TaxLiabilityReport().get_render_hints()
        cols = hints["columns"]
        assert "VAT" in cols, "Column 'VAT' should replace hardcoded 'VAT (18%)'"
        assert "SSCL" in cols, "Column 'SSCL' should replace hardcoded 'SSCL (2.5%)'"
        assert "VAT (18%)" not in cols
        assert "SSCL (2.5%)" not in cols
        assert cols["VAT"]["label_key"] == "reports.col_vat"
        assert cols["SSCL"]["label_key"] == "reports.col_sscl"

    def test_issue_795_voided_sale_excluded(self, db_session, test_user, test_supplier, test_product):
        # 1 completed sale
        sale_ok = Sale(
            document_number="REC-795-001",
            date=datetime(2026, 2, 10, 10, 0, 0),
            total_amount=Decimal("1180.00"),
            user_id=test_user.id,
            tax_vat=Decimal("180.00"),
            tax_sscl=Decimal("25.00"),
            net_revenue=Decimal("1000.00"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            vat_rate=Decimal("18.00"),
            sscl_rate=Decimal("2.50"),
        )
        # 1 voided sale
        sale_void = Sale(
            document_number="REC-795-VOID",
            date=datetime(2026, 2, 11, 11, 0, 0),
            total_amount=Decimal("1180.00"),
            user_id=test_user.id,
            tax_vat=Decimal("180.00"),
            tax_sscl=Decimal("25.00"),
            net_revenue=Decimal("1000.00"),
            payment_method="CASH",
            status=DocumentStatus.VOID,
            vat_rate=Decimal("18.00"),
            sscl_rate=Decimal("2.50"),
        )
        db_session.add_all([sale_ok, sale_void])
        db_session.commit()

        # Input VAT from completed purchase
        purchase = PurchaseService.create_purchase(test_supplier.id, "PUR-795-01", test_user.id)
        purchase.date = datetime(2026, 2, 10, 10, 0, 0)
        PurchaseService.commit_purchase(
            purchase.id,
            [{"product_id": test_product.id, "qty": Decimal("10"), "cost": Decimal("50")}],
            input_vat=Decimal("50.00"),
        )
        purchase.date = datetime(2026, 2, 10, 10, 0, 0)
        db_session.commit()

        report = TaxLiabilityReport()
        df = report.generate({"date_range": {"start": "2026-02-01", "end": "2026-02-28"}})

        invoices = list(df["Invoice #"])
        assert "REC-795-001" in invoices
        assert "REC-795-VOID" not in invoices, "Voided sale must be excluded from Tax Liability report"

        # Check total sales row
        sales_row = df[df["Invoice #"] == "TOTAL SALES"].iloc[0]
        assert sales_row["Total Sale"] == Decimal("1180.00")
        assert sales_row["VAT"] == Decimal("180.00")

        # Summary row should only have 180 - 50 = 130
        summary_row = df[df["Invoice #"] == "NET VAT LIABILITY"].iloc[0]
        assert summary_row["VAT"] == Decimal("180.00")
        assert summary_row["Input VAT"] == Decimal("50.00")
        assert summary_row["Net VAT Liability"] == Decimal("130.00")

    def test_issue_795_refund_shown_separately_and_netted(self, db_session, test_user, test_product):
        # 1 completed sale
        sale = Sale(
            document_number="REC-795-002",
            date=datetime(2026, 2, 12, 10, 0, 0),
            total_amount=Decimal("1180.00"),
            user_id=test_user.id,
            tax_vat=Decimal("180.00"),
            tax_sscl=Decimal("25.00"),
            net_revenue=Decimal("1000.00"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            vat_rate=Decimal("18.00"),
            sscl_rate=Decimal("2.50"),
        )
        db_session.add(sale)
        db_session.commit()

        # 1 refund document
        refund = Sale(
            document_number="REF-795-001",
            date=datetime(2026, 2, 13, 11, 0, 0),
            total_amount=Decimal("-590.00"),
            user_id=test_user.id,
            tax_vat=Decimal("-90.00"),
            tax_sscl=Decimal("-12.50"),
            net_revenue=Decimal("-500.00"),
            payment_method="REFUND",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=sale.id,
            vat_rate=Decimal("18.00"),
            sscl_rate=Decimal("2.50"),
        )
        db_session.add(refund)
        db_session.commit()

        df = TaxLiabilityReport().generate({"date_range": {"start": "2026-02-01", "end": "2026-02-28"}})

        invoices = list(df["Invoice #"])
        assert "REC-795-002" in invoices
        assert "TOTAL SALES" in invoices
        assert "REF-795-001" in invoices
        assert "TOTAL REFUNDS" in invoices
        assert "NET TOTALS" in invoices
        assert "NET VAT LIABILITY" in invoices

        # Verify ordering: sales section before refunds section
        assert invoices.index("REC-795-002") < invoices.index("TOTAL SALES")
        assert invoices.index("TOTAL SALES") < invoices.index("REF-795-001")
        assert invoices.index("REF-795-001") < invoices.index("TOTAL REFUNDS")
        assert invoices.index("TOTAL REFUNDS") < invoices.index("NET TOTALS")

        total_sales_row = df[df["Invoice #"] == "TOTAL SALES"].iloc[0]
        assert total_sales_row["Total Sale"] == Decimal("1180.00")
        assert total_sales_row["VAT"] == Decimal("180.00")

        total_refunds_row = df[df["Invoice #"] == "TOTAL REFUNDS"].iloc[0]
        assert total_refunds_row["Total Sale"] == Decimal("-590.00")
        assert total_refunds_row["VAT"] == Decimal("-90.00")

        net_totals_row = df[df["Invoice #"] == "NET TOTALS"].iloc[0]
        assert net_totals_row["Total Sale"] == Decimal("590.00")
        assert net_totals_row["Net Revenue"] == Decimal("500.00")
        assert net_totals_row["VAT"] == Decimal("90.00")
        assert net_totals_row["SSCL"] == Decimal("12.50")
        assert net_totals_row["Total Tax"] == Decimal("102.50")

        summary_row = df[df["Invoice #"] == "NET VAT LIABILITY"].iloc[0]
        assert summary_row["VAT"] == Decimal("90.00")
        assert summary_row["Net VAT Liability"] == Decimal("90.00")

    def test_issue_795_two_rates_in_period_breakdown(self, db_session, test_user):
        # Sale at 18%
        sale_18 = Sale(
            document_number="REC-795-RATE18",
            date=datetime(2026, 2, 14, 10, 0, 0),
            total_amount=Decimal("1180.00"),
            user_id=test_user.id,
            tax_vat=Decimal("180.00"),
            tax_sscl=Decimal("0.00"),
            net_revenue=Decimal("1000.00"),
            taxable_amount=Decimal("1180.00"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            vat_rate=Decimal("18.00"),
        )
        # Sale at 15%
        sale_15 = Sale(
            document_number="REC-795-RATE15",
            date=datetime(2026, 2, 15, 10, 0, 0),
            total_amount=Decimal("1150.00"),
            user_id=test_user.id,
            tax_vat=Decimal("150.00"),
            tax_sscl=Decimal("0.00"),
            net_revenue=Decimal("1000.00"),
            taxable_amount=Decimal("1150.00"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            vat_rate=Decimal("15.00"),
        )
        db_session.add_all([sale_18, sale_15])
        db_session.commit()

        df = TaxLiabilityReport().generate({"date_range": {"start": "2026-02-01", "end": "2026-02-28"}})
        invoices = list(df["Invoice #"])

        # Rate breakdown section must exist because there are 2 rates
        breakdown_header = _t("reports.vat_by_rate")
        assert breakdown_header in invoices or "VAT by rate" in invoices
        assert any("VAT @ 15%" in inv for inv in invoices)
        assert any("VAT @ 18%" in inv for inv in invoices)

        row_15 = df[df["Invoice #"] == "VAT @ 15%"].iloc[0]
        assert row_15["Net Revenue"] == Decimal("1000.00")
        assert row_15["VAT"] == Decimal("150.00")

        row_18 = df[df["Invoice #"] == "VAT @ 18%"].iloc[0]
        assert row_18["Net Revenue"] == Decimal("1000.00")
        assert row_18["VAT"] == Decimal("180.00")

    def test_single_rate_in_period_suppresses_breakdown(self, db_session, test_user):
        # 2 Sales both at 18%
        sale1 = Sale(
            document_number="REC-795-SINGLE1",
            date=datetime(2026, 2, 16, 10, 0, 0),
            total_amount=Decimal("1180.00"),
            user_id=test_user.id,
            tax_vat=Decimal("180.00"),
            tax_sscl=Decimal("0.00"),
            net_revenue=Decimal("1000.00"),
            taxable_amount=Decimal("1180.00"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            vat_rate=Decimal("18.00"),
        )
        sale2 = Sale(
            document_number="REC-795-SINGLE2",
            date=datetime(2026, 2, 17, 10, 0, 0),
            total_amount=Decimal("590.00"),
            user_id=test_user.id,
            tax_vat=Decimal("90.00"),
            tax_sscl=Decimal("0.00"),
            net_revenue=Decimal("500.00"),
            taxable_amount=Decimal("590.00"),
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            vat_rate=Decimal("18.00"),
        )
        db_session.add_all([sale1, sale2])
        db_session.commit()

        df = TaxLiabilityReport().generate({"date_range": {"start": "2026-02-01", "end": "2026-02-28"}})
        invoices = list(df["Invoice #"])

        breakdown_header = _t("reports.vat_by_rate")
        assert breakdown_header not in invoices
        assert not any("VAT @" in inv for inv in invoices)
