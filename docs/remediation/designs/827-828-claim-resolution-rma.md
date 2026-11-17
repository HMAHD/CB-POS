# Technical Design: Warranty Claim Resolution & Supplier RMA (#827, #828)

**Phase:** 9 · **Batch:** 9.5  
**Issues:** #827 (Warranty W7: Replacement & Refund Resolution), #828 (Warranty W8: Supplier RMA Tracking) · **Epic:** #820  
**Owner:** CB POS Remediation Team  
**Date:** 2026-11-17  
**Status:** APPROVED (Post-EGM Revisions Applied)  

---

## 1. Context & Objectives

In Phase 9 Batches 9.1–9.4 (#821, #822, #823, #824, #825, #826), CB POS implemented:
1. Reusable `WarrantyPolicy` models, product/category assignment precedence, calendar-aware duration arithmetic, and feature gating.
2. Per-unit `Warranty` registration at checkout (`<doc_number>-01..NN`), whole-unit validation, void/refund cascades with per-unit cancellation, and LAN sync protocol 1.4.
3. Checkout serial/IMEI capture, cart serial bookkeeping, held bill persistence, and customer-facing delivery (thermal receipt warranty blocks, A4 invoice lines, standalone thermal/PDF warranty cards).
4. Counter warranty lookup (barcode, serial, phone, customer), live effective status calculations, admin corrections with audit, and intake tickets (`WC-{Y}-{seq:05d}`) with claims board UI and sync protocol 1.5.

**Batch 9.5 (#827, #828)** completes the operational resolution and supplier supply-chain loops:
- **Issue #827 (W7)**: Atomic claim resolution via stock replacement or partial refund.
  - Stock replacement deducts a replacement unit from inventory (`MovementType.WARRANTY`), supersedes the old warranty, issues a linked replacement warranty (`replaces_warranty_id`), applies `REMAINING` vs `FRESH` policy terms, records serials, and ensures the defective unit is never returned to sellable stock.
  - Refund resolution routes directly through `RefundService.refund` for the exact claimed unit, canceling the warranty, issuing a statutory Credit Note (CN), allocating original tenders, and neutralizing normal refund return stock with a defective adjustment inside the same transaction.
- **Issue #828 (W8)**: Supplier and manufacturer RMA tracking.
  - Tracks dispatch to suppliers (`SUPPLIER_DISPATCHED`), return receipts (`IN_INSPECTION` / `SUPPLIER_RETURNED`), and manufacturer outcomes (`REPAIRED`, `REPLACED`, `CREDIT_NOTE`, `REJECTED`).
  - Maintains strict stock and payable integrity: supplier replacements restock the shop if a customer replacement was already provided; supplier credit notes reduce `Supplier.current_payable` and create a ledger row referencing the WC claim number.
  - Generates privacy-preserving supplier dispatch notes (thermal ESC/POS and vector PDF) omitting customer PII.
  - Calculates non-binding supplier coverage estimates from latest GRN purchase dates.

---

## 2. Elephant Pass: End-to-End Transaction Architecture

Every operational action across #827 and #828 spans multiple subsystems that must maintain strict consistency:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              ELEPHANT PASS: TRANSACTION MAP                            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  [Claim: INTAKE / IN_INSPECTION]                                                      │
│        │                                                                               │
│        ├─── (Resolution: Replacement) ───────────────────────────────────────────┐     │
│        │    1. Lock Claim, Old Warranty, Replacement Product                     │     │
│        │    2. Stock -1 (MovementType.WARRANTY, doc_id=claim.id)                 │     │
│        │    3. Old Warranty status -> REPLACED                                   │     │
│        │    4. Create New Warranty (replaces_warranty_id=old.id, REMAINING/FRESH)│     │
│        │    5. Claim status -> RESOLVED, defective_unit_status -> HELD           │     │
│        │    6. WarrantyClaimEvent + AuditLog (WARRANTY_EVENT)                    │     │
│        │                                                                         │     │
│        ├─── (Resolution: Refund) ────────────────────────────────────────────────┤     │
│        │    1. Lock Claim & Warranty                                             │     │
│        │    2. Call RefundService.refund() in caller-session:                    │     │
│        │       - Creates refund Sale (CN-...)                                    │     │
│        │       - Reverses tenders (Cash/Card/Credit/Loyalty)                     │     │
│        │       - Normal stock +1 (RETURN)                                        │     │
│        │       - Cancels claimed warranty                                        │     │
│        │    3. Neutralize Stock: Stock -1 (ADJUSTMENT, defective_not_sellable)   │     │
│        │       ==> Net sellable stock change = 0                                 │     │
│        │    4. Claim status -> RESOLVED, refund_sale_id = CN.id, def_status=HELD │     │
│        │    5. WarrantyClaimEvent + AuditLog (WARRANTY_EVENT)                    │     │
│        │                                                                         │     │
│        └─── (Supplier RMA Dispatch & Return) ────────────────────────────────────┘     │
│             1. Dispatch: supplier_id required -> SUPPLIER_DISPATCHED                   │
│                defective_unit_status -> SENT_TO_SUPPLIER                               │
│                Print Supplier Dispatch Note (ESC/POS & PDF, Customer Hidden)           │
│             2. Receive: back from supplier -> IN_INSPECTION / SUPPLIER_RETURNED         │
│                defective_unit_status -> RETURNED_FROM_SUPPLIER                         │
│             3. Outcome:                                                                │
│                - REPAIRED: no stock change                                             │
│                - REPLACED (if customer already got replacement):                       │
│                    Stock +1 (MovementType.WARRANTY, doc_id=claim.id)                  │
│                - REPLACED (if customer waiting for supplier unit):                     │
│                    Update customer replacement warranty serial                         │
│                - CREDIT_NOTE:                                                          │
│                    SupplierPayableService.record_credit_note_in_session()              │
│                    reduce supplier.current_payable, write SupplierLedgerEntry          │
│                - REJECTED: no stock or ledger change                                   │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Database Schema & Reversible Migration

### 3.1 Model Changes (`cbpos/core/models/warranty_claim.py`)

Add the following columns to `warranty_claims` (table inheritance from `documents`):

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `defective_unit_status` | `String(30)` | No | `"HELD"` | Physical status of defective unit: `HELD`, `SENT_TO_SUPPLIER`, `RETURNED_FROM_SUPPLIER`, `SCRAPPED`, `RETURNED_TO_CUSTOMER` |
| `refund_sale_id` | `Integer` | Yes | `None` | FK to `sales.id` (`ondelete="SET NULL"`), linking the credit note issued for refund resolution |
| `supplier_id` | `Integer` | Yes | `None` | FK to `suppliers.id` (`ondelete="RESTRICT"`), identifying RMA vendor |
| `supplier_rma_ref` | `String(100)` | Yes | `None` | Vendor RMA tracking or case reference |
| `sent_to_supplier_at` | `DateTime` | Yes | `None` | Timestamp when physical unit was dispatched to supplier |
| `returned_from_supplier_at` | `DateTime` | Yes | `None` | Timestamp when physical unit or replacement was received back |
| `supplier_outcome` | `String(30)` | Yes | `None` | Resolution from supplier: `REPAIRED`, `REPLACED`, `CREDIT_NOTE`, `REJECTED` |
| `supplier_credit_amount` | `Numeric(12, 2)` | No | `Decimal("0.00")` | Credit note amount received from supplier |

### 3.2 Constraints & Indexes

```python
CheckConstraint(
    "defective_unit_status IN ('HELD', 'SENT_TO_SUPPLIER', 'RETURNED_FROM_SUPPLIER', 'SCRAPPED', 'RETURNED_TO_CUSTOMER')",
    name="ck_warranty_claims_defective_status",
)
CheckConstraint(
    "supplier_outcome IS NULL OR supplier_outcome IN ('REPAIRED', 'REPLACED', 'CREDIT_NOTE', 'REJECTED')",
    name="ck_warranty_claims_supplier_outcome",
)
```

Indexes:
- `ix_warranty_claims_supplier_id` on `(supplier_id)`
- `ix_warranty_claims_refund_sale_id` on `(refund_sale_id)`
- `ix_warranty_claims_sent_supplier` on `(sent_to_supplier_at)`

### 3.3 Reversible Alembic Migration

Create migration `b4c5d6e7f8a9_add_claim_resolution_and_rma_fields.py`:
- **Upgrade**:
  - Add columns to `warranty_claims` with server defaults (`server_default="HELD"` for `defective_unit_status`, `server_default="0.00"` for `supplier_credit_amount`).
  - Add foreign keys and indexes.
  - Add check constraints (using batch mode for SQLite).
- **Downgrade**:
  - Drop constraints, indexes, foreign keys, and columns in reverse order (using batch mode for SQLite).

---

## 4. Goldfish Seam 1: MovementType.WARRANTY & Stock Service (#827)

### 4.1 MovementType Constant & Registration

In `cbpos/core/constants/status.py`:
```python
class MovementType:
    SALE = "SALE"
    PURCHASE = "PURCHASE"
    ADJUSTMENT = "ADJUSTMENT"
    RETURN = "RETURN"
    VOID = "VOID"
    OPENING = "OPENING"
    WARRANTY = "WARRANTY"  # Phase 9 W7 / W8 (#827, #828)
```

In `cbpos/core/services/stock_service.py`:
```python
_VALID_MOVEMENT_TYPES = frozenset(
    {
        MovementType.SALE,
        MovementType.PURCHASE,
        MovementType.ADJUSTMENT,
        MovementType.RETURN,
        MovementType.VOID,
        MovementType.OPENING,
        MovementType.WARRANTY,
    }
)
```

### 4.2 Translation & History UI Seams

In `cbpos/ui/dialogs/stock_history_dialog.py`:
```python
type_labels = {
    ...
    "WARRANTY": _t("stock_history.type_warranty", default="Warranty"),
}
type_meanings = {
    ...
    "WARRANTY": "info",
}
```

In `cbpos/i18n/{en,si,ta}.json`:
- `stock_history.type_warranty`: "Warranty" / "වගකීම්" / "உத்தரவாதம்"
- `stock.movement_warranty`: "Warranty replacement" / "වගකීම් ප්‍රතිස්ථාපනය" / "உத்தரவாத மாற்றீடு"

---

## 5. Goldfish Seam 2: Stock Replacement (`replace_from_stock`) (#827)

### 5.1 Service Interface

```python
@classmethod
def replace_from_stock(
    cls,
    claim_id: int,
    replacement_product_id: int,
    user_id: int,
    new_serial: str | None = None,
    resolution_notes: str | None = None,
    repair_cost: Decimal = Decimal("0.00"),
    charge_customer: Decimal = Decimal("0.00"),
    session: Session | None = None,
) -> WarrantyClaimDTO:
    """Resolve claim by issuing a replacement unit from shop inventory in one atomic transaction."""
```

### 5.2 Atomic Invariants & Execution Sequence

1. **Authorization & State Validation**:
   - Requires `Permissions.WARRANTY_CLAIM_RESOLVE` (or authenticated manager override).
   - Claim must exist and be in state `IN_INSPECTION`, `SUPPLIER_RETURNED`, or `SUPPLIER_DISPATCHED` (if shop decides to issue an advance shelf replacement while defective unit is at supplier). Cannot resolve `FINAL_STATUSES` (`COLLECTED`, `REJECTED`, `VOID`, `CANCELLED`).
   - Claim must have a linked `warranty` (`claim.warranty_id is not None`).
2. **Locking**:
   - `SELECT ... FOR UPDATE` on `WarrantyClaim`, `Warranty`, and replacement `Product`.
3. **Inventory Deduction**:
   - `StockService.record_movement(...)`:
     - `product_id = replacement_product_id`
     - `qty_change = Decimal("-1.000")`
     - `movement_type = MovementType.WARRANTY`
     - `document_id = claim.id`
     - `user_id = user_id`
     - `session = s`
     - `enforce_non_negative = True`
   - If stock is insufficient, `InsufficientStockError` / `ValueError("insufficient_stock")` is raised and transaction aborts immediately.
4. **Old Warranty Transition**:
   - `old_w.status = "REPLACED"`
   - `old_w.last_modified = now`
5. **Coverage Term Determination & Database Constraint Guard**:
   - Read shop setting `ConfigService.get("warranty_replacement_term") or "REMAINING"`.
   - Table `warranties` strictly enforces `CheckConstraint("end_date >= start_date", name="ck_warranties_dates")`.
   - If `REMAINING`: `new_end_date = max(now.date(), old_w.end_date)` (prevents constraint violation when intake/inspection elapsed past original expiry).
   - If `FRESH`: `new_end_date = WarrantyService.compute_end_date(now.date(), old_w.duration, old_w.duration_unit)`.
6. **New Warranty Creation**:
   - Generate code: `{old_w.code}-R` (or timestamp-disambiguated `{old_w.code}-R{mmddHHMM}`).
   - Copy immutable snapshots: `sale_id`, `sale_item_id`, `customer_id`, `policy_id`, `warranty_type`, `duration`, `duration_unit`, `remedy`, `provider_name`, `terms_text`, `exclusions_text`.
   - Set `product_id = replacement_product_id`.
   - Set `serial_number = new_serial.strip().upper() if new_serial else None`.
   - Set `start_date = now.date()`, `end_date = new_end_date`.
   - Set `status = "ACTIVE"`.
   - Set `replaces_warranty_id = old_w.id`.
7. **Claim State Mutation**:
   - `claim.claim_status = "RESOLVED"`
   - `claim.resolution = "REPLACED_SAME" if replacement_product_id == old_w.product_id else "REPLACED_DIFFERENT"`
   - `claim.replacement_warranty_id = new_w.id`
   - `claim.replacement_serial = new_w.serial_number`
   - `claim.defective_unit_status = "HELD"` if `claim.claim_status != "SUPPLIER_DISPATCHED"` else `"SENT_TO_SUPPLIER"` (never returned to inventory)
   - `claim.resolved_by_user_id = user_id`
   - `claim.resolved_at = now`
   - `claim.resolution_notes = resolution_notes`
   - `claim.repair_cost = Decimal(str(repair_cost or 0))`
   - `claim.charge_customer = Decimal(str(charge_customer or 0))`
8. **Audit Trail**:
   - Add `WarrantyClaimEvent(from_status=old_status, to_status="RESOLVED", notes="Resolved via stock replacement...")`.
   - Add `AuditLog(action="WARRANTY_REPLACEMENT_FROM_STOCK", event_type=WARRANTY_EVENT, details=...)`.
9. **Failure Injection**:
   - Any mid-transaction exception rolls back the stock movement, warranty status, claim status, and audit records cleanly.

---

## 6. Goldfish Seam 3: Refund Resolution & Defective Stock Neutrality (#827)

### 6.1 Deepening `RefundService.refund` with Caller Session

Currently, `RefundService.refund(...)` opens its own session:
```python
db = Database()
with db.get_session() as session:
```
Deepen `RefundService.refund(...)` to accept `session: Session | None = None`. If provided, it executes within the caller's transaction and does not commit or close the session; hardware printer notifications fire only after transaction commit.

### 6.2 Service Interface in `WarrantyClaimService`

```python
@classmethod
def refund_claim(
    cls,
    claim_id: int,
    user_id: int,
    reason: str | None = None,
    tender_override: str | None = None,
    override_reason: str | None = None,
    session: Session | None = None,
) -> tuple[WarrantyClaimDTO, RefundResult]:
    """Resolve claim by refunding the claimed unit through RefundService.refund."""
```

### 6.3 Defective Stock Neutrality & Linkage Sequence

1. **Unit Identification & Permission**:
   - Requires `Permissions.WARRANTY_CLAIM_RESOLVE` (or authenticated manager override).
   - Load claim and `claim.warranty`.
   - Verify `old_w.sale_id` and `old_w.sale_item_id` exist.
2. **Pre-Setting Claim Resolution (Refund Guard Seam)**:
   - In `WarrantyService.cancel_units_for_refund_in_session` (`cbpos/core/services/warranty_service.py` L606–635), active claims on a refund line are validated:
     ```python
     if active_claims:
         matching_claim = next((c for c in active_claims if c.id == claim_id), None)
         if matching_claim is not None and matching_claim.resolution == "REFUNDED":
             matching_claim.claim_status = "COLLECTED"
             ...
         else:
             raise ValueError("cannot_refund_unit_with_open_claim")
     ```
   - Therefore, `claim.resolution = "REFUNDED"` MUST be set on the claim model and flushed *before* invoking `RefundService.refund(...)` so the refund engine recognizes the authorized claim resolution.
3. **Execute Refund**:
   - Call `RefundService.refund(sale_id=old_w.sale_id, lines=[RefundLineRequest(sale_item_id=old_w.sale_item_id, qty=Decimal("1.000"), reason=reason or f"Warranty claim {claim.document_number}")], user_id=user_id, tender_override=tender_override, override_reason=override_reason, selected_serials={old_w.sale_item_id: [old_w.serial_number]} if old_w.serial_number else None, claim_id=claim.id, session=s)`.
   - `RefundService.refund` creates the refund `Sale` (`CN-...`), allocates tenders, creates `SaleItem` rows, adjusts loyalty, automatically transitions the matching claim to `COLLECTED` via `cancel_units_for_refund_in_session`, and writes a `MovementType.RETURN` (+1) stock movement.
4. **Stock Neutralization**:
   - Because the defective unit is broken and cannot be sold, immediately offset the +1 `RETURN`:
     ```python
     StockService.record_movement(
         product_id=old_w.product_id,
         qty_change=Decimal("-1.000"),
         movement_type=MovementType.ADJUSTMENT,
         user_id=user_id,
         document_id=claim.id,
         session=s,
         enforce_non_negative=False,
     )
     ```
   - This records the defect adjustment in `StockMovement` with reference to the claim, ensuring net inventory change for sellable stock is exactly 0.
5. **Claim Resolution Linkage**:
   - `claim.refund_sale_id = refund_result.refund_sale_id`
   - `claim.resolution = "REFUNDED"`
   - `claim.claim_status = "COLLECTED"` (customer received money back; refund resolution is immediately complete)
   - `claim.defective_unit_status = "HELD"`
   - `claim.resolved_by_user_id = user_id`
   - `claim.resolved_at = now`
6. **Events & Audit**:
   - Add `WarrantyClaimEvent(to_status="COLLECTED", notes="Resolved via refund CN-...")` (deduplicating with `cancel_units_for_refund_in_session`).
   - Add `AuditLog(action="WARRANTY_CLAIM_REFUND", event_type=WARRANTY_EVENT, details=...)` referencing both the claim and the refund document number (`CN-...`).

---

## 7. Goldfish Seam 4: Supplier RMA Tracking (#828)

### 7.1 RMA State Machine Transitions

```
[IN_INSPECTION] ──(send_to_supplier)──> [SUPPLIER_DISPATCHED]
      ▲                                       │
      │                                       │ (receive_from_supplier)
      │                                       ▼
      └──────────────────────────── [SUPPLIER_RETURNED]
                                              │
                                              ▼ (record_supplier_outcome)
                                         [RESOLVED]
```

### 7.2 Service Methods

1. **`send_to_supplier(claim_id, supplier_id, user_id, supplier_rma_ref=None, notes=None, session=None) -> WarrantyClaimDTO`**:
   - Requires `supplier_id`. Rejects if missing.
   - Validates claim status and physical unit state:
     - If `claim.claim_status in ("IN_INSPECTION", "INTAKE")`: transitions `claim.claim_status = "SUPPLIER_DISPATCHED"`.
     - If customer already received resolution (`claim.claim_status in ("RESOLVED", "COLLECTED")`): requires `claim.defective_unit_status == "HELD"`. The physical unit is dispatched without altering customer resolution status.
   - Sets:
     - `claim.supplier_id = supplier_id`
     - `claim.supplier_rma_ref = supplier_rma_ref.strip() if supplier_rma_ref else None`
     - `claim.sent_to_supplier_at = now`
     - `claim.defective_unit_status = "SENT_TO_SUPPLIER"`
   - Adds `WarrantyClaimEvent` and `AuditLog(action="WARRANTY_SUPPLIER_DISPATCH")`.

2. **`receive_from_supplier(claim_id, user_id, to_status="SUPPLIER_RETURNED", notes=None, session=None) -> WarrantyClaimDTO`**:
   - Validates `claim.defective_unit_status == "SENT_TO_SUPPLIER"`.
   - If `claim.claim_status == "SUPPLIER_DISPATCHED"`:
     - Validates `to_status in ("IN_INSPECTION", "SUPPLIER_RETURNED")`.
     - `claim.claim_status = to_status`
   - If claim was already resolved prior to RMA (`claim.claim_status in ("RESOLVED", "COLLECTED")`): customer status is preserved.
   - Sets:
     - `claim.returned_from_supplier_at = now`
     - `claim.defective_unit_status = "RETURNED_FROM_SUPPLIER"`
   - Adds `WarrantyClaimEvent` and `AuditLog(action="WARRANTY_SUPPLIER_RECEIVE")`.
   - Idempotent: cannot be received multiple times while not dispatched.

3. **`record_supplier_outcome(claim_id, outcome, user_id, credit_amount=Decimal("0.00"), replacement_serial=None, notes=None, session=None) -> WarrantyClaimDTO`**:
   - Validates `outcome in ("REPAIRED", "REPLACED", "CREDIT_NOTE", "REJECTED")`.
   - Validates `claim.defective_unit_status in ("SENT_TO_SUPPLIER", "RETURNED_FROM_SUPPLIER")`.
   - **Outcome Matrix**:
     - `REPAIRED`:
       - No stock changes.
       - `defective_unit_status = "HELD"`.
     - `REPLACED`:
       - Check if shop already issued a stock replacement to the customer:
         `has_prior_stock_replacement = claim.resolution in ("REPLACED_SAME", "REPLACED_DIFFERENT") or claim.replacement_warranty_id is not None`.
       - If `has_prior_stock_replacement`:
         - The supplier's replacement unit restocks the shop's sellable inventory:
           `StockService.record_movement(product_id=claim.product_id, qty_change=Decimal("1.000"), movement_type=MovementType.WARRANTY, user_id=user_id, document_id=claim.id, session=s, enforce_non_negative=False)`.
         - `defective_unit_status = "SCRAPPED"` (supplier kept defective unit; replacement restocked inventory).
       - If `not has_prior_stock_replacement`:
         - No inventory addition.
         - The received unit is allocated to the customer. Update `claim.replacement_serial = replacement_serial` and if a replacement warranty exists, update its `serial_number`.
         - `defective_unit_status = "SCRAPPED"`.
     - `CREDIT_NOTE`:
       - Validates `credit_amount > Decimal("0.00")`.
       - Deepen `SupplierPayableService`:
         ```python
         SupplierPayableService.record_credit_note_in_session(
             session=s,
             supplier_id=claim.supplier_id,
             amount=credit_amount,
             claim_id=claim.id,
             claim_number=claim.document_number,
             user_id=user_id,
             note=notes or f"Supplier credit for claim {claim.document_number}",
         )
         ```
       - Decrements `supplier.current_payable -= credit_amount`.
       - Adds `SupplierLedgerEntry(supplier_id=supplier.id, entry_type="CREDIT_NOTE", amount=-credit_amount, balance_after=supplier.current_payable, reference_id=claim.id, reference_doc=claim.document_number, user_id=user_id)`.
       - **FIFO Aging Update**: In `SupplierPayableService.oldest_unpaid_charge_date` and `get_overdue_suppliers`, expand `credit_types` from `{"PAYMENT", "REFUND", "ADJUSTMENT"}` to include `"CREDIT_NOTE"`.
       - Sets `claim.supplier_credit_amount = credit_amount`.
     - `REJECTED`:
       - No stock or ledger change.
   - Sets:
     - `claim.supplier_outcome = outcome`
     - `claim.claim_status = "RESOLVED"` (if not already resolved/collected)
     - `claim.resolved_at = now`
     - `claim.resolved_by_user_id = user_id`
   - Adds `WarrantyClaimEvent` and `AuditLog`.

---

## 8. Goldfish Seam 5: Supplier Coverage Estimation (#828)

### 8.1 Method Specification

```python
@classmethod
def estimate_supplier_coverage(
    cls,
    product_id: int,
    supplier_id: int | None = None,
    session: Session | None = None,
) -> dict[str, Any]:
    """Estimate supplier warranty validity from latest relevant GRN purchase date."""
```

### 8.2 Calculation Rules

1. Resolve product policy `supplier_cover_months` (via `WarrantyService.resolve_policy(product_id)`).
2. If `supplier_cover_months is None` or `<= 0`: return `{"has_estimate": False, "reason": "no_supplier_cover_policy"}`.
3. Query `PurchaseItem` joined with `Purchase`:
   - Filter `PurchaseItem.product_id == product_id`, `Purchase.status == DocumentStatus.COMPLETED`.
   - If `supplier_id` provided, filter `Purchase.supplier_id == supplier_id`.
   - Order by `Purchase.date.desc()`.
4. If no purchase found: return `{"has_estimate": False, "reason": "no_purchase_history"}`.
5. Compute estimated expiry date:
   `estimated_expiry = grn_date.date() + relativedelta(months=supplier_cover_months)`.
6. Return:
   ```python
   {
       "has_estimate": True,
       "estimated_expiry": estimated_expiry,
       "grn_date": grn_date.date(),
       "supplier_cover_months": supplier_cover_months,
       "is_valid": estimated_expiry >= date.today(),
       "days_remaining": (estimated_expiry - date.today()).days,
       "is_estimate": True,
   }
   ```
7. **Guardrail**: The UI must display this with an explicit "Estimate" pill/label and never disable or auto-reject claim dispatch based on this value.

---

## 9. Goldfish Seam 6: Supplier Dispatch Note Artifacts (#828)

### 9.1 Privacy & Content Rules

- **Privacy Invariant**: Customer name, phone, address, and email MUST BE OMITTED from supplier dispatch notes. Suppliers receive only product, fault, and shop identification.
- **Shop Header**: Business name, branch/terminal, contact number, email, address.
- **RMA Info**: Claim document number (`WC-...`), barcode (rendered via `choose_barcode`), dispatch date, supplier name, supplier RMA reference.
- **Product Details**: Product name, brand/model, serial/IMEI, accessories received, physical condition, detailed defect description.
- **CB POS Branding**: Retained in footer.

### 9.2 Rendering Formats & Non-Blocking Qt Execution (Rule 6)

- **Strict Non-Blocking Rule**: In accordance with `GEMINI.md` Rule 6, ReportLab vector PDF rendering, ESC/POS byte generation, and socket/spool I/O must NEVER run on the Qt UI thread.
1. **Thermal ESC/POS (58mm / 80mm)**:
   - Built via `WarrantyClaimReceiptBuilder.build_supplier_dispatch_receipt(claim_dto, supplier_name, shop_info, paper_width="80mm")`.
   - Uses trilingual raster rendering for Sinhala/Tamil text and standard barcode commands for CODE128.
   - Dispatched asynchronously through `PrintWorker.instance().add_job("print_commands", commands)`.
2. **Vector PDF (A4 / A5)**:
   - Built via `SupplierDispatchNotePDFBuilder.generate_pdf(...)` using ReportLab.
   - Clean tabular layout for service center handoff.
   - Executed inside a dedicated worker (`SupplierDispatchPDFWorker(QThread)`) with `finished` signal and progress indication, saving the file to an operator-selected location without freezing the UI.

---

## 10. Goldfish Seam 7: UI Extensions & Impeccable Gate (#827, #828)

### 10.1 Claims Board Extensions (`WarrantyClaimsBoardView`)

1. **Filters**:
   - Status combo includes `SUPPLIER_DISPATCHED` ("At Supplier").
   - Added checkbox / toggle: `chk_overdue_supplier`: "Overdue at Supplier (> 14 days)".
   - Supplier filter dropdown (populated with active suppliers).
2. **Master Table Columns**:
   - Added column: "Days Out" (`days_outstanding` when `claim_status == 'SUPPLIER_DISPATCHED'`).
   - Color coded: `> 14 days` highlighted in warning/danger.
3. **Detail Panel & Actions**:
   - Added "Send to Supplier" dialog (`WarrantyClaimSupplierDispatchDialog`):
     - Supplier selection combo (defaults to product's `default_supplier_id`).
     - RMA Reference line edit.
     - Coverage estimate banner (shows estimated expiry and "Estimate based on latest GRN").
     - "Print Dispatch Note" checkbox.
   - Added "Receive from Supplier" action:
     - Prompts for notes / condition upon return.
   - Added "Supplier Outcome" dialog (`WarrantyClaimSupplierOutcomeDialog`):
     - Outcome combo: `REPAIRED`, `REPLACED`, `CREDIT_NOTE`, `REJECTED`.
     - Credit Note amount input (visible when `CREDIT_NOTE` selected).
     - New serial input (visible when `REPLACED` selected and no prior stock replacement).
4. **Resolution Dialog Updates (`WarrantyClaimResolveDialog`)**:
   - Integrates `replace_from_stock` directly when `REPLACED_SAME` or `REPLACED_DIFFERENT` is selected:
     - For `REPLACED_SAME`: replacement product is locked to `claim.product_id` and live stock quantity is displayed in an informative pill (`In stock: N`).
     - For `REPLACED_DIFFERENT`: reveals a product selection field (`cmb_replacement_product` or search picker) showing product name, barcode, and available stock.
     - Validates stock availability in real time (`stock_qty >= 1`), disabling the submit button and warning the cashier if out of stock.
   - Integrates `refund_claim` when `REFUNDED` is selected, showing tender preview and prompt for manager override if required.
   - Manager PIN override dialog shown if cashier lacks `warranty.claim_resolve`.

---

## 11. Multi-Terminal LAN Sync & Invariants

1. **Table Mappings**:
   - `warranty_claims` and `warranty_claim_events` are already mapped in `_TABLE_MODEL_MAP` and synced in Phase 9.4.
   - New columns on `warranty_claims` (`defective_unit_status`, `refund_sale_id`, `supplier_id`, `supplier_rma_ref`, `sent_to_supplier_at`, `returned_from_supplier_at`, `supplier_outcome`, `supplier_credit_amount`) are serialized in `cbpos/infrastructure/sync_client.py` and deserialized in `cbpos/core/services/sync_apply_service.py` (and `cbpos/infrastructure/sync_client.py`).
2. **Terminal Authority**:
   - Claims and supplier RMA workflows are authoritative on Main PC (`terminal_mode != "terminal"`).
   - Sync applies updates idempotently without modifying existing local ledger sequences.
3. **Backup / Restore / Data Export**:
   - Verify `warranty_claims` and `warranty_claim_events` in `data_export_service.py` export all new fields cleanly.

---

## 12. Verification & Test Plan

1. **Domain Tests (`tests/domain/test_warranty_claim_resolution_rma.py`)**:
   - Replacement:
     - Successful replacement with `REMAINING` end date.
     - Successful replacement with `FRESH` end date.
     - Insufficient stock rolls back entire transaction (stock, warranty, claim, audit).
     - Concurrent stock replacement under row lock.
   - Refund:
     - Successful unit refund links CN sale and cancels warranty.
     - Defective stock neutrality: +1 RETURN cancelled by -1 ADJUSTMENT.
     - Concurrent refund blocked on claim.
   - Supplier RMA:
     - `send_to_supplier` requires valid supplier.
     - Duplicate `receive_from_supplier` idempotence.
     - Supplier outcome `REPLACED` with prior stock replacement adds +1 WARRANTY stock.
     - Supplier outcome `REPLACED` without prior stock replacement updates serial without stock increase.
     - Supplier outcome `CREDIT_NOTE` reduces `supplier.current_payable` and writes `SupplierLedgerEntry`.
     - Coverage estimate from GRN date.
2. **Migration Tests**:
   - Upgrade and downgrade on SQLite and PostgreSQL.
3. **UI Tests (`tests/ui/test_warranty_claims_rma_ui.py`)**:
   - Dispatch dialog interaction, supplier selection, dispatch note printing trigger.
   - Outcome dialog interaction and ledger validation.
   - Overdue filter toggling and days outstanding display.
4. **Invariant Regression Tests**:
   - `test_money_invariants.py` and `test_stock_invariants.py` run green with warranty flows included.

