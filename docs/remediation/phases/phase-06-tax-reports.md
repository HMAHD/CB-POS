# Phase 6 — Tax Calculation and Report Truth

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> This spec was verified against `origin/main` @ `4bcc837` on 2026-10-28. Re-verify every `file:line` before editing (§0.1 step 7).
> **Tax rules here must not be "improved" from general knowledge.** Follow D4 (rounding), D9 (SSCL model) and §0.12 P11 (the SSCL base excludes VAT; the code formula is legally correct). Anything not covered: Stop & Ask.

## Phase brief

**Outcome (end state):**
- Every sale stores the facts its tax was computed from:
  - VAT and SSCL rates;
  - the SSCL turnover %;
  - the taxable, VAT-exempt and SSCL-exempt amounts;
  - per-line exemption flags;
  - per-line cost at sale time.

  Reprints, invoices, refunds and reports read those facts, never today's settings.
- One rounding helper (`ROUND_HALF_UP`) is used everywhere, and VAT + SSCL + net always equals the total.
- SSCL works for shops that are SSCL-registered but not VAT-registered, uses Retail / Manufacturer / Distributor presets, and doesn't print on customer receipts.
- Shop owners can mark categories VAT-exempt (and SSCL-exempt) in the UI.
- Every report excludes voided sales, treats refunds by one consistent policy, and uses `Decimal`:
  - tax liability and the filing summary;
  - P&L, cash flow and void/refund;
  - daily sales, cashier and category reports;
  - the dashboard and the auto-email.
- Aging (customers, suppliers) is measured from the oldest unpaid item. Statements are correct for past periods. Date ranges never drop the last second of a day.

**Depends on:**
- Phase 3A: `method_kind`, the refund engine, `round_money` in `cbpos/core/utils/money.py`, and the TODO(#844) markers in report queries.
- Phase 3B: #813, the stored bill discount.
- Phase 4: AVCO correctness.
- Phase 5: #880, report permissions.

**Unblocks:**
- Phase 7: receipts and invoices print the stored facts.
- Phase 8: #814 tax invoice; #818 docs.
- The Q2 answer in PROGRESS.md: partial-refund VAT goes line-level once the per-line flags exist.

### Issues

| # | Title | Sev | Size | Batch | Gate |
|---|---|---|---|---|---|
| #810 | Banker's rounding; VAT rate integer-only | medium | M | 6.1 | decided (D4); accountant sign-off at release gate |
| #797 | Tax-exempt categories not settable; exempt split not stored | high | M | 6.1 | agent |
| #831 | SSCL for non-VAT-registered shops; remove from receipts | high | L | 6.1 | decided (D9); one sub-question, below |
| #811 | Invoice reprint shows the current tax % | low | S | 6.2 | agent (uses the 6.1 snapshot) |
| #795 | Tax Liability includes voids; hard-coded rate headers | high | S | 6.2 | agent |
| #796 | Tax Filing Summary: period unwired, discounts 0, SSCL base mismatch | high | M | 6.2 | agent |
| #798 | P&L uses VAT-inclusive revenue, current cost, float | high | M | 6.3 | agent |
| #843 | Refunds never appear in the Void/Refund report | high | S | 6.3 | agent |
| #844 | Cash Flow adds refunds back | high | S | 6.3 | agent |
| #845 | Sales reports, dashboard and auto-email count voids | high | M | 6.3 | agent |
| #912 | Date filters drop the last second of the day | low | S | 6.4 | agent |
| #883 | Overdue customers clock resets on every credit sale | medium | M | 6.4 | agent |
| #897 | Overdue suppliers measured from any entry | medium | M | 6.4 | agent |
| #907 | Thermal statement shows today's debt for a past period | low | S | 6.4 | agent |
| #909 | Low stock lists services and bundles | low | S | 6.4 | agent |
| #910 | Category sales drop uncategorized products | low | S | 6.4 | agent |

### Subsystem map

**Tax engine** — `cbpos/core/services/tax_service.py`:
- `calculate_taxes(total_mrp, taxable_amount=None)` `:40-110`, which returns 0 VAT and 0 SSCL when not `vat_registered` (`:62-68`), and computes SSCL only on the taxable portion (`:72-94`);
- `_get_rates()`.

Callers: `CartService.get_totals` (`cart_service.py:254-287,325-369`, with exemptions when `item_tax_exemptions` is on) and `TransactionService._execute_sale` (the temporary `sale._exempt_amount` at `transaction_service.py:354-356,381`).

**Models:**
- `Category.tax_exempt` (`models/__init__.py:333`);
- `Sale` fields `total_amount, tax_vat, tax_sscl, net_revenue` (`:190+`);
- `SaleItem` (`:494-513`) has **no** `unit_cost`.

**Settings** — `ConfigService` keys `vat_registered`, `tax_vat_rate`, `tax_sscl_rate`, `tax_sscl_turnover_pct`, `item_tax_exemptions`, `show_tax_breakdown`; the UI is `cbpos/ui/views/settings_pages/sales_tax.py` (VAT rate `QSpinBox` at `:84-89`).

**Categories** — `cbpos/core/services/category_service.py:209-282` (create and update don't accept `tax_exempt`); UI `cbpos/ui/dialogs/category_manager.py`.

**Receipts:**
- `cbpos/core/services/sales_receipt_builder.py:199-202` (the SSCL line behind `show_tax_breakdown`);
- A4 invoice `cbpos/core/services/invoice_service.py:448-450` (prints current rates).

**Reports** — `cbpos/core/reports/definitions/`:
- `financial_reports.py`: P&L `:40-100`, Tax Liability `:130-200`, Tax Filing Summary `:215-411`;
- `void_refund_report.py:68-109`;
- `cash_flow_report.py`;
- `sales_report.py:149-158`, `sales_reports.py:55-71,127-138`;
- `inventory_reports.py:202-207`;
- `overdue_report.py:50`.

Report UI filters: `cbpos/ui/views/reports/filter_widget.py:124-125`.

**Dashboard** — `cbpos/core/services/dashboard_service.py`: `get_kpis` `:65-116`, low stock `:80-86`, charts `:160-350`. Phase 2 #886 already replaced `strftime`; build on it.

**Other reports and services:**
- `ReportService.get_daily_sales` (`report_service.py:17-51`);
- auto-email (`scheduler_service.py:118-121`);
- aging: `customer_credit_service.py:449-464` (overdue customers) and `supplier_payable_service.py:243-274`;
- statements: `cbpos/core/services/statement_receipt_builder.py:53-94`, `ui/dialogs/customer_statement_dialog.py:291,379-390`.

**Date-range builders** (#912) — `sale_history_dialog.py:436`, `receipt_reprint_dialog.py:256`, `credit_book_view.py:889-896`, `customer_statement_dialog.py:291`. The correct pattern is in `document_view.py:530`.

### Domain invariants

1. For every sale: `round_money(vat) + round_money(sscl) + net == total_amount` exactly (D4).
2. Historical documents print and report from stored facts: rates, exempt splits, line costs. Changing settings never changes an old document.
3. Report sale sets:
   - **completed sales** = `status == COMPLETED AND payment_method != 'REFUND'`;
   - **refund documents** = `refund_of_sale_id IS NOT NULL` (status COMPLETED);
   - **voids** = `status == 'VOID'`.

   Revenue and tax figures = completed sales + refund documents (refunds are negative). Voids are excluded everywhere except the Void/Refund report. Transaction counts count completed sales only; refunds are counted separately. **Put this in one place**: `cbpos/core/reports/sale_filters.py` with `completed_sales()`, `refund_documents()`, `revenue_documents()` (completed + refunds) and `voided()` as SQLAlchemy criteria. Every report imports them.
4. Date ranges are half-open: `start <= ts < next_day_start`.
5. Aging is measured from the oldest unpaid charge (FIFO allocation of payments and credits against charges).

### Batches

| Batch | Branch | Issues | Why grouped |
|---|---|---|---|
| 6.1 | `fix/p6-b1-tax-calculation-facts` | #810, #797, #831 | The tax engine and the snapshot migration everything else reads |
| 6.2 | `fix/p6-b2-tax-reports-invoice-history` | #811, #795, #796 | Tax outputs from stored facts |
| 6.3 | `fix/p6-b3-profit-cash-sales-reports` | #798, #843, #844, #845 | Revenue reports on the shared sale filters |
| 6.4 | `fix/p6-b4-aging-statements-coverage` | #912, #883, #897, #907, #909, #910 | Time boundaries and coverage |

---

## Batch 6.1 — Tax calculation and stored facts

**Branch:** `fix/p6-b1-tax-calculation-facts` · **Skills for the batch:** domain-modeling → write a design note → `/egm-review` (tax is money-critical) → tdd → migration rules → ponytail · **Research:** none needed beyond D4 and D9. Cite DECISIONS in the PR.

**Shared migration `sale_tax_snapshot`** (first commit):

*`sales` gets:*
- `vat_rate Numeric(5,2)`
- `sscl_rate Numeric(5,2)`
- `sscl_turnover_pct Numeric(5,2)`
- `vat_registered Boolean`
- `sscl_registered Boolean`
- `taxable_amount Numeric(12,2)` (MRP of VAT-taxable lines after discounts)
- `vat_exempt_amount Numeric(12,2)`
- `sscl_base Numeric(12,2)`

All are nullable for history.

*`sale_items` gets:*
- `vat_exempt Boolean`
- `sscl_exempt Boolean`
- `unit_cost Numeric(12,2)` (cost at sale time, #798)

*`categories` gets:* `sscl_exempt Boolean NOT NULL default False` (D9: SSCL exemptions modelled separately).

*Backfill:*
- `vat_rate`, `sscl_rate` and `sscl_turnover_pct` from the **current** settings, which the migration reads from `settings.json`. Migrations can't import ConfigService, so read the JSON file directly. If it's missing, use the defaults 18 / 2.5 / 50.
- `vat_exempt_amount` = 0, and `taxable_amount` = `total_amount` when `tax_vat > 0`, else 0.
- `sale_items.unit_cost` from the current `products.cost`.

Write in the migration docstring and the release notes: "historical cost and rates are approximated by current values at upgrade time." Never recompute the stored `tax_vat` / `tax_sscl` / `net_revenue` (§0.2).

### #810 — Tax rounding uses banker's rounding; the VAT rate is integer-only

**Severity:** medium · **Size:** M · **Gate:** decided by **D4**: `ROUND_HALF_UP`, one helper, net = total − rounded VAT − rounded SSCL, VAT rate with two decimals. Accountant sign-off happens at the release gate.

**Evidence.**
- `tax_service.py:101-104` quantizes with the default context (`ROUND_HALF_EVEN`) and rounds net separately.
- `purchase_service.py:136` (AVCO).
- `sales_tax.py:84-89` uses an integer `QSpinBox`.
- Comment on the issue: VAT extraction can be written as the tax fraction `r/(1+r)` (= 18/118 = 9/59 for 18%).

**Fix.**
1. `cbpos/core/utils/money.py` (created in Phase 3A; create it here if absent):
   - `round_money(x) -> Decimal` with `ROUND_HALF_UP` to 0.01;
   - `round_qty(x)` with `ROUND_HALF_UP` to 0.001.
2. `calculate_taxes`:
   - `vat = round_money(taxable_mrp * vat_rate / (1 + vat_rate))`, using the tax fraction directly so it matches the Act's wording;
   - `sscl = round_money(sscl_base * turnover_pct * sscl_rate)` (see #831 for the base);
   - `net = total_mrp - vat - sscl`. Net is never rounded separately.
3. Replace every `.quantize(Precision.MONEY)` / `.quantize(Decimal("0.01"))` in services with `round_money`. List the sites with `graft grep "quantize(" --in cbpos/core`. UI input parsing may keep its `ROUND_HALF_UP` quantize. Add the guardrail test `test_no_quantize_without_rounding_mode_in_core`: AST-scan `cbpos/core` for `.quantize(` calls without a `rounding=` keyword, excluding `money.py`.
4. VAT rate setting: `QDoubleSpinBox`, 2 decimals, range 0–100, step 0.5. Stored as a string (`"18.00"`) and read as `Decimal(str(...))`. Check `_get_rates()` converts safely from the old int values too.

**Tests** (`tests/domain/test_tax_service.py`):
- `test_issue_810_half_up_boundaries`: inputs where the exact VAT has .xx5. Assert the half-up results.
- `test_issue_810_components_sum_to_total`: property-style loop over 1,000 totals from 0.01 to 99,999.99 (deterministic stepping). `vat + sscl + net == total`.
- `test_issue_810_vat_rate_two_decimals` (e.g. 15.50).
- `test_no_quantize_without_rounding_mode_in_core` (guardrail).

**UI/UX.** The VAT rate field accepts decimals, with a suffix " %". Run the §0.7 UI gate on the Sales & Tax settings page.

**Acceptance.**
- [ ] One rounding helper with an explicit mode, used in tax, AVCO and totals (guardrail green).
- [ ] Net = total − VAT − SSCL after rounding, and the parts always add up.
- [ ] The VAT rate accepts two decimals.
- [ ] Tests for .005 boundary cases.

### #797 — Tax-exempt categories can't be set from the UI; the exempt split isn't stored

**Severity:** high · **Size:** M · **Gate:** agent

**Evidence.**
- `Category.tax_exempt` exists (`models:333`) and is used by the cart (`cart_service.py:254-287,347`).
- `CategoryService.create/update` (`category_service.py:209-282`) don't accept it, and it's set only in the demo seed (`scripts/seed.py:189`).
- The in-app guide promises it (`en.json:1626`).
- The split lives only on the temporary `sale._exempt_amount` (`transaction_service.py:354-356,381`).

**Fix.**
1. `CategoryService.create/update` accept `vat_exempt` (field `tax_exempt`) and `sscl_exempt`.
   - Changing either requires the permission `settings.tax` (or the existing tax-settings permission; `graft grep "TAX" --in cbpos/core/constants/permissions.py`).
   - Write AuditLog `CATEGORY_TAX_FLAG_CHANGED` (old → new).
   - Subcategories inherit from the parent unless set: the cart's rule. Check `cart_service.py:254-287` and keep its inheritance logic as the single source (expose `CategoryService.effective_flags(category_id)` and make the cart use it).
2. Category Manager: two checkboxes, **"VAT exempt (zero VAT on these items)"** and **"SSCL exempt"**, visible only when `item_tax_exemptions` is on. Otherwise show a hint linking to the setting.
3. `_execute_sale` stores:
   - on each `SaleItem`: `vat_exempt` and `sscl_exempt` (effective flags at sale time) and `unit_cost` (product cost now);
   - on the `Sale`: `taxable_amount`, `vat_exempt_amount`, `sscl_base`, the rates and the registration flags.
   - Remove `sale._exempt_amount`.
4. The receipt reprint and A4 invoice show "Taxable" / "VAT exempt" amounts from the stored fields (A4 always; thermal only with `show_tax_breakdown`).
5. Update the Phase 3A `RefundService`: if the sale has per-line `vat_exempt` flags (not null), allocate refund VAT and SSCL by line taxability; otherwise use the proportional fallback. This is Q2 / follow-up A. Close the follow-up issue if it was filed.

**Tests.**
- `test_issue_797_category_flag_settable_and_audited`.
- `test_issue_797_sale_stores_exempt_split_and_line_flags`.
- `test_issue_797_reprint_shows_stored_split_after_flag_change`.
- `test_issue_797_partial_refund_uses_line_flags`.

**UI/UX.**
- Checkbox labels `category.vat_exempt` "VAT exempt (no VAT on these items)" and `category.sscl_exempt` "SSCL exempt".
- Tooltip `category.exempt_help` "Only tick these if your tax adviser has confirmed this category is exempt."
- Receipt and invoice: `receipt.taxable_amount` "Taxable amount" and `receipt.vat_exempt_amount` "VAT exempt amount".
- Run the §0.7 UI gate.

**Acceptance.**
- [ ] The "Tax exempt" checkbox in category create/edit goes through `CategoryService` and is audited.
- [ ] The sale stores the exempt split, and the reprint and A4 invoice use it.
- [ ] Tests: exempt category → stored → reprint shows the split.

### #831 — SSCL for non-VAT-registered shops; remove SSCL from customer receipts

**Severity:** high · **Size:** L · **Gate:** decided by **D9**:
- `sscl_registered` is independent of VAT;
- Retail 50% / Manufacturer 85% / Distributor 25% presets;
- SSCL exemptions are modelled separately;
- SSCL is removed from customer receipts but kept in liability reporting.

One sub-question is pre-written below.

**Evidence.**
- `tax_service.py:62-68` returns SSCL 0 when not VAT-registered.
- `:72-94` computes SSCL only on the VAT-taxable portion.
- `sales_receipt_builder.py:199-202` prints SSCL to customers.
- The research, sources and thresholds are in the issue body. The Rs 36M SSCL threshold from 1 Jul 2026 is a secondary source: verify it on ird.gov.lk before shipping any **copy** that quotes it. The code doesn't quote thresholds.

**Fix design.**
1. **Settings:**
   - `sscl_registered: bool`. Migration default: equal to the current `vat_registered` value, so behaviour doesn't change on upgrade. Do it in `ConfigService.load()` key migration: if the key is missing, copy `vat_registered`.
   - `sscl_turnover_preset` ∈ {RETAIL, MANUFACTURER, DISTRIBUTOR, CUSTOM}, mapping to 50/85/25 or the custom `tax_sscl_turnover_pct`.
2. **Tax engine:** `calculate_taxes(lines: list[TaxLine])`, where `TaxLine(amount_mrp_after_discounts, vat_exempt, sscl_exempt)`:
   - `taxable_mrp = Σ amount where not vat_exempt` (0 if not VAT-registered);
   - `vat = round_money(taxable_mrp × r/(1+r))` if VAT-registered, else 0;
   - **SSCL base (VAT-exclusive turnover, §0.12 P11)** = `Σ over lines not sscl_exempt` of: VAT-registered and the line is VAT-taxable → `amount/(1+r)`; otherwise → `amount` (no VAT inside it);
   - `sscl = round_money(sscl_base × turnover_pct × sscl_rate)` if SSCL-registered, else 0;
   - `net = total − vat − sscl`.
   - Bill-level discount and loyalty redemption (ADR 0002) are spread across lines in proportion to line amounts **before** tax, as the cart does now. Verify, and keep the cart and the engine consistent. One function computes the per-line after-discount amounts and both use it.
   - Keep a thin wrapper with the old signature for any remaining caller, then remove it once callers move.
3. **Receipts:** remove the SSCL line from the **thermal** customer receipt unconditionally. On the A4 invoice, also remove it. **Recommended:** don't show SSCL to customers anywhere, because the Act has no bill provision for it. The Tax Filing Summary and Tax Liability show it (6.2).
4. **Settings UI** (`sales_tax.py`):
   - "VAT registered" and "SSCL registered" as two separate switches, each with its rate;
   - the turnover preset combo, where Custom enables the % field;
   - an info line under SSCL: `settings.sscl_help` "SSCL is a cost to your business, not charged to customers. It's shown in your tax reports only."

**Tests** (`test_tax_service.py`):
- all four combinations of VAT/SSCL registration on a mixed bill (taxable + VAT-exempt + SSCL-exempt lines), with exact expected Decimals worked by hand in the test docstring;
- `test_issue_831_presets_map_to_turnover`;
- `test_issue_831_receipt_has_no_sscl_line` (receipt builder output);
- `test_issue_831_upgrade_sets_sscl_registered_from_vat`.

**UI/UX.**
- Keys:
  - `settings.vat_registered` "VAT registered"
  - `settings.sscl_registered` "SSCL registered"
  - `settings.sscl_preset` "Business type for SSCL"
  - `settings.sscl_preset_retail` "Retail / wholesale (50%)"
  - `settings.sscl_preset_manufacturer` "Manufacturer selling own goods (85%)"
  - `settings.sscl_preset_distributor` "Registered distributor of a local manufacturer (25%)"
  - `settings.sscl_preset_custom` "Custom"
  - `settings.sscl_help` (above)
- Run the §0.7 UI gate. The settings page is used by owners rarely, so add a short explanation for each switch.

**Stop & Ask (before merging; build the recommended version meanwhile):**

QUESTION (#831): For VAT-exempt items (e.g. essential foods) in a VAT-registered shop, SSCL is computed on their full MRP (no VAT inside it), unless the category is also marked SSCL-exempt. Is that what your tax adviser expects?
Options:
  A) Yes. VAT-exempt and SSCL-exempt are independent flags, as built.
  B) Treat VAT-exempt items as SSCL-exempt too.
Recommendation: A. It follows the Act's separate exemption schedule (D9). Get the accountant's confirmation recorded as D17.

**Acceptance.**
- [ ] `sscl_registered` is independent of VAT. The SSCL base excludes VAT where VAT applies and uses MRP otherwise.
- [ ] Turnover presets work.
- [ ] No SSCL line on customer receipts or invoices, and SSCL is kept in reports.
- [ ] Tests for all four VAT/SSCL combinations.

---

## Batch 6.2 — Tax reporting and invoice history

**Branch:** `fix/p6-b2-tax-reports-invoice-history`

First create `cbpos/core/reports/sale_filters.py` (invariant 3), with unit tests, and use it in every report touched from here on.

### #811 — Invoice reprint shows the current tax %

**Severity:** low · **Size:** S · **Gate:** agent

**Fix.** `invoice_service.py:448-450` and the thermal builder print `sale.vat_rate` / `sale.sscl_rate` from the 6.1 snapshot. If a value is null (a pre-upgrade row the migration missed), fall back to current settings and log a warning. Because SSCL is no longer printed (#831), only VAT % matters on outputs.

**Test.** `test_issue_811_reprint_uses_sale_rate_after_setting_change`: sale at 18, setting changed to 15, reprint shows 18.

**Acceptance.**
- [ ] The rates are stored on the sale and printed from there.
- [ ] After a rate change, an old sale's reprint shows the old %.

### #795 — Tax Liability Report includes voided sales and hard-codes rate headers

**Severity:** high · **Size:** S · **Gate:** agent

**Evidence.**
- `financial_reports.py:164-170` has no status filter, and `void_sale` leaves the tax amounts in place.
- Headers are hard-coded "VAT (18%)" / "SSCL (2.5%)" at `:138-139,182-183`.

**Fix.**
- Use `revenue_documents()` (completed + refunds, no voids).
- Show sales and refunds as separate sections plus a net total, matching the Tax Filing Summary layout.
- Headers: `reports.col_vat` "VAT" and `reports.col_sscl` "SSCL" without a rate. Add a per-rate breakdown table **only if** more than one rate occurs in the period (group by `sale.vat_rate`), titled `reports.vat_by_rate` "VAT by rate" with a row per rate.
- Report generation already runs off the UI thread? Check the report viewer's worker. If not, Phase 7 #731 handles it; note that.

**Tests.**
- `test_issue_795_voided_sale_excluded`.
- `test_issue_795_refund_shown_separately_and_netted`.
- `test_issue_795_two_rates_in_period_breakdown`.

**Acceptance.**
- [ ] Voids are excluded, and refunds are shown consistently with the Tax Filing Summary.
- [ ] Headers come from the configured or stored rates, translated.

### #796 — Tax Filing Summary: period unwired, discounts always 0, SSCL base mismatch

**Severity:** high · **Size:** M · **Gate:** agent (the SSCL basis is settled by the issue's comment and #831)

**Evidence.**
1. The period combo (`financial_reports.py:236-249`) is ignored; `generate()` reads only `date_range` (`:271-273`), and `filter_widget.py:124-125` just returns the combo value.
2. `total_discounts = self.ZERO` (`:319`).
3. Liable turnover = `net_sales * 0.5` on a gross base (`:322`) vs the stored SSCL on a VAT-exclusive base (`:323`).

**Fix.**
1. **Period:** the filter widget resolves Monthly (pick month and year), Quarterly (pick quarter and year: Q1 = Jan–Mar, etc.) or Custom (dates) into a half-open `[start, end)` range **in the filter widget**, and passes `date_range` to the report. When Monthly or Quarterly is chosen, the date pickers show the resolved range read-only.
   - Sri Lankan VAT periods: verify whether the IRD return periods are monthly or quarterly for the shop's category.
   - **Don't hard-code a fiscal year start.** Quarters are calendar quarters unless the owner says otherwise. If the research note in #814 (Phase 8) finds the VAT return quarter differs from calendar quarters, Stop & Ask.
2. **Total discounts** = Σ of line discounts (from `sale_items` original vs unit price × qty, or the stored discount fields), plus bill discount (`sales.additional_discount_*`, #813), plus loyalty redemption value (`sales.loyalty_points_value`, a discount per ADR 0002), over completed sales. Refund documents reduce it proportionally: use their stored values if refund docs carry discount fields; otherwise exclude refunds from this row and label it `reports.discounts_on_sales` "Discounts given on sales".
3. **Liable turnover** = Σ stored `sales.sscl_base × sscl_turnover_pct` for SSCL-registered sales in range (+ refunds). For pre-upgrade rows with no `sscl_base`, use `net_revenue + tax_sscl` (VAT-exclusive turnover) × stored or current pct. SSCL liability = Σ `tax_sscl`. The two lines now reconcile: `liability = round(liable_turnover × rate)` within rounding.
4. Use `method_kind` (3A) for any payment rows here (resolve the TODO(#844) markers).
5. Add the **quarterly SSCL liability view** (D9 / #831): a section "SSCL for the quarter" showing liable turnover, the rate and the liability.

**Tests.**
- `test_issue_796_period_monthly_quarterly_resolution`.
- `test_issue_796_total_discounts_sums_line_bill_loyalty`.
- `test_issue_796_liable_turnover_reconciles_with_sscl`.

**UI/UX.** The period combo with Month/Quarter pickers. Keys:
- `reports.period_monthly` "Monthly"
- `reports.period_quarterly` "Quarterly"
- `reports.period_custom` "Custom dates"
- `reports.quarter_n` "Q{n} {year} ({months})"

Run the §0.7 UI gate.

**Acceptance.**
- [ ] Monthly or Quarterly fills the date range; Custom keeps manual dates.
- [ ] Discounts are summed from stored data.
- [ ] Liable turnover uses the same base and % as the stored SSCL.
- [ ] Tests for period resolution and totals.

---

## Batch 6.3 — Profit, cash and sales report semantics

**Branch:** `fix/p6-b3-profit-cash-sales-reports`

### #798 — The P&L uses VAT-inclusive revenue, current cost and float

**Severity:** high · **Size:** M · **Gate:** agent

**Evidence.**
- `financial_reports.py:84-88`: `qty * float(unit_price)` (MRP incl. VAT) and `qty * float(unit_cost)`.
- `:51-56` uses the current product cost.

**Fix.**
- Revenue = Σ `net_revenue + tax_sscl` (VAT-exclusive turnover) over `revenue_documents()`.
- SSCL is shown as an **expense line** "SSCL levy", if any.
- COGS = Σ `sale_items.unit_cost × qty` (stored, from 6.1). Refund lines have negative qty, so COGS reverses automatically.
- Gross profit = revenue − COGS − SSCL. Margin % = gross profit / revenue.
- All `Decimal`. Remove every `float(`. **Guardrail:** `test_no_float_on_money_in_reports`, an AST scan of `cbpos/core/reports` for `float(` calls (an allow-list for chart rendering only, if any).
- Per-category and per-product breakdowns, if the report has them, use the same sources.

**Tests.**
- `test_issue_798_cost_change_between_sales_keeps_history`.
- `test_issue_798_revenue_excludes_vat`.
- `test_issue_798_refund_reverses_cogs`.

**Acceptance.**
- [ ] `SaleItem.unit_cost` is captured at sale time (6.1).
- [ ] P&L revenue is net of VAT, SSCL is an expense line, and COGS uses the stored cost.
- [ ] All `Decimal` (guardrail).

### #843 — Refunds never appear in the Void/Refund report

**Severity:** high · **Size:** S · **Gate:** agent

**Root cause.** `void_refund_report.py:82` filters `status IN (VOID, "REFUND")`, but refunds are COMPLETED with `refund_of_sale_id` set.

**Fix.**
- `or_(voided(), refund_documents())`.
- Columns: document, type (Void/Refund), original receipt, amount (refunds negative), user, approver (from AuditLog if stored; otherwise the user), reason, date.
- A partial-refund marker (from Phase 3A refund state): "Part" or "Full".

**Test.** `test_issue_843_refund_listed_with_user_and_negative_amount`.

**Acceptance.**
- [ ] A refund is listed with a negative amount and the user who did it.

### #844 — The Cash Flow report adds refunds back

**Severity:** high · **Size:** S · **Gate:** agent

**Root cause.** `cash_flow_report.py:60,80-86,97`: Total Sales already includes the negative refund documents, then subtracts Refunds again. It uses float.

**Fix.**
- Build the cash flow from **payments by `method_kind`** (3A), not from sale totals:
  - cash in = Σ CASH-kind `SalePayment.amount > 0`;
  - cash refunded = Σ |CASH-kind amount < 0|, together with legacy REFUND_LEGACY rows' cash-back share (via `refund_cash_back`);
  - cash movements in/out;
  - the same for each other kind as a breakdown.
- `Net = in − refunded ± movements`. All `Decimal`.

**Test.** `test_issue_844_sale_plus_full_refund_nets_zero`.

**Acceptance.**
- [ ] A sale plus its full refund gives net 0.

### #845 — Sales reports, the dashboard and the auto-email count voided sales

**Severity:** high · **Size:** M · **Gate:** agent

**Root cause.** These have no status filter:
- `sales_report.py:149-158`;
- `sales_reports.py:55-71,127-138`;
- `dashboard_service.py:65-76,105-116,160-167,201-350`;
- `report_service.py:25-44`;
- `scheduler_service.py:118-121`.

**Fix.**
- Every one of these uses `sale_filters` (invariant 3). Totals use `revenue_documents()`, and **transaction counts** use `completed_sales()` only.
- Top products, categories and cashiers use completed sales plus refunds netted by product.
- Payment breakdowns use `method_kind`.
- Replace `float` with `Decimal`, except at the chart-rendering boundary.
- Make the dashboard tax panel use the same filters, so it stops contradicting the other panels.

**Tests.**
- `test_issue_845_void_excluded_daily_sales_and_kpis`: void a 3,000 sale; the totals are 4,200 and the count is 3.
- `test_issue_845_refund_not_counted_as_transaction`.
- `test_issue_845_auto_email_report_matches_daily_sales`.

**Acceptance.**
- [ ] A voided sale disappears from Daily Sales, Cashier Performance, Sales by Category, the Dashboard and the auto-email.
- [ ] Tests cover `DailySalesSummaryReport` and `get_kpis`.

---

## Batch 6.4 — Aging, statements and coverage

**Branch:** `fix/p6-b4-aging-statements-coverage`

### #912 — Date filters drop the last second of the day

**Severity:** low · **Size:** S · **Gate:** agent

**Root cause.** The four builders listed in the subsystem map use `23:59:59` or `today_start - 1s`. Timestamps have microseconds.

**Fix.**
- One helper, `cbpos/core/utils/date_ranges.py`: `day_range(d) -> (start, next_start)` and `range_for(d_from, d_to) -> (start, end_exclusive)`.
- Services filter with `>= start AND < end_exclusive`. Change `get_ledger` and the history and statement queries to `<`.
- Guardrail: `graft grep "23, 59, 59\|timedelta(seconds=1)"` → fix every hit in `cbpos/` and list them in the PR.

**Tests.**
- `test_issue_912_entry_at_235959_5_in_day_statement`.
- `test_issue_912_get_ledger_boundary`.

**Acceptance.**
- [ ] A ledger entry at 23:59:59.5 appears in that day's statement.

### #883 — The overdue customers clock resets on every credit sale

**Severity:** medium · **Size:** M · **Gate:** agent

**Root cause.**
- `customer_credit_service.py:449-464` measures from the latest ledger entry of any type.
- Customers with no entries get a fake 999 days.

**Fix.** `CustomerCreditService.oldest_unpaid_charge_date(customer_id) -> date | None`:
- walk the customer's ledger in time order;
- keep a FIFO queue of charges (SALE / positive ADJUSTMENT);
- apply payments and credits (PAYMENT, REFUND, VOID reversals, negative ADJUSTMENT) to the oldest charges first;
- return the date of the oldest charge with a remaining balance.

Days overdue = `today − that date − payment_terms`. A customer with no unpaid charge isn't overdue (no 999). Do it in SQL-light Python per customer, only for customers with `current_debt > 0`.

**Tests.**
- `test_issue_883_old_debt_plus_new_sale_still_overdue`.
- `test_issue_883_paid_off_customer_not_overdue`.
- `test_issue_883_partial_payment_ages_remaining`.

**Acceptance.**
- [ ] A 60-day debt plus a new credit sale today is still overdue.

### #897 — Overdue suppliers measured from any ledger entry

**Severity:** medium · **Size:** M · **Gate:** agent

**Root cause.** `supplier_payable_service.py:243-274` uses `max(timestamp)` of any entry.

**Fix.** The same FIFO algorithm over `SupplierLedgerEntry` (PURCHASE = charge; PAYMENT / credit note / negative adjustment = credit). **Extract the shared FIFO function** into `cbpos/core/utils/aging.py` (`oldest_open_charge(entries, charge_types, credit_types)`), used by #883 and #897.

**Test.** `test_issue_897_old_unpaid_purchase_plus_new_purchase_still_overdue`.

**Acceptance.**
- [ ] An old unpaid purchase plus a new one is still overdue.

### #907 — The thermal statement shows today's debt for a past period

**Severity:** low · **Size:** S · **Gate:** agent

**Root cause.**
- `statement_receipt_builder.py:57-60,94` uses `customer.current_debt` when there are no entries.
- `:53` hard-codes "to".

**Fix.**
- Opening = `balance_after` of the last ledger entry **before** `period_from` (0 if none).
- Closing = opening + Σ entries in the period.
- Add `CustomerCreditService.balance_at(customer_id, at: datetime)` and use it in both the thermal statement and the A4 statement dialog (`customer_statement_dialog.py:379-390`).
- Period line: `statement.period_range` "{from} to {to}", translated in the **receipt language** (`translate_in`).

**Test.** `test_issue_907_past_period_without_entries_uses_balance_before_period`.

**Acceptance.**
- [ ] With an entry after `period_to` and none inside, opening and closing come from before the period.

### #909 — Low Stock lists services and bundles

**Severity:** low · **Size:** S · **Gate:** agent

**Fix.**
- Exclude `is_service` and `is_composite` in `inventory_reports.py:202-207`, `dashboard_service.py:80-86` and `stock_service.py:157-163` (the reorder query; Phase 4 #864 may have moved it, so follow it).
- One criteria helper: `ProductService.stock_tracked()`.

**Test.** `test_issue_909_services_and_bundles_never_low_stock`.

**Acceptance.**
- [ ] Service items and bundles never show as low stock.

### #910 — Category sales drop uncategorized products

**Severity:** low · **Size:** S · **Gate:** agent

**Fix.**
- Use `outerjoin(Category)` in `sales_reports.py:61-62` and `dashboard_service.py:317,330`.
- A null category groups as `reports.uncategorized` "Uncategorized", translated at the presentation layer (the service returns `None`, and the report or UI labels it).

**Test.** `test_issue_910_uncategorized_sale_appears`.

**Acceptance.**
- [ ] A sale of an uncategorized product shows under "Uncategorized".

---

## Phase exit gate
- [ ] All 16 issues merged and **verified closed** with closing comments (§0.10). Epic checklists updated.
- [ ] Guardrails green: no `quantize` without a rounding mode in core; no `float(` in reports.
- [ ] `sale_tax_snapshot` migration tested on a v1.3.0 DB copy and a current seeded DB, on SQLite and PostgreSQL.
- [ ] A reconciliation test, `tests/domain/test_report_reconciliation.py`, builds one day with:
  - sales across VAT/SSCL combinations;
  - a void;
  - a partial and a full refund;
  - a bill discount and a redemption.

  It then asserts that Tax Liability, the Tax Filing Summary, the P&L, Daily Sales, the Dashboard KPIs and Cash Flow agree on revenue, VAT, SSCL and refunds.
- [ ] Accountant review packet: a PDF export of the Tax Filing Summary and P&L for the reconciliation day, attached to the PR for the owner's accountant (release gate item for #810 and #831). Record the answer as D17.
- [ ] UI gate screenshots: Sales & Tax settings (both switches, presets), Category Manager exempt flags, the Tax Filing Summary period picker, and a reprint with the stored rate.
- [ ] PROGRESS.md updated. Q2 marked resolved by #797.
