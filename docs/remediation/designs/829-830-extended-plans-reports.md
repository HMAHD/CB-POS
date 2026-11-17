# Technical Design: Extended Warranty Plans & Reporting (#829, #830)

**Phase:** 9 · **Batch:** 9.6  
**Issues:** #829 (Warranty W9: Extended warranty sold as a paid add-on), #830 (Warranty W10: Warranty reports, dashboard alerts and expiry reminders) · **Epic:** #820  
**Owner:** CB POS Remediation Team  
**Date:** 2026-11-17  
**Status:** APPROVED (Post-EGM Review Applied)  

---

## 1. Context & Remediation Objectives

Phase 9 Batches 9.1–9.5 (#821–#828) established:
1. Reusable `WarrantyPolicy` models, category/product inheritance, calendar-aware duration arithmetic, feature flag `WarrantyService.is_enabled()`.
2. Per-unit `Warranty` registration at checkout (`<doc_number>-01..NN`), whole-unit validation, void/refund cascades with per-unit cancellation, multi-terminal sync protocol 1.4.
3. Checkout serial/IMEI capture, cart serial slots, held bill persistence, and customer-facing delivery (receipt blocks, A4 invoice lines, standalone thermal/PDF certificates).
4. Counter warranty lookup, live effective status calculations, admin corrections with audit, and intake tickets (`WC-{Y}-{seq:05d}`) with claims board UI and sync protocol 1.5.
5. Atomic claim resolution via stock replacement (`MovementType.WARRANTY`, `replaces_warranty_id`), refund resolution via `RefundService.refund`, and supplier RMA tracking with ledger payables.

**Batch 9.6 (#829, #830)** delivers the final business loops of Phase 9:
- **Issue #829 (W9)**: Paid extended-warranty plans sold at checkout as service add-ons.
  - Cart line stable IDs (`line_id`), referencing covered line IDs (`covered_line_id`).
  - Plan merge identity `(product_id, covered_line_id)`.
  - Plan quantity constrained to covered line quantity (`plan_qty <= covered_line_qty`) in `add_item` and `update_quantity`.
  - Covered line removal/reduction auto-adjusts or prompts removal of excess plans with clear translated notices.
  - Extended warranty rows created at checkout linked to base warranties (`covers_warranty_id`), or directly to the covered unit if no base warranty exists.
  - Consecutively scheduled coverage: `extended_starts` field on `WarrantyPolicy` supporting `AFTER_BASE` (`base.end_date + 1 day`) or `FROM_SALE` (`sale.date`).
  - Strict void and refund cascades: refunding base unit cancels base AND linked extended warranties; refunding plan line alone cancels only extended coverage.
  - Separate base and extended coverage display on receipts, invoices, warranty cards, and counter lookup.
- **Issue #830 (W10)**: Warranty reports, dashboard KPI tile, and scheduler reminders.
  - Category `CATEGORY_WARRANTY = "warranty"` with five registered reports:
    1. Active warranties (`warranty_active`)
    2. Expiring warranties (`warranty_expiring`) — serves as reminder list for CSV/XLSX export
    3. Claims register (`warranty_claims_register`)
    4. Claims by product / supplier (`warranty_claims_by_product_supplier`) — with hand-computed claim rate fixture
    5. Claim cost (`warranty_claim_cost`) — incorporating immutable `replacement_cost_snapshot`, shop repair cost, customer charges, and supplier credit notes
  - Seam extension: `BaseReport.required_permissions` supporting multi-permission gates (`reports.view_profit` + `warranty.view` for Claim Cost; `reports.view_sales` + `warranty.view` for others).
  - Schema completions: `WarrantyClaim.expected_ready_date` and `WarrantyClaim.replacement_cost_snapshot`.
  - Dashboard Management tile with shared query helper `WarrantyClaimService.get_claims_summary()` for exact parity with Claims Board filters (matching `defective_unit_status == "SENT_TO_SUPPLIER"` for overdue RMAs).
  - Background worker for Dashboard tile updates (zero UI-thread DB blocking).
  - Daily non-blocking `SchedulerService` in-app notifications for overdue claims and overdue supplier RMAs.

---

## 2. Elephant Pass: End-to-End System Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   ELEPHANT PASS: PHASE 9.6 ARCHITECTURE                                │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                        │
│  [1. Cart & Add-On Selection]                                                                          │
│      CartItem A: Product (Phone), qty=2, line_id="uuid-1", serials=["SN-1", "SN-2"]                    │
│      CartItem B: Plan (+1 Yr Ext), qty=2, line_id="uuid-2", covered_line_id="uuid-1"                  │
│      * Plan merge identity: (product_id, covered_line_id)                                              │
│      * Invariant: qty(Plan) <= qty(Covered) checked on add_item & update_quantity                      │
│      * Held bills: SuspendedTransaction preserves line_id & covered_line_id                            │
│      * Recall: Orphaned plan lines omitted with translated notice if covered item missing              │
│                                                                                                        │
│  [2. Checkout & Atomic Persistence]                                                                    │
│      Sale: INV-001                                                                                     │
│      ├── SaleItem 1: Phone (qty=2, unit_cost=50,000)                                                   │
│      └── SaleItem 2: Plan (qty=2, unit_cost=0, covered_item_id=SaleItem 1.id, is_service=True)         │
│          ├── Stock Movement: Phone -2 (SALE). Plan moves ZERO stock.                                   │
│          ├── Tax: Category VAT/SSCL flags applied normally to Plan line.                               │
│          └── Warranties:                                                                               │
│              ├── W-01: Base (Phone, unit 1, SN-1), 2026-11-17 -> 2027-11-17                            │
│              ├── W-02: Base (Phone, unit 2, SN-2), 2026-11-17 -> 2027-11-17                            │
│              ├── W-03: Extended (Phone, unit 1, covers_warranty_id=W-01, plan_sale_item_id=2),        │
│              │         2027-11-18 -> 2028-11-18 (AFTER_BASE)                                           │
│              └── W-04: Extended (Phone, unit 2, covers_warranty_id=W-02, plan_sale_item_id=2),        │
│                        2027-11-18 -> 2028-11-18 (AFTER_BASE)                                           │
│                                                                                                        │
│  [3. Refund & Cancellation Cascades]                                                                   │
│      Case A: Refund Plan Line alone (SaleItem 2, qty=1)                                                │
│              -> Query checks Warranty.plan_sale_item_id == 2. Cancels W-04 (Extended).                 │
│              -> W-02 (Base) remains ACTIVE. Net refund = Plan line price.                              │
│      Case B: Refund Base Line (SaleItem 1, qty=1 with SN-1)                                            │
│              -> Cancels W-01 (Base) AND queries covers_warranty_id == W-01.id -> Cancels W-03.         │
│              -> RefundDialog suggests refunding SaleItem 2 (Plan line) as well.                        │
│      Case C: Void Sale                                                                                 │
│              -> All warranties (W-01, W-02, W-03, W-04) VOIDED.                                         │
│                                                                                                        │
│  [4. Claim Resolution Cost Reporting Dependency]                                                       │
│      Claim resolution: replace_from_stock() captures Product.cost at replacement time                  │
│      into WarrantyClaim.replacement_cost_snapshot (immutable Decimal).                                 │
│      Historical claims with unknown cost remain visibly unknown (NULL / "-").                          │
│                                                                                                        │
│  [5. Reports, Dashboard & Reminders]                                                                   │
│      Category: CATEGORY_WARRANTY ("warranty")                                                          │
│      ├── Active Warranties (Revenue split, status/category/type filters)                               │
│      ├── Expiring Warranties (Within N days, customer contact, CSV reminder list)                      │
│      ├── Claims Register (Turnaround, status, resolution)                                              │
│      ├── Claims by Product / Supplier (Claim rate = claims / net units sold)                           │
│      └── Claim Cost (replacement_cost_snapshot + shop_cost - cust_charge - supplier_credit)            │
│      Dashboard Tile: Background worker calls shared query WarrantyClaimService.get_claims_summary()    │
│      SchedulerService: Daily non-blocking check for overdue claims & overdue RMAs                      │
│                                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Goldfish Invariants (Proving Correctness Step-by-Step)

### Invariant 1: Stable Cart Linkage & Merge Isolation
- **Rule:** Plan lines must never link to covered lines by mutable array index. Every cart item is assigned a UUID string `line_id`. Plan lines store `covered_line_id`.
- **Merge rule:** A plan item only merges into an existing cart line if `(item["product"].id == product.id and item.get("covered_line_id") == covered_line_id)`. Adding a plan for Phone A will never merge with a plan for Phone B.
- **Proof:** Test adding multiple base items and plans, changing quantities, and verifying that each plan line preserves its target line ID.

### Invariant 2: Plan Quantity Upper Bound & Cascade Adjustments
- **Rule:** Total quantity of plans covering a line `L` must never exceed `L.qty`.
- **Enforcement:**
  - `add_item(plan_product, qty, covered_line_id=...)`: raises `ValueError` if `current_plans + qty > covered_line["qty"]`.
  - `update_quantity(plan_index, new_qty)`: if `item.get("covered_line_id")` is set, verifies `new_qty <= covered_line["qty"]`, raising `ValueError(_t("cart.plan_qty_exceeds_covered"))`.
  - `update_quantity(covered_line_index, new_qty)`: if `new_qty < current_plans`, clamp/remove excess plan quantities and return an informative translated notice.
  - `remove_item(covered_line_index)`: removes all plan lines targeting that line.
- **Proof:** Tests covering line reduction, line removal, and direct attempt to over-allocate plans.

### Invariant 3: Held Bill & Recall Fidelity
- **Rule:** `SuspendedTransactionService` format v2 stores `line_id` and `covered_line_id` for each line.
- **Recall:** Reconstructing the cart reinstates the exact `line_id` and `covered_line_id` associations. If a covered product was deleted or unavailable, any plan item targeting it is omitted with a translated warning: `_t("orders.recall_plan_missing_covered_item", plan=product.name_en)`.
- **Proof:** Unit test serializing a cart with base items and plans to a held bill, clearing the cart, recalling the bill, and verifying linkage integrity.

### Invariant 4: Product Integrity & Service Exclusion
- **Rule:**
  - A product marked `is_warranty_plan=True` must have `is_service=True`.
  - `plan_policy_id` must reference a valid `WarrantyPolicy` of type `EXTENDED` and `is_active=True`.
  - `Product.plan_category_id` (optional): if set, restricts plan eligibility to products belonging to that category or its subcategories.
  - Plan products NEVER receive a base warranty (`WarrantyService.resolve_policies_for_products` skips plan products).
  - Plan products NEVER create stock movements (`StockService.record_movement` returns None for `is_service`).
- **Proof:** ProductService validation tests, StockMovement absence tests, and checkout policy resolution assertions.

### Invariant 5: Atomic Warranty Registration & Chaining
- **Rule:**
  - In `TransactionService._write_sale_lines`:
    - Maintains a mapping of `line_id -> SaleItem.id`.
    - If `cart_item.get("covered_line_id")` is set, sets `sale_item.covered_item_id = line_id_map[cart_item["covered_line_id"]]`.
  - In `WarrantyService.register_for_sale_in_session`:
    - Base warranties `B_i` are registered first for each base unit `i` in `1..N`.
    - Extended plans are processed next:
      - For each unit `j` of a plan line covering `covered_sale_item`:
        - Extended warranty `E_j` is created.
        - `E_j.product_id` is the covered product's ID (the item under cover).
        - `E_j.sale_item_id = covered_sale_item.id`.
        - `E_j.plan_sale_item_id = plan_sale_item.id`.
        - `E_j.unit_index = j`.
        - If base warranty `B_j` exists for that unit index:
          - `E_j.covers_warranty_id = B_j.id`.
          - If `plan_policy.extended_starts == "AFTER_BASE"` (default): `E_j.start_date = B_j.end_date + timedelta(days=1)`.
          - If `plan_policy.extended_starts == "FROM_SALE"`: `E_j.start_date = sale.date.date()`.
        - If no base warranty exists:
          - `E_j.covers_warranty_id = None`.
          - `E_j.start_date = sale.date.date()`.
        - `E_j.end_date` is computed via `WarrantyService.compute_end_date(E_j.start_date, plan_policy.duration, plan_policy.duration_unit)`.
- **Proof:** Checkout registration tests with 2 covered phones + 2 plans asserting exact date calculations, foreign keys, and unit pairing.

### Invariant 6: Refund & Void Cascade Symmetry
- **Rule:**
  - In `WarrantyService.cancel_units_for_refund_in_session`:
    - Query active warranties to cancel matching:
      ```python
      where(
          or_(
              Warranty.sale_item_id == sale_item_id,
              Warranty.plan_sale_item_id == sale_item_id,
          ),
          Warranty.status == "ACTIVE",
      )
      ```
    - If `sale_item_id` is a plan line (`Warranty.plan_sale_item_id == sale_item_id`): cancels only the extended warranties. Base warranties remain `ACTIVE`.
    - If `sale_item_id` is a base line (`Warranty.sale_item_id == sale_item_id`): cancels the base warranties `w`, AND queries and cancels any active extended warranty where `Warranty.covers_warranty_id == w.id`.
    - Serial selection: selecting Serial `S` for refund cancels the base warranty with serial `S` and specifically cancels the extended warranty linked to it via `covers_warranty_id`.
  - Voiding a sale: `WarrantyService.void_sale_warranties_in_session` marks all warranties belonging to `sale_id` (both base and extended) `VOID`.
- **Proof:** Failure-injection and refund scenarios testing base-only, plan-only, and combined refunds.

### Invariant 7: Reporting Permission Seam Extension
- **Rule:** Reports must support multiple required permissions.
- **Implementation:**
  - `BaseReport.required_permissions: tuple[str, ...]` (defaults to `(self.required_permission,)`).
  - `ClaimCostReport`: `required_permissions = (Permissions.REPORTS_VIEW_PROFIT, Permissions.WARRANTY_VIEW)`.
  - Other warranty reports: `required_permissions = (Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW)`.
  - `ReportService.available_reports` and `ReportService.run` enforce that the user holds ALL required permissions:
    ```python
    all(PermissionService.user_has_permission(user, p) for p in report.required_permissions)
    ```
- **Proof:** Permission combination matrix tests asserting access allowed/denied for Cashier, Manager, Admin, and custom roles.

### Invariant 8: Five Reports Specification & Fixture Truth
- **All money, rate, and cost metrics use `Decimal`.**
- **Report 1: `ActiveWarrantiesReport` (`warranty_active`)**
  - **Category:** `CATEGORY_WARRANTY`
  - **Permissions:** `(Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW)`
  - **Filters:** `date_range` (sold date), `category_id` (combo), `warranty_type` (combo: ALL, SHOP, MANUFACTURER, EXTENDED), `status` (combo: ALL, ACTIVE, EXPIRING, EXPIRED)
  - **Columns:**
    - "Warranty Code": `TEXT` (`reports.col_warranty_code`)
    - "Product": `TEXT` (`reports.col_product`)
    - "Serial Number": `TEXT` (`reports.col_serial_number`)
    - "Customer": `TEXT` (`reports.col_customer`)
    - "Phone": `TEXT` (`reports.col_phone`)
    - "Sold Date": `DATE` (`reports.col_sold_date`)
    - "Valid Until": `DATE` (`reports.col_valid_until`)
    - "Type": `TEXT` (`reports.col_type`)
    - "Plan Revenue": `MONEY` (`reports.col_plan_revenue`) — price of linked plan line, or 0.00 if base warranty
    - "Status": `TEXT` (`reports.col_status`)
- **Report 2: `ExpiringWarrantiesReport` (`warranty_expiring`)**
  - **Category:** `CATEGORY_WARRANTY`
  - **Permissions:** `(Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW)`
  - **Filters:** `days_ahead` (combo: 7, 14, 30 [default], 60, 90), `category_id` (combo), `warranty_type` (combo)
  - **Columns:**
    - "Warranty Code": `TEXT` (`reports.col_warranty_code`)
    - "Customer": `TEXT` (`reports.col_customer`)
    - "Phone": `TEXT` (`reports.col_phone`)
    - "Product": `TEXT` (`reports.col_product`)
    - "Serial Number": `TEXT` (`reports.col_serial_number`)
    - "Valid Until": `DATE` (`reports.col_valid_until`)
    - "Days Remaining": `INT` (`reports.col_days_remaining`)
    - "Type": `TEXT` (`reports.col_type`)
- **Report 3: `ClaimsRegisterReport` (`warranty_claims_register`)**
  - **Category:** `CATEGORY_WARRANTY`
  - **Permissions:** `(Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW)`
  - **Filters:** `date_range` (intake date), `claim_status` (combo), `resolution` (combo), `supplier_id` (combo)
  - **Columns:**
    - "Claim Number": `TEXT` (`reports.col_claim_number`)
    - "Intake Date": `DATE` (`reports.col_intake_date`)
    - "Expected Ready": `DATE` (`reports.col_expected_ready`)
    - "Customer": `TEXT` (`reports.col_customer`)
    - "Phone": `TEXT` (`reports.col_phone`)
    - "Product": `TEXT` (`reports.col_product`)
    - "Serial Number": `TEXT` (`reports.col_serial_number`)
    - "Coverage": `TEXT` (`reports.col_coverage`)
    - "Status": `TEXT` (`reports.col_status`)
    - "Resolution": `TEXT` (`reports.col_resolution`)
    - "Days Open": `INT` (`reports.col_days_open`)
- **Report 4: `ClaimsByProductSupplierReport` (`warranty_claims_by_product_supplier`)**
  - **Category:** `CATEGORY_WARRANTY`
  - **Permissions:** `(Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW)`
  - **Filters:** `date_range` (sale / intake period), `group_by` (combo: "Product", "Supplier")
  - **Columns:**
    - "Name": `TEXT` (`reports.col_name`)
    - "Net Units Sold": `QTY` (`reports.col_net_units_sold`)
    - "Total Claims": `INT` (`reports.col_total_claims`)
    - "Replacements": `INT` (`reports.col_replacements`)
    - "Rejections": `INT` (`reports.col_rejections`)
    - "Claim Rate": `PERCENT` (`reports.col_claim_rate`)
    - "Avg Turnaround Days": `INT` (`reports.col_avg_turnaround_days`)
  - **Claim Rate Formula:** `claims_in_period / net_units_sold_in_period`. Net units sold = `sum(SaleItem.qty) - sum(SaleItem.refunded_qty)`. If net units sold <= 0: claim rate is `0.00%`.
- **Report 5: `ClaimCostReport` (`warranty_claim_cost`)**
  - **Category:** `CATEGORY_WARRANTY`
  - **Permissions:** `(Permissions.REPORTS_VIEW_PROFIT, Permissions.WARRANTY_VIEW)`
  - **Filters:** `date_range` (resolution date), `resolution` (combo)
  - **Columns:**
    - "Claim Number": `TEXT` (`reports.col_claim_number`)
    - "Product": `TEXT` (`reports.col_product`)
    - "Replacement Cost": `TEXT` (`reports.col_replacement_cost`) — formatted money or `"-"` if historical unknown
    - "Repair Cost": `MONEY` (`reports.col_repair_cost`)
    - "Customer Charge": `MONEY` (`reports.col_customer_charge`)
    - "Supplier Credit": `MONEY` (`reports.col_supplier_credit`)
    - "Net Cost": `TEXT` (`reports.col_net_cost`) — formatted money or `"-"` if replacement cost unknown
  - **Net Cost Formula:** `(replacement_cost_snapshot or 0) + repair_cost - charge_customer - supplier_credit_amount`.

### Invariant 9: Dashboard & Board Filter Parity
- **Rule:** `WarrantyClaimService.get_claims_summary()` is the single source of truth:
  - Open claims: `claim_status.in_(["INTAKE", "IN_INSPECTION", "SUPPLIER_DISPATCHED", "SUPPLIER_RETURNED"])`.
  - Ready for pickup: `claim_status == "RESOLVED"`.
  - Overdue at supplier: matching `list_claims(status="OVERDUE_SUPPLIER")`:
    ```python
    (WarrantyClaim.defective_unit_status == "SENT_TO_SUPPLIER",)
    WarrantyClaim.sent_to_supplier_at <= cutoff
    ```
- Clicking the dashboard tile opens the Claims board with the identical filter applied.
- **Proof:** DB count assertions showing identical numbers returned by the summary helper and the Claims board filtered query.

### Invariant 10: Scheduler & Dashboard Threading Safety
- **Rule:**
  - `DashboardView` loads warranty tile counts via a background worker (`_WarrantyTileWorker`), delivering counts via Qt signals. No DB work on UI thread.
  - `SchedulerService.check_automation`:
    - Checks `ConfigService.get("warranty_reminders_last_run") == today_str`. If already checked today, skips.
    - Derives overdue claims (`expected_ready_date < today` and open) and overdue RMAs (`defective_unit_status == "SENT_TO_SUPPLIER"` and `sent_to_supplier_at <= cutoff`).
    - Writes `warranty_reminders_last_run = today_str`.
    - Emits in-app notices / updates dashboard badge without modal popups.
    - No background mutation of expired warranty status.
    - No external network, SMS, or email sending.

---

## 4. Schema & Data Model Changes

### 4.1 Products, Policies & Categories
```python
# cbpos/core/models/warranty.py -> WarrantyPolicy
extended_starts: Mapped[str] = mapped_column(
    String(20), default="AFTER_BASE", server_default="AFTER_BASE", nullable=False
)

# cbpos/core/models/__init__.py -> Product
is_warranty_plan: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
plan_policy_id: Mapped[int | None] = mapped_column(ForeignKey("warranty_policies.id"), nullable=True, index=True)
plan_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)

plan_policy: Mapped[Optional["WarrantyPolicy"]] = relationship("WarrantyPolicy", foreign_keys=[plan_policy_id])
plan_category: Mapped[Optional["Category"]] = relationship("Category", foreign_keys=[plan_category_id])
```

### 4.2 Sale Items
```python
# cbpos/core/models/__init__.py -> SaleItem
covered_item_id: Mapped[int | None] = mapped_column(ForeignKey("sale_items.id"), nullable=True, index=True)
covered_item: Mapped[Optional["SaleItem"]] = relationship("SaleItem", remote_side=[id], foreign_keys=[covered_item_id])
```

### 4.3 Warranties
```python
# cbpos/core/models/warranty.py -> Warranty
plan_sale_item_id: Mapped[int | None] = mapped_column(
    ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=True, index=True
)
plan_sale_item: Mapped[Optional["SaleItem"]] = relationship("SaleItem", foreign_keys=[plan_sale_item_id])
```

### 4.4 Warranty Claims
```python
# cbpos/core/models/warranty_claim.py -> WarrantyClaim
expected_ready_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
replacement_cost_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
```

---

## 5. Implementation & Commit Sequence

1. **Commit 1: Schema migration & models**
   - Migration `c5d6e7f8a9b0_add_extended_warranty_and_claim_reporting_fields.py`
   - Models: `WarrantyPolicy.extended_starts`, `Product.is_warranty_plan`, `Product.plan_policy_id`, `Product.plan_category_id`, `SaleItem.covered_item_id`, `Warranty.plan_sale_item_id`, `WarrantyClaim.expected_ready_date`, `WarrantyClaim.replacement_cost_snapshot`.
   - Update `replace_from_stock()` to capture `Product.cost` snapshot.
   - Sync protocol and `TERMINAL_REFS` updates.

2. **Commit 2: Paid extended-warranty plans (#829)**
   - `CartService` stable `line_id` and `covered_line_id` bookkeeping.
   - Merging, reduction, removal, and `SuspendedTransactionService` v2 integration.
   - `TransactionService` atomic registration of base + extended warranties.
   - `RefundService` plan-line and base-unit cascade handling.
   - UI: Product editor warranty tab, sales view plan binding, receipt/invoice/certificate builders.
   - Push: `feat(warranty): add paid extended warranty plans (#829)`.

3. **Commit 3: Reports, dashboard tile & reminders (#830)**
   - `CATEGORY_WARRANTY` in `base_report.py` and `register_all_reports()`.
   - 5 reports implementation (`ActiveWarrantiesReport`, `ExpiringWarrantiesReport`, `ClaimsRegisterReport`, `ClaimsByProductSupplierReport`, `ClaimCostReport`).
   - `BaseReport.required_permissions` seam extension in `report_service.py`.
   - Dashboard KPI tile with `WarrantyClaimService.get_claims_summary()`.
   - `SchedulerService` non-blocking daily reminders.
   - Push: `feat(warranty): add reports and reminders (#830)`.

4. **Commit 4: Verification, UI gate & Review addresses**
   - Impeccable review, light/dark screenshots, full test suite pass.
   - Push: `fix(warranty): address Phase 9.6 review findings (#829, #830)`.
