# Phase Spec Template

Every `phases/phase-XX-*.md` follows this structure exactly. The reader is an implementation agent with **no memory** and weaker independent judgment. It will do what the spec says and only what the spec says. So the spec must contain:

- **the decisions**, with reasons, so the agent doesn't re-decide them
- **the evidence**, as `file:line` plus short code excerpts, so the agent can verify instead of trusting
- **the traps**, so the agent doesn't take the obvious-but-wrong path

Write in plain English, using concrete names and no filler adjectives.

---

```markdown
# Phase <N> — <Theme>

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> This spec was verified against `origin/main` @ `4bcc837` on 2026-10-28. Re-verify every `file:line` before editing (§0.1 step 7).

## Phase brief

**Outcome (end state):** <what is true for the shop owner when this phase is done, 3–6 bullets, user terms>

**Depends on:** <phases/batches/issues that must be merged first, and why>
**Unblocks:** <what can start after>

### Issues

| # | Title | Sev | Size | Batch | Gate |
|---|---|---|---|---|---|
| #NNN | short title | high | M | 1 | agent / human |

### Subsystem map (read before any batch)

<For each subsystem this phase touches: key files, key classes and functions with file:line, what they do in one line, and how data flows (UI → service → model). Name the existing helpers to reuse (money rounding, permission_helper, destroy_hooks, dialog_footer, workers, audit logging, i18n), with paths.>

### Domain invariants this phase must preserve

<Numbered list of rules, e.g. "A sale's refunded quantity per line never exceeds sold quantity". The tests in this phase should assert them.>

### Batches (one PR each)

| Batch | Branch | Issues (in order) | Why grouped |
|---|---|---|---|

---

## Batch <N>.<B> — <name>

**Branch:** `fix/p<N>-b<B>-<slug>` · **Issues:** #a, #b · **Order:** #a before #b because …

### #<number> — <title>

**Severity:** <x> · **Size:** S/M/L · **Type:** bug / security / feature / docs · **Gate:** agent | human (<what needs deciding>)
**Skills:** <e.g. systematic-debugging → tdd → ponytail; impeccable(harden) for the dialog; egm-review for the design note>

**Problem.** <2–5 sentences: what the shop owner or cashier experiences, and why it matters (money, data, security, trust)>

**Evidence and root cause.** <Verified at 4bcc837. Each point is `path/to/file.py:123` (`function_name`) plus a ≤10-line excerpt and one line explaining why it is wrong. Name the true root cause, not the symptom.>

**Fix design.**
- *Recommended:* <the approach, at which layer, and why it is the best one>
- *Rejected alternatives:* <alternative → why not (one line each)>
- *Data/schema:* <migration needed? columns, types, defaults, backfill, SQLite batch mode, PostgreSQL notes; or "none">
- *Sync/network impact:* <does this data sync? protocol change? or "none">

**Implementation steps.**
1. <file → function → exact change. Concrete enough to follow without re-deciding.>
2. …

**Tests (write first).**
- `tests/domain/test_<x>.py::test_issue_<n>_<behaviour>`: Given … When … Then … (assert stored facts / exact Decimals). Fails today because …
- <edge-case tests>

**UI/UX spec.** <only if UI is touched: layout, states (loading/empty/error/success), exact English copy for new i18n keys (key → text), keyboard behaviour, focus, permission-aware visibility, both themes, si/ta length. Reference the nearest existing screen to copy. Otherwise: "No UI change.">

**Do NOT.**
- <specific traps for this issue: the tempting wrong fix and why it is wrong>

**Edge cases.** <list>

**Acceptance criteria.**
- [ ] <from the issue body, plus anything the analysis added>

**Verify.** <commands + manual check steps>

**Stop & Ask if.** <specific triggers, with the open question pre-written in §0.5 format and a recommended answer — or "None expected.">

---

## Phase exit gate
- [ ] <phase-level checks: all issues done, full suite, migrations on SQLite + PG, manual checks…>

## Newly discovered defects
<Defects found while writing this spec that have NO existing issue: id NEW-<phase>-<n>, title, severity, evidence file:line, description, suggested batch. The plan owner files them on GitHub and replaces the id with the issue number.>
```
