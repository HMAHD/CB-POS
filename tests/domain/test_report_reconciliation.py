"""Phase 6 Exit Gate: Report Reconciliation Test.

Builds a single operational day with:
1. Sales across VAT / SSCL combinations:
   - Standard VAT + SSCL
   - VAT-exempt, SSCL-liable
   - SSCL-exempt, VAT-liable
   - Both exempt (zero tax)
2. A voided sale (status=VOID)
3. A partial refund and a full refund
4. A bill discount and a loyalty redemption

Asserts that:
- Tax Liability Report
- Tax Filing Summary Report
- Profit & Loss Report
- Daily Sales Summary Report
- Dashboard KPIs & Tax Summary
- Cash Flow Report
all agree on revenue, VAT, SSCL, refunds, and transaction counts to the exact cent.
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from cbpos.core.constants.status import DocumentStatus, PaymentMethodKind
from cbpos.core.models import Permission, Product, Role, Sale, SaleItem, SalePayment, User
from cbpos.core.reports.definitions.cash_flow_report import CashFlowReport
from cbpos.core.reports.definitions.financial_reports import (
    ProfitLossReport,
    TaxFilingSummaryReport,
    TaxLiabilityReport,
)
from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport
from cbpos.core.services.dashboard_service import DashboardService


def test_phase_6_exit_gate_report_reconciliation(db_session):
    today = date.today()
    day_str = today.strftime("%Y-%m-%d")
    t10 = datetime.combine(today, time(10, 0, 0))
    t11 = datetime.combine(today, time(11, 0, 0))
    t12 = datetime.combine(today, time(12, 0, 0))
    t13 = datetime.combine(today, time(13, 0, 0))
    t14 = datetime.combine(today, time(14, 0, 0))
    t15 = datetime.combine(today, time(15, 0, 0))
    t16 = datetime.combine(today, time(16, 0, 0))
    t17 = datetime.combine(today, time(17, 0, 0))

    suffix = uuid.uuid4().hex[:8]
    perm = Permission(code=f"recon_perm_{suffix}")
    role = Role(name=f"ReconRole_{suffix}", permissions=[perm])
    user = User(username=f"recon_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([perm, role, user])
    db_session.flush()

    # Products
    # P_std: VAT + SSCL (Cost 40, Price 118)
    p_std = Product(
        name_en=f"Prod_Std_{suffix}",
        barcode=f"PSTD_{suffix}",
        price=Decimal("118.00"),
        cost=Decimal("40.00"),
        stock_qty=Decimal("100"),
        is_active=True,
    )
    # P_vat_ex: VAT-exempt, SSCL-liable (Cost 30, Price 102.50)
    p_vat_ex = Product(
        name_en=f"Prod_VatEx_{suffix}",
        barcode=f"PVAT_{suffix}",
        price=Decimal("102.50"),
        cost=Decimal("30.00"),
        stock_qty=Decimal("100"),
        is_active=True,
    )
    # P_sscl_ex: SSCL-exempt, VAT-liable (Cost 50, Price 118.00)
    p_sscl_ex = Product(
        name_en=f"Prod_SsclEx_{suffix}",
        barcode=f"PSSCL_{suffix}",
        price=Decimal("118.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("100"),
        is_active=True,
    )
    # P_both_ex: Both exempt (Cost 20, Price 50.00)
    p_both_ex = Product(
        name_en=f"Prod_BothEx_{suffix}",
        barcode=f"PBOTH_{suffix}",
        price=Decimal("50.00"),
        cost=Decimal("20.00"),
        stock_qty=Decimal("100"),
        is_active=True,
    )
    db_session.add_all([p_std, p_vat_ex, p_sscl_ex, p_both_ex])
    db_session.flush()

    # -------------------------------------------------------------------------
    # 1. Sales across VAT / SSCL combinations
    # -------------------------------------------------------------------------

    # Sale 1: Standard VAT (18%) + SSCL (2.5%)
    # 2x P_std @ 118 = 236.00
    # Net = 195.00, VAT = 36.00, SSCL = 5.00
    # COGS = 2 * 40 = 80.00
    # Paid CASH: 236.00
    sale1 = Sale(
        document_number="REC-RECON-001",
        date=t10,
        total_amount=Decimal("236.00"),
        net_revenue=Decimal("195.00"),
        tax_vat=Decimal("36.00"),
        tax_sscl=Decimal("5.00"),
        taxable_amount=Decimal("200.00"),
        vat_exempt_amount=Decimal("0.00"),
        sscl_base=Decimal("200.00"),
        vat_rate=Decimal("18.00"),
        sscl_rate=Decimal("2.50"),
        sscl_turnover_pct=Decimal("100.00"),
        user_id=user.id,
        payment_method="CASH",
        status=DocumentStatus.COMPLETED,
    )
    db_session.add(sale1)
    db_session.flush()

    s1_item = SaleItem(
        sale_id=sale1.id,
        product_id=p_std.id,
        qty=Decimal("2.000"),
        unit_price=Decimal("118.00"),
        original_price=Decimal("118.00"),
        subtotal=Decimal("236.00"),
        unit_cost=Decimal("40.00"),
        vat_exempt=False,
        sscl_exempt=False,
    )
    s1_pay = SalePayment(
        sale_id=sale1.id,
        payment_method="CASH",
        method_kind=PaymentMethodKind.CASH,
        amount=Decimal("236.00"),
    )
    db_session.add_all([s1_item, s1_pay])

    # Sale 2: VAT-exempt, SSCL-liable
    # 1x P_vat_ex @ 102.50 = 102.50
    # Net = 100.00, VAT = 0.00, SSCL = 2.50
    # COGS = 30.00
    # Paid CARD: 102.50
    sale2 = Sale(
        document_number="REC-RECON-002",
        date=t11,
        total_amount=Decimal("102.50"),
        net_revenue=Decimal("100.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("2.50"),
        taxable_amount=Decimal("0.00"),
        vat_exempt_amount=Decimal("100.00"),
        sscl_base=Decimal("100.00"),
        vat_rate=Decimal("0.00"),
        sscl_rate=Decimal("2.50"),
        sscl_turnover_pct=Decimal("100.00"),
        user_id=user.id,
        payment_method="CARD",
        status=DocumentStatus.COMPLETED,
    )
    db_session.add(sale2)
    db_session.flush()

    s2_item = SaleItem(
        sale_id=sale2.id,
        product_id=p_vat_ex.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("102.50"),
        original_price=Decimal("102.50"),
        subtotal=Decimal("102.50"),
        unit_cost=Decimal("30.00"),
        vat_exempt=True,
        sscl_exempt=False,
    )
    s2_pay = SalePayment(
        sale_id=sale2.id,
        payment_method="CARD",
        method_kind=PaymentMethodKind.CARD,
        amount=Decimal("102.50"),
    )
    db_session.add_all([s2_item, s2_pay])

    # Sale 3: SSCL-exempt, VAT-liable
    # 1x P_sscl_ex @ 118.00 = 118.00
    # Net = 100.00, VAT = 18.00, SSCL = 0.00
    # COGS = 50.00
    # Paid TRANSFER: 118.00
    sale3 = Sale(
        document_number="REC-RECON-003",
        date=t12,
        total_amount=Decimal("118.00"),
        net_revenue=Decimal("100.00"),
        tax_vat=Decimal("18.00"),
        tax_sscl=Decimal("0.00"),
        taxable_amount=Decimal("100.00"),
        vat_exempt_amount=Decimal("0.00"),
        sscl_base=Decimal("0.00"),
        vat_rate=Decimal("18.00"),
        sscl_rate=Decimal("0.00"),
        sscl_turnover_pct=Decimal("0.00"),
        user_id=user.id,
        payment_method="TRANSFER",
        status=DocumentStatus.COMPLETED,
    )
    db_session.add(sale3)
    db_session.flush()

    s3_item = SaleItem(
        sale_id=sale3.id,
        product_id=p_sscl_ex.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("118.00"),
        original_price=Decimal("118.00"),
        subtotal=Decimal("118.00"),
        unit_cost=Decimal("50.00"),
        vat_exempt=False,
        sscl_exempt=True,
    )
    s3_pay = SalePayment(
        sale_id=sale3.id,
        payment_method="TRANSFER",
        method_kind=PaymentMethodKind.TRANSFER,
        amount=Decimal("118.00"),
    )
    db_session.add_all([s3_item, s3_pay])

    # Sale 4: Both exempt (zero tax)
    # 1x P_both_ex @ 50.00 = 50.00
    # Net = 50.00, VAT = 0.00, SSCL = 0.00
    # COGS = 20.00
    # Paid CASH: 50.00
    sale4 = Sale(
        document_number="REC-RECON-004",
        date=t13,
        total_amount=Decimal("50.00"),
        net_revenue=Decimal("50.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        taxable_amount=Decimal("0.00"),
        vat_exempt_amount=Decimal("50.00"),
        sscl_base=Decimal("0.00"),
        vat_rate=Decimal("0.00"),
        sscl_rate=Decimal("0.00"),
        sscl_turnover_pct=Decimal("0.00"),
        user_id=user.id,
        payment_method="CASH",
        status=DocumentStatus.COMPLETED,
    )
    db_session.add(sale4)
    db_session.flush()

    s4_item = SaleItem(
        sale_id=sale4.id,
        product_id=p_both_ex.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("50.00"),
        original_price=Decimal("50.00"),
        subtotal=Decimal("50.00"),
        unit_cost=Decimal("20.00"),
        vat_exempt=True,
        sscl_exempt=True,
    )
    s4_pay = SalePayment(
        sale_id=sale4.id,
        payment_method="CASH",
        method_kind=PaymentMethodKind.CASH,
        amount=Decimal("50.00"),
    )
    db_session.add_all([s4_item, s4_pay])

    # -------------------------------------------------------------------------
    # 2. Voided Sale (must contribute ZERO to all reports)
    # -------------------------------------------------------------------------
    sale_void = Sale(
        document_number="REC-RECON-VOID",
        date=t14,
        total_amount=Decimal("118.00"),
        net_revenue=Decimal("97.50"),
        tax_vat=Decimal("18.00"),
        tax_sscl=Decimal("2.50"),
        taxable_amount=Decimal("100.00"),
        vat_exempt_amount=Decimal("0.00"),
        sscl_base=Decimal("100.00"),
        vat_rate=Decimal("18.00"),
        sscl_rate=Decimal("2.50"),
        user_id=user.id,
        payment_method="CASH",
        status=DocumentStatus.VOID,
    )
    db_session.add(sale_void)
    db_session.flush()

    sv_item = SaleItem(
        sale_id=sale_void.id,
        product_id=p_std.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("118.00"),
        original_price=Decimal("118.00"),
        subtotal=Decimal("118.00"),
        unit_cost=Decimal("40.00"),
    )
    sv_pay = SalePayment(
        sale_id=sale_void.id,
        payment_method="CASH",
        method_kind=PaymentMethodKind.CASH,
        amount=Decimal("118.00"),
    )
    db_session.add_all([sv_item, sv_pay])

    # -------------------------------------------------------------------------
    # 3. Refunds: 1 partial refund (Sale 1) and 1 full refund (Sale 2)
    # -------------------------------------------------------------------------

    # Partial refund of Sale 1: refund 1x P_std (118.00)
    # Refund Net = -97.50, VAT = -18.00, SSCL = -2.50, Total = -118.00
    # COGS reverse = -40.00
    # Paid CASH: -118.00
    ref_partial = Sale(
        document_number="REF-RECON-PARTIAL",
        date=t15,
        total_amount=Decimal("-118.00"),
        net_revenue=Decimal("-97.50"),
        tax_vat=Decimal("-18.00"),
        tax_sscl=Decimal("-2.50"),
        taxable_amount=Decimal("-100.00"),
        vat_exempt_amount=Decimal("0.00"),
        sscl_base=Decimal("-100.00"),
        vat_rate=Decimal("18.00"),
        sscl_rate=Decimal("2.50"),
        sscl_turnover_pct=Decimal("100.00"),
        user_id=user.id,
        payment_method="REFUND",
        status=DocumentStatus.COMPLETED,
        refund_of_sale_id=sale1.id,
    )
    db_session.add(ref_partial)
    db_session.flush()

    rp_item = SaleItem(
        sale_id=ref_partial.id,
        product_id=p_std.id,
        qty=Decimal("-1.000"),
        unit_price=Decimal("118.00"),
        original_price=Decimal("118.00"),
        subtotal=Decimal("-118.00"),
        unit_cost=Decimal("40.00"),
        refund_of_item_id=s1_item.id,
    )
    rp_pay = SalePayment(
        sale_id=ref_partial.id,
        payment_method="CASH",
        method_kind=PaymentMethodKind.CASH,
        amount=Decimal("-118.00"),
    )
    db_session.add_all([rp_item, rp_pay])

    # Full refund of Sale 2: refund all 102.50
    # Refund Net = -100.00, VAT = 0.00, SSCL = -2.50, Total = -102.50
    # COGS reverse = -30.00
    # Paid CARD: -102.50
    ref_full = Sale(
        document_number="REF-RECON-FULL",
        date=t16,
        total_amount=Decimal("-102.50"),
        net_revenue=Decimal("-100.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("-2.50"),
        taxable_amount=Decimal("0.00"),
        vat_exempt_amount=Decimal("-100.00"),
        sscl_base=Decimal("-100.00"),
        vat_rate=Decimal("0.00"),
        sscl_rate=Decimal("2.50"),
        sscl_turnover_pct=Decimal("100.00"),
        user_id=user.id,
        payment_method="REFUND",
        status=DocumentStatus.COMPLETED,
        refund_of_sale_id=sale2.id,
    )
    db_session.add(ref_full)
    db_session.flush()

    rf_item = SaleItem(
        sale_id=ref_full.id,
        product_id=p_vat_ex.id,
        qty=Decimal("-1.000"),
        unit_price=Decimal("102.50"),
        original_price=Decimal("102.50"),
        subtotal=Decimal("-102.50"),
        unit_cost=Decimal("30.00"),
        refund_of_item_id=s2_item.id,
    )
    rf_pay = SalePayment(
        sale_id=ref_full.id,
        payment_method="CARD",
        method_kind=PaymentMethodKind.CARD,
        amount=Decimal("-102.50"),
    )
    db_session.add_all([rf_item, rf_pay])

    # -------------------------------------------------------------------------
    # 4. Bill Discount and Loyalty Redemption
    # -------------------------------------------------------------------------

    # Sale 6: Bill discount of 10.00
    # 1x P_both_ex @ 50.00, Bill discount = 10.00 -> Total = 40.00
    # Net = 40.00, VAT = 0, SSCL = 0, COGS = 20.00
    # Paid CASH: 40.00
    sale6 = Sale(
        document_number="REC-RECON-006",
        date=t17,
        total_amount=Decimal("40.00"),
        net_revenue=Decimal("40.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        taxable_amount=Decimal("0.00"),
        vat_exempt_amount=Decimal("40.00"),
        sscl_base=Decimal("0.00"),
        additional_discount_type="FIXED",
        additional_discount_value=Decimal("10.00"),
        user_id=user.id,
        payment_method="CASH",
        status=DocumentStatus.COMPLETED,
    )
    db_session.add(sale6)
    db_session.flush()

    s6_item = SaleItem(
        sale_id=sale6.id,
        product_id=p_both_ex.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("50.00"),
        original_price=Decimal("50.00"),
        subtotal=Decimal("50.00"),
        unit_cost=Decimal("20.00"),
        vat_exempt=True,
        sscl_exempt=True,
    )
    s6_pay = SalePayment(
        sale_id=sale6.id,
        payment_method="CASH",
        method_kind=PaymentMethodKind.CASH,
        amount=Decimal("40.00"),
    )
    db_session.add_all([s6_item, s6_pay])

    # Sale 7: Loyalty point redemption of 20.00 (ADR 0002)
    # 1x P_both_ex @ 50.00, Loyalty redemption = 20.00 -> Total = 30.00
    # Net = 30.00, VAT = 0, SSCL = 0, COGS = 20.00
    # Paid CASH: 30.00
    sale7 = Sale(
        document_number="REC-RECON-007",
        date=t17,
        total_amount=Decimal("30.00"),
        net_revenue=Decimal("30.00"),
        tax_vat=Decimal("0.00"),
        tax_sscl=Decimal("0.00"),
        taxable_amount=Decimal("0.00"),
        vat_exempt_amount=Decimal("30.00"),
        sscl_base=Decimal("0.00"),
        loyalty_points_value=Decimal("20.00"),
        user_id=user.id,
        payment_method="CASH",
        status=DocumentStatus.COMPLETED,
    )
    db_session.add(sale7)
    db_session.flush()

    s7_item = SaleItem(
        sale_id=sale7.id,
        product_id=p_both_ex.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("50.00"),
        original_price=Decimal("50.00"),
        subtotal=Decimal("50.00"),
        unit_cost=Decimal("20.00"),
        vat_exempt=True,
        sscl_exempt=True,
    )
    s7_pay = SalePayment(
        sale_id=sale7.id,
        payment_method="CASH",
        method_kind=PaymentMethodKind.CASH,
        amount=Decimal("30.00"),
    )
    db_session.add_all([s7_item, s7_pay])

    db_session.commit()

    # -------------------------------------------------------------------------
    # EXPECTED VALUES BREAKDOWN
    # -------------------------------------------------------------------------
    # Sales (non-refund completed):
    # Sale 1: Total 236.00, Net 195.00, VAT 36.00, SSCL 5.00, COGS 80.00, Cash 236.00
    # Sale 2: Total 102.50, Net 100.00, VAT  0.00, SSCL 2.50, COGS 30.00, Card 102.50
    # Sale 3: Total 118.00, Net 100.00, VAT 18.00, SSCL 0.00, COGS 50.00, Transfer 118.00
    # Sale 4: Total  50.00, Net  50.00, VAT  0.00, SSCL 0.00, COGS 20.00, Cash 50.00
    # Sale 6: Total  40.00, Net  40.00, VAT  0.00, SSCL 0.00, COGS 20.00, Cash 40.00 (Disc 10)
    # Sale 7: Total  30.00, Net  30.00, VAT  0.00, SSCL 0.00, COGS 20.00, Cash 30.00 (Loyalty 20)
    # Total Sales (MRP without discount): 236 + 102.50 + 118 + 50 + 50 + 50 = 606.50
    # Sales Total (Paid): 236.00 + 102.50 + 118.00 + 50.00 + 40.00 + 30.00 = 576.50
    # Sales Net: 195.00 + 100.00 + 100.00 + 50.00 + 40.00 + 30.00 = 515.00
    # Sales VAT: 36.00 + 0.00 + 18.00 + 0.00 + 0.00 + 0.00 = 54.00
    # Sales SSCL: 5.00 + 2.50 + 0.00 + 0.00 + 0.00 + 0.00 = 7.50
    # Sales COGS: 80.00 + 30.00 + 50.00 + 20.00 + 20.00 + 20.00 = 220.00
    # Sales Count: 6 transactions

    # Refunds:
    # Ref Partial: Total -118.00, Net -97.50, VAT -18.00, SSCL -2.50, COGS -40.00, Cash -118.00
    # Ref Full:    Total -102.50, Net -100.00, VAT 0.00, SSCL -2.50, COGS -30.00, Card -102.50
    # Total Refunds: 118.00 + 102.50 = 220.50
    # Refunds Net: -197.50
    # Refunds VAT: -18.00
    # Refunds SSCL: -5.00
    # Refunds COGS: -70.00
    # Refunds Count: 2

    # NET TOTALS (Sales - Refunds):
    # Total Revenue (Paid/Gross): 576.50 - 220.50 = 356.00
    # Net Revenue: 515.00 - 197.50 = 317.50
    # VAT: 54.00 - 18.00 = 36.00
    # SSCL: 7.50 - 5.00 = 2.50
    # Total Tax: 36.00 + 2.50 = 38.50
    # P&L Revenue (Net + SSCL): 317.50 + 2.50 = 320.00
    # P&L COGS: 220.00 - 70.00 = 150.00
    # P&L SSCL Expense: 2.50
    # P&L Gross Profit: 320.00 - 150.00 - 2.50 = 167.50
    # Transaction Count: 6 (refunds do not increment)

    expected_total_sales = Decimal("356.00")
    expected_net_revenue = Decimal("317.50")
    expected_vat = Decimal("36.00")
    expected_sscl = Decimal("2.50")
    expected_total_tax = Decimal("38.50")
    expected_pl_revenue = Decimal("320.00")
    expected_pl_cogs = Decimal("150.00")
    expected_pl_gross_profit = Decimal("167.50")
    expected_txn_count = 6

    # =========================================================================
    # RECONCILIATION ASSERTIONS ACROSS ALL REPORTS
    # =========================================================================
    date_filter = {"date_range": {"start": day_str, "end": day_str}}

    # 1. Tax Liability Report
    df_tax_liab = TaxLiabilityReport().generate(date_filter)
    assert not df_tax_liab.empty
    row_tax_totals = df_tax_liab[df_tax_liab["Invoice #"] == "NET TOTALS"].iloc[0]
    assert row_tax_totals["Total Sale"] == expected_total_sales
    assert row_tax_totals["Net Revenue"] == expected_net_revenue
    assert row_tax_totals["VAT"] == expected_vat
    assert row_tax_totals["SSCL"] == expected_sscl
    assert row_tax_totals["Total Tax"] == expected_total_tax

    # 2. Tax Filing Summary Report
    df_tax_filing = TaxFilingSummaryReport().generate(date_filter)
    assert not df_tax_filing.empty
    filing_map = dict(zip(df_tax_filing["Description"], df_tax_filing["Amount"], strict=False))
    assert filing_map["Net Sales"] == expected_total_sales
    assert filing_map["VAT Liability"] == expected_vat
    assert filing_map["SSCL Liability"] == expected_sscl
    assert filing_map["Number of Sales"] == Decimal(str(expected_txn_count))
    assert filing_map["Number of Refunds"] == Decimal("2")
    assert filing_map["Total Refunds"] == Decimal("220.50")
    assert filing_map["Discounts given on sales"] == Decimal("30.00")  # 10 bill + 20 loyalty

    # 3. Profit & Loss Report
    df_pl = ProfitLossReport().generate(date_filter)
    assert not df_pl.empty
    row_pl_total = df_pl[df_pl["Invoice #"] == "TOTAL"].iloc[0]
    assert row_pl_total["Revenue"] == expected_pl_revenue
    assert row_pl_total["Cost (COGS)"] == expected_pl_cogs
    assert row_pl_total["SSCL Expense"] == expected_sscl
    assert row_pl_total["Gross Profit"] == expected_pl_gross_profit

    # 4. Daily Sales Summary Report
    df_daily = DailySalesSummaryReport().generate(date_filter)
    assert not df_daily.empty
    row_daily = df_daily.iloc[0]
    assert row_daily["Total Sales"] == expected_total_sales
    assert row_daily["Transactions"] == expected_txn_count

    # 5. Dashboard KPIs and Tax Summary
    kpis = DashboardService.get_kpis()
    tax_summary = DashboardService.get_today_tax_summary()
    assert kpis["total_sales"] == expected_total_sales
    assert kpis["txn_count"] == expected_txn_count
    assert tax_summary["vat"] == expected_vat
    assert tax_summary["sscl"] == expected_sscl
    assert tax_summary["net_revenue"] == expected_net_revenue

    # 6. Cash Flow Report
    df_cash = CashFlowReport().generate(date_filter)
    assert not df_cash.empty
    cash_map = dict(zip(df_cash["Category"], df_cash["Amount"], strict=False))
    # Cash tender: in = 236 + 50 + 40 + 30 = 356.00; refund = 118.00; net cash = 238.00
    assert cash_map["Cash Sales"] == Decimal("356.00")
    assert cash_map["Cash Refunds"] == Decimal("118.00")
    assert cash_map["Net Cash"] == Decimal("238.00")
    # Card tender: in = 102.50; refund = 102.50; net card = 0.00
    assert cash_map["Card Sales"] == Decimal("102.50")
    assert cash_map["Card Refunds"] == Decimal("102.50")
    assert cash_map["Net Card"] == Decimal("0.00")
    # Transfer tender: in = 118.00; refund = 0; net transfer = 118.00
    assert cash_map["Bank Transfer Sales"] == Decimal("118.00")
    assert cash_map["Net Bank Transfer"] == Decimal("118.00")
    # Total Net across all tenders = 238.00 + 0.00 + 118.00 = 356.00 == Net Total Sales!
    total_net_cashflow = cash_map["Net Cash"] + cash_map["Net Card"] + cash_map["Net Bank Transfer"]
    assert total_net_cashflow == expected_total_sales
