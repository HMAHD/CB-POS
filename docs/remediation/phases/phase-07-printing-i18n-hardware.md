# Phase 7 — Printing, Scanning, PDF, Multilingual Output, UI Concurrency

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> This spec was verified against `origin/main` @ `4bcc837` on 2026-10-28. Re-verify every `file:line` before editing (§0.1 step 7).
> **Hardware rule:** anything you can't prove in a unit test must be marked "⚠️ Verify on Windows" in the PR and in PROGRESS.md (§0.12 P6). Never write "works on printer X" unless the human confirms it.

## Phase brief

**Outcome (end state):**
- Printing is truthful and responsive:
  - A4 invoices go to the chosen printer, are built off the UI thread, and report real failures;
  - barcodes print and fit the paper;
  - a screen reacts only to its own print jobs.
- Receipts are readable in Sinhala and Tamil: item names in the receipt language, long lines wrapped, merged lines that add up.
- Report PDFs render Sinhala and Tamil correctly.
- Scanned barcodes arrive intact whatever has focus. The dashboard can't crash the app.
- No hard-coded English in the crash dialog or the report email. The en, si and ta key sets are identical.

**Depends on:**
- Phase 3A/3B: `method_kind`, refund engine, bill discount;
- Phase 6: stored tax facts, and SSCL removed from receipts;
- Phase 5: reprint service.

#731 / #878 need a human with real printers (D1, D10).

**Unblocks:** the release gate's printer and language matrix (RELEASE_PLAN.md §1.3). Phase 10A (#923–#925 font work) builds on #806's font module.

### Issues

| # | Title | Sev | Size | Batch | Gate |
|---|---|---|---|---|---|
| #876 | Printer-name validation rejects real names; PowerShell failures discarded | medium | M | 7.1 | agent |
| #803 | Configured A4 printer ignored | medium | S | 7.1 | agent |
| #879 | A4 invoice PDF built on the UI thread at checkout | medium | M | 7.1 | agent |
| #731 | Verify background report printing on real Windows printers | medium | M | 7.1 | **human** (D1 printer matrix) |
| #840 | Labels print without barcode (CODE128 needs `{B`) | high | S | 7.2 | agent |
| #878 | Receipt invoice barcode wider than paper | medium | S | 7.2 | decided (D10) + human print check |
| #877 | Long Sinhala/Tamil lines clipped on 58 mm | medium | M | 7.2 | agent |
| #908 | Merged receipt lines show wrong price and saving | low | S | 7.2 | agent |
| #841 | Scanner duplicates each key per widget hop | high | S | 7.3 | agent |
| #842 | Hidden Document view reacts to every later print job | high | M | 7.3 | agent |
| #846 | Dashboard aborts (SIGABRT) when re-shown during a load | high | S | 7.3 | agent |
| #805 | Thermal receipts always print English item names | medium | S | 7.4 | agent |
| #806 | Report PDF can't render Sinhala/Tamil | medium | L | 7.4 | agent (approach decided below) |
| #807 | Hard-coded English; 16 missing Tamil keys | low | S | 7.4 | agent (Tamil quality per §0.12 P7) |

### Subsystem map

**Print worker** — `cbpos/infrastructure/hardware/escpos_driver.py`:
- `PrintWorker(QThread)` `:379`: a singleton via `instance()` `:414`, `add_job(job_type, data)` `:439`, the job loop `~:470-540`;
- signals `job_completed()` `:396` and `error_occurred(str)` `:395`, which carry **no job identity**;
- `_drawer_wanted` `:460` (Phase 3B changed it);
- `print_commands`;
- the barcode call `:344-348`.

**Peripherals port** — `cbpos/infrastructure/hardware/print_worker_peripherals.py:43-45` (`sale_completed` calls the A4 invoice inline).

**Printer service** — `cbpos/core/services/printer_service.py`:
- `print_transaction` `:88-90`;
- `_print_a4_invoice` `~:145-178` (PDF to `tempfile.gettempdir()` at `:167`);
- `_validate_name` `:181-185` (regex);
- launch `:203-215` (`Popen` + `Start-Process -Verb Print`, DEVNULL, not waited on).

**Builders:**
- `cbpos/core/services/base_receipt_builder.py` (`:146-152` wrapping only header/footer);
- `sales_receipt_builder.py` (item name `:119`, lines `:107,127-148`, barcode `:227-229`, doc title `:251-264`, `_merge_items` `:267-287`);
- `void_receipt_builder.py:93`;
- `refund_receipt_builder.py:67`;
- `statement_receipt_builder.py:46`;
- `label_service.py:26-31`.

**Raster text** — `cbpos/infrastructure/hardware/text_raster.py`: `render_text_line` `:42-95` (shrinks to `_MIN_PIXEL_SIZE=14` `:29`, no wrap), `render_text_png` `:97+` (wraps). `PAPER_DOT_WIDTH` in `cbpos/core/utils/thermal_image.py:14` is {58mm: 384, 80mm: 576}.

**A4 invoice** — `cbpos/core/services/invoice_service.py` (`generate_pdf` `~:252`, raster workaround `:118-129`).

**Report PDF** — `cbpos/core/services/export_service.py:~99` (xhtml2pdf, Helvetica). Fonts are bundled in `cbpos/assets/fonts/{Noto_Sans, Noto_Sans_Sinhala, Noto_Sans_Tamil}`.

**Scanner** — `cbpos/infrastructure/hardware/scanner.py:50-75` (Phase 3B #890 already added the modal check).

**Views:**
- `cbpos/ui/views/document_view.py:861-900` (reprint signal wiring);
- `ui/views/history_view.py:387-394` (dead view, same bug);
- `cbpos/ui/views/dashboard_view.py:564-616` (parentless QThreads per showEvent);
- `cbpos/ui/views/management_view.py:185` (views cached).

**Background jobs** — `start_background_job(worker)` in `cbpos/ui/workers.py:97`. **This is the required way to start view-owned workers.** The correct disconnect pattern is in `shift_closing_dialog.py:_on_z_report_printed`.

**Note:** `tests/conftest.py` replaces `QThread.start` with `run` in some fixtures (`_autocomplete_preload_runs_inline`). Real-thread tests must opt out of that; check the fixture and use `@pytest.mark.real_threads` if one exists, or add a fixture override in the test module.

**i18n** — `cbpos/i18n/{en,si,ta}.json`; `scripts/validate_translations.py`; `translate_in(lang, key)`. The crash dialog is at `main.py:103-107`, the scheduler email at `scheduler_service.py:16,94,114,132-150`.

### Domain invariants

1. A print job ends in exactly one result (ok or error, with a message), delivered only to the screen that queued it.
2. "Sent" or "success" is shown only after the OS print command or the ESC/POS write succeeded.
3. No PDF building, rasterising or spooling runs on the UI thread.
4. Every printed line fits the paper width without clipping glyphs.
5. Customer-facing output uses the receipt language, falling back to English per field.

### Batches

| Batch | Branch | Issues | Why grouped |
|---|---|---|---|
| 7.1 | `fix/p7-b1-printer-selection-transport` | #876, #803, #879, #731 | One A4 print path: safe launch, named printer, off-thread, then the human matrix |
| 7.2 | `fix/p7-b2-thermal-barcode-layout` | #840, #878, #877, #908 | Thermal output correctness |
| 7.3 | `fix/p7-b3-scanner-signal-dashboard-lifecycle` | #841, #842, #846 | Input and signal lifecycle |
| 7.4 | `fix/p7-b4-multilingual-receipt-pdf` | #805, #806, #807 | Language output |

**Batch-wide change (first commit of 7.1): job identity on the print worker.**
- `add_job(job_type, data=None) -> str` returns a `job_id` (`uuid4().hex`).
- A new signal `job_result = pyqtSignal(str, bool, str)` carries `(job_id, ok, message)` and is emitted for **every** job.
- Keep `job_completed` and `error_occurred` emitting exactly as today, so no current listener breaks.
- New code, starting with #842, listens to `job_result` and filters by its own `job_id`.

---

## Batch 7.1 — Printer selection and output transport

**Branch:** `fix/p7-b1-printer-selection-transport`

### #876 — Printer-name validation rejects real Windows names, and PowerShell failures are thrown away

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** systematic-debugging → tdd → ponytail-review (security: command injection)

**Problem.**
- Real printer names like `HP LaserJet Pro M404-M405 (PCL 6)` are rejected, so every A4 invoice fails.
- Windows short temp paths (`ADMINI~1`) fail too.
- The "safe" check lets newlines through.
- When printing fails, nobody is told.

**Evidence and root cause.**
- `printer_service.py:181-185`: regex `^[a-zA-Z0-9_\-\.\s\\/:]+$` (no parentheses or `~`; `\s` allows `\n`; `$` matches before a trailing newline).
- `:207-215`: a PowerShell **command string** with an f-string, `Popen` with stdout and stderr to DEVNULL, never waited on.
- `:167`: the PDF goes in `%TEMP%`.

**Fix design.**
1. **No command strings.**
   - On Windows, print the PDF with `win32api.ShellExecute(0, "printto", pdf_path, f'"{printer_name}"', ".", 0)` when a printer is configured, else `"print"`. pywin32 is a Windows dependency (Phase 5 #809 confirmed it).
   - `ShellExecute` raises `pywintypes.error` on failure (for example, no app registered for the `printto` verb), so failure is visible.
   - On non-Windows dev machines, `lp -d <name> <file>` via an argv list (`subprocess.run([...], check=True, timeout=60)`).
2. **Validate the printer name by membership, not by characters:** it must be in `win32print.EnumPrinters(PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS)` names. Also reject names containing control characters (`\x00-\x1f`) as defence in depth.
3. **Path:** write PDFs to `Config.DATA_DIR / "print_spool"` (create it), named `invoice_<doc>_<uuid8>.pdf`. Delete files older than 1 day at startup (a cleanup function called from `main.py` after logging is set up).
4. **Run on the worker thread** (#879), and report through `job_result` (ok / error with a translated message).

   "No PDF app registered" maps to `printer.no_pdf_handler` "Windows has no app set up to print PDFs. Install Adobe Acrobat Reader or set a PDF app that supports printing, then try again."
5. Remove `_validate_name`, or keep it only for the control-character check.

**Tests.**
- `test_printer_service.py::test_issue_876_names_with_parentheses_accepted_when_installed`: monkeypatch `EnumPrinters`.
- `test_issue_876_name_not_installed_rejected`.
- `test_issue_876_control_chars_rejected`.
- `test_issue_876_tilde_path_accepted`.
- `test_issue_876_shellexecute_error_reported`: monkeypatch `ShellExecute` to raise, and assert a `job_result(..., False, msg)` emission.

**UI/UX.**
- `printer.not_installed` "The A4 printer \"{name}\" isn't installed on this computer. Choose another in Settings → Hardware."
- `printer.no_pdf_handler` (above).
- Errors show as the Sales screen's existing non-blocking print-error notice.
- Run the §0.7 UI gate.

**Acceptance.**
- [ ] Names with `( )` and paths with `~` are accepted. Names with a newline or other control characters are rejected. No shell string is built.
- [ ] A failing print command produces an error result.

### #803 — The configured A4 printer is ignored

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.** `printer_service.py:203-215` validates `printer_name`, then uses `-Verb Print`, which goes to the default printer.

**Fix.** Covered by #876's `printto` with the configured `a4_printer_name`. Use `print` (the default printer) only when no A4 printer is configured. Make that decision in one function, `_resolve_a4_printer() -> str | None`.

**Test.** `test_issue_803_configured_printer_passed_to_printto`.

**Acceptance.**
- [ ] Printing goes to the named printer, falling back to the default only when none is configured.
- [ ] Manual note added to the #731 matrix.

### #879 — The A4 tax invoice PDF is built on the UI thread inside checkout

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail

**Root cause.**
- `print_worker_peripherals.py:43-45` (`sale_completed`) → `printer_service.print_transaction` → `_print_a4_invoice` → `InvoiceService.generate_pdf` (`printer_service.py:168`), all on the caller's (UI) thread.
- `transaction_service.py:504-507` triggers it.

**Fix.**
- A new job type `"a4_invoice"`, whose data is the **sale id** (not an ORM object; detached objects across threads are fragile).
- The worker loads the sale with eager loads in its own session, builds the PDF with `InvoiceService.generate_pdf`, prints it via #876, and emits `job_result`.
- `sale_completed` just queues it.
- Check `InvoiceService` for Qt usage. The raster workaround uses Qt to render text: `QImage`/`QPainter` are fine off the GUI thread, but `QPixmap` is not. Grep `QPixmap` in `invoice_service.py` and `text_raster.py`, and replace it with `QImage` if found.

**Tests.**
- `test_issue_879_sale_completed_does_not_build_pdf_on_calling_thread`: patch `generate_pdf` to record `threading.current_thread()`, run `sale_completed`, process the worker, and assert it isn't the main thread.
- `test_issue_879_a4_job_failure_reports_error`.

**Acceptance.**
- [ ] `sale_completed` for a VAT-registered customer returns without building the PDF on the calling thread.

### #731 — Verify background report printing on real Windows printers

**Severity:** medium · **Size:** M · **Gate:** **human** (D1: real thermal 58 mm, 80 mm, A4 and Microsoft Print to PDF)
**Skills:** verification-before-completion

**Agent part.**
1. Read the report-print worker (`graft grep "QPrinter" --in cbpos`). It builds **and** prints in the worker (#643).
2. Add a defensive option **now**, so the human test has a fallback: a setting `report_print_main_thread_final` (default False).
   - When True, the worker builds the `QTextDocument`/pages, and the final `print()` call is invoked on the main thread via a queued signal.
   - Unit-test both modes with a `QPrinter` set to PDF output (`QPrinter.OutputFormat.PdfFormat`) into `tmp_path`.
   - Cancel and printer-offline produce an error result, never "sent".
3. Write the test matrix into the PR description and PROGRESS.md "⚠️ Verify on Windows".

**Human part (the matrix).**

| Printer | Report | si/ta text | UI responsive | Cancel/offline error |
|---|---|---|---|---|
| 58 mm thermal | | | | |
| 80 mm thermal | | | | |
| A4 laser/inkjet | | | | |
| Microsoft Print to PDF | | | | |

Use Inventory Valuation (large) and the Tax Filing Summary. If any row fails with the default mode, set `report_print_main_thread_final=True`, retest, and if that passes, make it the default.

**Acceptance.**
- [ ] The matrix is completed by the human and attached to the PR.
- [ ] Cancel and offline show an error.
- [ ] A fallback mode exists and is tested.

---

## Batch 7.2 — Thermal barcodes and receipt layout

**Branch:** `fix/p7-b2-thermal-barcode-layout`

### #840 — Product labels print without a barcode

**Severity:** high · **Size:** S · **Gate:** agent

**Root cause.**
- `escpos_driver.py:344-348` calls `escpos.barcode(code, "CODE128", function_type="B")` with `check=True`. python-escpos 3.x requires a code-set prefix (`{A`/`{B`/`{C`), so it raises `BarcodeCodeError`.
- The error is logged and the job still completes.
- `label_service.py:26-31` builds the label commands.

**Fix.**
1. In the driver's barcode command:
   - if the data is a valid EAN-13 (13 digits with a correct check digit), send `EAN13`;
   - else CODE128 with the prefix: `{C` for even-length all-digit data (denser), else `{B`.
   - Put this in a pure function `choose_barcode(data) -> (bc_type, payload)`.
2. A barcode failure now **fails the job** (`job_result(id, False, _t("printer.barcode_failed", code=…))`) instead of logging and continuing.

**Tests.**
- `test_escpos_driver.py::test_issue_840_label_sends_gs_k_to_dummy`: `escpos.printer.Dummy`, a label from `LabelService` with `4791234567890`, and assert `b"\x1dk"` is in `dummy.output`.
- `test_issue_840_choose_barcode_ean13_code128c_b`.
- `test_issue_840_unencodable_barcode_fails_job`.

**Acceptance.**
- [ ] A label barcode sends `GS k`.
- [ ] Unencodable data fails the job visibly.

### #878 — The receipt's invoice barcode is wider than the paper

**Severity:** medium · **Size:** S · **Gate:** decided by **D10**: CODE128 `{B}`, with dimensions calculated to fit the longest allowed document number on 58 mm and 80 mm. A human verifies the print.

**Root cause.**
- `sales_receipt_builder.py:227-229`: CODE39 with no width, so python-escpos's default `GS w 3`.
- The doc number can include a terminal prefix (Phase 2 #867 made prefixes longer: `TILL01-INV-2026-00001`).

**Fix.**
- Use CODE128 via `choose_barcode` (#840). For document numbers (alphanumeric) this is `{B`.
- Compute the module width: `modules = 11 × (len(data) + 3) + 2` (start, check, stop, plus the 2-module terminator); `width = max(1, min(3, PAPER_DOT_WIDTH[paper] // modules))`.
- If even width 1 doesn't fit the longest allowed number (`DOC_NUMBER_MAX_LENGTH` from `document_service.py`), print the number as text only and log it once. Always encode the document **number**, never the id: refund-by-scan reads the number. The unit test proves the fit.
- Pass `width` and a `height` of about 60 dots to `barcode()`.
- Check the refund-by-scan path parses CODE128-scanned numbers. Scanners emit the same text, so it should be unchanged; confirm with `graft grep "refund" --in cbpos/infrastructure/hardware/scanner.py` or the refund search.

**Tests.**
- `test_issue_878_longest_doc_number_fits_58_and_80mm`: for `DOC_NUMBER_MAX_LENGTH`, assert `width × modules ≤ PAPER_DOT_WIDTH`.
- `test_issue_878_receipt_uses_code128`.

**Manual.** Add the 58 mm and 80 mm print-and-scan check to the #731 matrix (⚠️ Verify on Windows).

**Acceptance.**
- [ ] The longest allowed document number fits both paper widths (unit test).
- [ ] Manual 58 mm and 80 mm print-and-scan check recorded.

### #877 — Long Sinhala/Tamil lines are clipped on 58 mm

**Severity:** medium · **Size:** M · **Gate:** agent

**Root cause.**
- `text_raster.py:42-95` (`render_text_line`) shrinks the font down to 14 px, then draws one line into a fixed width. There is no wrap.
- Only header and footer are pre-wrapped (`base_receipt_builder.py:146-152`).
- The shop address, customer name and item names overflow.

**Fix.**
- In `render_text_line`, when the text doesn't fit at `_MIN_PIXEL_SIZE`, lay it out with `QTextLayout`, or draw with `Qt.TextFlag.TextWordWrap` into a rect of the paper width.
- Compute the needed height with `QFontMetrics.boundingRect(rect, flags, text)`, create the image at that height, and draw. That's what `render_text_png` does; **reuse its code** (extract a shared `_draw_wrapped(text, font, width, align) -> QImage`).
- Keep alignment (centred text centres each wrapped line).
- Don't break inside a grapheme cluster: Qt's word wrap respects clusters. Add a test with a Sinhala conjunct near the break.

**Tests.**
- `test_text_raster.py::test_issue_877_sinhala_address_wraps_on_58mm`: the 53-code-point address gives an image height > 1 line and no ink in column 0 or column 383.
- `test_issue_877_tamil_line_wraps`.
- `test_issue_877_short_line_unchanged`.

**Manual.** A Sinhala and Tamil receipt print on 58 mm, added to the #731 matrix.

**Acceptance.**
- [ ] A long Sinhala or Tamil line on 58 mm renders taller, with no clipped ink and no dropped glyphs.

### #908 — Merged receipt lines show the wrong unit price and saving

**Severity:** low · **Size:** S · **Gate:** agent

**Root cause.** `sales_receipt_builder.py:267-287` (`_merge_items`) sums qty and subtotal but keeps the first line's `unit_price` and `original_price`.

**Fix (decided).** Merge only lines with the same `(product_id, unit_price, original_price, is_manual_price)`. Lines with different prices stay separate. That's the honest receipt. Savings per printed line = `(original_price − unit_price) × qty`.

**Test.** `test_issue_908_different_prices_not_merged_and_savings_correct`: 300 and 350 lines stay separate, and the total saving is 50.

**Acceptance.**
- [ ] Two lines of one product at 300 and 350 don't merge, and the saving printed is 50.

---

## Batch 7.3 — Scanner, signal and dashboard lifecycle

**Branch:** `fix/p7-b3-scanner-signal-dashboard-lifecycle`

### #841 — The scanner duplicates each key once per widget the key passes through

**Severity:** high · **Size:** S · **Gate:** agent

**Root cause.** `scanner.py:~62-74` buffers on every `KeyPress` delivered to any widget. Qt re-delivers an unaccepted key to each parent, so it's buffered once per hop.

**Fix.** Buffer only when `obj is QApplication.focusWidget()`. If `focusWidget()` is None, buffer when `obj` is the active window. Keep the timing logic. Add a de-dup guard as well: ignore an event whose `(event.timestamp(), event.key())` equals the last one buffered.

**Tests** (`tests/unit/test_barcode_scanner.py`):
- `test_issue_841_focus_on_nested_button_emits_exact_code`: a button two layouts deep has focus, then `QTest.keyClicks` + Return gives exactly `"4791234567890"`.
- The existing #546/#547/#548 tests still pass.

**Acceptance.**
- [ ] A scan with a nested button focused emits exactly the scanned string, and the existing scanner tests pass.

### #842 — After one reprint, the hidden Document view reacts to every later print job

**Severity:** high · **Size:** M · **Gate:** agent

**Root cause.**
- `document_view.py:861-882` connects `PrintWorker.job_completed` and `error_occurred` to the view and never disconnects. The view is cached for the app's lifetime (`management_view.py:185`).
- So every later receipt and drawer kick pops "Receipt … sent to printer".
- `history_view.py:387-394` (dead) has the same pattern.

**Fix.**
- The reprint stores `self._reprint_job_id = PrintWorker.instance().add_job(...)` and connects **once** (in `__init__`) to `job_result`.
- The handler is `if job_id != self._reprint_job_id: return`.
- Remove the old connect and disconnect code.
- Apply the same pattern to every other screen that connects to the print worker's signals: `graft grep "job_completed.connect\|error_occurred.connect" --in cbpos/ui`. Convert each one to `job_result` with id filtering, and list them in the PR.
- Delete `history_view.py` if it's truly unused (`graft callers HistoryView`). If anything references it, leave it but fix the same way.

**Tests.**
- `test_issue_842_document_view_ignores_other_jobs`: reprint once, then queue a receipt and a kick (with a Null printer), and assert the handler wasn't triggered for them (count calls).
- `test_issue_842_job_result_carries_id`.

**Acceptance.**
- [ ] After one reprint, unrelated receipt and kick jobs don't trigger the Documents handlers.
- [ ] HistoryView is fixed or deleted.

### #846 — The dashboard aborts the app when re-shown while a load is running

**Severity:** high · **Size:** S · **Gate:** agent

**Root cause.**
- `dashboard_view.py:564-567, 584-587, 613-616`: each `showEvent` creates a new parentless `QThread`, stored only in an attribute. Replacing the attribute garbage-collects a running thread, and Qt aborts.
- conftest replaces `start` with `run`, which hides this.

**Fix.**
- Start the loaders with `start_background_job(worker)` (`workers.py:97`), which keeps them alive.
- Add a `self._load_generation` counter: each refresh increments it, and each worker carries its generation. The result handler ignores results whose generation isn't current.
- Skip a refresh if one is already in flight for the same panel. Set a flag, and clear it on the result or error.
- Rename the custom `finished` signal on the dashboard workers (it shadows `QThread.finished`) to `loaded`, and update its connections.
- **Never connect `destroyed` to a lambda.** If the view needs to cancel on destruction, use `call_on_destroyed`.

**Tests.** A real-thread test (opt out of the conftest inline-start fixture for this module): `test_issue_846_refresh_twice_during_slow_load_no_crash`. Monkeypatch the dashboard service to sleep 0.3 s, call `refresh_all()` twice, and `qtbot.waitUntil` until no background jobs run. The process is still alive.

**Acceptance.**
- [ ] Re-showing during a slow load doesn't crash, and a real-thread test calls `refresh_all` twice.

---

## Batch 7.4 — Multilingual receipt and PDF output

**Branch:** `fix/p7-b4-multilingual-receipt-pdf`

### #805 — Thermal receipts always print English item names

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.** `sales_receipt_builder.py:119`, `void_receipt_builder.py:93` and `refund_receipt_builder.py:67` use `product.name_en`.

**Fix.**
- One helper `ProductService.display_name(product, lang) -> str`: `name_si` / `name_ta` / `name_en` by language, falling back to `name_en` when empty.
- **Use it in the A4 invoice too**, which already does this inline (`graft grep "name_si" --in cbpos/core/services/invoice_service.py`). Refactor it to the helper, so there's one rule.
- Builders use the receipt language setting. Non-Latin names go through the raster path; check how the builder routes non-Latin text today (`text_raster`) and make sure item lines use it.

**Tests.** For each builder: si with a localised name, si without one (English fallback), ta likewise.

**Acceptance.**
- [ ] Line names use the receipt language, falling back to English. Tests are added for each builder.

### #806 — The report PDF can't render Sinhala/Tamil

**Severity:** medium · **Size:** L · **Gate:** agent. The approach is decided by the issue comment's benchmark: xhtml2pdf can't shape, so **build report PDFs with ReportLab Platypus directly, using shaped Noto fonts** (option 1, shared with #924 in Phase 10A).
**Skills:** research (check ReportLab's shaping support in the **locked** version: `uv pip show reportlab`, plus its docs for `shaping`/`uharfbuzz`) → write a design note → `/egm-review` → tdd

**Evidence.** `export_service.py:~99` uses xhtml2pdf with Helvetica.

**Fix design.**
1. **Font module** `cbpos/infrastructure/pdf_fonts.py`: registers `NotoSans`, `NotoSansSinhala` and `NotoSansTamil` from `cbpos/assets/fonts` as `TTFont`s, plus a font-fallback helper `font_for(text) -> str` that picks by Unicode block (Sinhala U+0D80–0DFF, Tamil U+0B80–0BFF, else NotoSans).
2. **Shaping:**
   - If the locked ReportLab version supports HarfBuzz shaping (ReportLab ≥ 4.x with `uharfbuzz` installed and `rl_config.shapedFonts` or the equivalent), enable it, and add `uharfbuzz` with `uv add` if missing. **Verify by rendering a Sinhala conjunct** (e.g. "ශ්‍රී") and visually checking the output PDF. Attach a screenshot to the PR.
   - If shaping isn't available in the locked version, use option 3 (the PNG raster workaround the A4 invoice uses) **per text cell with non-Latin text**. Record the decision as D18, and Stop & Ask before upgrading ReportLab.
3. **Report PDF builder** `cbpos/core/services/report_pdf_builder.py`:
   - Platypus `SimpleDocTemplate` with a title, filter summary, table (with repeat header rows), totals, and a footer with CB POS branding and the website (§0.2 Branding);
   - text in each cell uses `font_for(text)`.
   - `export_service` uses it for PDF and drops xhtml2pdf for reports. Keep xhtml2pdf if other features use it (`graft grep "xhtml2pdf"`).
4. Build PDFs off the UI thread. They already go through the report export worker? Verify, and if not, use `start_background_job`.

**Tests.**
- `test_issue_806_report_pdf_uses_noto_fonts_for_si_ta`: generate a PDF with si and ta product names, parse it with `pypdf` (if available; else check the font names embedded with a regex on the bytes), and assert NotoSansSinhala and NotoSansTamil are embedded.
- Golden images aren't required.
- **Manual:** sample PDFs in si and ta attached to the PR (D1 matrix).

**Acceptance.**
- [ ] An exported PDF in si and ta shows readable, correctly shaped headings and product names, with sample PDFs attached.

### #807 — Hard-coded English, and 16 missing Tamil keys

**Severity:** low · **Size:** S · **Gate:** agent (Tamil translations follow §0.12 P7; if unsure, use the English value and list the key in PROGRESS.md for human review)

**Evidence.**
- `main.py:103-107` (crash dialog).
- `scheduler_service.py:16,94,114,132-150` (daily email subject, body and PDF title).
- `ta.json` is missing 16 keys:
  - `receipt_reprint.filter_{today,yesterday,this_week,this_month}`, `receipt_reprint.preview_title`, `receipt_reprint.select_to_preview`;
  - `sale_history.{change,copied,copied_to_clipboard,copy_invoice_tooltip,discount,grand_total,sales_found,subtotal,tax,tendered}`.

**Fix.**
1. Crash dialog:
   - keys `crash.title` and `crash.body` ("CB POS ran into a problem and needs to close. Your sales are saved. Please open CB POS again. If this keeps happening, send the log file from {path} to support.");
   - the crash handler must not fail if i18n isn't loaded yet: wrap `_t` in try/except and fall back to the English literal **only in this handler**, with a comment.
2. Daily email: `translate_in(receipt_language, ...)` for the subject, body and PDF title. Keep the CB POS footer.
3. Add the 16 Tamil keys using the existing `sale_history` / `receipt_reprint` Tamil vocabulary in `ta.json`, so they stay consistent with the neighbouring keys.
4. Guardrail test `test_i18n_key_parity`: the en, si and ta flattened key sets are identical, and `{param}` sets match per key. Extend `validate_translations.py --strict` if it already does this, and call it from the test.

**Tests.** The parity test, plus `test_issue_807_daily_email_uses_receipt_language`.

**Acceptance.**
- [ ] The crash dialog, daily email and PDF title use `_t` / `translate_in`. The email uses the receipt language.
- [ ] The 16 Tamil keys are added per the quality checklist.
- [ ] A test asserts the en, si and ta key sets are identical.

---

## Phase exit gate
- [ ] All 14 issues merged and **verified closed** with closing comments (§0.10). #731 and #878 stay open with `ready-for-human` until the matrix is done.
- [ ] Guardrails green: i18n key parity; no print-worker listener without job-id filtering (`graft grep` result pasted in the PR).
- [ ] The **#731 matrix** has been completed by a human (D1): 58 mm, 80 mm, A4 and Print to PDF, covering:
  - an English, Sinhala and Tamil receipt;
  - a label with a barcode;
  - the receipt invoice barcode scanned back for a refund;
  - a large report;
  - an A4 invoice to a named printer;
  - cancel and offline errors.
- [ ] Full suite green once per batch, and `pre-commit` clean.
- [ ] UI gate screenshots: print error notices, the PDF samples (si, ta), and a dashboard re-show with no crash.
- [ ] PROGRESS.md updated, with the i18n review list filled where Tamil was uncertain.
