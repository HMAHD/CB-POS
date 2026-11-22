# Design Document: Phase 10B.4 (#926) Expiry Dates & Batches with Per-Batch MRP

**Issue:** #926 — Expiry dates and batches, with per-batch MRP (pharmacy, grocery, bakery)  
**Phase:** 10B.4  
**Decisions Reference:** D42–D53 (`docs/remediation/DECISIONS.md`), ADR 0003 (`docs/adr/0003-batch-and-expiry-tracking-invariants.md`)  
**Status:** Implementation Ready (Hardened after EGM Design Critic & Tech Lead Audits)  

---

## 1. Executive Summary & Problem Context

In Sri Lankan retail (specifically pharmacies, bakeries, groceries, and packaged consumer goods), products are received in distinct manufacturer lots carrying batch numbers and expiration dates. Due to government gazetted price controls (National Medicines Regulatory Authority / NMRA for medicines, Consumer Affairs Authority / CAA for essential foods) and frequent VAT/supplier revisions, the identical product often exists on the physical shelf under two different Maximum Retail Prices (MRPs). 

Under Sri Lankan law (Consumer Affairs Authority Act No. 9 of 2003, Section 29, and NMRA Act No. 5 of 2015), charging a customer more than the printed MRP on the package is a criminal offense. Furthermore, selling expired goods violates the Food Act No. 26 of 1980 and NMRA regulations. 

Phase 10B.4 (#926) introduces complete batch and expiry date tracking with per-batch MRP, automated First-Expiry-First-Out (FEFO) stock allocation, line splitting across batches, per-batch stock counts, and regulatory manager overrides, while maintaining strict financial, tax, and stock invariants.

---

## 2. Locked Decisions (D42–D53)

* **D42 (Scope & Nullability):** Controlled via `Features.BATCHES` and `Features.EXPIRY_DATES` flags and a per-product toggle `Product.tracks_batches: bool`. In `ProductBatch`, `batch_no` and `expiry_date` are independently nullable in the database, with service validation requiring at least one to be set (supporting expiry-only bakery goods, batch-only hardware/chemicals, and full pharmacy batches). Enforced at the DB level by a Check Constraint.
* **D43 (Synthetic Opening Batch):** Toggling `tracks_batches = True` on an existing product with `stock_qty != 0` automatically generates a synthetic opening batch (`batch_no="OPENING"`, `expiry_date=None`, `qty_on_hand=stock_qty`, `cost=product.cost`, `mrp=product.price`, `is_active=True`), ensuring mathematical balance without blocking operations even if the product currently has negative stock under `allow_negative_stock = True`.
* **D44 (Per-Batch Stock Count):** Stock Count (Stock Take) for tracked items counts per batch, recording variances against specific batches via `StockCountItem.batch_id` so $\sum \text{batch.qty\_on\_hand} == \text{Product.stock\_qty}$ is preserved without silent variance dumping.
* **D45 (FEFO Allocation & Concurrency):** Strict FEFO sort (`expiry_date ASC NULLS LAST`, `received_at ASC`, `id ASC`) locked via deterministic row locking in PostgreSQL (`sorted(batch_ids)` with `SELECT ... FOR UPDATE`). Lines automatically split across batches if needed to fulfill quantity. If negative stock is permitted by shop config (`allow_negative_stock = True`) and all batches are exhausted, the newest active batch absorbs the overdraft.
* **D46 (Cashier Interaction & Differing MRPs):** Silent FEFO when MRPs match. When active batches carry differing MRPs, a lightweight `BatchPicker` dialog appears (defaulting to FEFO, showing batch/expiry/MRP/qty). Lines with different MRPs or different batches appear as distinct cart lines. At payment commit, `process_sale` re-validates expiry dates against current system date.
* **D47 (Manager Override for Expired Stock):** Selling expired stock requires `sales.override_expired_batch` (granted to Admin/Manager). Encountering an expired batch displays `ManagerOverrideDialog` with regulatory warnings; manager approval writes an `AuditLog` row (`EXPIRED_BATCH_OVERRIDE`).
* **D48 (Traceable Returns & Voids):** Voids and refunds return stock strictly to the originating `SaleItem.batch_id` via `StockMovement(type="RETURN"|"VOID", batch_id=...)`. FK `RESTRICT` prevents deletion. Returns to inactive or zeroed batches automatically reactivate them (`is_active = True`).
* **D49 (Per-Batch MRP Pricing & Tax Truth):** If set, `batch.mrp` sets `original_price` and default `unit_price`. Discounts apply against MRP. Overriding prices above `batch.mrp` requires manager override. Phase 6 tax snapshots and `ROUND_HALF_UP` operate on line subtotals. Receipts and invoices print batch number and expiry.
* **D50 (GRN & Unit Conversion #937):** GRN captures batch details in base units (`base_qty = purchase_qty * factor`, `base_unit_cost = purchase_unit_cost / factor`). If identical `(product_id, batch_no, expiry_date, mrp)` lot exists, increments `qty_on_hand`; otherwise creates new batch. `PurchaseItem.batch_id` stores immutable batch reference.
* **D51 (Main-PC Authority & LAN Sync 1.7):** Batches are catalog entities created/edited exclusively on Main PC (`require_catalog_writable`) and synced down to tills via protocol 1.7. Deletions propagate via `sync_deletions` tombstones. Tills push sales with `batch_id`; offline till overdrafts are absorbed by Main PC as negative batch balances with a `BATCH_OVERDRAFT_SYNC_CONFLICT` audit log entry.
* **D52 (Dashboard Expiring List Actions):** Expiring view (30/60/90 days) provides "Write-off / Mark Expired" (Phase 4 `StockAdjustmentDialog` with reason `EXPIRED`) and "Discount / Clearance" (Price Board). "Return to Supplier" is shown but disabled with tooltip pending Phase 10B.5 (#930 Supplier Returns).
* **D53 (Alembic Migration & Recovery):** Clean Alembic migration: creates `product_batches` table with `version_id` optimistic locking and indexes on `(product_id, is_active, expiry_date, received_at)`, adds `tracks_batches` to `products`, and adds nullable `batch_id` FKs (with `ON DELETE RESTRICT`) to `sale_items`, `stock_movements`, `purchase_items`, `stock_count_items`, and `inventory_logs` using `batch_alter_table` for SQLite compatibility. Fully reversible downgrade.

---

## 3. Domain Invariants

1. **The Batch-Stock Invariant:**
   For every product with `tracks_batches = True`:
   $$\sum_{b \in \text{batches}(p)} b.\text{qty\_on\_hand} = p.\text{stock\_qty}$$
   Every stock mutation writes a `StockMovement` capturing both `product_id` and `batch_id`.
2. **Base-Unit Uniformity:**
   All quantities (`qty_on_hand`) and financial costs (`cost`) on `ProductBatch` are strictly denominated in the product's base inventory unit (`Product.unit_id`).
3. **Immutability of Historical Batch Facts:**
   Once a sale or GRN is committed, the `SaleItem.batch_id` and `PurchaseItem.batch_id` foreign keys are immutable. Deletion of referenced `ProductBatch` records is strictly prohibited by database constraint (`ON DELETE RESTRICT`).
4. **Reconciliation of Split Lines:**
   When a cashier sells a single logical line spanning $N$ batches, the system creates $N$ distinct `SaleItem` rows such that:
   $$\sum_{i=1}^N \text{item}_i.\text{qty} = \text{requested\_qty}$$
   $$\sum_{i=1}^N \text{item}_i.\text{subtotal} = \text{total\_charged}$$
5. **Fail-Closed Expiry Boundary:**
   An item is legally expired if $\text{expiry\_date} < \text{current\_date}$. At both scan-time and payment-time, allocating or selling an expired batch without verified manager authorization is strictly blocked.
6. **No Mixed Lot Merging in Cart or Receipt:**
   Cart lines and receipt lines for batch-tracked items must never be merged across different `batch_id`s, preserving per-batch pricing, expiry dates, and lot audit trails.
7. **Composite Item Prohibition:**
   Composite (bundle) parent products and child components of composite products cannot have `tracks_batches = True` enabled in Phase 10B.4 (fail-closed validation in `InventoryService`).

---

## 4. State Transitions & Lifecycle

### 4.1 ProductBatch Lifecycle State Machine

```
   [ GRN Inward / Opening Migration / Stock Adjustment ]
                            │
                            ▼
                     ┌──────────────┐
                     │    ACTIVE    │ (qty_on_hand > 0, expiry_date >= today or None)
                     └──────┬───────┘
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
  [ Sold Down / Adj ] [ Date Crosses ]   [ Manually Closed ]
         │                  │                  │
         ▼                  ▼                  ▼
  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
  │   DEPLETED   │   │   EXPIRED    │   │  DEACTIVATED │
  │(qty_on_hand=0│   │(today>expiry)│   │(is_active=F) │
  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
         │                  │                  │
         └─────────┬────────┴──────────────────┘
                   │
                   ▼ (Customer Refund / Sale Void / GRN Addition)
         ┌──────────────────┐
         │   REACTIVATED    │ ──► [ Transitions back to ACTIVE or EXPIRED ]
         │  (is_active = T) │
         └──────────────────┘
```

### 4.2 Decoupled Scan-Time vs Checkout FEFO Resolution Flow

To avoid criminal liability under CAA Section 29, explicit cashier lot selection is cleanly decoupled from silent FEFO checkout:

```
   [ Cashier Scans / Adds Product to Cart ]
                            │
            (product.tracks_batches is True)
                            │
                            ▼
   [ Query Active Unexpired Batches: qty_on_hand > 0, is_active=True, expiry_date >= today or None ]
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
      (All MRPs Identical)      (Differing Shelf MRPs)
               │                         │
               ▼                         ▼
   [ Add to Cart with          [ Open BatchPickerModal ]
     batch_id = None ]         [ Cashier picks physical box ]
               │                         │
               │                         ▼
               │               [ Add to Cart with
               │                 batch_id = selected_batch.id,
               │                 unit_price = selected_batch.mrp ]
               │                         │
               └────────────┬────────────┘
                            │
                            ▼
                 [ Checkout / Payment Commit ]
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
     (item.batch_id is Set)    (item.batch_id is None)
               │                         │
               ▼                         ▼
     [ Deterministic Lock      [ BatchService.allocate_fefo_stock:
       Single ProductBatch ]     Query & lock unexpired batches;
               │                 Split line across batches ]
               ▼                         │
     [ Verify Available Qty              ▼
       & Unexpired Date ]      [ Verify Expiry & Stock ]
               │                         │
               └────────────┬────────────┘
                            │
                            ▼
              (Any Allocated Batch Expired?)
               ├── No  ──► [ StockService.record_movement(batch_id=...) & Commit ]
               └── Yes ──► [ Raise ExpiredBatchError -> Prompt ManagerOverrideDialog ]
```

---

## 5. Schema, Migration & LAN Sync Design

### 5.1 SQLAlchemy Models (`cbpos/core/models/__init__.py`)

```python
class ProductBatch(Base):
    __tablename__ = "product_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False)
    batch_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    qty_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(10, 3), nullable=False, default=Decimal("0.000"), server_default="0.000"
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=sa.func.now(), index=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", index=True, nullable=False)
    version_id: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    last_modified: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, server_default=sa.func.now(), index=True, nullable=False
    )

    product: Mapped["Product"] = relationship("Product", back_populates="batches")

    __mapper_args__ = {"version_id_col": version_id}

    __table_args__ = (
        CheckConstraint("batch_no IS NOT NULL OR expiry_date IS NOT NULL", name="ck_product_batches_has_identity"),
        Index("ix_product_batches_fefo", "product_id", "is_active", "expiry_date", "received_at"),
    )
```

*(Note: `grn_line_id` is intentionally omitted from `ProductBatch` to prevent circular FK cycles with `purchase_items`; `PurchaseItem.batch_id` is the authoritative 1:N reference.)*

### 5.2 Existing Model Modifications

* `Product`:
  - `tracks_batches: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)`
  - `batches: Mapped[list["ProductBatch"]] = relationship("ProductBatch", back_populates="product")`
* `SaleItem`:
  - `batch_id: Mapped[int | None] = mapped_column(ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=True, index=True)`
  - `batch: Mapped[Optional["ProductBatch"]] = relationship("ProductBatch")`
* `StockMovement`:
  - `batch_id: Mapped[int | None] = mapped_column(ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=True, index=True)`
  - `batch: Mapped[Optional["ProductBatch"]] = relationship("ProductBatch")`
* `PurchaseItem`:
  - `batch_id: Mapped[int | None] = mapped_column(ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=True, index=True)`
  - `batch: Mapped[Optional["ProductBatch"]] = relationship("ProductBatch")`
* `StockCountItem`:
  - `batch_id: Mapped[int | None] = mapped_column(ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=True, index=True)`
  - `batch: Mapped[Optional["ProductBatch"]] = relationship("ProductBatch")`
* `InventoryLog`:
  - `batch_id: Mapped[int | None] = mapped_column(ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=True, index=True)`
  - `batch: Mapped[Optional["ProductBatch"]] = relationship("ProductBatch")`

### 5.3 Alembic Migration Plan

* **Revision File:** `alembic/versions/xxxx_add_batch_and_expiry_tracking.py`
* **Upgrade:**
  1. Create table `product_batches` with all columns, defaults, check constraint `ck_product_batches_has_identity`, and index `ix_product_batches_fefo`.
  2. `batch_alter_table("products")`: add column `tracks_batches` (Boolean, server_default="0", nullable=False).
  3. `batch_alter_table("sale_items")`: add column `batch_id` (Integer, ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=True).
  4. `batch_alter_table("stock_movements")`: add column `batch_id` (Integer, ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=True).
  5. `batch_alter_table("purchase_items")`: add column `batch_id` (Integer, ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=True).
  6. `batch_alter_table("stock_count_items")`: add column `batch_id` (Integer, ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=True).
  7. `batch_alter_table("inventory_logs")`: add column `batch_id` (Integer, ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=True).
* **Downgrade:** Drop added columns and drop `product_batches` table in reverse dependency order, using `batch_alter_table` for SQLite compatibility.

### 5.4 LAN Sync Protocol 1.7 Updates

1. **Protocol Version:** Bump `SYNC_PROTOCOL_VERSION = "1.7"` in `cbpos/core/services/sync_protocol.py`.
2. **Table Mappings:**
   - Add `"product_batches": ProductBatch` to `_TABLE_MODEL_MAP`.
   - Add `"product_batches"` to `CATALOG_TABLES` immediately *after* `"products"`.
   - Add `"product_batches"` to `CATALOG_DELETION_ORDER` immediately *before* `"products"`.
3. **Main PC Server Ingestion (`cbpos/core/services/sync_apply_service.py`):**
   - In `SyncApplyService._on_insert` for `stock_movements`:
     ```python
     if instance.batch_id is not None:
         batch = self._session.get(ProductBatch, instance.batch_id)
         if batch is not None:
             batch.qty_on_hand += instance.qty_change
             if batch.qty_on_hand < Decimal("0.000"):
                 # Log audit entry as mandated by D51
                 log = AuditLog(
                     user_id=instance.user_id,
                     action="BATCH_OVERDRAFT_SYNC_CONFLICT",
                     event_type="SYNC_CONFLICT",
                     terminal_id=self._terminal_id,
                     details=f"Till {self._terminal_id} overdrafted batch {batch.id} ({batch.batch_no}) by {abs(instance.qty_change)}. New balance: {batch.qty_on_hand}.",
                 )
                 self._session.add(log)
     ```
4. **Stock Pull:** `EP_PULL_STOCK` continues to return product stock, while active batches and their balances sync down through catalog pulls (`CATALOG_TABLES`).

---

## 6. Service Contracts & Transaction Design

### 6.1 Authoritative Stock Mutation Seam: `StockService.record_movement`

`StockService.record_movement` is the single authoritative seam for all inventory mutations:

```python
def record_movement(
    product_id: int,
    qty_change: Decimal,
    movement_type: str,
    user_id: int,
    document_id: int | None = None,
    session: Session | None = None,
    enforce_non_negative: bool = True,
    batch_id: int | None = None,
) -> StockMovement | None:
```

**Implementation Invariants in `StockService._execute_movement`:**
1. Mutate `Product.stock_qty += qty_change`.
2. If `batch_id` is supplied:
   - Retrieve `ProductBatch` in the session.
   - Mutate `batch.qty_on_hand += qty_change`.
   - If `qty_change > 0` and `not batch.is_active`: reactivate `batch.is_active = True`.
   - If `enforce_non_negative` and `batch.qty_on_hand < 0`: raise `ValueError(f"Insufficient stock for batch {batch.batch_no}")`.
3. Record `StockMovement(product_id=product_id, batch_id=batch_id, qty_change=qty_change, balance_after=product.stock_qty, ...)`.

### 6.2 `BatchService` (`cbpos/core/services/batch_service.py`)

* `get_batches_for_product(product_id: int, include_depleted: bool = False, session: Session = None) -> list[ProductBatch]`
* `get_active_differing_mrps(product_id: int, session: Session = None) -> list[Decimal]`: Returns sorted unique MRPs for unexpired active batches with stock.
* `allocate_fefo_stock(product_id: int, qty_required: Decimal, acting_user_id: int, session: Session, allow_negative: bool = False) -> list[tuple[int, Decimal, Decimal]]`:
  - Planning function: locks candidate batches deterministically, resolves quantity allocations, and returns `list[tuple[batch_id, allocated_qty, batch_mrp]]`.
  - Filters `expiry_date >= current_date or expiry_date is None` (never silently allocates expired batches).
  - Deterministic row locking: collects candidate IDs, sorts ascending (`sorted(batch_ids)`), and executes `select(ProductBatch).where(ProductBatch.id.in_(sorted_ids)).with_for_update()`.
  - If stock is exhausted and `allow_negative` is True: executes fallback lock on the newest active batch:
    `select(ProductBatch).where(ProductBatch.product_id == product_id, ProductBatch.is_active.is_(True)).order_by(ProductBatch.received_at.desc(), ProductBatch.id.desc()).limit(1).with_for_update()`.
* `create_synthetic_opening_batch(product: Product, session: Session) -> ProductBatch`:
  - Creates opening batch: `batch_no="OPENING", expiry_date=None, qty_on_hand=product.stock_qty, cost=product.cost, mrp=product.price, is_active=True`.
* `parse_mmyy_to_month_end(val: str) -> date`:
  - Parses `"MM/YY"` into a `date` representing the final day of the specified month.

### 6.3 `CartService` & `PricingService` Integration

* **`CartService.add_item`:**
  ```python
  def add_item(
      self,
      product: Product,
      qty: Decimal = Decimal("1"),
      serials: list[str] | None = None,
      covered_line_id: int | None = None,
      line_id: str | None = None,
      batch_id: int | None = None,
      batch_mrp: Decimal | None = None,
  ) -> dict[str, Any]:
  ```
  Matching line condition:
  ```python
  if (
      item["product"].id == product.id
      and item.get("covered_line_id") == covered_line_id
      and item.get("batch_id") == batch_id
  ):
  ```
* **`PricingService.calculate_price`:**
  - Accepts optional `batch_mrp: Decimal | None = None`.
  - If `batch_mrp` is provided, `original_price` is initialized to `batch_mrp`, and discounts/promotions reduce from this base MRP.

### 6.4 `TransactionService` Checkout & Line Splitting

In `TransactionService._execute_sale`:
1. For each cart line:
   - If `line.get("batch_id")` is set:
     - Lock specific batch: `select(ProductBatch).where(ProductBatch.id == batch_id).with_for_update()`.
     - Re-validate expiry: if `batch.expiry_date and batch.expiry_date < date.today()` and not `expired_batch_override_by`:
       raise `ExpiredBatchError(product_id=product.id, batch_id=batch.id, batch_no=batch.batch_no, expiry_date=batch.expiry_date)`.
     - Deduct stock: `StockService.record_movement(..., batch_id=batch.id)`.
     - Write single `SaleItem(batch_id=batch.id, original_price=batch.mrp or product.price, ...)`.
   - If `line.get("batch_id") is None` and `product.tracks_batches`:
     - Plan FEFO allocation: `plan = BatchService.allocate_fefo_stock(product.id, line["qty"], user_id, session, allow_negative)`.
     - For each `(batch_id, alloc_qty, mrp)` in plan:
       - Apportion fixed line discounts proportionally: `split_disc = round_money(line["discount_value"] * (alloc_qty / line["qty"]))`.
       - Deduct stock: `StockService.record_movement(..., batch_id=batch_id)`.
       - Write `SaleItem(batch_id=batch_id, qty=alloc_qty, original_price=mrp, ...)`.
2. Eagerly touch receipt relations in `_load_receipt_relations`:
   - `_ = item.batch` to prevent `DetachedInstanceError` on background receipt print threads.

### 6.5 `PurchaseService` GRN Inward Seams

In `PurchaseService.receive_goods`:
1. `GrnLine` and `ValidatedGrnLine` include `batch_no: str | None`, `expiry_date: date | None`, `mrp: Decimal | None`.
2. For tracked products, validate that at least one of `batch_no` or `expiry_date` is present.
3. Quantities and costs are converted to base units: `base_qty = purchase_qty * factor`, `base_unit_cost = purchase_unit_cost / factor`.
4. Query existing lot: `(product_id, batch_no, expiry_date, mrp)`. If found, increment `qty_on_hand`; if not found, create `ProductBatch`.
5. Set `PurchaseItem.batch_id = batch.id` and pass `batch_id` to `StockService.record_movement`.

### 6.6 Voids and Refunds Traceability

* In `RefundService.refund`:
  - Set `refund_item.batch_id = orig_item.batch_id`.
  - Pass `batch_id=orig_item.batch_id` to `TransactionService._move_stock(..., batch_id=orig_item.batch_id)`.
* In `TransactionService.void_sale`:
  - Pass `item.batch_id` to `_move_stock(..., batch_id=item.batch_id)`.

---

## 7. UI / UX Design & Workflow Integration

### 7.1 `BatchPickerModal` (`cbpos/ui/dialogs/batch_picker.py`)
* **Trigger:** Scanned product has `tracks_batches = True` AND shelf stock has differing MRPs.
* **Layout:**
  - Compact dialog (minimum 500×320px).
  - Product name and barcode header.
  - Interactive table:
    * Col 0: `Batch No` (left)
    * Col 1: `Expiry Date` (with visual tag if < 30 days)
    * Col 2: `MRP` (bold, right-aligned)
    * Col 3: `Available Qty` (right-aligned)
  - Quick search filter box at top (`QLineEdit`) for high-volume pharmacies.
  - Keyboard navigation: Up/Down arrow keys navigate rows, `Enter` selects and adds to cart, `Esc` dismisses.
  - Impeccable styling: themed according to dark/light mode palette, using `make_dialog_footer`.

### 7.2 `ManagerOverrideDialog` Integration (`cbpos/ui/dialogs/manager_override_dialog.py`)
* Enhanced with `warning_message: str | None = None`.
* Displays regulatory warning banner when attempting to sell an expired batch or price above MRP.
* Successful PIN authorization emits user details; caller logs `AuditLog(action="EXPIRED_BATCH_OVERRIDE")`.

### 7.3 `StockAdjustmentDialog` (`cbpos/ui/dialogs/stock_adjustment_dialog.py`)
* Added parameters: `batch_id: int | None = None`, `default_reason: str | None = None`.
* When adjusting a tracked product, displays a batch selection combo (`QComboBox`).
* Passes `batch_id` to `InventoryService.adjust_stock(..., batch_id=batch_id)` and down to `StockService.record_movement`.

### 7.4 `ProductEditor` (`cbpos/ui/dialogs/product_editor.py`)
* Adds checkbox `chk_tracks_batches: QCheckBox` under Inventory tab.
* Disabled for composite products and child components.
* On save: if `tracks_batches` transitions from `False` to `True` on a product with `stock_qty != 0`, `InventoryService` creates the synthetic opening batch.

### 7.5 Dashboard Expiring Tile & Dialog (`cbpos/ui/views/dashboard_view.py`)
* Background Worker: `_ExpiringBatchesWorker(QThread)` queries batch data off the UI thread per Rule 6.
* Displays "Expiring Soon" KPI card.
* Clicking opens `ExpiringBatchesDialog`:
  - Filter tabs: `< 30 Days` | `< 60 Days` | `< 90 Days` | `Expired`.
  - Actions:
    - "Write-off / Mark Expired": Opens `StockAdjustmentDialog(product, batch_id=batch.id, default_reason="EXPIRED")`.
    - "Discount / Clearance": Opens Price Board.
    - "Return to Supplier": Disabled button with tooltip pending #930.

### 7.6 Thermal Receipts & Invoices (`cbpos/core/services/sales_receipt_builder.py`)
* If `item.batch_id` is present and `Features.BATCHES` or `Features.EXPIRY_DATES` is enabled:
  - Prints sub-line: `   Batch: <batch_no>  Exp: <YYYY-MM-DD>`.
* `SalesReceiptBuilder._merge_items`: Grouping key includes `getattr(item, "batch_id", None)` to ensure distinct lots are never merged on receipts.

---

## 8. Test Matrix & Verification Strategy

### 8.1 Domain Unit Tests (`tests/domain/test_batch_expiry_service.py`)
1. `test_issue_926_tracks_batches_flag_and_nullability`: Check constraint and independent nullability of `batch_no` and `expiry_date`.
2. `test_issue_926_synthetic_opening_batch_creation`: Enabling `tracks_batches` creates opening batch matching `stock_qty` (including negative stock).
3. `test_issue_926_batch_stock_invariant`: Invariant $\sum b.\text{qty\_on\_hand} == p.\text{stock\_qty}$ holds across sales, voids, adjustments, and GRNs.
4. `test_issue_926_fefo_allocation_order_and_ties`: Strict sorting (`expiry_date ASC`, `received_at ASC`, `id ASC`).
5. `test_issue_926_silent_fefo_excludes_expired_stock`: Expired stock is never automatically allocated by silent FEFO.
6. `test_issue_926_sale_line_splitting_across_batches`: Selling 5 units across Batch A (3 units) and Batch B (4 units) creates two distinct `SaleItem` rows with exact split discount reconciliation.
7. `test_issue_926_negative_stock_absorbs_into_newest_batch_when_allowed`: Under `allow_negative_stock = True`, overdraft is absorbed by newest batch, preserving invariant.
8. `test_issue_926_expired_batch_override_and_audit`: Selling expired batch raises `ExpiredBatchError`; allows with manager override and writes `AuditLog`.
9. `test_issue_926_void_and_refund_returns_to_exact_batch`: Refund returns stock strictly to original `batch_id`; reactivates depleted batch.
10. `test_issue_926_grn_unit_conversion_integration`: GRN receiving in purchase units converts correctly to base quantities and costs on `ProductBatch`.
11. `test_issue_926_differing_mrp_pricing_and_caa_cap`: Per-batch MRP sets line price; overrides exceeding MRP trigger manager override.
12. `test_issue_926_stock_take_per_batch_reconciliation`: Counting specific batches adjusts individual batch quantities via `StockCountItem.batch_id`.
13. `test_issue_926_cart_service_different_batches_no_merge`: Adding two batches of the same product creates distinct cart items.
14. `test_issue_926_atomic_sale_rollback_on_batch_failure`: Failure-injection test proving zero partial state on batch error (Rule 4).

### 8.2 UI Integration Tests (`tests/ui/test_batch_ui.py`)
1. `test_issue_926_batch_picker_dialog_keyboard_selection`: Modal shows when MRPs differ; arrow navigation and Enter select batch.
2. `test_issue_926_grn_batch_expiry_inline_inputs`: MM/YY input formatting and validation on purchase view.
3. `test_issue_926_dashboard_expiring_batches_actions`: Expiring tile filter tabs, stock write-off routing, and disabled supplier return button.
4. `test_issue_926_stock_adjustment_dialog_with_batch`: Selecting batch adjusts specific batch stock.

### 8.3 Concurrency & Multi-Till Tests (`tests/integration/test_batch_concurrency.py`)
1. `test_issue_926_concurrent_till_fefo_row_locking`: Two concurrent PostgreSQL connections selling from the same batch serialize without double-selling or deadlocks.
2. `test_issue_926_offline_till_overdraft_sync_resolution`: Main PC ingests offline till sales, records negative batch balance, and logs `BATCH_OVERDRAFT_SYNC_CONFLICT`.
3. `test_issue_926_migration_upgrade_and_downgrade`: Alembic upgrade and downgrade roundtrip on SQLite and PostgreSQL.

---

## 9. Rollout, Rollback & Batch Plan

* **Proposed Batch:** Phase 10B.4 (`feat/p10b-b4-expiry-batches`).
* **Branching:** Created from fresh `origin/main` after Phase 10B.3 (#937) is merged.
* **Commit Strategy:** One Conventional Commit per logical layer:
  1. `feat(batches): add ProductBatch model and alembic migration (#926)`
  2. `feat(batches): implement BatchService and FEFO allocation engine (#926)`
  3. `feat(batches): integrate batch tracking into StockService and PurchaseService (#926)`
  4. `feat(batches): add CartService, PricingService, and Checkout batch support (#926)`
  5. `feat(batches): implement BatchPicker and ManagerOverride dialogs (#926)`
  6. `feat(batches): integrate per-batch stock takes and dashboard expiring tile (#926)`
  7. `feat(batches): update LAN Sync protocol to 1.7 with overdraft conflict logging (#926)`
* **Zero AI Attribution:** Strictly enforced (no `Co-Authored-By`, no "Generated with").
* **Rollback & Safety:**
  * Pre-upgrade database backup automatically created.
  * Fully reversible Alembic downgrade script tested on SQLite and PostgreSQL.
  * In the event of production rollback after live batch transactions are written, restore from pre-upgrade backup.
