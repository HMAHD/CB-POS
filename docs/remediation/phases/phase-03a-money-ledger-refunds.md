# Phase 3A — Money: Shift Cash, Payment-Method Identity, Credit Ledger, Refunds and Voids

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> This spec was verified against `origin/main` @ `4bcc837` on 2026-10-28. Re-verify every `file:line` before editing (§0.1 step 7).

## Phase brief

**Outcome (end state):**
- The shift's expected cash equals the cash that physically entered and left the drawer:
  - change given is not counted;
  - cash refunds are subtracted;
  - F12 Quick Pay counts;
  - any cash-type method counts, whatever it's named.
- Payment methods are identified by a stable **kind** (CASH, CARD, CREDIT, QR, CHEQUE, TRANSFER, OTHER), never by display name. Renaming "Cash" to "මුදල්" breaks nothing.
- A customer's debt changes only by the bill amount actually put on credit, for the customer actually attached. Every change has one ledger row equal to it (ADR 0001).
- Refunds can be **partial**: chosen lines and quantities, several times per sale, capped at what was sold, allocated back to the original tenders proportionally (D5).
- A refunded sale can't be voided, a refund can't be voided, and the UI shows whether a sale is not refunded, partly refunded or fully refunded.

**Depends on:** Phase 1 merged (auth: `check_permission_with_override` must check the real cashier, #835).
**Unblocks:**
- Phase 3B (cart and checkout build on the payment rules here);
- Phase 6 (reports read the new `method_kind` and refund rows);
- Phase 9 (#827 warranty refunds reuse the partial-refund service).

### Issues

| # | Title | Sev | Size | Batch | Gate |
|---|---|---|---|---|---|
| #802 | Shift summary misses "Bank Transfer" (expects "Transfer") | medium | (in foundation) | 3A.1 | agent |
| #885 | Expected cash only matches a method named exactly "Cash" | medium | (in foundation) | 3A.1 | agent |
| #854 | F12 Quick Pay stores "CASH", left out of shift cash | high | S | 3A.1 | agent |
| #834 | Change given inflates expected cash | critical | M | 3A.1 | agent |
| #850 | Expected cash never subtracts cash refunds | high | S (falls out of 3A.3 design + test here) | 3A.1 | agent |
| #851 | Over-tender accepted on Credit and other non-cash methods | high | M | 3A.2 | agent |
| #852 | Credit charged to the first customer in the list | high | M | 3A.2 | agent |
| #887 | Two CREDIT lines raise debt by both, ledger writes one | medium | S | 3A.2 | agent |
| #849 | Refund of an over-credited sale wipes more debt than the bill | high | S | 3A.2 | agent |
| #888 | Balance adjustment clamps debt at 0, wiping store credit | medium | S | 3A.2 | agent |
| #847 | Void allowed on an already-refunded sale | high | S | 3A.3 | agent |
| #848 | Void allowed on a refund (credit note) | high | S | 3A.3 | agent |
| #812 | Partial / item-level refunds | medium (feature) | L | 3A.3 | human (tax allocation question below, recommended answer given) |
| #915 | Refunded sales still show "Completed" with an active Refund button | low | M | 3A.3 | agent |

### Subsystem map (read before any batch)

**Checkout flow.** `SalesView` (`cbpos/ui/views/sales_view.py`) → `PaymentDialog` (`cbpos/ui/dialogs/payment_dialog.py`):
- `self.payments: list[{"method": name, "amount": Decimal}]`, built in `add_payment()` `~:597-641`;
- the credit customer combo is filled `~:409-414` / `:442-444`.

From there the flow continues:
1. `SalesView` calls `TransactionService.process_sale(...)` (`cbpos/core/services/transaction_service.py:73`).
2. That calls `_execute_sale()` (`:432-510`), which writes `SalePayment(payment_method=p["method"], amount=p["amount"])` `~:487`.
3. `_charge_credit()` (`:188-229`) puts CREDIT on `Customer.current_debt`.
4. `_record_credit_charge()` (`:232-252`) writes the ledger row via `CustomerCreditService.record_credit_sale_in_session`.

Quick Pay: `SalesView.quick_pay` `~:1639` (F12).

**Models** (`cbpos/core/models/__init__.py`):
- `SalePayment` `:515-525`: `payment_method: str(20)` is a **name string**, plus `amount`.
- `PaymentMethod` `:819-831`: `name` unique, `is_cash`, `open_drawer`, `shortcut`, `is_active`.
- `Sale` `:190+`:
  - `total_amount`, `tax_vat`, `tax_sscl`, `net_revenue`;
  - `additional_discount_type/value` (bill discount);
  - `loyalty_points_redeemed/value` (redemption is a discount, ADR 0002);
  - `payment_method`, where `"REFUND"` **marks a refund document**;
  - `refund_of_sale_id`.
- `SaleItem` `:494-513`: `qty`, `unit_price`, `original_price`, `discount_type/value`, `is_manual_price`, `subtotal`, `notes`.

**Constants:** `PaymentMethodType` in `cbpos/core/constants/status.py:55-64`: `CASH="Cash"`, `CARD`, `CREDIT`, `QR_MOBILE`, `CHEQUE`, `BANK_TRANSFER="Transfer"`, `REFUND="REFUND"`.

**Seeds disagree:**
- `database_setup_service.py:158` seeds "Bank Transfer";
- `scripts/seed.py:~1689` seeds "Transfer".

**Shift:** `ShiftService.get_shift_summary` (`cbpos/core/services/shift_service.py:91-202`):
- groups `SalePayment.payment_method` and looks up literal names (`:125-131`);
- expected cash at `:145`.

(#884, in Phase 2.6, changes the same query to scope by terminal and shift. Coordinate: make your change merge-friendly by keeping the method classification in one helper.)

**Credit:** `cbpos/core/services/customer_credit_service.py`:
- `credit_to_reverse` `:183-240`;
- `reverse_credit_sale_in_session` `:243-330` (allows negative balances by design, #715);
- `record_adjustment` `~:340-370`.

**Refund and void:**
- `TransactionService.refund_breakdown` `:612-653`;
- `process_refund` `:656-806` (full refund only; swallows its own `ValueError` at `~:775-777`);
- `void_sale` `:524-586`.
- `cbpos/core/services/refund_breakdown.py` defines `RefundBreakdown` and `refund_cash_back`.
- Loyalty: `LoyaltyService.reverse_sale_points` `:201-273`, `return_redeemed_points` `:312-364`.

**UI for refunds and voids:**
- `cbpos/ui/dialogs/refund_dialog.py` (`load_sale` `:180-239`);
- `sale_history_dialog.py` (`_on_sale_selected` `:555-687`, `_start_refund` `:769-789`);
- `ui/views/history_view.py:295-314`;
- `ui/views/document_view.py` (`update_action_buttons` `~:801-808`).

**Every reader of `SalePayment.payment_method`** (run `graft grep "SalePayment.payment_method"`); all must move to `method_kind`:
- `shift_service.py:109,122`
- `financial_reports.py:331,336` (TaxFilingSummary)
- `void_refund_report.py:165,178` (PaymentMethodSummary)
- `customer_credit_service.py:210`
- `dashboard_service.py:426,431`
- `payment_service.py:73`
- `report_service.py:40,43`

**Helpers to reuse:**
- `Precision.MONEY` (`status.py:70`) and the D4 `ROUND_HALF_UP` helper. Phase 6 #810 introduces the single helper. **If it doesn't exist yet when you start, create `cbpos/core/utils/money.py` with `round_money(x: Decimal) -> Decimal` (`x.quantize(Precision.MONEY, rounding=ROUND_HALF_UP)`) and use it. #810 will adopt it.**
- `check_permission_with_override`.
- `RefundBreakdown`.

### Domain invariants this phase must preserve

1. For every sale: `sum(SalePayment.amount) == Sale.total_amount`. Tendered cash above that is stored in `tendered_amount`, never in `amount`.
2. Non-cash payments never exceed the amount still due. Only CASH kind may be over-tendered.
3. `expected_cash = starting_cash + Σ(CASH-kind SalePayment.amount for the shift's sales and refunds) + cash ins − drops − payouts`. Refund payments are negative.
4. For every customer: `current_debt == Σ ledger amounts` (ADR 0001). Every debt change writes exactly one ledger row whose amount is that change. No clamping.
5. For every sale line: `Σ refunded qty ≤ sold qty`. For every sale: `Σ refund totals ≤ total_amount`, and a full refund reverses exactly `total_amount`, `tax_vat`, `tax_sscl` and `net_revenue`.
6. A sale with any refund cannot be voided. A refund document can never be voided or refunded.
7. Credit reversed on a sale never exceeds the credit charged on that sale.

### Batches (one PR each)

| Batch | Branch | Issues (in order) | Why grouped |
|---|---|---|---|
| 3A.1 | `fix/p3a-b1-shift-cash-payment-identity` | foundation (method kind) → #802, #885, #854, #834, #850 | One schema change, payment-method kind plus tendered amount, fixes five symptoms |
| 3A.2 | `fix/p3a-b2-credit-ledger` | #851, #852, #887, #849, #888 | Credit checkout and ledger invariants |
| 3A.3 | `fix/p3a-b3-refund-void-state-machine` | #847, #848, #812, #915 | One refund engine with partial refunds, plus the void guards and refund state that depend on it |

---

## Batch 3A.1 — Shift cash and payment-method identity

**Branch:** `fix/p3a-b1-shift-cash-payment-identity` · **Issues:** #802, #885, #854, #834, #850

### Foundation (first commit of the batch): payment-method kind

**Skills:** domain-modeling → migration rules (§0.2 Schema) → tdd → ponytail. This is L-size design work: write the design note in the PR first and run `/egm-review` on it (§0.6).

**Why.** Five issues (#802, #885, #854, #834, #850) and three in Phase 6 come from one root cause: money is classified by matching **display names**. Names are user-editable, seeded inconsistently ("Bank Transfer" vs "Transfer"), case-sensitive ("CASH" vs "Cash"), and will be translated by shops. A stable kind fixes every symptom at once.

**Design.**
- `PaymentMethodKind` (new, in `cbpos/core/constants/status.py`), a string enum: `CASH`, `CARD`, `CREDIT`, `QR`, `CHEQUE`, `TRANSFER`, `OTHER`, `REFUND_LEGACY`. The last one exists only for historical "REFUND" payment rows.
- `PaymentMethod.kind: str(20)`: NOT NULL, default `"OTHER"`, indexed. The shop can rename a method freely; the **kind** of a built-in method can't be changed in the UI. For custom methods the shop picks the kind in Payment Methods settings.
- `PaymentMethod.is_cash` stays, but is derived. Keep it in sync on save (`is_cash = kind == CASH`), so existing readers keep working. Add a code comment saying `kind` is authoritative.
- `SalePayment` gets two columns:
  - `method_kind: str(20)`: NOT NULL, server default `"OTHER"`, indexed. A snapshot of the method's kind at sale time.
  - `tendered_amount: Numeric(12,2)`, nullable: what the customer handed over, CASH only, when it differs from `amount`. Change = `tendered_amount - amount`.

  `payment_method` (the name) stays as a display snapshot.
- **Migration** `payment_method_kind` (one migration, SQLite batch mode):
  1. Add the columns.
  2. Backfill `payment_methods.kind`, case-insensitive on `name`:
     - `cash` → CASH; `card` → CARD; `credit` → CREDIT; `qr/mobile` or `qr` → QR; `cheque` or `check` → CHEQUE; `transfer` or `bank transfer` → TRANSFER;
     - otherwise CASH if `is_cash` else OTHER.
  3. Backfill `sale_payments.method_kind` by `UPPER(payment_method)` matched against `UPPER(payment_methods.name)`. Then fix the unmatched rows: `UPPER(payment_method) = 'CASH'` → CASH (#854 legacy rows); `'REFUND'` → REFUND_LEGACY; `'TRANSFER'`/`'BANK TRANSFER'` → TRANSFER; `'CREDIT'` → CREDIT; everything else → OTHER.
  4. **Do not rename** existing method names.
  5. Downgrade drops the columns.
- `DatabaseSetupService.create_empty_database()` and `scripts/seed.py` set `kind` explicitly for each seeded method. Keep their names as they are, but make the seeds agree on "Bank Transfer" (the empty-DB name). Update `PaymentMethodType.BANK_TRANSFER` only if nothing else depends on the literal; the kind removes that dependency anyway.
- `PaymentService` (`cbpos/core/services/payment_service.py`): add `get_kind_for(method_name) -> str` (cached per session) and `get_default_cash_method() -> PaymentMethod` (the first active method with kind CASH, ordered by id).
- **Writing payments:** `_execute_sale` resolves `method_kind` from the PaymentMethod row by name. **If no row matches, raise `ValueError("unknown_payment_method")`.** Never guess.
- **Readers:** every reader in the list above switches from `payment_method` to `method_kind` for classification. For display, group by `method_kind` and show the translated kind name, or the method name for custom OTHER methods. In Phase 3A, change **only** `shift_service`, `customer_credit_service` and `payment_service`. Reports (financial, void_refund, dashboard, report_service) are Phase 6 (#843–#845). Leave them working on names, and add `# TODO(#844): use method_kind` markers so Phase 6 finds them.
- *Sync impact:* `SalePayment` rows sync from tills to the Main PC, and `PaymentMethod` syncs to tills. Find the serializers (`graft grep "SalePayment" --in cbpos/core/services/sync`, and the same for `PaymentMethod`) and add the new fields. An older peer that doesn't send `method_kind` must be handled: on apply, compute the kind from the name with the migration's mapping function, which lives in `payment_service.py` as `classify_method_name(name) -> str` and is reused by the migration through a copied constant table. **Migrations must not import app code**, so duplicate the small mapping inside the migration file.

**Tests (write first).** `tests/unit/test_payment_method_kind.py`.
- `test_classify_method_name_mapping`: table-driven test of the mapping.
- `test_sale_payment_snapshots_kind`: a sale paid with the method "Bank Transfer" has `method_kind == "TRANSFER"`.
- `test_unknown_method_name_rejected`: `process_sale` with method "Bitcoin" raises `ValueError`.
- `test_migration_backfills_kind`: build a DB at the previous head with "Bank Transfer", "CASH" and "REFUND" payment rows, upgrade, and assert the kinds. Pattern: an Alembic upgrade test on a `tmp_path` SQLite file. If no such test exists, write it with `alembic.command.upgrade` and a `Config` pointing at that file.

**UI/UX spec.** Payment Methods management screen (find it with `graft grep "class PaymentMethod" --in cbpos/ui`):
- add a **Type** column and field, a combo with translated kinds:
  - `payment_methods.kind_cash` → "Cash"
  - `…kind_card` → "Card"
  - `…kind_credit` → "Customer credit"
  - `…kind_qr` → "QR / mobile pay"
  - `…kind_cheque` → "Cheque"
  - `…kind_transfer` → "Bank transfer"
  - `…kind_other` → "Other"
- Built-in methods show the type read-only, with the tooltip `payment_methods.kind_locked` → "This is a built-in payment type. You can rename it, but its type can't change."
- Help text under the combo: `payment_methods.kind_help` → "The type tells CB POS how to count this payment in the cash drawer and the credit book."
- Run the §0.7 UI gate.

**Do NOT.**
- Do not match names case-insensitively as "the fix". That still breaks on renames and translations.
- Do not delete or rename existing payment methods in the migration.
- Do not touch Phase 6 report queries beyond adding TODO markers.

### #802 — Shift summary misses "Bank Transfer" sales

**Severity:** medium · **Size:** covered by the foundation · **Gate:** agent

**Root cause.**
- `shift_service.py:131` looks up `PaymentMethodType.BANK_TRANSFER` (`"Transfer"`, `status.py:63`).
- Real shops have "Bank Transfer" (`database_setup_service.py:158`); the demo seed uses "Transfer" (`scripts/seed.py:~1689`).

**Fix.** `get_shift_summary` groups by `SalePayment.method_kind`: `transfer_sales = by_kind.get("TRANSFER", 0)`, and likewise CARD, CREDIT, QR and CHEQUE. Keep `sales_by_method` (names) for display, because the closing screen shows it.

**Test.** `tests/unit/test_shift_service.py::test_issue_802_bank_transfer_counted_in_transfer_total`, on the **empty-DB seed** (`create_empty_database`) rather than the demo seed.

**Acceptance.**
- [ ] Payment methods identified by kind, not name.
- [ ] A transfer sale appears in the shift transfer total on an empty-DB seed.

### #885 — Expected cash matches only a method named exactly "Cash"

**Severity:** medium · **Size:** covered by the foundation · **Gate:** agent

**Root cause.** `shift_service.py:125`: `sales_by_method.get(PaymentMethodType.CASH, …)`.

**Fix.** `total_cash_sales = by_kind.get("CASH", 0)`, which sums every CASH-kind row: renamed methods, "Cash (USD)", and refunds' negative rows (see #850).

**Test.** `test_issue_885_renamed_and_second_cash_methods_count`: rename "Cash" to "Salli" and add "Cash USD" (kind CASH). Sales on both count in `cash_sales` and `expected_cash`.

**Acceptance.**
- [ ] A renamed or extra CASH-kind method counts.

### #854 — F12 Quick Pay records "CASH"

**Severity:** high · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Problem.** Quick Pay (F12, on by default) saves payments as "CASH". The shift summary only knows "Cash", so every F12 sale is missing from the drawer total and the drawer looks over.

**Evidence and root cause.** `sales_view.py:~1639` (`quick_pay`) builds `[{"method": "CASH", "amount": total}]`, a literal string.

**Fix.**
- `quick_pay` asks the service for the default cash method: `PaymentService.get_default_cash_method()`, and uses its `name`.
- If there is no active CASH method, show `_t("pos.no_cash_method")` and don't process the sale.
- The kind is then resolved by `_execute_sale` like any other payment.

**Tests.**
- `test_issue_854_quick_pay_counts_as_cash`: a service-level test calling `process_sale` the way `quick_pay` does (with the name from `get_default_cash_method()`), then `get_shift_summary`: `cash_sales == total`.
- Optional pytest-qt test of `SalesView.quick_pay` if an existing SalesView test harness exists (`graft grep "def test_.*quick_pay"`).

**UI/UX.** `pos.no_cash_method` → "There's no active cash payment type. Turn one on in Settings → Payment Methods." Run the §0.7 UI gate.

**Do NOT.** Do not hard-code "Cash" either.

**Acceptance.**
- [ ] An F12 sale counts in `cash_sales` and `expected_cash`.

### #834 — Change given inflates the shift's expected cash

**Severity:** critical · **Size:** M · **Gate:** agent · **Skills:** systematic-debugging → tdd → ponytail; impeccable (harden) for the payment dialog

**Problem.** For a Rs 100 bill paid with a Rs 1000 note, CB POS records Rs 1000 of cash. The drawer only gained Rs 100. Every shift shows a false shortage equal to all the change given, which can get an honest cashier accused.

**Evidence and root cause.**
- `payment_dialog.py:~635` appends `{"method": …, "amount": amount}` with the **tendered** amount.
- `transaction_service.py:~487` stores `amount=p["amount"]`, unchanged.
- No field holds the change.

**Fix design.**
- *Recommended:* in `_execute_sale`, normalise payments **before** writing:
  1. `due = final_total`.
  2. Validate: for non-CASH kinds, `Σ amount ≤ due`, else `ValueError("non_cash_overpay")`. This is also #851's service-side guard; implement it once here, and #851 adds the dialog part.
  3. `excess = Σ all amounts − due`. If `excess > 0`, it must be covered by CASH payments. Take it off the **last** CASH payment (then earlier ones) down to 0. Set `tendered_amount` = the original amount on each CASH row that was reduced.
  4. If `Σ amounts < due` → `ValueError("underpaid")`. This is presumably checked already; verify and keep it.
  5. Assert invariant 1 before flush.
- The receipt shows "Tendered" and "Change" from `Σ tendered_amount` (or `amount` where `tendered_amount` is null) and `change = tendered − amount`. Find the receipt builder's current change logic (`graft grep "change" --in cbpos/infrastructure/hardware` and the receipt service) and make it read the stored fields, so reprints show the same numbers.
- *Rejected alternatives:* "Subtract change in the shift summary": change isn't stored anywhere, and every report would need the same correction.
- *Data/schema:* `tendered_amount` comes from the foundation migration. Existing rows: leave them null. Historical over-tendered rows stay inflated. Note this in the PR and the release notes: shift reports before the upgrade may show a shortage. **Do not rewrite history** (§0.2).

**Implementation steps.**
1. Add `_normalise_payments(payments, due, kinds) -> list[dict]` in `transaction_service.py`, a pure function so it's easy to test, and call it at the top of `_execute_sale`.
2. Write `SalePayment(payment_method=name, method_kind=kind, amount=applied, tendered_amount=tendered or None)`.
3. Update the receipt "Tendered / Change" lines to use the stored values. Check thermal (`escpos` receipt builder) **and** A4 invoice.

**Tests (write first).** `tests/unit/test_transaction_service.py`:
- `test_issue_834_cash_overtender_stores_applied_amount`:
  - Given a bill of 100.00, paid `[Cash 1000.00]`.
  - Then the stored `amount == Decimal("100.00")` and `tendered_amount == Decimal("1000.00")`.
  - Also `get_shift_summary(...)["expected_cash"] == starting_cash + 100.00`.
- `test_issue_834_split_cash_and_card_overtender_reduces_cash`: bill 100, Card 60 + Cash 100 → Card 60, Cash applied 40, tendered 100.
- `test_issue_834_receipt_shows_tendered_and_change`: the receipt data or builder output contains 1000.00 and 900.00. Use the receipt-model function the printer uses, not the printer.

**UI/UX spec.** The payment dialog already shows change; keep it. Reprint must show the same tendered and change as the original. Run the §0.7 UI gate on a reprint.

**Do NOT.**
- Do not store change as a negative cash payment.
- Do not adjust historical rows.
- Do not cap in the dialog only.

**Edge cases.**
- A rounding-adjusted total (if cash rounding exists: `graft grep "round" --in cbpos/ui/dialogs/payment_dialog.py`) uses the final, rounded due.
- A Rs 0 total sale: no payments needed.

**Acceptance.**
- [ ] Bill 100, Cash 1000 → stored SalePayment 100.00, and `expected_cash` rises by 100.
- [ ] Receipt and reprint show tendered 1000 and change 900.

### #850 — Expected cash never subtracts cash refunds

**Severity:** high · **Size:** S here (the mechanism is built in 3A.3) · **Gate:** agent

**Problem.** A Rs 2000 cash sale refunded in the same shift leaves expected cash Rs 2000 too high.

**Evidence and root cause.**
- Refunds write one `SalePayment(payment_method="REFUND", amount=-total)` (`transaction_service.py:~766-771`), which is not cash.
- `shift_service.py:145` has no refund term.

**Fix design.**
- From 3A.3 onward, refund documents write **one negative SalePayment per original tender kind** (D5 proportional allocation). Cash handed back is a negative CASH-kind row, so `total_cash_sales = Σ CASH kind` subtracts it automatically, in the shift of the user who did the refund (the drawer it left).
- Until 3A.3 lands, this batch only adds the failing test, marked `@pytest.mark.xfail(reason="fixed by 3A.3 refund engine (#812)", strict=True)`. 3A.3 removes the marker. **This is the one place an xfail is allowed**, because the fix is deliberately scheduled; record it in PROGRESS.md.
- Legacy "REFUND" rows (REFUND_LEGACY kind) from before the upgrade: `get_shift_summary` subtracts their cash-back share for refunds of sales that were paid in cash, using `refund_cash_back` from `refund_breakdown.py`. This handles shifts open across the upgrade. **Recommended:** don't bother. A shift spanning an upgrade is an edge case; note it in the release notes instead. → Apply the recommendation.

**Test.** `tests/unit/test_shift_service.py::test_issue_850_cash_refund_reduces_expected_cash`: start a shift with 0, sell 2000 cash, refund in full, and `expected_cash == 0`.

**Acceptance.**
- [ ] Sell 2000 cash, refund it, and `expected_cash` returns to the starting float (passes once 3A.3 is merged).

---

## Batch 3A.2 — Credit payments and customer ledgers

**Branch:** `fix/p3a-b2-credit-ledger` · **Issues:** #851, #852, #887, #849, #888 · **Order:** as listed. #851 and #852 are the checkout entry points. #887 and #849 are ledger arithmetic. #888 is a separate adjustment path.

### #851 — Over-tender accepted on Credit and other non-cash payments

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (harden) for the dialog

**Problem.** On a Rs 200 bill a cashier can type Credit 1000 by mistake. CB POS accepts it, shows "Change 800" and puts Rs 1000 on the customer's credit book. Card payments can also show "change". Only cash can be over-tendered.

**Evidence and root cause.**
- `payment_dialog.py:~597-641` (`add_payment`) checks `amount > 0` but never `amount ≤ remaining` for non-cash methods.
- `transaction_service.py:~227`: `customer.current_debt += p["amount"]`.

**Fix design.**
- *Service (already added by #834's `_normalise_payments`):* reject `Σ non-CASH > due` with `ValueError("non_cash_overpay")`. Make sure the CREDIT charge uses the **applied** amount after normalisation.
- *Dialog (prevention):* in `add_payment`, if `self.current_method.kind != CASH` and `amount > remaining`:
  - clamp the field to `remaining`;
  - show an inline note (not a modal) `payment.non_cash_capped` with `{amount}`;
  - don't add it until the cashier presses Enter again.

  **Recommended:** clamp and add immediately, with the inline note, because it's faster at the till. → Apply the recommendation.
  - The dialog needs `kind` on its method objects. It loads methods from `PaymentService`; carry `kind` through.
- The **Finish** button stays disabled while non-cash total > due. That can't happen after the clamp, but guard it anyway.

**Tests.**
- `tests/unit/test_transaction_service.py::test_issue_851_credit_overpay_rejected_by_service`: bill 200, `[Credit 1000]` → `ValueError`, customer debt unchanged, no Sale row.
- `tests/unit/test_payment_dialog.py::test_issue_851_non_cash_amount_clamped_to_remaining` (pytest-qt; build the dialog the way existing payment dialog tests do: `graft grep "PaymentDialog(" --in tests`).

**UI/UX spec.**
- `payment.non_cash_capped` → "Card and credit payments can't be more than the bill, so {amount} was used."
- Shown in the dialog's existing status or info label area, in the warning colour from QSS (`class="warning"` or the existing equivalent), cleared on the next input.
- Run the §0.7 UI gate, keyboard only: Credit → type 1000 → Enter → Finish.

**Do NOT.** Do not silently clamp in the service. The service rejects, and the dialog prevents.

**Acceptance.**
- [ ] Credit 1000 on a 200 bill is clamped to 200 in the dialog.
- [ ] `process_sale` raises when non-cash payments exceed the total.
- [ ] Customer debt rises by exactly the bill's credit portion.

### #852 — A Credit payment is charged to the first customer in the list

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** tdd (pytest-qt) → ponytail; impeccable (clarify)

**Problem.** With customer Nimal attached, choosing Credit and pressing Enter charges whoever happens to be first in the customer list. The debt, ledger row, loyalty points and the sale's customer all go to the wrong person. Two customers with the same name collide.

**Evidence and root cause.**
- `payment_dialog.py:~409-414`: `self.customers_map = {c.name: c.id …}` keyed by **name**, and `cmb_customer.addItems(names)`. Index 0 is never pre-selected to the attached customer.
- `add_payment` `~:621-633` reads `currentText()` and **overwrites** `self.customer_id`.

**Fix design.**
- Fill the combo with `addItem(display_text, userData=customer.id)`.
  - `display_text` = `name`, plus ` — {phone}` when the phone is set, to tell same-name customers apart.
  - Drop `customers_map`.
- After loading, if `self.customer_id` (the attached customer) is set, `setCurrentIndex(findData(self.customer_id))`.
- When the sale already has an attached customer, show the combo **read-only** (disabled) with that customer. Changing the customer is done in the sales screen (F2), so there is one place to pick a customer.
- No attached customer, with Credit chosen: the combo is editable and searchable; read the id with `currentData()`. If `currentData()` is None (typed text not matching an item), show the existing `payment.credit_customer_not_found`.
- After a successful Credit add, tell `SalesView` which customer was chosen so the cart shows it. The dialog already exposes `customer_id` in `payment_data`; verify that `SalesView` (`~:1052-1062`) applies it to the cart **before** `process_sale`.

**Tests.** `tests/unit/test_payment_dialog.py`:
- `test_issue_852_attached_customer_preselected_for_credit`: attach id 2, with id 1 first alphabetically. Choose Credit, add, and `payment_data["customer_id"] == 2`.
- `test_issue_852_same_name_customers_charged_by_id`: two "Nimal" customers. Select the second by data, and its id is used.

**UI/UX spec.**
- Credit section with an attached customer: label `payment.credit_to` → "Put on credit for:", then the customer name and phone, read-only.
- Without one: the searchable combo, with placeholder `payment.credit_pick_customer` → "Type a name or phone…".
- Keyboard: when Credit is selected, focus goes to the amount if a customer is attached, and to the combo if not.
- Run the §0.7 UI gate.

**Do NOT.** Do not key anything by customer name. Do not let the dialog change an attached customer silently.

**Acceptance.**
- [ ] With an attached customer, Credit pre-selects them and `payment_data` returns their id.
- [ ] Two same-name customers can each be charged correctly.

### #887 — Two CREDIT lines raise the debt by both but write one ledger row

**Severity:** medium · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Root cause.**
- `transaction_service.py:211-228` (`_charge_credit`): `charge = (p["amount"], customer.current_debt)` is **overwritten** on each CREDIT payment.
- `_record_credit_charge` then writes one row with the last amount.

**Fix.**
- Accumulate: `total += applied_amount` per CREDIT payment.
- Lock the customer once.
- Check the credit limit against `current_debt + total`.
- Return `(total, balance_after)`.
- One ledger row per sale, for the summed credit. That matches how reversal reads it (`credit_to_reverse` sums all CREDIT rows).
- Use `method_kind == CREDIT`, not `p["method"].upper()`.

**Test.** `test_issue_887_two_credit_lines_one_ledger_row_equal_to_debt_change`: Credit 400 + Credit 600 on a 1000 bill. The debt delta is 1000, and the sum of this sale's ledger rows is 1000 (one row).

**Acceptance.**
- [ ] The ledger sum equals the debt change after a sale with two CREDIT lines.

### #849 — Refunding an over-credited sale wipes more debt than the bill

**Severity:** high · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Root cause.** `customer_credit_service.py:207-232` (`credit_to_reverse`) sums the CREDIT payments with no cap at `sale.total_amount`. After #851 new sales can't be over-credited, but **historical** ones can.

**Fix.**
- `credit_portion = min(Σ CREDIT-kind amounts, sale.total_amount)`.
- Subtract the credit already reversed by earlier partial refunds (3A.3 provides `credit_already_reversed(sale_id)`; until then, the full-refund rule makes it 0 or all).
- Match `method_kind == CREDIT`, falling back to `UPPER(payment_method) == 'CREDIT'` for REFUND_LEGACY-era rows. The migration already set the kind.

**Test.** `test_issue_849_refund_of_overcredited_sale_reverses_at_most_total`: insert a legacy-style sale (total 1000, CREDIT payment 1200; insert the rows directly, as the service now forbids this). Refund, and the debt falls by 1000.

**Acceptance.**
- [ ] A refund of a 1000 sale paid with 1200 credit reduces debt by at most 1000.

### #888 — A balance adjustment clamps the debt at 0

**Severity:** medium · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Problem.** A customer the shop owes Rs 1000 (store credit after a refund) gets a +50 fee adjustment. CB POS sets the balance to 0, erasing Rs 950 of store credit, and the ledger no longer adds up. The same thing happens the other way round with large negative adjustments.

**Evidence and root cause.** `customer_credit_service.py:363-365`:

```python
customer.current_debt += amount
if customer.current_debt < 0:
    customer.current_debt = Decimal("0.00")
```

The ledger row keeps `amount=amount` (`:367-374`).

**Fix.** Remove the clamp. Negative balances are valid store credit (#715, the same rule as `reverse_credit_sale_in_session`). The ledger amount equals the actual change, which is now always `amount`.

**Test.** `test_issue_888_adjustment_keeps_negative_balance`: balance −1000, +50 → −950, and the ledger sum equals `current_debt`.

**UI/UX.** The Adjust Balance dialog should already explain signs. Check that a negative balance displays as store credit ("Shop owes Rs 950") in the credit book and the customer card (`graft grep "current_debt" --in cbpos/ui`). If it shows "-950.00" bare, use the existing store-credit wording if there is one; otherwise add `credit.store_credit` → "Store credit: {amount}". Run the §0.7 UI gate.

**Acceptance.**
- [ ] The debt change equals the ledger row amount after any adjustment.
- [ ] −1000 + 50 = −950.

---

## Batch 3A.3 — Refund and void state machine

**Branch:** `fix/p3a-b3-refund-void-state-machine` · **Issues:** #847, #848, #812, #915

**Order:**
1. #847 and #848 first (small guards; safe to ship even if #812 slips).
2. #812 (the refund engine).
3. #915 (UI state from the engine).
4. Remove the `xfail` from #850's test.

### #847 — You can void a sale that was already refunded

**Severity:** high · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Problem.** A refunded sale can still be voided. That returns its stock a second time, pushes net sales negative, and takes back points the customer had redeemed.

**Evidence and root cause.**
- `transaction_service.py:546-549` (`void_sale`) only guards `status == "VOID"`, with no refund check.
- `loyalty_service.py:230-238`: `already_reversed` sums **all** REVERSAL rows, including the positive redemption-return row, so a second reversal over-deducts.
- `document_view.py:~801-808` keeps Void enabled.

**Fix.**
- `void_sale`: `if session.query(Sale.id).filter(Sale.refund_of_sale_id == sale.id).first(): raise ValueError("sale_has_refund")`. Read how `void_sale` reports errors today (bool vs raise). Make it raise `ValueError` for business-rule refusals, matching `process_sale`, and make sure its callers show `translate_error`.
- `loyalty_service.py` `already_reversed`: add `LoyaltyLedgerEntry.points < 0` to the filter.
- UI: covered by #915's refund state.

**Tests.**
- `test_issue_847_void_after_refund_refused`: sale with redemption → refund → void raises, and stock, points and debt equal their post-refund values.
- `test_issue_847_reverse_sale_points_idempotent_after_redemption_return`.

**Acceptance.**
- [ ] `void_sale` on a refunded (or partly refunded) sale is refused and changes nothing.

### #848 — You can void a refund (credit note)

**Severity:** high · **Size:** S · **Gate:** agent

**Root cause.** `void_sale` has no check for `sale.payment_method == "REFUND"` or `sale.refund_of_sale_id is not None`.

**Fix.** Raise `ValueError("cannot_void_refund")` for either. Refund documents are final: a wrong refund is corrected by a new sale, never a void.

**Test.** `test_issue_848_void_of_refund_document_refused`: stock and debt are unchanged.

**UI/UX.** `errors.cannot_void_refund` → "A refund can't be voided. If it was a mistake, ring the items up as a new sale." `errors.sale_has_refund` → "This sale has a refund, so it can't be voided. Refund the remaining items instead." Add both to the `translate_error` map (`cbpos/core/utils/error_messages.py`). Run the §0.7 UI gate.

**Acceptance.**
- [ ] `void_sale(refund_id)` is refused and changes nothing.
- [ ] Void is disabled for CN documents (via #915).

### #812 — Partial / item-level refunds and returns

**Severity:** medium (feature, release-blocking per #832) · **Size:** L · **Gate:** human for one accounting question (pre-written below, with a recommendation; you may build everything else first)
**Skills:** brainstorming → domain-modeling → write the design note → `/egm-review` (Goldfish) on it → tdd → codebase-design (deep module) → ponytail; impeccable (full UI gate) for the dialog

**Problem.** Shops constantly return one item from a bill. CB POS can only refund a whole sale, once, so cashiers either refund everything and re-ring the rest (messy books) or refuse the customer.

**Evidence.**
- `transaction_service.py:656-806`: `process_refund` is whole-sale only.
- `:696-698` rejects any second refund.
- `:775-777` swallows its own `ValueError`s.

**Fix design (decide nothing beyond this; ask for anything not covered).**

*Module.* A new deep module, `cbpos/core/services/refund_service.py`, `class RefundService`. `TransactionService.process_refund` becomes a thin wrapper meaning "refund all remaining quantities", kept for existing callers.

```
RefundService.refundable_lines(sale_id) -> list[RefundableLine]
    # per original SaleItem: sold_qty, refunded_qty, remaining_qty, line_refund_value_per_unit
RefundService.preview(sale_id, lines: list[RefundLineRequest]) -> RefundPreview
    # RefundLineRequest = (sale_item_id, qty, reason); RefundPreview = totals, tax, tender allocation
RefundService.refund(sale_id, lines, reason, user_id, *, tender_override=None,
                     override_reason=None, peripherals=None) -> RefundResult
    # raises ValueError(code) for rule violations; never returns False for them
RefundService.refund_state(sale_id) -> Literal["NONE","PARTIAL","FULL"]
RefundService.refund_states(sale_ids) -> dict[int, str]   # one query, for history lists
```

*Schema* (migration `refund_lines`):
- `sale_items.refund_of_item_id`: nullable FK to `sale_items.id`, indexed. Set on refund lines, pointing at the original line.
- `sale_items.refund_reason`: `String(200)`, nullable.
- `sales.refund_tender_override`: `String(20)`, nullable. Set when a manager overrode the tender.
- `sale_items.refunded_qty`: `Numeric(10,3)`, NOT NULL, default 0, kept on the **original** lines and incremented by every refund. Add the DB constraint `CHECK (refunded_qty >= 0 AND (qty < 0 OR refunded_qty <= qty))` (named `ck_sale_items_refunded_qty`; SQLite batch mode recreates the table). The database itself then refuses an over-return, even when two tills race (this is how #914 in Phase 2.6 is enforced; see the question there). Backfill: for each original line of a sale that has a legacy full refund, set `refunded_qty = qty`; otherwise 0.

Historical full refunds have `refund_of_item_id` null; the `refunded_qty` backfill above marks their original lines fully refunded, so `refundable_lines` just reads `qty - refunded_qty`.

*Value of a refunded line.*
- Bill-level discount and loyalty redemption (ADR 0002: redemption is a discount) are spread over lines in proportion to line subtotals:
  - `alloc_factor = sale.total_amount / Σ original line subtotals` (if Σ = 0, the factor is 0);
  - `line_net = line.subtotal × alloc_factor`;
  - `unit_refund = line_net / line.qty`.
- For a request of `q`, value = `round_money(unit_refund × q)`.
- **Remainder rule:** if, after this refund, every line is fully refunded, set this refund's total = `sale.total_amount − Σ previous refund totals` (absolute values). That makes a full set of partial refunds reverse the sale exactly, to the cent.

*Tax.*
- Proportional to value: `refund_vat = round_money(sale.tax_vat × value / sale.total_amount)`, the same for SSCL; `refund_net = value − refund_vat − refund_sscl` (D4: net is the remainder).
- Apply the remainder rule on the final refund to each of `tax_vat`, `tax_sscl` and `net_revenue`.
- **This is the open accounting question below.**

*Tender allocation (D5).*
- Original tenders by kind, from the sale's SalePayment rows (applied amounts), give shares `kind_amount / total_amount`.
- Each kind gets `round_money(value × share)`. The last kind takes the rounding remainder.
- Kinds that can't take money back (OTHER) go to CASH. Show that in the preview.
- The CREDIT share is reversed on the customer's book (`CustomerCreditService.reverse_credit_sale_in_session` with an explicit `amount`; extend it to accept `amount`, defaulting to the full remaining).
- CASH, CARD, QR, CHEQUE and TRANSFER shares become negative SalePayment rows of that kind on the refund document. CASH is handed back from the drawer; CARD and QR are reversed on the terminal by the cashier (the preview says so).
- *Override:* a user with `sales.refund_override_tender` (new permission; add it to `cbpos/core/constants/permissions.py`, the seeds, and the Admin and Manager roles) can send the whole value to CASH or to CUSTOMER_CREDIT (the latter only if the sale has a customer: it becomes a negative CREDIT row and a ledger reversal, which may leave store credit). This needs `override_reason` and writes an AuditLog `REFUND_TENDER_OVERRIDE`. Go through `check_permission_with_override`.

*Stock.* A RETURN movement per refunded line through `_move_stock` (composite-aware), with qty `+q`.
- Service items (`is_service`) get no stock movement. Check the `_move_stock` handling.
- Weighed items accept 3-decimal quantities.

*Loyalty.*
- Points earned on the sale are reversed proportionally: `floor(earned × value / total)`; on the final refund, the remainder of earned points not yet reversed.
- Redeemed points are returned proportionally on the same basis (`floor`, remainder at the end).
- Reuse `LoyaltyService.reverse_sale_points` / `return_redeemed_points` by adding an explicit `points` parameter. Keep "full" as the default for void.

*Documents.*
- Each refund is a new `Sale` with `payment_method="REFUND"`, `refund_of_sale_id`, numbered "RETURN" (as today, `transaction_service.py:~729`).
- Refund items carry negative `qty` and `subtotal`, `refund_of_item_id`, and `refund_reason`.

*Validation (all `ValueError(code)`):*
- `sale_not_found`, `sale_void`, `is_refund_document`;
- `qty_exceeds_remaining` (per line), `qty_not_positive`, `no_lines`;
- `override_needs_reason`, `credit_override_needs_customer`.
- Lock the original sale row for the duration: `session.get(Sale, id, with_for_update=True)`. On SQLite this is a no-op; PostgreSQL concurrency is #914 in Phase 2.6.

*Permission.* `sales.refund` through `check_permission_with_override` at the UI entry. The service also checks `AuthService.get_current_user()` has `sales.refund`, so the Documents path (#889) is covered too.

*Receipt.* The refund receipt lists the returned lines (name, qty, value), the reason, the tender breakdown ("Cash returned Rs X · Card reversal Rs Y · Credit reduced Rs Z") and the original receipt number. Extend `_build_refund_receipt` (`:589-610`).

*`process_refund` (legacy full refund)* = `RefundService.refund(sale_id, all remaining lines, reason)`. Remove its `except Exception: return False`: let `ValueError` propagate (#915).

**Implementation steps.**
1. Migration and model fields. Add the permission to constants, seeds and `create_empty_database`.
2. `refund_service.py`, with pure helpers (allocation, remainder rule) unit-tested separately.
3. Credit and loyalty services: explicit-amount parameters.
4. `TransactionService.process_refund`: delegate.
5. `RefundDialog` (`cbpos/ui/dialogs/refund_dialog.py`): rebuild as described in the UI spec.
6. Receipt builder for refunds.
7. Remove the `xfail` from #850's test.

**Tests (write first).** `tests/unit/test_refund_service.py`.
- `test_issue_812_partial_refund_one_line`: sale of A×2 (100 each) and B×1 (50), total 250. Refund A×1. Value 100.00, stock A +1, VAT proportional, `refund_state == "PARTIAL"`.
- `test_issue_812_cannot_refund_more_than_sold`: refund A×2, then A×1 → `qty_exceeds_remaining`.
- `test_issue_812_series_of_partials_reverses_sale_exactly`: a sale with a bill discount and a loyalty redemption giving an awkward total (e.g. 333.33); refund line by line. `Σ refund totals == total_amount`, and the same for VAT, SSCL and net, to the cent.
- `test_issue_812_tender_allocation_proportional`: Cash 600 + Credit 400; refund 300 → CASH −180, CREDIT −120, and debt falls by 120.
- `test_issue_812_override_to_cash_requires_reason_and_audits`.
- `test_issue_812_weighed_item_partial_qty`: 1.250 kg sold, 0.500 refunded.
- `test_issue_812_service_item_no_stock_movement`.
- `test_issue_812_legacy_full_refund_counts_as_full`.
- `test_issue_812_failure_midway_leaves_nothing`: monkeypatch the loyalty reversal to raise. No refund Sale, no stock movement, no ledger row.

**UI/UX spec — Refund dialog (the key surface; run the full §0.7 UI gate).** Model it on the Sale History master-detail layout (`sale_history_dialog.py`).

```
┌ Refund — INV-2026-00123 · 14 Oct 2026 · Nimal (077…) ────────────────────┐
│ Item                 Sold   Refunded   Return qty   Value     Reason     │
│ Anchor Milk 400g      2       0        [ 1   ]     Rs 100.00  [Damaged▾] │
│ Sugar (kg)          1.250     0        [0.500]     Rs  60.00  [       ▾] │
│ Bread                 1       1          —            —     (refunded)   │
│                                                                          │
│ Refund total  Rs 160.00   (VAT incl. Rs 24.41)                           │
│ Give back:  Cash Rs 96.00 · Credit book −Rs 64.00   [Change… (manager)]  │
│ Reason for refund: [__________________________]                          │
│                                     [Refund Rs 160.00]   [Cancel]        │
└──────────────────────────────────────────────────────────────────────────┘
```

- Columns: the Return qty spinbox is limited to `0..remaining`, with `decimals = 3` for weighed items and 0 otherwise. Fully refunded lines are disabled with a "(refunded)" tag.
- Buttons:
  - **Return all remaining** (Alt+A) fills every remaining qty.
  - The primary button shows the live amount, is disabled at 0, and needs a reason.
- Totals and the "Give back" line update live from `RefundService.preview` (a service call; cheap and synchronous is fine, since there's no heavy I/O).
- **Change…** opens a small override panel (Cash / Customer credit plus a reason). It is permission-gated: without permission it asks for override through the existing manager-override dialog.
- States:
  - loading the sale;
  - sale not found;
  - sale void ("This sale was voided and can't be refunded.");
  - already fully refunded ("Everything on this receipt has already been refunded." plus a list of the refund receipts);
  - success: a quiet toast or status message, the refund receipt prints (via the existing peripherals path), and the dialog closes.
- Keyboard: arrows move rows; typing a number sets the focused row's qty; Enter on the primary button refunds; Esc cancels.
- Copy (new keys, `refund.*`):
  - `refund.col_sold` "Sold", `refund.col_refunded` "Refunded", `refund.col_return_qty` "Return qty", `refund.col_value` "Value", `refund.col_reason` "Reason"
  - `refund.return_all` "Return all remaining"
  - `refund.total` "Refund total"
  - `refund.give_back` "Give back"
  - `refund.change_tender` "Change…"
  - `refund.tender_cash` "Cash"
  - `refund.tender_credit` "Credit book"
  - `refund.tender_card_note` "Reverse {amount} on the card machine"
  - `refund.reason_label` "Reason for refund"
  - `refund.primary` "Refund {amount}"
  - `refund.fully_refunded` "Everything on this receipt has already been refunded."
  - `refund.line_refunded` "(refunded)"
  - Reason presets: Damaged / Wrong item / Customer changed mind / Expired / Other. **Reuse the void-reason list if it fits**; otherwise use a small static translated list.
- si/ta: the table columns must not clip at 1366×768. Allow the table to scroll horizontally rather than shrink fonts.

**Do NOT.**
- Do not compute refund value from current product prices. Use the stored line values.
- Do not refund tax by recalculating at the current VAT rate.
- Do not let the UI compute allocations; it displays the service preview.
- Do not keep `except Exception: return False`.
- Do not break `TransactionService.process_refund`'s signature: callers and tests use it.

**Edge cases.**
- A sale total of 0 (100% discount): value 0. Allow a stock-only return; the tender allocation is empty.
- A customer since deleted or deactivated with a CREDIT share: still reverse it on their ledger.
- A refund on another terminal in LAN-sync mode: the refund document syncs. Note for Phase 2: `refund_of_item_id` must map across terminals (see #869). Add a TODO comment and a PROGRESS note.

**Acceptance criteria.**
- [ ] Choose lines and quantities (weighed included) with reasons. Stock RETURN movements are written, and tax is refunded proportionally.
- [ ] Several partial refunds per sale, capped at sold quantities. A full series reverses totals and taxes exactly.
- [ ] Refunds go to the original tenders proportionally. A manager can override to cash or credit with a reason, and it is audited.
- [ ] `sales.refund` is enforced in the service. The refund receipt lists the returned lines.
- [ ] Over-return is prevented, and tested.

**Verify.**
- Focused tests and the full suite.
- Manual: sell 3 lines (one weighed) with a bill discount, refund one line, then the rest, and check stock, the credit book, the shift summary and both receipts.

**Stop & Ask if.** Ask this before merging; build with the recommendation meanwhile:

QUESTION (#812): Should a partial refund's VAT be proportional to value (simple and exact over a full series), or computed only on the refunded lines' taxable share (exact per refund when a bill mixes VAT-exempt and taxable items)?
Context: sales don't store a per-line taxable/exempt flag until #797 (Phase 6.1). Proportional gives slightly wrong VAT on a single partial refund from a mixed bill, but the full series always nets to zero.
Options:
  A) Proportional now; switch to line-level once #797 stores the per-line flag. Small temporary error on mixed bills only.
  B) Block partial refunds on mixed taxable/exempt bills until #797 lands.
Recommendation: A, with a follow-up issue linked to #797 so Phase 6.1 updates `RefundService` tax allocation.

### #915 — Refunded sales still show "Completed" with an active Refund button

**Severity:** low · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (clarify, harden)

**Problem.** Nothing ever marks a sale as refunded. History shows a green "Completed" pill and an active Refund button. A retry ends in "unknown error" because the real reason is swallowed.

**Evidence and root cause.**
- No code assigns `"REFUNDED"`. UI checks at `sale_history_dialog.py:678,776` and `refund_dialog.py:229` test a status that never exists.
- `process_refund`'s `except Exception: return False` (`transaction_service.py:~775-777`).

**Fix design.**
- Use the **derived** state from `RefundService.refund_states(ids)` ("NONE" / "PARTIAL" / "FULL"). Don't add a stored status: reports filter on `status`, and adding "REFUNDED" would silently drop refunded sales from them.
- Every list showing sales (Sale History, History view, Documents view) fetches states in one batched call and:
  - shows a pill: **Refunded** (full) or **Part refunded** (partial), in the QSS `info` style;
  - Refund enabled only when the state is not FULL, the status is COMPLETED and it isn't a refund doc;
  - Void enabled only when the state is NONE and it isn't a refund doc (#847/#848).
- Remove the dead `"REFUNDED"` string checks.
- Errors: dialogs catch `ValueError` and show `translate_error(code)`.

**Tests.**
- `test_issue_915_process_refund_on_refunded_sale_raises`.
- `test_issue_915_refund_states_batched`: one query for many ids. Use SQLAlchemy event counting if the test suite has a helper (`graft grep "before_cursor_execute" --in tests`); otherwise skip the count assertion.
- pytest-qt: `test_issue_915_history_shows_refunded_pill_and_disables_refund`.

**UI/UX spec.**
- `history.pill_refunded` → "Refunded", `history.pill_part_refunded` → "Part refunded".
- Disabled-button tooltips:
  - `history.refund_disabled_full` → "Everything on this sale has been refunded."
  - `history.void_disabled_refunded` → "This sale has a refund, so it can't be voided."
  - `history.void_disabled_is_refund` → "Refunds can't be voided."
- Pill styles go in both QSS files, next to the existing status pills.
- Run the §0.7 UI gate on Sale History, the History view and the Documents view.

**Acceptance.**
- [ ] An already-refunded sale shows a Refunded marker, and Refund is disabled. A partial refund shows Part refunded, and Refund stays enabled.
- [ ] Retrying a refund shows the real reason.
- [ ] Void is disabled for refunded sales and for refund documents.

---

## Phase exit gate
- [ ] All 14 issues merged and **verified closed** with closing comments (§0.10). #832 and #922 checklists updated.
- [ ] Migrations (`payment_method_kind`, `refund_lines`) upgrade-tested on a seeded SQLite copy **and** a v1.3.0 DB. If PostgreSQL is available, run them there too; otherwise add "⚠️ PG verify" to PROGRESS.md.
- [ ] Invariant tests pass. Add one integration test, `tests/unit/test_money_invariants.py`, that runs a day: sales with change, a credit sale, a split payment, F12, a partial refund, a full refund, an adjustment. It then asserts invariants 1–7 from the phase brief.
- [ ] Full suite green once per batch, and `pre-commit` clean.
- [ ] Sync serializers carry `method_kind`, `tendered_amount`, `refund_of_item_id` and `refund_reason`, or a PROGRESS note hands this to Phase 2.4 explicitly.
- [ ] UI gate screenshots: Payment Methods type column, payment dialog credit section (attached and unattached), non-cash clamp note, Refund dialog (partial, full, already refunded, override), and history pills.
- [ ] Follow-ups filed: #812 line-level tax once #797 lands (if answer A), and the Phase 6 report TODO markers listed in the PR.
- [ ] PROGRESS.md updated.
