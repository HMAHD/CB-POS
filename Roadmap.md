# CB POS: Roadmap — Free POS for Sri Lankan Retailers

**Status:** In Progress
**Architecture:** Python 3.12 | PyQt6 | MVC Pattern | SQLite
**Platform:** Windows (primary target)
**Target:** Sri Lankan small-to-medium shop owners — any type (grocery, pharmacy, hardware, clothing, etc.)
**Deployment:** Free software, self-install by clients (installer + setup wizard)
**Languages:** Sinhala, English, Tamil (full trilingual support)
**Business Model:** 100% free software (not open source). Grow reputation by solving real problems. All printed outputs (receipts, reports, invoices, PDFs) carry CB POS branding + website — free users become promoters.

> **Design Philosophy:** Most users are non-technical shop owners who learn through practice. The UI must be clean, intuitive, and forgiving. Every screen should be self-explanatory. No manuals needed for daily operations.

---

## Remaining Build Order (Ship to First Client)

1. **Phase 17 – Data Safety** — backup/restore (retailers WILL lose data without this)
2. **Phase 19 – Testing** — core unit + integration tests for confidence before shipping
3. **Phase 20 – Deployment** — installer + auto-update for self-install clients
4. **Phase 22 – Purchase & Stock** — GRN, stock take, complete inventory lifecycle
5. **Phase 26 – UI Polish** — keyboard shortcuts, sounds, loading spinners
6. **Phase 27 – Admin Tools** — logs, DB info for support/troubleshooting
7. **Phase 23 – Promotions** — remaining promo types (nice to have)
8. **Phase 9 – Tax Extras** — tax breakdown display, exempt sales (nice to have)
9. **Phase 18 – Multi-Terminal** — built, needs real-world testing (when a client needs it)
10. **Phase 30 – Simple Reports** — trends, margins (last priority)

---

## Completed Phases

### Phase 1: Project Initialization & Environment ✅
*Goal: Establish a sterile, reproducible development environment.*

- [x] **1.1 Directory Structure**
    - [x] Generate standard folders (`core`, `infrastructure`, `ui`, `tests`).
    - [x] Create `assets` folders (fonts, icons, sounds).
    - [x] Initialize `__init__.py` in all packages.
- [x] **1.2 Version Control & Config**
    - [x] Initialize Git repository.
    - [x] Create `.gitignore` (Python, PyCharm, VSCode specific).
    - [x] Create `config.py` using `pydantic-settings` for strongly typed env vars.
- [x] **1.3 Dependency Management**
    - [x] Create virtual environment (`.venv`).
    - [x] Generate `requirements.txt` with pinned versions (`PyQt6==6.7.0`, `SQLAlchemy==2.0.30`).
    - [x] Setup `pre-commit` hooks (Black, Flake8) for code quality.
- [x] **1.4 Documentation Structure**
    - [x] Create `docs/` folder with README.md
    - [x] Setup API documentation framework (Sphinx/MkDocs)
    - [x] Create developer onboarding guide

---

### Phase 2: Database Layer ✅
*Goal: Define the data structure ensuring integrity and speed.*

- [x] **2.1 ORM Setup (SQLAlchemy 2.0)**
    - [x] Implement Singleton Database Connection.
    - [x] Configure Connection Pooling (for high throughput).
    - [x] Create Base declarative model.
- [x] **2.2 Core Models**
    - [x] **Auth:** `User`, `Role`, `Permission`.
    - [x] **Inventory:** `Category`, `Product`, `ProductVariant`, `Unit`.
    - [x] **Sales:** `Sale`, `SaleItem`, `Payment`.
    - [x] **Audit:** `Log`, `Shift`, `CashMovement`.
- [x] **2.3 Migration Engine**
    - [x] Initialize **Alembic**.
    - [x] Create initial migration script.
    - [x] Create `scripts/seed.py` for SL Default Data.
- [x] **2.4 Extended Models**
    - [x] **Customer Extended:** Add loyalty_points, credit_limit, price_list_id
    - [x] **Supplier Model:** name, company, tax_number, contact info
    - [x] **PriceList:** Support multiple pricing tiers
    - [x] **PriceListItem:** Product-specific pricing per list
    - [x] **Promotion:** time-based, quantity-based discounts
    - [x] **StockMovement:** Complete audit trail with document references
    - [x] **Document:** Unified document system (Sales, Purchase, Proforma, Returns)
    - [x] **VoidReason:** Track void/cancellation reasons
- [x] **2.5 Advanced Relationships**
    - [x] Product-Supplier many-to-many relationship
    - [x] Customer-PriceList assignment
    - [x] Hierarchical ProductGroup (parent-child categories)
    - [x] Document-StockMovement linkage

---

### Phase 3: Authentication & Security ✅
*Goal: Protect the system from unauthorized access.*

- [x] **3.1 Security Logic**
    - [x] Implement SHA-256 PIN Hashing.
    - [x] Create `AuthService.login(pin)`.
    - [x] Create `SessionManager` (Singleton).
- [x] **3.2 RBAC (Role-Based Access Control)**
    - [x] Define Permissions (`CAN_VOID`, `CAN_REFUND`, `CAN_SEE_REPORTS`).
    - [x] Implement `check_permission` decorator for sensitive functions.
    - [x] **Access Level System (0-9):** Numeric hierarchy like Aronium
    - [x] **Operation-Level Permissions:** Granular control per feature
    - [x] **Permission Groups:** Sales, Management, Documents, Reports, Settings
- [x] **3.3 Login UI**
    - [x] Design Split-Screen Login (Brand Left / Numpad Right).
    - [x] Implement Masked PIN Input.
    - *(Manager Override popup moved to Phase 31)*
- [x] **3.4 Session Management**
    - [x] Auto-logout on inactivity (configurable timeout)
    - [x] Session activity logging
    - [x] Multi-user session tracking (for networked version)
    - [x] Password recovery mechanism (email-based)

---

### Phase 4: Advanced Inventory Management ✅
*Goal: Manage complex retail products.*

- [x] **4.1 Product Logic**
    - [x] Implement `ProductService`.
    - [x] Support **Weighted Items** (Boolean flag).
    - [x] Support **Composite Items** (Hampers).
- [x] **4.2 Inventory UI**
    - [x] Create Product Master Grid (Search, Filter, Sort).
    - [x] Create Product Editor Dialog.
    - [x] Implement CSV Import Wizard (`pandas` integration).
    - [x] **Product Image Upload:** Support product photos
    - [x] **Multiple Barcode Support:** Pipe-separated barcodes per product
    - [x] **Age Restriction Flag:** For controlled items
- [x] **4.3 Stock Control**
    - [x] Implement `StockAdjustment` (Damage/Expired/Correction).
    - [x] Create "Low Stock" logic and UI indicators.
- [x] **4.4 Advanced Stock Features**
    - [x] **Reorder Point System:** Auto-generate purchase suggestions
    - [x] **Preferred Quantity:** Target stock levels per product
    - [x] **Supplier Assignment:** Default supplier per product
    - [x] **Service Items:** Non-stock items (don't track inventory)
    - [x] **Stock History View:** Complete movement audit trail
    - [x] **Prevent Negative Inventory:** Optional blocking with override
    - [x] **Stock Valuation Report:** FIFO/LIFO/Weighted Average
- [x] **4.5 Category Management**
    - [x] Hierarchical category tree (unlimited depth)
    - [x] Full Category Manager dialog (tree view CRUD, add/edit/delete, subcategories)
    - [x] Category color coding with visual indicators
    - [x] Category-based discounts and promotions
    - [x] Visual category icons for touch interface
    - [x] Category-based reporting

---

### Phase 5: Hardware Abstraction Layer (HAL) ✅
*Goal: Write code once, run on any hardware.*

- [x] **5.1 Architecture**
    - [x] Define Interfaces: `IPrinter`, `IScanner`, `IDisplay`.
    - [x] **Cash Drawer Interface:** Standard kick commands
    - [x] **Weighing Scale Interface:** Serial communication protocol
    - [x] **Customer Display Interface:** Secondary screen support
- [x] **5.2 Printing (ESC/POS)**
    - [x] Implement `ThermalPrinter` driver using `python-escpos`.
    - [x] Support USB and Network printers.
    - [x] Implement "Image Print" mode for Sinhala/Tamil text fallback.
    - [x] **A4 Invoice Printing:** PDF generation with reportlab
    - [x] **Receipt Templates:** Customizable header/footer/logo
- [x] **5.3 Input Devices**
    - [x] Implement `BarcodeScanner` hook (differentiate typing vs scanning).
    - [x] Implement `CashDrawer` kick logic (RJ11 signal).
    - [x] **Weighing Scale Integration:** Barcode prefix detection
    - [x] **Scale Barcode Parser:** Extract weight from embedded barcodes
- [x] **5.4 Printer Configuration**
    - [x] Paper width settings (58mm/80mm/A4)
    - [x] Character set selection
    - [x] Print density and line spacing
    - [x] Auto-print on payment option
    - [x] Number of receipt copies

---

### Phase 6: The Sales Terminal (UI/UX) ✅
*Goal: A mouse-free interface for high-speed checkout.*

- [x] **6.1 Layout Engine**
    - [x] **Left Panel:** High-Contrast Cart Grid.
    - [x] **Right Panel:** Command Center (Numpad + Action Grid).
    - [x] **Top Bar:** Status Indicators (Printer, Network, User).
- [x] **6.2 Interaction Design**
    - [x] Implement **Focus Trap** (Cursor auto-return).
    - [x] Map Function Keys (`F1`-`F12`) to Actions.
    - *(Touch Visual Groups moved to Phase 31)*
- [x] **6.3 Visual Layout Mode**
    - [x] **Product Grid:** Large touchscreen-friendly buttons
    - [x] **Product Images:** Visual product representation
    - [x] **Category Navigation:** Quick category switching
    - [x] **Responsive Design:** Adapt to screen size
- [x] **6.4 Search & Filter**
    - [x] **Multi-Mode Search:** Barcode / SKU / Name toggle
    - [x] **Type-ahead Search:** Live filtering as you type
    - [x] **Advanced Search Dialog (F3):** Multi-field filtering
    - [x] **Quick Product Lookup:** Recent/favorite products
- [x] **6.5 Order Item Display**
    - [x] **Status Icons:** Added/Confirmed/Voided indicators
    - [x] **Line Item Actions:** Edit qty/price/discount per line
    - [x] **Item Notes:** Add special instructions
    - [x] **Item Colors:** Visual status differentiation

---

### Phase 7: Cart Logic & Math Engine ✅
*Goal: Precision calculation without floating point errors.*

- [x] **7.1 Cart Service**
    - [x] Implement `add_item`, `remove_item`, `update_qty`.
    - [x] Logic: Merge duplicates vs New Line.
    - [x] Logic: Weighted item decimal handling (`0.500` kg).
- [x] **7.2 Calculation Engine**
    - [x] Implement `Decimal` based math (No floats).
    - [x] Calculate `Subtotal`, `LineDiscount`, `CartDiscount`, `Total`.
- [x] **7.3 Advanced Discount System**
    - [x] **Item-Level Discounts:** Percentage or fixed amount
    - [x] **Cart-Level Discounts:** Applied to total
    - [x] **Customer Discounts:** Auto-apply from customer profile
    - [x] **Product-Specific Discounts:** Per product rules
    - [x] **Group Discounts:** Category-based discounts
    - [x] **Discount Precedence:** Product > Group > Customer
- [x] **7.4 Price Override**
    - [x] **Manual Price Change:** If allowed by product settings
    - [x] **Permission Check:** Require higher access level
    - [x] **Price History:** Log original price

---

### Phase 8: Transaction Processing ✅
*Goal: The core business function.*

- [x] **8.1 Transaction Service**
    - [x] Implement **Atomic Commit** (DB Transaction).
    - [x] Sequence: Save Header -> Save Lines -> Deduct Stock -> Commit.
- [x] **8.2 Operations**
    - [x] **Hold Bill:** Serialize cart to "Pending" table.
    - [x] **Recall Bill:** Restore from Pending.
    - [x] **Void Bill:** Record void reason.
    - [x] **Lock Order:** Save and prevent modifications
    - [x] **Transfer Order:** Split to another order/user
- [x] **8.3 Multiple Open Orders**
    - [x] **Unlimited Simultaneous Orders:** Per user
    - [x] **Order Switching:** Quick navigation between orders
    - [x] **Order List View:** See all open orders
    - [x] **User-Specific Orders:** Filter by cashier
    - [x] **Order Status Tracking:** Open/Saved/Locked/Closed/Voided
- [x] **8.4 Document Numbering**
    - [x] **Auto-Generated Numbers:** Sequential document IDs
    - [x] **Configurable Format:** Prefix/suffix patterns
    - [x] **Reset Options:** Daily/monthly/yearly reset

---

### Phase 9: Sri Lankan Compliance Module (Tax) — Mostly Complete ✅
*Goal: Local tax laws.*

- [x] **9.1 Tax Engine (Backward Calc)**
    - [x] Logic: `Shelf Price = Base + VAT + SSCL`.
    - [x] Implement extraction formula for 18% VAT.
    - [x] Implement extraction formula for 2.5% SSCL.
- [x] **9.2 Invoicing Rules** *(2 items remaining — nice to have)*
    - [x] Logic: Detect Registered Customer (VAT No).
    - [x] Output: Switch Receipt format to "Tax Invoice".
    - [ ] **Tax Breakdown Display:** Show VAT and SSCL separately on receipt
    - [ ] **Tax-Exempt Sales:** Support with permission

> **Removed:** Phase 9.3 (Multi-Tax Support) — Sri Lanka has fixed VAT (18%) + SSCL (2.5%). Small retailers don't need per-product tax rates, multiple taxes per product, or tax overrides. Current implementation is correct and complete for the market.

---

### Phase 10: Payment & Checkout ✅
*Goal: Flexible tender handling.*

- [x] **10.1 Payment UI**
    - [x] Design Payment Dialog (Big Total).
    - [x] "Smart Cash" Buttons (Exact, 1000, 5000).
- [x] **10.2 Logic**
    - [x] **Split Payment:** Cash + Card.
    - [x] **Credit Sale:** Assign to Customer Debt.
    - [x] **Change Calculation:** Live update.
- [x] **10.3 Payment Types**
    - [x] **Configurable Payment Methods:** Create custom types
    - [x] **Payment Type Properties:**
        - [x] Mark transaction as paid (Yes/No)
        - [x] Allow change calculation
        - [x] Auto-open cash drawer
        - [x] Auto-print receipt
        - [x] Keyboard shortcut assignment
    - [x] **Quick Payment (F12):** One-click default payment
    - [x] **Payment Form Settings:** Customize display
- [x] **10.4 Receipt Options**
    - [x] **Print Receipt:** Thermal printer
    - [x] **Print Invoice:** A4 printer
    - [x] **Email Receipt:** Send to customer
    - [x] **Save as PDF:** Digital copy
    - [x] **Skip Printing:** No receipt option
    - [x] **Receipt Dialog:** Choose action after sale

---

### Phase 11: Customer Management (CRM) ✅
*Goal: Repeat business.*

- [x] **11.1 Customer DB**
    - [x] CRUD for Customers (Name, Phone, VAT No).
    - [x] Credit Limit logic.
    - [x] **Company Information:** Separate company fields
    - [x] **Multiple Contacts:** Phone, email, address
    - [x] **Customer Type:** Customer vs Supplier flag
- [x] **11.2 Loyalty**
    - [x] Points Engine (Earn X points per Y spent).
    - [x] Redemption Logic at checkout.
    - [x] **Loyalty Card Assignment:** Barcode scannable cards
    - [x] **Quick Customer Lookup:** Search by card/phone/tax number
    - [x] **Purchase History:** View customer transactions
- [x] **11.3 Customer Features**
    - [x] **Price List Assignment:** Customer-specific pricing
    - [x] **Customer Discounts:** Pre-configured discount rules
    - [x] **Credit Terms:** Payment terms per customer
    - [x] **Outstanding Balance:** Real-time debt tracking
    - [x] **Customer Reports:** Purchase patterns, payment history
- [x] **11.4 Customer Selection**
    - [x] Select from sales screen
    - [x] Select from payment screen
    - [x] Search by name/tax/card
    - [x] Quick add during sale

---

### Phase 12: Shift Management ✅
*Goal: Cash control and theft prevention.*

- [x] **12.1 Cash Control**
    - [x] **Float Entry:** Start of day cash.
    - [x] **Cash In/Out:** Petty cash recording.
- [x] **12.2 Reports**
    - [x] **X-Read:** Mid-shift snapshot.
    - [x] **Z-Read:** End of day reset & variance calculation.
- [x] **12.3 End of Day Process**
    - [x] **Cash Reconciliation:** Count vs expected
    - [x] **Variance Tracking:** Over/short reporting
    - [x] **Shift Summary:** Sales by payment type
    - [x] **User Activity:** Per-cashier performance
    - [x] **Transaction Count:** Number of sales
    - [x] **Voided Items:** Track cancellations
    - [x] **Optional Number Reset:** Daily document numbering

---

### Phase 13: Receipt Generation ✅
*Goal: Professional physical output.*

- [x] **13.1 Templating**
    - [x] Create `ReceiptBuilder` class.
    - [x] Header (Logo, Address).
    - [x] Body (Items, Qty, Price).
    - [x] Footer (Tax breakdown, Thank you message).
- [x] **13.2 Routing**
    - [x] Logic to print to Kitchen vs Counter based on Category.
- [x] **13.3 Advanced Receipt Features**
    - [x] **Company Logo:** Image printing support
    - [x] **Custom Header/Footer:** Configurable text
    - [x] **Barcode/QR Code:** On receipt (with plugins)
    - [x] **Tax Breakdown Display:** Line-by-line tax amounts
    - [x] **Payment Details:** Show payment types and change
    - [x] **Item Merging:** Combine duplicate items
    - [x] **Receipt vs Invoice:** Different formats
- [x] **13.4 Template Customization**
    - [x] Visual template designer
    - [x] Multiple template support
    - [x] Test print functionality
    - [x] Preview before printing

---

### Phase 14: Reporting & Analytics ✅
*Goal: Business insights.*

- [x] **14.1 Dashboard**
    - [x] Live Sales Ticker.
    - [x] "Top Movers" Widget.
    - [x] **Today's Summary:** Sales, profit, transactions
    - [x] **Stock Alerts:** Low stock warnings
- [x] **14.2 Core Reports**
    - [x] Sales by Date/User/Category.
    - [x] Inventory Valuation.
    - [x] Tax Liability Report (Output VAT - Input VAT).
- [x] **14.3 Export**
    - [x] Export Table Data to Excel/CSV.
    - [x] **PDF Export:** Professional report format
    - [x] **Email Reports:** Direct email delivery
- [x] **14.4 Comprehensive Report Suite**
    - [x] **Sales Reports:** Summary, by Product/Group/User/Payment Type/Customer/Hourly
    - [x] **Financial Reports:** Profit, Tax, Payment Type, Cash In/Out
    - [x] **Inventory Reports:** Stock on Hand, Value, Movement, Low Stock, Reorder, by Group
    - [x] **Customer Reports:** Sales, Purchase History, Unpaid, Discounts
    - [x] **Product Reports:** Best Selling, Margin, Slow Moving, Price List
    - [x] **Document Reports:** List, Voided, Unpaid, Paid
- [x] **14.5 Report Filtering & Actions**
    - [x] Date range, multi-field filtering, view/print/export/email
- [x] **14.6 Scheduled Reporting**
    - [x] Daily/weekly/monthly automatic reports with auto-email

---

### Phase 15: Settings & Configuration ✅
*Goal: User customizability.*

- [x] **15.1 Config UI** — Hardware, Business Details, Tax Rates
- [x] **15.2 Feature Flags** — Toggle features (Loyalty, Touch Mode, etc.)
- [x] **15.3 Comprehensive Settings** — General, Order & Payment, Product, Document, Print, User settings — all complete

---

### Phase 16: Theme & Localization ✅
*Goal: Ceylon Byte Branding.*

- [x] **16.1 Theme Engine** — Ceylon Night/Day themes, high-contrast, touch-optimized, color customization
- [x] **16.2 Localization** — Sinhala/Tamil translations, runtime language switcher, Unicode fonts, locale formatting

---

### Phase 21: Document Management System ✅
*Goal: Comprehensive transaction documentation.*

- [x] **21.1 Document Types** — Sales, Proforma/Quotation, Purchase, Adjustment
- [x] **21.2 Document Properties** — Header, items, totals, payment info — all complete
- [x] **21.3 Document Operations** — View, create, void, print/export — all complete
- [x] **21.4 Proforma/Quotation System** — Create quotes, convert to sale, custom template
- [x] **21.5 Document Filters** — Date range, type, paid status, customer/supplier, number, user

---

### Phase 25: Credit Management & Accounts Receivable ✅
*Goal: Manage customer credit sales.*

- [x] **25.1 Credit Sale Features** — Credit payment type, unpaid tracking, outstanding balance
- [x] **25.2 Settling Credit Balance** — Credit payments screen, automatic distribution, partial payments, receipt
- [x] **25.3 Credit Management** — Credit limit, terms, block if over limit, reports
- [x] **25.4 Payment Allocation** — Auto distribution to oldest invoices, partial payments, receipts

---

## Remaining Phases (In Priority Order)

### Phase 31: Polish & Hardening ✅
*Goal: Fix gaps in completed features before shipping to first client.*

- [x] **31.1 Returns/Refund UI Flow**
    - [x] Proper return-to-stock workflow with RefundDialog
    - [x] Return against original sale (lookup by receipt number)
    - [x] Stock restoration on return via TransactionService.process_refund()
- [x] **31.2 Customer Account Statements**
    - [x] StatementService for generating structured statement data
    - [x] CustomerStatementDialog with date range selection
    - [x] Running balance display with debit/credit breakdown
- [x] **31.3 Barcode Label Printing**
    - [x] LabelService generating CODE128 barcode label commands
    - [x] LabelPrintDialog for batch printing with product search
    - [x] Print Labels button in inventory view
- [x] **31.4 End-of-Day Automation**
    - [x] BackupService (zip DB + images + settings)
    - [x] Backup prompt after shift close in ShiftClosingDialog
- [x] **31.5 Receipt Reprint**
    - [x] ReceiptReprintDialog with search by doc number and date range
    - [x] Reprint via ReceiptBuilder + PrintWorker
- [x] **31.6 Duplicate Barcode Detection** *(already existed in product_editor.py)*
    - [x] Warn on product creation if barcode already exists
- [x] **31.7 Manager Override Integration**
    - [x] check_permission_with_override() utility helper
    - [x] Used in void_bill, change_line_price, refund
    - [x] ManagerOverrideDialog already existed
- [x] **31.8 Touch Visual Product Grid**
    - [x] ProductGridPanel with category tabs and product buttons
    - [x] Collapsible panel in SalesView (More button toggle)
- [x] **31.9 Branding on All Outputs**
    - [x] "Powered by CB POS — ceybyte.com" on all receipts
    - [x] Branding footer on PDF exports and Excel reports
    - [x] Invoice company details from ConfigService (not hardcoded)
    - [x] Z-report branding
- [x] **31.10 Trilingual Receipt Strings**
    - [x] RECEIPT_STRINGS dictionary with en/si/ta translations
    - [x] Receipt labels use translated strings based on language config
- [x] **31.11 Units of Measurement CRUD**
    - [x] Unit model (name, abbreviation, decimal_places, is_active) with Product FK
    - [x] UnitService with full CRUD (create, update, soft-delete with product guard)
    - [x] UnitManagerDialog accessible from Inventory view
    - [x] Unit selector integrated into ProductEditor
    - [x] Inventory table shows unit abbreviation from product.unit relationship
    - [x] Default seed units (Piece, Kilogram, Gram, Liter, Meter, Pack, Box, Dozen)

---

### Phase 17: Data Safety
*Goal: Protect retailers from data loss. This is the #1 risk for small retailers.*

- [x] **17.1 CSV Import** *(already built — `import_service.py`)*
    - [x] Products with template and column mapping
    - [x] Duplicate handling and validation
- [x] **17.2 Backup System — MUST HAVE**
    - [x] **Manual Backup** (zip DB + product images to chosen location)
    - [x] **Auto-Backup on App Close**
    - [x] **Restore from Backup** (select zip, verify, restore)
    - [x] **Backup Retention:** Keep last N backups
- [x] **17.3 Database Maintenance**
    - [x] Database Optimizer (`VACUUM` on schedule or manual trigger)
- [x] **17.4 CSV Export**
    - [x] Products, Customers, Sales data export

---

### Phase 19: Quality Assurance
*Goal: Confidence before shipping.*

- [x] **19.1 Unit Tests — Math Engine**
    - [x] Tax calculations (VAT backward calc, SSCL)
    - [x] Discount calculations (item, cart, customer, group)
    - [x] Cart totals and rounding
- [x] **19.2 Unit Tests — Transaction Service**
    - [x] Create sale (atomic commit, stock deduction)
    - [x] Void sale (stock restoration, audit trail)
    - [x] Refund workflow
- [x] **19.3 Unit Tests — Credit Service**
    - [x] Credit ledger entries
    - [x] Payment allocation (oldest first)
    - [x] Credit limit enforcement
- [x] **19.4 Integration Test — Full Sale Workflow**
    - [x] Cart → Payment → Receipt → Stock deduction → Shift totals
    - [x] End-to-end with database

---

### Phase 20: Packaging & Deployment
*Goal: Clients can self-install.*

- [x] **20.1 PyInstaller**
    - [x] Create `cbpos.spec` file.
    - [x] Handle hidden imports (SQLAlchemy, PyQt).
    - [x] Bundle assets (Fonts/Icons).
- [ ] **20.2 Windows Installer**
    - [ ] InnoSetup installer (`setup.iss`)
    - [ ] Desktop shortcut and Start Menu entry
    - [ ] Clean uninstaller
- [ ] **20.3 Auto-Update Checker**
    - [ ] Check GitHub releases on startup
    - [ ] Notify user of new version
    - [ ] Download link / one-click update
- [ ] **20.4 First-Run Setup Wizard**
    - [ ] Verify `setup_wizard.py` works end-to-end
    - [ ] Business details, printer setup, initial admin PIN
    - [ ] Sample data option for demo
- [x] **20.5 Licensing**
    - [x] Machine ID generation
    - [x] License key verification

---

### Phase 22: Advanced Purchase & Inventory
*Goal: Complete the inventory lifecycle for retailers who buy stock from suppliers.*

- [ ] **22.1 Goods Received Note (GRN)**
    - [ ] Receive stock against purchase order
    - [ ] Verify quantities against PO
    - [ ] Update stock on confirmation
    - [ ] External document reference (supplier invoice number)
- [ ] **22.2 Physical Stock Take**
    - [ ] Create stock count document
    - [ ] Count → Compare → Adjust workflow
    - [ ] Variance report (expected vs counted)
    - [ ] Approval before applying adjustments
- [ ] **22.3 Supplier Payment Tracking**
    - [ ] Track who we owe and how much
    - [ ] Payment against purchase invoices
    - [ ] Outstanding payables report

---

### Phase 26: UI Polish
*Goal: Quality-of-life improvements.*

- [ ] **26.1 Remaining Keyboard Shortcuts**
    - [ ] F8 - Save current, start new sale
    - [ ] F10 - Open payment screen
    - [ ] F12 - Quick close with default payment
    - [ ] Ctrl+D - Open cash drawer
    - [ ] Page Up/Down - Select first/last item
- [ ] **26.2 Sound Effects**
    - [ ] Beep on successful scan
    - [ ] Error sound on failed operation
    - [ ] Payment complete sound
- [ ] **26.3 Loading Indicators**
    - [ ] Loading spinners for long operations (reports, exports)
    - [ ] Progress bars for imports/backups

---

### Phase 27: Admin Tools
*Goal: Support and troubleshooting for self-install clients.*

- [ ] **27.1 Database Info**
    - [ ] View database location and file size
    - [ ] Table row counts (products, sales, customers)
- [ ] **27.2 Error Log Viewer**
    - [ ] View application error logs in-app
    - [ ] Export logs for support
- [ ] **27.3 Printer Test Page**
    - [ ] Send test print to configured printer
    - [ ] Verify printer connectivity

---

### Phase 23: Promotions & Pricing Engine
*Goal: Advanced pricing strategies. Most core features already built.*

- [x] **23.1 Price Lists** *(already implemented)*
    - [x] Multiple named price lists (`price_list_service.py`, `pricelist_view.py`)
    - [x] Product-specific overrides
    - [x] Customer assignment
    - [x] Automatic application
- [x] **23.2 Customer Discounts** *(already implemented)*
    - [x] Product-specific and group discounts
    - [x] Percentage or fixed amount
    - [x] Automatic application with precedence rules
    - [x] Discount tracking and reports
- [x] **23.3 Price Change Control** *(already implemented)*
    - [x] Per-product "price change allowed" flag
    - [x] Permission-based override
    - [x] Price history logging
- [x] **23.4 Basic Promotions** *(already implemented)*
    - [x] Percentage discount promotions (`promotion_service.py`, `promotion_view.py`)
    - [x] Fixed price promotions
    - [x] Start/end date and time
    - [x] Active/inactive toggle
    - [x] Product/group selection
- [ ] **23.5 Remaining Promotion Types** *(nice to have)*
    - [ ] Buy X get Y promotions
    - [ ] Time-based happy hour (day-of-week scheduling)
    - [ ] Quantity discount tiers (buy 3+ get 10% off)

---

### Phase 30: Simple Reports
*Goal: Basic business insights beyond what's in Phase 14.*

> **Simplified from "Advanced Analytics & BI".** Removed: RFM scoring, CLV estimation, churn indicators, basket analysis, forecasting, BI export.

- [ ] **30.1 Profit Margins by Product/Category**
    - [ ] Cost vs selling price analysis
    - [ ] Margin percentage ranking
    - [ ] Category-level rollup
- [ ] **30.2 Sales Trends**
    - [ ] Daily/weekly/monthly comparison
    - [ ] Same period last month/year
    - [ ] Simple trend direction indicator

> Note: Best/worst selling products report already exists in Phase 14.

---

### Phase 18: Multi-Terminal *(Built — Needs Real-World Testing)*
*Goal: Allow multiple PCs to sell from one central database over LAN.*

> **Status:** Code is built and checked in. PostgreSQL support, network configuration UI, concurrency control, and multi-user operations are all implemented. However, this has not been tested with real clients in production. No further development investment until a client needs it.

- [x] **18.1 Database Engine Factory** — Dynamic SQLite/PostgreSQL switching
- [x] **18.2 Network Configuration UI** — Mode selector, server settings, test connection
- [x] **18.3 Concurrency & Locking** — Optimistic locking, conflict handling
- [x] **18.4 Multi-User Operations** — Simultaneous users, real-time inventory, centralized reporting

---

## Bonus Phase: Training & Documentation
*Goal: Smooth rollout.*

- [ ] **B.1 User Documentation**
    - [ ] Cashier manual
    - [ ] Manager/admin guide
    - [ ] Hardware setup guide
- [ ] **B.2 Developer Documentation**
    - [ ] Architecture overview
    - [ ] API reference

---

## Future Addon: Restaurant Module
*Not part of the core retail product. Build only if there is demand from F&B clients.*

- [ ] Floor Plan Design — Visual layout designer (drag/drop tables), multiple floors
- [ ] Table Operations — Assign orders to tables, status indicators, move/combine/split
- [ ] Kitchen Print Stations — Multi-station routing, separate tickets, order timing
- [ ] Restaurant Settings — Enable/disable mode, auto-show floor plan

---

## Removed Phases

The following phases were removed from the roadmap as they are out of scope for small single-store retail:

| Removed | Reason |
|---------|--------|
| **Phase 28: Multi-Location & Warehouse** | Single-store target. Different product entirely. |
| **Phase 29: Gift Cards & Vouchers** | Small retailers don't need this. |
| **Phase 9.3: Multi-Tax Support** | Sri Lanka has fixed VAT + SSCL. No per-product tax rates needed. |
