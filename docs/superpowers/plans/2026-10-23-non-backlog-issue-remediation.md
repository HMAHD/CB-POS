# Non-Backlog Issue Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix and verify every open CB-POS GitHub issue that is not labelled `backlog`, while preserving data, accounting integrity, security, hardware compatibility, and release compliance.

**Architecture:** Work is split into independently mergeable PR batches ordered by destructive-risk and shared dependencies. Each issue body is the authoritative behavioral specification; fixes belong at the narrowest responsible service or infrastructure boundary, with UI code limited to presentation and signal handling. Database, tax, payment, inventory, and sync changes are proven with regression tests before their implementation is accepted.

**Tech Stack:** Python 3.12+, PyQt6, SQLAlchemy 2.0, Alembic, SQLite, PostgreSQL, pytest, Ruff, ESC/POS, ReportLab, Inno Setup.

**Spec:** GitHub issues in `HMAHD/CB-POS`, especially tracking epics #832 and #922 and warranty epic #820. Human decisions are locked in this document.

## Global Constraints

- Scope snapshot on 2026-10-23: 155 open issues, 23 backlog, 132 non-backlog, comprising 3 tracking epics and 129 actionable issues.
- Exclude every issue carrying `backlog`; #815 was explicitly moved to backlog because paid code signing is not currently viable.
- Never use `float` for money; use `Decimal` and the approved `ROUND_HALF_UP` money helper.
- UI views and dialogs must not access the database directly; business rules and persistence remain in services.
- Every critical state change requires permission enforcement and an `AuditLog` entry.
- Every schema change requires an Alembic migration, upgrade coverage, and rollback/recovery notes.
- All user-facing copy must use i18n keys present in English, Sinhala, and Tamil.
- Never perform blocking database, printing, email, PDF, bcrypt, or network work on the Qt UI thread.
- Do not close an issue until its body’s acceptance checklist and the verification gates below pass.
- Do not close an epic until every included child issue is closed or explicitly moved to backlog by the owner.
- Update `graphify` after code changes.

## Review Focus

- Existing shops upgrading across multiple historical schema versions must retain all data and either migrate successfully or stop before mutation.
- Two tills acting on the same sale, catalog row, sequence, or shift must not duplicate money, stock, identifiers, or permissions.
- Refund, void, discount, credit, loyalty, tax, and cash calculations must reconcile to stored ledger and stock movements after partial failure.
- Hardware and multilingual output must degrade with an explicit error, never false success, UI freezing, truncation, or a process abort.
- A failed or interrupted operation must leave retryable state, no orphan documents, and enough audit evidence to explain the outcome.

---

## Locked Human Decisions

1. **#731 — Full printer verification:** Test on Windows with real thermal and A4 printers plus Microsoft Print to PDF.
2. **#799 — Fully support PostgreSQL network mode:** Connection and migration belong in one guided Network Setup flow. After a successful connection, an administrator on the designated Main PC may run Alembic; tills never migrate and block on schema mismatch with “Main PC update required.”
3. **#800 — Verified first connection:** Display the Main PC certificate fingerprint on both systems, require the user to confirm a match, persist the pin, and block/audit later certificate changes.
4. **#810 — `ROUND_HALF_UP`:** One explicit money-rounding helper governs currency, taxes, AVCO, and totals; calculate rounded net as total minus rounded VAT and SSCL.
5. **#812 — Partial refunds:** Allocate to original tenders proportionally by default. A permitted manager may override to cash or customer credit only with a reason and audit entry.
6. **#814 — Full tax-invoice compliance:** Verify against official IRD/Gazette sources; implement the mandated serial and fields, amount in words where required, and `ORIGINAL`/`COPY ONLY`; retain ordinary retail receipts as a separate document type.
7. **#815 — Backlog:** Defer installer architecture, paid signing, and portable packaging. The issue is labelled `backlog` and excluded from this plan.
8. **#817 — GPLv3 distribution:** Keep PyQt6, distribute CB-POS and corresponding source under GPLv3, and add privacy and third-party notices. Obtain legal review before public release.
9. **#831 — Independent SSCL model:** `sscl_registered` is independent of VAT; support Retail/Manufacturer/Distributor turnover presets; model SSCL exemptions separately; remove SSCL from customer receipts and retain liability reporting.
10. **#878 — CODE128:** Use `{B}` and calculated dimensions that fit the longest allowed document number on both 58 mm and 80 mm paper.
11. **#914 — Database-enforced concurrency:** Use PostgreSQL row locking plus a partial unique index, proven with two concurrent database connections.
12. **#918 — Remove every forbidden Qt destruction hook:** Use `call_on_destroyed` or owner-bound callbacks, remove redundant cleanup hooks, and add a guardrail test.

## Required Skill Routing

| Work type | Required workflow |
|---|---|
| Bug or failing test | `systematic-debugging` → `test-driven-development` → `surgical-patch` |
| Schema, data, or protocol transition | `migration` in addition to the bug workflow |
| Behavior-preserving structural change | `safe-refactor` with before/after verification |
| PyQt UI, threading, or lifecycle | `pyqt6-ui-development-rules`; use `impeccable` only when visual design judgment is required |
| Tax, legal, licensing, or framework facts | `research`, restricted to current primary/official sources where available |
| Each completed PR batch | `verification-before-completion` → `requesting-code-review` |
| Whole-program execution | `subagent-driven-development` is recommended because batches are separable and financial mistakes have high cost |

## Execution Rules for Every PR Batch

- [ ] Read every included issue body and discussion; copy its acceptance criteria into the PR checklist.
- [ ] Reproduce or prove the root cause against current `HEAD`; if current behavior contradicts the issue, document evidence before changing code.
- [ ] Write the smallest regression test that fails for the stated root cause.
- [ ] Run that test and record the expected failure.
- [ ] Implement only the narrowest root-cause fix; do not bundle unrelated cleanup.
- [ ] Run the focused test and affected subsystem suite.
- [ ] Run `uv run pre-commit run --all-files`.
- [ ] Run `QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/unit/ -q -n auto`.
- [ ] Run `graphify update .` and inspect the resulting diff for accidental generated churn.
- [ ] Perform any issue-specific PostgreSQL, Windows, printer, legal, or manual acceptance checks.
- [ ] Review the diff against every included issue checklist, then create one focused PR linking the issues.
- [ ] Close issues only after CI and required manual gates are green.

---

## Phase 1 — Destructive Safety, Authentication, and Recovery

**Outcome:** A fresh install, login, manager override, logout, upgrade, backup, and restore cannot silently expose privileged access or destroy/overwrite shop data. Every batch is independently releasable.

### Batch 1.1: Setup and destructive-operation safety

**Issues:** #791, #833

**Primary files:** `main.py`, `cbpos/core/services/database_setup_service.py`, `cbpos/ui/dialogs/setup_wizard.py`, setup-related unit tests.

- [ ] Prove database errors are distinct from an actually uninitialized database and make destructive demo loading require a positively identified empty target.
- [ ] Restore first-run wizard routing and apply the chosen administrator PIN atomically during database creation.
- [ ] Test unreadable/corrupt/live databases, cancelled setup, fresh setup, and demo setup without allowing `drop_all` on ambiguous state.

### Batch 1.2: Authentication and session ownership

**Issues:** #835, #856, #857, #859, #860

**Primary files:** authentication/user services, permission override helper, login/main-window/session-watchdog UI, user-management tests.

- [ ] Separate temporary manager authorization from the authenticated cashier identity.
- [ ] Enforce unique PIN ownership and the existing lockout policy on the real login path.
- [ ] Prevent deactivation or demotion of the last active administrator.
- [ ] Make logout and timeout close dialogs, clear carts, and clear `AuthService` state before returning to login.

### Batch 1.3: Migration, settings, backup, and restore safety

**Issues:** #837, #838, #839, #873, #874, #875

**Primary files:** `main.py`, `cbpos/core/database.py`, config/backup/restore/migration services, Data Safety UI, Alembic tests.

- [ ] Replace “stamp missing schema at head” with evidence-based baseline detection and real migration execution.
- [ ] Quarantine corrupt settings instead of silently overwriting them; preserve network and tax configuration.
- [ ] Make network-mode backup/restore/maintenance operate on PostgreSQL or explicitly refuse unsupported actions without claiming success.
- [ ] Validate backup app/schema compatibility before mutation and restore the safety snapshot on failure.
- [ ] Restart/reload through one controlled restore boundary so stale settings or engines cannot overwrite restored state.
- [ ] Re-encrypt restored secrets exactly once with the destination installation key.

---

## Phase 2 — PostgreSQL and Multi-Terminal Correctness

**Outcome:** Supported network mode migrates safely, authenticates the intended server, synchronizes authoritative data, survives failures visibly, and prevents cross-terminal collisions.

### Batch 2.1: Guided PostgreSQL connection and schema ownership

**Issues:** #799, #904

- [ ] Combine connection testing, schema inspection, and administrator-controlled migration in the Network Setup UI.
- [ ] Designate the Main PC as migration owner; block tills when server schema and application revisions differ.
- [ ] Run Alembic against the selected PostgreSQL URI with an advisory migration lock and PostgreSQL CI coverage.
- [ ] Refactor `Database.get_session()` so retry creates a new context attempt rather than yielding twice.

### Batch 2.2: Pinned TLS pairing

**Issues:** #800

- [ ] Display one normalized SHA-256 certificate fingerprint on the Main PC and terminal.
- [ ] Require explicit first-pair confirmation, persist the pin securely, and block/audit mismatch without transmitting the sync token.
- [ ] Test first pairing, matching reconnect, certificate rotation, mismatch, cancellation, and unreachable server.

### Batch 2.3: Terminal identity and collision-proof synchronization

**Issues:** #866–#869

- [ ] Give each installation an immutable generated identity distinct from the human-readable terminal name.
- [ ] Prevent duplicate active terminal registration and make reinstall/restore recovery explicit rather than overwriting history.
- [ ] Replace cross-database integer-ID assumptions with stable sync identities/mappings for till-created rows.
- [ ] Serialize promotion daily time windows in the protocol without breaking the catalog batch.

### Batch 2.4: Catalog, deletion, and permission synchronization

**Issues:** #836, #871, #872, #903

- [ ] Make optimistic-version fields merge correctly for Main-PC product edits.
- [ ] Represent deletions/tombstones so removed promotions, price overrides, and payment methods stop applying.
- [ ] Synchronize role-permission membership and invalidate terminal authorization caches.
- [ ] Include audit and inventory logs in an idempotent, bounded sync stream.

### Batch 2.5: Server resilience, numbering, and honest status

**Issues:** #870, #905, #906

- [ ] Add authenticated connection timeouts/concurrency so one idle socket cannot block the server.
- [ ] Allocate document sequences numerically and atomically across formatting boundaries.
- [ ] Surface pending/failing pushes and server startup errors; emit “Synced” only after confirmed bidirectional completion.

### Batch 2.6: Network-aware shifts, dashboards, and transaction serialization

**Issues:** #884, #886, #914

- [ ] Scope shifts by terminal/session identity rather than cashier alone.
- [ ] Replace SQLite-only date grouping with SQLAlchemy/PostgreSQL-compatible expressions.
- [ ] Lock original sales for void/refund and add the approved partial unique index; prove the loser observes the winner’s committed state.

---

## Phase 3 — Checkout, Payment, Refund, and Ledger Integrity

**Outcome:** All sale state transitions preserve money, stock, customer debt, loyalty, shift cash, and audit invariants, including retries and partial failures.

### Batch 3.1: Shift cash and payment-method identity

**Issues:** #834, #850, #854

- [ ] Store/count net cash received rather than tendered cash when change is returned.
- [ ] Subtract cash actually returned by refunds from the originating shift/terminal totals.
- [ ] Resolve Quick Pay through the configured `PaymentMethod` identity and `is_cash`, never a magic string.

### Batch 3.2: Credit payments and customer ledgers

**Issues:** #849, #851, #852, #887, #888

- [ ] Reject non-cash over-tender and cap debt effects at the bill allocation.
- [ ] Bind credit strictly to the sale’s selected customer.
- [ ] Write one ledger entry per credit allocation or a correctly summed entry with traceable payment references.
- [ ] Preserve negative balances as store credit and make every balance adjustment equal the ledger delta.
- [ ] Refund only the debt created by the returned value, never prior or unrelated customer debt.

### Batch 3.3: Refund and void state machine

**Issues:** #812, #847, #848, #915

- [ ] Implement line/quantity refund allocation, cumulative caps, proportional tax, stock returns, reasons, and receipt output.
- [ ] Allocate refunds proportionally to original tenders; allow audited manager override to cash or customer credit.
- [ ] Forbid voiding an already-refunded sale and voiding a credit note through the sale-void path.
- [ ] Derive display status and available actions from refund state so completed/refunded labels cannot disagree.

### Batch 3.4: Cart and checkout failure integrity

**Issues:** #801, #804, #853, #892, #913

- [ ] Use the canonical loyalty minimum-redemption key.
- [ ] Snapshot and restore held-bill discounts, overrides, notes, customer, and loyalty state.
- [ ] Clear or roll back redemption state after failed sales and write ledger deltas equal to clamped point changes.
- [ ] Propagate typed service errors to translated actionable UI messages; never silently return `None`.

### Batch 3.5: POS rules and operator controls

**Issues:** #792, #793, #813, #855, #890, #891, #916

- [ ] Connect email receipt to a real service method with background execution and explicit failure reporting.
- [ ] Make drawer opening functional under default settings and permission/audit gated.
- [ ] Add bill-level percentage/amount discounts through existing authorization and Decimal calculation paths.
- [ ] Exempt service products from physical stock availability checks without affecting stock-tracked products.
- [ ] Suppress global scanner routing while a modal owns input.
- [ ] Revalidate fixed discounts after quantity changes and require authorization above the configured cap.
- [ ] Quantize percentage promotion unit/line values so persisted multiplication reconciles exactly.

---

## Phase 4 — Inventory, Purchasing, and Import Integrity

**Outcome:** Inventory mutations are concurrent-safe, fully recorded, validated, and visible across catalogs larger than 1,000 items.

### Batch 4.1: Stock adjustment, take, and product concurrency

**Issues:** #794, #861, #862, #863

- [ ] Expose one permission-gated stock-adjustment flow that always writes `StockMovement`.
- [ ] Apply physical counts against current stock under optimistic locking rather than a stale loaded delta.
- [ ] Prevent product metadata saves from overwriting current stock/cost and enforce `version_id` on the actual update path.
- [ ] Replace the inventory hard cap with paged/searchable server-side retrieval.

### Batch 4.2: Reorder and CSV correctness

**Issues:** #864, #865, #900, #901

- [ ] Base reorder purchase-order supplier selection on the product’s maintained default supplier, with an explicit missing-supplier workflow.
- [ ] Map CSV columns by normalized exact aliases, detect ambiguity, and preview the mapping.
- [ ] Read user-selected USB/other-drive paths and supported UTF-8/ANSI encodings with visible row-level errors.
- [ ] Reject negative selling price, cost, and opening stock before any row is committed.

### Batch 4.3: GRN transactional integrity

**Issues:** #895, #899, #902, #919

- [ ] Persist the entered GRN date and use it for the correct accounting/tax period.
- [ ] Define and test the AVCO rule when receipts cover negative stock using Decimal arithmetic.
- [ ] Make identity cells non-editable, validate positive quantity/cost, and calculate totals from committed grid values.
- [ ] Create/number the GRN inside the committing transaction or cleanly roll back draft and sequence state on failure.

### Batch 4.4: Supplier and category consistency

**Issues:** #920, #921

- [ ] Write supplier adjustment ledger rows using the actual clamped balance delta.
- [ ] Render/search the complete category hierarchy recursively without dropping deeper descendants.

---

## Phase 5 — Permission, Audit, Export, and Qt Security

**Outcome:** Every exposed privileged action is enforced at its service boundary, every sensitive export is inert, and Qt cleanup follows the repository’s crash-safe lifecycle rule.

### Batch 5.1: Permission model repair

**Issues:** #858, #880, #889, #893, #894, #896

- [ ] Assign Stock Take, Price Lists, and Promotions dedicated least-privilege permissions rather than `admin.manage_users`.
- [ ] Enforce sales/profit/report-export permissions for view, email, print, and export entry points.
- [ ] Enforce `sales.refund` from every navigation path.
- [ ] Treat quantity reduction as a permission/audit-sensitive removal.
- [ ] Either enforce every displayed permission or remove it from the permission catalog; cover CSV, category, and unit editing.
- [ ] Enforce `purchase.create_grn` at the service boundary and UI affordance.

### Batch 5.2: Secret and spreadsheet safety

**Issues:** #809, #898

- [ ] Generate a cryptographically random encryption key and provide a safe migration path for legacy hostname-derived keys.
- [ ] Escape formula-leading cells in every spreadsheet/CSV export while preserving ordinary text.

### Batch 5.3: Reprint authorization and document truth

**Issues:** #911

- [ ] Permission/audit gate reprints and render void/refund document types and duplicate markers truthfully instead of “Cash Receipt.”

### Batch 5.4: Authentication performance and Qt lifecycle guardrails

**Issues:** #917, #918

- [ ] Replace per-user bcrypt scanning with a lookup/authentication design that preserves PIN secrecy and does not block the UI thread.
- [ ] Replace all direct `destroyed.connect(...)` uses outside `destroy_hooks.py`, owner-bind translation callbacks, remove redundant cleanup, and add static guardrail tests.

---

## Phase 6 — Tax, Reports, and Accounting Truth

**Outcome:** Historical reports derive from stored transaction facts, exclude voided activity correctly, include refunds correctly, and implement approved Sri Lankan tax rules.

### Batch 6.1: Tax calculation and stored facts

**Issues:** #797, #810, #831

- [ ] Add configurable tax-exempt category behavior and snapshot taxable/exempt splits on each sale.
- [ ] Introduce the approved `ROUND_HALF_UP` helper and reconcile rounded components to the total; accept two-decimal VAT rates.
- [ ] Add independent SSCL registration, turnover presets, and exemption classification; remove SSCL from customer receipts.

### Batch 6.2: Tax reporting and compliant invoice history

**Issues:** #795, #796, #811

- [ ] Exclude voided sales and render tax headers from stored/configured rates rather than hard-coded labels.
- [ ] Wire the filing period and use stored discounts plus VAT-exclusive liable turnover and configured SSCL percentage.
- [ ] Reprint the tax rate and tax facts stored with the original invoice, not current settings.

### Batch 6.3: Profit, cash, and sales report semantics

**Issues:** #798, #802, #843–#845

- [ ] Calculate profit from VAT-exclusive stored revenue and sale-time cost snapshots using Decimal.
- [ ] Identify payment methods by stable identity/capability rather than display names.
- [ ] Include refunds in the void/refund report, subtract them once in cash flow, and exclude voided sales from every sales/dashboard/email aggregate.

### Batch 6.4: Aging, historical statements, and category/stock coverage

**Issues:** #883, #885, #897, #907, #909, #910, #912

- [ ] Base customer/supplier aging on the oldest outstanding allocation, not the newest ledger activity.
- [ ] Use `PaymentMethod.is_cash` for expected cash.
- [ ] Compute historical statement opening and closing balances at the requested boundaries.
- [ ] Exclude services/bundles from low-stock metrics unless they actually track stock.
- [ ] Include uncategorized products as an explicit report bucket.
- [ ] Use half-open date ranges `[start, next_day)` so the final second/microseconds are never dropped.

---

## Phase 7 — Printing, Scanning, PDF, i18n, and UI Concurrency

**Outcome:** Output is responsive, truthful, multilingual, and proven on supported Windows hardware without duplicated input or lifecycle crashes.

### Batch 7.1: Printer selection and output transport

**Issues:** #731, #803, #876

- [ ] Respect the configured A4 printer and validate real Windows printer/8.3 names without discarding PowerShell diagnostics.
- [ ] Keep expensive document construction off the UI thread and prove final printing behavior using the full #731 Windows matrix.

### Batch 7.2: Thermal barcodes and receipt layout

**Issues:** #840, #877, #878, #908

- [ ] Use valid CODE128 `{B}` data for product and invoice barcodes.
- [ ] Calculate barcode size against 58 mm/80 mm dot widths and maximum document length.
- [ ] Wrap shaped Sinhala/Tamil shop, customer, and item text within paper width.
- [ ] Merge receipt lines using reconciled weighted unit/line totals and savings rather than the first line’s price.

### Batch 7.3: Scanner, signal, and dashboard lifecycle

**Issues:** #841, #842, #846

- [ ] Consume each scanner key once at the application boundary, independent of widget propagation.
- [ ] Disconnect/ownership-scope print and drawer signals when the Documents view is hidden or destroyed.
- [ ] Give dashboard loads one owned worker lifecycle; cancel or ignore stale results before re-show/destruction.

### Batch 7.4: Multilingual receipt and PDF output

**Issues:** #805–#807, #879

- [ ] Resolve item names in the selected receipt language with defined fallback.
- [ ] Replace the unshaped report PDF path with direct ReportLab Platypus plus shaped Noto fonts, sharing approved font primitives without scheduling backlog work.
- [ ] Add missing translations and route crash/email text through i18n.
- [ ] Generate A4 invoices outside the UI thread and deliver completion/error signals safely.

---

## Phase 8 — Release, Legal, Update, Export, and Documentation

**Outcome:** Public claims match shipped behavior, licensing and privacy obligations are visible, updates are controllable, and scheduled/export work is reliable.

### Batch 8.1: Update and external-path behavior

**Issues:** #808, #881, #882

- [ ] Add an update-check opt-out, enforce `min_version`, and parse/display release changelog content.
- [ ] Permit explicit user-selected export destinations including removable/other drives without weakening path validation elsewhere.
- [ ] Make scheduled email jobs single-flight with recorded attempt/success/failure state and bounded retry timing.

### Batch 8.2: Verified tax-invoice format

**Issues:** #814

- [ ] Use `research` to capture current official IRD/Gazette requirements in a repository research note before implementation.
- [ ] Implement the mandated serial/fields, amount in words where required, and original/copy lifecycle without changing ordinary retail receipts into tax invoices.
- [ ] Add retention/reprint tests and obtain accountant confirmation before closing.

### Batch 8.3: GPL, privacy, notices, and About surface

**Issues:** #816, #817

- [ ] Add GPLv3 licensing and corresponding-source release instructions compatible with PyQt6 distribution.
- [ ] Generate third-party notices from the locked dependency set and bundle them.
- [ ] Add a privacy notice covering update checks, SMTP, LAN sync, and PostgreSQL.
- [ ] Expose version, licence, privacy, help, website, and issue-report links in About using CB POS branding.

### Batch 8.4: Documentation and product-label truth

**Issues:** #818, #819

- [ ] Correct SSCL documentation to VAT-exclusive turnover and reconcile every audited documentation claim with code.
- [ ] Use localized product names, real barcode data in preview, and explicit supported label-size settings.

---

## Phase 9 — Warranty and Repairs

**Outcome:** Deliver warranty work only after core sale/refund, stock, tax, sync, printing, and permission invariants are stable. Follow epic #820’s schema and acceptance specification without expanding into its stated out-of-scope features.

### Batch 9.1: Warranty policy foundation

**Issues:** #821

- [ ] Implement policy/category/product assignment, calendar-aware duration, migrations, permissions, sync, setup defaults, seed data, and trilingual UI.

### Batch 9.2: Per-unit sale warranties

**Issues:** #822

- [ ] Snapshot one warranty per sold unit inside the sale transaction and cascade sale void/refund atomically.

### Batch 9.3: Serial capture and printing

**Issues:** #823, #824

- [ ] Capture optional/required serial or IMEI values without creating inbound serial inventory.
- [ ] Print snapshotted coverage on thermal receipts, tax invoices, and standalone warranty cards.

### Batch 9.4: Lookup and claim lifecycle

**Issues:** #825, #826

- [ ] Implement indexed lookup by receipt, serial, phone, and customer.
- [ ] Implement the audited claim/event state machine with permissions, numbering, sync, and trilingual UI.

### Batch 9.5: Claim resolutions and supplier RMA

**Issues:** #827, #828

- [ ] Use the completed #812 partial-refund service and stock movements for replacement/refund resolutions.
- [ ] Track supplier dispatch, return, reference, outcome, and costs without weakening the customer-facing claim lifecycle.

### Batch 9.6: Extended plans and reporting

**Issues:** #829, #830

- [ ] Sell extended warranty as a service SKU linked to the covered sale line and snapshotted policy.
- [ ] Add active/expiring/claim/RMA reports and reminders through the existing report and scheduler boundaries.

---

## Dependency and Release Order

```text
Phase 1 safety/auth/recovery
        |
        +--> Phase 2 network foundation --------+
        |                                       |
        +--> Phase 3 POS/refund/ledger ----+     |
        |                                  |     |
        +--> Phase 4 inventory/purchase ---+-----+
        |                                  |
        +--> Phase 5 permission/security --+
                                           |
                                           v
                                  Phase 6 tax/reports
                                           |
                         +-----------------+-----------------+
                         v                                   v
                 Phase 7 hardware/i18n              Phase 8 release/legal
                         |                                   |
                         +-----------------+-----------------+
                                           v
                                  Public release gate
                                           |
                                           v
                                  Phase 9 warranty epic
```

- Phases 2–5 may proceed as separate branches after the specific Phase 1 foundation they consume is merged.
- Phase 6 follows stable transaction semantics from Phases 3 and 4.
- Phase 7 hardware checks use stable receipt/report semantics from Phases 3 and 6.
- Phase 8 documentation and public claims are finalized only after shipped behavior is known.
- Warranty #827 requires #812; the complete warranty epic follows the public-release remediation unless the owner explicitly reprioritizes it.

## Final Verification and Epic Closure

- [ ] Refresh the GitHub inventory and prove there are zero open actionable issues without `backlog` other than approved tracking epics awaiting final closure.
- [ ] Run the full pre-commit and unit-test commands from a clean worktree.
- [ ] Run PostgreSQL migrations from every supported historical release fixture and run multi-terminal concurrency/sync tests.
- [ ] Complete Windows installer smoke testing without claiming signed distribution; #815 remains visibly backlog.
- [ ] Complete #731/#878 real 58 mm, 80 mm, A4, and Print-to-PDF checks.
- [ ] Obtain accountant confirmation for #810, #814, and #831 and legal confirmation for #817.
- [ ] Validate English, Sinhala, and Tamil receipt/PDF paths on Windows.
- [ ] Verify backup/restore round trips for SQLite and PostgreSQL with encrypted settings.
- [ ] Update release notes and public documentation to describe only verified behavior.
- [ ] Close #922 and #832 after all included non-backlog children are closed.
- [ ] Close #820 only after #821–#830 are closed.

## Rollback Policy

- Code-only PRs revert normally while preserving forward-compatible data.
- Schema PRs include downgrade/recovery instructions and a pre-upgrade backup; never depend on destructive downgrade for user recovery.
- Sync protocol transitions remain version-gated until all connected terminals upgrade; mismatched peers fail closed with a clear message.
- Tax and accounting corrections preserve original transaction snapshots; reports may be recomputed, but historical source records are never rewritten without a separately approved data migration.
- Release/legal changes are reversible in packaging, but distributed licence obligations for an already shipped GPL build are not revoked retroactively.

## Approval Status

Human decisions are complete. Implementation may begin after the owner confirms this document accurately captures the choices above.
