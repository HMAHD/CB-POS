# 📋 CB POS: Master Industrial Roadmap (30 Phases)

**Status:** 🟡 In Progress  
**Architecture:** Python 3.12 | PyQt6 | MVC Pattern | SQLite/PostgreSQL  
**Target:** Industrial Retail (Sri Lanka)  
**Based on:** POS Feature Analysis + Industrial Best Practices

---

## 🔀 Recommended Build Order (Retail Focus)

1. Phase 1 – Project Initialization & Environment  
2. Phase 2 – Database Layer (The Brain)  
3. Phase 3 – Authentication & Security  
4. Phase 4 – Advanced Inventory Management  
5. Phase 5 – Hardware Abstraction Layer (HAL)  
6. Phase 6 – The Sales Terminal (UI/UX)  
7. Phase 7 – Cart Logic & Math Engine  
8. Phase 8 – Transaction Processing  
9. Phase 10 – Payment & Checkout  
10. Phase 9 – Sri Lankan Compliance Module  
11. Phase 11 – Customer Management (CRM)  
12. Phase 12 – Shift Management  
13. Phase 13 – Receipt Generation  
14. Phase 14 – Reporting & Analytics  
15. Phase 21 – Document Management System  
16. Phase 22 – Advanced Purchase & Inventory  
17. Phase 23 – Promotions & Pricing Engine  
18. Phase 25 – Credit Management & Accounts Receivable  
19. Phase 29 – Gift Cards & Vouchers  
20. Phase 28 – Multi-Location & Warehouse  
21. Phase 18 – Networking & Sync (Future Proofing)  
22. Phase 17 – Data Management  
23. Phase 27 – System Administration Tools  
24. Phase 15 – Settings & Configuration  
25. Phase 16 – Theme & Localization  
26. Phase 26 – Advanced UI/UX Features  
27. Phase 30 – Advanced Analytics & BI  
28. Phase 19 – Quality Assurance  
29. Phase 20 – Packaging & Deployment  
30. Bonus Phase – Training & Documentation  
31. Restaurant Module – moved from Phase 24 (do later)

---

## 🏗️ Phase 1: Project Initialization & Environment
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

## 💾 Phase 2: Database Layer (The Brain)
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
- [x] **2.4 Extended Models **
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

## 🔐 Phase 3: Authentication & Security
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
    - [ ] Add "Manager Override" popup logic.
- [x] **3.4 Session Management**
    - [x] Auto-logout on inactivity (configurable timeout)
    - [x] Session activity logging
    - [x] Multi-user session tracking (for networked version)
    - [x] Password recovery mechanism (email-based)

---

## 📦 Phase 4: Advanced Inventory Management
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
- [x] **4.4 Advanced Stock Features **
    - [x] **Reorder Point System:** Auto-generate purchase suggestions
    - [x] **Preferred Quantity:** Target stock levels per product
    - [x] **Supplier Assignment:** Default supplier per product
    - [x] **Service Items:** Non-stock items (don't track inventory)
    - [x] **Stock History View:** Complete movement audit trail
    - [x] **Prevent Negative Inventory:** Optional blocking with override
    - [x] **Stock Valuation Report:** FIFO/LIFO/Weighted Average
- [x] **4.5 Category Management**
    - [x] Hierarchical category tree (unlimited depth)
    - [x] Category-based discounts and promotions
    - [x] Visual category icons for touch interface
    - [x] Category-based reporting

---

## 🤖 Phase 5: Hardware Abstraction Layer (HAL)
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

## 🖥️ Phase 6: The Sales Terminal (UI/UX)
*Goal: A mouse-free interface for high-speed checkout.*

- [x] **6.1 Layout Engine**
    - [x] **Left Panel:** High-Contrast Cart Grid.
    - [x] **Right Panel:** Command Center (Numpad + Action Grid).
    - [x] **Top Bar:** Status Indicators (Printer, Network, User).
- [x] **6.2 Interaction Design**
    - [x] Implement **Focus Trap** (Cursor auto-return).
    - [x] Map Function Keys (`F1`-`F12`) to Actions.
    - [ ] Create "Touch Visual Groups" for non-barcoded items.
- [x] **6.3 Visual Layout Mode **
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

## 🛒 Phase 7: Cart Logic & Math Engine
*Goal: Precision calculation without floating point errors.*

- [x] **7.1 Cart Service**
    - [x] Implement `add_item`, `remove_item`, `update_qty`.
    - [x] Logic: Merge duplicates vs New Line.
    - [x] Logic: Weighted item decimal handling (`0.500` kg).
- [x] **7.2 Calculation Engine**
    - [x] Implement `Decimal` based math (No floats).
    - [x] Calculate `Subtotal`, `LineDiscount`, `CartDiscount`, `Total`.
- [x] **7.3 Advanced Discount System **
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

## 💳 Phase 8: Transaction Processing
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
- [x] **8.3 Multiple Open Orders **
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

## 🇱🇰 Phase 9: Sri Lankan Compliance Module (Tax)
*Goal: Local tax laws.*

- [x] **9.1 Tax Engine (Backward Calc)**
    - [x] Logic: `Shelf Price = Base + VAT + SSCL`.
    - [x] Implement extraction formula for 18% VAT.
    - [x] Implement extraction formula for 2.5% SSCL.
- [x] **9.2 Invoicing Rules**
    - [x] Logic: Detect Registered Customer (VAT No).
    - [x] Output: Switch Receipt format to "Tax Invoice".
    - [ ] **Tax Breakdown Display:** Show VAT and SSCL separately
    - [ ] **Tax-Exempt Sales:** Support with permission
- [ ] **9.3 Multi-Tax Support (Future)**
    - [ ] **Per-Product Tax Rates:** Different taxes per item
    - [ ] **Multiple Taxes Per Product:** Tax1:10|Tax2:5 format
    - [ ] **Tax Override:** Change rate during sale
    - [ ] **Fixed Tax Amounts:** Support fixed-value taxes

---

## 💵 Phase 10: Payment & Checkout
*Goal: Flexible tender handling.*

- [x] **10.1 Payment UI**
    - [x] Design Payment Dialog (Big Total).
    - [x] "Smart Cash" Buttons (Exact, 1000, 5000).
- [x] **10.2 Logic**
    - [x] **Split Payment:** Cash + Card.
    - [x] **Credit Sale:** Assign to Customer Debt.
    - [x] **Change Calculation:** Live update.
- [x] **10.3 Payment Types **
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

## 👥 Phase 11: Customer Management (CRM)
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
- [x] **11.3 Customer Features **
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

## ⏲️ Phase 12: Shift Management
*Goal: Cash control and theft prevention.*

- [x] **12.1 Cash Control**
    - [x] **Float Entry:** Start of day cash.
    - [x] **Cash In/Out:** Petty cash recording.
- [x] **12.2 Reports**
    - [x] **X-Read:** Mid-shift snapshot.
    - [x] **Z-Read:** End of day reset & variance calculation.
- [x] **12.3 End of Day Process **
    - [x] **Cash Reconciliation:** Count vs expected
    - [x] **Variance Tracking:** Over/short reporting
    - [x] **Shift Summary:** Sales by payment type
    - [x] **User Activity:** Per-cashier performance
    - [x] **Transaction Count:** Number of sales
    - [x] **Voided Items:** Track cancellations
    - [x] **Optional Number Reset:** Daily document numbering

---

## 🧾 Phase 13: Receipt Generation
*Goal: Professional physical output.*

- [x] **13.1 Templating**
    - [x] Create `ReceiptBuilder` class.
    - [x] Header (Logo, Address).
    - [x] Body (Items, Qty, Price).
    - [x] Footer (Tax breakdown, Thank you message).
- [x] **13.2 Routing**
    - [x] Logic to print to Kitchen vs Counter based on Category.
- [x] **13.3 Advanced Receipt Features **
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

## 📊 Phase 14: Reporting & Analytics
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
- [x] **14.4 Comprehensive Report Suite **
    - [x] **Sales Reports:**
        - [x] Sales Summary by period
        - [x] Sales by Product (individual performance)
        - [x] Sales by Group (category performance)
        - [x] Sales by User (employee performance)
        - [x] Sales by Payment Type
        - [x] Sales by Customer
        - [x] Hourly Sales (time-based patterns)
    - [x] **Financial Reports:**
        - [x] Profit Report (margins and totals)
        - [x] Tax Report (tax collected by rate)
        - [x] Payment Type Report
        - [x] Cash In/Out movements
    - [x] **Inventory Reports:**
        - [x] Stock on Hand (current levels)
        - [x] Stock Value (inventory valuation)
        - [x] Stock Movement (item history)
        - [x] Low Stock Warning
        - [x] Reorder List (purchase recommendations)
        - [x] Stock by Group
    - [x] **Customer Reports:**
        - [x] Customer Sales
        - [x] Customer Purchase History
        - [x] Unpaid Sales (outstanding balances)
        - [x] Customer Discounts usage
    - [x] **Product Reports:**
        - [x] Best Selling Products
        - [x] Product Margin (profit by product)
        - [x] Slow Moving Items
        - [x] Price List export
    - [x] **Document Reports:**
        - [x] Document List (all by type)
        - [x] Voided Items
        - [x] Unpaid Documents
        - [x] Paid Documents
- [x] **14.5 Report Filtering & Actions**
    - [x] Date range selection
    - [x] Multi-field filtering
    - [x] View on screen
    - [x] Print report
    - [x] Export (PDF/Excel/CSV)
    - [x] Email directly
- [x] **14.6 Scheduled Reporting**
    - [x] Daily automatic reports
    - [x] Weekly summaries
    - [x] Monthly reports
    - [x] Custom intervals
    - [x] Auto-email recipients

---

## ⚙️ Phase 15: Settings & Configuration
*Goal: User customizability.*

- [x] **15.1 Config UI**
    - [x] Hardware Setup (Select Printer/Scanner).
    - [x] Business Details (Name, Address, Phone).
    - [x] Tax Rates configuration.
- [x] **15.2 Feature Flags**
    - [x] Toggle features (e.g., Enable Loyalty, Enable Touch Mode).
- [x] **15.3 Comprehensive Settings **
    - [x] **General Settings:**
        - [x] Company information
        - [x] Regional settings (language, currency, date format)
        - [x] Appearance (theme, font size, zoom level)
    - [x] **Order & Payment Settings:**
        - [x] Default search type (Barcode/Code/Name)
        - [x] Show search switcher
        - [x] Default quantity behavior
        - [x] Default discount type
        - [x] Prevent negative inventory
        - [x] Display receipt print dialog
        - [x] Merge items on receipt
        - [x] Void reason requirement
    - [x] **Product Settings:**
        - [x] Allow quantity decimals
        - [x] Show product groups in search
        - [x] Default tax rate
        - [x] Price change allowed by default
        - [x] Auto-generate product codes
    - [x] **Document Settings:**
        - [x] Document numbering format
        - [x] Starting numbers
        - [x] Prefix/suffix patterns
        - [x] Reset frequency
    - [x] **Print Settings:**
        - [x] Receipt printer selection
        - [x] A4 printer selection
        - [x] Paper width (58mm/80mm/A4)
        - [x] Character set
        - [x] Receipt template
        - [x] Auto-print options
        - [x] Number of copies
    - [x] **User Settings:**
        - [x] Change password
        - [x] Display name
        - [x] Default layout preference
        - [x] Language preference

---

## 🎨 Phase 16: Theme & Localization
*Goal: Ceylon Byte Branding.*

- [x] **16.1 Theme Engine**
    - [x] Implement `styles.qss`.
    - [x] Create "Ceylon Night" and "Ceylon Day" themes.
    - [x] **High-Contrast Mode:** For visibility
    - [x] **Touch-Optimized Theme:** Large buttons
    - [x] **Color Customization:** Brand color support
- [x] **16.2 Localization**
    - [x] Generate `.ts` files for Qt Linguist.
    - [x] Translate UI to Sinhala and Tamil.
    - [x] Implement Runtime Language Switcher.
    - [x] **Font Support:** Unicode fonts for Sinhala/Tamil
    - [x] **Date/Number Formatting:** Locale-specific

---

## 🔄 Phase 17: Data Management
*Goal: Safety and Portability.*

- [ ] **17.1 Backup System**
    - [ ] Manual Backup Button (Zip DB + Images).
    - [ ] Auto-Backup on Exit logic.
    - [ ] **Scheduled Backups:** Automatic daily/weekly
    - [ ] **Backup Location:** Configurable path
    - [ ] **Backup Retention:** Keep last N backups
- [ ] **17.2 Data Tools**
    - [ ] "Factory Reset" (Clear Transactions, keep Items).
    - [ ] Database Optimizer (`VACUUM`).
    - [ ] **Database Repair:** Fix corruption issues
- [ ] **17.3 Import/Export **
    - [ ] **CSV Import:**
        - [ ] Products (with template)
        - [ ] Customers
        - [ ] Suppliers
        - [ ] Column mapping
        - [ ] Duplicate handling (skip/merge)
        - [ ] Validation before import
        - [ ] Progress tracking
    - [ ] **CSV Export:**
        - [ ] Products
        - [ ] Customers
        - [ ] Sales data
        - [ ] Stock levels
    - [ ] **Bulk Operations:**
        - [ ] Bulk price update
        - [ ] Bulk category assignment
- [ ] **17.4 Database Utilities**
    - [ ] View database location
    - [ ] Change database server (for networked version)
    - [ ] Database health check
    - [ ] Integrity verification

---

## 🌐 Phase 18: Local Network & Multi-Terminal (LAN)
*Goal: Allow multiple PCs to sell from one central database over Ethernet/WiFi.*

  - [x] **18.1 Database Engine Factory**
      - [x] Add `psycopg2-binary` dependency.
      - [x] Refactor `core/database.py` to support dynamic switching.
      - [x] Implement `get_db_url()`: Returns `sqlite:///...` or `postgresql://...` based on config.
      - [x] Configure **Connection Pooling** (QueuePool) for PostgreSQL mode.
  - [x
  ] **18.2 Network Configuration UI**
      - [x] Create `ui/views/settings/network_page.py`.
      - [x] **Mode Selector:** [Standalone (Default)] vs [Network Client].
      - **Server Settings:** Host IP, Port, DB Name, Username, Password.
      - **Test Connection:** Button to verify visibility of the Server PC.
  - [x] **18.3 Concurrency & Locking**
      - **Optimistic Locking:** Add `version_id` to `Product` model.
      - **Conflict Handling:** Update `TransactionService` to catch `StaleDataError`.
          - *Scenario:* Cashier A and B try to buy the last item at the exact same moment. The DB rejects the second one. The system must auto-refresh and tell Cashier B "Stock changed, retrying...".

---

## 🌐 Phase 18: Networking & Sync (Future Proofing)
*Goal: Multi-terminal readiness.*

- [x] **18.1 API Hooks**
    - [x] Prepare structure for REST API client.
    - [x] **Client-Server Architecture:** Design for multi-terminal
- [x] **18.2 Sync Worker**
    - [x] Create background thread for potential cloud sync.
- [x] **18.3 Multi-Terminal Support (From Aronium Pro)**
    - [x] **Database Server Setup:**
        - [x] PostgreSQL server configuration
        - [x] Network discovery
        - [x] Connection pooling
        - [x] Test connectivity
    - [x] **Multi-User Operations:**
        - [x] Simultaneous users support
        - [x] User-specific orders
        - [x] Real-time inventory updates
        - [x] Centralized reporting
        - [x] User activity tracking
    - [x] **Concurrency Control:**
        - [x] Optimistic locking
        - [x] Stock conflict detection
        - [x] First-come-first-served logic
        - [x] Real-time sync
    - [x] **Network Configuration:**
        - [x] Server name/IP setup
        - [x] Database instance config
        - [x] Authentication settings
        - [x] Auto-discover servers
- [x] **18.4 Cloud Integration (Future)**
    - [x] Cloud backup
    - [x] Remote monitoring
    - [x] Multi-location consolidation

---

## 🧪 Phase 19: Quality Assurance
*Goal: Bug-free code.*

- [ ] **19.1 Unit Tests**
    - [ ] Test Math Engine (Rounding, Tax).
    - [ ] Test Cart Logic.
    - [ ] **Test Discount Calculations:** All discount types
    - [ ] **Test Tax Calculations:** Sri Lankan tax formulas
    - [ ] **Test Payment Logic:** Split payments, credit
- [ ] **19.2 Integration Tests**
    - [ ] Test Database Transactions (Rollback).
    - [ ] **Test Hardware Integration:** Printer, scanner, drawer
    - [ ] **Test Multi-User Scenarios:** Concurrent access
- [ ] **19.3 Stress Tests**
    - [ ] Rapid Scan Test (50ms interval).
    - [ ] Large DB Load Test (50k items).
    - [ ] **Long-Running Session:** 24-hour stability test
    - [ ] **High-Volume Sales:** 1000 transactions/day
- [ ] **19.4 User Acceptance Testing**
    - [ ] Real-world scenario testing
    - [ ] Beta testing with actual retailers
    - [ ] Performance benchmarking

---

## 🚀 Phase 20: Packaging & Deployment
*Goal: Shipping the product.*

- [x] **20.1 PyInstaller**
    - [x] Create `cbpos.spec` file.
    - [x] Handle hidden imports (SQLAlchemy, PyQt).
    - [x] Bundle assets (Fonts/Icons).
- [ ] **20.2 Installer (InnoSetup)**
    - [ ] Create `setup.iss` script.
    - [ ] Register Desktop Shortcuts.
    - [ ] **Start Menu Integration:** Program shortcuts
    - [ ] **File Associations:** Associate with CB POS files
    - [ ] **Uninstaller:** Clean removal process
- [x] **20.3 Licensing**
    - [x] Implement Machine ID generation.
    - [x] Create License Key verification logic.
    - [ ] **Activation System:** Online activation
    - [ ] **Trial Period:** 30-day trial
    - [ ] **License Management:** View/update license

---

## 🏪 Phase 21: Document Management System
*Goal: Comprehensive transaction documentation .*

- [ ] **21.1 Document Types**
    - [ ] **Income Documents:**
        - [ ] Sales (regular transactions)
        - [ ] Proforma/Quotation (quotes)
        - [ ] Customer Orders
        - [ ] Returns (credit notes)
    - [ ] **Expense Documents:**
        - [ ] Purchase (inventory receive)
        - [ ] Stock Return (return to supplier)
        - [ ] Purchase Orders
    - [ ] **Internal Documents:**
        - [ ] Inventory Count (physical stock take)
        - [ ] Loss and Damage (write-offs)
        - [ ] Transfer (between locations)
        - [ ] Adjustment (stock corrections)
- [ ] **21.2 Document Properties**
    - [ ] **Header Information:**
        - [ ] Auto-generated document number
        - [ ] Document type and status
        - [ ] Date/time tracking
        - [ ] Customer/Supplier link
        - [ ] User who created
        - [ ] Due date (for unpaid)
    - [ ] **Document Items:**
        - [ ] Product details snapshot
        - [ ] Quantity, price, discount, tax
        - [ ] Line totals
        - [ ] Cost price (for profit tracking)
    - [ ] **Document Totals:**
        - [ ] Subtotal, discount, tax, total
        - [ ] Paid amount and balance
    - [ ] **Payment Information:**
        - [ ] Payment types used
        - [ ] Amounts per type
        - [ ] Change given
- [ ] **21.3 Document Operations**
    - [ ] **View Documents:**
        - [ ] List view with filters
        - [ ] Search by number/customer/date
        - [ ] Status filtering
        - [ ] Type filtering
    - [ ] **Create Document:**
        - [ ] Select type
        - [ ] Add header info
        - [ ] Add items (drag-drop or search)
        - [ ] Add payments
        - [ ] Save and commit
    - [ ] **Edit Document:**
        - [ ] Modify allowed fields
        - [ ] Restrictions on closed documents
    - [ ] **Delete/Void Document:**
        - [ ] Permission-based
        - [ ] Cannot delete if referenced
        - [ ] Void reason tracking
    - [ ] **Print/Export:**
        - [ ] Receipt format
        - [ ] Invoice format (A4)
        - [ ] Proforma format
        - [ ] PDF export
        - [ ] Email to customer
- [ ] **21.4 Proforma/Quotation System**
    - [ ] Create quotes for customers
    - [ ] Does not affect stock
    - [ ] Convert to actual sale later
    - [ ] Custom proforma template
    - [ ] Validity period tracking
- [ ] **21.5 Document Filters**
    - [ ] Date range (from/to)
    - [ ] Document type
    - [ ] Paid status (paid/unpaid/all)
    - [ ] Customer/Supplier
    - [ ] Document number
    - [ ] User who created
    - [ ] Amount range

---

## 📦 Phase 22: Advanced Purchase & Inventory
*Goal: Complete inventory lifecycle management .*

- [ ] **22.1 Purchase Documents**
    - [ ] **Create Purchase:**
        - [ ] Auto-generated number
        - [ ] External document reference (supplier invoice)
        - [ ] Vendor/Supplier selection
        - [ ] Name, company details
        - [ ] Tax number
        - [ ] Contact information
        - [ ] Address
        - [ ] Active/inactive status
    - [ ] **Supplier Features:**
        - [ ] Link products to suppliers
        - [ ] Default supplier per product
        - [ ] Supplier-based reorder reports
        - [ ] Supplier payment tracking
        - [ ] Purchase history per supplier
- [ ] **22.3 Stock Control Plugin Features**
    - [ ] **Reorder Management:**
        - [ ] Reorder point alerts
        - [ ] Preferred quantity targets
        - [ ] Auto-generate purchase suggestions
        - [ ] Low stock warnings (real-time)
        - [ ] Required quantity calculation
    - [ ] **Reorder Reports:**
        - [ ] Reorder Product List (grouped by supplier)
        - [ ] Quantity needed to reach preferred level
        - [ ] Supplier-based filtering
        - [ ] Low stock warning report
        - [ ] Purchase planning tool
- [ ] **22.4 Stock Operations**
    - [ ] **Stock Adjustments:**
        - [ ] Manual quantity changes
        - [ ] Stock take corrections
        - [ ] Damage/loss recording
        - [ ] Transfer between locations
    - [ ] **Stock Documents:**
        - [ ] Purchase receipts
        - [ ] Stock returns
        - [ ] Inventory counts
        - [ ] Loss and damage
        - [ ] Inter-location transfers
    - [ ] **Stock History:**
        - [ ] View all movements
        - [ ] Date range filtering
        - [ ] Document reference
        - [ ] User tracking
        - [ ] Before/after quantities
- [ ] **22.5 Inventory Valuation**
    - [ ] FIFO method
    - [ ] LIFO method
    - [ ] Weighted average
    - [ ] Stock value reports

---

## 🎯 Phase 23: Promotions & Pricing Engine
*Goal: Advanced pricing strategies .*

- [ ] **23.1 Price Lists**
    - [ ] **Multiple Price Lists:**
        - [ ] Create named price lists
        - [ ] Copy/duplicate lists
        - [ ] Bulk price editing
        - [ ] Percentage adjustments
        - [ ] Product-specific overrides
    - [ ] **Price List Assignment:**
        - [ ] Assign to customers
        - [ ] Manual selection in sale
        - [ ] Automatic application
        - [ ] Priority rules
    - [ ] **Price List Operations:**
        - [ ] Create/edit/delete lists
        - [ ] Set product prices per list
        - [ ] Time-based pricing
        - [ ] Customer-specific pricing
- [ ] **23.2 Promotions & Happy Hour**
    - [ ] **Promotion Types:**
        - [ ] Percentage discount
        - [ ] Fixed price
        - [ ] Buy X get Y discounts
        - [ ] Quantity discounts
        - [ ] Time-based promotions
    - [ ] **Configuration:**
        - [ ] Start/End date and time
        - [ ] Days of week selection
        - [ ] Active/inactive toggle
        - [ ] Product/Group selection
    - [ ] **Quantity Promotions:**
        - [ ] Apply to all (e.g., buy 3, get 50% off all 3)
        - [ ] Apply to next (e.g., buy 2, get 1 free)
        - [ ] Required quantity to trigger
        - [ ] Number of items to discount
        - [ ] Product vs group level
        - [ ] Promotion precedence rules
- [ ] **23.3 Customer Discounts**
    - [ ] **Discount Rules:**
        - [ ] Product-specific discounts
        - [ ] Product group discounts
        - [ ] Percentage or fixed amount
        - [ ] Automatic application
        - [ ] Discount precedence: Product > Group > Customer
    - [ ] **Discount Management:**
        - [ ] Assign to customers
        - [ ] Track discount usage
        - [ ] Discount reports
- [ ] **23.4 Price Change Control**
    - [ ] Per-product "price change allowed" flag
    - [ ] Permission-based override
    - [ ] Price history logging
    - [ ] Original price retention

---

## 💳 Phase 25: Credit Management & Accounts Receivable
*Goal: Manage customer credit sales .*

- [ ] **25.1 Credit Sale Features**
    - [ ] **Credit Payment Type:**
        - [ ] Create "Credit" payment method
        - [ ] Uncheck "Mark transaction as paid"
        - [ ] Set default due date (days)
        - [ ] Track unpaid documents
        - [ ] Outstanding balance monitoring
    - [ ] **Credit Sale Workflow:**
        - [ ] Create sale with credit payment
        - [ ] Document marked "Unpaid"
        - [ ] Track in Credit Payments screen
        - [ ] Receive payment later
        - [ ] Allocate to specific invoices
        - [ ] Update status to "Paid"
- [ ] **25.2 Settling Credit Balance**
    - [ ] **Credit Payments Screen:**
        - [ ] Select customer
        - [ ] View outstanding invoices
        - [ ] Enter paid amount
        - [ ] Choose payment type (Cash, Card, etc.)
        - [ ] Automatic distribution (oldest first)
        - [ ] Manual invoice selection
        - [ ] Partial payments support
        - [ ] Full balance settlement
        - [ ] Print payment receipt
- [ ] **25.3 Credit Management**
    - [ ] **Customer Credit Settings:**
        - [ ] Credit limit per customer
        - [ ] Credit terms (payment days)
        - [ ] Block sales if over limit
        - [ ] Credit approval workflow
    - [ ] **Credit Reports:**
        - [ ] Outstanding balances report
        - [ ] Aging analysis (30/60/90 days)
        - [ ] Customer payment history
        - [ ] Credit limit utilization
        - [ ] Overdue accounts
- [ ] **25.4 Payment Allocation**
    - [ ] Automatic distribution to oldest invoices
    - [ ] Manual selection of invoices to pay
    - [ ] Partial payment recording
    - [ ] Payment receipt generation

---

## 🎨 Phase 26: Advanced UI/UX Features
*Goal: Polish and usability enhancements .*

- [ ] **26.1 Keyboard Shortcuts Enhancement**
    - [ ] **Complete Shortcut Mapping:**
        - [ ] Del - Void selected item
        - [ ] F2 - Open discount dialog
        - [ ] F3 - Product search screen
        - [ ] F4 - Change quantity
        - [ ] F7 - Split order screen
        - [ ] F8 - Save current, start new sale
        - [ ] F9 - Create sub-order
        - [ ] F10 - Open payment screen
        - [ ] F11 - Toggle full screen
        - [ ] F12 - Quick close with default payment
        - [ ] Esc - Deselect item, focus search
        - [ ] Ctrl+D - Open cash drawer
        - [ ] Ctrl+T - Toggle search type
        - [ ] Ctrl++ - Zoom in
        - [ ] Ctrl+- - Zoom out
        - [ ] Ctrl+0 - Reset zoom (100%)
        - [ ] Page Up - Select first item
        - [ ] Page Down - Select last item
    - [ ] Customizable shortcut configuration
    - [ ] Shortcut confirmation options
    - [ ] Display shortcut hints in UI
- [ ] **26.2 Touch Optimization**
    - [ ] **Large Touch Buttons:**
        - [ ] Minimum button size (60px height)
        - [ ] Touch-friendly spacing
        - [ ] Visual feedback on touch
    - [ ] **Touch Gestures:**
        - [ ] Swipe to delete
        - [ ] Long press for options
        - [ ] Pinch zoom
    - [ ] **Virtual Keyboard:**
        - [ ] On-screen numpad
        - [ ] On-screen QWERTY keyboard
        - [ ] Auto-show when needed
- [ ] **26.3 Visual Feedback**
    - [ ] **Status Indicators:**
        - [ ] Item status icons (added/confirmed/voided)
        - [ ] Order status colors
        - [ ] Payment status badges
    - [ ] **Progress Indicators:**
        - [ ] Loading spinners
        - [ ] Progress bars for long operations
        - [ ] Success/error notifications
    - [ ] **Sound Effects:**
        - [ ] Beep on successful scan
        - [ ] Error sound
        - [ ] Payment complete sound
- [ ] **26.4 Accessibility**
    - [ ] High contrast mode
    - [ ] Font size adjustment
    - [ ] Colorblind-friendly schemes
    - [ ] Screen reader support
    - [ ] Keyboard-only navigation

---

## 🔧 Phase 27: System Administration Tools
*Goal: Maintenance and troubleshooting utilities.*

- [ ] **27.1 Database Tools**
    - [ ] **Database Health:**
        - [ ] Integrity check
        - [ ] Corruption detection
        - [ ] Repair utilities
        - [ ] Optimization (VACUUM, ANALYZE)
    - [ ] **Database Info:**
        - [ ] View database location
        - [ ] Database size statistics
        - [ ] Table row counts
        - [ ] Index status
- [ ] **27.2 System Diagnostics**
    - [ ] **Health Monitoring:**
        - [ ] Disk space check
        - [ ] Memory usage
        - [ ] CPU utilization
        - [ ] Network status (if networked)
    - [ ] **Error Logging:**
        - [ ] View application logs
        - [ ] Export logs for support
        - [ ] Log level configuration
        - [ ] Automatic error reporting
- [ ] **27.3 Troubleshooting Wizards**
    - [ ] **Printer Troubleshooter:**
        - [ ] Test print
        - [ ] Detect printers
        - [ ] Driver verification
        - [ ] Connection test
    - [ ] **Scanner Troubleshooter:**
        - [ ] Test scan
        - [ ] Barcode format detection
        - [ ] Connection test
    - [ ] **Database Troubleshooter:**
        - [ ] Connection test
        - [ ] Server status (networked)
        - [ ] Migration status
        - [ ] Fix common issues
- [ ] **27.4 Reset & Maintenance**
    - [ ] **Selective Reset:**
        - [ ] Clear transactions only
        - [ ] Clear customers only
        - [ ] Clear products only
        - [ ] Full factory reset
    - [ ] **Data Cleanup:**
        - [ ] Archive old transactions
        - [ ] Delete test data
        - [ ] Clean up orphaned records

---

## 🌍 Phase 28: Multi-Location & Warehouse
*Goal: Support retail chains (From Aronium Community Requests).*

- [ ] **28.1 Multiple Warehouse Locations**
    - [ ] **Location Setup:**
        - [ ] Create locations/warehouses
        - [ ] Location-based inventory
        - [ ] Default location per user
        - [ ] Location selection in POS
    - [ ] **Inter-Location Transfers:**
        - [ ] Transfer documents
        - [ ] Stock movement per location
        - [ ] Approval workflow
- [ ] **28.2 Location-Based Reporting**
    - [ ] Sales by location
    - [ ] Stock by location
    - [ ] Profitability by location
    - [ ] Location comparison dashboards
- [ ] **28.3 Location Permissions**
    - [ ] Per-location access for users
    - [ ] Role-based location visibility
    - [ ] Central vs store-level rights

---

## 🎁 Phase 29: Gift Cards & Vouchers
*Goal: Prepaid and promotional balances.*

- [ ] **29.1 Gift Card Basics**
    - [ ] Issue gift cards
    - [ ] Fixed and variable amounts
    - [ ] Generate card numbers/barcodes
    - [ ] Expiry rules
- [ ] **29.2 Gift Card Usage**
    - [ ] Redeem at POS
    - [ ] Partial redemption
    - [ ] Balance enquiry
    - [ ] Combine with other tenders
- [ ] **29.3 Management & Reporting**
    - [ ] Card list and status
    - [ ] Liability report
    - [ ] Redemption statistics
    - [ ] Expiry tracking

---

## 📈 Phase 30: Advanced Analytics & BI
*Goal: Strategic decision support.*

- [ ] **30.1 KPIs & Dashboards**
    - [ ] Sales KPIs (GMV, margin, AOV)
    - [ ] Inventory KPIs (turnover, coverage)
    - [ ] Cash/credit mix
- [ ] **30.2 Product Analytics**
    - [ ] ABC analysis
    - [ ] Slow/fast movers
    - [ ] Profitability by product/group
- [ ] **30.3 Customer Analytics**
    - [ ] RFM scoring
    - [ ] CLV estimation
    - [ ] Churn indicators
    - [ ] Basket analysis
- [ ] **30.4 Forecasting**
    - [ ] Sales forecasts
    - [ ] Reorder suggestions based on trends
- [ ] **30.5 Integration**
    - [ ] Export datasets to BI tools
    - [ ] Accounting/ERP export hooks

---

## 🎓 Bonus Phase: Training & Documentation
*Goal: Smooth rollout and collaboration.*

- [ ] **B.1 User Documentation**
    - [ ] Cashier manual
    - [ ] Manager/admin guide
    - [ ] Hardware setup guide
- [ ] **B.2 Developer Documentation**
    - [ ] Architecture overview
    - [ ] API reference
    - [ ] Plugin/how-to-extend guide
- [ ] **B.3 Training Assets**
    - [ ] Video tutorials
    - [ ] Sample datasets
    - [ ] Practice exercises
- [x] **Phase 11: Enterprise CRM**
    - [x] Advanced Customer Models (B2B, Contacts).
    - [x] Loyalty Program Basics.
    - [x] Price Lists & Tiered Pricing.ses

---

## 🍽️ Restaurant Module (Deferred from Phase 24)
*Goal: Table and kitchen management for F&B – build only after core retail is stable.*

- [ ] **R1 Floor Plan Design**
    - [ ] Visual layout designer (drag/drop tables)
    - [ ] Multiple floor plans (rooms/areas)
    - [ ] Table sizing and arrangement
    - [ ] Design mode with visual feedback
- [ ] **R2 Floor Plan Management**
    - [ ] Create/edit/delete floor plans
    - [ ] Switch between floors
    - [ ] Save layout configurations
- [ ] **R3 Table Operations**
    - [ ] Assign order to table
    - [ ] Table number tracking
    - [ ] Table status indicators (available/occupied/reserved)
    - [ ] Move orders between tables
    - [ ] Combine/merge tables
    - [ ] Split checks
    - [ ] Table turnover tracking
- [ ] **R4 Kitchen Print Stations**
    - [ ] Multi-station routing by product/group
    - [ ] Separate tickets per station
    - [ ] Kitchen ticket format
    - [ ] Order timing and reprints
    - [ ] Station configuration and templates
- [ ] **R5 Restaurant Settings**
    - [ ] Enable/disable restaurant mode
    - [ ] Auto-show floor plan on login/F9
    - [ ] Single-user vs multi-user behavior
