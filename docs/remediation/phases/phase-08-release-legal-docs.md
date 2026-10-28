# Phase 8 — Release, Legal, Update Checks, Documentation

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> This spec was verified against `origin/main` @ `4bcc837` on 2026-10-28. Re-verify every `file:line` before editing (§0.1 step 7).
> **Legal and tax text is never invented.**
> - Use only the decisions (D6, D8) and primary sources: IRD, Gazette, licence texts.
> - Legal wording (EULA, privacy notice) is drafted from the templates named below, then **reviewed by the owner and a lawyer** before release (D8). Mark it DRAFT until then.

## Phase brief

**Outcome (end state):**
- Owners control update checks. Critical updates can be marked required. "What's new" shows the real changelog.
- Exports and scheduled emails work with USB drives and flaky SMTP, without spamming or freezing.
- VAT-registered shops can issue a compliant **tax invoice**: the gazetted serial, mandatory particulars, amount in words, and ORIGINAL / COPY ONLY. Ordinary receipts stay separate.
- The app and installer carry a licence, privacy notice, third-party notices and an About dialog with CB POS branding, website, help and issue reporting.
- Every public document matches the shipped code.

**Depends on:** Phases 1–7. Docs describe final behaviour. #814 needs Phase 6's stored tax facts and Phase 3A's refund documents.
**Unblocks:** the public release gate (§1.3).

### Issues

| # | Title | Sev | Size | Batch | Gate |
|---|---|---|---|---|---|
| #808 | Update check can't be disabled; `min_version` ignored; changelog empty | medium | M | 8.1 | agent |
| #881 | Export to USB/another drive refused | medium | S | 8.1 | agent |
| #882 | Auto-report email resent every minute | medium | M | 8.1 | agent |
| #814 | Tax invoice compliance (serial, particulars, amount in words, copy marking) | high | L | 8.2 | decided (D6) + research + accountant sign-off |
| #817 | EULA, privacy notice, third-party notices | high | M | 8.3 | **human**: licensing conflict, below |
| #816 | About dialog, help and report-issue links | low | M | 8.3 | agent |
| #818 | Documentation drift | medium | M | 8.4 | agent (last; after all code phases) |
| #819 | Labels: English-only, fake barcode preview, no size setting | low | M | 8.4 | agent |

### Subsystem map

**Update** — `cbpos/core/services/update_service.py` (manifest URL `:36`); the startup call in `main.py:574-583` (deferred 3 s); the update dialog (`graft grep "class UpdateDialog"`); release workflow `.github/workflows/release.yml:235-250` (template notes, `"changelog": ""`); `installer/latest.json.template`.

**Exports** — `cbpos/core/services/export_service.py:18-29` (path allow-list).

**Scheduler and email** — `cbpos/core/services/scheduler_service.py` (`check_automation` `:59-150`, called every 60 s by the timer in `main.py`); `email_service.py:15` (worker).

**Invoices:**
- `cbpos/core/services/invoice_service.py` (A4 invoice);
- `cbpos/core/utils/amount_to_words.py:89` (exists, unused);
- `document_service.py:25` (`INV-{Y}-{seq:05d}`);
- reprint markers in `printer_service.py:82,101`.

**Installer and packaging** — `installer/cbpos.iss` (no `LicenseFile`), `cbpos.spec` (one-dir build), `create_installer.py:19-23`.

**Docs** — `README.md`, `public-releases-readme.md`, `SECURITY.md`, `CHANGELOG.md`, `CLAUDE.md`, `docs/PROJECT_OVERVIEW.md`, `docs/TAX.md`, `docs/Roadmap.md`; the shortcuts help at `cbpos/ui/dialogs/shortcuts_help_dialog.py:21-36`.

**Labels** — `cbpos/core/services/label_service.py:22-36`, `cbpos/ui/dialogs/label_preview_dialog.py:25-37`. Phase 7 #840 added `choose_barcode`.

### Batches

| Batch | Branch | Issues | Why grouped |
|---|---|---|---|
| 8.1 | `fix/p8-b1-update-export-scheduler` | #808, #881, #882 | Background and external I/O behaviour |
| 8.2 | `feat/p8-b2-tax-invoice-compliance` | #814 | Legal document format, reviewed alone |
| 8.3 | `feat/p8-b3-legal-about` | #817, #816 | Licence, notices and the About surface |
| 8.4 | `docs/p8-b4-docs-labels-truth` | #819, #818 | Labels, then docs **last** (they describe everything) |

---

## Batch 8.1 — Update, export, scheduler

**Branch:** `fix/p8-b1-update-export-scheduler`

### #808 — The update check can't be disabled; `min_version` is ignored; the changelog is empty

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (clarify)

**Fix.**
1. **Setting:** `auto_update_check: bool` (default True), on the Settings → System page, checked in `main.py` before the deferred check. A **Check now** button on the same page, and in Help (#816), runs it on demand.
2. **`min_version`:**
   - `UpdateService` parses `min_version` from the manifest and compares it with `packaging.version.Version` (confirm `packaging` is available; it usually is through pip tooling, otherwise add it with `uv add packaging`).
   - If running < `min_version`, the dialog shows "Required update", with no "Remind me later" (only **Download** and **Close**), and shows the banner again on each launch. Don't block use of the app: it is offline-first, and a shop can't stop selling.
3. **Changelog:**
   - `release.yml` extracts the section `## [X.Y.Z]` … up to the next `## [` from `CHANGELOG.md`, using a small Python step (`scripts/changelog_section.py <version>`; add the script, with a test);
   - it writes the section into the GitHub release body and `latest.json.changelog`;
   - the dialog renders it as plain text (Markdown bullets displayed as text, which is safe; no HTML).
4. Delete `installer/latest.json.template`, or regenerate it from the workflow (`graft grep "latest.json.template"` decides which).

**Tests.**
- `test_update_service.py::test_issue_808_min_version_marks_required`.
- `test_issue_808_setting_off_skips_startup_check`.
- `test_changelog_section.py::test_extracts_version_section`.

**UI/UX.**
- `settings.auto_update_check` "Check for CB POS updates when it starts"
- `settings.auto_update_help` "CB POS only downloads a small version file from the internet. Your shop data is never sent."
- `update.required_title` "Important update"
- `update.required_body` "This update fixes a serious problem. Please install it as soon as you can."
- `update.check_now` "Check for updates now"

Run the §0.7 UI gate.

**Acceptance.**
- [ ] A "Check for updates automatically" setting exists, default on, translated.
- [ ] Below `min_version`, the update is marked required (no "Remind me later").
- [ ] The release workflow puts the CHANGELOG section into the release notes and `latest.json`.
- [ ] The template is removed or regenerated.

### #881 — Exports to USB or another drive are refused

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.** `export_service.py:18-29` allows only home and temp.

**Fix.**
- Paths chosen in a `QFileDialog` are user intent. Accept any absolute path whose parent exists and is writable (`os.access(parent, os.W_OK)`), and refuse only when it isn't.
- Grep for other copies of the allow-list (`graft grep "outside allowed"`), apply the same rule, and share one helper `cbpos/core/utils/paths.py: ensure_writable_target(path) -> Path`. Phase 4 #900 handled import paths; make them use the same helper.

**Tests.**
- `test_issue_881_export_to_other_drive_path_succeeds` (use `tmp_path` outside home via monkeypatch of `Path.home`).
- `test_issue_881_unwritable_parent_raises`.

**UI/UX.** `export.not_writable` "Can't save to {folder}. Check the USB drive is plugged in and not write-protected." Run the §0.7 UI gate.

**Acceptance.**
- [ ] Exporting to another drive succeeds, with a test.

### #882 — The auto-report email is resent every minute

**Severity:** medium · **Size:** M · **Gate:** agent

**Root cause.**
- `scheduler_service.py:59, 80-90, 105-150` has no in-progress flag and no backoff.
- The report and PDF are built on the UI thread (the timer callback).

**Fix.**
1. Persist state in settings:
   - `auto_report_last_sent_date` (already exists? check), `auto_report_in_progress_since`, `auto_report_failures`, `auto_report_next_attempt`.
   - **Only** set `last_sent_date` after a confirmed send.
2. `check_automation`:
   - return if in progress, unless that started more than 15 minutes ago, which counts as stuck: clear it and log;
   - return if `now < next_attempt`;
   - otherwise mark in progress and start **one** worker (`start_background_job`) that builds the report and PDF **and** sends.
3. On failure, `failures += 1` and `next_attempt = now + min(2^failures × 5 min, 6 h)`. After 5 failures in a day, stop for that day and show the owner a notice next time Management opens.
4. On success, clear the counters.

**Tests** (drive `check_automation` with a fake clock and a fake sender):
- `test_issue_882_slow_send_sends_once`;
- `test_issue_882_failing_send_backs_off`;
- `test_issue_882_build_runs_off_ui_thread`.

**UI/UX.** `auto_report.failed_notice` "The daily report email couldn't be sent today ({reason}). Check Settings → Email." Run the §0.7 UI gate.

**Acceptance.**
- [ ] A slow send produces one email, and a failing send backs off.
- [ ] Unit tests drive `check_automation`.

---

## Batch 8.2 — Tax invoice compliance

**Branch:** `feat/p8-b2-tax-invoice-compliance`

### #814 — Tax invoice compliance features are missing

**Severity:** high · **Size:** L · **Gate:** decided by **D6**:
- verify against official IRD and Gazette sources;
- implement the mandated serial, fields, amount in words and `ORIGINAL` / `COPY ONLY`;
- ordinary receipts stay a separate document type.

An accountant signs off before close.

**Skills:** research (primary sources) → write a design note → `/egm-review` → tdd → migration rules → ponytail; impeccable (full UI gate for the invoice layout)

**Step 0 — research note (required before code).** Write `docs/research/2026-tax-invoice-requirements.md`. Use **primary sources only**: ird.gov.lk, documents.gov.lk (Gazettes 2463/05, 2481/22 and 2500/106), and the VAT Act s.20. The issue comment summarises them, but its Gazette details come from a *secondary* source (KPMG), so confirm each point against the Gazette PDF and cite the URL and page. Record:
- the serial format `YYMMM_QQQQ_XXXXX`: what each part means (year, month code? TIN part? branch? sequence), the max length (≤ 40, no spaces), the reset period;
- the mandatory particulars list;
- the "TAX INVOICE" wording and placement;
- the copy marking ("copy only");
- 9-digit TIN rules;
- the effective date (1 Oct 2026, per the Gazette postponement chain);
- the 5-year retention;
- when a tax invoice is required (registered buyer, written request within 14 days, government body) vs a retail receipt (s.20(6)(a)).

If any point can't be confirmed from a primary source, **Stop & Ask**, and don't guess.

**Fix design (after the note):**
1. **Document type.**
   - A tax invoice is its **own document**, `TaxInvoice`, linked 1:1 to a `Sale`, created on demand: at checkout when the customer is VAT-registered, or later from Sale History within 28 days ("Issue tax invoice").
   - New table `tax_invoices`: `id`, `sale_id` (unique FK), `serial` (unique, String(40)), `issued_at`, `buyer_name`, `buyer_address`, `buyer_tin`, `supplier_tin`, `issued_by`, `print_count`.
   - It's a snapshot: buyer details are copied at issue time. Migration required.
2. **Serial generator.** `TaxInvoiceService.next_serial(session, issued_at)` implements the confirmed format, generated inside the issuing transaction (Phase 2 #905's numeric max rule applies). In LAN-sync mode the Main PC must not collide with tills: include the terminal component **if the format allows one**; otherwise Stop & Ask (Q: can tills issue tax invoices, or only the Main PC?). The recommended answer is "only the Main PC or standalone".
3. **Particulars** come from stored sale facts (Phase 6 snapshot): the per-line description and qty, value excluding VAT, VAT charged, total consideration, date of supply (= sale date), the supplier name, address and TIN from settings, and the buyer details snapshot. LKR to 2 dp.
4. **Amount in words** via `amount_to_words.py` in the invoice language. Check that it supports si and ta; if not, English words plus the figure. Mark si/ta words "⚠️ human review" in PROGRESS.md i18n review.
5. **Original vs copy.** The first print is marked "ORIGINAL". Every later print (`print_count > 0`) is marked "COPY ONLY", using the exact wording confirmed in the note. `print_count` increments in the same transaction as the print job queue, and the reprint audit (Phase 5 #911) applies.
6. **Retail receipts unchanged**: never titled "TAX INVOICE".
7. **Refunds:** a credit-note format for a tax invoice. Check s.20 / the research note for credit or debit note particulars. If required, add `TaxCreditNote`. Otherwise reference the original serial on the refund document. Write this into the note, and Stop & Ask if unclear.
8. **Public claims:** update `CHANGELOG.md:215` and `public-releases-readme.md:101` to describe exactly what's implemented (this is also in #818).

**Tests.**
- `test_tax_invoice_service.py`: serial format matches the regex from the note; the sequence is unique and monotonic; it resets per the confirmed rule; an issue after 28 days is refused (if the note confirms the 28-day rule as a hard limit; otherwise warn only).
- Particulars present in the generated PDF text (extract the text with `pypdf`).
- The first print says ORIGINAL; the second says COPY ONLY.
- A retail receipt never contains "TAX INVOICE".

**UI/UX.**
- Sale History has an **Issue tax invoice** action (permission `sales.tax_invoice`, new and seeded), enabled for COMPLETED, non-refund sales within the window.
- A buyer-details dialog with name, address and 9-digit TIN (validated), prefilled from the customer record.
- At checkout, when the attached customer has a TIN, show an "Issue tax invoice" checkbox, checked by default.
- Invoice layout: "TAX INVOICE" prominent at the top; ORIGINAL or COPY ONLY marking per the confirmed wording.
- Keys under `tax_invoice.*`, with English copy written from the research note's terms. Si/ta must be human-reviewed (legal text).
- Run the full §0.7 UI gate with a printed sample.

**Acceptance.**
- [ ] The research note cites primary sources for every requirement.
- [ ] Compliant tax invoices: serial, particulars, amount in words, ORIGINAL / COPY ONLY. Retail receipts are separate.
- [ ] The CHANGELOG and public readme describe only what exists.
- [ ] Accountant sign-off recorded (release gate).

---

## Batch 8.3 — Legal notices and About

**Branch:** `feat/p8-b3-legal-about`

### #817 — EULA, privacy notice and third-party licence notices

**Severity:** high · **Size:** M · **Gate:** **human**. Resolve this conflict **before** writing any licence file:

**Stop & Ask (first thing in this batch):**

QUESTION (#817): D8 (2026-10-23) says to distribute CB POS and its source under **GPLv3** (because PyQt6 is GPL unless you buy a commercial licence). But the product notes say CB POS is "free software, **closed code** (NOT open source)". These conflict: shipping PyQt6-based closed-source binaries needs a commercial PyQt6 licence (Riverbank), or a switch to PySide6 (LGPL), or open-sourcing under GPLv3.
Options:
  A) GPLv3: publish the source (as D8 says). The app stays free, the code becomes public, and anyone may fork it.
  B) Buy a PyQt6 commercial licence, keep the code closed, and ship a freeware EULA.
  C) Migrate PyQt6 → PySide6 (LGPL): closed code allowed with LGPL compliance (dynamic linking, notices, relinking ability). A large but mechanical migration; it would become its own epic.
Recommendation: confirm A or B with a lawyer. D8 currently says A. If the owner now wants closed code, record a new decision (D19) that supersedes D8. Nothing in this batch ships until this is answered.

**After the answer, the agent builds:**
1. `THIRD_PARTY_NOTICES.txt`, generated from `uv.lock` by `scripts/gen_third_party_notices.py`:
   - for each runtime dependency (not dev or build): name, version, licence (from installed package metadata via `importlib.metadata`), project URL, and the licence text if the package ships one;
   - Qt/PyQt notices included;
   - add a test that the file lists every runtime package in `uv.lock`;
   - run it in the release workflow, and bundle the file in `cbpos.spec` datas.
2. Licence file:
   - **A:** `LICENSE` with the full GPLv3 text from gnu.org, a "corresponding source" section in `public-releases-readme.md` with a link to the source for each release, and the installer `LicenseFile=LICENSE`.
   - **B:** `EULA.txt` drafted from a standard freeware EULA template, covering a warranty disclaimer, limitation of liability, no-resale, and attribution of CB POS branding, marked **DRAFT, legal review required**; and `LicenseFile=EULA.txt`.
3. `PRIVACY.md`, written for shop owners in plain language, describing every network call:
   - update check: what's sent, a version GET only (confirm from `update_service.py`);
   - SMTP: only to the shop's own mail server;
   - LAN sync: only inside the shop's network;
   - PostgreSQL: the shop's own server.

   It states that no data is sent to Ceylon Byte, that there's no telemetry, and where data is stored (`%LOCALAPPDATA%\CB POS`). Marked **DRAFT** for owner and lawyer review. It's in English only for now; the Sinhala/Tamil versions are a follow-up issue (legal translation).
4. The installer shows the licence page (`LicenseFile=`). The About dialog (#816) links all three documents.

**Tests.**
- `test_third_party_notices_complete`.
- `test_installer_script_has_license_file` (a parse of `cbpos.iss` for `LicenseFile=`).

**Acceptance.**
- [ ] The owner has answered the licensing question (recorded as D19 or as D8 confirmed).
- [ ] The licence and EULA are shown in the installer and in About.
- [ ] The privacy notice describes every network call.
- [ ] THIRD_PARTY_NOTICES is generated from `uv.lock` and bundled.

### #816 — About dialog, plus help and report-issue links

**Severity:** low · **Size:** M · **Gate:** agent · **Skills:** impeccable (full UI gate: a brand surface)

**Fix.**
1. `AboutDialog` (`cbpos/ui/dialogs/about_dialog.py`, objectName `AboutDialog`), with:
   - the CB POS logo (from `cbpos/assets`), name, version (from the version module used by `update_service`), and build date (embed it at build time in the version file if it isn't there; check `release.yml`'s version stamp step);
   - the "Ceylon Byte · ceybyte.com" link;
   - buttons **Licence**, **Privacy**, **Open-source notices** (each opens the bundled text in a read-only viewer dialog);
   - **Check for updates** (#808);
   - **Report a problem**.
2. **Report a problem** opens `https://github.com/ceybyte/cbpos-releases/issues/new?title=...&body=...` with the version, Windows version and language prefilled (URL-encoded). Confirm the public issues repo with the owner. The `cbpos-releases` repo is public per CLAUDE.md; use it unless told otherwise. Never include shop data.
3. Help menu or side-menu entries: **User guide** (website docs URL, from a constant in one place, `cbpos/core/constants/links.py`), **Report a problem**, **Check for updates**, **About**.
4. The support message (`en.json:87`) includes the website: "Need help? Visit ceybyte.com/support". Use the URL constant; confirm the exact URL with the owner, with the default `https://ceybyte.com`.

**Tests.**
- pytest-qt `test_about_dialog_shows_version_and_links`.
- `test_report_problem_url_has_version_no_pii`.

**UI/UX.**
- A centred logo, version in secondary text, link buttons in a row, and a footer `[Close]`.
- Keys `about.*`:
  - `title` "About CB POS"
  - `version` "Version {version} ({date})"
  - `licence` "Licence"
  - `privacy` "Privacy"
  - `notices` "Open-source notices"
  - `report` "Report a problem"
  - `guide` "User guide"
  - `made_by` "Made by Ceylon Byte · ceybyte.com"
- Both themes. Run the full §0.7 UI gate.

**Acceptance.**
- [ ] The About dialog has the version, build date, website, licence and notices.
- [ ] Help entries: user guide, report a problem (version prefilled), check for updates.
- [ ] The support message includes the website, in en/si/ta.

---

## Batch 8.4 — Labels and documentation truth

**Branch:** `docs/p8-b4-docs-labels-truth` · **Run last, after Phases 1–8.3 are merged.**

### #819 — Labels: English-only names, fake barcode preview, no size setting

**Severity:** low · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (full UI gate)

**Fix.**
1. Preview renders the **real** barcode: `python-barcode` (a dependency) generates the CODE128 / EAN-13 matching `choose_barcode` (Phase 7 #840) as an image. Remove the hash-based fake bars (`label_preview_dialog.py:25-37`).
2. Label language option: English, Sinhala, Tamil, or "English + local". Non-Latin names go through the raster path (`text_raster`), and the name comes from `ProductService.display_name` (Phase 7 #805).
3. Label size setting: 50×30 mm, 40×25 mm, 58 mm-receipt (the current layout), or custom W×H. The layout scales the name font, barcode width and price to the width. **Width-only** is honoured on receipt printers; height affects the spacing between labels.

   Real label printers (TSPL/ZPL) are out of scope; record that in the PR.

**Tests.**
- `test_issue_819_preview_barcode_matches_printed_type`.
- `test_issue_819_label_layout_respects_width`.
- `test_issue_819_sinhala_label_uses_raster`.

**UI/UX.** The Label dialog gets size and language combos and a live real preview. Keys `labels.size`, `labels.language`, `labels.size_custom`. Run the full §0.7 UI gate, with printed samples (⚠️ Verify on Windows).

**Acceptance.**
- [ ] The preview shows the real barcode.
- [ ] Names print in si or ta through the raster path.
- [ ] The label width setting is honoured.

### #818 — Documentation drift

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** egm `drift-report` (ask the human to run `/egm-drift-report docs`, or follow `~/.gemini/config/plugins/egm/skills/egm_drift_report/SKILL.md` inline) → write

**Fix.**
- Go through **every** checkbox in the issue body, plus everything that Phases 1–8 changed. Update each document to match the **shipped** code.
- The comment on the issue gives the SSCL correction: VAT-exclusive base. The Rs 100 example is SSCL **1.06**, net **83.69**. Recompute it with the final Phase 6 rounding and write the verified numbers.
- Also update:
  - CLAUDE.md: the startup flow (#791's `setup_completed`, #833's setup check, #799's network gate, `SchemaMigrationService`); the PyInstaller one-dir build; the Payment Methods location; pyusb.
  - CONTEXT.md: new terms (Payment kind, Refund state, Tax invoice, Schema owner, Till identity).
  - `SECURITY.md` supported versions.
  - `public-releases-readme.md`:
    - the version;
    - "offline" wording that mentions the optional update check;
    - menu paths;
    - LAN Sync;
    - VAT/SSCL off by default;
    - the admin PIN wording from #791;
    - the "update all PCs together / re-pair tills" notes from Phase 2.
  - `CHANGELOG.md`: mark 1.3.0 as a pre-release, add a new `[Unreleased]` / next-version section listing every fixed issue by number, and correct the 1.3.0 date.
  - The shortcuts help dialog: add Ctrl+Z, Ctrl+Alt+C, and Phase 3B's bill discount shortcut. It's UI, so si/ta keys are needed.
  - `CBPOS_FACTS.md` (website fact sheet, §0.12 P12): re-audit every claim against the release build, and mark anything unverifiable.
- **Do not** describe planned features (Phases 9–10) as shipped.

**Tests.** The shortcuts dialog test, if one exists. Otherwise a doc PR needs no tests, but run `scripts/validate_translations.py --strict` for the dialog keys.

**Acceptance.**
- [ ] Every checkbox in the issue body is resolved, and each document matches the code at the release commit.
- [ ] CHANGELOG lists the remediation fixes, and 1.3.0 is marked as a pre-release.
- [ ] CBPOS_FACTS.md is re-audited.

---

## Phase exit gate
- [ ] All 8 issues merged and **verified closed** with closing comments (§0.10). #832 and #922 closed if all their children are closed.
- [ ] The research note for #814 is merged, with primary-source citations. Accountant sign-off recorded (D-number).
- [ ] The licensing decision is recorded (D8 confirmed or D19). The licence or EULA, privacy notice and notices are bundled. Lawyer review noted.
- [ ] Release workflow dry-run (`workflow_dispatch`) produces release notes from CHANGELOG and a `latest.json` with changelog and `min_version`.
- [ ] UI gate screenshots: the About dialog, an update-required dialog, a tax invoice ORIGINAL and COPY ONLY sample, the label preview.
- [ ] Then run the **public release gate** (RELEASE_PLAN.md §1.3).
