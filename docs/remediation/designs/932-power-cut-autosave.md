# Design Document: Phase 10B.1 (#932) Power-Cut Autosave and Recovery

**Issue:** #932 — Power-cut safety: autosave the in-progress bill and restore it on restart  
**Phase:** 10B.1  
**Decision Reference:** D36 (`docs/remediation/DECISIONS.md`)  
**Status:** Approved for Implementation  

---

## 1. Problem & Context

Frequent power outages in Sri Lanka can cause abrupt machine shutdowns mid-transaction. Cashiers may have already scanned 10–20 items, entered custom prices, applied line discounts, or captured device serial numbers. When power is restored or the POS application restarts, re-scanning the entire cart is slow, frustrating for customers in queue, and error-prone.

The goal of Phase 10B.1 (#932) is to automatically persist the in-progress open bill in the background on every cart change, and gracefully offer to restore it upon application restart or cashier login, with zero disruption to regular sales workflows.

---

## 2. Requirements & Scope Boundaries

### In Scope
1. **Feature Flag (`power_cut_autosave`):**
   - Controlled via `Features.POWER_CUT_AUTOSAVE`.
   - Enabled by default across all 8 shop presets (Grocery, Pharmacy, Hardware, Clothing, Phone/Electronics, Bookshop, Bakery, and Other) per Decision D36.
   - Fresh unconfigured databases have all flags off by default.
   - Upgraded/existing shops: Safe compatibility data migration enables `power_cut_autosave` if feature flags already exist, without resetting or overwriting any merchant-customized flags.
   - Visible as a toggle in **Settings → Features** with full audit logging.
2. **Schema & Model:**
   - Extend `SuspendedTransaction` with `is_autosave: bool` (default False, `server_default=sa.false()`) and `terminal_id: str | None` (String(50), indexed).
   - Reversible Alembic migration compatible with SQLite WAL and PostgreSQL.
   - Partial unique index `uq_suspended_transactions_autosave_terminal` on `terminal_id WHERE is_autosave = 1` (Postgres: `is_autosave IS TRUE`) to enforce at the engine level that at most one autosave row exists per terminal.
   - Invariant: At most one autosave row exists per terminal at any given time.
3. **Core Service (`CartAutosaveService`):**
   - Clean, narrow interface: `save()`, `get_autosave_summary()`, `discard_autosave()`, `restore_autosave()`, `has_autosave()`.
   - Thread safety: `save()` and `invalidate_and_delete()` synchronized under a `threading.RLock` to eliminate TOCTOU races under abrupt power cuts.
   - Full fidelity: Reuses `SuspendedTransactionService` v2 JSON serialization format (preserving customer, products, quantities, prices, overrides, approved-by, line discounts, cart discounts, line notes, serial numbers, warranty plans, and covered line references).
   - Strict separation from manual held bills: `SuspendedTransactionService.get_held_bills()`, `get_held_bill_count()`, and `get_latest_suspended()` explicitly filter `is_autosave.is_(False)` so autosaved carts are never visible or counted in the manual held bills list.
4. **Debounced Background Saving:**
   - Single-shot `QTimer` with 1000 ms debounce interval attached to cart mutations in `SalesView`.
   - Snapshot captured on UI thread; database writes execute in a background thread via `WorkerThread` / generation counter token.
   - Monotonic generation counter ensures out-of-order background writes and stale callbacks are dropped immediately.
5. **Lifecycle Cleanup:**
   - Autosave row is cleared atomically or immediately upon sale completion (`TransactionService.process_sale`), manual bill hold (`hold_bill`), cart clear (`clear_cart`), user discard, or feature flag disable.
6. **Recovery Dialog & UX:**
   - After cashier login, if `feature_visible(Features.POWER_CUT_AUTOSAVE)` is True and an autosave row exists for `terminal_id`:
     Display `AutosaveRecoveryDialog`: *"You had an unfinished bill ({count} items, {total}). Continue or discard?"*
   - Keyboard accessible (Enter to Continue, Esc to leave without discarding).
   - Touch-friendly (minimum 44px tap targets).
   - Full dark and light theme QSS styling.
   - Complete trilingual translations in English, Sinhala, and Tamil.

### Out of Scope
- Multiple autosaves per terminal (only the latest cart snapshot is maintained).
- Auto-saving completed or suspended bills.
- Price board (#931) or other Phase 10B features.

---

## 3. Architecture & Data Flow

```
   [ Cashier Input / Scanner ]
               │
               ▼
   [ SalesView: Cart Mutation ]
               │
               ▼
   [ Monotonic Generation ++ ]
   [ Reset 1000ms QTimer ] ──(if cart empty: cancel timer & delete autosave)
               │ (timeout)
               ▼
   [ UI Thread: Cart Snapshot ]
               │
               ▼
   [ WorkerThread: Background DB Save ]
               │
               ▼
   [ Generation Token Check (generation == active_gen?) ]
         │ (yes)                      │ (no: stale/cleared)
         ▼                            ▼
   [ Upsert SuspendedTransaction ]    [ Drop write / Purge row ]
   (is_autosave=True, terminal_id)
```

### Recovery Flow
```
   [ Application Launch / Cashier Login ]
               │
               ▼
   [ Check feature_visible(Features.POWER_CUT_AUTOSAVE) ]
         │ (True)
         ▼
   [ Query CartAutosaveService.get_autosave_summary(terminal_id) ]
         │ (Found)
         ▼
   [ Show AutosaveRecoveryDialog ]
        ├── Continue ──► SuspendedTransactionService.recall_bill() ──► Cart Restored
        ├── Discard  ──► Confirm Discard ──► Delete Row
        └── Esc / Close ──► Leave row in DB (prompt again on next login)
```

---

## 4. Five Core Failure Proofs

### Proof 1: An old background save cannot recreate the autosave after sale/hold/clear
- **Failure Mode:** A slow background thread is writing a cart snapshot to SQLite while the cashier clicks "Clear Cart" or completes a sale. If the slow thread commits after the clear/sale, an obsolete autosave row reappears.
- **Proof of Prevention:**
  1. `SalesView` tracks `_autosave_generation: int`. Any cart clear, sale finalization, or bill hold increments `_autosave_generation += 1` and stops `_autosave_timer`.
  2. `CartAutosaveService` maintains `_lock = threading.RLock()` and `_active_generations: dict[str, int]`.
  3. When `invalidate_and_delete(terminal_id)` runs (on clear, hold, or sale), it acquires `_lock`, increments `_active_generations[terminal_id]`, and purges any existing autosave row.
  4. When `CartAutosaveService.save(...)` runs, it acquires `_lock` and checks `if generation < _active_generations.get(terminal_id, 0): return False` before opening the DB session or committing.
  5. Because `save()` and `invalidate_and_delete()` share `_lock`, a background save cannot check generation, pause, and then commit after a clear. Either the save commits before the clear (and the clear immediately deletes it), or the clear runs first, advancing the generation and causing the save to abort before touching the database.

### Proof 2: A completed sale cannot leave a restorable cart that could create a duplicate sale
- **Failure Mode:** A sale completes, but the autosave row remains in the database. When the cashier logs in or restarts, the bill is restored and could be sold a second time.
- **Proof of Prevention:**
  1. In `SalesView.process_payment()` and `SalesView.quick_pay()`: Stop `_autosave_timer` and advance `_autosave_generation += 1` *before* opening `PaymentDialog` or calling `TransactionService.process_sale`.
  2. In `TransactionService._execute_sale`: The database transaction that inserts the `Sale`, `SaleItem`, and payment records also calls `CartAutosaveService.delete_autosave_in_session(session, terminal_id)`.
  3. Inside `delete_autosave_in_session()`, `CartAutosaveService` advances `_active_generations[terminal_id]` under `_lock`, rejecting any pending or queued saves.
  4. Because the deletion is executed **inside the exact same DB transaction**, the autosave row is atomically deleted when the sale commits.
  5. If the sale transaction rolls back due to an error, the autosave row is NOT deleted (preserving the customer's cart).
  6. Additionally, `SalesView._finalize_sale` calls `CartAutosaveService.invalidate_and_delete(terminal_id)` and stops the timer, eliminating any in-flight saves.

### Proof 3: Terminals never restore each other's carts
- **Failure Mode:** In a multi-terminal network environment, Terminal 1 restarts and prompts to restore a cart that was actually in progress on Terminal 2.
- **Proof of Prevention:**
  1. `SuspendedTransaction.terminal_id` is populated using `ConfigService.get("terminal_id") or "TERM-01"`.
  2. All queries in `CartAutosaveService` (`get_autosave`, `save_autosave`, `discard_autosave`, `restore_autosave`) strictly require `terminal_id` and query with:
     ```python
     select(SuspendedTransaction).where(
         SuspendedTransaction.is_autosave.is_(True),
         SuspendedTransaction.terminal_id == terminal_id,
     )
     ```
  3. The compound index `ix_suspended_transactions_terminal_autosave` enforces isolation and fast lookups.

### Proof 4: Corrupt or obsolete payloads fail safely without blocking login
- **Failure Mode:** The POS computer lost power while writing JSON data or the disk suffered a partial write, or a product in the cart was deleted/deactivated while the machine was off. On restart, the JSON parser or product lookup crashes, blocking the cashier from logging in.
- **Proof of Prevention:**
  1. `CartAutosaveService.get_autosave_summary()` catches `json.JSONDecodeError`, `KeyError`, and `ValueError`. If parsing fails, it logs an error, automatically purges the corrupt row via `discard_autosave(terminal_id)`, and returns `None`.
  2. If the user chooses "Continue" in `AutosaveRecoveryDialog`, `SuspendedTransactionService.recall_bill()` handles inactive or missing products gracefully by appending user-facing notices (`orders.recall_item_missing`) and continuing to restore the remaining items.
  3. Price changes are detected via `PricingService.calculate_price()` and reported via `orders.recall_price_changed` without failing the recall.
  4. Cashier login and POS startup never block or raise unhandled exceptions.

### Proof 5: Disabling the feature leaves no autosave timer, query, or prompt
- **Failure Mode:** A shop disables the `power_cut_autosave` flag, but background timers continue firing or startup prompts appear.
- **Proof of Prevention:**
  1. `SalesView.update_cart_display()` checks `if not feature_visible(Features.POWER_CUT_AUTOSAVE): return` before starting the debounce timer.
  2. Startup recovery check checks `if not feature_visible(Features.POWER_CUT_AUTOSAVE): return` before executing any database queries or instantiating dialogs.
  3. When `FeatureFlags.set(Features.POWER_CUT_AUTOSAVE, False)` is called, it triggers `CartAutosaveService.delete_all_autosaves()`, purging any leftover autosave records.

---

## 5. UI/UX Specification

### Dialog Layout & Visual Design
- **Window Title:** `_t("autosave.recovery_title")` ("Unfinished Bill Found" / "අවසන් නොකළ බිල්පතක් හමු විය" / "முடிக்கப்படாத பில் கண்டுபிடிக்கப்பட்டது")
- **Prompt Banner:** Card container with icon and clear typography:
  - Header: `_t("autosave.recovery_header")` ("Recover previous cart?")
  - Details: `_t("autosave.recovery_body", count=item_count, total=formatted_total)` ("You had an unfinished bill with {count} items ({total}). Would you like to restore it?")
  - Timestamp notice: Saved time formatted with standard date/time helper.
- **Buttons (Dialog Footer):**
  - **Continue (`btn_continue`):** Primary accent button (`btn-primary`), default button (`setAutoDefault(True)`), triggered by `Enter` or `Return`.
  - **Discard (`btn_discard`):** Danger button (`btn-danger`), styled with red accent.
  - **Close / Dismiss:** Triggered by `Esc` or window close button; leaves the autosave in the DB for the next login.
- **Discard Confirmation:**
  - Clicking "Discard" displays a confirmation box: `_t("autosave.discard_confirm_title")`, `_t("autosave.discard_confirm_body")`.
  - Only upon explicit confirmation is the record deleted.

---

## 6. Verification & Test Plan

1. **Unit / Domain Tests (`tests/domain/test_cart_autosave_service.py`):**
   - Verify save/load/discard lifecycle.
   - Verify generation token drops stale writes.
   - Verify isolation between different `terminal_id`s.
   - Verify manual held bill queries (`get_held_bills`) never return autosave rows.
   - Verify corrupt JSON payload fails closed, logs warning, and purges row.
2. **Atomic Sale Test (`tests/domain/test_cart_autosave_sale_integration.py`):**
   - Verify sale completion atomically deletes autosave row.
   - Inject failure into sale transaction to verify rollback preserves autosave row.
3. **UI & Debounce Tests (`tests/ui/sales/test_cart_autosave_ui.py`):**
   - Cart mutation starts 1000ms timer; clearing cart stops timer.
   - Background worker saves cart snapshot.
   - Toggling feature flag OFF prevents timer start and startup dialog.
4. **Recovery Dialog Tests (`tests/ui/dialogs/test_autosave_recovery_dialog.py`):**
   - "Continue" recalls cart with fidelity.
   - "Discard" prompts confirmation and deletes row.
   - "Esc" leaves row intact.
   - Trilingual rendering (EN/SI/TA) and theme verification (Dark/Light).

