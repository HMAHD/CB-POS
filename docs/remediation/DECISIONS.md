# Locked Decisions

Append-only log of decisions the owner has made. An agent may **not** reverse or reinterpret a decision here. If one looks wrong given new evidence, raise it with Stop & Ask (RELEASE_PLAN.md §0.5).

Format: `D<n> — <date> — #<issue> — <decision>`. New decisions go at the bottom with the next number.

## Carried over from the 2026-10-23 plan

**D1 — 2026-10-23 — #731 — Full printer verification.** Test report printing from the background thread on Windows with real thermal (58 mm and 80 mm) and A4 printers, plus Microsoft Print to PDF.

**D2 — 2026-10-23 — #799 — PostgreSQL network mode is fully supported.** Connection and migration belong in one guided Network Setup flow. After a successful connection, an administrator on the designated **Main PC** may run Alembic. Tills never migrate. A till that finds a schema mismatch blocks with "Main PC update required."

**D3 — 2026-10-23 — #800 — Verified first connection (certificate pinning).** Show the Main PC certificate's SHA-256 fingerprint on both machines, require the user to confirm they match, persist the pin, and block and audit any later certificate change. The sync token is never sent before the pin is verified.

**D4 — 2026-10-23 — #810 — `ROUND_HALF_UP` everywhere.** One explicit money-rounding helper governs currency, taxes, AVCO and totals. The rounded net is calculated as total − rounded VAT − rounded SSCL, so the components always reconcile to the total. The VAT rate accepts two decimals.

**D5 — 2026-10-23 — #812 — Partial refunds.** Refunds are allocated to the original tenders proportionally by default. A manager with permission may override to cash or customer credit, but only with a reason, and the override writes an AuditLog entry.

**D6 — 2026-10-23 — #814 — Full tax-invoice compliance.** Verify against official IRD/Gazette sources. Implement the mandated serial, the required fields, amount in words where required, and `ORIGINAL` / `COPY ONLY` marking. Ordinary retail receipts stay a separate document type.

**D7 — 2026-10-23 — #815 — Installer architecture deferred.** Paid code signing is not viable now. (Re-scoped by D13: the parts of #815 that need no paid signing are now in Phase 10A.)

**D8 — 2026-10-23 — #817 — GPLv3 distribution.** Keep PyQt6. Distribute CB-POS and its corresponding source under GPLv3, and add privacy and third-party notices. Legal review is required before public release.

**D9 — 2026-10-23 — #831 — Independent SSCL model.** `sscl_registered` is independent of VAT registration. Support Retail / Manufacturer / Distributor turnover presets. Model SSCL exemptions separately. Remove SSCL from customer receipts and keep it in liability reporting.

**D10 — 2026-10-23 — #878 — CODE128 for the receipt invoice barcode.** Use code set `{B}`, with dimensions calculated to fit the longest allowed document number on both 58 mm and 80 mm paper.

**D11 — 2026-10-23 — #914 — Database-enforced concurrency.** Use PostgreSQL row locking (`SELECT … FOR UPDATE`) plus a partial unique index, proven by a test with two concurrent database connections.

**D12 — 2026-10-23 — #918 — Remove every forbidden Qt `destroyed` hook.** Use `call_on_destroyed` or owner-bound callbacks, remove redundant cleanup hooks, and add a guardrail test that fails if `destroyed.connect(` appears outside `destroy_hooks.py`.

## 2026-10-28

**D13 — 2026-10-28 — scope — Former backlog is in scope.** All 23 `backlog` issues (#815, #923–#944) are included in this plan as Phases 10A–10C, after the public release gate. Product-design gates in those issues still require Stop & Ask before implementation.

**D14 — 2026-10-28 — priority — Phase order approved.** Data loss and money first, then security, cross-till correctness, report truth, hardware and language output, release paperwork, and finally features (RELEASE_PLAN.md §1.1).

**D15 — 2026-10-28 — process — Defects discovered during remediation** are filed as GitHub issues and added to PROGRESS.md and the relevant phase (RELEASE_PLAN.md §0.9).

## 2026-10-29 — UI system (from docs/remediation/UI_SYSTEM_AUDIT.md)

**D16 — 2026-10-29 — UI — Foundation first.**
1. Build the design system layer: tokens, shared components (PageHeader, ActionBar, DataTable, FilterBar/DateRangeFilter, KpiStrip, FormDialog, EntityPicker, StatusPill, ContextMenu builder), the view lifecycle contract (`on_activated`), and guardrails.
2. Then migrate screens one by one.
3. No screen gets one-off styling.

**D17 — 2026-10-29 — Purchasing IA.**
- Tabs: Suppliers | Purchase Orders (new screen) | Goods Received | Payables.
- "New PO" and "New GRN" are actions that open focused forms. A GRN can be started from a PO ("Receive this order").

**D18 — 2026-10-29 — Stock Control.**
- One sidebar section, **Stock Control**, with tabs Reorder | Stock Count (renamed from Stock Take) | Adjustments (Phase 4 #794).

**D19 — 2026-10-29 — Who builds.**
- Claude builds the foundation (tokens, components, view lifecycle, guardrails).
- Gemini migrates screens onto it, following specs in the remediation plan.

**D20 — 2026-10-29 — UI — Colour tokens keep the documented palette.**
- The tokens are the palette in CLAUDE.md: dark `#1E1E1E`/`#252526`, cyan `#00BCEB`, green `#39FF14`, yellow `#FFDC00`, red `#FF4136`; light `#F8F9FA`/`#FFFFFF`, blue `#0D6EFD`, green `#198754`, red `#DC3545`.
- Every stray shade snaps to its nearest token.
- The goal is consistency, not a new look.

**D21 — 2026-10-29 — #948 — Quarantining tracked pre-existing failures.** Pre-existing failures that are already tracked by an open issue may be quarantined with `xfail(strict=True)` and a reason naming the issue. `strict=True` makes CI fail when the bug is fixed, so the marker must be removed in the fixing PR. Any other use of xfail or skip is still forbidden (§0.3).

**D22 — 2026-10-30 — #856 — Nullable audit_logs.user_id for terminal events.** Make audit_logs.user_id nullable via an Alembic migration so terminal-scoped security events like LOCKOUT can be recorded with user_id=None without attributing unknown attempts to the Admin user or polluting the audit trail.

**D23 — 2026-11-04 — #914 — Concurrency locking via `FOR UPDATE` and `refunded_qty` CHECK (amending D11).** Replace D11's partial unique index on `sales.refund_of_sale_id` with row-level locking (`SELECT … FOR UPDATE` via `with_for_update=True`) on the original sale in `void_sale` and refund operations, paired with the database CHECK constraint on `sale_items.refunded_qty` (`ck_sale_items_refunded_qty`) from Phase 3A (D5, #812). This prevents concurrent over-refunds and race conditions in network mode while allowing legitimate multiple partial refunds of a single sale.

**D24 — 2026-11-05 — #812 — Partial-refund VAT proportional to value.** A partial refund's VAT is proportional to value now (`round_money(sale.tax_vat * value / sale.total_amount)` with remainder reconciliation on final refund). Switch to line-level calculation once #797 stores the per-line taxable flag in Phase 6.1.

**D25 — 2026-11-08 — #831 — Independent SSCL registration and presets.** `sscl_registered` is independent of `vat_registered` (defaulting on config load to current `vat_registered` if unset). Support turnover presets: RETAIL (50%), MANUFACTURER (85%), DISTRIBUTOR (25%), CUSTOM. SSCL base is VAT-exclusive turnover: `amount / (1 + vat_rate/100)` for VAT-taxable lines in VAT-registered shops; full `amount` for lines where no VAT was charged (VAT-exempt or shop not VAT-registered); 0.00 for SSCL-exempt lines. SSCL is removed from customer receipts and invoices, shown in tax reports only.

**D26 — 2026-11-09 — #810, #831 — Accountant review packet for Tax Filing Summary and Profit & Loss.** Tax Filing Summary and P&L report outputs for the reconciliation day (incorporating VAT/SSCL combinations, voids, partial/full refunds, discounts and loyalty redemptions) are exported and reconciled. The accountant review packet is attached to the PR with the reconciliation artifacts confirming exact tie-out across gross revenue, net revenue, input VAT, output VAT, SSCL liable turnover, and net cash flow.

## 2026-11-12

**D27 — 2026-11-12 — #817 — GNU GPLv3 distribution confirmed (confirming D8, superseding closed-source notes).** The owner chose the GPLv3 distribution path on 2026-11-12. Keep PyQt6. CB POS is free and open-source software under the GNU General Public License version 3 (GPLv3). Every binary release provides the complete corresponding source code for that exact version via public tagged repository link (`https://github.com/HMAHD/CB-POS/tree/v{version}`). There is no closed-source freeware EULA and no additional "no resale", "no modification", or other GPL-incompatible restrictions. This supersedes all previous "closed source / not open source" product notes. Final owner and lawyer review remains required before the first public release.

**D28 — 2026-11-12 — #820, #821 — Phase 9 warranty development pulled forward.** The owner explicitly approved starting Phase 9 (Warranty and Repairs) before the public release gate (§1.3) passes, as permitted by the Phase 9 dependency rule in `phase-09-warranty.md`. Warranty development and testing proceed on internal pre-release builds while unresolved legal review gates (#817) and physical hardware verification gates (#819, #911, #731, #878, #877) continue to hold the public release gate.








