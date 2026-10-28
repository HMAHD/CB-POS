# Phase 10B — Shop Workflow Features (stock, catalog, POS) and the Feature-Flag Foundation

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> These are **product features** from market research (2026-10-21). The research itself says: *"Evidence is weak on direct owner voice, so validate with 5–10 real shop owners before building."* So **every feature here has a human gate**: before starting a batch, ask the owner (§0.5) whether to build it now, and confirm the MVP scope below. Build nothing the owner hasn't confirmed.
> Read each issue body (`gh issue view <n>`) for the user-facing design. This file adds the technical design, the corrections against the remediated codebase, and the guardrails. Verified against `origin/main` @ `4bcc837`; re-verify before editing.

## Phase brief

**Outcome:** shops of each type switch on only what they need. A grocery cashier never sees pharmacy screens. The validated features work with correct stock, money, tax, sync and audit.

**Depends on:** the public release gate; Phases 3A (refund engine), 4 (StockService single source, GRN service), 6 (tax snapshots), 2 (sync, read-only catalog on tills).

**Global rules for every feature in 10B and 10C:**
1. **Off by default.** Gate it with the `FeatureFlags` service from #942. When off, the UI is completely hidden: no dead buttons, no empty tabs. Add a test per feature that a fresh DB shows nothing.
2. **The cashier flow gains no steps** for shops that don't use a feature.
3. **Never compromise the invariants** of Phases 3A, 4 and 6. Every new stock path goes through `StockService.record_movement`, every money path through the payment kinds and ledgers, every refund through `RefundService`. The invariant test files (`test_money_invariants.py`, `test_stock_invariants.py`, `test_report_reconciliation.py`) get a scenario for each new feature.
4. **Catalog-type settings** (presets, units, deposit items) are catalog: read-only on tills (Phase 2 #869) and synced with tombstones (#871). Bump the sync protocol minor version for new synced tables.
5. Sinhala/Tamil text needs **native review**: put keys on the PROGRESS.md i18n review list unless you're sure (§0.12 P7). The issue bodies give draft labels; treat them as drafts.
6. Full §0.7 UI gate on every screen.

### Issues and batches

| Batch | Branch | Issue | Title | Size | Gate |
|---|---|---|---|---|---|
| 10B.0 | `feat/p10b-b0-feature-flags-presets` | #942 | Shop-type presets and feature flags (**foundation**) | M | human (preset matrix sign-off) |
| 10B.1 | `feat/p10b-b1-power-cut-autosave` | #932 | Power-cut autosave of the open bill | S | human (go/no-go) |
| 10B.2 | `feat/p10b-b2-price-board` | #931 | Price board for often-changing prices | S | human |
| 10B.3 | `feat/p10b-b3-unit-conversion` | #937 | Buy by box, sell by piece; ft/m/sqft | M | human |
| 10B.4 | `feat/p10b-b4-expiry-batches` | #926 | Expiry and batches with per-batch MRP | L | human |
| 10B.5 | `feat/p10b-b5-supplier-returns` | #930 | Supplier returns with debit note | M | human |
| 10B.6 | `feat/p10b-b6-variants-exchange` | #936 | Size/colour variants and exchange | L | human |
| 10B.7 | `feat/p10b-b7-deposits-empties` | #941 | Deposits and empties | S–M | human (weak evidence: confirm first) |
| — | — | #933 | Serial/IMEI capture | — | **Delivered by Phase 9 #823**. Here, only the GRN-side capture and preset wiring remain, if the owner still wants them (Stop & Ask) |

Order rationale: the foundation comes first; then small, high-value, low-risk items (autosave, price board); then units (needed by batches and the pharmacy preset); then batches, then supplier returns (which pair with batches); then the large clothing feature; then the weakest-evidence feature last.

---

## 10B.0 — #942 Shop-type presets and feature flags (foundation)

**Gate:** sign-off on the preset matrix in the issue body.

QUESTION (#942): Confirm the preset matrix as drafted in the issue (7 shop types × 11 features), and that the wizard step is "What kind of shop is this?", shown after shop info.
Recommendation: yes. Ship the flags and the wizard step now, even if features arrive later. Flags for features not yet built stay hidden on the Features page.

**Design:**
- **`FeatureFlags` service** (`cbpos/core/services/feature_flags.py`):
  - `is_on(name) -> bool`, `set(name, bool, user_id)` (audited, permission `settings.features`, new code with the guardrail rule), `apply_preset(shop_type, user_id)`;
  - the flag names are constants in `cbpos/core/constants/features.py`;
  - storage: **DB, not settings.json**, because flags must be shared across network-mode PCs and synced to tills. A `feature_flags(name PK, enabled, updated_at)` table, catalog-synced, read-only on tills.
- **The preset** sets flags and seeds units and categories (idempotently: skip existing names), using the units from the issue's matrix.
- **Wizard step** inside the Phase 1 Setup Wizard, after shop info: big icon tiles labelled in the chosen language (see the issue). Choosing one calls `apply_preset` after the DB exists. The PIN-ordering logic from #791 applies: the wizard only *collects* the choice, and DB setup applies it.
- **Settings → Features page:** one switch per **built** feature, each with a one-line explanation. A switch is hidden for any feature not yet implemented (a registry of implemented features in `features.py`).
- **Gating helper for the UI:** `feature_visible(name) -> bool`, which reads the service. Views call it, never ConfigService.

**Tests:**
- presets set exactly the matrix flags;
- apply is idempotent;
- tills can't change flags;
- a fresh DB with no preset has all flags off;
- an AST guardrail: no view reads `features.*` from ConfigService.

**Acceptance:** as in the issue body, plus flags stored in the DB and synced.

---

## 10B.1 — #932 Power-cut autosave of the open bill

**Design:**
- Reuse held bills. Phase 3B #804 gave them a v2 format with full fidelity. Add `SuspendedTransaction.is_autosave` (Boolean): one row per terminal, upserted.
- On every cart change, `CartAutosaveService.save(cart)` runs on a **debounced 1 s QTimer**, never on each keystroke. It writes in a short transaction (SQLite WAL makes this cheap; confirm WAL is on in `database.py`'s pragmas, which it is if `journal_mode=WAL` is set).
- On a completed sale, hold, or clear: delete the autosave row.
- **Startup:** if an autosave row exists for this terminal, then after login show "You had an unfinished bill (5 items, Rs 2,340). Continue or discard?" Continue = recall through the #804 path, including its notices.
- The flag: on for every preset? **Recommended:** default **on** for all shops once built (pure safety, no extra steps). → Stop & Ask to confirm.
- The startup integrity check the issue mentions: Phase 1 #833/#838 already fail closed; just reuse their messages.

**Tests:** autosave after a change (with a fake timer); recall after a simulated restart restores the lines; the row is deleted after the sale; one row per terminal.

## 10B.2 — #931 Price board

**Design:**
- `Product.price_changes_often` (Boolean, migration).
- A shortcut (propose a free key and add it to F1 help) opens `PriceBoardDialog`, a grid of only flagged products: name (receipt language), current price, new price. Tab/Enter moves down, and **Save** applies.
- Prices change through `PricingService` / `InventoryService.update_product` with the Phase 4 #862 optimistic check, with an audit row per change: `PRICE_CHANGE` with old → new, user. Permission `inventory.edit` (or `pricing.manage` from Phase 5).
- **Print shelf labels** for the changed items uses the Phase 8 #819 label path.
- "Change price for this sale only" already exists as the line price override with permission, so reuse it and don't build a second path.

**Tests:** only flagged items listed; save writes one audit per change; a stale edit is refused.

## 10B.3 — #937 Unit conversion

**Design:**
- `Product.purchase_unit_id` (FK units) and `Product.purchase_factor` (Numeric(10,3), base units per purchase unit, default 1).
- The GRN grid (Phase 4.3) accepts a quantity in purchase units and shows the base-unit equivalent. `GrnRequest` lines carry `purchase_qty` and `factor`. Stock is in base units: `record_movement(qty = purchase_qty × factor)`. AVCO cost per base unit = `unit_cost / factor`, using `round_money`.
- Sales stay in base units (3 decimals are already supported).
- Presets seed the units (#942).
- **Owner question:** sell in several units (sell a box *or* a piece at different prices)?

  Recommendation: not in the MVP. Only buy-unit vs sell-unit. Multi-unit selling is a follow-up.

**Tests:** a GRN of 2 boxes × 10 adds 20 base units; AVCO per piece is correct; the stock invariant holds.

## 10B.4 — #926 Expiry and batches with per-batch MRP

**Gate:** the largest feature here. Run a `/grill-with-docs` session with the owner on scope before designing (the pharmacy and grocery flows differ).

**Design sketch** (to confirm in the grilling):
- `ProductBatch(id, product_id, batch_no nullable, expiry_date nullable, mrp nullable, qty_on_hand Numeric(10,3), received_at, grn_line_id)`, plus `Product.tracks_batches` (Boolean).
- `StockMovement.batch_id` (nullable FK).
- `Product.stock_qty` stays the product total and the single source of the invariant. Add a new invariant: `Σ batch.qty_on_hand == product.stock_qty` for batch-tracked products.
- **GRN:** batch-tracked lines get an Expiry (MM/YY → last day of the month) field, a Batch field, and an MRP if it differs.
- **Sale:** FEFO (first expiry first out). The cart line carries `batch_id`, chosen silently. A picker appears **only** if the remaining batches have different MRPs. Selling across batches splits the line, one line per batch, so price and tax are exact.
- An expired batch scanned → a blocking prompt that needs a manager override (`check_permission_with_override`), audited.
- **Refund** (3A `RefundService`) returns stock to the **same** batch, using the line's `batch_id`.
- **Stock take** (Phase 4 #861) counts per batch for tracked products. That's a significant extension: Stop & Ask whether the MVP may count per product only and allocate any variance to the newest batch.
- Dashboard "Expiring in 30/60/90 days" with actions: Return to supplier (#930), Mark damaged (Phase 4 adjustment with reason EXPIRED), Discount (a line price override).
- **Tax:** per-batch MRP affects the line amount only, and the tax engine (Phase 6) works on line amounts. Nothing else changes.

**Do NOT:** make batch fields mandatory for all products (#943's do-not-build list, item 8); build an NMRA database (item 9).

**Tests:** FEFO choice; the split across batches; the expired block plus override; refund to the same batch; both stock invariants; GRN creates a batch.

## 10B.5 — #930 Supplier returns with a debit note

**Design:**
- `SupplierReturn(Document)` (JTI, numbering `SR-{Y}-{seq:05d}`, terminal-scoped as in Phase 2) with lines `(product_id, qty, unit_cost, batch_id nullable, reason)`.
- `PurchaseService.return_to_supplier(request)` in **one transaction**:
  - stock out via `record_movement("SUPPLIER_RETURN")` (add the type);
  - the supplier payable reduces through a `SupplierLedgerEntry` (DEBIT_NOTE) equal to Σ qty × unit_cost (ADR 0001; Phase 4 #920 rules: no clamping, so a negative payable means the supplier owes the shop);
  - audit.
- Unit cost defaults to the current AVCO and can be edited with permission. **Owner question:** credit at the AVCO or at the last GRN cost from this supplier? Recommendation: the last GRN cost from this supplier for that product when available (that's what the supplier will credit), with a fallback to AVCO.
- AVCO on return: removing stock at a cost different from AVCO changes the AVCO of the remaining stock. **Recommended:** don't recompute AVCO on returns (standard practice: issues and returns leave the unit cost unchanged). Write that in the design note and test it.
- **Debit note PDF:** A4, branding, the supplier, lines and total. Generated off the UI thread (Phase 7 pattern).
- Permission `purchase.return` (new; guardrail).

**Tests:** stock, payable, ledger and invariants; the batch path (if #926 is done); rollback on failure.

## 10B.6 — #936 Size/colour variants and exchange

**Gate:** a large clothing feature. Grill the owner on scope first.

**Design sketch:**
- Reuse `Product.parent_id` (it exists: `models/__init__.py`, check it's unused or compatible). A parent "style" product (not sellable, `is_active` for display only) has child SKUs per size × colour. Add the attribute columns `variant_size`, `variant_colour` (String(20)) on children.
- Product editor: a **variant grid** (sizes × colours with checkboxes) generates the children, with auto barcodes (reuse the barcode generation; `test_auto_generate_barcodes.py` exists), a price inherited from the parent unless overridden, and labels via #819.
- **Exchange** = a refund of item A plus a sale of item B in one flow:
  - an `ExchangeService` calls `RefundService.refund` (3A) and `TransactionService.process_sale` **in one DB transaction**, so either both commit or neither does. Check that both services can run within a caller's session (both take `session=` or have an internal variant). Refactor if needed, in the design note.
  - The difference: customer pays (payment dialog for the net) or receives (refund tender allocation per D5).
- Reports group by parent style when the flag is on (a Phase 6 report option).

**Tests:** the grid creates N children with unique barcodes; an exchange is atomic (failure injection); the difference is paid or refunded correctly; money and stock invariants hold.

## 10B.7 — #941 Deposits and empties

**Gate:** the evidence is weak. **Ask the owner first** whether to build it at all.

QUESTION (#941): Build deposits and empties (gas cylinders, bottles) now? Evidence is limited to one vendor.
Recommendation: park it in #943 unless a real shop asks for it.

If built:
- a deposit product (service-like, no tax: confirm with the accountant) linked by `Product.deposit_product_id`;
- the line toggle "Customer brings an empty" removes the deposit line;
- the empties count as a simple stock item.

## #933 — Serial/IMEI capture

Phase 9 #823 implements capture at sale and lookup. Here:
- (a) the phone-shop preset turns on the warranty feature flag (#942);
- (b) **GRN-side serial capture** was explicitly out of scope in #820 ("inbound serial inventory").

QUESTION (#933): Build inbound serial capture at GRN (serials tracked in stock), or close #933 as delivered by #823?
Recommendation: close as delivered. Inbound serial inventory is a large feature, and #820 excluded it deliberately.

---

## Phase exit gate
- [ ] Each issue is either built (merged and **verified closed**) or explicitly parked or closed by the owner's answer (recorded as a D-number), with #943 updated for parked items.
- [ ] Every feature hidden when its flag is off (tests), and presets verified.
- [ ] The invariant suites include each built feature's scenarios.
- [ ] i18n review list submitted for native review.
- [ ] UI gate screenshots for every new screen.
