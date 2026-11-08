# Phase 6 Batch 6.2 Design Note: Tax Reporting and Invoice History

## Overview
Batch 6.2 implements truthful tax reporting and historical accuracy across reprints and reports (#811, #795, #796).

## 1. Shared Sale Filters (`cbpos/core/reports/sale_filters.py`)
Composable SQLAlchemy binary expressions for uniform document classification:
- `completed_sales()`: `and_(Sale.status == DocumentStatus.COMPLETED, Sale.refund_of_sale_id.is_(None), Sale.payment_method != "REFUND")`
- `refund_documents()`: `and_(Sale.status == DocumentStatus.COMPLETED, or_(Sale.refund_of_sale_id.isnot(None), Sale.payment_method == "REFUND"))`
- `revenue_documents()`: `and_(Sale.status == DocumentStatus.COMPLETED)` (encompasses ordinary completed sales and refunds, excludes voids)
- `voided()`: `Sale.status == DocumentStatus.VOID`

No queries execute inside filter functions. Returns clauses for use in `.filter(*clauses)`.

## 2. Historical Rate Resolution & Reprints (#811)
- Reprints on thermal (`SalesReceiptBuilder`) and A4 (`InvoiceService`) read `sale.vat_rate` stored at checkout.
- A legitimate stored `Decimal("0.00")` is preserved as 0.00% (never replaced with default).
- Fallback only if `sale.vat_rate is None` (unmigrated legacy rows): read `tax_vat_rate` from `ConfigService` and log a single warning with `document_number` (no customer/sensitive info). Coalesce `sale.vat_rate` with fallback config rate in grouping.
- Translations: Use `receipt_strings.vat` or `receipt_strings.vat_with_rate` with parameter `{rate}` across `en`, `si`, and `ta`.
- SSCL remains omitted from customer receipt and A4 invoice outputs per D9/D25.

## 3. Tax Liability Report Truth (#795)
- Uses `revenue_documents()`: excludes voids; includes completed sales and refunds.
- Filtering uses half-open date ranges: `Sale.date >= start_date` and `Sale.date < end_date` (same for `Purchase.date`).
- Generic translated column headers: "VAT" (`reports.col_vat`) and "SSCL" (`reports.col_sscl`) without hardcoded rates.
- Tabular DataFrame layout:
  - Section 1: Individual completed sales rows. Subtotal row `"TOTAL SALES"`.
  - Section 2: Individual completed refund rows (values stored or signed negative). Subtotal row `"TOTAL REFUNDS"`.
  - Section 3: Net totals row `"NET TOTALS"`.
  - Section 4: Final summary row `"NET VAT LIABILITY"` (`VAT: net_vat`, `Input VAT: input_vat_total`, `Net VAT Liability: net_vat - input_vat_total`).
  - Rate breakdown: If more than one distinct VAT rate was charged across the sales in the period, appends breakdown rows titled `"VAT @ {rate}%"` (`Invoice #`: `"VAT @ {rate}%"`, `Net Revenue`: taxable base, `VAT`: collected tax). If exactly one rate occurs, suppresses the breakdown table.
  - Maintains tabular schema compatibility with `PandasModel`, pagination, and Excel/PDF exports.

## 4. Tax Filing Summary: Period Resolution & Basis Truth (#796)
- **Period Resolution in UI (`FilterWidget`)**:
  - Adds interactive Month/Quarter and Year selectors when `period` is defined.
  - Monthly: Month (1–12) + Year -> half-open `[YYYY-MM-01, YYYY-MM_next-01)`.
  - Quarterly: Q1 (Jan 1 – Apr 1), Q2 (Apr 1 – Jul 1), Q3 (Jul 1 – Oct 1), Q4 (Oct 1 – Jan 1 next year).
  - Custom: Free start/end date selection; resolves end to `end_date + 1 day` at 00:00:00.
  - Date pickers display the resolved range read-only during Monthly/Quarterly.
  - Reports apply strict `< end_date` for half-open bounds.
- **Total Discounts**:
  - Line discounts: `sum(max(Decimal("0.00"), ((item.original_price or item.unit_price) * item.qty) - item.subtotal) for item in sale.items)`.
  - Bill discount: if `additional_discount_type == "PERCENTAGE"`, `(sum(item.subtotal for item in sale.items)) * (sale.additional_discount_value / Decimal("100"))`; if `"FIXED"`, `sale.additional_discount_value`.
  - Loyalty discount: `sale.loyalty_points_value` (ADR 0002).
  - Summed over completed sales. Since refund documents do not store discount item breakdown lines, refunds are excluded from this row, labeled `reports.discounts_on_sales` ("Discounts given on sales") per phase spec §796.
- **SSCL Liable Turnover & Section**:
  - Liable turnover = $\sum (\text{sscl\_base} \times \frac{\text{sscl\_turnover\_pct}}{100})$ filtered by `Sale.sscl_registered.is_(True)` (or legacy `Sale.tax_sscl > 0`).
  - Legacy rows where `sscl_base is None` use $(\text{net\_revenue} + \text{tax\_sscl}) \times \frac{\text{pct}}{100}$.
  - Refund documents for SSCL-registered sales reduce liable turnover and SSCL liability.
  - SSCL Liability = $\sum \text{tax\_sscl}$. Reconciles with `round_money(liable_turnover * sscl_rate)`.
  - Quarterly SSCL section displays Liable Turnover, SSCL Rate, and SSCL Liability.
