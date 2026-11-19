# Design: Phase 10A.2 — Receipt Font Choice with Live Preview (#925)

## Overview & Goals

Phase 10A.2 (#925) implements a curated receipt font selection system for trilingual (Sinhala/English/Tamil) receipts in CB POS:
1. **Owners need layout control**: Small shops printing on 58mm or 80mm thermal paper often struggle with line length. Certain fonts (like Yaldevi) fit up to 26% more characters per line than standard Noto Sans, allowing item descriptions and addresses to fit on fewer lines.
2. **Prevent bad thermal output**: Most arbitrary system fonts break or become unreadable when rendered at 203 DPI 1-bit thermal resolution. Therefore, free font pickers are strictly avoided. CB POS offers a tested, curated list:
   - **Clear (default & recommended)**: Noto Sans Sinhala, Noto Sans Tamil, Noto Sans. Crisp and legible.
   - **Compact**: Yaldevi for Sinhala (narrower glyphs, +26% characters per line); retains Noto Sans Tamil for Tamil (since Yaldevi contains no Tamil glyphs) and Noto Sans for Latin.
   - **Windows Nirmala UI**: Supported only on Windows if benchmark criteria pass; kept hidden otherwise. Never offer arbitrary system fonts.
3. **Single deep seam**: A unified `ReceiptFontService.current()` provides the active preset configuration across both 1-bit thermal rasterization (`text_raster.render_text_line`) and A4 vector PDF output (`pdf_fonts.py`).
4. **Live preview equals print**: The Receipt settings page features a live preview that renders sample receipt lines through the real `render_text_line` raster pipeline at the selected 58mm/80mm paper width and currently selected font preset (even before saving).
5. **Print test receipt**: A dedicated "Print test receipt" button queues the test receipt on the background `PrintWorker`, tracks its specific `job_id`, and reports success only after the matching job completes.

---

## Architecture (Elephant View)

```
[ConfigService: "receipt_font_preset" ("clear" | "compact" | "nirmala")]
                                │
                                ▼
                   [ReceiptFontService.current()]
                                │
        ┌───────────────────────┼────────────────────────┐
        ▼                       ▼                        ▼
[text_raster.py]        [pdf_fonts.py]          [Settings -> Receipt]
 - `_font()` queries     - `font_for()` &        - Radio group: Clear / Compact
   `get_font_families()`   `make_shaped_paragraph` - Live preview via
 - Thermal raster uses     use Yaldevi for si in   `ReceiptPreviewWidget` +
   Noto or Yaldevi         Compact mode with       `render_text_line`
 - Accepts explicit        shaping=1 (HarfBuzz)  - Passes unsaved preset to
   `font_families`       - Registers Yaldevi       preview & test print
 - 58mm (384 dots) /       in ReportLab TTFonts  - "Print test receipt" button
   80mm (576 dots)         (normal & bold)         dispatches to PrintWorker
        │                       │                        │
        ▼                       ▼                        ▼
[ESCPOSDriver]          [A4 / A5 Invoices]       [PrintWorker Queue]
 - Real thermal receipt  - Vector PDF invoice    - Tracks unique `job_id`
   matches preview         with compact font     - `job_result` signal filter
```

---

## Detailed Specifications (Goldfish Invariants)

### Invariant 1: Font Bundling & Upstream Provenance
- Yaldevi variable TrueType font is bundled under `cbpos/assets/fonts/Yaldevi/`:
  - `Yaldevi[wght].ttf` (469,216 bytes, SHA-256: `21d5516cd9a8831964b57503f5b7a119aafa9603bdddd0183e91a0ac8c8dc2e4`)
  - `OFL.txt` (SIL Open Font License v1.1, Copyright 2020 The Yaldevi Project Authors / Mooniak)
- Font name table is normalized so Qt's `QFontDatabase.addApplicationFont` registers family `"Yaldevi"` with styles `['Regular', 'Medium', 'SemiBold', 'Bold']`.
- `scripts/gen_third_party_notices.py` includes a static entry for the bundled Yaldevi font under SIL OFL 1.1, and the generated `THIRD_PARTY_NOTICES.txt` deterministically documents it.
- Font bundle guardrail tests in `tests/guardrails/test_font_bundle.py` are updated to expect:
  - 13 font files total (12 Noto + 1 Yaldevi).
  - Raw bundle size < 2.5 MB (target ~2.3 MB).
  - Qt registered families: `{"Noto Sans", "Noto Sans Sinhala", "Noto Sans Tamil", "Yaldevi"}`.
  - Styles for `"Yaldevi"` include `Regular`, `Medium`, `SemiBold`, `Bold`.

### Invariant 2: Deep `ReceiptFontService` Seam & Config Defaults
- Service located at `cbpos/core/services/receipt_font_service.py`.
- Presets:
  - `PRESET_CLEAR = "clear"` (Default)
  - `PRESET_COMPACT = "compact"`
  - `PRESET_NIRMALA = "nirmala"`
- Added to `ConfigService.DEFAULTS`:
  - `"receipt_font_preset": "clear"`
- Key API methods:
  - `ReceiptFontService.current() -> str`: Returns active preset ID from `ConfigService.get("receipt_font_preset")`, falling back to `"clear"` if missing or invalid.
  - `ReceiptFontService.set_preset(preset: str) -> None`: Validates and persists the setting via `ConfigService.set("receipt_font_preset", preset)`.
  - `ReceiptFontService.is_nirmala_available() -> bool`: Returns `True` strictly on Windows (`sys.platform == "win32"`) if `"Nirmala UI"` is detected in system fonts.
  - `ReceiptFontService.get_available_presets() -> list[dict]`: Returns available presets with translated names and descriptions. Excludes Nirmala UI on non-Windows platforms.
  - `ReceiptFontService.get_font_families(preset: str | None = None) -> list[str]`:
    - `"clear"`: `["Noto Sans Sinhala", "Noto Sans Tamil", "Noto Sans"]`
    - `"compact"`: `["Yaldevi", "Noto Sans Tamil", "Noto Sans"]`
    - `"nirmala"`: `["Nirmala UI", "Noto Sans Sinhala", "Noto Sans Tamil", "Noto Sans"]`
  - `ReceiptFontService.get_pdf_font_name(lang: str, bold: bool = False, preset: str | None = None) -> str`:
    - If preset is `"compact"` and `lang == "si"`: returns `"Yaldevi-Bold"` if bold else `"Yaldevi"`.
    - Otherwise returns standard NotoSans families (`NotoSansSinhala`, `NotoSansTamil`, `NotoSans`).

### Invariant 3: Thermal Raster & A4 PDF Plumbing (Complex Script Shaping)
- In `cbpos/infrastructure/hardware/text_raster.py`:
  - `_font(bold: bool, pixel_size: int, font_families: list[str] | None = None) -> QFont`:
    - Resolves `font_families = font_families or ReceiptFontService.get_font_families()`.
    - Sets `font.setFamilies(font_families)`.
  - `render_text_line(command: dict, paper_width: str = "80mm", font_families: list[str] | None = None) -> Image.Image`:
    - Resolves `font_families = font_families or command.get("font_families") or ReceiptFontService.get_font_families()`.
    - Passes `font_families` to `_font`.
- In `cbpos/infrastructure/pdf_fonts.py`:
  - `register_pdf_fonts()` registers `Yaldevi`:
    - `ttfonts.TTFont("Yaldevi", str(font_dir / "Yaldevi/Yaldevi[wght].ttf"))`
    - `ttfonts.TTFont("Yaldevi-Bold", str(font_dir / "Yaldevi/Yaldevi[wght].ttf"))`
    - `pdfmetrics.registerFontFamily("Yaldevi", normal="Yaldevi", bold="Yaldevi-Bold")`
  - In `font_for(text: str)`:
    - If text has Sinhala and `ReceiptFontService.current() == "compact"`: returns `"Yaldevi"`.
  - In `make_shaped_paragraph()`:
    - Update complex script detection:
      `is_complex = font_base in ("NotoSansSinhala", "NotoSansTamil", "Yaldevi")`
    - Ensures ReportLab sets `shaping=1` (HarfBuzz) for `Yaldevi`, properly shaping Sinhala ligatures and diacritics.

### Invariant 4: Settings UI (`ReceiptPage`) & Live Preview Propagation
- In `cbpos/ui/views/settings_pages/receipt.py`:
  - New section in Tab 1 (under Receipt Language): `"settings.receipt.section_receipt_font"` with a radio button group:
    - Clear (recommended) (`rb_font_clear`)
    - Compact (`rb_font_compact`)
    - Nirmala UI (`rb_font_nirmala`, visible only on Windows when available)
  - Selecting a radio button restarts debounce timer and triggers `_refresh_preview()`.
  - `load(settings)` populates the radio selection from `settings.get("receipt_font_preset", "clear")`.
  - `save()` exports `"receipt_font_preset": selected_preset`.
  - In `_refresh_preview()`:
    - Retrieves active radio preset: `selected_preset = self._current_selected_preset()`.
    - Calls `self._preview.set_font_preset(selected_preset)`.
    - Passes `config["receipt_font_preset"] = selected_preset` to `ReceiptBuilder.build_receipt(..., config_override=config)`.
    - Injects `cmd["font_families"] = ReceiptFontService.get_font_families(selected_preset)` into commands so unsaved on-screen choices render immediately.

### Invariant 5: Live Preview Pipeline
- `ReceiptPreviewWidget` in `cbpos/ui/widgets/receipt_preview_widget.py`:
  - Stores `self._font_preset: str = "clear"` and provides `set_font_preset(preset: str) -> None`.
  - When rendering text commands (`ctype == "text"`): lines that contain Sinhala or Tamil characters (`needs_raster(raw)` or `needs_raster(left_val)` or `needs_raster(right_val)`) are rendered via `render_text_line(cmd, paper_width, font_families=families)` into 1-bit thermal images and embedded as base64 PNG data URIs.
  - Because `render_text_line` uses the passed/configured font families, switching between Clear and Compact immediately updates the rendered glyph shapes in the preview without requiring a page save.
  - `ReceiptPage._make_dummy_sale()` is enhanced with Sinhala and Tamil product names:
    - `Product(name_en="Milk Powder 400g", name_si="කිරි පිටි 400g", name_ta="பால் மா 400g")`
    - `Product(name_en="White Sugar 1kg", name_si="සුදු සීනි 1kg", name_ta="வெள்ளை சீனி 1kg")`
    - `Product(name_en="Samba Rice 5kg", name_si="සම්බා සහල් 5kg", name_ta="சம்பா அரிசி 5kg")`
    Ensuring that the preview exhibits the chosen font regardless of UI language.

### Invariant 6: "Print Test Receipt" Execution & Single-Connected Signal
- Dedicated button `btn_print_test` placed below preview scroll area in the right panel.
- In `ReceiptPage.init_ui()`:
  - Connects `PrintWorker.instance().job_result.connect(self._on_test_print_job_result)` **once**.
  - Registers cleanup on widget destruction using `call_on_destroyed(self, self._cleanup_print_signals)` to disconnect the signal cleanly.
- On click (`_on_print_test_clicked()`):
  1. Disables button, sets status text to `_t("settings.receipt.test_print_status_printing")`.
  2. Builds receipt commands for the sample sale with current settings and previewed width (`ReceiptBuilder.build_receipt(dummy_sale, config_override)`).
  3. Injects `cmd["font_families"] = ReceiptFontService.get_font_families(selected_preset)` into commands.
  4. Dispatches job: `self._test_print_job_id = PrintWorker.instance().add_job("print_receipt", commands)`.
- In `_on_test_print_job_result(self, job_id: str, ok: bool, message: str)`:
  - If `self._test_print_job_id is None or job_id != self._test_print_job_id`: return.
  - `self._test_print_job_id = None`.
  - `self.btn_print_test.setEnabled(True)`.
  - If `ok`:
    - `self.lbl_print_test_status.setText(_t("settings.receipt.test_print_status_success"))`.
  - Else:
    - `self.lbl_print_test_status.setText(_t("settings.receipt.test_print_status_failed"))`.
    - Shows non-blocking warning / error message: `QMessageBox.warning(self, _t("common.error"), message or _t("settings.receipt.test_print_status_failed"))`.

### Invariant 7: Benchmark Tooling (`scripts/font_benchmark.py`)
- Standalone CLI benchmark script:
  - Ensures headless Qt safety: instantiates `QGuiApplication(sys.argv)` (defaulting `QT_QPA_PLATFORM=offscreen` if `DISPLAY` is unset).
  - Explicitly calls `ResourceLoader.load_fonts()` before running queries.
  - Tests rendering of benchmark strings (Sinhala phrases, Tamil phrases, conjuncts: ශ්‍රී, ක්‍ෂ, ර්‍ය, ප්‍ර, ஸ்ரீ, க்ஷ) across 58mm (384 dots) and 80mm (576 dots) at 14–24 px.
  - Measures:
    - Rendering time (microseconds/ms per line).
    - Character capacity (characters per line before wrap/shrink).
    - Conjunct shaping validity.
  - Outputs formatted Markdown/text table comparing Noto Sans vs Yaldevi (and Nirmala UI on Windows).

### Invariant 8: i18n Translation Catalogue
- The following keys are added to `en.json`, `si.json`, `ta.json`:
  - `settings.receipt.section_receipt_font`
  - `settings.receipt.font_clear`
  - `settings.receipt.font_clear_desc`
  - `settings.receipt.font_compact`
  - `settings.receipt.font_compact_desc`
  - `settings.receipt.font_nirmala`
  - `settings.receipt.font_nirmala_desc`
  - `settings.receipt.btn_print_test`
  - `settings.receipt.test_print_status_printing`
  - `settings.receipt.test_print_status_success`
  - `settings.receipt.test_print_status_failed`

---

## Verification Plan

### Automated Tests
1. **Domain / Service**:
   - `tests/domain/test_receipt_font_service.py`:
     - Test default preset is "clear".
     - Test setting and retrieving presets.
     - Test fallback on unknown preset.
     - Test font families returned for each preset.
     - Test PDF font name mapping for English, Sinhala, Tamil.
     - Test Nirmala UI detection logic (mocked on Windows and non-Windows).
2. **Infrastructure / Hardware**:
   - `tests/ui/printing/test_receipt_font_raster.py`:
     - Test `render_text_line` output dimensions and pixel values with Noto vs Yaldevi.
     - Verify Yaldevi yields higher character density on Sinhala test line before wrapping.
     - Verify `pdf_fonts.py` shapes Yaldevi with HarfBuzz (`shaping=1`) and registers Yaldevi and Yaldevi-Bold.
3. **UI / Settings**:
   - `tests/ui/settings/test_receipt_font_settings.py`:
     - Test `ReceiptPage` loads and saves `receipt_font_preset`.
     - Test toggling radio button triggers preview refresh with unsaved font preset.
     - Test "Print test receipt" button queues job with `PrintWorker`, disables button, filters `job_result`, and re-enables button on completion.
4. **Guardrails**:
   - Update `tests/guardrails/test_font_bundle.py` to account for Yaldevi: 13 files, < 2.5 MB, and Qt styles.
   - Run `python scripts/gen_third_party_notices.py` and verify `THIRD_PARTY_NOTICES.txt` is updated.

### Manual / UI Gate Verification
- Capture screenshots of `ReceiptPage` in:
  - Dark & Light themes.
  - English, Sinhala, and Tamil languages.
  - Clear vs Compact preset selections.
  - 58mm and 80mm paper widths.
- Verify that keyboard navigation (Tab, Arrow keys, Space/Enter) works smoothly for font selection and test printing.
