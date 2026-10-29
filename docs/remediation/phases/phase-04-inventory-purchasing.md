# Phase 4 — Inventory, Purchasing (GRN), CSV Import

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> This spec was verified against `origin/main` @ `4bcc837` on 2026-10-28. Re-verify every `file:line` before editing (§0.1 step 7).

## Phase brief

**Outcome (end state):**
- Every stock change goes through `StockService` and leaves a `StockMovement`: sales, returns, GRNs, stock takes, and a new reachable **Adjust stock** action. The product editor can no longer change stock or cost.
- A stock take sets stock to what's on the shelf, even while the shop keeps trading during the count.
- Saving a product never overwrites newer stock or cost. Concurrent edits are detected.
- Inventory pages and searches cover every product, at any catalog size.
- Reorder → PO works on real shops. CSV import maps columns correctly, reads USB files and Excel ANSI files, rejects bad numbers, and reports errors.
- GRNs keep the entered date, compute AVCO correctly even from negative stock, validate every cell, and leave nothing behind on failure.
- Supplier ledgers reconcile, and nested categories are manageable.

**Depends on:**
- Phase 1 (auth and permissions);
- Phase 3A's `round_money` helper (`cbpos/core/utils/money.py`). Create it if it isn't merged yet; it is a one-function module.

#869 (Phase 2.3) makes catalog services read-only on tills; keep that guard in any service you touch.

**Unblocks:** Phase 6 (COGS and profit read correct costs).

### Issues

| # | Title | Sev | Size | Batch | Gate |
|---|---|---|---|---|---|
| #794 | Stock adjustment unreachable; product-editor stock edits leave no movement | high | M | 4.1 | agent |
| #862 | Product editor overwrites stock/cost with stale values | high | M | 4.1 | agent |
| #861 | Stock take applies a stale delta | high | M | 4.1 | agent |
| #863 | Inventory shows/searches only the first 1,000 products | high | M | 4.1 | agent |
| #864 | Reorder → PO unusable on real databases | high | S | 4.2 | agent |
| #865 | CSV import maps columns by substring | high | M | 4.2 | agent |
| #900 | CSV import silently imports nothing (USB path, ANSI) | medium | S | 4.2 | agent |
| #901 | CSV import accepts negative prices/costs/stock | medium | S | 4.2 | agent |
| #919 | Failed GRN commit leaves an orphan DRAFT and burns a number | low | M | 4.3 | agent |
| #902 | GRN grid editable and unvalidated; total ignores edits | medium | M | 4.3 | agent |
| #895 | GRN date ignored | medium | S | 4.3 | agent |
| #899 | AVCO wrong when a GRN meets negative stock | medium | S | 4.3 | agent |
| #920 | Supplier payable adjustment clamps but ledger doesn't | low | S | 4.4 | agent |
| #921 | Nested categories disappear from the Category Manager | low | S | 4.4 | agent |

### Subsystem map

**Stock core** — `cbpos/core/services/stock_service.py`:
- `StockService.record_movement(product_id, qty_change, movement_type, user_id, document_id=None, session=None)` `:29-90`. It validates the type against `_VALID_MOVEMENT_TYPES`, checks negative stock, skips `is_service`, and updates `Product.stock_qty`.
- **This is the only function allowed to change `stock_qty`.**

**Inventory** — `cbpos/core/services/inventory_service.py`:
- `update_product` `:78-134` (`setattr` for every key in `data`; `session.get` loads fresh);
- `adjust_stock(self, product_id, qty_change, reason, user_id)` `:136-173` (writes InventoryLog plus AuditLog, **no StockMovement**);
- `get_all_products(limit=1000, offset=0)` `:192-198`;
- `count_active_products` `:200`, which has no caller.

**Product search** — `ProductService.search_products(query, mode="ALL", limit=50)` (`cbpos/core/services/product_service.py:29`) matches English, Sinhala and Tamil names and barcodes.

**UI:**
- `cbpos/ui/views/inventory_view.py`: `load_data` `~:217-231` (all products into memory), `filter_data` (client-side), and opening the editor `~:219,256`;
- `cbpos/ui/dialogs/product_editor.py`: stock input and payload `:600-640`, validation `:652`;
- `cbpos/ui/dialogs/stock_adjustment_dialog.py`, which is never opened and calls the service wrongly at `:104`.

**Stock take** — `cbpos/core/services/stock_count_service.py`:
- load snapshots `expected_qty=product.stock_qty` `:133,184`;
- `update_count` `:192-222`, `increment_count` `:224-270`, `finalize_count` `:300-353`;
- `approve_and_apply` `:355-400`, which calls `record_movement(qty_change=item.variance_qty)`.
- Model `StockCountItem` `models/__init__.py:765-777`.

**Reorder** — `stock_service.py:~164` (the reorder query); `cbpos/ui/views/reorder_view.py:174-178, 224`. It reads `product.suppliers` (M2M `product_suppliers`, only seeded), while the editor writes `Product.default_supplier_id`.

**Import** — `cbpos/core/services/import_service.py`:
- `_validate_file_path` `:22-31` (home-only);
- open and decode `:64-66`;
- header mapping `:70-82`;
- row parse `:109-136`;
- outer except `:144-146`.

UI: `cbpos/ui/dialogs/csv_import_dialog.py:179-194`.

**Purchasing** — `cbpos/core/services/purchase_service.py`:
- `create_purchase` `:30-60` (date = now at `:36-37`);
- `commit_purchase` `:96-148`, with AVCO at `:130-136`.

UI: `cbpos/ui/views/purchase_view.py`:
- date input `:322,333`;
- grid model `:367-370`;
- totals `:852-855`;
- `commit_grn` `:880-930` (draft committed before VAT parse, `:911-924`).

**Supplier payable** — `cbpos/core/services/supplier_payable_service.py:163-174` (clamp).

**Categories** — `cbpos/core/services/category_service.py:93-117`; `cbpos/ui/dialogs/category_manager.py:157-196`.

### Domain invariants

1. `Product.stock_qty == opening + Σ StockMovement.qty_change` for every non-service product. No code path writes `stock_qty` except `StockService.record_movement`.
2. AVCO after a receipt of `q @ c` onto stock `s` at cost `k`: if `s ≤ 0`, then `c`; else `(s·k + q·c)/(s+q)`, rounded with `round_money`.
3. A GRN is all-or-nothing: header, lines, stock, cost, payable and ledger commit together or not at all, and the document number is taken inside that transaction.
4. `supplier.current_payable == Σ SupplierLedgerEntry.amount` (ADR 0001 applies to supplier balances too).
5. A product save changes only the fields the user edited, and fails if the row changed since the editor loaded it.

### Batches

| Batch | Branch | Issues | Why grouped |
|---|---|---|---|
| 4.1 | `fix/p4-b1-stock-adjust-take-concurrency` | #794, #862, #861, #863 | All about the single source of truth for stock |
| 4.2 | `fix/p4-b2-reorder-csv` | #864, #865, #900, #901 | Reorder and import correctness |
| 4.3 | `fix/p4-b3-grn-integrity` | #919, #902, #895, #899 | One transactional GRN service, then the grid, the date and AVCO |
| 4.4 | `fix/p4-b4-supplier-category` | #920, #921 | Small and independent |

---

## Batch 4.1 — Stock adjustment, stock take, product concurrency

**Branch:** `fix/p4-b1-stock-adjust-take-concurrency` · **Order:** #794 (it creates the adjustment path), then #862 (which removes stock from the editor and depends on #794), then #861, then #863.

### #794 — Ad-hoc stock adjustment is unreachable and broken

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (full UI gate: new entry point)

**Problem.** There is no working way to correct stock for damage, expiry, theft or a found item. The adjustment dialog is never opened and would crash if it were. Owners therefore type a new number into the product editor, which leaves no record at all.

**Evidence and root cause.**
- `stock_adjustment_dialog.py:104` calls `InventoryService.adjust_stock(self.product.id, change, reason)` statically with 3 args, while the real method (`inventory_service.py:136`) is an instance method needing `user_id`.
- Nothing opens the dialog.
- `adjust_stock` (`:136-173`) writes no `StockMovement`.
- The product editor writes `stock_qty` directly (`product_editor.py:610,627`).

**Fix design.**
1. **Service.** Rewrite `InventoryService.adjust_stock(product_id, qty_change, reason_code, note, user_id) -> StockMovement`:
   - check `inventory.adjust_stock` permission at the service boundary (`check_permission`; add the code to `permissions.py`, the seeds and the Admin and Manager roles, if it doesn't exist; `graft grep "adjust" --in cbpos/core/constants/permissions.py`);
   - reject `qty_change == 0` and service products;
   - call `StockService.record_movement(..., movement_type="ADJUSTMENT", session=session)`, making sure "ADJUSTMENT" is in `_VALID_MOVEMENT_TYPES`;
   - keep the `InventoryLog` row (it holds the reason) and an `AuditLog` row `STOCK_ADJUSTMENT` with product, delta, reason and new qty;
   - do it all in one session.
   - Reason codes: `DAMAGED`, `EXPIRED`, `THEFT`, `FOUND`, `CORRECTION`, `OTHER` (note required for OTHER).
2. **Dialog.** Fix `StockAdjustmentDialog`:
   - two modes, **Add** and **Remove** (positive quantity entered, sign from the mode). That's easier for cashiers than signed numbers.
   - The quantity spinbox shows 3 decimals for weighted products and 0 otherwise.
   - Reason combo, plus a note.
   - Live preview: "Stock {current} → {new}".
   - It calls the service through an instance, the way the inventory view gets it (`self.inventory_service`).
3. **Entry points:**
   - Inventory view: an **Adjust stock** button and a context-menu item on the selected product (Ctrl+J if free);
   - the product editor's stock field links to it (#862).

**Tests.**
- `tests/domain/test_inventory_service.py::test_issue_794_adjust_stock_writes_movement_and_audit`: one `StockMovement(type=ADJUSTMENT, qty_change=-2)`, one AuditLog, and stock decreased.
- `test_issue_794_adjust_requires_permission`.
- `test_issue_794_adjust_rejects_zero_and_service`.
- pytest-qt `test_issue_794_dialog_calls_service_with_user` (extend the existing `tests/ui/test_adjustment_dialogs.py`).

**UI/UX spec.**

```
┌ Adjust stock — Anchor Milk 400g ──────────────────┐
│ In stock now: 24                                  │
│ (•) Remove  ( ) Add        Quantity: [  2  ]      │
│ Reason: [Damaged            ▾]                    │
│ Note:   [__________________________]              │
│ Stock will be: 22                                 │
│                          [Save adjustment] [Cancel]│
└───────────────────────────────────────────────────┘
```

Keys `stock_adjust.*`:
- `title` "Adjust stock — {name}"
- `in_stock` "In stock now: {qty}"
- `remove` "Remove"
- `add` "Add"
- `quantity` "Quantity"
- `reason` "Reason"
- `note` "Note"
- `will_be` "Stock will be: {qty}"
- `save` "Save adjustment"
- `reason_damaged` "Damaged"
- `reason_expired` "Expired"
- `reason_theft` "Lost or stolen"
- `reason_found` "Found / extra"
- `reason_correction` "Count correction"
- `reason_other` "Other (write a note)"
- `note_required` "Please write a note for 'Other'."
- `negative_blocked` "This would make stock below zero, which isn't allowed in Settings."

Mode defaults to Remove (more common). Focus starts on Quantity. Enter saves. Run the full §0.7 UI gate.

**Do NOT.**
- Do not write `stock_qty` outside `record_movement`.
- Do not keep the static call.
- Do not hide the adjustment behind the stock-take screen.

**Acceptance.**
- [ ] The dialog is wired into Inventory and calls the service correctly.
- [ ] Every adjustment creates a `StockMovement` (ADJUSTMENT) and an audit entry.
- [ ] Reasons are i18n keys in en/si/ta, and the service path is tested.

### #862 — Saving the product editor overwrites current stock and cost with stale values

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail

**Problem.** Fixing a typo in a product name can reset its stock and cost to what they were when the list was loaded an hour ago. Sales and GRNs since then are silently undone, and nobody is warned.

**Evidence and root cause.**
- `product_editor.py:610,626-627` always sends `cost` and `stock_qty`.
- `inventory_service.py:81,92-94` (`update_product`) loads a fresh row with `session.get` and `setattr`s every key, so `version_id` (the optimistic lock) never sees the stale state.
- `inventory_view.py:219,256` opens the editor from the list's cached Product object.

**Fix design.**
1. **Stock is not editable for existing products.** In the editor, the stock field is read-only for existing products and shows the current value, with an **Adjust…** link button that opens #794's dialog. For **new** products, the opening stock stays editable: `create_product` records it as an `OPENING` movement via `record_movement` (add "OPENING" to the valid types if missing; check what the import uses).
2. **Cost is not editable for existing products either** (AVCO owns it). Show it read-only with a tooltip. For new products, the initial cost stays editable.

   **Recommended exception:** a permitted manager can "Set cost manually" (permission `inventory.set_cost`), which writes an AuditLog `COST_OVERRIDE` with old and new values. → Implement it; owners do need to fix bad imported costs.
3. **Optimistic concurrency.**
   - The editor loads the product **fresh** when it opens (`InventoryService.get_product(id)`) and keeps `version_id`.
   - `update_product(product_id, data, expected_version)` compares `product.version_id != expected_version` and raises `StaleProductError` ("modified by another user"). Reuse the existing error class and message if one exists (`graft grep "modified by another" --in cbpos`).
   - The service drops `stock_qty` and `cost` from `data` for updates. It never sets them, even if passed.
4. **Changed fields only.** The editor sends only fields whose value differs from what it loaded. That reduces lost updates on other fields too.

**Tests.**
- `test_issue_862_stale_snapshot_does_not_overwrite_stock_cost`: load v1 (stock 50, cost 40); in another session sell 30 and GRN 20 @100 (cost 70); `update_product(name=...)` with v1 raises `StaleProductError`, and stock and cost are unchanged.
- `test_issue_862_update_ignores_stock_and_cost_keys`.
- `test_issue_862_new_product_opening_stock_writes_movement`.
- `test_issue_862_set_cost_requires_permission_and_audits`.

**UI/UX.**
- Stock field: read-only style, value plus an **Adjust…** button.
- Cost field: read-only, with a **Set cost…** button visible only with permission. The tooltip `product.cost_avco_tooltip` reads "Cost is worked out automatically from your purchases (average cost)."
- Stale error: `product.modified_elsewhere` "Someone else changed this product while you were editing. Close and open it again to see the latest details." The dialog stays open so they can copy their text.
- Run the §0.7 UI gate.

**Acceptance.**
- [ ] `update_product` with a stale snapshot leaves stock and cost unchanged and raises a stale error.
- [ ] The product editor reloads the product from the DB when it opens.

### #861 — Stock take applies a stale delta

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** systematic-debugging → tdd → ponytail

**Problem.** Load a stock count in the morning (expected 10), sell 3 during the day, then count the shelf at 7. Approving then applies −3 to the current 7, giving 4. Every sale during the counting window is deducted twice, and every GRN is added twice. A large stale delta can also make approval impossible ("Insufficient stock").

**Evidence and root cause.**
- `stock_count_service.py:133,184`: `expected_qty=product.stock_qty` at **load**.
- `:210, 262, 336`: `variance = counted − expected`.
- `:355-400` applies the variance to the **current** stock.

**Fix design (no schema change).**
- Snapshot `expected_qty` when the line is **first counted**:
  - in `update_count` and `increment_count`, if `item.counted_qty is None` (the first entry for this line), set `item.expected_qty = product.stock_qty` read in the same session, **before** applying the count;
  - recompute the variance as now.
- At approve, apply `counted − expected` to the current stock. The result is `counted + (all movements after the line was first counted)`, which is the shelf truth plus later trading. Sales and GRNs before counting are no longer double-counted.
- Approval must not fail because of trading after the count:
  - add `enforce_non_negative: bool = True` to `record_movement`;
  - stock-take application passes `False`, because it records physical reality. A negative result after approve means sales happened beyond the counted stock, which is a real discrepancy the variance report should show, not a blocker.
- Show both numbers on each line of the count screen: "System when counted: {expected}". Check the count view displays `expected_qty` (`graft grep "expected_qty" --in cbpos/ui`).
- Lines never counted keep their load-time `expected_qty` and no variance (unchanged behaviour).

**Tests.**
- `test_stock_count_service.py::test_issue_861_sale_during_count_not_double_counted`: load (10), sell 3, count 7, finalize, approve, stock is 7.
- `test_issue_861_grn_during_count_not_doubled`.
- `test_issue_861_sale_after_counting_kept`: load 10, count 10, sell 3, approve, stock is 7.
- `test_issue_861_approve_never_fails_insufficient_stock`.

**UI/UX.** The count screen line shows "System: {expected} (when counted)" in secondary text. If stock changed since the line was counted, show an info icon with the tooltip `stock_take.changed_since_count` "{n} sold or received after this was counted — CB POS will include them." Run the §0.7 UI gate.

**Acceptance.**
- [ ] Load, sell 3, count the shelf, finalize, approve: the final stock equals the shelf count.
- [ ] A GRN during counting isn't doubled.
- [ ] Approve never fails "Insufficient Stock" because of sales after the snapshot.

### #863 — Inventory shows and searches only the first 1,000 products

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (harden: loading and empty states)

**Problem.** A shop with 3,000 products can't see, find, edit or deactivate anything past roughly the letter M in Inventory. The owner thinks those products were never imported.

**Evidence and root cause.**
- `inventory_view.py:217-231` loads `get_all_products()` (default `limit=1000`, `inventory_service.py:192-198`), then pages and filters in memory.
- `count_active_products()` (`:200`) is unused.

**Fix design.**
- **Server-side paging and search.**
  - New service method: `InventoryService.list_products(query: str | None, filters: ProductFilter, page: int, page_size: int = 100) -> tuple[list[ProductRow], int]`, returning the rows and the total count.
  - Search uses the same matching as `ProductService.search_products`: English, Sinhala and Tamil names, plus barcode. Extract the WHERE-clause builder into a shared private function so both use one definition; don't copy-paste.
  - Filters keep whatever the view has today (category, active, low stock; check `filter_data`).
  - Sorting is by English name, then id (stable).
  - The query uses `LIMIT/OFFSET` with a separate `COUNT(*)` using the same WHERE clause.
- The view keeps its pager but asks the service for each page.
- Search runs on 300 ms debounce (`QTimer.singleShot`) in a worker if there's an existing pattern for DB work off the UI thread in views (`graft grep "QThread" --in cbpos/ui/views/inventory_view.py`). Otherwise synchronous is acceptable for paged queries of 100 rows; measure, and note it in the PR.
- Use `batch_table_update` when filling the table.

**Tests.**
- `test_issue_863_product_1400_reachable_by_page_and_search`: seed 1,500 products with a bulk insert in the test.
- `test_issue_863_search_matches_sinhala_name`.
- `test_issue_863_count_matches_filter`.

**UI/UX.**
- Pager text `inventory.page_info` "{first}–{last} of {total}".
- Empty search `inventory.no_match` "No products match \"{query}\". Check the spelling, or search by barcode."
- A loading state while fetching.
- Run the §0.7 UI gate with 3,000 products.

**Acceptance.**
- [ ] With 1,500 products, product #1,400 is reachable by paging and by search.

---

## Batch 4.2 — Reorder and CSV correctness

**Branch:** `fix/p4-b2-reorder-csv`

### #864 — Reorder → Purchase Order is unusable on real databases

**Severity:** high · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Root cause.**
- `stock_service.py:~164` and `reorder_view.py:174-178,224` read `product.suppliers` (M2M), which only `scripts/seed.py:~1402` fills.
- The product editor writes `default_supplier_id` (`product_editor.py:630`).

**Fix.**
- The reorder query eager-loads `Product.default_supplier`.
- The row supplier is `default_supplier or (suppliers[0] if suppliers else None)`.
- **Move the supplier choice into the service:** `StockService.get_reorder_rows()` returns rows with `supplier_id` and `supplier_name` already resolved. The view stops reading relationships.
- PO creation with mixed or missing suppliers: rather than refusing outright, offer **Create one PO per supplier**, and list "No supplier" rows separately with the hint below.

**Tests.**
- `test_issue_864_default_supplier_used_in_reorder`.
- `test_issue_864_po_created_for_default_supplier`.
- `test_issue_864_mixed_suppliers_split_into_pos`.

**UI/UX.**
- `reorder.no_supplier_hint` "Set a supplier on these products (Inventory → Edit product → Supplier) to order them."
- `reorder.split_confirm` "These items come from {count} suppliers. Create {count} purchase orders?"
- Run the §0.7 UI gate.

**Acceptance.**
- [ ] A product with only `default_supplier_id` appears in reorder with that supplier, and a PO can be created.

### #865 — CSV import maps columns by substring

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (clarify) for the preview

**Root cause.** `import_service.py:70-82`: `if "price" in lower_field` comes before the cost check, so later headers overwrite earlier ones. "Name (Sinhala)" overwrites the English name.

**Fix design.**
1. **Exact alias table**, normalised: lowercase, strip, collapse spaces, remove `_ - ( ) .`.
   - `barcode`: barcode, code, sku, item code, itemcode
   - `name_en`: name, name en, name english, product name, item name, description
   - `name_si`: name si, name sinhala, sinhala name, sinhala
   - `name_ta`: name ta, name tamil, tamil name, tamil
   - `price`: price, selling price, sell price, retail price, mrp, sale price
   - `cost`: cost, cost price, buying price, purchase price, unit cost
   - `stock_qty`: stock, qty, quantity, stock qty, on hand
   - `category`, `unit`, `reorder_point`: existing fields; check which the importer supports and give each an alias set.
2. A header that maps to a field already mapped raises `ImportMappingError("duplicate_column", field, header)`. An unknown header is ignored but reported.
3. A **preview step** in `csv_import_dialog.py` shows the mapping (CSV header → CB POS field) and the first 5 parsed rows before import. The user can change a mapping with a combo per column. The service accepts an explicit `mapping: dict[str, str]` from the dialog, and the auto-mapping is only the default.

**Tests.**
- `test_issue_865_selling_and_cost_price_map_correctly`.
- `test_issue_865_name_sinhala_does_not_replace_english`.
- `test_issue_865_duplicate_mapping_rejected`.
- `test_issue_865_explicit_mapping_honoured`.

**UI/UX spec.** The preview step:

```
Column in your file   →  CB POS field
Selling Price         →  [Selling price ▾]
Cost Price            →  [Cost         ▾]
Name (Sinhala)        →  [Name — Sinhala▾]
Old Code              →  [(ignore)     ▾]
[first 5 rows table]
                         [Import 1,240 products] [Back]
```

Keys:
- `import.map_title` "Check the columns"
- `import.ignore` "(ignore)"
- `import.duplicate_column` "Two columns are set to {field}. Choose one."
- `import.import_n` "Import {count} products"

Run the full §0.7 UI gate.

**Acceptance.**
- [ ] `Selling Price,Cost Price` map correctly.
- [ ] `Name (Sinhala)` doesn't replace name_en.

### #900 — CSV import silently imports nothing from USB or ANSI files

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.**
- `import_service.py:22-31` (`_validate_file_path`) allows only `Path.home()`.
- `:64-66` reads `utf-8-sig` only.
- `:144-146` swallows the error and returns `{0,0,0}`.

**Fix.**
- Accept any path the user picked: keep only `exists()`, `is_file()`, and the `.csv` suffix checks. A file picked in a `QFileDialog` is user intent, so the home-only rule protects nothing here.
- Decode: try `utf-8-sig`; on `UnicodeDecodeError` retry the **whole file** with `cp1252`. Read it fully first, then parse, so a bad byte never leaves a partial import.
- Do all row inserts in **one transaction**, so a failure rolls everything back. Per-row validation failures (#901) are counted, not raised.
- File-level errors raise `ImportError_(code)` (`file_unreadable`, `encoding`, `empty`, `no_header`), and the dialog's `_on_error` shows them.

**Tests.**
- `test_issue_900_cp1252_file_imports_all_rows`.
- `test_issue_900_path_outside_home_imports`.
- `test_issue_900_unreadable_file_raises_not_zero_success`.

**UI/UX.** `import.error_unreadable` "Couldn't read this file. Save it as CSV from Excel and try again." `import.error_empty` "The file has no rows." Run the §0.7 UI gate.

**Acceptance.**
- [ ] A cp1252 file imports every row.
- [ ] A path outside home imports.
- [ ] An unreadable file shows an error.

### #901 — CSV import accepts negative prices, costs and stock

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.** `import_service.py:109-136` doesn't validate values. The editor rejects price ≤ 0 (`product_editor.py:652`).

**Fix.**
- Put the validation rules in one place, `ProductValidator` in a new module `cbpos/core/utils/validators.py` (it doesn't exist yet, although CLAUDE.md mentions validators; first check `graft grep "def validate" --in cbpos/core/utils` for an existing home and use that if one fits): price > 0, cost ≥ 0, opening stock ≥ 0 (or any value if `allow_negative_stock`).
- The editor and the importer both use it, and the editor's inline check is replaced by the shared one.
- A failing row is counted as failed, with the reason and row number collected and shown in the import result ("Row 14: selling price must be more than 0").
- Opening stock from import is written as `OPENING` movements via `record_movement`. Check that import doesn't set `stock_qty` directly; if it does, fix that too (same root rule as #794).

**Tests.**
- `test_issue_901_negative_price_row_failed_not_created`.
- `test_issue_901_import_opening_stock_writes_movement`.

**Acceptance.**
- [ ] A row with a negative price is counted as failed and not created.

---

## Batch 4.3 — GRN transactional integrity

**Branch:** `fix/p4-b3-grn-integrity` · **Order:** #919 (the one-transaction service the others build on), then #902, #895 and #899.

### #919 — A failed GRN commit leaves an orphan DRAFT and burns a number

**Severity:** low · **Size:** M · **Gate:** agent · **Skills:** codebase-design (one deep service call) → tdd → ponytail

**Root cause.** `purchase_view.py:911-925` commits `create_purchase` (DRAFT with a number) **before** parsing the Input VAT. Later errors leave the draft behind, and the view orchestrates a multi-step transaction.

**Fix design.**
- One service call: `PurchaseService.receive_goods(GrnRequest) -> Purchase`.
- `GrnRequest` is a dataclass: `supplier_id`, `date_received: datetime`, `supplier_invoice_no`, `input_vat: Decimal`, `lines: list[GrnLine(product_id, qty, unit_cost)]`, `purchase_order_id: int | None`, `user_id`.
- All validation runs first, then one session does:
  1. number the document;
  2. insert header and lines;
  3. stock via `record_movement("PURCHASE")`;
  4. AVCO (#899);
  5. supplier payable and ledger;
  6. audit.
- Any exception rolls everything back, including the number, because it's taken inside the transaction.
- The view parses its inputs into `GrnRequest` and shows field errors **before** calling. It never calls `create_purchase` / `commit_purchase` separately again.
- Keep the old methods if other callers use them (`graft callers create_purchase`). Otherwise make them private.

**Tests.**
- `test_issue_919_invalid_vat_leaves_no_purchase`.
- `test_issue_919_failure_midway_rolls_back_all`: patch the ledger write to raise. No Purchase, no movements, stock and cost unchanged.

**Acceptance.**
- [ ] Invalid VAT, or any failure, leaves no new Purchase row and no partial effects.

### #902 — New GRN grid is editable and unvalidated; the total ignores edits

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** tdd (pytest-qt) → ponytail; impeccable (harden)

**Root cause.**
- `purchase_view.py:367-370`: `QStandardItemModel`, editable by default.
- `commit_grn` re-reads text from cells (`:886-891`).
- The total comes from `self.grn_items` (`:852-855`), which doesn't follow edits.
- The service doesn't check qty or cost.

**Fix.**
1. Columns ID (0), Name (1) and Line total (4) are non-editable: `item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)`.
2. Qty and Cost cells use a delegate with numeric validation: qty > 0 (3 decimals if weighted), cost ≥ 0 (2 decimals). Invalid input is refused in the editor.
3. `itemChanged` recalculates the line total and the footer total from the model, the single source.
4. Add a **Remove line** action (Delete key plus a button).
5. `GrnRequest` is built from the model. The service validates `qty > 0` and `unit_cost >= 0` (raising `ValueError("grn_invalid_line", row)`), so it is defended twice.

**Tests.**
- `test_issue_902_service_rejects_nonpositive_qty_negative_cost`.
- pytest-qt `test_issue_902_editing_cell_updates_total`.
- `test_issue_902_id_column_not_editable`.

**UI/UX.**
- Invalid-cell tooltip `grn.qty_positive` "Quantity must be more than 0." and `grn.cost_not_negative` "Cost can't be negative."
- A remove-line button with an icon.
- Run the §0.7 UI gate.

**Acceptance.**
- [ ] `receive_goods` raises on qty ≤ 0 or cost < 0.
- [ ] Editing a cell updates the total label.
- [ ] Identity columns are read-only.

### #895 — GRN "Date" field is ignored

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.** `purchase_view.py:322` creates `date_input`, but `commit_grn` never passes it. `purchase_service.py:36-37` stamps `datetime.now()`. The tax report filters on `Purchase.date` (`financial_reports.py:190-195`).

**Fix.**
- `GrnRequest.date_received = datetime.combine(self.date_input.date().toPyDate(), datetime.now().time())`.
- The service uses it for `Purchase.date`. A future date is rejected (`ValueError("grn_future_date")`). A date earlier than the earliest open accounting period is allowed: there's no period lock yet.
- Stock movements keep `timestamp = now` (when the goods physically arrived in the system). Only the document date follows the supplier invoice. Note this in a code comment.

**Test.** `test_issue_895_back_dated_grn_stores_date`.

**UI/UX.** The date field's max date is today. `grn.future_date` "The GRN date can't be in the future." Run the §0.7 UI gate.

**Acceptance.**
- [ ] A GRN saved with a past date stores that date.

### #899 — AVCO gives a wrong cost when a GRN meets negative stock

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.** `purchase_service.py:130-136`: `(old_qty·old_cost + new) / (old_qty+new_qty)` with a negative `old_qty`. When the total is 0, the cost isn't updated.

**Fix (invariant 2).**

```
if old_qty <= 0: new_cost = unit_cost
else: new_cost = round_money((old_qty*old_cost + q*unit_cost) / (old_qty + q))
```

Apply it per line in `receive_goods`. Several lines for the same product within one GRN are applied sequentially. Use `round_money`.

**Tests.**
- `test_issue_899_negative_stock_receipt_uses_unit_cost`: −5 @100 + 10 @120 → 120.00.
- `test_issue_899_receipt_to_exact_zero_updates_cost`: −10 + 10 @120 → 120.00.
- `test_issue_899_normal_weighted_average`.

**Acceptance.**
- [ ] −5 @100 + 10 @120 → 120.00, and −10 + 10 @120 → 120.00.

---

## Batch 4.4 — Supplier and category consistency

**Branch:** `fix/p4-b4-supplier-category`

### #920 — Supplier payable adjustment clamps the balance, but the ledger records the full amount

**Severity:** low · **Size:** S · **Gate:** agent

**Root cause.** `supplier_payable_service.py:163-174`: `current_payable += amount; if < 0: = 0`, while the ledger writes the full `amount`.

**Fix (matching #888's customer rule).** Remove the clamp. A negative payable means the supplier owes the shop (an over-credit), which is real and must stay visible. The ledger amount equals the change.

**Test.** `test_issue_920_adjustment_ledger_sum_equals_payable`: 3,720 − 5,000 gives −1,280 on both.

**UI/UX.** The supplier balance displays a negative value as `supplier.credit_balance` "Supplier owes you {amount}". Check the supplier views (`graft grep "current_payable" --in cbpos/ui`). Run the §0.7 UI gate.

**Acceptance.**
- [ ] After any adjustment, the ledger sum equals `current_payable`.

### #921 — Categories nested under a subcategory disappear

**Severity:** low · **Size:** S · **Gate:** agent

**Root cause.**
- `category_manager.py:157-168` (`_load_tree`) draws two levels only.
- `_populate_parent_combo` (`:182-196`) offers every category as a parent.
- The model docstring says "one level of nesting".

**Fix (decided: enforce the documented one-level model).**
- The parent combo offers **top-level categories only**.
- `CategoryService.create/update` rejects a parent that itself has a parent (`ValueError("category_too_deep")`).
- **Existing deeper categories** (created through the bug): a data migration re-parents any grandchild to its top-level ancestor, preserving products, and logs each change. That keeps them visible and manageable.

**Tests.**
- `test_issue_921_parent_must_be_top_level`.
- `test_issue_921_migration_reparents_grandchildren`.

**UI/UX.** The parent combo hint `category.parent_hint` "Categories can have one level of sub-categories." Run the §0.7 UI gate.

**Acceptance.**
- [ ] A grandchild can't be created, and existing ones are re-parented and visible.

---

## Phase exit gate
- [ ] All 14 issues merged and **verified closed** with closing comments (§0.10). Epic checklists updated.
- [ ] Invariant test `tests/domain/test_stock_invariants.py`:
  - run sales, refunds, an adjustment, a stock take during trading, a GRN onto negative stock, a CSV import with opening stock;
  - assert invariant 1 (`stock_qty == Σ movements`) for every product, and invariant 2 for the GRN.
- [ ] `graft grep "stock_qty ="` shows no assignments outside `StockService` (and the migration/seed). Paste the result in the PR.
- [ ] Migration (category re-parent) tested on a seeded copy.
- [ ] Full suite green once per batch, and `pre-commit` clean.
- [ ] UI gate screenshots: the Adjust stock dialog, the product editor read-only stock and cost, the stale-edit error, the inventory pager with 3,000 items, the CSV mapping preview, GRN grid validation, the reorder split confirm.
- [ ] PROGRESS.md updated.
