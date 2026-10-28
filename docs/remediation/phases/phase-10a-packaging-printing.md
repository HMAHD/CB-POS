# Phase 10A — Packaging and Printing Improvements (former backlog)

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> These issues already contain benchmark results and exact commands. **The issue bodies are the primary spec**; this file adds post-remediation corrections, gates and order. Verified against `origin/main` @ `4bcc837`; re-verify before editing.

## Phase brief

**Outcome:**
- a 64-bit installer path (code signing decided by the owner, D7);
- a smaller font bundle;
- A4 invoices with real vector Sinhala/Tamil text;
- a safe, short list of receipt fonts with a live preview.

**Depends on:**
- the public release gate;
- Phase 7 #806, which created `cbpos/infrastructure/pdf_fonts.py` and the `uharfbuzz` shaping path. #924 reuses it; don't create a second font registry.

| # | Title | Size | Batch | Gate |
|---|---|---|---|---|
| #923 | Slim the font bundle 6.4 → 1.9 MB | S | 10A.1 | agent |
| #924 | A4 invoice: vector si/ta via ReportLab shaping | M | 10A.1 | agent |
| #925 | Receipt font choice (Clear/Compact) with live preview | M | 10A.2 | human (font list sign-off) |
| #815 | Installer: 64-bit mode, signing, portable build | M | 10A.3 | **human** (signing cost, D7; portable build) |

## Batch 10A.1 — `feat/p10a-b1-fonts-vector-invoice` (#923, then #924)

### #923 — Slim the font bundle

Follow the issue's "Do" list exactly. In particular, **keep `--name-IDs='*'`**: without it, QSS weights 500/600 break.

Additions:
- `scripts/subset_fonts.py` is idempotent. It reads the originals from a pinned source: keep the full originals in `scripts/font_sources/` (not bundled) or download them by a pinned URL with a checksum. **Recommended:** keep the originals under `scripts/font_sources/`, and exclude that folder from `cbpos.spec`.
- Test `test_registered_font_families`: the families equal {Noto Sans, Noto Sans Sinhala, Noto Sans Tamil}, **and** `QFontDatabase.styles("Noto Sans")` includes Medium and SemiBold, so the weights still resolve.
- Run the §0.7 UI gate with screenshots of the 5 busiest screens in both themes × en/si/ta, compared with "before" screenshots, so there are no weight regressions.

### #924 — A4 invoice with vector Sinhala/Tamil

Follow the issue. **Correction:** register fonts through Phase 7's `pdf_fonts.py` (extend it with the Bold weights), and keep the PNG path only as the import-failure fallback (as the issue says).

Tests (as in the issue): no embedded PNGs for si/ta invoices, plus a shaping smoke test that renders "ශ්‍රී" and checks the glyph count through ReportLab's shaped output API if one is accessible; otherwise a sample PDF is attached for human review.

The release notes must mention that copied text loses ligature clusters. That is a known ReportLab limitation, and printing is unaffected.

## Batch 10A.2 — `feat/p10a-b2-receipt-font-choice` (#925)

**Gate (Stop & Ask before building):**

QUESTION (#925): Offer "Clear (Noto, recommended)" and "Compact (Yaldevi)" only, and add "Windows built-in (Nirmala UI)" only if it passes the same benchmark script?
Recommendation: yes. Never offer arbitrary system fonts.

Design per the issue:
- the radio list in Settings → Receipt;
- the live preview **through the real `render_text_line` pipeline** at the selected paper width;
- a "Print test receipt" button (using a Phase 7 job id).

Additions:
- The setting changes only `text_raster`'s font family and (after #924) the A4 font, read through one getter `ReceiptFontService.current()`.
- The benchmark script goes in `scripts/font_benchmark.py`, as the issue asks.
- Bundle Yaldevi under `cbpos/assets/fonts/Yaldevi/` with its OFL licence. Add it to THIRD_PARTY_NOTICES (Phase 8 #817 generator: fonts aren't in `uv.lock`, so add a static "bundled assets" section to the generator).
- Run the full §0.7 UI gate (preview = print; a photo of a printed test on 58 mm, ⚠️ Verify on Windows).

## Batch 10A.3 — `feat/p10a-b3-installer-64bit` (#815)

D7 deferred paid signing. Split the work:
1. **Agent, now:**
   - add `ArchitecturesAllowed=x64compatible` and `ArchitecturesInstallIn64BitMode=x64compatible` to `installer/cbpos.iss`;
   - **upgrade path:** existing installs live in `C:\Program Files (x86)\CB POS`. Verify `UsePreviousAppDir=yes` keeps them there (acceptable), or migrate them. **Recommended:** keep the previous dir. Moving the install isn't worth the risk; user data is in `%LOCALAPPDATA%` anyway (CLAUDE.md).
   - Test the upgrade in a Windows VM: install 1.3.0, then upgrade, and check the shortcut, the uninstall entry and that data is intact (⚠️ Verify on Windows).
2. **Human gates (Stop & Ask):**

   QUESTION (#815-a): Code signing. Options: Azure Trusted Signing (about USD 10/month, needs an identity-verified org), an OV certificate (about USD 200–400/year), or stay unsigned with SmartScreen instructions.
   Recommendation: Azure Trusted Signing once the business entity is verified. Until then, unsigned, with clear SmartScreen steps on the website.

   QUESTION (#815-b): Ship a portable zip?
   Recommendation: no for the first public build. Portable installs break the AppData data-directory rule and auto-update.
3. If signing is approved, add a SignTool step for `cbpos.exe` and the installer to `release.yml`, with the secrets referenced by name only.

## Phase exit gate
- [ ] #923, #924, #925 and #815 merged and **verified closed** (or #815 split: the agent part closed, signing tracked in a new issue per the owner's answer).
- [ ] UI gate screenshots, PDF samples, and photos of printed receipts.
- [ ] Release notes updated, and THIRD_PARTY_NOTICES includes the bundled fonts.
