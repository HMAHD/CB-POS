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

-- Note: serial and sale_id have UNIQUE constraints; no redundant CREATE INDEX needed.

-- 2. tax_invoice_lines
CREATE TABLE tax_invoice_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_invoice_id INTEGER NOT NULL REFERENCES tax_invoices(id) ON DELETE RESTRICT,
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

CREATE INDEX ix_tax_invoice_lines_tax_invoice_id ON tax_invoice_lines(tax_invoice_id);

-- 3. tax_invoice_sequences
CREATE TABLE tax_invoice_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prefix VARCHAR(30) NOT NULL UNIQUE,
    last_seq INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Note: prefix has UNIQUE constraint; no redundant CREATE INDEX needed.

-- 4. tax_credit_notes
CREATE TABLE tax_credit_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_invoice_id INTEGER NOT NULL REFERENCES tax_invoices(id) ON DELETE RESTRICT,
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

-- Note: serial and refund_sale_id have UNIQUE constraints.
CREATE INDEX ix_tax_credit_notes_tax_invoice_id ON tax_credit_notes(tax_invoice_id);
```

### 3.2 SQLAlchemy Models
Add classes `TaxInvoice`, `TaxInvoiceLine`, `TaxInvoiceSequence`, and `TaxCreditNote` in `cbpos/core/models/tax_invoice.py` and re-export in `cbpos/core/models/__init__.py`.

---

## 4. Statutory Serial Number Generation (`YYMMM_QQQQ_XXXXX` and `CN_{YYMMM}_{QQQQ}_{XXXXX}`)

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
  - **Sequence Width & Overflow**: Zero-padded minimum 5 digits (`f"{next_seq:05d}"`). If numbers exceed 99,999 in a single monthly sequence, digits expand monotonically without wrapping around.
  - **Statutory Length Guarantee**: Total serial length is strictly validated `len(serial) <= 40`. If 40 characters is exceeded, system fails closed with `OverflowError`.
- **Credit Note Serial Format**:
  - `CN_{YYMMM}_{QQQQ}_{XXXXX}` (e.g. `CN_26NOV_MAIN_00001`), allocated atomically using dedicated sequence prefix `CN_{YYMMM}_{QQQQ}`. Total length ≤ 30 characters, guaranteeing no truncation.

### 4.2 Atomic Sequence Allocation
To ensure gapless monotonicity and cross-engine safety (PostgreSQL and SQLite):
1. Compute prefix: `{YY}{MMM}_{QQQQ}` (or `CN_{YYMMM}_{QQQQ}` for credit notes).
2. Dialect validation: Check `session.bind.dialect.name`. If unbound (`session.bind is None`), raise `RuntimeError("Unbound session cannot allocate sequences")`.
3. In PostgreSQL:
   Row-level lock on the sequence record via `SELECT last_seq FROM tax_invoice_sequences WHERE prefix = :prefix FOR UPDATE` (or atomic upsert `INSERT ... ON CONFLICT (prefix) DO UPDATE SET last_seq = tax_invoice_sequences.last_seq + 1 RETURNING last_seq;`).
4. In SQLite:
   Execute sequence update using a nested transaction (SAVEPOINT) or engine-level write lock (`BEGIN IMMEDIATE` transaction) without rolling back outer caller-owned transactions on transient conflict.

---

## 5. Eligibility Rules & Lifecycle Guards

Before issuing a `TaxInvoice`, `TaxInvoiceService.validate_eligibility(sale_id, session)` checks:
1. **Shop VAT Registration**: `TaxService.is_vat_active()` must be True, and canonical supplier TIN must be configured.
   - **Canonical Supplier TIN Resolver**: Look up `company_tax_id` and legacy `vat_number`/`tax_tin`. If both are populated with conflicting values, fail closed with an actionable error.
2. **Terminal Authority**: `ConfigService.get("terminal_mode")` must be `"standalone"` or `"main"`. If `"terminal"`, reject with error: `"tax_invoice.network_mode_restriction"`.
3. **Sale Status**: Sale must be `COMPLETED` and not a refund (`sale.payment_method != "REFUND"` and `sale.refund_of_sale_id is None` and `sale.status != "VOID"`).
4. **Issue Window (28 Days)**:
   - Sale date must not be None (`if sale.date is None: raise ValueError("sale_date_missing")`).
   - Comparison normalizes naive and aware datetimes to UTC before evaluating the 28-day window (`sale.date >= now - timedelta(days=28)`).
5. **Buyer Particulars**: Buyer TIN is strictly mandatory and must match `^\d{9}$`. Buyer Name and Address must not be blank.
6. **No Pre-existing Invoice**: If `TaxInvoice` already exists for this `sale_id`, return existing invoice (idempotent, locking the Sale row first).

### 5.1 Lock Order & Void Guard
To prevent concurrency race conditions between invoice issuance and voiding:
- Both `TaxInvoiceService.issue_tax_invoice` and `TransactionService.void_sale` acquire a lock on the `Sale` row first (`session.query(Sale).filter(Sale.id == sale_id).with_for_update().first()`).
- In `TransactionService.void_sale`:
  ```python
  has_tax_invoice = session.query(TaxInvoice.id).filter_by(sale_id=sale_id).first() is not None
  if has_tax_invoice:
      raise ValueError("cannot_void_tax_invoice_sale")
  ```
- Because both paths lock the same `Sale` record in the same order, exactly one operation can proceed: either the sale is voided, or the tax invoice is issued, never both.

### 5.2 Tax Math & Snapshot Reconciliation
Prices in CB POS are VAT-inclusive MRP. Tax-line calculation uses backward VAT extraction per D4/D25:
- For each item in `sale.items`:
  - `line_total = item.total` (VAT-inclusive MRP after line/bill discounts).
  - If taxable:
    `line_vat = line_total - round_money(line_total / (1 + vat_rate / 100))`
    `line_net = line_total - line_vat`
  - If exempt (rate == 0):
    `line_vat = Decimal("0.00")`
    `line_net = line_total`
- Reconcile line totals against stored sale facts:
  - `sum(line_net) + sum(line_vat) == sale.total_amount`.
  - Discrepancies due to fractional cents reconcile onto the largest taxable line item.
  - Inconsistency (e.g. sale has positive `tax_vat` but zero taxable line items) fails closed.
  - SSCL is strictly excluded from customer tax invoices (tracked in liability reporting only per D25).

---

## 6. Deep Artifact-Issuance Module

### 6.1 Unified Artifact Interface (`issue_artifact`)
Replace fragmented UI print/reload/render calls with a single deep interface:
```python
def issue_artifact(
    invoice_id: int,
    destination_path: Path,
    user_id: int,
    channel: str = "print",  # "print" or "pdf"
) -> TaxInvoiceArtifactResult: ...
```
Behind this interface, the module hides:
1. **Concurrency Lock / Reservation**: Locks the invoice row.
2. **Original vs. Copy Decision**:
   - First successful issuance / delivery (print or PDF export) is marked `"ORIGINAL"`.
   - Subsequent issuances are marked `"COPY ONLY"`.
3. **Safe Rendering**: Generates ReportLab PDF to a temporary file.
4. **Atomic Write**: Uses `os.replace` to write to the destination path.
5. **State Finalization**: Only upon successful filesystem write, increments `print_count` and updates `original_printed_at` if `print_count == 1`.
6. **Audit Trail**: Writes `AuditLog` inside the same database transaction.
7. **Failure Recovery**: If rendering, write, or DB commit fails, temporary files are cleaned up, `print_count` is NOT consumed, and the transaction rolls back cleanly.

### 6.2 ReportLab PDF Formatting & Text Normalization
- `_text(val)`: None is blank; numeric 0 is `'0'`; text is XML-escaped; newlines become `<br/>` for Paragraphs and line breaks for raster rendering.
- Supplier header: Left-aligned title style matching layout hierarchy.
- Absent optional fields (phone, buyer phone) omitted cleanly without rendering Python `'None'`.
- Mixed VAT rates: Generates per-rate breakdown dynamically from line snapshots instead of hardcoded 18%.
- Localization: PDF labels translated via `translate_in(invoice.issue_language, key)`. Prominent header "TAX INVOICE" is preserved in English per statutory mandate.
- Qt thread offloading: PDF generation and file I/O execute in a background thread via `start_background_job`, preventing UI freezes.

### 6.3 Trilingual Amount in Words
`cbpos/core/utils/amount_to_words.py`:
- Converts amounts to words in English (`en`), Sinhala (`si`), and Tamil (`ta`).
- Retains Rupees and Cents ending with "Only" across all three languages.
- Fails closed (`ValueError`) on unsupported language codes.

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
