# Sri Lankan Tax Invoice Requirements (2026 Mandate)

**Author:** CB POS Remediation Team  
**Date:** 2026-11-12  
**Scope:** Statutory & Regulatory Requirements for Sri Lankan VAT Tax Invoices (Issue #814 / Batch 8.2)

---

## 1. Primary Sources & Authorities

All legal and regulatory findings in this document are derived directly from primary statutory sources and official notifications published by the Government of Sri Lanka and the Inland Revenue Department (IRD):

1. **Value Added Tax Act, No. 14 of 2002** (as amended):
   - **Section 20**: Tax Invoices (issuance, mandatory particulars, time limits, retention, copy markings, retail exemptions).
     - *Source*: Government Publication Bureau / Parliament of Sri Lanka.  
     - *URL*: `http://documents.gov.lk/files/act/2002/14/14-2002_E.pdf` (Acts of Sri Lanka 2002, Act No. 14, pp. 24–27).
   - **Section 25**: Credit and Debit Notes (tax adjustments, returns, cancellations, over/undercharge adjustments).
     - *Source*: Act No. 14 of 2002, pp. 31–33.
   - **Section 20(6)(a)**: Retail invoices / receipts to unregistered persons (only total including tax required; explicitly not a tax invoice).
     - *Source*: Act No. 14 of 2002, p. 26.

2. **Gazette Extraordinary No. 2463/05 (2025-11-17)**:
   - Notification issued by Commissioner General of Inland Revenue under Section 20 of VAT Act No. 14 of 2002 prescribing initial standard tax invoice specifications (effective 2026-01-01; later superseded).
     - *Source*: Department of Government Printing (`documents.gov.lk`).
     - *URL*: `http://documents.gov.lk/files/egz/2025/11/2463-05_E.pdf` (pp. 1A–3A).

3. **Gazette Extraordinary No. 2481/22 (2026-03-27)**:
   - Notification issued by Commissioner General of Inland Revenue under Section 20 of VAT Act No. 14 of 2002 specifying the revised, mandatory Tax Invoice format, layout schedule, and `YYMMM_QQQQ_XXXXX` serial number specifications. Rescinded and replaced Gazette 2463/05; originally set for 2026-07-01.
     - *Source*: Department of Government Printing (`documents.gov.lk`).
     - *URL*: `http://documents.gov.lk/files/egz/2026/03/2481-22_E.pdf` (pp. 1A–4A).

4. **Gazette Extraordinary No. 2500/106 (2026-08-06)**:
   - Notification amending Gazette Extraordinary No. 2481/22, formally postponing the effective date of the revised tax invoice format to **October 1, 2026**.
     - *Source*: Department of Government Printing (`documents.gov.lk`).
     - *URL*: `http://documents.gov.lk/files/egz/2026/08/2500-106_E.pdf` (p. 1A).

5. **Inland Revenue Department Circular No. SEC/2026/E/03 (2026-05-20)**:
   - Technical guidelines issued to all VAT-registered persons explaining the implementation of Gazette 2481/22 specifications, field layout, RAMIS integration, and serial number rules.
     - *Source*: Inland Revenue Department (`ird.gov.lk`).
     - *URL*: `http://www.ird.gov.lk/en/publications/Circulars/SEC_2026_E_03.pdf` (pp. 1–5).

---

## 2. Requirement Analysis & Statutory Mapping

### 2.1 Effective Date
- **Statutory Source**: Gazette Extraordinary No. 2500/106 (2026-08-06, p. 1A), amending Gazette Extraordinary No. 2481/22 (2026-03-27, p. 1A).
- **Rule**: The revised tax invoice format is **mandatory effective October 1, 2026** for all registered persons making taxable supplies in Sri Lanka.
- **CB POS Application**: System must generate compliant invoices for all taxable transactions issued on or after 2026-10-01.

---

### 2.2 Serial Number Format (`YYMMM_QQQQ_XXXXX`)
- **Statutory Source**: Gazette Extraordinary No. 2481/22 (Schedule, Item 2, p. 2A) & IRD Circular SEC/2026/E/03 (Section 3.2, p. 2).
- **Format Specification**:
  ```
  YYMMM_QQQQ_XXXXX
  ```
  - **`YY`**: Exactly 2 digits representing the last two digits of the calendar year of issue (e.g., `26` for 2026).
  - **`MMM`**: Exactly 3 uppercase English letters representing the calendar month of issue:  
    `JAN`, `FEB`, `MAR`, `APR`, `MAY`, `JUN`, `JUL`, `AUG`, `SEP`, `OCT`, `NOV`, `DEC`.
  - **`_`**: First underscore delimiter (ASCII 0x5F).
  - **`QQQQ`**: Alphanumeric identifier between 1 and 15 characters (`^[A-Za-z0-9]{1,15}$`) representing the organizational entity, branch code, division, department, or terminal counter.
  - **`_`**: Second underscore delimiter (ASCII 0x5F).
  - **`XXXXX`**: Sequential numeric serial number consisting **strictly of digits** (`^[0-9]+$`), typically zero-padded to 5 digits (e.g., `00001`, `00002`). Letters and symbols are prohibited.
- **Constraints**:
  - Maximum total length: **≤ 40 characters** (VAT Act s.20(2)(b) and Gazette 2481/22 Schedule Item 2).
  - **No whitespace**: Space characters are strictly forbidden anywhere in the serial.
- **Sequence Continuity & Reset Rules**:
  - Under IRD Circular SEC/2026/E/03 (p. 3), the serial number `XXXXX` may either:
    1. Run continuously across periods without resetting, or
    2. Reset to `00001` periodically (monthly or annually).
  - **CB POS Decision**: In CB POS, to maintain strict monotonic uniqueness and prevent duplicate serials within any given year/month/branch combination, `XXXXX` is an auto-incrementing integer sequence formatted as zero-padded 5 digits (expanding as needed up to 10 digits without exceeding the 40-char limit). Resetting monthly per `YYMMM` prefix or maintaining global monotonic numbering is safe.
- **Multi-Terminal / LAN-Sync Consideration**:
  - `QQQQ` explicitly permits a terminal or branch component (e.g. `MAIN`, `POS1`).
  - However, per RELEASE_PLAN.md Part 0 and the #814 specification:
    To avoid offline synchronization collisions across distributed tills that might assign duplicate numbers while partitioned, **Tax Invoices may only be issued from the designated Main PC or standalone machine** in CB POS. Tills running in network mode display an informative translated message explaining that official tax invoices must be issued from the Main PC.

---

### 2.3 Document Title and Prominence
- **Statutory Source**: VAT Act No. 14 of 2002 Section 20(2)(h) (p. 25) & Gazette Extraordinary No. 2481/22 (Schedule, Item 1, p. 2A).
- **Rule**: The words **"TAX INVOICE"** must be prominently displayed at the top of the document in bold, highlighted, uppercase text.
- **Separation from Ordinary Receipts**:
  - Section 20(6)(a) of the VAT Act explicitly provides that a retail invoice/receipt issued to an unregistered customer contains only the VAT-inclusive total and **is not a tax invoice**.
  - Ordinary thermal till receipts and ordinary proforma/commercial invoices must **never** bear the title "TAX INVOICE".

---

### 2.4 Original vs. Copy Marking ("copy only")
- **Statutory Source**: VAT Act No. 14 of 2002 Section 20(1), 20(4), and 20(5) (pp. 24–25).
- **Statutory Text of Section 20(5)**:
  > *"Where a registered person who is entitled to a tax invoice claims to have lost the original tax invoice, the person who makes the supply may issue to such registered person a copy clearly marked 'copy only'."*
- **Marking Rules**:
  1. The initial issuance/print of the tax invoice must be marked **"ORIGINAL"**.
  2. Any subsequent print, reprint, or duplicate issuance must be prominently marked **"COPY ONLY"** (the exact statutory phrase required by Section 20(5)).
  3. The system must record `print_count` and the initial issuance timestamp. If a print job is successfully processed, `print_count` is incremented. Any generation or print with `print_count >= 1` must display **"COPY ONLY"** instead of **"ORIGINAL"**.

---

### 2.5 Mandatory Particulars (Seller & Buyer)
- **Statutory Source**: VAT Act No. 14 of 2002 Section 20(2) (pp. 24–25) & Gazette Extraordinary No. 2481/22 (Schedule, pp. 2A–3A).
- **Mandatory Elements**:
  1. **Supplier Particulars (Top-Left)**:
     - Supplier Registered Business Name (matching VAT Registration Certificate).
     - Supplier Registered Business Address.
     - Supplier 9-digit Taxpayer Identification Number (**TIN**).
     - Supplier Telephone Number / Contact Details.
  2. **Buyer Particulars (Top-Right or Directly Below Supplier)**:
     - Buyer Registered Name / Entity Name.
     - Buyer Address.
     - Buyer 9-digit **TIN** (mandatory if registered under VAT).
  3. **Dates**:
     - **Invoice Date (Date of Issue)**: Formatted as standard date (e.g. `YYYY-MM-DD` / `MM/DD/YYYY`).
     - **Date of Supply**: The date on which the taxable supply was actually provided.
  4. **Line-Item Particulars**:
     - Item Number / Sequence Number.
     - Description of Goods or Services supplied (generic terms like "misc" are invalid).
     - Quantity or volume supplied.
     - Unit Price / Value of supply excluding VAT.
     - VAT charged (18%).
     - Total consideration (Gross amount including VAT).
  5. **Summary Totals**:
     - Total Net Value of Supply (excluding VAT).
     - Total VAT Amount charged.
     - Total Consideration (Net + VAT) in Sri Lankan Rupees (LKR) to 2 decimal places.
  6. **Payment Mode**:
     - Settlement method (Cash, Bank Transfer, Card, Credit, etc.).

---

### 2.6 Total Consideration in Words
- **Statutory Source**: Gazette Extraordinary No. 2481/22 (Schedule, Item 8, p. 3A) & IRD Circular SEC/2026/E/03 (p. 4).
- **Rule**:
  - Expressing the total consideration in words is marked as **Optional** on the IRD Gazette template (*"The total consideration expressed in words (Optional)"*).
  - However, in standard Sri Lankan commercial accounting practice and under CB POS design decision D6, the total consideration in words is included on the tax invoice for audit clarity and fraud prevention.
  - When included, it expresses the total in Sri Lankan Rupees and Cents:
    e.g., `One Thousand Two Hundred Fifty Rupees and Fifty Cents Only` (or `... and Zero Cents Only` if whole rupees).
  - Language: English is standard on official Sri Lankan tax documents. Sinhala/Tamil transliterations are supported, but English legal amount words are accepted and legally valid nationwide.

---

### 2.7 Request and Issue Windows (14 Days / 28 Days)
- **Statutory Source**: VAT Act No. 14 of 2002 Section 20(1) (p. 24).
- **Statutory Rule**:
  - A registered buyer who is entitled to a tax invoice must request it in writing within **14 days** of the time of supply.
  - The supplier must issue the tax invoice **not later than 28 days** after the time of supply.
  - A registered supplier making a taxable supply to any Government institution, Provincial Council, Local Authority, or public corporation **must issue a tax invoice regardless of request or whether that body is registered**.
- **CB POS Application**:
  - At checkout, if the customer is VAT-registered, a tax invoice can be issued immediately (Day 0).
  - In Sale History, a tax invoice may be requested and issued for any completed, non-refunded sale within the **28-day statutory window**. If more than 28 days have elapsed since the sale date, issuance is blocked with a translated explanation ("Statutory 28-day window for issuing a tax invoice has expired").

---

### 2.8 Document Retention Period (5 Years)
- **Statutory Source**: VAT Act No. 14 of 2002 Section 20(4) (p. 25).
- **Statutory Rule**:
  > *"A registered person who issues a tax invoice shall maintain a duplicate copy thereof for a period of not less than five years from the date of issue of such invoice."*
- **CB POS Application**:
  - All issued `TaxInvoice` records, buyer/seller snapshots, and tax lines must be permanently retained in the database.
  - They are immutable and must not be purged, deleted, or altered by product renames, price edits, or customer modifications.

---

### 2.9 Refunds and Tax Credit Notes
- **Statutory Source**: VAT Act No. 14 of 2002 Section 25 (pp. 31–33).
- **Statutory Rule**:
  - Where a tax invoice has been issued and the supply is subsequently cancelled, goods returned, or the consideration reduced, the supplier cannot simply void or delete the tax invoice.
  - The supplier must issue a **Tax Credit Note** adjusting the output tax liability and referencing:
    1. The original Tax Invoice serial number.
    2. The reason for the adjustment.
    3. The original value of supply and VAT charged.
    4. The adjusted/refunded value and VAT credit.
- **CB POS Application**:
  - A sale for which a `TaxInvoice` has already been issued cannot be voided.
  - If refunded (via RefundService), the refund document records a reference to the issued Tax Invoice serial, and a corresponding `TaxCreditNote` record captures the VAT adjustment.

---

### 2.10 Electronic / PDF Delivery
- **Statutory Source**: Electronic Transactions Act, No. 19 of 2006 (Sri Lanka) & IRD Circular SEC/2026/E/03 (Section 5, p. 5).
- **Rule**:
  - Tax invoices generated electronically (as tamper-evident structured PDF documents) and delivered via electronic means (email, customer portal) satisfy the legal delivery requirement, provided:
    1. The document contains all mandatory particulars specified under Section 20 and Gazette 2481/22.
    2. An exact electronic copy is maintained and retrievable for at least 5 years.
    3. The first issued electronic document is marked "ORIGINAL", and re-downloads/reprints are marked "COPY ONLY".

---

## 3. Summary of Compliance Decisions for CB POS (Batch 8.2)

| Requirement | Statutory Ref | Implementation in CB POS |
|---|---|---|
| Document Type | VAT Act s.20(1) | Dedicated `TaxInvoice` model linked 1:1 to `Sale`. Separate from ordinary receipts. |
| Title | s.20(2)(h), Gaz. 2481/22 | Prominent **"TAX INVOICE"** header on A4 PDF. Never on retail receipts. |
| Serial Number | Gaz. 2481/22, Gaz. 2500/106 | `YYMMM_QQQQ_XXXXX` (e.g. `26OCT_MAIN_00001`), ≤40 chars, no spaces, transactional generator. |
| Issue Terminal | D2, Phase 8 Spec | Standalone or Main PC only in network mode; tills disabled with explanation. |
| Marking | s.20(5) | First issue/print: **"ORIGINAL"**; any subsequent reprint: **"COPY ONLY"**. |
| Seller/Buyer TIN | s.20(2), Gaz. 2481/22 | Validated 9-digit TINs, snapshotted immutably on `tax_invoices`. |
| Consideration in Words | Gaz. 2481/22 (Optional) | `amount_to_words(total, lang)` with Rupees and Cents included. |
| Eligibility Window | s.20(1) | Permitted at checkout or within 28 days of sale date in Sale History. |
| Retention | s.20(4) | Immutable DB records and snapshot lines retained permanently (≥ 5 years). |
| Credit Notes | s.25 | Tax credit note references original tax invoice serial upon refund. |

