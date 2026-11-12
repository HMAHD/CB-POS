# Technical Design: Sri Lankan Tax Invoice Compliance (#814)

**Phase:** 8 · **Batch:** 8.2  
**Owner:** CB POS Remediation Team  
**Date:** 2026-11-12  
**Status:** APPROVED (Post-EGM / Goldfish Review Updates Applied)

---

## 1. Context & Objectives

Sri Lanka's Inland Revenue Department (IRD) mandates that VAT-registered businesses issuing tax invoices must comply with Section 20 of the Value Added Tax Act, No. 14 of 2002, Gazette Extraordinary No. 2481/22 (as amended by Gazette 2500/106, effective October 1, 2026), and IRD Circular SEC/2026/E/03.

Currently, CB POS:
1. Conflates ordinary commercial/retail A4 invoices with tax invoices via `InvoiceService._shows_vat`.
2. Employs ordinary document serials (`INV-{Y}-{seq:05d}`) rather than the mandated `YYMMM_QQQQ_XXXXX` serial structure.
3. Does not record or enforce the statutory `ORIGINAL` vs `COPY ONLY` copy marking.
4. Lacks immutable snapshots of buyer/seller particulars and line-item tax facts, exposing historical reprints to retroactive mutations if products, tax rates, or shop settings change.
5. Allows voiding of sales even after official documents have been issued, violating VAT Act Section 25.

**Core Goal:** Implement dedicated, immutable, transactionally safe, and fully compliant `TaxInvoice` generation and PDF issuance in CB POS while preserving ordinary retail receipts and commercial invoices as separate document types.

---

## 2. Architecture & Domain Responsibilities

### 2.1 Layer Separation
Following the 10 Non-Negotiable Rules of CB POS (Part 0 §0.2):
- **UI (`cbpos/ui/**`)**: Gathers buyer details, displays eligibility status, triggers issuance, and displays/previews PDFs. UI never touches the database, never generates serial numbers, and never performs tax math.
- **Service (`TaxInvoiceService`)**: Single owner of tax invoice eligibility, permission checks, serial allocation, snapshotting, idempotency, audit logging, and persistence.
- **Transaction Engine (`TransactionService`)**: Integrates atomic checkout issuance so `Sale` and `TaxInvoice` are committed in the same database transaction. Enforces void prevention on sales with issued tax invoices.
- **Refund Engine (`RefundService`)**: Records `TaxCreditNote` when refunding sales with issued tax invoices.
- **Worker / Background Layer (`TaxInvoicePrintWorker`)**: Handles ReportLab PDF generation and printing off the Qt UI thread, reporting results asynchronously via job IDs.

### 2.2 Permissions
- Add permission code: `sales.tax_invoice` ("Issue and print official VAT Tax Invoices").
- Seeded to: `Admin` and `Manager` default roles.
- Enforced at both:
  1. Service boundary: `TaxInvoiceService.issue_tax_invoice(...)` calls `check_permission_with_override("sales.tax_invoice", user_id)`.
  2. UI boundary: Buttons and menu actions are enabled/disabled/hidden based on `has_permission("sales.tax_invoice")`.

---

## 3. Data Model & Alembic Migration

### 3.1 Schema Design
Create new models in `cbpos/core/models/tax_invoice.py` and write a reversible Alembic migration (`alembic/versions/xxxx_add_tax_invoices.py`):

```sql
-- 1. tax_invoices
CREATE TABLE tax_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL UNIQUE REFERENCES sales(id),
    serial VARCHAR(40) NOT NULL UNIQUE,
    issued_at TIMESTAMP NOT NULL,
    supply_date DATE NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    issued_by_user_id INTEGER NOT NULL REFERENCES users(id),
    
    -- Immutable Supplier Snapshots
    supplier_name VARCHAR(255) NOT NULL,
    supplier_address TEXT NOT NULL,
    supplier_phone VARCHAR(50) NOT NULL,
    supplier_tin VARCHAR(20) NOT NULL,
    
    -- Immutable Buyer Snapshots
    buyer_name VARCHAR(255) NOT NULL,
    buyer_address TEXT NOT NULL,
    buyer_phone VARCHAR(50),
    buyer_tin VARCHAR(20) NOT NULL,
    
    -- Document State & Metadata
    issue_language VARCHAR(5) NOT NULL DEFAULT 'en',
    print_count INTEGER NOT NULL DEFAULT 0,
    original_printed_at TIMESTAMP,
    
    -- Monetary & Tax Reconciliation (Decimal, 2 decimal places)
    subtotal_amount NUMERIC(12, 2) NOT NULL,
    discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    net_amount NUMERIC(12, 2) NOT NULL,
    tax_vat NUMERIC(12, 2) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    amount_in_words TEXT NOT NULL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_tax_invoices_serial ON tax_invoices(serial);
CREATE INDEX ix_tax_invoices_sale_id ON tax_invoices(sale_id);

-- 2. tax_invoice_lines
CREATE TABLE tax_invoice_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_invoice_id INTEGER NOT NULL REFERENCES tax_invoices(id) ON DELETE CASCADE,
    item_number INTEGER NOT NULL,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    item_code_snapshot VARCHAR(50),
    product_name_snapshot VARCHAR(255) NOT NULL,
    unit_snapshot VARCHAR(20) NOT NULL DEFAULT 'pcs',
    quantity NUMERIC(10, 3) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    net_amount NUMERIC(12, 2) NOT NULL,
    vat_rate NUMERIC(5, 2) NOT NULL,
    vat_amount NUMERIC(12, 2) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
);

CREATE INDEX ix_tax_invoice_lines_invoice_id ON tax_invoice_lines(tax_invoice_id);

-- 3. tax_invoice_sequences
CREATE TABLE tax_invoice_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prefix VARCHAR(30) NOT NULL UNIQUE,
    last_seq INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_tax_invoice_sequences_prefix ON tax_invoice_sequences(prefix);

-- 4. tax_credit_notes
CREATE TABLE tax_credit_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_invoice_id INTEGER NOT NULL REFERENCES tax_invoices(id),
    refund_sale_id INTEGER NOT NULL UNIQUE REFERENCES sales(id),
    serial VARCHAR(40) NOT NULL UNIQUE,
    issued_at TIMESTAMP NOT NULL,
    issued_by_user_id INTEGER NOT NULL REFERENCES users(id),
    reason TEXT NOT NULL,
    net_amount NUMERIC(12, 2) NOT NULL,
    tax_vat NUMERIC(12, 2) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    amount_in_words TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_tax_credit_notes_serial ON tax_credit_notes(serial);
CREATE INDEX ix_tax_credit_notes_tax_invoice_id ON tax_credit_notes(tax_invoice_id);
```

### 3.2 SQLAlchemy Models
Add classes `TaxInvoice`, `TaxInvoiceLine`, `TaxInvoiceSequence`, and `TaxCreditNote` in `cbpos/core/models/tax_invoice.py` and re-export in `cbpos/core/models/__init__.py`.

---

## 4. Statutory Serial Number Generation (`YYMMM_QQQQ_XXXXX`)

### 4.1 Format Specification
Gazette 2481/22 and 2500/106 mandate:
- `YY`: 2-digit year (e.g. `26` for 2026).
- `MMM`: 3-letter English uppercase month code. Crucial: Do NOT use `strftime("%b")` which is locale-dependent. Use explicit mapping:
  ```python
  MONTH_CODES = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
  mmm = MONTH_CODES[now.month - 1]
  ```
- `_`: Mandatory underscore separator.
- `QQQQ`: Alphanumeric branch/terminal code (1 to 15 characters, no spaces, uppercase). Derived from sanitized `ConfigService.get("terminal_id")` or `"MAIN"`. In standalone or main PC mode, defaults to `"MAIN"`.
- `_`: Mandatory underscore separator.
- `XXXXX`: Monotonically incrementing 5-digit zero-padded numeric sequence (e.g. `00001`), resetting at the beginning of each calendar month.
- Total length: ≤ 40 characters (e.g. `26OCT_MAIN_00001` is 16 chars).

### 4.2 Atomic Sequence Allocation
To ensure gapless monotonicity and cross-engine safety (PostgreSQL and SQLite):
1. Compute prefix: `{YY}{MMM}_{QQQQ}`.
2. In PostgreSQL:
   ```sql
   INSERT INTO tax_invoice_sequences (prefix, last_seq) VALUES (:prefix, 0)
   ON CONFLICT (prefix) DO NOTHING;
   SELECT last_seq FROM tax_invoice_sequences WHERE prefix = :prefix FOR UPDATE;
   UPDATE tax_invoice_sequences SET last_seq = last_seq + 1 WHERE prefix = :prefix;
   ```
3. In SQLite:
   Use `session.execute` with `serializable=True` (or execute inside a transaction with retry loop on `IntegrityError` / `OperationalError("database is locked")`) to ensure atomic sequence incrementation.

---

## 5. Eligibility Rules & Lifecycle Guards

Before issuing a `TaxInvoice`, `TaxInvoiceService.validate_eligibility(sale_id, session)` checks:
1. **Shop VAT Registration**: `TaxService.is_vat_active()` must be True, and `ConfigService.get("company_tax_id")` (or `ConfigService.get("vat_number")`) must be set.
2. **Terminal Authority**: `ConfigService.get("terminal_mode")` must be `"standalone"` or `"main"`. If `"terminal"`, reject with error: `"tax_invoice.network_mode_restriction"`.
3. **Sale Status**: Sale must be `COMPLETED` and not a refund (`sale.payment_method != "REFUND"` and `sale.refund_of_sale_id is None` and `sale.status != "VOID"`).
4. **Issue Window (28 Days)**: `sale.date >= datetime.now() - timedelta(days=28)`. (Uses `sale.date`, NOT `created_at`).
5. **Buyer Particulars**: Buyer TIN must match `^\d{9}$`. Buyer Name and Address must not be blank.
6. **No Pre-existing Invoice**: If `TaxInvoice` already exists for this `sale_id`, return existing invoice (idempotent).

### 5.1 Void Guard in `TransactionService.void_sale`
Under VAT Act Section 25, a sale with an issued Tax Invoice cannot be voided; adjustments must go through an official credit note.
In `cbpos/core/services/transaction_service.py:void_sale`:
```python
has_tax_invoice = session.query(TaxInvoice.id).filter_by(sale_id=sale_id).first() is not None
if has_tax_invoice:
    raise ValueError("cannot_void_tax_invoice_sale")
```

### 5.2 Bill-Level Discount & Loyalty Proration
When snapshotting lines:
- For each item in `sale.items`, calculate line net amount after allocating whole-bill discounts and loyalty redemptions proportionally:
  `effective_line_net = item.subtotal * (1 - sale_discount / sale_subtotal)`.
- Line VAT is computed on `effective_line_net` (if item is taxable).
- Reconciliation: Any 1-cent rounding difference between `sum(lines.net)` and `sale.net_revenue` or `sum(lines.vat)` and `sale.tax_vat` is adjusted onto the final taxable line item, preserving exact tie-out.

---

## 6. Document Generation & Output Rules

### 6.1 Original vs. Copy Marking
- Statutory requirement (VAT Act s.20(5)):
  - First printed/delivered copy: prominent **"ORIGINAL"** header marking.
  - Any subsequent reprint/re-download: prominent **"COPY ONLY"** header marking.
- Lifecycle tracking:
  - `print_count` starts at `0`.
  - PDF generation uses `status = "ORIGINAL"` if `invoice.print_count == 0` else `"COPY ONLY"`.
  - Previewing on screen does not increment `print_count`.
  - When a physical print or exported PDF is generated, call `TaxInvoiceService.record_print(tax_invoice_id, user_id)`:
    - Atomically increments `print_count = print_count + 1`.
    - If `print_count == 1`, sets `original_printed_at = datetime.now()`.
    - Logs to `AuditLog` (`action="TAX_INVOICE_PRINT"`, details with serial and count).

### 6.2 Elimination of Commercial Invoice Conflation
In `cbpos/core/services/invoice_service.py`:
- In `generate_pdf`: Remove logic that sets `title = t("title_tax")` ("TAX INVOICE") when VAT is active.
- Standard commercial A4 invoices generated by `InvoiceService` must always be titled `INVOICE` or `COMMERCIAL INVOICE`.
- The prominent title **"TAX INVOICE"** is strictly reserved for `TaxInvoicePDFBuilder`.

### 6.3 Amount to Words with Rupees and Cents
In `cbpos/core/utils/amount_to_words.py`:
- Update `amount_to_words(amount: Decimal, language: str = "en") -> str`:
  - Split amount into whole rupees and cents (`00` to `99`).
  - Format: `f"{rupees_words} Rupees and {cents_words} Cents Only"` (or `f"{rupees_words} Rupees Only"` if cents == 0).

---

## 7. User Interface Workflows

### 7.1 Checkout Workflow (`PaymentDialog`)
- Add checkbox in `PaymentDialog`: `"Issue Tax Invoice"`.
- Disabled with tooltip if VAT is not active or machine is in till network mode.
- If checked:
  - If customer has a 9-digit TIN, pre-populate buyer details.
  - If customer is walk-in or TIN is missing, clicking "Issue Tax Invoice" opens `BuyerDetailsDialog` modal.
  - When payment is confirmed, pass `tax_invoice_details` into `TransactionService.process_sale`.
  - `TransactionService._execute_sale` atomically creates the `Sale` and calls `TaxInvoiceService._create_tax_invoice_in_session(session, sale, tax_invoice_details, user_id)`.
  - Prompt: "Tax Invoice [SERIAL] created. Print now?"

### 7.2 Sale History Workflow (`HistoryView`)
- For selected sale:
  - If `TaxInvoice` exists: Show button `"View / Print Tax Invoice"` (icon: document/print). Shows serial and print status.
  - If eligible and no `TaxInvoice` exists: Show button `"Issue Tax Invoice"`.
  - If ineligible (e.g. >28 days, voided, or refunded): Button disabled with explanatory tooltip.
- Clicking `"Issue Tax Invoice"` opens `BuyerDetailsDialog`. Upon validation, calls `TaxInvoiceService.issue_tax_invoice(...)`.

### 7.3 Buyer Details Dialog (`BuyerDetailsDialog`)
- Standard `FormDialog` with `make_dialog_footer`.
- Fields:
  - `Buyer Name` (Required, String).
  - `Buyer Address` (Required, Text).
  - `Buyer Phone` (Optional, String).
  - `Buyer Taxpayer Identification Number (TIN)` (Required, 9 digits `^\d{9}$`).
- Keyboard navigation: Enter submits, Esc cancels. Inline validation warnings for invalid TIN.

---

## 8. Verification Strategy & Test Matrix

1. **Unit & Domain Tests (`tests/domain/test_tax_invoice_service.py`)**:
   - Monotonic serial generation matching regex `^\d{2}[A-Z]{3}_[A-Z0-9]{1,15}_\d{5,}$`.
   - Invariant English month code regardless of OS locale.
   - Atomic upsert and concurrent sequence reservation safety.
   - 28-day window check on `sale.date`.
   - Void prevention on sales with issued tax invoices.
   - Proportional bill discount and loyalty redemption allocation with cent reconciliation.
   - Immutable snapshot verification.
2. **Amount in Words Tests (`tests/domain/test_amount_to_words.py`)**:
   - Verify rupees and cents formatting with "Only".
3. **PDF Generation Tests (`tests/domain/test_tax_invoice_pdf.py`)**:
   - `pypdf` extraction verifying prominent "TAX INVOICE".
   - "ORIGINAL" vs "COPY ONLY" based on print count.
   - Seller & Buyer 9-digit TINs, address, and amount in words.
   - Decoupled `InvoiceService` outputting "INVOICE", never "TAX INVOICE".
4. **Migration Tests (`tests/domain/test_tax_invoice_migration.py`)**:
   - Upgrade and downgrade on SQLite and PostgreSQL.
5. **UI & Integration Tests (`tests/ui/test_tax_invoice_ui.py`)**:
   - `BuyerDetailsDialog` validation and keyboard order.
   - `PaymentDialog` checkout integration.
   - `HistoryView` issue and reprint actions.
