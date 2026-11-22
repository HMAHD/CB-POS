# Phase U Discovery Brief — UI/UX and UI Architecture

> **Status:** owner-approved Phase U handoff, recorded 2026-11-20 and amended by D42 on 2026-11-22.
> **Read with:** `RELEASE_PLAN.md` Part 0, `DECISIONS.md` D16–D20 and D37–D42, `UI_SYSTEM_AUDIT.md`, and `phases/phase-U-ui-system.md`.
> **Purpose:** preserve the owner’s concerns and the agreed discovery-first process. This brief is not an implementation issue or permission to make speculative UI changes.

## Roadmap and ownership

1. Merge and verify #937 before Phase U.0 begins. Under D42, Gemini may continue a remaining Phase 10B issue in parallel only after that issue’s required human gate passes and its decision is recorded; D42 grants concurrency, not feature-scope approval.
2. Defer Phase 10C to a later release.
3. Run and record the risk-ranked retrospective integrity audit of completed remediation work in `docs/remediation/phase-u/RETROSPECTIVE_INTEGRITY_AUDIT.md` before Phase U structural changes. Resolve every surviving release or data-integrity blocker before product-code implementation.
4. Claude starts Phase U discovery, architecture, implementation, review, and integration. D37 supersedes D19’s Claude/Gemini split; as D42’s explicit exception to D37(3), Gemini may continue Phase U from the execution playbook if Claude usage is unavailable, under the same gates.
5. Existing Phase U issues #963–#975 are inputs to discovery, not an automatically approved implementation queue. Phase U.0 must verify, deduplicate, expand, replace, defer, or reject each item against the post-Phase-10B codebase.

## Interaction model

CB POS is **keyboard-first and mouse-friendly**.

- Keyboard navigation, shortcuts, focus order, default actions, Enter/Escape behavior, and visible focus are release requirements.
- Mouse operation, discoverable controls, context menus, and clear hover/selection states are release requirements.
- Touch-specific sizing, gestures, or interaction patterns are not current requirements unless separately approved later.
- Existing useful touch behavior need not be removed; it simply must not drive Phase U scope or acceptance criteria.

## Owner concerns Phase U must investigate

### 1. Very large view files and UI maintainability

Some view files exceed 1,000 lines and appear to combine too many responsibilities. Phase U.0 must identify natural responsibility seams, ownership, dependencies, and test surfaces before proposing extraction.

File length is a maintainability signal, not proof of poor runtime performance. Performance claims require measurements such as construction time, activation time, query count, UI-thread blocking, worker lifecycle, and avoidable reloads. Do not split files to meet an arbitrary line-count target.

### 2. Full-product UX review

Review complete user journeys, not isolated widgets. Find workflows that are unclear, slow, repetitive, hard to recover from, inconsistent, permission-confusing, or dependent on hidden knowledge. Include first use, keyboard and mouse paths, validation, loading, empty, error, permission-denied, cancellation, and success states.

Prioritize the journeys used most by non-technical shop owners and cashiers. Every recommendation must identify evidence, root cause, affected journey, and measurable acceptance criteria.

### 3. Scattered views and dialogs

Map every view, dialog, widget, settings page, worker, and service it depends on. Identify unclear ownership, duplicate implementations, business logic in UI classes, blocking work on the UI thread, inconsistent lifecycle handling, and dialogs that belong to a feature module rather than a global bucket.

The goal is understandable ownership and deep modules with small interfaces—not directory churn or arbitrary file movement.

### 4. Opaque text backgrounds and inconsistent surfaces

Audit both themes for labels or text widgets that expose rectangular or mismatched backgrounds over their parent surface. Determine whether each defect comes from QSS selector scope, palettes, inline styles, child widgets, or platform rendering. Fix root causes through shared tokens/selectors where safe; do not apply broad transparency rules without checking controls that legitimately need opaque surfaces.

### 5. Repeated update and hardware checks

Inventory every entry point and implementation for update checking and hardware diagnostics. Start by evaluating the existing `cbpos/core/services/update_service.py`, `cbpos/core/services/hardware_test_service.py`, and shared asynchronous UI adapters as the ownership seams. Multiple entry points may be useful, but duplicate rules, network calls, device probing, status mapping, or error handling are not. Propose new structure only for responsibilities those existing modules demonstrably cannot absorb; keep different UI entry points as thin adapters.

### 6. Help and About placement

Evaluate removing Help and About from the Sales side panel and placing them in Settings, potentially in a tabbed support/about area consistent with other Settings pages. Preserve fast contextual help for the Sales workflow—such as F1 or another keyboard-accessible path—even if the persistent side-panel items move.

This is a direction to validate through the navigation and information-architecture audit, not permission to move controls before Phase U.0 establishes the final design.

## Retrospective integrity-audit contract

Record the audit in `docs/remediation/phase-u/RETROSPECTIVE_INTEGRITY_AUDIT.md`. A provisional pass may start against `69fd64a`, but completion requires a mandatory delta pass against the exact final Phase 10B `main` SHA.

- **Scope:** completed remediation work, prioritized by irreversible or cross-cutting risk: money and tax truth, stock and purchasing, sync and PostgreSQL, permissions and audit, migrations and upgrade paths, UI-thread/worker boundaries, warranty history, and every merged Phase 10B batch. Include #937 because its final Claude whole-PR review was blocked by a usage limit before merge.
- **Risk classes:** R1 blocks release or risks data, money, tax, security, schema, or historical corruption; R2 is an important correctness or recovery defect without that immediate impact; R3 is an evidence gap or maintainability debt. Fix every R1 before Phase U product-code work. Give every surviving R2/R3 a linked issue, evidence-backed disposition, and owner decision where product scope is involved.
- **Evidence per area:** identify the issue/PR and reviewed SHA, state the invariant, inspect the responsible seams and their callers, give each finding a concrete state/input → wrong behavior, record focused test or reproducible evidence, and link its repair or disposition. Record SQLite/PostgreSQL, Windows, printer, or hardware limits honestly; absence of evidence is not a pass.
- **Method:** review highest-risk invariants first, then sample lower-risk batches by changed seam and failure impact. Do not substitute green CI for inspection, and do not silently repair product code inside the audit-doc branch; verified repairs use their own issue, branch, PR, and fresh review loop.
- **Completion:** every scoped area and discovered finding has a recorded disposition; the final-Phase-10B delta is complete; no R1 remains; required focused checks and the final suite state are recorded; and a fresh whole-audit review has no surviving findings.

## Phase U.0 — mandatory discovery and re-baseline

Under D42, U.0 may begin provisionally against post-#937 `main` (`69fd64a`). “Final Phase 10B” is reached only when **every** checkbox in the canonical Phase 10B exit gate in `phases/phase-10b-shop-workflows.md` passes, including recording the exact final `main` SHA and green post-merge CI in `PROGRESS.md`. Before U.0 can complete, receive owner approval, or authorize product-code implementation, rerun the discovery delta re-baseline and the retrospective integrity-audit delta against that SHA; never rely on the stale 2026-10-29 baseline.

1. **Surface inventory** — enumerate every user-visible view, dialog, settings page, reusable widget, navigation entry point, and state-bearing overlay.
2. **Architecture map** — record ownership, callers, service/worker dependencies, lifecycle behavior, shared modules, duplicate implementations, and oversized responsibility clusters.
3. **Journey audit** — walk the highest-value end-to-end workflows with keyboard and mouse, including all significant UI states and recovery paths.
4. **Visual-system audit** — capture dark/light and English/Sinhala/Tamil evidence at the supported release size; inspect typography, transparency, hierarchy, spacing, controls, focus, and state consistency.
5. **Performance baseline** — measure representative view construction and activation, query behavior, UI-thread blocking, worker lifetime, and unnecessary reloads before attributing slowness to code structure.
6. **Existing-issue reconciliation** — verify every issue #963–#975 and every `UI_SYSTEM_AUDIT.md` finding against current code and evidence.
7. **Root-cause grouping** — consolidate findings by shared cause and user journey rather than creating one issue for every visual symptom.
8. **Owner review** — present a deduplicated issue map with dependencies, risk, scope, and proposed batches before creating or expanding implementation issues.

Follow the established UI audit discipline: trace each reported issue and expert recommendation to current code; maintain one `docs/remediation/phase-u/issues/<screen>_issues.md` file per audited screen plus `docs/remediation/phase-u/ISSUES_SUMMARY.md`; record uncertain platform behavior as needing Windows verification; and complete the audit before fixes begin.

## Discovery deliverables

U.0 is complete only when all of the following exist:

- a current UI surface and navigation inventory;
- a UI architecture and ownership map;
- a journey-based UX audit;
- a dark/light and trilingual visual audit with evidence;
- a measured performance baseline;
- a completed `docs/remediation/phase-u/RETROSPECTIVE_INTEGRITY_AUDIT.md`, with every surviving release or data-integrity blocker resolved;
- a disposition for every existing Phase U issue and audit finding;
- an evidence-derived implementation-batch proposal, using U.1–U.7 only where the evidence supports those boundaries, with dependencies and acceptance criteria;
- the exact final Phase 10B `main` SHA and green post-merge CI used for the delta re-baseline;
- explicit owner approval of that proposal before implementation issue creation.

## Proposed delivery sequence after discovery

This sequence is a provisional naming hypothesis, not a required seven-batch output. U.0 evidence may merge, split, rename, reorder, defer, or reject these boundaries before owner approval:

- **U.0 — Discovery and re-baselining**
- **U.1 — UI architecture and ownership**
- **U.2 — Shared design-system foundation**
- **U.3 — Shell, navigation, Help/About, update and hardware consolidation**
- **U.4 — Core user journeys**
- **U.5 — Visual consistency and surface defects**
- **U.6 — Reports**
- **U.7 — Full-app migration and release gate**

## Issue-creation rule

Do not create six broad implementation issues directly from the concerns above. Start with one Phase U parent epic and one U.0 discovery/re-baseline issue when Phase U begins. Create or revise implementation issues only after the Phase 10B exit gate, final-SHA delta re-baseline, retrospective integrity-audit gate, and owner approval of the evidence-backed, deduplicated issue map.
