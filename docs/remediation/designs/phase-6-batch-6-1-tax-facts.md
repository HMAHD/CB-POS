# Design Note: Phase 6 Batch 6.1 — Tax Calculation and Stored Facts (Amended Post-Audit)

## 1. Context & Business Problem
Under the pre-release audit (#810, #797, #831), several financial and regulatory defects were identified in tax handling:
1. **Rounding & Non-reconciling Components (#810)**: `TaxService.calculate_taxes` quantizes VAT, SSCL, and Net independently using Python's default `ROUND_HALF_EVEN` (banker's rounding) without an explicit rounding mode. Because each component is rounded separately, `rounded_vat + rounded_sscl + rounded_net` does not always reconcile to `total_mrp`. Furthermore, the VAT rate in the settings UI is an integer `QSpinBox`, preventing standard fractional rates (e.g. 15.5%).
2. **Missing Tax Facts & Category Exemptions (#797)**: Products belonging to tax-exempt categories (e.g., staple foods) cannot have exemption flags set from the UI (`CategoryService.create/update` ignore `tax_exempt`). Crucially, when an exempt sale occurs, the exempt amount is held only in transient memory (`sale._exempt_amount`), meaning reprints, customer invoices, refunds, and financial reports lose the tax split as soon as the sale is committed.
3. **SSCL Coupling, Turnover Presets, and Customer Receipt Truth (#831)**:
   - Under current code, SSCL is completely zeroed out if the shop is not VAT-registered (`if not vat_registered: sscl = 0`). Under Sri Lankan tax amendments (effective July 2026), the SSCL registration threshold is Rs 36M/year, while the VAT threshold remains Rs 60M/year. Shops in this bracket are liable for SSCL but not VAT.
   - For VAT-registered shops, SSCL base is VAT-exclusive turnover (`MRP / (1 + VAT)`). For non-VAT registered shops (or VAT-exempt items), the SSCL base is full turnover (`MRP`).
   - SSCL is a corporate levy on turnover, not a customer charge, and the SSCL Act has no bill provision. Customer receipts should not display an SSCL levy line.
   - Turnover liability presets (Retail/Wholesale 50%, Manufacturer 85%, Distributor 25%, Custom) need standard configuration.

---

## 2. Core Decisions & Domain Invariants
- **D4 (Rounding & Reconciled Net)**:
  - Explicit `ROUND_HALF_UP` to `0.01` via `round_money()` in `cbpos/core/utils/money.py`.
  - Component equation:
    $$\text{net} = \text{total} - \text{round\_money}(\text{vat}) - \text{round\_money}(\text{sscl})$$
    Net is never independently quantized, guaranteeing $\text{vat} + \text{sscl} + \text{net} = \text{total}$ to the exact cent across all transactions.
- **D9 (SSCL Decoupling & Customer Receipt Truth)**:
  - `sscl_registered: bool` operates independently of `vat_registered: bool`.
  - SSCL line is removed from customer receipts and invoices, but preserved on tax and liability reports.
  - Turnover presets: Retail/Wholesale (50%), Manufacturer (85%), Distributor (25%), Custom.
- **D24 & Line-Level Refunds**:
  - Refunds of sales with stored per-line tax flags allocate VAT and SSCL according to the taxability of the specific returned line items, with final-refund remainder reconciliation. Sales without stored line flags fallback to proportional allocation.
- **P11 (SSCL Statutory Base)**:
  - For a line liable for SSCL:
    - If shop is VAT-registered and line is VAT-taxable: $\text{base} = \text{amount} / (1 + \frac{\text{vat\_rate}}{100})$
    - If shop is not VAT-registered OR line is VAT-exempt: $\text{base} = \text{amount}$
    - If line is SSCL-exempt: $\text{base} = 0$.

---

## 3. Database Schema Changes & Migration (`sale_tax_snapshot`)
A new Alembic migration adds stored tax facts to ensure complete document truth for historical reprints, reporting, and refunds.

### `sales` Table:
- `vat_rate`: `Numeric(5, 2)`, nullable (whole percentage, e.g. `18.00`, `15.50`)
- `sscl_rate`: `Numeric(5, 2)`, nullable (whole percentage, e.g. `2.50`)
- `sscl_turnover_pct`: `Numeric(5, 2)`, nullable (whole percentage, e.g. `50.00`)
- `vat_registered`: `Boolean`, nullable
- `sscl_registered`: `Boolean`, nullable
- `taxable_amount`: `Numeric(12, 2)`, nullable (VAT-taxable MRP after discounts)
- `vat_exempt_amount`: `Numeric(12, 2)`, nullable (VAT-exempt MRP after discounts)
- `sscl_base`: `Numeric(12, 2)`, nullable (Total liable SSCL base turnover)

### `sale_items` Table:
- `vat_exempt`: `Boolean`, nullable (leaves historical rows `NULL` as sentinel for legacy proportional refunds)
- `sscl_exempt`: `Boolean`, nullable (leaves historical rows `NULL`)
- `unit_cost`: `Numeric(12, 2)`, nullable (cost at sale time for profit truth #798)

### `categories` Table:
- `sscl_exempt`: `Boolean NOT NULL DEFAULT False` (with `server_default=sa.false()` in migration)

### Backfill Strategy:
- The migration directly reads `settings.json` (resolving path via `Config.DATA_DIR / "settings.json"`). If `settings.json` is missing: defaults to `18.0` / `2.5` / `50.0` / `False` / `False`. If `sscl_registered` is not present in `settings.json`, defaults to `settings.get("vat_registered", False)`.
- Existing `sales` rows:
  - `vat_rate`, `sscl_rate`, `sscl_turnover_pct`, `vat_registered`, `sscl_registered` backfilled from settings.
  - `vat_exempt_amount` = `0.00`.
  - `taxable_amount`:
    ```sql
    CASE WHEN tax_vat IS NOT NULL AND tax_vat != 0 THEN total_amount ELSE 0.00 END
    ```
    (Preserves negative values for historical refund documents).
  - `sscl_base`:
    ```sql
    CASE 
        WHEN tax_sscl IS NOT NULL AND tax_sscl != 0 THEN
            CASE WHEN tax_vat IS NOT NULL AND tax_vat != 0 THEN
                ROUND(total_amount / (1.0 + (vat_rate / 100.0)), 2)
            ELSE
                total_amount
            END
        ELSE 0.00
    END
    ```
  - Never recalculate historical `tax_vat`, `tax_sscl`, or `net_revenue`.
- Existing `sale_items` rows:
  - `vat_exempt`: remains `NULL`.
  - `sscl_exempt`: remains `NULL`.
  - `unit_cost`: backfilled from current `products.cost` (or `0.00`).

---

## 4. Architecture & Service Seams

### 4.1 Tax Engine (`cbpos/core/services/tax_service.py`)
Introduce `TaxLine` dataclass:
```python
@dataclass(frozen=True)
class TaxLine:
    amount: Decimal  # MRP after discounts
    vat_exempt: bool = False
    sscl_exempt: bool = False
```
Refactor `calculate_taxes`:
```python
def calculate_taxes(
    lines: list[TaxLine] | None = None,
    total_mrp: Decimal | None = None,
    taxable_amount: Decimal | None = None,
    vat_registered: bool | None = None,
    sscl_registered: bool | None = None,
    vat_rate: Decimal | None = None,
    sscl_rate: Decimal | None = None,
    turnover_pct: Decimal | None = None,
) -> dict[str, Decimal]:
```
- Fully supports backward-compatible callers via `total_mrp` and `taxable_amount`.
- Rates are whole percentages (`18.00`, `2.50`, `50.00`).
- For `lines`:
  - $r_{\text{vat}} = \text{vat\_rate} / 100$, $r_{\text{sscl}} = \text{sscl\_rate} / 100$, $t = \text{turnover\_pct} / 100$.
  - $\text{taxable\_mrp} = \sum_{\text{line} \notin \text{vat\_exempt}} \text{line.amount}$ (if VAT-registered, else $0.00$).
  - $\text{vat\_exempt\_amount} = \text{total\_mrp} - \text{taxable\_mrp}$.
  - $\text{vat} = \text{round\_money}(\text{taxable\_mrp} \times \frac{r_{\text{vat}}}{1 + r_{\text{vat}}})$ if VAT-registered else $0.00$.
  - For each line not SSCL-exempt:
    - If VAT-registered and line not VAT-exempt: $\text{line\_sscl\_base} = \text{line.amount} / (1 + r_{\text{vat}})$
    - Else: $\text{line\_sscl\_base} = \text{line.amount}$
  - $\text{sscl\_base} = \text{round\_money}(\sum \text{line\_sscl\_base})$ if SSCL-registered else $0.00$.
  - $\text{sscl} = \text{round\_money}(\text{sscl\_base} \times t \times r_{\text{sscl}})$ if SSCL-registered else $0.00$.
  - $\text{net} = \text{total\_mrp} - \text{vat} - \text{sscl}$.

### 4.2 Discount & Loyalty Allocation Across Lines
- Both bill-level discounts and loyalty redemptions reduce total bill amount before tax.
- In `CartService`: line amounts after line discounts are `item["total"]`.
- Allocation helper computes per-line net MRP after bill discounts:
  ```python
  subtotal = sum(item["total"] for item in items)
  total_discount = cart_discount + loyalty_discount
  if subtotal > 0 and total_discount > 0:
      ratio = total_discount / subtotal
      for item in items:
          item_discount = round_money(item["total"] * ratio)
          item_net_mrp = item["total"] - item_discount
      # Reconcile cent delta on largest line
  ```
  Zero-division guarded when `subtotal == 0`.

### 4.3 Category Exemption Controls (`CategoryService` & Category Manager UI)
- `CategoryService.create()` and `update()` accept `vat_exempt` (mapping to `tax_exempt`) and `sscl_exempt`.
- Security: Modifying tax flags requires `Permissions.ADMIN_SETTINGS` (or Manager override). Standard edits (name, color, parent) only require `Permissions.INVENTORY_EDIT`.
- Audit Logging: If `tax_exempt` or `sscl_exempt` changes:
  - `event_type = "CATEGORY"`
  - `action = "CATEGORY_TAX_FLAG_CHANGED"`
  - `details = json.dumps({"category_id": id, "field": field, "old": old_val, "new": new_val})`
  - `user_id = acting_user_id`
  - `terminal_id = ConfigService.get("terminal_id") or "TERM-01"`
- Single Source of Inheritance:
  - `CategoryService.effective_flags(category_id: int | None, session: Session | None = None) -> tuple[bool, bool]`
  - If subcategory has parent, inherits `True` from parent if parent flag is `True`.
  - If `not ConfigService.get("item_tax_exemptions")`, returns `(False, False)`.

### 4.4 Checkout & Stored Facts (`TransactionService._execute_sale`)
When committing a sale:
- Inspect each cart line:
  - `SaleItem.vat_exempt = line_vat_exempt`
  - `SaleItem.sscl_exempt = line_sscl_exempt`
  - `SaleItem.unit_cost = product.cost`
- On `Sale`:
  - `vat_rate`, `sscl_rate`, `sscl_turnover_pct` (percentages)
  - `vat_registered`, `sscl_registered`
  - `taxable_amount`, `vat_exempt_amount`, `sscl_base`
- Eliminate temporary attribute `sale._exempt_amount`.

### 4.5 Line-Level Refund Allocation (`RefundService`)
- When refunding a sale:
  - If the original sale has per-line tax flags (i.e. `orig_item.vat_exempt is not None`):
    - Aggregate taxable refund amount: $\text{taxable\_refund\_mrp} = \sum_{\text{lines not vat\_exempt}} \text{line\_val}$
    - If `sale.vat_registered`:
      $$\text{refund\_vat} = \text{round\_money}\left(\text{taxable\_refund\_mrp} \times \frac{r_{\text{vat}}}{1 + r_{\text{vat}}}\right)$$
      Clamped to remaining unrefunded VAT: $\min(\text{refund\_vat}, \max(0, \text{sale.tax\_vat} - \text{prev\_vat}))$.
    - Similar aggregate logic for SSCL using line exemption.
    - If `is_final_refund`, reconcile exact remainder:
      $$\text{refund\_vat} = \text{sale.tax\_vat} - \text{prev\_vat}$$
      $$\text{refund\_sscl} = \text{sale.tax\_sscl} - \text{prev\_sscl}$$
      $$\text{refund\_net} = \text{total\_value} - \text{refund\_vat} - \text{refund\_sscl}$$
  - If legacy sale (`orig_item.vat_exempt is None`), use proportional fallback as before (D24).
- In `RefundService._execute_refund`:
  - `refund_sale` gets negated `taxable_amount`, negated `vat_exempt_amount`, negated `sscl_base`, and copies rates/flags from original sale.
  - Refund `SaleItem` rows copy `vat_exempt`, `sscl_exempt`, and `unit_cost` from `orig_item`.

### 4.6 Customer Outputs (Receipts & Invoices)
- Customer Receipts:
  - Thermal receipt (`SalesReceiptBuilder`): completely remove SSCL line.
  - Display "Taxable Amount" and "VAT Exempt Amount" when `show_tax_breakdown` is enabled and exempt amount > 0.
- A4 Invoice (`InvoiceService`):
  - Remove SSCL line from invoice layout.
  - Display "Taxable Amount" and "VAT Exempt Amount" from stored sale facts.

---

## 5. Security & Multi-Terminal Sync Impact
- LAN Sync Protocol:
  - `sales` and `sale_items` snapshot fields are read-only once written on either terminal.
  - `categories.sscl_exempt` is synced during catalog sync. Main PC is catalog authority (`require_catalog_writable` applies to Category edits).
- Concurrency & Row Locking:
  - Network mode row-locking (`with_for_update=True`) on `Sale` during refund/void operations remains intact (D23).
- AST Guardrail:
  - Guardrail `test_no_quantize_without_rounding_mode_in_core` ensures no `.quantize()` call in `cbpos/core` omits `rounding=`.

---

## 6. Rollback & Failure Recovery
- Alembic downgrade cleanly drops the added columns in batch mode (SQLite) and standard DDL (PostgreSQL).
- No historical sale totals or ledger entries are modified.
- If settings migration fails, existing `settings.json` is preserved with backup copy.
