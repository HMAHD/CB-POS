# CB POS — Agent Rules (always loaded)

You are fixing CB POS, a free trilingual (Sinhala/English/Tamil) PyQt6 + SQLAlchemy point-of-sale app for small Sri Lankan shops, before its public release. Shops will trust it with their money, stock and tax records. Work like a careful senior engineer: correct first, small diffs, evidence for every claim.

## Before anything else

The work is driven by **`docs/remediation/RELEASE_PLAN.md`**. When the human says "start phase N", "continue" or "next":

1. Read `CLAUDE.md`. It holds the project rules for every agent, not just Claude.
2. Read `docs/remediation/RELEASE_PLAN.md` **Part 0** fully: the operating manual.
3. Read `docs/remediation/PROGRESS.md` to see where work stopped, including the Handoff note.
4. Read the phase spec `docs/remediation/phases/phase-NN-*.md` **fully**.
5. Read `docs/remediation/DECISIONS.md`. Those decisions are locked.
6. Follow the session start protocol in RELEASE_PLAN.md §0.1.

Re-read the phase spec at the start of each batch. Do not work from memory of it.

## The ten rules you must never break

1. UI code never touches the database. Services own business logic. Fix bugs at the layer that owns the rule.
2. Money is `Decimal` built from strings, rounded only through the approved `ROUND_HALF_UP` helper. Never `float`.
3. Every stock change writes a `StockMovement`. Every balance change writes a ledger row equal to the real change. Every critical action is permission-checked and written to `AuditLog`.
4. A failed operation leaves no partial state. Use one transaction, and prove it with a failure-injection test.
5. Write a failing regression test `test_issue_<n>_...` before the fix. Never weaken, skip or delete a test to go green.
6. No blocking work (DB reports, printing, PDF, email, bcrypt, network) on the Qt UI thread. Never connect `destroyed` to a lambda; use `call_on_destroyed`.
7. Every user-facing string goes through `_t()`, with keys in `en.json`, `si.json` and `ta.json`. Write natural, casual Sinhala/Tamil per §0.12 P7. If unsure, use the English text and list the key for human review.
8. Schema changes need an Alembic migration that works on SQLite and PostgreSQL. Never edit a shipped migration.
9. Fail closed: on ambiguous or error states, stop and inform. Never fall back to "fresh", "defaults" or "allow".
10. Don't guess product, tax, legal or UX decisions. Use the **Stop & Ask** protocol (RELEASE_PLAN.md §0.5, `grill-me` / `grill-with-docs`) and record the answer in DECISIONS.md.

## UI/UX is release-critical

Any UI-touching fix must pass the **UI gate** in RELEASE_PLAN.md §0.7:
- trace the cause in code first
- impeccable `critique` before, then `audit` / `harden` / `clarify` / `polish` after
- keyboard-only walkthrough in the running app
- before and after screenshots in dark and light themes, in English and si/ta, at 1366×768, attached to the PR
- every state designed: loading, empty, error, success, permission-denied
- no clipped Sinhala/Tamil
- reuse `make_dialog_footer`, `batch_table_update` and the existing card and master-detail patterns

## Commit and close (never skip, RELEASE_PLAN.md §0.10)

- One branch and one PR per batch (`fix/p<phase>-b<batch>-<slug>`) from fresh `origin/main`.
- **Commit each issue as soon as its tests pass** (one Conventional Commit per issue), then **push** right away.
- At batch end: full suite, then PR with `Fixes #n`. Merge with `gh pr merge --merge` after CI is green and the human approves.
- **Verify every issue is closed** (`gh issue view <n> --json state`). Close any that remain with a comment giving the root cause, fix, test and PR. Leave an issue open with `ready-for-human` only if a "⚠️ Verify on Windows" check is pending.
- Update the epics (#832, #922, #820, #944) and PROGRESS.md.
- **No AI attribution** anywhere: no `Co-Authored-By`, no "Generated with".
- Never `--no-verify`, never force-push `main`, never squash or rebase merge.

## Standing owner policies

Read RELEASE_PLAN.md §0.12 (P1–P13). They cover:
- merge-not-squash and no watermark
- test once per batch
- understand before fixing
- the i18n quality checklist (casual register, loanword limit, param parity, `--strict` validation)
- ledger-only balances (ADR 0001)
- redemption-as-discount (ADR 0002)
- SSCL code is correct (the docs are wrong)
- 1.3.0 is pre-release only

## Tools

- Use `graphify query "<q>"` / `graft ask "<q>" --source` to find code.
- Run `graft callers <symbol> --depth all` before changing a shared symbol.
- Run `graphify update .` after code changes.
- Fast loop after each issue: `uv run python -m pytest -m "domain or guardrails" -q -n auto` (~15 s). Tests live in `tests/{domain,guardrails,ui,integration}/` (RELEASE_PLAN.md §0.8).
- Run the full test suite once per batch:

  ```bash
  QT_QPA_PLATFORM=offscreen uv run python -m pytest -q -n auto
  ```

- Lint with `uv run pre-commit run --all-files`.
