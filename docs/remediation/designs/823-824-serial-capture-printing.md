# Technical Design: Serial/IMEI Capture & Warranty Printing (#823, #824)

**Phase:** 9 · **Batch:** 9.3  
**Issues:** #823 (Warranty W3), #824 (Warranty W4) · **Epic:** #820  
**Owner:** CB POS Remediation Team  
**Date:** 2026-11-13  
**Status:** APPROVED (Post-EGM Revisions Applied)  

---

## 1. Context & Objectives

In Phase 9 Batches 9.1 (#821) and 9.2 (#822), CB POS established:
- Reusable `WarrantyPolicy` models, product/category assignment precedence, calendar-aware duration arithmetic, and feature gating.
- Per-unit `Warranty` registration at checkout (`<doc_number>-01..NN`), whole-unit validation, void/refund cascades with per-unit cancellation, and LAN sync protocol 1.4.

**Batch 9.3 (#823, #824)** completes the checkout capture and customer-facing delivery of warranties:
1. **Product Serial Configuration (#823)**:
   - Expose `Product.serial_mode` (`OFF`, `OPTIONAL`, `REQUIRED`) in the Product Editor Warranty tab with label "Ask for serial / IMEI number when selling", visible only when `WarrantyService.is_enabled()`.
   - **Coupling Invariant:** Serial tracking requires a resolved warranty policy. Enabling `serial_mode in ("OPTIONAL", "REQUIRED")` requires the product to resolve to an active `WarrantyPolicy`. If `warranty_override == "NONE"` or no category default policy exists, assignment is rejected with `ValueError(_t("errors.serial_requires_warranty_policy"))`.
   - Permission-checked (`warranty.edit`) and audited via `InventoryService`.
2. **Cart Serial Bookkeeping (#823)**:
   - Cart line items gain an ordered slot list `serials: list[str | None]` with exactly one slot per whole unit.
   - Normalization: whitespace stripped, converted to uppercase; empty strings normalized to `None`.
   - Uniqueness: Non-empty serials must be unique across all lines in the entire cart.
   - Re-adding an existing serial-tracked product merges quantity, prompting only for newly added units without wiping already entered serials. Cancelling the prompt leaves the cart unmutated.
   - Reducing quantity trims from the end. `CartService.would_discard_serials(index, new_qty) -> list[str]` checks whether entered non-empty serials would be discarded; if so, `SalesView` prompts for cashier confirmation before applying `update_quantity`.
   - Cashiers can inspect and edit serials at any time prior to payment via context menu `_t("cart.context_edit_serials")`.
   - Held/suspended carts: Persist normalized serials in `SuspendedTransaction` JSON payload v2, restoring them upon recall, with seamless backwards compatibility.
3. **`SerialEntryDialog` UX (#823)**:
   - Clean, touch-friendly modal dialog (`objectName="SerialEntryDialog"`), 44px input rows, styled for both dark and light themes.
   - Sets `self.accepts_scans = True` and implements `process_barcode_external(self, barcode: str)` so application-level barcode scanner hooks route directly into the active dialog row.
   - First empty row receives initial focus. Barcode scanner `Enter` validates current input, normalizes, and automatically advances focus to the next row. Enter on the last row submits the dialog.
   - Modal isolation: `QApplication.activeModalWidget() is not None` ensures physical hardware scanner events never bleed into the background `SalesView`.
   - Required mode: `Esc` cancels the addition/update; no "Skip" button.
   - Optional mode: "Skip" button present; `Esc` skips (leaves slots as `None`). `Cancel` accessible via `Alt+C` or standard `Tab` focus.
   - Duplicate-in-cart inline validation error.
   - IMEI Luhn checksum helper: Advisory validation only runs when `len(serial) == 15 and serial.isdigit()`. Alphanumeric or non-15 digit serials bypass Luhn without warning.
   - Historical active warranty check: Batched query checks if serial currently has an `ACTIVE` warranty for the product; displays an advisory warning showing the prior receipt number (non-blocking).
4. **Checkout & Quick Cash Gates (#823)**:
   - Before opening `PaymentDialog` or executing `quick_pay` (F12), inspect all cart lines. If any `REQUIRED` line has unentered serials, automatically re-open the entry prompt. Payment cannot proceed until complete.
   - Service layer guard: `TransactionService._execute_sale` validates that all `REQUIRED` products have valid serials matching whole units, failing closed with `ValueError` if unsatisfied.
5. **Thermal Receipt Printing (#824)**:
   - `SalesReceiptBuilder`: Under each covered item line, print coverage details:
     `   Warranty: <duration> <unit> (<provider>) until <date>`
     and `   S/N: <serial>` for each unit with a serial.
   - Merged items list serials across all merged units. `ItemDisplay` gains `"warranties"` in `__slots__` and `_merge_items()` aggregates line warranties.
   - In reprint mode: If warranty is `VOID` or `CANCELLED`, print `[VOID]` or `[CANCELLED]` status tag.
   - After payments, append a compact "WARRANTY TERMS" block: Deduplicated across policies, formatted to printer width (32/42/48 chars) using `_wrap_free_text`.
   - Golden test: Receipts for sales with no warranty products remain byte-for-byte identical.
6. **A4 Invoices (#824)**:
   - Ordinary A4 invoice (`InvoiceService`) and Tax Invoice (`TaxInvoicePdfBuilder`): Include warranty coverage period, valid-until date, and serial numbers in line item descriptions/sub-rows, plus a warranty terms section before signatures.
   - `TaxInvoiceService.issue_artifact()` eager-loads `joinedload(TaxInvoice.sale).joinedload(Sale.warranties)` to prevent `DetachedInstanceError`.
7. **Standalone Warranty Card (#824)**:
   - `WarrantyCardBuilder` supporting:
     - 58mm / 80mm ESC/POS thermal commands dispatched to `PrintWorker.instance().add_job("print_commands", commands)`.
     - A5 / A4 ReportLab PDF generated off the Qt UI thread via `WarrantyCardPdfWorker` (or background thread).
   - Card contents: CB POS branding, shop metadata, receipt ref, dates, customer contact snapshot, remedy, terms, exclusions, signature box, and a CODE128 barcode of the warranty `code` via `choose_barcode`.
   - Multi-unit sales print individual cards per unit, terminated by an ESC/POS cut.
8. **Settings & Post-Sale Flow (#824)**:
   - Settings in `ReceiptPage`: `show_warranty_on_receipt` (default `True`), `warranty_card_mode` (`OFF`, `ASK`, `ALWAYS`; default `ASK`).
   - Frictionless checkout support:
     - If `warranty_card_mode == "ALWAYS"`, `SalesView._finalize_sale` spools card prints immediately via `PrintWorker` regardless of `show_receipt_dialog`.
     - If `warranty_card_mode == "ASK"`: If `show_receipt_dialog` is `True`, `ReceiptOptionsDialog` displays "Print Warranty Card(s)"; if `show_receipt_dialog` is `False`, `_finalize_sale` prompts with `QMessageBox.question`.
   - Reprint flow via `ReceiptReprintService`: Generates duplicate warranty cards with `REPRINT_WARRANTY_CARD` audit logging.
9. **Legal Gate (#824)**:
   - The statutory wording gate under CAA Act No. 9 of 2003 remains unresolved.
   - Print ONLY owner-entered terms/exclusions from policy snapshots.
   - Do NOT add, translate, expose, or print any fixed statutory-rights sentence.
   - Do NOT add `show_statutory_rights_note` setting.

---

## 2. Architecture & Data Flow

```
                      +-----------------------------+
                      |   Product Editor (UI)       |
                      |   Warranty Tab: serial_mode |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |      InventoryService       |
                      |  - enforce policy coupling  |
                      |  - validate_warranty_assign |
                      |  - audit PRODUCT_WARRANTY   |
                      +--------------+--------------+
                                     |
                                     v
+------------------+         +-------+--------+
| Scanner / Search | ------> |   SalesView    | <------- Held Bill Recall
+------------------+         +-------+--------+
                                     |
                         serial_mode != OFF?
                                     |
                                     v
                      +-----------------------------+
                      |      SerialEntryDialog      |
                      |  - accepts_scans = True     |
                      |  - process_barcode_external |
                      |  - N inputs (1 per unit)    |
                      |  - Scan -> auto-advance     |
                      |  - Cart uniqueness check    |
                      |  - 15-digit Luhn warning    |
                      |  - Active warranty warning  |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |         CartService         |
                      |  item["serials"] = [s1, s2] |
                      |  would_discard_serials()    |
                      +--------------+--------------+
                                     |
                           Checkout / Quick Cash
                                     |
                                     v
                      +-----------------------------+
                      |     TransactionService      |
                      |  - Validate REQUIRED mode   |
                      |  - Whole-unit enforcement   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |       WarrantyService       |
                      | register_for_sale_in_sess.  |
                      | assigns Warranty.serial_no  |
                      | backward-compatible tuples  |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |      Printing & Cards       |
                      |  - SalesReceiptBuilder      |
                      |    (ItemDisplay.warranties) |
                      |  - InvoiceService / A4 PDF  |
                      |  - WarrantyCardBuilder      |
                      |    - Thermal -> PrintWorker |
                      |    - PDF -> BackgroundThread|
                      +-----------------------------+
```

---

## 3. Component Details

### 3.1 Product Configuration & Permissions
- Model: `Product.serial_mode` (`String(10)`, values: `"OFF"`, `"OPTIONAL"`, `"REQUIRED"`, default `"OFF"`).
- In `ProductEditor`:
  - When `WarrantyService.is_enabled()`, expose `serial_mode_combo` with translated choices:
    - `"OFF"`: `product_editor.serial_mode_off` ("Off")
    - `"OPTIONAL"`: `product_editor.serial_mode_optional` ("Optional")
    - `"REQUIRED"`: `product_editor.serial_mode_required` ("Required")
  - Row label: `product_editor.serial_mode` ("Ask for serial / IMEI number when selling").
  - Gated by `Permissions.WARRANTY_EDIT` and disabled if `is_weighted` is checked or if effective warranty policy is None.
- In `InventoryService`:
  - Enforce `warr_actor_id = WarrantyService._resolve_actor(user_id, Permissions.WARRANTY_EDIT)` whenever `serial_mode` is provided or modified.
  - Reject `serial_mode != "OFF"` on weighted products (`ValueError`).
  - **Coupling Guard:** If `serial_mode in ("OPTIONAL", "REQUIRED")`, verify that the product has a resolved active warranty policy. If `warranty_override == "NONE"` or category policy is None, raise `ValueError(_t("errors.serial_requires_warranty_policy"))`.
  - Audit logging on create and update records `serial_mode` in `AuditLog` details under `WARRANTY_EVENT`.

### 3.2 Cart Serial Management (`CartService`)
- Each cart item dictionary carries:
  `item["serials"]: list[str | None]`
  Length is guaranteed to match `int(item["qty"])` for integer quantities.
- Helper methods on `CartService`:
  - `set_item_serials(index: int, serials: list[str | None])`: Normalizes entries (strips whitespace, uppercases non-empty strings, turns blank strings into `None`). Validates cart-wide uniqueness among non-empty serials.
  - `get_all_cart_serials(exclude_index: int | None = None) -> set[str]`: Returns all non-empty serials across all cart items except `exclude_index`.
  - `would_discard_serials(index: int, new_qty: Decimal) -> list[str]`: Returns list of non-empty serials that would be truncated if line `index` is reduced to `new_qty`.
  - `add_item(product, qty, serials=None)`:
    - If product already in cart, appends `[None] * int(qty)` or the provided new serials to existing `item["serials"]`.
    - If new product, initializes `item["serials"] = serials or [None] * int(qty)`.
  - `update_quantity(index, qty)`:
    - When expanding quantity (`qty > old_qty`), appends `[None] * (int(qty) - int(old_qty))`.
    - When reducing quantity (`qty < old_qty`), slices `item["serials"][:int(qty)]`.
- `SalesView` integration:
  - If reducing quantity discards any non-empty serial (via `would_discard_serials`), prompt for confirmation before invoking `update_quantity`.
  - Context menu on cart table offers `_t("cart.context_edit_serials")` for lines with `serial_mode != "OFF"`, reopening `SerialEntryDialog` populated with existing serials.
- `SuspendedTransactionService`:
  - When holding a bill: `lines_data` saves `item.get("serials", [])`.
  - When recalling a bill: restores `serials` on recalled cart item. If held bill is v1 or lacks serials, initializes `[None] * int(qty)`.

### 3.3 `SerialEntryDialog` UX & Behavior
- Class: `SerialEntryDialog(QDialog)`, `objectName="SerialEntryDialog"`.
- Properties: `self.accepts_scans = True`.
- Implements: `process_barcode_external(self, barcode: str)` to capture hardware scanner input:
  1. Sets barcode on currently focused line edit.
  2. Normalizes text.
  3. Validates and advances focus.
- Layout:
  - Header: Product name (`ProductService.display_name`) and unit count.
  - Scrollable container of N rows (one per unit, labeled "Unit 1", "Unit 2", etc.).
  - Each row contains:
    - Label: `_t("serial_entry.unit_label", index=i)`
    - `QLineEdit` (height: 44px, large clear font, styled for dark/light themes).
    - Status/warning indicator icon and label.
  - Buttons:
    - Required mode: `[OK / Confirm]` (primary), `[Cancel]` (`Esc`).
    - Optional mode: `[OK / Confirm]` (primary), `[Skip]` (secondary, `Esc`), `[Cancel]` (`Alt+C`).
- Scanner & Focus Invariants:
  - Initial focus set to the first empty row.
  - Scanner `Enter` on any row:
    1. Normalizes current text (strip + uppercase).
    2. Runs cart uniqueness check (cannot duplicate another row in dialog or another line in cart).
    3. If invalid, displays inline error and keeps focus on current field.
    4. If valid, runs advisory checks:
       - 15-digit IMEI Luhn check (gated to `len == 15 and isdigit()`) -> shows warning tooltip/label if invalid.
       - Batched active warranty check -> shows warning tooltip/label with prior receipt number if already active.
       - Advances focus to the next empty row.
    5. If all rows are satisfied and Enter is pressed on the final row, triggers dialog acceptance (`accept()`).
- Validation rules:
  - `REQUIRED`: All N rows must be non-empty and unique.
  - `OPTIONAL`: Rows can be blank (`None`). Any non-empty entries must be unique.

### 3.4 Transaction & Service Integration
- In `TransactionService._execute_sale`:
  - Extend batched resolution:
    - Fetch products and resolve `serial_mode`.
    - If any product has `serial_mode == "REQUIRED"`:
      - Verify integer quantity (`qty % 1 == 0`).
      - Verify `item["serials"]` exists, `len(serials) == int(qty)`, and every element is non-empty.
      - If missing or blank, raise `ValueError(_t("errors.serial_required", name=...))`.
    - Verify cart-wide uniqueness of all non-empty serials.
- In `WarrantyService.register_for_sale_in_session`:
  - Backward-compatible signature:
    ```python
    @classmethod
    def register_for_sale_in_session(
        cls,
        session: Session,
        sale: Sale,
        sale_items_with_policies: list[tuple[SaleItem, WarrantyPolicy] | tuple[SaleItem, WarrantyPolicy, list[str | None]]],
        receipt_lang: str | None = None,
        item_serials: dict[int, list[str | None]] | None = None,
    ) -> list[Warranty]:
    ```
  - Flexible unpacking ensures Batch 9.2 tests (which pass 2-tuples) remain completely green.
  - Assigns `warranty.serial_number = serials[unit_idx - 1]` in exact 1-based unit order.
  - If serial was blank/None, `warranty.serial_number = None`.

### 3.5 Printing & Receipt Builders (#824)
- **`SalesReceiptBuilder`**:
  - Controlled by `ConfigService.get("show_warranty_on_receipt")` (default `True`).
  - Under each warranty line:
    `   Warranty: 12 months (Shop) until 2027-11-13`
    For each unit with a serial number:
    `   S/N: 356912345678901`
  - Merged Items Support:
    - Add `"warranties"` to `ItemDisplay.__slots__`.
    - Update `_merge_items()` to aggregate `item.warranties` onto `ItemDisplay.warranties`.
    - Render all serials across merged units.
  - In reprint mode: If warranty is `VOID` or `CANCELLED`, print `[VOID]` or `[CANCELLED]` status tag.
  - Bottom compact "WARRANTY TERMS" block:
    - Appended after payments, before loyalty/barcode.
    - Title: `cls._rt("warranty_terms_title")` ("WARRANTY TERMS").
    - Terms and exclusions deduplicated per distinct policy snapshot.
    - Wrapped using `cls._wrap_free_text(text, line_chars)`.
    - Golden test: Non-warranty receipts produce identical command lists.
- **`InvoiceService` & `TaxInvoicePdfBuilder`**:
  - In items table: Append warranty coverage line and serial numbers under product description in Helvetica 8pt muted font.
  - Before signature section: Add "Warranty Terms" section listing deduplicated snapshot terms and exclusions.
  - `TaxInvoiceService.issue_artifact()` eager-loads `joinedload(TaxInvoice.sale).joinedload(Sale.warranties)`.
- **`WarrantyCardBuilder`**:
  - ESC/POS format: 58mm / 80mm thermal receipt commands.
    - Shop header, title "WARRANTY CERTIFICATE".
    - Document number, sale date, customer snapshot.
    - Product name (in receipt language), serial number, coverage dates.
    - Remedy, terms, exclusions.
    - CODE128 barcode of `warranty.code` via `choose_barcode`.
    - Stamp/signature box, CB POS footer.
    - Terminated by an ESC/POS cut command per unit.
    - Spooled to thermal printer via `PrintWorker.instance().add_job("print_commands", commands)`.
  - ReportLab PDF format: A5 / A4 document template.
    - Clean tabular card layout, crisp typography, Sinhala/Tamil text rasterization support.
    - CODE128 barcode drawing.
    - Generated off the Qt UI thread using `WarrantyCardPdfWorker(QThread)` or background runner.
- **Settings & Frictionless Checkout Flow**:
  - Settings: `show_warranty_on_receipt` (default `True`), `warranty_card_mode` (`OFF`, `ASK`, `ALWAYS`; default `ASK`).
  - In `SalesView._finalize_sale`:
    - If `warranty_card_mode == "ALWAYS"`: Spools thermal warranty cards immediately via `PrintWorker`.
    - If `warranty_card_mode == "ASK"`:
      - If `show_receipt_dialog` is `True`: `ReceiptOptionsDialog` shows "Print Warranty Card(s)" button.
      - If `show_receipt_dialog` is `False`: Prompts cashier with `QMessageBox.question(_t("warranty.prompt_print_cards"))`.
- **Reprint Flow**:
  - `ReceiptReprintService.reprint_warranty_cards(sale_id, user_id)`:
    - Requires `Permissions.SALES_REPRINT` or `Permissions.WARRANTY_VIEW`.
    - Writes `AuditLog(action="REPRINT_WARRANTY_CARD", event_type=WARRANTY_EVENT)`.
    - Respects void/cancelled status (`[VOID]` / `[CANCELLED]`).

---

## 4. Legal Gate Compliance (CAA Act No. 9 of 2003)

- **Statutory Rights Sentence**: Unresolved legal wording gate.
  - No fixed statutory rights sentence will be hard-coded, translated, or rendered.
  - No `show_statutory_rights_note` setting will be created in this batch.
  - Only owner-configured terms and exclusions snapshotted on the policy/warranty will be printed.

---

## 5. Test Strategy

1. **Domain Tests (`tests/domain/test_serial_capture.py`)**:
   - `test_cart_serial_slots_allocation`: Adding 3 units creates 3 slots.
   - `test_cart_serial_normalization`: Trims whitespace, uppercases, normalizes empty to `None`.
   - `test_cart_duplicate_prevention`: Duplicate serial in same line or across lines rejected.
   - `test_cart_merge_preserves_serials`: Re-adding same product preserves existing serials and allocates new slots.
   - `test_cart_quantity_reduction_trims_serials`: Reducing quantity slices from end.
   - `test_cart_would_discard_serials_query`: Identifies non-empty serials at risk of truncation.
   - `test_suspended_bill_serial_persistence`: Holding and recalling cart preserves serials; backward-compatible with v1.
   - `test_service_layer_required_serial_guard`: `TransactionService._execute_sale` raises `ValueError` if required serials are missing.
   - `test_policy_coupling_guard`: `InventoryService` rejects `serial_mode != OFF` when product has no policy.
   - `test_imei_luhn_validator`: Validates 15-digit IMEI check digit calculation, ignores non-15/alphanumeric strings.
   - `test_active_warranty_serial_lookup`: Returns prior receipt number for active serial.
2. **Printing Tests (`tests/domain/test_warranty_printing.py`)**:
   - `test_sales_receipt_builder_golden_unchanged`: Non-warranty sale receipt is byte-for-byte identical.
   - `test_sales_receipt_builder_warranty_lines_and_terms`: Renders coverage, S/N, and deduplicated terms.
   - `test_sales_receipt_builder_merged_items_serials`: Multiple serials rendered on merged line via `ItemDisplay.warranties`.
   - `test_reprint_void_cancelled_status_tag`: Reprint displays `[VOID]` or `[CANCELLED]`.
   - `test_invoice_pdf_warranty_subrow_and_terms`: Invoice PDF includes warranty info and terms section.
   - `test_warranty_card_builder_escpos_and_pdf`: Smoke tests ESC/POS commands and ReportLab PDF generation (>0 bytes) in EN, SI, TA.
   - `test_reprint_warranty_card_audit`: Reprints generate `REPRINT_WARRANTY_CARD` audit row.
3. **UI Tests (`tests/ui/test_serial_entry_dialog.py`)**:
   - `test_dialog_scan_advances_focus`: Enter advances from unit 1 to unit 2.
   - `test_dialog_process_barcode_external`: Hardware scan event populates field and advances.
   - `test_dialog_required_vs_optional_modes`: Required mode has no Skip; Optional mode allows Skip and Alt+C Cancel.
   - `test_dialog_cart_duplicate_error`: Displays error on duplicate.
   - `test_dialog_active_warranty_warning`: Shows non-blocking warning with receipt number.

---

## 6. Implementation Steps

1. **Commit 1: Implement #823 (`feat(warranty): capture serials at checkout (#823)`)**:
   - Implement `validate_imei_luhn` in `cbpos/core/utils/validators.py`.
   - Add `WarrantyService.find_active_warranties_by_serials` in `cbpos/core/services/warranty_service.py`.
   - Update `CartService` with serial slots, normalization, duplicate prevention, and `would_discard_serials`.
   - Update `SuspendedTransactionService` to hold and recall serials.
   - Build `SerialEntryDialog` with `accepts_scans = True` and `process_barcode_external` in `cbpos/ui/dialogs/serial_entry_dialog.py`.
   - Hook Product Editor Warranty tab `serial_mode_combo` with policy coupling guard and `InventoryService` audit/validation.
   - Wire `SalesView` add-to-cart prompts, quantity reduction confirmation, `_t("cart.context_edit_serials")` context menu, and checkout / quick cash gates.
   - Update `TransactionService._execute_sale` and `WarrantyService.register_for_sale_in_session` for serial assignment.
   - Translations: Add `serial_entry.*`, `product_editor.serial_mode_*`, `errors.serial_*` to `en.json`, `si.json`, `ta.json`.
   - Add regression tests in `tests/domain/test_serial_capture.py` and `tests/ui/test_serial_entry_dialog.py`.
   - Run tests, pre-commit, commit and push immediately: `feat(warranty): capture serials at checkout (#823)`.
2. **Commit 2: Implement #824 (`feat(warranty): print warranty details and cards (#824)`)**:
   - Update `ConfigService` with `show_warranty_on_receipt` and `warranty_card_mode`.
   - Extend `ItemDisplay` with `warranties` slot and update `SalesReceiptBuilder` for warranty lines, merged item serials, and deduplicated terms.
   - Extend `InvoiceService` and `TaxInvoicePdfBuilder` for warranty sub-rows and terms.
   - Eager-load `Sale.warranties` in `TaxInvoiceService.issue_artifact()`.
   - Implement `WarrantyCardBuilder` for ESC/POS (via `PrintWorker`) and ReportLab PDF (off UI thread).
   - Wire `ReceiptOptionsDialog` and `SalesView._finalize_sale` for warranty cards (supporting frictionless checkout).
   - Add `reprint_warranty_cards` to `ReceiptReprintService` with `REPRINT_WARRANTY_CARD` audit logging.
   - Translations: Add `receipt.warranty_*`, `invoice.warranty_*`, `warranty_card.*` in `en.json`, `si.json`, `ta.json`.
   - Add regression tests in `tests/domain/test_warranty_printing.py`.
   - Run tests, pre-commit, commit and push immediately: `feat(warranty): print warranty details and cards (#824)`.
