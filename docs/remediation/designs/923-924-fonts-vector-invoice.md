# Design: Phase 10A.1 — Font Bundle Slimming (#923) and Vector Trilingual Invoices (#924)

## Overview & Goals

Phase 10A.1 resolves two packaging and document quality defects:
1. **#923 (Font Bundle Slimming)**: CB POS currently bundles 16 font files (6.39 MB raw, ~2.9 MB installer payload). 4 italic variants are never referenced by Qt stylesheets or code, and the Latin fonts contain thousands of glyphs for languages never used in Sri Lankan retail. Subsetting Noto Sans Latin to relevant character ranges (Latin, extended Latin, currency symbols, box drawing, arrows) while preserving full metadata (`--name-IDs='*'`) reduces the bundle to 12 files (~1.92 MB raw, ~0.8 MB installer) while preserving all QSS weights (400, 500, 600, 700).
2. **#924 (Vector Trilingual Invoices)**: A4 commercial invoices, statutory VAT tax invoices, warranty certificates, and RMA waybills historically rasterized Sinhala and Tamil text into 300 DPI PNG images via Qt `render_text_png`. With `uharfbuzz` and ReportLab shapable TTFonts (introduced in Phase 7 #806 for report tables), all A4 invoice text can now be rendered natively as vector text using `ParagraphStyle(shaping=1)`. This produces crisp, scalable text, smaller PDF files, and eliminates the Qt rasterization dependency during PDF compilation.

---

## Architecture (Elephant View)

```
[scripts/font_sources/] (Full upstream TTF files + OFL licenses + CHECKSUMS)
        │
        ▼ (scripts/subset_fonts.py via fonttools with PEP 723 metadata)
[cbpos/assets/fonts/] (Bundled in git & PyInstaller)
   ├── Noto_Sans/static/
   │     ├── NotoSans-Regular.ttf  (~150 KB subset)
   │     ├── NotoSans-Medium.ttf   (~150 KB subset)
   │     ├── NotoSans-SemiBold.ttf (~150 KB subset)
   │     └── NotoSans-Bold.ttf     (~150 KB subset)
   ├── Noto_Sans_Sinhala/static/ (4 static weights, unsubsetted: Regular, Medium, SemiBold, Bold)
   └── Noto_Sans_Tamil/static/   (4 static weights, unsubsetted: Regular, Medium, SemiBold, Bold)
        │
        ├──────────────────────────────────────────────────┐
        ▼                                                  ▼
[Qt UI: ResourceLoader]                      [PDF: pdf_fonts.py]
 - QFontDatabase registers 3 families:        - Registers TTFonts in ReportLab:
   1. "Noto Sans" (Regular, Medium,             NotoSans, NotoSans-Bold
      SemiBold, Bold)                           NotoSansSinhala, NotoSansSinhala-Bold
   2. "Noto Sans Sinhala"                       NotoSansTamil, NotoSansTamil-Bold
   3. "Noto Sans Tamil"                       - Checks `is_shaping_available()` (uharfbuzz)
 - Injects fallback chains in QSS:            - Configures `ParagraphStyle(shaping=1, parent=style)`
   "Noto Sans", "Noto Sans Sinhala",          - Provides `make_shaped_paragraph()` with
   "Noto Sans Tamil"                            newline-to-<br/> conversion & XML escaping
                                              - Standardizes on NotoSans across all builders
                                              - Fallback to `render_text_png` ONLY if
                                                uharfbuzz is genuinely missing (ImportError)
                                                           │
                                                           ▼
                                         [Invoice & PDF Builders]
                                          - InvoiceService (A4 Commercial Invoice)
                                          - TaxInvoicePDFBuilder (A4 Statutory VAT Invoice)
                                          - WarrantyCardBuilder (A4/A5 Warranty Certificate)
                                          - WarrantyClaimReceiptBuilder (A5 RMA Waybill)
```

---

## Detailed Specifications (Goldfish Invariants)

### Invariant 1: Font Source Preservation & Exclusion
- Full upstream original Noto Sans fonts (all 8 static variants including Italics) are archived in `scripts/font_sources/Noto_Sans/static/` alongside `OFL.txt` and `CHECKSUMS.txt`.
- `scripts/font_sources/` is strictly outside `cbpos/assets/` and is NOT referenced in `cbpos.spec` `datas`, preventing source fonts from inflating the installer bundle.

### Invariant 2: Idempotent Subsetting Tooling
- `scripts/subset_fonts.py` contains PEP 723 script metadata:
  ```python
  # /// script
  # dependencies = ["fonttools>=4.50.0"]
  # ///
  ```
- It reads originals from `scripts/font_sources/Noto_Sans/static/` and subsets the 4 non-italic weights:
  - `NotoSans-Regular.ttf`
  - `NotoSans-Medium.ttf`
  - `NotoSans-SemiBold.ttf`
  - `NotoSans-Bold.ttf`
- The subset command uses the corrected unicode ranges containing `U+2500-25FF`:
  ```bash
  pyftsubset <font.ttf> \
    --unicodes='U+0000-024F,U+0259,U+02B0-036F,U+1E00-1EFF,U+2000-22FF,U+2500-25FF,U+FEFF,U+FFFD' \
    --layout-features='*' \
    --name-IDs='*' \
    --name-languages='*' \
    --output-file=<target.ttf>
  ```
- Running `python scripts/subset_fonts.py` multiple times produces bit-identical files with identical SHA-256 hashes.
- Unicode coverage retains:
  - Basic Latin & Latin-1 Supplement (ASCII, common European characters, currency symbols like `£`, `€`, `¥`)
  - Latin Extended-A and B
  - General Punctuation (`U+2000-206F`), Currency Symbols (`U+20A0-20CF`, including Sri Lankan Rupee `₨` and Indian Rupee `₹`)
  - Letterlike Symbols, Number Forms, Arrows (`U+2190-21FF`)
  - Mathematical Operators, Miscellaneous Technical, Box Drawing (`U+2500-257F`), Block Elements (`U+2580-259F`), Geometric Shapes (`U+25A0-25FF`)
  - Replacement Character `U+FFFD` and Byte Order Mark `U+FEFF`.
- Retaining `--name-IDs='*'` ensures typographic family/subfamily records (name IDs 16, 17, 21, 22) are preserved so Qt recognizes Medium (500) and SemiBold (600) as weights of "Noto Sans" rather than distinct top-level families.

### Invariant 3: Qt Font Registration Integrity
- `ResourceLoader.load_fonts()` walks `cbpos/assets/fonts/` (now containing 12 files).
- Registered font family count is exactly 3:
  - `Noto Sans`
  - `Noto Sans Sinhala`
  - `Noto Sans Tamil`
- `QFontDatabase.styles("Noto Sans")` includes `"Regular"`, `"Medium"`, `"SemiBold"`, and `"Bold"`.
- Weight mapping verifies:
  - Weight 400 maps to Regular
  - Weight 500 maps to Medium
  - Weight 600 maps to SemiBold
  - Weight 700 maps to Bold
- Zero font loading failures (`failed_count == 0`).

### Invariant 4: Vector Sinhala & Tamil Invoices via ReportLab + HarfBuzz
- `cbpos/infrastructure/pdf_fonts.py` registers:
  - `NotoSans`, `NotoSans-Bold`
  - `NotoSansSinhala`, `NotoSansSinhala-Bold`
  - `NotoSansTamil`, `NotoSansTamil-Bold`
  - Associated `FontFamily` definitions.
- `pdf_fonts.py` exposes `make_shaped_paragraph(text, style, width=None)`:
  - Converts newlines to `<br/>` and XML-escapes text:
    ```python
    val = "" if text is None else str(text)
    escaped = xml.sax.saxutils.escape(val).replace("\n", "<br/>")
    ```
  - Standardizes on `NotoSans` / `NotoSans-Bold` for Latin and numeric text instead of Type 1 Helvetica, ensuring uniform typography and consistent metrics across scripts.
  - Inspects text for Sinhala (`0x0D80..0x0DFF`) and Tamil (`0x0B80..0x0BFF`).
  - If Sinhala or Tamil is present and `is_shaping_available()` is True:
    - Font resolves to `NotoSansSinhala` / `NotoSansSinhala-Bold` or `NotoSansTamil` / `NotoSansTamil-Bold`.
    - Creates `ParagraphStyle` inheriting from `parent=style`:
      ```python
      shaped_style = ParagraphStyle(
          f"{style.name}_{font_name}",
          parent=style,
          fontName=font_name,
          shaping=1,
      )
      ```
    - Returns `Paragraph(escaped, shaped_style)`.
  - If text is purely Latin/numeric:
    - Font resolves to `NotoSans` (or `NotoSans-Bold` if style indicates bold).
    - Returns `Paragraph(escaped, shaped_style)`.
  - Fallback boundary: If and only if `not is_shaping_available()` (i.e. `uharfbuzz` failed to import), calls `render_text_png` and wraps in `Image(BytesIO(png), ...)`. Unrelated exceptions during layout or PDF construction fail closed and propagate.
- Updated entry points:
  1. `cbpos/core/services/invoice_service.py` (`_text`)
  2. `cbpos/core/services/tax_invoice_pdf_builder.py` (`_text`)
  3. `cbpos/core/services/warranty_card_builder.py` (`_text`)
  4. `cbpos/core/services/warranty_claim_receipt_builder.py` (`_p`)
- Resulting PDF streams for Sinhala and Tamil invoices contain zero raster Image XObjects for shaped text (only vector text operations and embedded TrueType font subsets).

### Invariant 5: Known Limitations & Statutory Verification
- Known ReportLab limitation: Copied/selected text for complex ligatures (e.g. `ශ්‍රී`, conjuncts) in ReportLab may not decode back to standard Unicode characters due to ReportLab's ToUnicode CMap generator. However, vector rendering, screen clarity, and physical printing are 100% sharp and accurate. This limitation is explicitly documented in release notes.
- Physical Windows printer verification remains tracked under ⚠️ Verify on Windows.

---

## Test & Verification Plan

Per `RELEASE_PLAN.md §0.8`, tests are organized in standard test layers with explicit issue-tagged names:

1. **`tests/guardrails/test_font_bundle.py`**:
   - `test_issue_923_font_bundle_slimming_and_weights`:
     - Asserts the 4 italic TTF files are deleted from `cbpos/assets/fonts/Noto_Sans/static/`.
     - Asserts total font count across all subdirectories of `cbpos/assets/fonts/` is exactly 12.
     - Asserts total raw font bundle size is under 2.0 MB (target ~1.92 MB).
     - Asserts `QFontDatabase.applicationFontFamilies()` registers exactly `Noto Sans`, `Noto Sans Sinhala`, and `Noto Sans Tamil`.
     - Asserts `QFontDatabase.styles("Noto Sans")` includes `"Regular"`, `"Medium"`, `"SemiBold"`, and `"Bold"`.
     - Asserts critical symbols (`₨`, `₹`, arrows, box drawing `─`, `│`, `┌`, `┐`, `└`, `┘`) exist in the subset `Noto Sans`.
   - `test_issue_923_subset_idempotency`:
     - Executes `scripts/subset_fonts.py` twice.
     - Asserts SHA-256 hashes of generated font files are byte-for-byte identical.

2. **`tests/domain/test_vector_invoice.py`**:
   - `test_issue_924_vector_invoice_contains_no_raster_images`:
     - Builds trilingual test documents across all 4 builders:
       1. `InvoiceService.generate_pdf`
       2. `TaxInvoicePDFBuilder.generate_pdf`
       3. `WarrantyCardBuilder.build_pdf`
       4. `WarrantyClaimReceiptBuilder.build_rma_dispatch_pdf`
     - Inspects generated PDF pages and verifies that zero `Image` or raster XObjects exist for shaped text.
     - Asserts `NotoSansSinhala` and `NotoSansTamil` are embedded in the PDF font resources.
   - `test_issue_924_complex_indic_shaping`:
     - Renders complex Sinhala and Tamil test strings (`ශ්‍රී`, `ක්‍ෂ`, `කෝ`, `ொ`, `பு`) through `make_shaped_paragraph`.
     - Verifies `style.shaping == 1` and `style.fontName` matches the script.
     - Verifies newlines are converted to `<br/>` and `parent=style` preserves alignment, font size, and color.
   - `test_issue_924_fallback_to_png_on_import_error`:
     - Patches `is_shaping_available` to return `False`.
     - Asserts builders fall back to `render_text_png` and embed an `Image` Flowable without crashing.

3. **UI Gate**:
   - Before and after screenshots across the 5 busiest screens (`SalesView`, `InventoryView`, `SaleHistoryView`, `DashboardView`, `ReportViewer`) in dark/light and en/si/ta at 1366×768.
