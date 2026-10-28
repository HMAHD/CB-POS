# Phase 3B — Cart and Checkout Behaviour, Operator Controls

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> This spec was verified against `origin/main` @ `4bcc837` on 2026-10-28. Re-verify every `file:line` before editing (§0.1 step 7).

## Phase brief

**Outcome (end state):**
- The cart is never left in a misleading state:
  - a failed sale undoes its loyalty redemption;
  - a walk-in cart never carries a loyalty discount;
  - unexpected errors are shown to the cashier, never swallowed;
  - held bills come back exactly as left.
- Operator controls work and are guarded:
  - the email receipt sends;
  - the manual drawer open works, needs permission and is audited;
  - the bill-level discount is reachable by keyboard and capped;
  - service items sell;
  - a scan can't change the cart behind an open dialog;
  - a quantity change can't push a discount over the cap.
- Every stored line reconciles: `unit_price × qty = subtotal` before line discount.

**Depends on:** Phase 1 (auth/override) and Phase 3A:
- `PaymentMethodKind` / `method_kind`, used by #793's drawer rule;
- `round_money` in `cbpos/core/utils/money.py`, used by #916;
- the payment normalisation in `_execute_sale`.

**Unblocks:** Phase 6 (#796's "Total Discounts" needs #813's stored bill discount), Phase 7 (receipts).

### Issues

| # | Title | Sev | Size | Batch | Gate |
|---|---|---|---|---|---|
| #892 | Unexpected checkout error fails silently | medium | S | 3B.1 | agent |
| #853 | Failed sale leaves loyalty redemption on the cart | high | S | 3B.1 | agent |
| #801 | Loyalty minimum-redeem setting ignored (key mismatch) | medium | S | 3B.1 | agent |
| #913 | Loyalty clamps balance at 0 but writes unclamped ledger | low | S | 3B.1 | agent (decided below by ADR 0001) |
| #804 | Recalled held bills lose discounts, overrides, notes | medium | M | 3B.1 | agent |
| #855 | Service products blocked by stock check | high | S | 3B.2 | agent |
| #916 | Promotion leaves unrounded unit price | low | S | 3B.2 | agent |
| #891 | FIXED line discount survives qty reduction, exceeds cap | medium | S | 3B.2 | agent |
| #890 | Scan while a modal is open changes the cart behind it | medium | S | 3B.2 | agent |
| #793 | Manual drawer open does nothing; not permission-gated | high | M | 3B.2 | agent |
| #792 | "Email receipt" crashes (method doesn't exist) | high | M | 3B.2 | agent |
| #813 | Bill-level discount not exposed in the sales screen | medium | M | 3B.2 | agent |

### Subsystem map

**Cart** — `cbpos/core/services/cart_service.py`, in memory, one per SalesView:
- `items`, `clear()` `:96-102`;
- `update_quantity` `~:113-121`;
- line discount `apply_line_discount` `~:78-90`;
- `_recalculate_line` `~:218-222`;
- `_validate_discount_cap`;
- cart discount `set_cart_discount` (or equivalent) `:132-137`;
- `set_loyalty_redemption` `~:337-341`;
- `get_totals()` (tax after discount at `:325-333,366-369`).

**Sale writing** — `TransactionService.process_sale` (`transaction_service.py:73-110`, with a catch-all returning None at `:104-109`), `_check_stock` `:146-172`, and `_execute_sale` `:432-510` (step 0 mutates the live cart's redemption at `:449-456`).

**Pricing** — `cbpos/core/services/pricing_service.py`: `calculate_price` `~:110-170` (promotion at `:123-125`, price list at `:165`).

**Loyalty** — `cbpos/core/services/loyalty_service.py`:
- `validate_redemption` around `:113` (reads the wrong key);
- `reverse_sale_points` `:201-273` (clamp `:248-266`);
- `record_redemption` `~:280-305` (clamp `:290-302`).
- The redemption UI is in `payment_dialog.py:558,576`.

**Held bills** — `cbpos/core/services/suspended_transaction_service.py`: `hold_bill` `:19-48` (serialises `{barcode, qty}` at `:34`), `recall_bill` `:61-99`.

**UI:**
- `cbpos/ui/views/sales_view.py`: `process_payment` `~:1040-1070`, `open_cash_drawer` `:1584-1590`, `quick_pay` `~:1620-1650`, `process_barcode_external` `~:718`.
- `cbpos/ui/dialogs/receipt_options_dialog.py:246` (email).
- `cbpos/ui/main_window.py:197-202` (`on_barcode_scanned`).

**Hardware:**
- `cbpos/infrastructure/hardware/scanner.py:50-75`: the `ShortcutOverride` branch checks `activeModalWidget()` at `:57`; the `KeyPress` branch emits at `:70` without that check.
- `cbpos/infrastructure/hardware/escpos_driver.py:460-470`: `_drawer_wanted`, which matches the literal `"CASH"`.
- `PrintWorker.instance().add_job(...)`.

**Email** — `cbpos/core/services/email_service.py`: `deliver_email` `:22`, `send_email` `:102`, `send_email_with_pdf` `:127`. Find the A4 PDF generator: `graft grep "def generate_pdf" --in cbpos/core/services`.

**Permissions** — `cbpos/core/constants/permissions.py` (`cash.open_drawer` exists; confirm with `graft grep "open_drawer" --in cbpos/core/constants`).

### Domain invariants

1. The in-memory cart changes only by cashier actions or a **committed** sale. A failed `process_sale` leaves the cart exactly as it was before the call.
2. No cart without a customer has loyalty redemption.
3. Every line discount is ≤ `max_discount_percent` of the line's current gross, unless an override was approved for that exact line state.
4. `round_money(unit_price) × qty`, rounded, equals `subtotal` when there is no line discount.
5. Every cash-drawer open is either the result of a cash payment or a permitted, audited manual "no-sale" open.
6. Loyalty: `customer.loyalty_points == opening + Σ ledger points` (ADR 0001).

### Batches

| Batch | Branch | Issues (in order) | Why grouped |
|---|---|---|---|
| 3B.1 | `fix/p3b-b1-cart-failure-integrity` | #892, #853, #801, #913, #804 | Cart state and loyalty correctness across failures and holds |
| 3B.2 | `fix/p3b-b2-pos-rules-operator-controls` | #855, #916, #891, #890, #793, #792, #813 | Rules and controls on the selling screen |

---

## Batch 3B.1 — Cart and checkout failure integrity

**Branch:** `fix/p3b-b1-cart-failure-integrity`

### #892 — An unexpected checkout error fails silently

**Severity:** medium · **Size:** S · **Gate:** agent · **Skills:** systematic-debugging → tdd → ponytail; impeccable (harden)

**Problem.** A database lock, connection drop or numbering failure during checkout closes the payment dialog with no message. The cart stays, and the cashier may hand over the goods thinking the sale went through. There is no sale record and no stock change.

**Evidence and root cause.**
- `transaction_service.py:104-109`: `except Exception as e: logger.error(...); return None`.
- `sales_view.py:~1058-1064` and `~:1644-1646` do `if sale:` with no `else`. Their own `except Exception` branch, with `sales.transaction_failed`, can never run.

**Fix.**
- Remove the catch-all in `process_sale`. Keep `ValueError` (business rules) as is. Let every other exception propagate, after `logger.exception(...)`, so the stack trace reaches the log.
- In both UI call sites:
  - `except ValueError as e` → `translate_error(str(e))`;
  - `except OperationalError` → `errors.db_connection_lost` (from Phase 2 #904; add it now if not merged yet);
  - `except Exception` → `sales.transaction_failed`.
- **Also** add an explicit `else` / `if sale is None` guard that shows `sales.transaction_failed`, as a belt-and-braces check.
- The payment dialog must stay **open** on failure, so the cashier can retry or cancel and nothing is lost. Check the flow: if the dialog already closed before `process_sale`, reopen with the same payments, or restructure so `process_sale` runs before the dialog accepts. Recommended: the dialog emits `finish_requested(payment_data)`, and the view processes the sale and calls `dialog.accept()` only on success. Use whichever fits the existing structure with the fewest changes. The requirement is that **the cashier sees the error and the cart and payments are not lost**.

**Tests.**
- `test_transaction_service.py::test_issue_892_operational_error_propagates`: patch `_execute_sale` to raise `OperationalError`, and `pytest.raises(OperationalError)`.
- pytest-qt `test_sales_view_shows_error_when_process_sale_raises`: patch `process_sale`, then assert a `QMessageBox` was shown. Monkeypatch `QMessageBox.critical` to record calls, as other UI tests do (`graft grep "monkeypatch.setattr(QMessageBox" --in tests`).

**UI/UX.**
- `sales.transaction_failed` exists; check its wording. It should say: "The sale was NOT saved. Don't hand over the goods. {reason} Try again, or hold the bill (F6)."
- If the existing key differs, update the English (and si/ta) to that meaning.
- Run the §0.7 UI gate.

**Acceptance.**
- [ ] A forced `OperationalError` inside `_execute_sale` shows an error dialog in the Sales view, and the cart and payments are kept.

### #853 — A failed sale leaves the loyalty redemption on the cart

**Severity:** high · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Problem.** If a sale with a loyalty redemption fails (stock, credit limit, numbering), the Rs discount stays on the cart. The next walk-in sale gets it free, and nobody's points are deducted.

**Evidence and root cause.**
- `_execute_sale` step 0 (`transaction_service.py:449-456`) calls `cart_service.set_loyalty_redemption(points)` on the **caller's live cart** before the DB work.
- A DB rollback doesn't undo in-memory state, and only `clear()` resets it (`cart_service.py:96-102`).
- `get_totals()` applies the redemption even with no customer.

**Fix.**
1. `_execute_sale` must not mutate the caller's cart. Compute the redemption's effect on a local totals value: call `get_totals(redemption_override=points)` if you add such a parameter, or take a copy of the cart (`copy.copy` plus a deep copy of `items`, if cheap). **Recommended:** add `get_totals(self, loyalty_points=None)`, where `None` means use the cart's own value. `_execute_sale` passes the points explicitly and never calls `set_loyalty_redemption`.
2. The UI sets the cart's redemption only after a successful sale, or not at all. Check whether anything reads `cart.loyalty_points_redeemed` after the sale (receipt?). If yes, pass the value from the sale object instead.
3. `get_totals()` ignores redemption when `self.get_customer()` is None, and `set_customer(None)` resets `loyalty_points_redeemed = 0`.

**Tests.**
- `test_issue_853_failed_sale_leaves_no_redemption_on_cart`: force a stock failure, then `cart.loyalty_points_redeemed == 0`.
- `test_issue_853_walk_in_cart_has_no_loyalty_discount`.

**Acceptance.**
- [ ] After a failed `process_sale`, `cart.loyalty_points_redeemed == 0`.
- [ ] A walk-in cart never shows a loyalty discount.

### #801 — The loyalty minimum-redeem setting is ignored

**Severity:** medium · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Root cause.**
- Settings saves `loyalty_min_redeem_points` (`settings_pages/sales_tax.py:372`; default `config_service.py:115`).
- The readers use `loyalty_minimum_redeem`: `loyalty_service.py:113`, `payment_dialog.py:558,576`.

**Fix.**
1. Replace the three readers with `ConfigService.get("loyalty_min_redeem_points")`.
2. In `ConfigService.load()`, migrate legacy keys: if `loyalty_minimum_redeem` or `min_redeem_points` exists and `loyalty_min_redeem_points` doesn't, copy it over, delete the legacy key, and mark changed. That covers `sales_tax.py:347`'s `min_redeem_points` fallback too; then remove that fallback.
3. The payment dialog should read the minimum through `LoyaltyService` (e.g. `LoyaltyService.min_redeem_points()`), not `ConfigService` directly, so one place owns the rule.

**Tests.**
- `test_issue_801_min_redeem_enforced`: min 100, then `validate_redemption(50)` raises.
- `test_issue_801_legacy_key_migrated`.

**UI/UX.** The payment dialog shows the minimum when points are below it. That key probably exists; check `payment_dialog.py:576` context. Run the §0.7 UI gate.

**Acceptance.**
- [ ] All readers use `loyalty_min_redeem_points`, and legacy keys are migrated.
- [ ] With min = 100, redeeming 50 is rejected.

### #913 — Loyalty clamps the balance at 0 but writes the unclamped ledger row

**Severity:** low · **Size:** S · **Gate:** agent. The decision follows ADR 0001 ("points move only by ledger events") and the credit book's precedent (#715: balances may go negative).
**Skills:** tdd → ponytail

**Root cause.**
- `loyalty_service.py:248-266` (`reverse_sale_points`): `customer.loyalty_points = 0` while writing `points=-N`.
- `:290-302` (`record_redemption`) does the same.

**Fix (decided).** **Write the ledger row equal to the actual change, and don't let points go negative.**
- Points are a reward, not a debt. A negative points balance can't be "collected", and showing customers negative points is confusing.
- So `removed = min(N, current)`, `customer.loyalty_points -= removed`, and the ledger row is `points=-removed`, with `note` / `details` recording `"requested {N}, removed {removed}; {N-removed} already spent"`.
- `record_redemption` already validates against the balance, so its clamp should never trigger. Make it raise `ValueError("insufficient_points")` instead of clamping.
- Add one line to `docs/adr/0001-points-and-balances-move-by-ledger-events.md`: "Points never go below zero; a reversal that would go below zero removes only what is left, and the ledger records the amount actually removed."

**Tests.**
- `test_issue_913_reversal_below_zero_ledger_matches_balance`: opening 500, earn 10 on A, spend 510 on B, refund A. Balance 0, and `opening + Σ ledger == 0`.
- `test_issue_913_redemption_over_balance_raises`.

**Acceptance.**
- [ ] The loyalty ledger sum plus the opening balance equals `customer.loyalty_points` after a reversal that would go below zero.

### #804 — Recalled held bills lose line discounts, price overrides and notes

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (clarify) for the price-changed notice

**Problem.** Holding a bill (F6) stores only barcodes and quantities. Recalling it (F7) rebuilds the cart at today's prices, dropping:
- manager-approved price overrides;
- line discounts;
- notes;
- the bill discount.

The customer then pays a different amount than agreed.

**Evidence and root cause.**
- `suspended_transaction_service.py:34`: `items_data.append({"barcode": ..., "qty": ...})`.
- Recall `:76-92` re-adds via `ProductService.get_by_barcode` at current pricing.

**Fix design.**
- Serialise format **v2**: `{"v": 2, "cart": {...}, "lines": [...]}`.
  - `cart`: `discount_type`, `discount_value`. Leave the loyalty redemption out (#853: it isn't kept on hold).
  - `lines`: `product_id`, `barcode` (for fallback), `qty`, `unit_price`, `original_price`, `is_manual_price`, `override_approved_by` (user id if the cart tracks it; check the cart's line dict keys with `graft grep "is_manual_price" --in cbpos/core/services/cart_service.py`), `discount_type`, `discount_value`, `notes`.
  - Decimals are serialised as strings.
- Recall:
  - `v` missing: legacy path (unchanged behaviour).
  - `v == 2`: re-add each line by `product_id` (fall back to barcode), then restore its fields **through CartService methods** (not by poking dicts) so validation runs. Overrides restore without a new prompt, because they were approved already (keep `override_approved_by`).
  - If the product's current price differs from the held `original_price`, keep the held `unit_price` and collect a notice.
  - If a product was deleted or deactivated, skip it and collect a notice.
- Return a `RecallResult(ok: bool, notices: list[str])` instead of `bool` (update the two callers, `sales_view.recall_bill` and the order-bar tabs; `graft callers recall_bill`).

**Tests.**
- `test_issue_804_round_trip_keeps_discount_override_notes_cart_discount`.
- `test_issue_804_price_changed_since_hold_keeps_held_price_with_notice`.
- `test_issue_804_legacy_rows_still_recall`.

**UI/UX.**
- After recall, if there are notices, show one non-blocking info message:
  - `orders.recall_notices_title` "Bill recalled with changes";
  - one bullet per notice: `orders.recall_price_changed` "{name}: price is now {new}; the held price {old} was kept." and `orders.recall_item_missing` "{name} is no longer available and was left out."
- Run the §0.7 UI gate.

**Do NOT.** Do not re-run the discount cap against a manager-approved held override (it was approved). Do not store the loyalty redemption.

**Acceptance.**
- [ ] A held bill round-trips line discounts, overrides (with approver), notes and the cart discount.
- [ ] A price change since the hold keeps the held price and shows a notice.
- [ ] Existing held rows still recall.

---

## Batch 3B.2 — POS rules and operator controls

**Branch:** `fix/p3b-b2-pos-rules-operator-controls`

### #855 — Service products can't be sold under "no negative stock"

**Severity:** high · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Root cause.** `transaction_service.py:146-172` (`_check_stock`) compares `stock_qty < qty` and ignores `is_service`, for the product and for composite components. `StockService.record_movement` already skips services (`stock_service.py:~86`).

**Fix.** Skip `is_service` products and service components in `_check_stock`. Check `CartService` too, in case it pre-checks stock when adding (`graft grep "Insufficient stock"`), and apply the same skip.

**Test.** `test_issue_855_service_item_sells_with_zero_stock`: `allow_negative_stock=False`, a service with stock 0 sells, and its stock stays 0 with no movement row.

**Acceptance.**
- [ ] A service product with stock 0 sells under the default setting, and its stock stays 0.

### #916 — A percentage promotion leaves an unrounded unit price

**Severity:** low · **Size:** S · **Gate:** agent

**Root cause.** `pricing_service.py:123-125, 165`: `final_price` is not quantized. `transaction_service.py:~400-406` stores the 2-dp column, so `unit × qty ≠ subtotal`.

**Fix.** Return `round_money(final_price)` (Phase 3A's helper, ROUND_HALF_UP) on every path of `calculate_price`. Line subtotals are then computed from the rounded unit price.

**Tests.**
- `test_issue_916_calculate_price_two_dp`.
- `test_issue_916_saved_line_reconciles`: for a 15% promo on 99.99 × 10, stored `unit_price*qty == subtotal`.

**Acceptance.**
- [ ] `calculate_price` always returns a 2-dp price, and saved lines reconcile.

### #891 — A FIXED line discount survives a quantity reduction and exceeds the cap

**Severity:** medium · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (clarify)

**Root cause.**
- `cart_service.py:~113-121` (`update_quantity`) recalculates with the stale FIXED amount.
- `_recalculate_line` (`:218-222`) caps at gross, so the line can become free.
- The cap check runs only in `apply_line_discount` (`:78-90`).

**Fix (decided).** After a quantity change on a FIXED discount, **scale the discount proportionally** (`new = old × new_qty / old_qty`, rounded with `round_money`). That keeps the same percentage the cashier or manager approved, so the cap holds automatically.
- On quantity **increase** this scales up too, which is correct for a per-unit deal.
- Then re-run `_validate_discount_cap` as a safety net. If it still fails (e.g. a manager-approved over-cap discount), drop the discount and return a notice.
- PERCENT discounts need nothing.
- Treat quantity reduction itself as a permission and audit event: that is #893 (Phase 5). Leave a TODO referencing #893.

**Tests.**
- `test_issue_891_fixed_discount_scales_with_qty`: 10 × 10 with FIXED 15, qty → 1, discount 1.50 (15%).
- `test_issue_891_cap_never_exceeded_after_qty_change`.

**UI/UX.** If the discount is dropped, a status-bar notice `cart.discount_removed_qty` → "Discount on {name} was removed because the quantity changed. Apply it again if needed." Run the §0.7 UI gate.

**Acceptance.**
- [ ] Reducing quantity never leaves a line discount above `max_discount_percent`.

### #890 — A scan while a modal dialog is open changes the cart behind it

**Severity:** medium · **Size:** S · **Gate:** agent · **Skills:** tdd (pytest-qt) → ponytail

**Root cause.**
- `scanner.py:~64-71`: the `KeyPress` branch emits `barcode_scanned` with no `activeModalWidget()` check. The `ShortcutOverride` branch at `:57` has one.
- `main_window.py:197-202` routes the scan to `SalesView.process_barcode_external` (`sales_view.py:~718`).

**Fix.**
- In the `KeyPress` branch, only treat Enter as a scan when `QApplication.activeModalWidget() is None`. Otherwise reset the buffer and let the key go to the dialog.
- Also guard in `MainWindow.on_barcode_scanned`: `if QApplication.activeModalWidget() is not None: return` (defence in depth).
- Exception: dialogs that **want** scans (e.g. a product-search or customer dialog that accepts a barcode) receive the scan as normal typing into their focused line edit. That's what happens when the filter doesn't swallow it. Check the existing tests for dialogs relying on `barcode_scanned` while modal (`graft grep "barcode_scanned" --in cbpos/ui/dialogs`). If any exist, keep them working by routing to the active modal when it exposes `accepts_scans = True`.

**Test.** `tests/unit/test_barcode_scanner.py::test_issue_890_scan_with_modal_open_not_emitted`: with a modal `QDialog` open and a focused `QPushButton`, simulate a burst plus Enter (copy the burst helper in that file). Nothing is emitted.

**Acceptance.**
- [ ] With a modal open, a scan burst plus Enter emits nothing and reaches the dialog as a normal Enter.

### #793 — F8 / Ctrl+D "Open cash drawer" does nothing, and isn't permission-gated

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (harden)

**Problem.**
- With the default "kick drawer for cash only" setting, the manual Open Drawer shortcut silently does nothing.
- Anyone can open the drawer without permission or a record.

**Evidence and root cause.**
- `sales_view.py:1584-1590`: `PrintWorker.instance().add_job("kick_drawer")` with no data.
- `escpos_driver.py:460-470` (`_drawer_wanted`) returns False when `drawer_on_cash_only` is on (default, `config_service.py:65`) and the data is empty. It also matches the literal `"CASH"` name, the same identity bug as Phase 3A.

**Fix design.**
1. The job payload becomes a dict: `{"manual": bool, "method_kinds": [..]}`. `_drawer_wanted(data)`:
   - `manual=True` → True;
   - otherwise, with `drawer_on_cash_only` on → `"CASH" in method_kinds`;
   - accept the legacy list-of-names payload, and map names via `PaymentService.classify_method_name` (from 3A).
   - Update the automatic caller after payment to send `method_kinds` (`graft grep "kick_drawer"`).
2. Manual open:
   - `SalesView.open_cash_drawer` calls `check_permission_with_override("cash.open_drawer", ...)`;
   - on success it calls a new service method `CashDrawerService.record_manual_open(user_id, approved_by_id, reason)`, which writes AuditLog `NO_SALE_DRAWER_OPEN` with terminal id and shift id, then queues the job with `manual=True`;
   - put the service in `cbpos/core/services/cash_drawer_service.py`, or in `shift_service.py` if a drawer API already lives there (check first).
3. Reason: optional, from a small prompt with presets ("Change for customer", "Check float", "Other"). **Recommended:** no prompt, because cashiers use this often; the audit row is enough. Phase 10C #940 (owner anomaly report) will surface frequent opens. → Apply: no prompt.
4. Find every trigger (F8, Ctrl+D, the action-panel button; `graft grep "open_cash_drawer"`). All go through the same method.

**Tests.**
- `test_escpos_driver.py::test_issue_793_manual_kick_ignores_cash_only`.
- `test_issue_793_auto_kick_card_only_skipped`.
- `test_issue_793_manual_open_requires_permission_and_audits`: cashier without the permission is denied with no job queued; with an override, one audit row and one job.

**UI/UX.**
- When denied, the standard override dialog.
- After opening, a quiet status message: `pos.drawer_opened` "Drawer opened (recorded)."
- If the printer or drawer is not configured: `pos.drawer_not_configured` "No cash drawer is set up. Set it up in Settings → Hardware."
- Run the §0.7 UI gate.

**Acceptance.**
- [ ] Manual kick jobs carry `manual: True` and bypass `drawer_on_cash_only`.
- [ ] Permission check plus audit entry for manual opens.
- [ ] Tests: manual kick works with the default config; an automatic card-only kick is still skipped.

### #792 — "Email receipt" crashes

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (harden, clarify)

**Root cause.** `receipt_options_dialog.py:246` calls `EmailService.send_receipt(email, doc_no)`, which doesn't exist. `email_service.py` has `deliver_email` `:22`, `send_email` `:102` and `send_email_with_pdf` `:127`.

**Fix design.**
1. Add `EmailService.send_receipt(sale_id: int, to_email: str) -> QThread-worker`, matching the return type the dialog expects (`self.worker = ...`). Look at how `send_email_with_pdf` returns a worker and follow it. It:
   - builds the sale's PDF. Use the **A4 invoice generator**. Find it with `graft grep "def generate_pdf"`. It must run in the worker thread, not the UI thread (Phase 7 #879 moves A4 generation off the UI thread generally; here, generate inside the worker);
   - sends with subject `email.receipt_subject` and body `email.receipt_body`, in the **receipt language** setting (use `translate_in(lang, key)`), with the CB POS footer (find the existing email footer helper used by the daily report email; reuse it);
   - validates the email address with the existing validator in `cbpos/core/utils/` (check `validators`).
2. `EmailService.is_configured() -> bool` checks the SMTP settings. The dialog disables the Email button with a tooltip when not configured.
3. The worker's finished and error signals report back. The dialog shows success or error and never blocks.

**Tests.**
- `test_email_service.py::test_issue_792_send_receipt_attaches_pdf`: mock SMTP, or mock `deliver_email`, and assert it was called with the attachment, subject and recipient.
- `test_issue_792_not_configured_button_disabled` (pytest-qt).

**UI/UX.**
- Email field with validation.
- Button **Send** with a spinner while sending (disabled).
- Success `receipt.email_sent` "Receipt sent to {email}."
- Failure `receipt.email_failed` "Couldn't send the email: {reason}. The sale is saved; you can resend it from Sale History."
- Not configured: tooltip `receipt.email_not_configured` "Email isn't set up. Set it up in Settings → Email."
- Subject `email.receipt_subject` "Your receipt {doc} from {shop}".
- Body `email.receipt_body` "Thank you for shopping at {shop}. Your receipt {doc} is attached.\n\n— Sent by CB POS · {website}".
- Run the §0.7 UI gate.

**Acceptance.**
- [ ] Email receipt sends the sale's PDF through SMTP in the background.
- [ ] Subject and body are i18n keys with CB POS branding.
- [ ] Without SMTP, the button is disabled with an explanation.
- [ ] Unit test with SMTP mocked.

### #813 — Expose bill-level discount (% or amount) in the sales screen

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (full UI gate: new dialog)

**Problem.** The cart and tax maths already support a whole-bill discount, but no button or shortcut reaches it.

**Evidence.** `cart_service.py:132-137` (cart discount) and `:325-333, 366-369` (tax after discount). Only tests call it.

**Fix design.**
1. **Shortcut:** **Ctrl+B** ("Bill discount").
   - Check it's free (`graft grep "Ctrl+B"`); if taken, use **Shift+F4** (line discount is likely F-something; keep them adjacent).
   - Add it to the F1 shortcuts help (`shortcuts.*` keys) and to the action panel next to the line discount.
2. **Dialog** `BillDiscountDialog` (`cbpos/ui/dialogs/bill_discount_dialog.py`, objectName `BillDiscountDialog`):
   - **% / Amount** toggle;
   - value field;
   - a live preview "Bill Rs 2,450.00 → Rs 2,205.00 (−Rs 245.00)";
   - **Remove discount** when one exists;
   - footer `[Apply] [Cancel]`.
   - Reuse the line-discount dialog's look if one exists.
3. **Permission:**
   - Use `sales.discount` (or the existing discount permission; `graft grep "discount" --in cbpos/core/constants/permissions.py`).
   - Above `max_discount_percent` (as a percentage of the bill, after line discounts), require `check_permission_with_override` with the override permission used for line discounts.
   - Audit `BILL_DISCOUNT` with value and approver.
4. **Storage:** `Sale.additional_discount_type/value` already exist; verify `_execute_sale` writes them from the cart.
5. **Outputs:**
   - the cart totals area shows a "Bill discount" row (styled like the existing discount row: `test_cart_discount_row_tint.py` hints at the existing style);
   - the thermal receipt and A4 invoice show "Bill discount −Rs X". Check both builders print `additional_discount_*`.
6. The Tax Filing Summary "Total Discounts" is Phase 6 #796. Leave a note.
7. **Interaction with loyalty:** the order is line discounts, then bill discount, then loyalty redemption (ADR 0002). Verify `get_totals` uses that order, and document it in the dialog's preview.

**Tests.**
- `test_cart_service.py::test_issue_813_bill_discount_percent_and_amount_totals_and_tax`.
- `test_issue_813_bill_discount_over_cap_requires_override` (service or permission-helper level).
- `test_issue_813_sale_stores_bill_discount`.
- pytest-qt `test_issue_813_dialog_keyboard_flow`: Ctrl+B, type 10, Enter, and the cart total is updated.

**UI/UX keys:**
- `bill_discount.title` "Bill discount"
- `bill_discount.percent` "%"
- `bill_discount.amount` "Amount"
- `bill_discount.preview` "Bill {before} → {after} (−{discount})"
- `bill_discount.remove` "Remove discount"
- `bill_discount.over_cap` "This is more than the {cap}% you can give. A manager must approve it."
- `cart.bill_discount_row` "Bill discount"
- `shortcuts.bill_discount` "Bill discount"

Keyboard: the value field is focused on open, Tab toggles %/Amount (or Alt+P / Alt+A), Enter applies and Esc cancels. Run the full §0.7 UI gate, including si/ta at 1366×768.

**Acceptance.**
- [ ] A "Bill discount" action with a keyboard shortcut (listed in F1 help), % or amount, permission-gated with an override threshold.
- [ ] Shown on the cart, the receipt and the A4 invoice, and stored on the sale.
- [ ] i18n in en/si/ta.

---

## Phase exit gate
- [ ] All 12 issues merged and **verified closed** with closing comments (§0.10). Epic checklists updated.
- [ ] Full suite green once per batch, and `pre-commit` clean.
- [ ] Manual checkout walkthrough by keyboard only (English plus si or ta):
  - scan, line discount, qty change, Ctrl+B bill discount;
  - F6 hold, then F7 recall;
  - redeem points then force a failure (unplug the DB: rename the file on a copy), then a walk-in sale;
  - F8 drawer as cashier (override prompt);
  - email receipt.
- [ ] UI gate screenshots: the bill discount dialog, the recall-notices message, the email receipt states, the drawer messages, the error-on-failure dialog.
- [ ] ADR 0001 updated for points (#913).
- [ ] PROGRESS.md updated.
