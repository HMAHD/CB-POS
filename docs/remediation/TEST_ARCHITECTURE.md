# Test Architecture Plan

**Status:** layers implemented on 2026-10-29 (branch `chore/test-architecture`). Triage and deletion (step 2 below) are still pending owner review.

## Results after the restructure (2026-10-29, 4-core Mac, `-n auto`)

| Run | Tests | Time | Notes |
|---|---|---|---|
| Before: all of `tests/unit` | 2,821 | 6 min 32 s (24.8 min summed) | 29 failed / 83 errors on `main` |
| `-m "domain or guardrails"` (fast loop) | 679 | **15 s** | 1 pre-existing guardrail failure |
| `-m "ui or integration"` | 2,144 | 6 min 11 s | 14 pre-existing failures |

- **Most of the "29 failed / 83 errors" was one app bug:** `SideMenu` read `_nav_buttons` before creating it. Fixed in PR #951.
- **Remaining pre-existing failures:**
  - #950 (report-viewer layout, 10);
  - `test_zero_inline_stylesheets_in_ui`;
  - `test_display_scaling`;
  - `test_font_metrics_and_registration`;
  - `test_shift_management_dialog` (2).
- **Domain and guardrail tests skip the per-test `gc.collect()` and heap scan for QThreads**, which only widget tests need (`tests/conftest.py`).
- **Every test is marked from its folder**, and a test outside `tests/<layer>/` fails collection.
- **1,814 log lines** read "theme change callback: wrapped C/C++ object … has been deleted". Theme callbacks are registered without an owner, the same bug class as #918. Fix them with that issue.

## What we measured (2026-10-28)

- `tests/unit/` holds 355 files and 2,289 tests. A full run takes about 20 minutes, even with `-n auto`.
- 56 files are named after UI cosmetics (colour, spacing, tint, width, icon, font, theme, button, mnemonic, redesign…). Most are one-off checks written for one visual fix.
- 17 files read source code as text (`read_text()` / `inspect.getsource`). That checks how the code is written, not how it behaves, so these tests break on harmless refactors.
- Almost everything is labelled "unit", but many tests build real Qt widgets and real databases. There is no split between fast and slow tests.

## Root cause

Every fix added a new test file shaped like that one fix. Nothing retires old tests, and nothing marks which tests guard money, stock, security or data, and which only pinned a pixel. The suite grows forever, and its cost grows with it.

## Target architecture (4 layers)

| Layer | Folder / marker | What belongs there | Speed budget | When it runs |
|---|---|---|---|---|
| **1. Domain** | `tests/domain/` | Service behaviour through public APIs on an in-memory DB: money, tax, stock, ledgers, refunds, permissions, sync apply. **The invariant suites** (`test_money_invariants.py`, `test_stock_invariants.py`, `test_report_reconciliation.py`) live here | ≤ 2 min total | Every commit, plus CI |
| **2. Guardrails** | `tests/guardrails/` | AST and static rules for the whole codebase: no `float` money, no `destroyed.connect`, permission codes enforced, i18n key parity, no `quantize` without a rounding mode, no UI→DB imports. **One parametrised test per rule** replaces dozens of one-off source-text tests | ≤ 30 s | Every commit, plus CI |
| **3. UI behaviour** | `tests/ui/`, marker `ui` | pytest-qt tests of **flows**: keyboard path, enabled/disabled state, permission gating, error shown. No colours, pixels or QSS values | ≤ 5 min | CI, plus the end of each batch |
| **4. Integration** | `tests/integration/`, markers `postgres`, `two_machine`, `slow` | PostgreSQL, two-machine sync, migrations from v1.2.2/v1.3.0, real threads, printing to PDF | Unlimited | CI nightly, plus before release |

**Visual design** (colours, spacing, fonts) is **not unit-tested**. It's checked by the §0.7 UI gate screenshots, plus at most one guardrail ("no hard-coded hex colours outside QSS").

## Rules for new tests (add to RELEASE_PLAN.md §0.8 once approved)

1. A regression test goes into the **existing file for that service or flow**, never into a new file named after the issue. Name the test `test_issue_<n>_<behaviour>` so its origin is traceable.
2. Test behaviour through public APIs and stored facts. Never read source code as text. If it's a code rule, it belongs in a guardrail.
3. Don't test styling. Don't assert QSS strings, colours or pixel sizes.
4. Every test belongs to exactly one layer (folder or marker). Default local run: `pytest tests/domain tests/guardrails` in under 3 minutes.
5. Writing a new test that duplicates an old one means deleting or merging the old one.

## Migration plan

Step 3 (move and mark) is **done**. Steps 1, 2 and 4 remain.

1. **Measure:** run `pytest tests/unit -n auto --durations=50` once and save the output. Run with `--cov=cbpos --cov-context=test` to find tests that add no unique coverage.
2. **Triage each file** into: Keep → domain/ui/integration; Convert → guardrail (the 17 source-text files); Delete (pure cosmetics, or superseded by an invariant suite). List the decisions in a table in the PR so the owner can review them. **Delete nothing without that review.**
3. Move the files (`git mv`), add the markers, and update `pyproject.toml` markers and the CI jobs (fast = domain + guardrails on every PR; full = everything nightly).
4. Expected result: about 900–1,200 meaningful tests, a fast run under 3 minutes, and the full run under 8.

**Owner decision needed:** approve the layers and the "no cosmetic unit tests" rule before step 2.
