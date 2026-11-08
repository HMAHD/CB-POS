# Phase 6 Batch 6.3: Profit, Cash and Sales Report Semantics Design Note

## 1. Scope & Objective
Establish report truth across all financial, sales, cashier, category, and dashboard reports by applying unified sale filter semantics, stored historical facts, Decimal precision, and strict refund/void accounting.

## 2. Invariants & Populations
- **Sale Populations (`sale_filters.py`):**
  - `revenue_documents()`: `Sale.status == COMPLETED` (encompassing completed sales and refund documents where `refund_of_sale_id IS NOT NULL` or `payment_method == 'REFUND'`). All monetary totals (revenue, tax, line subtotals, tender totals) sum over this set.
  - `completed_sales()`: `Sale.status == COMPLETED` AND `Sale.refund_of_sale_id.is_(None)` AND `Sale.payment_method != 'REFUND'`. Transaction counts sum over this set only.
  - `voided()`: `Sale.status == VOID`. Voids contribute 0.00 to all totals and transaction counts.
- **Refund Signs:**
  - Refund documents carry negative `total_amount`, negative `net_revenue`, negative `tax_vat`, and negative `tax_sscl`.
  - Refund `SaleItem` rows carry negative `qty` and negative `subtotal`, with positive `unit_cost`. COGS (`qty * unit_cost`) reverses automatically.
  - In `VoidRefundReport`: includes `or_(voided(), refund_documents())`. Refunds show negative amount, original receipt number, acting user, approver from AuditLog, reason, and Part/Full badge.

## 3. P&L Semantics (#798)
- **VAT-Exclusive Revenue:** `sum(Sale.net_revenue + Sale.tax_sscl)` over `revenue_documents()`. VAT is excluded from revenue.
- **COGS:** `sum(SaleItem.unit_cost * SaleItem.qty)` using stored `SaleItem.unit_cost` captured at sale time. Never re-query current `Product.cost` for historical sales.
- **SSCL Expense:** `sum(Sale.tax_sscl)` over `revenue_documents()` displayed as a separate internal business expense line (D9, D25).
- **Gross Profit & Margin:** `Gross Profit = Revenue - COGS - SSCL`. `Margin % = (Gross Profit / Revenue) * 100` if `Revenue != 0` else `Decimal("0.00")`.
- **Decimal Precision & Guardrail:** Remove `float()` from `cbpos/core/reports/definitions/financial_reports.py`. Enforce via AST guardrail `test_no_float_on_money_in_reports`.

## 4. Cash Flow Semantics (#844)
- Group by `PaymentMethod.kind` (`PaymentMethodKind`), not method-name strings or `Sale.total_amount`.
- Inflows: `sum(SalePayment.amount)` where `amount > 0` on `revenue_documents()`.
- Refund Outflows: `sum(abs(SalePayment.amount))` where `amount < 0` on `revenue_documents()`.
- Legacy single-row refund fallback: If refund document lacks payment rows, use `refund_cash_back` once. Avoid double-counting.
- Drawer movements: Add cash in, subtract cash out from `CashMovement` (`type == 'IN'` vs `type.in_(['OUT', 'DROP', 'PAYOUT'])`).
- Net Flow: `Inflows - Refund Outflows ± Drawer Movements`. Physical cash and credit debt remain separate.

## 6. Review Dispositions
- Model confirmation: Drawer cash movements use `CashMovement` (table `cash_movements`, lines 729-740 of `models/__init__.py`).
- Tender grouping: `SalePayment.method_kind` is stored directly on `SalePayment` rows and matches `PaymentMethodKind` constants.
- COGS check constraint: `SaleItem` constraint `ck_sale_items_refunded_qty` allows `qty < 0`, and negative line quantities on refund rows multiply positive `unit_cost` to naturally reverse COGS.
- Guardrail: AST check `test_no_float_on_money_in_reports` will verify no `float()` calls exist in `cbpos/core/reports/`.


## 5. Sales Reports, Dashboard & Email Consistency (#845)
- `sales_report.py` (`DailySalesSummaryReport`), `sales_reports.py` (`SalesByCategoryReport`, `CashierPerformanceReport`), `dashboard_service.py` (`get_kpis`, `get_period_stats`, `get_top_categories`, `get_period_top_products`, `_monthly_sales_query`, `_hourly_sales_query`, `get_payment_breakdown`, `get_today_tax_summary`), `report_service.py` (`get_daily_sales`), and `scheduler_service.py` (auto-email) all use `sale_filters.py`.
- Voided sales disappear from all figures and counts.
- Refunds reduce monetary totals but do NOT increment transaction counts.
- Top products, categories, and cashiers net refund lines against sales.
- Floating-point conversions are strictly isolated to chart library boundaries.

