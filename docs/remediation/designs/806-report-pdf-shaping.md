# Design Note: #806 Shaped Trilingual Report PDF Builder

## Overview & Citations
- **ReportLab**: 5.0.1 (locked in `pyproject.toml`/`uv.lock`, https://docs.reportlab.com/, accessed 2026-11-11). Directly supports HarfBuzz word shaping in `reportlab.pdfbase.ttfonts.TTFont` when `uharfbuzz` is importable and `ParagraphStyle(shaping=1)` is set.
- **uharfbuzz**: 0.57.0 runtime dependency added via `uv add uharfbuzz` (https://github.com/harfbuzz/uharfbuzz, accessed 2026-11-11).
- **Unicode Standards**: Sinhala `U+0D80..U+0DFF`, Tamil `U+0B80..U+0BFF` (Unicode Standard v15.0, https://www.unicode.org/charts/, accessed 2026-11-11).

## Architecture & Verified Specifications

### 1. Font Registration & Mixed-Script Fallback (`cbpos/infrastructure/pdf_fonts.py`)
- Registers `NotoSans` (Regular, Bold), `NotoSansSinhala` (Regular, Bold), and `NotoSansTamil` (Regular, Bold) from `cbpos/assets/fonts/` as `TTFont` instances via `pdfmetrics.registerFont`.
- Registers font families with `pdfmetrics.registerFontFamily` for all three fonts to ensure bold/normal styles resolve cleanly without `ValueError`.
- `font_for(text: str) -> str`: Checks Unicode ranges; returns `NotoSansSinhala` if Sinhala codepoints (`0x0D80..0x0DFF`) exist, `NotoSansTamil` if Tamil codepoints (`0x0B80..0x0BFF`) exist, else `NotoSans`. Both Indic Noto fonts bundle ASCII Latin characters and numbers, allowing mixed script + number cells.
- `escape_text(text: Any) -> str`: Converts `None`, `nan`, `pd.NA` to `"—"` or `""`, and escapes XML characters (`&`, `<`, `>`, `"`) using `xml.sax.saxutils.escape`.
- `format_cell_paragraph(val: Any, bold: bool = False, align: str = "left", font_size: int = 8) -> Paragraph`:
  Builds a shaped `Paragraph` using the appropriate font style (`shaping=1` when `uharfbuzz` is available).

### 2. Shaping Availability & Headless Fallback
- `is_shaping_available() -> bool` checks `import uharfbuzz`.
- Primary path: `shaping=1` on `ParagraphStyle`, yielding native HarfBuzz shaping for Sinhala conjuncts ("ශ්‍රී" -> `['shiivowelsinh', 'sharasinh']`) and Tamil ligatures ("க்ஷ" -> `['tchatamil']`).
- Fallback path (if `uharfbuzz` is missing): Renders non-Latin cell text via PIL PNG raster (`render_text_png` from `cbpos/core/services/invoice_service.py`), avoiding any PyQt UI dependencies in service threads.

### 3. Report PDF Builder (`cbpos/core/services/report_pdf_builder.py`)
- **Document Setup**: Platypus `SimpleDocTemplate`. A4 Portrait for <= 5 columns (width ~595 pt), A4 Landscape for > 5 columns (width ~842 pt). Margins: 12 mm (~34 pt).
- **Atomic Generation (Rule 4)**: Generates the PDF into a temporary file (`tempfile.NamedTemporaryFile`) and atomically renames (`os.replace`) to target `filepath` only upon successful `doc.build(story)`. On any exception, the temporary file is deleted, leaving no corrupt or 0-byte file on disk.
- **Deterministic Column Widths (`colWidths`)**:
  - Available printable width = `doc.width`.
  - Classifies columns as fixed-compact (ID: 35 pt, Date/Time: 75 pt, Qty: 45 pt, Unit Price/Amount/Total/Tax: 65 pt, Status: 50 pt).
  - Distributes remaining printable width proportionally among text/description columns based on average/max character length.
- **Alignment & Types**:
  - Headers: bold, centered or left/right matching column alignment.
  - Numbers/Currencies: right-aligned (`alignment=TA_RIGHT`), formatted with 2 decimal places for money.
  - Quantities: right-aligned, formatted via `format_quantity()`.
  - Descriptions/Names: left-aligned (`alignment=TA_LEFT`).
- **Table Styling**:
  - Header background: `#00BCEB` (teal), header text: `#FFFFFF` (white), bold.
  - Rows: subtle alternating row backgrounds (`#FFFFFF` and `#F8F9FA`).
  - Grid: 0.5 pt `#E0E0E0` borders, padding: `TOPPADDING=4`, `BOTTOMPADDING=4`, `LEFTPADDING=4`, `RIGHTPADDING=4`.
  - `repeatRows=1` so headers repeat on every page break.
- **Empty State**:
  - If DataFrame is empty, appends a single row spanning all columns displaying translated or fallback message: `"No records found for the selected period"`.
- **Branding & Footer**:
  - Dynamic page canvas callback (`_draw_page_decorations`): draws report title/timestamp in header on later pages if desired, and centered footer at `x = canvas._pagesize[0] / 2`, `y = 8 * mm`: `"Powered by CB POS — ceybyte.com"`.

### 4. Integration with `ExportService`, `ExportWorker`, and `SchedulerService`
- `ExportService.export_to_pdf(df, filepath, title)` delegates directly to `ReportPDFBuilder.build(df, filepath, title)`.
- Replaces legacy `xhtml2pdf` for all report generation.
- No `QPixmap` or Qt UI widget code is used anywhere in the PDF pipeline; pure Python and ReportLab Platypus.
- Can be safely called from background workers (`ExportWorker` in `cbpos/ui/workers.py`) and timer services (`SchedulerService._process_auto_report`).

### 5. PyInstaller Packaging (`cbpos.spec`)
- Adds `uharfbuzz` via `collect_all('uharfbuzz')` to `datas`, `binaries`, and `hiddenimports`.
- Bundled Noto fonts in `cbpos/assets/fonts/` are already bundled under `cbpos/assets`.
