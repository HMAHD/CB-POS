# Phase U.0 Discovery and Re-baselining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete issue #1041 with reproducible full-product UI evidence, a risk-ranked retrospective integrity audit, and an owner-approved Phase U implementation proposal without changing product behavior.

**Architecture:** Keep U.0 as a documentation-and-measurement branch. Reproducible inventory, visual-capture, and performance scripts write versioned evidence under `docs/remediation/phase-u/evidence/`; hand-reviewed journey, architecture, issue-reconciliation, and integrity conclusions live in focused Markdown documents. Product fixes found during discovery use separate issues, branches, and PRs; this branch only records evidence and dispositions.

**Tech Stack:** Python 3.12+, AST, PyQt6/QTest, SQLAlchemy instrumentation, JSON, Markdown/Sphinx, pytest, GitHub CLI.

**Spec:** `docs/remediation/PHASE_U_DISCOVERY_BRIEF.md`

## Global Constraints

- U.0 remains documentation and measurement only; do not modify `cbpos/`, Alembic revisions, QSS, translations, or product tests to repair discovered behavior.
- Product-code implementation remains blocked until every Phase 10B exit checkbox passes, the exact final `main` SHA and green post-merge CI are recorded, both final-SHA delta passes are complete, no R1 remains, and the owner approves the deduplicated issue map.
- Treat issues #963–#975 and `UI_SYSTEM_AUDIT.md` A1–G as provisional inputs, not approved implementation work.
- CB POS is keyboard-first and mouse-friendly; touch-specific sizing, gestures, and interaction patterns are out of scope.
- File length is a responsibility signal, never performance evidence; performance claims require measurements.
- Every finding records current code/evidence, root cause, affected journey, state/input → wrong behavior, risk, measurable acceptance criteria, and platform limits.
- Audit dark and light themes, English/Sinhala/Tamil, and the supported 1366×768 release size; label Windows, printer, scanner, PostgreSQL, and physical-hardware gaps honestly.
- Never create one issue per visual symptom. Group by shared cause and journey, then wait for owner approval before creating or expanding Phase U implementation issues.
- Use `Decimal` for money evidence and preserve existing service/domain ownership in recommendations.
- Use regular merge commits, never squash; do not add AI attribution to commits, PRs, issue comments, or files.

## Review Focus

- A UI surface reachable only through a permission-filtered path must not be classified as globally reachable; record the exact role/path or the missing path.
- A screen that renders correctly in English may clip or lose actions in Sinhala/Tamil at 1366×768; capture all six theme/language combinations for the selected evidence set.
- A fast SQLite run must not be used to declare a synchronous database path safe on PostgreSQL or a slow network; separate observed timing from thread-ownership evidence.
- A green test suite must not substitute for review of money, stock, schema, permission, historical, or worker-lifecycle invariants in the retrospective audit.
- A finding that disappears on the final Phase 10B baseline must be marked superseded with the fixing SHA/PR, not carried into the owner proposal.

---

### Task 1: Make the mechanical UI inventory reproducible

**Files:**
- Create: `scripts/phase_u_inventory.py`
- Create: `tests/guardrails/test_phase_u_inventory.py`
- Create: `docs/remediation/phase-u/evidence/ui_inventory.json`
- Modify: `docs/remediation/phase-u/UI_SURFACE_INVENTORY.md`
- Modify: `docs/remediation/phase-u/ISSUES_SUMMARY.md`

**Interfaces:**
- Consumes: Python files under `cbpos/ui/` and a baseline SHA supplied on the command line.
- Produces: `scan_ui_tree(root: Path, baseline_sha: str) -> dict[str, object]`, `write_inventory(payload: dict[str, object], output: Path) -> None`, and CLI flags `--root`, `--baseline-sha`, `--output`, and `--check`.
- Evidence schema per file: `path`, `role`, `line_count`, `classes`, `core_service_imports`, `direct_database_import`, `worker_classes`, `inline_stylesheet_calls`, and `hex_literals`.

- [ ] **Step 1: Write inventory-tool regression tests**

Add tests using temporary Python fixtures that assert AST-based class/import/style detection, deterministic path ordering, baseline-SHA recording, and `--check` failure when the checked-in JSON differs.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `uv run python -m pytest tests/guardrails/test_phase_u_inventory.py -v`

Expected: FAIL because `scripts.phase_u_inventory` does not exist.

- [ ] **Step 3: Implement the minimum AST inventory tool**

Do not import application modules. Count source lines and inspect imports, classes, `setStyleSheet` calls, and string literals through `ast`; keep reachability and severity out of this mechanical tool.

- [ ] **Step 4: Run the focused tests and generate the provisional evidence file**

Run:

```bash
uv run python -m pytest tests/guardrails/test_phase_u_inventory.py -v
uv run python scripts/phase_u_inventory.py \
  --root cbpos/ui \
  --baseline-sha 69fd64a \
  --output docs/remediation/phase-u/evidence/ui_inventory.json
uv run python scripts/phase_u_inventory.py \
  --root cbpos/ui \
  --baseline-sha 69fd64a \
  --output docs/remediation/phase-u/evidence/ui_inventory.json \
  --check
```

Expected: tests PASS; the second script run exits 0 and reports no drift.

- [ ] **Step 5: Replace non-reproducible mechanical claims with manifest-backed counts**

Update the inventory method/counts and the summary to cite the JSON baseline and explicitly retain manual reachability/state review as separate work.

- [ ] **Step 6: Verify and commit**

Run:

```bash
uv run pre-commit run --files scripts/phase_u_inventory.py tests/guardrails/test_phase_u_inventory.py docs/remediation/phase-u/UI_SURFACE_INVENTORY.md docs/remediation/phase-u/ISSUES_SUMMARY.md
git diff --check
git add scripts/phase_u_inventory.py tests/guardrails/test_phase_u_inventory.py docs/remediation/phase-u/evidence/ui_inventory.json docs/remediation/phase-u/UI_SURFACE_INVENTORY.md docs/remediation/phase-u/ISSUES_SUMMARY.md
git commit -m "docs(ui): make Phase U inventory reproducible (#1041)"
```

Expected: checks pass and one commit records the tool plus evidence.

### Task 2: Complete reachability, ownership, and lifecycle classification

**Files:**
- Modify: `docs/remediation/phase-u/UI_SURFACE_INVENTORY.md`
- Modify: `docs/remediation/phase-u/UI_ARCHITECTURE_MAP.md`
- Create or modify: `docs/remediation/phase-u/issues/<screen>_issues.md` for every audited screen group
- Modify: `docs/remediation/phase-u/ISSUES_SUMMARY.md`

**Interfaces:**
- Consumes: `ui_inventory.json`, Graphify/graft caller evidence, `MainWindow`, `SideMenu`, `ManagementView`, `SettingsView`, dialog callers, and permission maps.
- Produces: one disposition for every inventory record: `navigation-root`, `direct-view`, `embedded-surface`, `modal-surface`, `state-overlay`, `reusable-control`, `worker/adapter`, `helper-only`, or `unreachable/stale`; each visible record also gets owner, caller/path, permission gate, construction lifetime, activation/reload seam, and state coverage.

- [ ] **Step 1: Add a deliberately incomplete classification table and run a completeness assertion**

Use an isolated Python assertion that compares all JSON `path` values with the classification rows in `UI_SURFACE_INVENTORY.md`.

Expected: FAIL and print the unclassified paths.

- [ ] **Step 2: Trace every unclassified surface from its navigation or caller root**

Use Graphify first, then graft callers/grep for exact edges. Do not infer reachability from an import alone. Record unreachable/stale items with the failed caller search and no deletion recommendation unless the evidence is conclusive.

- [ ] **Step 3: Record ownership and lifecycle seams**

Complete the architecture map for eager/lazy construction, activation, service/worker ownership, permission exposure, language/theme callback lifetime, and modal ownership. Distinguish UI navigation permission from service mutation permission.

- [ ] **Step 4: Rerun the completeness assertion**

Expected: PASS with every manifest path classified exactly once and every visible surface linked to a screen audit file.

- [ ] **Step 5: Verify and commit**

Run:

```bash
uv run sphinx-build -Q -b html docs docs/_build/html
git diff --check
git add docs/remediation/phase-u/UI_SURFACE_INVENTORY.md docs/remediation/phase-u/UI_ARCHITECTURE_MAP.md docs/remediation/phase-u/issues docs/remediation/phase-u/ISSUES_SUMMARY.md
git commit -m "docs(ui): complete Phase U surface ownership map (#1041)"
```

Expected: docs build and diff check pass.

### Task 3: Map oversized responsibility clusters without prescribing splits

**Files:**
- Modify: `docs/remediation/phase-u/UI_ARCHITECTURE_MAP.md`
- Modify: matching `docs/remediation/phase-u/issues/<screen>_issues.md` files
- Modify: `docs/remediation/phase-u/ISSUES_SUMMARY.md`

**Interfaces:**
- Consumes: the ten ≥1,000-line candidates from `ui_inventory.json`, their callers/callees, tests, workers, services, and state ownership.
- Produces: for each candidate, a responsibility-cluster table with entry points, owned state, service/worker dependencies, test surfaces, shared mutable state, natural seams, and “do not split” constraints.

- [ ] **Step 1: Assert that every ≥1,000-line manifest record has a cluster section**

Expected: FAIL listing the candidates not yet covered beyond Sales, Purchasing, Network, Admin Tools, or shared workers.

- [ ] **Step 2: Trace each missing candidate and write the cluster evidence**

Cover at minimum `product_editor.py`, `admin_tools_view.py`, `credit_book_view.py`, `document_view.py`, `stock_take_view.py`, `warranty_claims_board_view.py`, `settings_pages/network.py`, and `workers.py`, plus any candidates introduced by the current baseline. No extraction proposal may cite line count alone.

- [ ] **Step 3: Group repeated defects by owning seam**

When multiple screens share one blocking call, lifecycle error, or duplicated orchestration rule, record one root-cause group and link all affected journeys; do not inflate the finding count.

- [ ] **Step 4: Rerun the cluster coverage assertion**

Expected: PASS for every current ≥1,000-line record.

- [ ] **Step 5: Verify and commit**

Run the Sphinx build and `git diff --check`, then commit as:

```bash
git commit -m "docs(ui): map Phase U responsibility clusters (#1041)"
```

### Task 4: Audit the highest-value keyboard and mouse journeys

**Files:**
- Create: `docs/remediation/phase-u/JOURNEY_AUDIT.md`
- Modify: `docs/remediation/phase-u/issues/<screen>_issues.md`
- Modify: `docs/remediation/phase-u/ISSUES_SUMMARY.md`

**Interfaces:**
- Consumes: seeded demo database; roles Admin, Manager, Cashier; navigation map; current services and permission maps.
- Produces: journey matrices covering start state, keyboard path, mouse path, focus order, validation, loading, empty, error, permission-denied, cancellation, success, re-entry/reload, recovery, evidence location, and finding IDs.

- [ ] **Step 1: Create the journey matrix with all required journeys marked `not-run`**

Required journeys: first-run/setup and login; shift start/close; scan/search/add/edit cart; normal payment and Quick Pay; cancellation/held bill/autosave recovery; history/reprint/refund; customer/credit payment; inventory/product/category/stock adjustment/import; supplier/GRN/payables/payment; stock count/reorder; reports/filter/export/print; backup/restore/maintenance; settings/hardware/network/update; users/roles/permissions; warranty lookup/intake/resolve; logout/session expiry.

- [ ] **Step 2: Run the seeded app at 1366×768 and walk each journey keyboard-only, then mouse**

Run `uv run python scripts/seed.py`, then `uv run python main.py` with a disposable worktree database. Record exact state/input → observed behavior and never mark printer, scanner, Windows, or PostgreSQL behavior verified without that environment.

- [ ] **Step 3: Trace every surviving defect to current code and its owning seam**

For each candidate finding, first search existing GitHub issues. Record evidence and acceptance criteria in the screen file; update the summary counts and owner-concern tracker. Do not create implementation issues yet.

- [ ] **Step 4: Assert no required journey remains `not-run`**

Expected: PASS; any genuinely unavailable environment is marked `blocked — <specific evidence needed>`, not passed.

- [ ] **Step 5: Verify and commit**

Run Sphinx and diff checks, then commit as:

```bash
git commit -m "docs(ui): audit Phase U user journeys (#1041)"
```

### Task 5: Capture the dark/light and trilingual visual baseline

**Files:**
- Create: `scripts/capture_phase_u_screenshots.py`
- Create: `tests/ui/shell/test_phase_u_capture_manifest.py`
- Create: `docs/remediation/phase-u/VISUAL_AUDIT.md`
- Create: `docs/remediation/phase-u/evidence/screenshots/*.png`
- Create: `docs/remediation/phase-u/evidence/screenshot_manifest.json`
- Modify: per-screen issue files and `ISSUES_SUMMARY.md`

**Interfaces:**
- Consumes: journey/surface map, seeded data, `ThemeService.render_stylesheet(theme)`, `set_language(language)`, and `QWidget.grab()`.
- Produces: `CaptureSpec(name: str, factory: Callable[[], QWidget], prepare: Callable[[QWidget], None] | None)`, `capture_specs(...)`, CLI `--output-dir`, `--manifest`, and `--check`; manifest keys include surface, journey/state, theme, language, viewport, baseline SHA, file, and manual-review disposition.

- [ ] **Step 1: Write capture-manifest tests**

Assert the required matrix is exactly dark/light × en/si/ta at 1366×768 for each selected primary surface/state, file names are stable, missing files fail `--check`, and the tool does not compare colours or pixel values.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/ui/shell/test_phase_u_capture_manifest.py -v`

Expected: FAIL because the capture module does not exist.

- [ ] **Step 3: Implement the capture harness using existing screenshot-script patterns**

Capture one primary state for every reachable top-level/management/settings screen and each issue-specific loading/empty/error/permission state needed to prove a finding. Keep real-flow screenshots separate from synthetic state setup in the manifest.

- [ ] **Step 4: Generate and manually inspect the six-combination evidence set**

Run the capture script with `QT_QPA_PLATFORM=offscreen`, then inspect every image for clipping, hierarchy, opaque/mismatched text backgrounds, focus visibility, action discoverability, table readability, and translation flow. Record findings in `VISUAL_AUDIT.md` and per-screen files.

- [ ] **Step 5: Verify manifest completeness and focused tests**

Expected: every required manifest row has a readable PNG and a disposition; no `pending-review` rows remain.

- [ ] **Step 6: Verify and commit**

Run focused UI test, Sphinx, pre-commit for the new script/test, and `git diff --check`; commit as:

```bash
git commit -m "docs(ui): capture Phase U visual baseline (#1041)"
```

### Task 6: Measure construction, activation, queries, blocking, workers, and reloads

**Files:**
- Create: `scripts/measure_phase_u_ui.py`
- Create: `tests/ui/shell/test_phase_u_measurement_tools.py`
- Create: `docs/remediation/phase-u/PERFORMANCE_BASELINE.md`
- Create: `docs/remediation/phase-u/evidence/performance_baseline.json`
- Modify: per-screen issue files and `ISSUES_SUMMARY.md`

**Interfaces:**
- Consumes: seeded SQLite database; widget factories; public `on_activated()` seams; SQLAlchemy engine events; Qt event-loop heartbeat; worker signals.
- Produces: `measure_construction(factory, repetitions)`, `measure_activation(widget, repetitions)`, `count_queries(engine)`, `measure_event_loop(action, heartbeat_ms)`, and JSON rows with environment, sample count, median, p95, query count, event-loop gap, worker lifetime, reload count, and baseline SHA.

- [ ] **Step 1: Write measurement-tool tests with deterministic fake work**

Assert median/p95 calculation, query counting, heartbeat detection for a deliberately blocking action, worker completion tracking, and stable JSON serialization. Do not set performance budgets in these tests.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/ui/shell/test_phase_u_measurement_tools.py -v`

Expected: FAIL because the measurement module does not exist.

- [ ] **Step 3: Implement the minimum measurement helpers**

Keep the tool observational. Never move product work to threads or alter production timeouts in this branch.

- [ ] **Step 4: Record representative measurements**

Measure top-level startup construction; first and repeat activation for each management destination; eager Settings construction; Sales checkout commit; GRN receipt; Network setup operations using safe test doubles; report generation; update check; hardware-test workers; and unnecessary repeated reloads. Use warmup plus at least 10 measured repetitions for deterministic local paths and record machine/OS/Python/Qt/DB mode.

- [ ] **Step 5: Separate observations from conclusions**

`PERFORMANCE_BASELINE.md` must say what was measured, what was only statically traced, and what still requires PostgreSQL/Windows/hardware. Do not generalize SQLite timing to network mode.

- [ ] **Step 6: Verify and commit**

Run focused tests, Sphinx, pre-commit for the tool/test, and diff check; commit as:

```bash
git commit -m "docs(ui): measure Phase U performance baseline (#1041)"
```

### Task 7: Reconcile the historical audit and issues #963–#975

**Files:**
- Create: `docs/remediation/phase-u/ISSUE_RECONCILIATION.md`
- Modify: `docs/remediation/UI_SYSTEM_AUDIT.md`
- Modify: `docs/remediation/phases/phase-U-ui-system.md`
- Modify: `docs/remediation/phase-u/ISSUES_SUMMARY.md`

**Interfaces:**
- Consumes: Tasks 2–6 evidence, audit findings A1–G, decisions D16–D20/D37–D42, and issues #963–#975.
- Produces: one evidence-backed provisional disposition per historical finding and issue: `retain`, `merge`, `split`, `replace`, `defer`, `reject`, or `already-fixed`; each row includes evidence, root cause group, dependencies, acceptance criteria, and owner-decision need.

- [ ] **Step 1: Add all audit finding IDs and #963–#975 with empty dispositions**

Run a structural assertion that compares the document with the complete A1–A5, B1–B4, C1–C9, D1–D3, E1–E5, F1–F4, G, and issue-number sets.

Expected: FAIL because dispositions/evidence are empty.

- [ ] **Step 2: Revalidate every row against current code and collected evidence**

Preserve locked decisions unless new evidence creates a Stop & Ask question. Merge symptoms sharing a root cause. Record `already-fixed` only with the fixing PR/SHA and current proof.

- [ ] **Step 3: Update the historical audit and provisional phase map**

Do not rewrite the post-U.0 implementation sequence as approved. Mark it as the evidence-derived proposal pending final Phase 10B delta and owner approval.

- [ ] **Step 4: Rerun the structural assertion**

Expected: PASS with every input exactly once and no blank disposition/evidence/acceptance field.

- [ ] **Step 5: Verify and commit**

Run Sphinx and diff checks, then commit as:

```bash
git commit -m "docs(ui): reconcile Phase U audit inputs (#1041)"
```

### Task 8: Audit money, tax, ledger, and report-truth invariants

**Files:**
- Create: `docs/remediation/phase-u/RETROSPECTIVE_INTEGRITY_AUDIT.md`
- Modify: `docs/remediation/phase-u/ISSUES_SUMMARY.md`

**Interfaces:**
- Consumes: completed remediation PRs/issues for payments, refunds, VAT/SSCL, credit, supplier payable, loyalty, cash movement, document totals, and reports; responsible services/callers and focused tests.
- Produces: audit rows with issue/PR/reviewed SHA, invariant, responsible seam/callers, concrete failure search, focused evidence, SQLite/PostgreSQL limits, risk grade, and disposition.

- [ ] **Step 1: Create the audit matrix with every required money/tax area marked `unreviewed`**

- [ ] **Step 2: Review highest-loss invariants first**

Verify exact Decimal reconciliation, refund/void concurrency, VAT/SSCL bases, payment-method kinds, credit/loyalty/supplier ledger truth, document totals, and report tie-outs. Green CI is supporting evidence, never the review itself.

- [ ] **Step 3: Run focused domain/integration tests named by each row and record outputs**

Any discovered R1/R2/R3 must include state/input → wrong behavior. Do not repair it on this branch. R1 blocks U.0 and gets a separate issue/repair branch immediately; R2/R3 gets an evidence-backed disposition and owner decision where scope changes.

- [ ] **Step 4: Assert no scoped row remains `unreviewed` or lacks evidence**

- [ ] **Step 5: Verify and commit**

Run cited focused tests, Sphinx, and diff check; commit as:

```bash
git commit -m "docs(audit): review money and tax integrity for Phase U (#1041)"
```

### Task 9: Audit stock, purchasing, Phase 10B, sync, and schema invariants

**Files:**
- Modify: `docs/remediation/phase-u/RETROSPECTIVE_INTEGRITY_AUDIT.md`
- Modify: `docs/remediation/phase-u/ISSUES_SUMMARY.md`

**Interfaces:**
- Consumes: stock movements/AVCO, purchase/GRN/payables, migrations/upgrades, sync/PostgreSQL, and every merged Phase 10B issue including the final #937 review gap.
- Produces: the same audit-row contract as Task 8 plus exact SQLite/PostgreSQL and migration upgrade/downgrade evidence.

- [ ] **Step 1: Add all required areas as `unreviewed`**

Include stock movement conservation, weighted quantities, AVCO, purchase-unit snapshots, batch allocation/MRP/expiry, autosave CAS/recovery, price-board atomicity, feature flags/presets, sync IDs/protocol compatibility, schema gates, and migration paths.

- [ ] **Step 2: Review responsible seams and callers, then run focused tests**

Review #937 at its final merged SHA even though its pre-merge whole-PR review was usage-blocked. Include every later Phase 10B batch when it merges.

- [ ] **Step 3: Record risk and disposition without repairing product code here**

- [ ] **Step 4: Assert no scoped row remains `unreviewed` or evidence-free**

- [ ] **Step 5: Verify and commit**

Commit as:

```bash
git commit -m "docs(audit): review stock sync and schema integrity (#1041)"
```

### Task 10: Audit permissions, history, migrations, and asynchronous lifecycle

**Files:**
- Modify: `docs/remediation/phase-u/RETROSPECTIVE_INTEGRITY_AUDIT.md`
- Modify: `docs/remediation/phase-u/ISSUES_SUMMARY.md`

**Interfaces:**
- Consumes: permission catalog/service boundaries, AuditLog mutation coverage, warranty historical truth, backup/restore, update/printing/hardware/network workers, callback destruction, and remaining completed-remediation samples.
- Produces: completed provisional retrospective audit with all findings dispositioned and no silent evidence gaps.

- [ ] **Step 1: Add all required areas as `unreviewed`**

- [ ] **Step 2: Review fail-closed permission and audit behavior**

Distinguish hidden navigation from service enforcement; inspect manager overrides and acting-user requirements.

- [ ] **Step 3: Review historical and recovery truth**

Cover warranty policy/history, backup/restore, migration continuity, worker cancellation/timeouts, duplicate-trigger prevention, destroy-time callbacks, and UI-thread boundaries.

- [ ] **Step 4: Sample lower-risk completed batches by changed seam and failure impact**

Record the sampling rule and why omitted batches are covered by a shared invariant or explicitly outside scope.

- [ ] **Step 5: Assert the provisional audit completion contract**

Expected: every scoped area/finding has a disposition; no provisional R1 remains; focused checks and limits are recorded. Final Phase 10B delta remains visibly pending.

- [ ] **Step 6: Verify and commit**

Commit as:

```bash
git commit -m "docs(audit): complete provisional Phase U integrity audit (#1041)"
```

### Task 11: Run the mandatory final Phase 10B delta and write the implementation proposal

**Files:**
- Regenerate: `docs/remediation/phase-u/evidence/ui_inventory.json`
- Regenerate as needed: visual/performance evidence
- Modify: all Phase U.0 evidence documents
- Create: `docs/remediation/phase-u/IMPLEMENTATION_PROPOSAL.md`
- Modify: `docs/remediation/phase-u/ISSUES_SUMMARY.md`
- Modify: `docs/remediation/PROGRESS.md`
- Modify: `docs/remediation/phases/phase-U-ui-system.md`

**Interfaces:**
- Consumes: exact final Phase 10B `origin/main` SHA, green post-merge CI URL/run ID, Tasks 1–10 evidence, and all final Phase 10B changes.
- Produces: final-SHA discovery delta, final-SHA retrospective delta, no unresolved R1, and a dependency-ordered proposal with measurable acceptance criteria; approval state remains `pending owner` until explicit owner response.

- [ ] **Step 1: Verify every Phase 10B exit checkbox from authoritative GitHub/main evidence**

Do not proceed on a feature branch SHA or PR CI. Record each issue as merged/verified closed or owner-parked with D-number, feature-flag/preset tests, invariant suites, i18n review submission, UI screenshots, exact final `main` SHA, and green post-merge CI URL.

- [ ] **Step 2: Merge final `origin/main` into the U.0 branch and rerun inventory `--check`**

Regenerate the manifest with the exact SHA, classify any added/removed/changed UI surfaces, and record the delta rather than silently replacing provisional evidence.

- [ ] **Step 3: Rerun affected journeys, screenshots, and performance measurements**

Recheck every seam changed after `69fd64a` plus all owner concerns. Mark superseded findings with the fixing SHA/PR.

- [ ] **Step 4: Run the retrospective integrity delta**

Review all post-provisional commits by changed invariant. Resolve every R1 through separate repair PRs, then rerun the affected evidence before continuing.

- [ ] **Step 5: Write the deduplicated implementation proposal**

For each proposed batch record: included root-cause groups/findings, excluded/deferred items, dependencies, service/component ownership, exact acceptance criteria, focused tests, UI evidence required, Windows/hardware gates, and issue changes proposed. Use U.1–U.7 labels only where evidence supports them.

- [ ] **Step 6: Run structural completeness assertions**

Expected: every surface, required journey/state, owner concern, audit finding A1–G, issue #963–#975, retrospective area/finding, and final Phase 10B delta has exactly one traceable disposition; no R1 remains; proposal approval is still `pending owner`.

- [ ] **Step 7: Verify and commit**

Run focused audit tools/tests, Sphinx, pre-commit, and diff check; commit as:

```bash
git commit -m "docs(ui): propose evidence-backed Phase U batches (#1041)"
```

- [ ] **Step 8: Present the proposal to the owner and stop**

Do not create/expand implementation issues, mark U.0 complete, or edit product code until explicit owner approval is recorded.

### Task 12: Whole-U.0 review and completion record

**Files:**
- Modify: evidence documents and summary only for review fixes
- Modify after approval: `docs/remediation/PROGRESS.md`
- Modify after approval: `docs/remediation/phases/phase-U-ui-system.md`

**Interfaces:**
- Consumes: full branch diff against final Phase 10B `main`, owner approval, and all verification output.
- Produces: a reviewed, approved U.0 record and the final authorized implementation map.

- [ ] **Step 1: Build one whole-branch review package**

Review the complete U.0 diff against the discovery brief, #1041, UI gate, decisions D16–D20/D37–D42, and the final Phase 10B exit record. Deliberately inspect all five Review Focus items.

- [ ] **Step 2: Run a fresh independent whole-U.0 review**

No finding is fixed silently. Correct important documentation/tool defects in one pass with focused regression checks; record lower-risk evidence gaps as blocking until resolved, not “minor” if they invalidate a required deliverable.

- [ ] **Step 3: Run final verification once**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/guardrails/test_phase_u_inventory.py tests/ui/shell/test_phase_u_capture_manifest.py tests/ui/shell/test_phase_u_measurement_tools.py -v
uv run pre-commit run --all-files
uv run sphinx-build -Q -b html docs docs/_build/html
git diff --check
```

Expected: all commands pass; evidence manifests report no drift or pending review; every completion assertion passes.

- [ ] **Step 4: Record explicit owner approval and final U.0 status**

After approval, replace the provisional map in `phase-U-ui-system.md`, update `PROGRESS.md` with final SHA/CI, review evidence, approval link/date, and next authorized batch. Do not infer approval from silence.

- [ ] **Step 5: Commit the completion record**

```bash
git commit -m "docs(ui): complete Phase U discovery gate (#1041)"
```

Expected: the branch is clean and ready for normal PR review/merge; product-code work begins only from the first owner-approved batch after U.0 merges.
