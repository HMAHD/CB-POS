# Phase 9 — Warranty and Repairs (epic #820)

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> **How this phase works.** Epic #820 and its children #821–#830 are already full specifications: research, data model, integration points, acceptance criteria. **The issue bodies are the primary spec.** Read the epic body fully, then each child body fully, before its batch (`gh issue view <n> --comments`).
> This file adds what the issue bodies can't know: the changes Phases 1–8 made to the codebase, the corrections that follow, the gates, and the UI/UX bar. **Where this file and an issue body disagree, this file wins**, because it was written later, against the remediated design. If you find a disagreement this file doesn't cover, Stop & Ask.

## Phase brief

**Outcome (end state).** As stated in #820's goal and its definition of done:
- shops selling electronics, hardware and phones attach warranty policies, sell with per-unit warranties (optional serial/IMEI), and print them;
- they can look warranties up instantly, and run claims through to collection, with supplier RMAs and paid extended warranties;
- stock, money, sync and audit stay correct;
- the feature is invisible to shops that don't use it (off by default).

**Depends on.** The public release gate passed, or the owner explicitly pulls this phase earlier (Owner's call, RELEASE_PLAN.md §1.1). Specifically:
- Phase 3A: `RefundService` (partial refunds), `refunded_qty`, `method_kind`;
- Phase 2: catalog read-only on tills, tombstones, protocol versioning, `sync_terminals`;
- Phase 5: permission guardrail, reprint service;
- Phase 6: stored tax facts, `ProductService.display_name`;
- Phase 7: `job_result` ids, the raster wrap, the `choose_barcode` helper.

**Unblocks.** 10B #933 (serial/IMEI capture for phone shops) **is delivered by #823**. Close #933 as a duplicate when #823 merges, or reduce it to whatever #823 doesn't cover (Stop & Ask).

### Issues and batches

| Batch | Branch | Issue | Title | Size | Gate |
|---|---|---|---|---|---|
| 9.1 | `feat/p9-b1-warranty-policies` | #821 | W1: Policies and assignment | L | agent |
| 9.2 | `feat/p9-b2-per-unit-warranty` | #822 | W2: Per-unit warranty, void/refund cascade | L | agent |
| 9.3 | `feat/p9-b3-serial-capture-printing` | #823, #824 | W3: Serial/IMEI capture; W4: Printing | L | agent; legal text gate (below) |
| 9.4 | `feat/p9-b4-lookup-claims` | #825, #826 | W5: Lookup; W6: Claims | L | agent |
| 9.5 | `feat/p9-b5-claim-resolution-rma` | #827, #828 | W7: Replace/refund; W8: Supplier RMA | L | agent |
| 9.6 | `feat/p9-b6-extended-plans-reports` | #829, #830 | W9: Extended warranty; W10: Reports and reminders | L | agent |
| — | — | #820 | EPIC: closes when all children are closed and its definition of done passes | — | — |

**Every batch:** this is L-size feature work. Write a design note in the PR, run `/egm-review` (Goldfish) on it, then TDD. The full §0.7 UI gate applies to every new screen.

## What changed since the issues were written (apply these corrections)

| Issue text says | Do this instead | Why |
|---|---|---|
| Migration `down_revision d2b635fce696` (#821) | Use the current head (`uv run alembic heads`) | Many migrations landed in Phases 1–8 |
| Refund cascade in `process_refund` lines `:656-807` (#822) | Hook the cascade into **`RefundService.refund`** (Phase 3A, `cbpos/core/services/refund_service.py`). For **partial** refunds, cancel warranties **per unit**: refunding q units of a line cancels q ACTIVE warranties of that `sale_item_id`. Choose them by serial if the refund dialog lets the user pick serials (add that to the refund dialog when the line has serials), otherwise the highest unit index first | Phase 3A replaced whole-sale refunds with line and quantity refunds |
| "Full refund → CANCELLED; refunding a sale with an open claim is blocked" (#822/#826) | The open-claim guard applies **per unit**: refunding a unit that has an open claim is blocked; other units can be refunded | Same |
| W7 refund resolution: "single-unit sale → `process_refund`; multi-unit depends on #812, until then manual note" (#827) | #812 is done. **Always** resolve REFUNDED through `RefundService.refund(sale_id, [(sale_item_id, 1, reason)])` for the claimed unit, with the claim linked to the refund document. Delete the manual-note fallback | Phase 3A |
| W9: "refunding only the plan line depends on #812" (#829) | Plan lines are refundable like any line through `RefundService`. Refunding the base unit **also** cancels its plan warranty, and refunds the plan line only if the user includes it (the refund dialog suggests it) | Phase 3A |
| `StockMovement` type `WARRANTY` added to `stock_service.py:13-21` | Add it to `_VALID_MOVEMENT_TYPES`. Replacement stock out uses `record_movement(..., "WARRANTY")`. Never set `stock_qty` directly (Phase 4 invariant 1, and `test_stock_invariants.py` must still pass) | Phase 4 |
| Sync: "add tables to `sync_protocol.py:356-394`, `synced` column, `_TABLE_MODEL_MAP`" | As written, **plus**: bump `SYNC_PROTOCOL_VERSION` (minor). Policies are catalog, so they are read-only on tills (Phase 2 #869 guard via `require_catalog_writable()`) and get tombstones (#871's `before_flush` hook covers them if their table is in `CATALOG_TABLES`). Warranties and claims are transaction data with id mapping through `sync_id_map` **including `origin_db_instance_id`** (#866) | Phase 2 |
| Claim numbering "decide terminal scoping" (#826) | **Decided:** claims are terminal-scoped like sales (`_TERMINAL_SCOPED_TYPES`), with the Phase 2 full-ID prefix (#867) and the numeric sequence (#905) | Phase 2 |
| Permissions `warranty.*` | Add them to `Permissions`, the groups, seeds and `MANAGEMENT_TAB_PERMISSIONS`. The **permission guardrail test** (Phase 5 #894) requires each code to be checked somewhere, so wire each one in the same PR that adds it | Phase 5 |
| Printing via the receipt builders | Use `ProductService.display_name(product, lang)` (Phase 7 #805), the raster wrap for long si/ta lines (#877), and `choose_barcode` (#840) for claim-slip barcodes. Print jobs return `job_id`, and screens filter `job_result` by it (#842). Warranty card reprints go through the Phase 5 reprint service, so they are audited | Phases 5 and 7 |
| Report definitions | Use `cbpos/core/reports/sale_filters.py` (Phase 6) for any sale-based query, half-open date ranges (#912), `Decimal` only (guardrail), and `required_permission` on each report (#880) | Phases 5 and 6 |
| Tax on extended-warranty plans (#829) | A plan is a service product. Its tax follows its category flags (Phase 6 #797: VAT-exempt / SSCL-exempt). Don't special-case it | Phase 6 |

## Gates and pre-written questions

1. **Legal wording (#824 printing, and any terms text).** The epic warns that the CAA Act text came from a transcription. Printed legal text must be verified against the official Act (documents.gov.lk / caa.gov.lk) **before** release.
   - Build with an owner-editable terms field per policy (from #821).
   - Ship one fixed statutory line only after verification.

   QUESTION (#824): Print a fixed line such as "This warranty is in addition to your rights under the Consumer Affairs Authority Act No. 9 of 2003" on warranty cards?
   Recommendation: yes, once the Act text is verified by the owner or a lawyer. It's required in spirit by s.31(g)/s.32. Until verified, print no statutory line.
2. **#933 overlap.** When #823 merges, compare #933's body with what #823 delivered. Close #933 with a comment, or narrow it (Stop & Ask if it's unclear).
3. **Off by default.** Every warranty UI element (product-editor tab, side-menu entry, Management tab, checkout prompts) is hidden until Settings → System → "Warranty & repairs" is on, or a policy exists (#820 principle). Add a single `WarrantyService.is_enabled()` and use it everywhere. A test asserts that a fresh DB shows none of it.

## UI/UX bar for this phase

These screens are used at a counter with a customer waiting, often by staff with little training:
- **Lookup (#825)** is reachable in two keystrokes from the sales screen (side menu, plus a shortcut; propose a free key and add it to F1 help). One search box accepts receipt number, serial or IMEI, phone, or name, and auto-detects which. A scan works straight into it (#841 scanner fixes).
- **Claims board (#826)** is a master-detail layout (Sale History pattern), with status columns or filters, a big claim number, and a timeline in the detail pane. Each state has one clear next action.
- **Serial prompt (#823)** handles one serial per unit with scan-to-fill, shows a duplicate-in-this-sale warning, and supports Esc to skip when the serial is optional. Required serials block payment with a clear message naming the item.
- **Warranty card (#824)** is printed in the receipt language with shop branding, the CB POS footer, coverage dates and the serial. It's tested on 58 mm and 80 mm (⚠️ Verify on Windows).
- Run the full §0.7 UI gate (critique → audit → harden → clarify → polish, keyboard-only walkthrough, screenshots in both themes and si/ta) on every new screen.

## Batch notes (beyond the issue bodies)

**9.1 #821.**
- Policies are catalog. Edits are allowed on the Main PC or standalone only.
- Durations are calendar-aware (months and years via `dateutil.relativedelta`; check it's a dependency, otherwise implement month arithmetic in `cbpos/core/utils/dates.py` with tests for Jan 31 + 1 month).
- Policy names and terms are trilingual fields, falling back to English.

**9.2 #822.**
- Fractional quantity on warranty products is refused (as written).
- Warranty codes `<doc no>-01..NN` use the **full** document number (with the Phase 2 prefix).
- Add a test: refund 1 of 3 units cancels exactly 1 warranty.

**9.3 #823/#824.**
- The serial uniqueness rule: warn, don't block, when the same serial was sold before on an ACTIVE warranty. That can be a legitimate resale, but it's flagged. **Stop & Ask** if the owner wants a hard block.

**9.4 #825/#826.**
- Claims are a `Document` subclass (JTI) as the epic says. Voiding a claim needs a permission and a reason (Phase 5 patterns).
- One open claim per warranty is enforced in the **service** and by a partial unique index (PostgreSQL) or a check in the service under a row lock (SQLite).

**9.5 #827/#828.**
- Replacement is one transaction:
  1. stock −1 (WARRANTY) for the new unit;
  2. the old warranty REPLACED;
  3. a new warranty with remaining or fresh coverage per the policy;
  4. the claim RESOLVED.

  A failure-injection test proves it's all-or-nothing.
- RMA costs are `Decimal`, and supplier credit notes from an RMA go through `SupplierPayableService` ledger rows (ADR 0001; Phase 4 #920 rules).

**9.6 #829/#830.**
- Reminders are in-app only: dashboard tiles and a list with copy-able text. SMS and WhatsApp sending are out of scope (#820), and are Phase 10C (#927, #934).
- Report queries follow Phase 6 rules.

## Phase exit gate
- [ ] #821–#830 merged and **verified closed** with closing comments. #820 closed with a summary comment (§0.10). #933 resolved (closed or narrowed).
- [ ] The epic's definition of done passes:
  - pre-commit and the full suite are green;
  - the demo seed has warranty products, sales with warranties and two claims;
  - `graphify update .` has been run.
- [ ] Money and stock invariant tests from Phases 3A and 4 still pass with warranty flows added. Add warranty steps to `test_money_invariants.py` and `test_stock_invariants.py`.
- [ ] Two-machine sync test: a policy on the Main PC reaches the till; a till sale with warranties and a claim reaches the Main PC; no id collisions.
- [ ] A fresh DB shows no warranty UI until it is enabled.
- [ ] Legal-text gate answered (Q above), and printed samples photographed (⚠️ Verify on Windows).
- [ ] PROGRESS.md updated.
