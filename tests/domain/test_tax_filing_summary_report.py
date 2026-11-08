import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.status import DocumentStatus, PaymentMethodKind
from cbpos.core.models import Permission, Product, Role, Sale, SaleItem, SalePayment, User
from cbpos.core.reports.definitions.financial_reports import TaxFilingSummaryReport
from cbpos.core.utils.money import round_money


@pytest.fixture
def test_user(db_session):
    suffix = uuid.uuid4().hex[:8]
    permission = Permission(code=f"tax_filing_test_{suffix}")
    role = Role(name=f"TaxFilingRole_{suffix}", permissions=[permission])
    user = User(username=f"tax_filing_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    suffix = uuid.uuid4().hex[:8]
    product = Product(
        name_en=f"FilingProduct_{suffix}",
        barcode=f"FP{suffix}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("100"),
    )
    db_session.add(product)
    db_session.flush()
    return product


class TestTaxFilingSummaryReportIssue796:
    """Issue #796: Tax Filing Summary truth - discounts from stored data, reconciled SSCL base, quarterly view, method_kind."""

    def test_issue_796_discounts_calculated_from_lines_bill_loyalty(self, db_session, test_user, test_product):
        # Sale with:
        # Line 1: qty=2, original_price=100.00, unit_price=80.00, subtotal=160.00 (line discount = 40.00)
        # Bill discount: FIXED 50.00
        # Loyalty discount: 25.00
        # Total discounts = 40.00 + 50.00 + 25.00 = 115.00
        sale = Sale(
            document_number="REC-796-DISC",
            date=datetime(2026, 2, 10, 10, 0, 0),
            total_amount=Decimal("85.00"),
            net_revenue=Decimal("85.00"),
            tax_vat=Decimal("0.00"),
            tax_sscl=Decimal("0.00"),
            user_id=test_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            additional_discount_type="FIXED",
            additional_discount_value=Decimal("50.00"),
            loyalty_points_value=Decimal("25.00"),
        )
        item = SaleItem(
            sale=sale,
            product_id=test_product.id,
            qty=Decimal("2.000"),
            original_price=Decimal("100.00"),
            unit_price=Decimal("80.00"),
            subtotal=Decimal("160.00"),
        )
        payment = SalePayment(
            sale=sale,
            payment_method="Cash",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("85.00"),
        )
        db_session.add_all([sale, item, payment])
        db_session.commit()

        df = TaxFilingSummaryReport().generate({"date_range": {"start": "2026-02-01", "end": "2026-02-28"}})
        descriptions = list(df["Description"])

        # Row for discounts given on sales
        assert any("Discount" in d for d in descriptions)
        disc_row = df[df["Description"].str.contains("Discount", na=False)].iloc[0]
        assert disc_row["Amount"] == Decimal("115.00"), f"Expected 115.00 discounts, got {disc_row['Amount']}"

    def test_issue_796_sscl_liable_turnover_reconciles_with_stored_sscl(self, db_session, test_user, test_product):
        # Liable turnover = sscl_base * (turnover_pct / 100)
        # With sscl_base = 800.00 (distinct from net_revenue = 1000.00), turnover_pct = 50%, rate = 2.50%
        # Liable turnover = 400.00, SSCL = 10.00
        # Reconciles: 400.00 * 0.025 = 10.00
        sale = Sale(
            document_number="REC-796-SSCL",
            date=datetime(2026, 2, 12, 10, 0, 0),
            total_amount=Decimal("1180.00"),
            net_revenue=Decimal("1000.00"),
            tax_vat=Decimal("180.00"),
            tax_sscl=Decimal("10.00"),
            sscl_base=Decimal("800.00"),
            sscl_turnover_pct=Decimal("50.00"),
            sscl_rate=Decimal("2.50"),
            sscl_registered=True,
            vat_registered=True,
            user_id=test_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        payment = SalePayment(
            sale=sale,
            payment_method="Cash",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("1180.00"),
        )
        db_session.add_all([sale, payment])
        db_session.commit()

        df = TaxFilingSummaryReport().generate({"date_range": {"start": "2026-02-01", "end": "2026-02-28"}})

        # Check SSCL section
        sscl_turnover_row = df[df["Description"].str.contains("Liable Turnover", na=False)].iloc[0]
        sscl_liability_row = df[df["Description"] == "SSCL Liability"].iloc[0]

        assert sscl_turnover_row["Amount"] == Decimal("400.00"), "Liable turnover must be sscl_base * 50% = 400.00"
        assert sscl_liability_row["Amount"] == Decimal("10.00")
        assert round_money(sscl_turnover_row["Amount"] * Decimal("0.025")) == sscl_liability_row["Amount"]

    def test_issue_796_quarterly_sscl_view_present(self, db_session, test_user):
        sale = Sale(
            document_number="REC-796-QTR",
            date=datetime(2026, 2, 14, 10, 0, 0),
            total_amount=Decimal("1000.00"),
            net_revenue=Decimal("1000.00"),
            tax_vat=Decimal("0.00"),
            tax_sscl=Decimal("25.00"),
            sscl_base=Decimal("1000.00"),
            sscl_turnover_pct=Decimal("100.00"),
            sscl_rate=Decimal("2.50"),
            sscl_registered=True,
            user_id=test_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.commit()

        df = TaxFilingSummaryReport().generate({"date_range": {"start": "2026-02-01", "end": "2026-02-28"}})
        qtr_rows = df[df["Section"].str.contains("QUARTER", na=False)]
        assert not qtr_rows.empty, "Quarterly SSCL section must be present"
        qtr_turnover = qtr_rows[qtr_rows["Description"].str.contains("Liable Turnover", na=False)].iloc[0]
        assert qtr_turnover["Amount"] == Decimal("1000.00")

    def test_issue_796_payment_summary_uses_method_kind(self, db_session, test_user):
        sale = Sale(
            document_number="REC-796-PMT",
            date=datetime(2026, 2, 15, 10, 0, 0),
            total_amount=Decimal("300.00"),
            net_revenue=Decimal("300.00"),
            tax_vat=Decimal("0.00"),
            tax_sscl=Decimal("0.00"),
            user_id=test_user.id,
            payment_method="SPLIT",
            status=DocumentStatus.COMPLETED,
        )
        p1 = SalePayment(
            sale=sale,
            payment_method="Store Cash Register",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("100.00"),
        )
        p2 = SalePayment(
            sale=sale,
            payment_method="Visa Credit Terminal",
            method_kind=PaymentMethodKind.CARD,
            amount=Decimal("200.00"),
        )
        db_session.add_all([sale, p1, p2])
        db_session.commit()

        df = TaxFilingSummaryReport().generate({"date_range": {"start": "2026-02-01", "end": "2026-02-28"}})
        # Check descriptions and aggregated amounts across entire report
        cash_row = df[df["Description"] == "Cash"].iloc[0]
        card_row = df[df["Description"] == "Card"].iloc[0]
        assert cash_row["Amount"] == Decimal("100.00")
        assert card_row["Amount"] == Decimal("200.00")
