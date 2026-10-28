# CB POS Release Remediation Plan

**Owner:** HMAHD · **Created:** 2026-10-28 · **Baseline commit:** `origin/main` @ `4bcc837`
**Scope:** every open GitHub issue in `HMAHD/CB-POS` on 2026-10-28 (155 issues: 132 release fixes, 23 former-backlog features, 3 tracking epics), plus any defect found while executing this plan.
**Supersedes:** `docs/superpowers/plans/2026-10-23-non-backlog-issue-remediation.md`. All 12 locked decisions in that plan carry over unchanged into [DECISIONS.md](DECISIONS.md).

This plan is written for an AI coding agent (Gemini in Antigravity or Gemini CLI) working with no memory of earlier sessions. Everything that agent needs is in this folder:

| File | What it is | When to read it |
|---|---|---|
| [`/GEMINI.md`](../../GEMINI.md) | The short always-loaded rules card | Loaded automatically every session |
| **`RELEASE_PLAN.md`** (this file) | Part 0: the operating manual. Part 1: the phase roadmap | At the start of **every** session, fully |
| [`phases/phase-XX-*.md`](phases/) | One self-contained spec per phase: every issue with root cause, fix design, tests, UI spec, traps and acceptance criteria | The phase you are working on, fully, before touching code |
| [`DECISIONS.md`](DECISIONS.md) | Decisions the owner has locked. Append-only | Before designing any fix; after every Stop & Ask answer |
| [`PROGRESS.md`](PROGRESS.md) | Status of every issue, the current batch, open questions, handoff notes | At session start (to find where you are) and after every issue |

---

# Part 0 — Operating Manual (read every session)

## 0.1 Session start protocol

When the human says **"start phase N"**, **"continue phase N"** or **"next"**, do exactly this, in order, before writing any code:

1. Read `CLAUDE.md` at the repo root. Its rules are the project's rules for every agent, not only Claude.
2. Read this file, Part 0, end to end.
3. Read `docs/remediation/PROGRESS.md`. Check that every row marked `done` is actually closed on GitHub (`gh issue list --state open`), and fix any that isn't (§0.10 step 5). Find the first issue of phase N that is not `done`. If a **Handoff** note exists at the bottom, read it; it is the previous session talking to you.
4. Read `docs/remediation/phases/phase-N-*.md` end to end. Do not skim it: the "Do NOT" and "Stop & Ask" sections of each issue are there because an agent made that mistake before.
5. Read `DECISIONS.md` and `CONTEXT.md` (domain glossary), plus any `docs/adr/*.md` that touches the subsystem.
6. Run `git status`, `git fetch origin`, and confirm you are on the batch branch named in the phase file (create it from fresh `origin/main` if not).
7. **Re-verify before trusting.** The phase file cites `file:line` from commit `4bcc837`. Code moves. Before editing, open each cited location and confirm the root cause is still there. If it has moved, find it with `graphify query "<question>"` or `graft ask "<question>" --source`. If the bug is already fixed, record evidence in PROGRESS.md and move on.
8. Tell the human, in at most 5 lines: which batch, which issues, the branch, and anything blocked on a human gate.

At the end of every session, or when your context is getting long, write a **Handoff** note at the bottom of PROGRESS.md covering: what is done, what is half-done (file and function), what you were about to do next, and any surprise. The `handoff` skill does this well.

## 0.2 Non-negotiable engineering rules

These are absolute. Breaking one is a failed fix even if tests pass.

**Architecture**
- UI (`cbpos/ui/**`) never touches the database. No `Database()`, no `session`, no ORM query in views, dialogs or widgets. UI calls a service; services own business rules and I/O.
- Services (`cbpos/core/services/**`) never import PyQt widgets.
- Put the fix at the **narrowest layer that owns the rule**. A money rule belongs in the service that writes the ledger, not in the dialog that happens to call it. An authorization rule belongs at the service boundary **and** is reflected in the UI (hide or disable), never in the UI alone.
- Reuse existing helpers before writing new ones. Each phase file lists the ones that exist. Search before creating: `graft grep "<name>"`.

**Money and quantities**
- `decimal.Decimal` for every amount, rate and cost. Construct it from strings (`Decimal("0.18")`), never from floats. `float()` on money anywhere in a diff is a bug.
- Round with the single approved helper (`ROUND_HALF_UP`, decision D4). Never call `.quantize()` with a different rounding mode, and never round in the UI.
- Quantities have 3 decimal places (weighed items). Amounts have 2.
- Stored totals must reconcile: `sum(lines) == subtotal`, `net + VAT == gross`, `ledger delta == balance change`. Tests should assert reconciliation, not just a single value.

**Data integrity**
- Every stock change writes a `StockMovement`. Every customer or supplier balance change writes a ledger row whose amount equals the actual change, after any clamping.
- Every critical action (void, refund, price change, discount over cap, permission change, drawer open, stock adjustment, user change) checks permission with `check_permission_with_override()` and writes an `AuditLog` row.
- A failed operation leaves **no partial state**: no orphan documents, no burned sequence numbers unless documented, no half-applied stock. Do it in one session transaction and prove it with a test that injects a failure mid-way.
- Historical documents are facts. Never recompute an old sale's tax, price or cost from current settings. Snapshot what you need at write time.

**Schema**
- Any model change needs an Alembic migration in `alembic/versions/`, written by hand or autogenerated and then reviewed by hand. It must be idempotent-safe for SQLite **and** PostgreSQL (batch mode for SQLite `ALTER`).
- Never edit a migration that has shipped. Add a new one.
- Update `DatabaseSetupService.create_empty_database()` and `scripts/seed.py` when defaults change.
- Run `uv run alembic upgrade head` on a copy of a seeded DB and on an empty DB.

**Threading and Qt lifecycle**
- Never block the UI thread with DB-heavy reports, printing, PDF, email, bcrypt, network or file I/O. Use a `QThread` or worker with signals. Results return to the UI only through signals.
- Never connect `obj.destroyed` to a lambda or nested function (segfault, #392/#718/#918). Use `call_on_destroyed(owner, cb, *args)` from `cbpos/core/utils/destroy_hooks.py`.
- Long-lived widgets register `register_language_callback(self.retranslate_ui, owner=self)`. Dialogs call `retranslate_ui()` in `__init__` only.
- A worker must not deliver results into a widget that has been hidden or destroyed. Guard with an owned lifecycle or a generation token (see #846).

**i18n (trilingual is a product principle, not polish)**
- No user-facing English literal in code. Every string goes through `_t("section.key", **params)`.
- Add every new key to `cbpos/i18n/en.json`, `si.json` and `ta.json`. Validate with `uv run python scripts/validate_translations.py`.
- Sinhala and Tamil must be natural, casual shop language. Read the whole sentence, not word by word. Allow at most 1–2 English loanwords per sentence. Use native words where a common one exists: "export" is අපනයනය / ஏற்றுமதி. Look up existing vocabulary in the JSON files before inventing a term.
- If you are not confident in a Sinhala or Tamil translation, use the English text as the value, add the key to the **i18n review** list in PROGRESS.md, and move on. A wrong translation is worse than an English fallback.
- Any key containing `&` must pass `tests/unit/test_ampersand_mnemonic_escaping.py`.

**Security**
- Fail closed. On an ambiguous state (DB error, missing key, unknown schema version, certificate mismatch), stop and tell the user. Never fall back to "fresh install", "defaults" or "allow".
- Never log PINs, passwords, tokens or secrets. Never weaken an existing check to make a test pass.

**Branding**
- Every customer-facing output (receipt, invoice, PDF, report, email) keeps the CB POS name and website.

## 0.3 Forbidden actions

- Do **not** edit, skip, `xfail` or loosen an existing test to make it pass. If an existing test encodes the bug, change it in a separate commit whose message explains why the old expectation was wrong, and cite the issue.
- Do **not** mock the unit under test, or mock away the database in a test that is about data. Use the `db_session` / `test_engine` fixtures in `tests/conftest.py`.
- Do **not** catch `Exception` and continue silently. Catch the specific error, log it, and surface a translated, actionable message. Returning `None` on failure is how #892 happened.
- Do **not** "fix" by adding a UI-only guard to a service-level bug.
- Do **not** bundle unrelated refactors, renames or reformatting into a fix PR. Note them in PROGRESS.md as follow-ups.
- Do **not** run `scripts/seed.py`, `drop_all`, or any destructive DB command against anything except a throwaway copy.
- Do **not** use `git commit --no-verify`, force-push to `main`, squash-merge, or rebase-merge. PRs merge with `gh pr merge --merge`.
- Do **not** add `Co-Authored-By`, "Generated with", or any AI attribution to commits or PRs. The owner has forbidden it.
- Do **not** close an issue until its acceptance criteria and the phase gate pass, and the PR is merged.
- Do **not** guess a business, tax, legal or UX decision that the phase file marks as a human gate. Use Stop & Ask (§0.5).
- Do **not** invent Sinhala/Tamil text, tax rules, IRD requirements, legal wording or customer evidence.

## 0.4 The fix loop (for every issue)

Size labels in the phase files: **S** is under 1 hour with 1–2 files. **M** is a half day or a few files plus tests. **L** means a design note first, schema or protocol changes, or many files.

```
1. UNDERSTAND   Read the issue spec in the phase file + `gh issue view <n> --comments`.
                Restate the bug in one sentence in PROGRESS.md (status: in-progress).
2. REPRODUCE    Write the failing regression test FIRST (test_issue_<n>_<behaviour>).
                Run it. Paste the failure line into PROGRESS.md. No failing test = no fix
                (exceptions: pure UI layout, docs, hardware: use the manual check instead).
3. ROOT CAUSE   Confirm the cause the phase file names. If evidence disagrees, STOP:
                use systematic-debugging, then record the real cause.
4. DESIGN       S: follow the phase file. M/L: write a 10–30 line design note in the PR
                description first (what changes, invariants, migration, rollback).
                L or anything touching money/sync/schema/security: run a Goldfish review
                (§0.6) on the design note before coding.
5. IMPLEMENT    Smallest change that fully solves the root cause (ponytail).
                Follow the phase file's step list and "Do NOT" list.
6. VERIFY       Focused test → subsystem tests → lint → (batch end) full suite. §0.8.
7. SELF-REVIEW  Run the ponytail-review checklist on your own diff (§0.6). Fix findings.
8. RECORD       PROGRESS.md: status, PR, test names, notes. New bug found? §0.9.
```

## 0.5 Stop & Ask protocol (grill-me)

You are an implementer, not the product owner. When you hit one of these triggers, **stop coding and ask the human**:

- The phase file marks the issue `Gate: human` or lists an open question without a locked answer in DECISIONS.md.
- The code contradicts the phase file's root cause, and the right fix changes behaviour the user can see.
- The fix needs a new setting, a new permission, a schema change the phase file does not describe, or a sync protocol version bump.
- Tax, legal, accounting, licensing or receipt-format behaviour is ambiguous.
- Two acceptable designs differ in user-visible behaviour, or in data that cannot be migrated back.
- You would need to change more than ~3 files outside the ones the phase file names.
- A test you did not write starts failing and you do not understand why.

**How to ask.** Ask one question at a time, in this format:

```
QUESTION (#<issue>): <one-sentence decision needed>
Context: <2–4 lines: what you found, with file:line>
Options:
  A) <option> — consequence for the shop owner / data
  B) <option> — consequence
Recommendation: <A or B> because <reason>.
```

For a design with several connected unknowns, ask the human to run **`/grill-with-docs`** on the topic, or read `~/.gemini/config/skills/grill-with-docs/SKILL.md` and run that interview yourself. Use `/grill-me` when no docs need to be written. After the answer:
1. Append it to `DECISIONS.md` as `D<next>` with date, issue and the exact decision.
2. If it defines a domain term, add it to `CONTEXT.md`. If it is architectural, add an ADR in `docs/adr/`.
3. Remove the question from the Open Questions table in PROGRESS.md.

While waiting for an answer, continue with a different issue in the same batch that is not blocked.

## 0.6 Skill routing

The skills below are installed for Gemini in `~/.gemini/config/skills/` and the EGM plugin in `~/.gemini/config/plugins/egm/`. Most are `disable-model-invocation`, which means you cannot call them as a tool. Either:
- **(a)** ask the human to type the slash command, or
- **(b)** read the skill's `SKILL.md` file and follow its steps yourself.

(b) is the default. Do (a) when the skill needs subagents you cannot spawn, such as EGM Goldfish reviews.

| When | Skill | How to use it here |
|---|---|---|
| Every session start | `using-superpowers` | Check which skill applies before acting |
| Unsure which skill or flow fits | `ask-matt` | Router over the installed skills |
| Any bug fix (default for every issue) | `systematic-debugging` → `tdd` (or `test-driven-development`) | Reproduce with a failing test before any fix |
| Hard, intermittent or concurrency bug | `diagnosing-bugs` | Build a feedback loop, rank hypotheses with evidence |
| Writing the change | `ponytail` | Smallest complete change; no speculative abstraction |
| Reviewing your own diff before PR | `ponytail-review` (+ `requesting-code-review`) | Logic, safety, load, tests, speed, every line needed |
| Design decision / unclear requirement | `grill-me` / `grill-with-docs` | §0.5. `grill-with-docs` also writes ADR + glossary |
| L-size or money/sync/schema/security design | `egm-draft` → `egm-review` (human types `/egm-review <file>`) | Goldfish = zero-context reviewers who catch the assumptions you can't see |
| Schema, data or protocol change | `migration` rules in §0.2 + `domain-modeling` | Reversible, both DBs, upgrade-tested |
| Boundary or module redesign (sync identity, refund engine, permissions model) | `codebase-design` / `improve-codebase-architecture` | Deep modules, small interfaces |
| Any UI change | `impeccable` (read `~/.gemini/skills/impeccable/SKILL.md`) | §0.7. Use `audit`, `critique`, `harden`, `clarify`, `polish` |
| Tax / legal / library facts | `research` | Primary sources only (IRD, Gazette, official docs); cite URL + date in the PR |
| Finished batch | `verification-before-completion` → `finishing-a-development-branch` → `pr` | Evidence before claims |
| Reviewing a PR comment | `receiving-code-review` | Verify, don't comply blindly |
| Context getting long / end of session | `handoff` | Write the Handoff block in PROGRESS.md |
| Last message confused the human | `wait-what` | Re-pitch in plain words |
| After code changes | `graphify` (`graphify update .`) | Keep the knowledge graph current |

**Code navigation tools** (use them before grepping):
- `graphify query "<question>"`, `graphify explain "<concept>"`, `graphify path "<A>" "<B>"`
- `graft ask "<task>" --source`: ranked code with `file:line`
- `graft grep "<literal>"`: every occurrence
- `graft callers <symbol> --depth all`: run this before changing any shared symbol, to see what else breaks

## 0.7 UI/UX standard (enterprise quality, impeccable): release-critical

**UI/UX is release-critical, not polish.** The users are non-technical shop owners who learn by doing. A correct fix behind a confusing, clipped or English-only screen is a failed fix. Any issue that touches a view, dialog, widget, QSS, receipt or PDF layout cannot be marked done until the **UI gate** below passes.

Read `PRODUCT.md` (users, principles) and `docs/plans/2026-10-18-enterprise-design-system-audit.md` (known UI debt) before UI work. CB POS is a **native PyQt6 desktop app styled with QSS**. Ignore web-only advice from any skill: no HTML, no CSS frameworks, no browser live mode.

Users are non-technical shop owners and cashiers. Many are not fluent in English, run modest Windows PCs, and serve a queue of customers. Every UI change must meet all of the following:

1. **Keyboard first.** Every action is reachable by keyboard. Tab order is logical. Enter runs the primary action and Esc cancels. Checkout-path dialogs must never steal focus from the barcode input unexpectedly. Numpad buttons use `Qt.FocusPolicy.NoFocus`.
2. **One primary action per dialog.** Footer order `[Primary] [Cancel]`, using `make_dialog_footer` where it exists. Red (`danger`) is only for destructive actions, never for Cancel.
3. **Every state designed.** Loading (worker running: disable the trigger, show progress), empty (explain what to do), error (what happened, and what the user can do next, in their language), success (quiet confirmation, no modal for routine success).
4. **Errors are actionable and translated.** "Couldn't save the sale because the printer is offline. The sale is saved; reprint from History." Never a raw exception, never a stack trace, never English-only.
5. **Prevent, then confirm, then undo.** Disable impossible actions (for example, Refund on an already-refunded sale) rather than erroring after the click. Confirm destructive actions with the consequence spelled out ("This voids REC-1042 and returns 3 items to stock").
6. **Text expansion.** Sinhala and Tamil strings run 30–60% longer. No `setFixedSize` on text containers, no clipped labels. Test with `si` and `ta` on a 1366×768 screen.
7. **Both themes.** Style through `objectName` / `class` selectors in **both** `dark.qss` and `light.qss`. Use the palette in CLAUDE.md. No inline `setStyleSheet()` colours.
8. **Consistency over novelty.** Copy the pattern of the nearest existing screen. Do not invent new widget styles in a bug fix.
9. **Permission-aware UI.** Hide or disable what the user can't do, with a tooltip explaining why. The service still enforces it.

10. **Reuse the established UI building blocks** before writing new ones:
    - `make_dialog_footer` (`cbpos/ui/widgets/dialog_footer.py`) for dialog buttons
    - `batch_table_update` for filling any table, so tables never latch invisible across stack transitions (#945)
    - the enterprise card / KPI-grid pattern (Admin Tools hardware tab, Data Safety maintenance tab)
    - the master-detail inspector (Sale History)
    - `qtawesome` icons from `cbpos/ui/resources/icons.py`

    Find the newest screen with the same shape and copy its structure.

**UI gate (every UI-touching issue, no exceptions):**
- [ ] **Before you change anything**, trace why the screen behaves as it does (`file:line`). Suggested "Fix:" text in issue bodies or test reports is often wrong about the code (e.g. a layout already using `QFormLayout`). Verify before following it.
- [ ] Run impeccable's `critique` on the screen before the change. Run `audit`, then `harden` (states and errors), `clarify` (copy) and `polish` after it. Fix every finding, or record it as a follow-up issue.
- [ ] Run the app (`uv run python main.py`, seeded throwaway DB) and walk the real flow by keyboard only, then by mouse.
- [ ] Take **screenshots after the change in dark and light themes, in English and in Sinhala or Tamil, at 1366×768**, plus a "before" screenshot. Attach them to the PR. The owner reviews UI by these screenshots.
- [ ] Check every state: loading, empty, error, success, permission-denied. Check that long si/ta text does not clip.
- [ ] Mark anything that can only be confirmed on the real Windows build (fonts, DPI, printers, scanner timing) as **"⚠️ Verify on Windows"** in the PR and in PROGRESS.md. Never claim it works.
- [ ] Report new UI problems you notice on other screens with the **UI/UX test finding** issue template (`.github/ISSUE_TEMPLATE/ui-ux-test-finding.yml`). Don't fix them in the current PR.

## 0.8 Testing and verification standard

```bash
export QT_QPA_PLATFORM=offscreen
uv run python -m pytest tests/unit/test_<file>.py -v                  # focused, while iterating
uv run python -m pytest tests/unit/ -q -n auto                        # full suite, ONCE per batch before PR
uv run pre-commit run --all-files                                     # ruff lint + format
uv run python scripts/validate_translations.py                        # if any i18n key changed
uv run alembic upgrade head                                           # on a COPY of a seeded DB, if schema changed
graphify update .                                                     # after code changes
```

- **Test once per batch (owner policy).** While fixing an issue, run only the focused test files for your change, plus ruff and translation checks. Run the full suite **once per batch**, in parallel (`-n auto`, about 5 minutes on the 4-core Mac), after merging fresh `origin/main` into the batch branch. If it fails, fix it on the branch and rerun once. A parallel run reshuffles test order, so it exposes leaked global state (logged-in user, config, registries). Fix those leaks; never dismiss them as flaky.
- Every issue gets at least one regression test named `test_issue_<number>_<behaviour>`, in the test file of the service it touches. The test must fail on `main` and pass on the branch. Record both runs.
- Test behaviour through the public service API, not private helpers. Assert on stored DB facts (rows, ledger, movements), not only return values.
- Money tests assert exact `Decimal` values and reconciliation.
- Concurrency and network tests that need PostgreSQL: mark them `@pytest.mark.postgres` and skip when `CBPOS_TEST_PG_URL` is unset. Phase 2 sets up how to run them.
- Hardware issues (printers, scanners, Windows paths) need the manual check in the phase file. Record the result (printer model, OS, photo or log) in the PR.
- A test that needs `time.sleep` is wrong. Use `qtbot.waitSignal` / `waitUntil`.

## 0.9 New defects found while working

When you find a bug that is not part of the current issue:
1. **Do not fix it in the current PR.** Small and in the same function is the only exception, and it still gets its own commit and a mention in the PR.
2. Check it is not already tracked: `gh issue list --state all --search "<keywords>"`.
3. File it:
   ```bash
   gh issue create --title "<what breaks, in user terms>" --label bug --label "severity:<critical|high|medium|low>" --label ready-for-agent --body "<Problem / Evidence (file:line) / Steps / Expected / Found while fixing #<n>>"
   ```
4. Add a row to the **Discovered during remediation** table in PROGRESS.md, with the phase it belongs to. Severity critical or high goes into the current or earliest affected phase. Tell the human.

## 0.10 Git, commit and PR protocol

- **One branch and one PR per batch**: `fix/p<phase>-b<batch>-<slug>`, e.g. `fix/p1-b2-auth-session`. Always branch from fresh `origin/main`.
- Write **one commit per issue** (plus separate test-only or migration commits if that makes review clearer), using Conventional Commits: `fix(refund): forbid voiding an already-refunded sale (#847)`. No AI attribution lines.
- PR title: `Phase <N>.<B>: <batch name>`. Use the `pr` skill for the body. It must contain:
  - `Fixes #a, Fixes #b, …`
  - per-issue: root cause (one line) and fix (one line)
  - the design note for M/L issues
  - test evidence (failing before, passing after)
  - manual checks done
  - migrations and rollback
  - i18n keys added
  - follow-ups filed
### Commit and close protocol (mandatory, never skipped)

1. **Commit each issue as soon as its focused tests pass**, before starting the next issue. Never leave a fixed issue uncommitted, and never carry several issues in one commit. Run `git status` after committing to confirm a clean tree.
2. **Push the branch after every commit** (`git push -u origin <branch>`), so no work is lost if the session ends.
3. At batch end, after the full suite passes, open the PR (`gh pr create`) with the body described above and `Fixes #n` for every issue in it. Then post the PR link and a 5-line summary to the human.
4. **Merge** with `gh pr merge <n> --merge` once CI is green and the human approves. If the human has said "merge when green" for this phase, merging without asking again is allowed.
5. **Close the issues and verify.** After merging, run `gh issue view <n> --json state` for every issue in the batch. Any issue not auto-closed gets closed explicitly:
   ```bash
   gh issue close <n> --comment "Fixed in #<PR> (<merge sha>). Root cause: <one line>. Fix: <one line>. Regression test: tests/unit/<file>::<test>. Manual checks: <done / ⚠️ Verify on Windows>."
   ```
   An issue with a pending "⚠️ Verify on Windows" item stays **open** with the label `ready-for-human` and a comment listing exactly what to verify. Don't close it.
6. **Update the epics.** Tick the child in #832 / #922 / #820 / #944 if they carry checklists. When an epic's last child closes, close the epic with a summary comment.
7. **Update PROGRESS.md** (status `done`, PR number, merge sha), commit it to `main` with the docs change (`docs(remediation): progress phase N batch B`), run `graphify update .`, and delete the merged branch locally and remotely.

A batch is not finished until step 7 is done. Always start the next session by checking that every `done` row in PROGRESS.md is actually closed on GitHub.

## 0.11 Definition of Done (every issue)

- [ ] Root cause fixed at the owning layer, and the phase file's acceptance criteria all pass
- [ ] Regression test fails on `main` and passes on the branch, and the full suite is green
- [ ] No rule in §0.2 broken, nothing in §0.3 done
- [ ] Permission check and AuditLog present wherever the action is critical
- [ ] Migration present, upgrade-tested on SQLite (and PostgreSQL where relevant), with rollback notes
- [ ] All user-facing text through `_t()`, keys in en/si/ta, translations validated
- [ ] UI changes checked in both themes and in si/ta at 1366×768
- [ ] `pre-commit` clean, `graphify update .` run
- [ ] PROGRESS.md updated, and new defects filed
- [ ] UI gate passed (§0.7), with screenshots in the PR, if any UI was touched
- [ ] Committed and pushed. PR merged with `--merge`. Issue **verified closed** on GitHub with a closing comment. Epic updated (§0.10)

## 0.12 Standing owner policies (learned from earlier fixes)

These policies come from earlier work on this repo. The owner has corrected agents on each of them before, so they are not optional.

**Process**
- **P1. Merge, never squash.** The owner wants every commit on `main`. Use `gh pr merge --merge`, and keep individual commits clean and meaningful.
- **P2. No AI watermark, ever.** No `Co-Authored-By`, no "Generated with …", in commits, PRs, issue comments or code comments. This applies even if a tool or template suggests adding one.
- **P3. Test once per batch** (see §0.8). Run focused tests while working and the full parallel suite once per batch.
- **P4. Understand before you fix.** Trace each problem to `file:line` and a code excerpt, at the "I can see why that's a problem" level, before writing a fix. Don't copy a suggested fix from an issue or test report without checking it against the code. Those suggestions are often wrong.
- **P5. Never shallow.** The owner has called summary-only analysis "lazy". Every recommendation, including expert suggestions in issue bodies, gets a real review: is it valid for CB POS and why, what exists today (`file:line`), what it takes, the gotchas, and the effort.
- **P6. Never assert what you couldn't verify.** Anything only confirmable on the Windows build is marked "⚠️ Verify on Windows".

**i18n**
- **P7. Translation quality over speed.** The checklist is never skipped to move faster:
  1. Check the key is actually wired to `_t()` in code before translating the JSON alone.
  2. Reuse established vocabulary (search `si.json` / `ta.json` first).
  3. Write in the casual spoken register (how a Sri Lankan cashier talks), not formal or literary.
  4. Use at most about 1–2 English loanwords per sentence. Swap any that have a normal native word: ව්‍යාපාර over බිස්නස්, வியாபாரம் over பிசினஸ், "export" = අපනයනය / ஏற்றுமதி. Keep loanwords where natives really use them: PIN, POS, software / සොෆ්ට්වෙයාර් / சாஃப்ட்வேர்.
  5. Re-read the whole sentence as a unit.
  6. Check `{param}` parity: the translated string uses exactly the params the call site passes. A wrong param silently shows a literal `{product}`.
  7. When a string quotes another label ("Settings > Hardware"), quote that label's **translated** text, and update the quoting strings if the label changes.
  8. Run `scripts/validate_translations.py --strict` and `test_ampersand_mnemonic_escaping.py`.
  9. Never generate translation content with scripts.
- **P8. Keep the established exceptions in English:** CB POS, ceybyte.com, VAT, SSCL, TIN, GRN, PIN, ID, format codes like `INV-{Y}-{seq:05d}`, and 80mm / 58mm.

**Domain**
- **P9. Points and balances move only by ledger events** (`docs/adr/0001`). A customer's points, credit balance and supplier payable are the sum of their ledger rows. Never set a balance field directly without the matching ledger event.
- **P10. Loyalty redemption is a discount, not a payment** (`docs/adr/0002`). Respect this in refunds, tax and reports.
- **P11. The SSCL formula in code (VAT-exclusive base) is legally correct** under SSCL Act s.3(3)(b). The *docs* are wrong (#818, #831). Don't "fix" the code to match the old docs.
- **P12. Version 1.3.0 is a test pre-release only.** Don't treat its behaviour as shipped or public. The first public build is the one after the §1.3 gate. `CBPOS_FACTS.md`, the website fact sheet, must be re-audited against that build.
- **P13. Branding on every output** (CB POS name + website). It is a business-model requirement.

---

# Part 1 — Roadmap

## 1.1 Phase order

The ordering principle: **data loss and money first, then security, then cross-till correctness, then reporting truth, then hardware and language output, then release paperwork, then new features.** A phase starts only after the phases it depends on have merged their relevant batches.

| Phase | Theme | Issues | Release-blocking | Spec |
|---|---|---|---|---|
| 1 | Destructive safety, authentication, recovery | 13 | Yes | [phase-01](phases/phase-01-safety-auth-recovery.md) |
| 2 | PostgreSQL network mode and LAN multi-terminal sync | 17 | Yes | [phase-02](phases/phase-02-network-multi-terminal.md) |
| 3A | Money: shift cash, payment-method identity, credit ledger, refunds and voids | 14 | Yes | [phase-03a](phases/phase-03a-money-ledger-refunds.md) |
| 3B | Cart and checkout behaviour and operator controls | 12 | Yes | [phase-03b](phases/phase-03b-cart-checkout-controls.md) |
| 4 | Inventory, purchasing (GRN), CSV import | 14 | Yes | [phase-04](phases/phase-04-inventory-purchasing.md) |
| 5 | Permissions, audit, export safety, Qt lifecycle | 11 | Yes | [phase-05](phases/phase-05-permissions-security.md) |
| 6 | Tax calculation and report truth | 16 | Yes | [phase-06](phases/phase-06-tax-reports.md) |
| 7 | Printing, scanning, PDF, multilingual output, UI concurrency | 14 | Yes | [phase-07](phases/phase-07-printing-i18n-hardware.md) |
| 8 | Release, legal, update checks, documentation | 8 | Yes | [phase-08](phases/phase-08-release-legal-docs.md) |
| — | **Public release gate** (§1.3) | — | — | — |
| 9 | Warranty and repairs (epic #820) | 10 (+ epic #820) | Owner's call | [phase-09](phases/phase-09-warranty.md) |
| 10A | Packaging and printing improvements | 4 | No | [phase-10a](phases/phase-10a-packaging-printing.md) |
| 10B | Shop workflow features (stock, catalog, POS) | 8 | No | [phase-10b](phases/phase-10b-shop-workflows.md) |
| 10C | Communication, finance, onboarding features | 10 (+ epic #944) | No | [phase-10c](phases/phase-10c-comms-finance-onboarding.md) |

The tracking epics #832, #922 (pre-release) and #944 (feature backlog) close when all their children close.

## 1.2 Dependencies

```text
Phase 1 (safety/auth/recovery)
   ├──> Phase 2 (network/sync) ──────────────┐
   ├──> Phase 3A (money/ledger/refunds) ──┐   │
   │        └──> Phase 3B (cart/checkout) ─┤   │
   ├──> Phase 4 (inventory/purchasing) ───┤   │
   └──> Phase 5 (permissions/security) ───┤   │
                                          v   v
                                   Phase 6 (tax/reports)
                                          │
                        ┌─────────────────┴─────────────────┐
                        v                                   v
               Phase 7 (printing/i18n)             Phase 8 (release/legal)
                        └─────────────────┬─────────────────┘
                                          v
                                 PUBLIC RELEASE GATE
                                          v
                        Phase 9 (warranty) ──> 10A / 10B / 10C
```

- Phases 2, 3A, 4 and 5 can run in parallel on separate branches once Phase 1 batch 1 (setup safety) and batch 2 (auth/session) are merged.
- Phase 3B needs 3A's refund/payment service changes.
- Phase 6 needs stable transaction semantics from 3A, 3B and 4.
- Phase 9 needs #812 (partial refunds, Phase 3A). #933 (serial capture, 10B) builds on #823 (Phase 9).

## 1.3 Public release gate

- [ ] Phases 1–8 done; zero open `severity:critical` / `severity:high` issues
- [ ] Full suite and pre-commit green on a clean checkout of `main`
- [ ] Upgrade from every shipped release's database to head on SQLite and PostgreSQL
- [ ] Multi-terminal smoke: Main PC and 2 tills, sales, refunds, catalog edits and permission changes all sync
- [ ] #731 / #878 real-printer matrix on Windows: 58 mm, 80 mm, A4, Microsoft Print to PDF
- [ ] English, Sinhala and Tamil receipts, invoices and report PDFs verified on Windows
- [ ] SQLite and PostgreSQL backup → restore round-trip with encrypted settings
- [ ] Accountant sign-off on #810, #814, #831. Legal sign-off on #817
- [ ] Release notes describe only verified behaviour

## 1.4 Rollback policy

- Code-only PRs revert normally.
- Schema PRs ship with downgrade or recovery notes and a pre-upgrade backup. Never rely on a destructive downgrade for user recovery.
- Sync protocol changes are version-gated. Mismatched peers fail closed with a clear "update required" message.
- Tax and accounting fixes never rewrite historical transactions without a separately approved data migration. Reports may be recomputed from stored facts.
