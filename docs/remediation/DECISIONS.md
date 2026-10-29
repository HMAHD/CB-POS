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
