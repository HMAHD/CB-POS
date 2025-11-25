# 📋 CB POS: Master Industrial Roadmap (20 Phases)

**Status:** 🟡 In Progress
**Architecture:** Python 3.12 | PyQt6 | MVC Pattern | SQLite/PostgreSQL
**Target:** Industrial Retail (Sri Lanka)

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
    - [ ] Setup `pre-commit` hooks (Black, Flake8) for code quality.

## 💾 Phase 2: Database Layer (The Brain)
*Goal: Define the data structure ensuring integrity and speed.*

- [x] **2.1 ORM Setup (SQLAlchemy 2.0)**
    - [x] Implement Singleton Database Connection.
    - [ ] Configure Connection Pooling (for high throughput).
    - [x] Create Base declarative model.
- [x] **2.2 Core Models**
    - [x] **Auth:** `User`, `Role`, `Permission`.
    - [x] **Inventory:** `Category`, `Product`, `ProductVariant`, `Unit`.
    - [x] **Sales:** `Sale`, `SaleItem`, `Payment`.
    - [ ] **Audit:** `Log`, `Shift`, `CashMovement`.
- [ ] **2.3 Migration Engine**
    - [ ] Initialize **Alembic**.
    - [ ] Create initial migration script.
    - [x] Create `scripts/seed.py` for SL Default Data.

## 🔐 Phase 3: Authentication & Security
*Goal: Protect the system from unauthorized access.*

- [x] **3.1 Security Logic**
    - [x] Implement SHA-256 PIN Hashing.
    - [x] Create `AuthService.login(pin)`.
    - [x] Create `SessionManager` (Singleton).
- [ ] **3.2 RBAC (Role-Based Access Control)**
    - [ ] Define Permissions (`CAN_VOID`, `CAN_REFUND`, `CAN_SEE_REPORTS`).
    - [ ] Implement `check_permission` decorator for sensitive functions.
- [x] **3.3 Login UI**
    - [x] Design Split-Screen Login (Brand Left / Numpad Right).
    - [x] Implement Masked PIN Input.
    - [ ] Add "Manager Override" popup logic.

## 📦 Phase 4: Advanced Inventory Management
*Goal: Manage complex retail products.*

- [x] **4.1 Product Logic**
    - [x] Implement `ProductService`.
    - [x] Support **Weighted Items** (Boolean flag).
    - [ ] Support **Composite Items** (Hampers).
- [ ] **4.2 Inventory UI**
    - [ ] Create Product Master Grid (Search, Filter, Sort).
    - [ ] Create Product Editor Dialog.
    - [ ] Implement CSV Import Wizard (`pandas` integration).
- [ ] **4.3 Stock Control**
    - [ ] Implement `StockAdjustment` (Damage/Expired/Correction).
    - [ ] Create "Low Stock" logic and UI indicators.

## 🤖 Phase 5: Hardware Abstraction Layer (HAL)
*Goal: Write code once, run on any hardware.*

- [ ] **5.1 Architecture**
    - [ ] Define Interfaces: `IPrinter`, `IScanner`, `IDisplay`.
- [ ] **5.2 Printing (ESC/POS)**
    - [ ] Implement `ThermalPrinter` driver using `python-escpos`.
    - [ ] Support USB and Network printers.
    - [ ] Implement "Image Print" mode for Sinhala/Tamil text fallback.
- [ ] **5.3 Input Devices**
    - [ ] Implement `BarcodeScanner` hook (differentiate typing vs scanning).
    - [ ] Implement `CashDrawer` kick logic (RJ11 signal).

## 🖥️ Phase 6: The Sales Terminal (UI/UX)
*Goal: A mouse-free interface for high-speed checkout.*

- [x] **6.1 Layout Engine**
    - [x] **Left Panel:** High-Contrast Cart Grid.
    - [x] **Right Panel:** Command Center (Numpad + Action Grid).
    - [ ] **Top Bar:** Status Indicators (Printer, Network, User).
- [x] **6.2 Interaction Design**
    - [x] Implement **Focus Trap** (Cursor auto-return).
    - [x] Map Function Keys (`F1`-`F12`) to Actions.
    - [ ] Create "Touch Visual Groups" for non-barcoded items.

## 🛒 Phase 7: Cart Logic & Math Engine
*Goal: Precision calculation without floating point errors.*

- [x] **7.1 Cart Service**
    - [x] Implement `add_item`, `remove_item`, `update_qty`.
    - [x] Logic: Merge duplicates vs New Line.
    - [x] Logic: Weighted item decimal handling (`0.500` kg).
- [x] **7.2 Calculation Engine**
    - [x] Implement `Decimal` based math (No floats).
    - [x] Calculate `Subtotal`, `LineDiscount`, `CartDiscount`, `Total`.

## 💳 Phase 8: Transaction Processing
*Goal: The core business function.*

- [x] **8.1 Transaction Service**
    - [x] Implement **Atomic Commit** (DB Transaction).
    - [x] Sequence: Save Header -> Save Lines -> Deduct Stock -> Commit.
- [ ] **8.2 Operations**
    - [ ] **Hold Bill:** Serialize cart to "Pending" table.
    - [ ] **Recall Bill:** Restore from Pending.
    - [ ] **Void Bill:** Record void reason.

## 🇱🇰 Phase 9: Sri Lankan Compliance Module
*Goal: Local tax laws.*

- [x] **9.1 Tax Engine (Backward Calc)**
    - [x] Logic: `Shelf Price = Base + VAT + SSCL`.
    - [x] Implement extraction formula for 18% VAT.
    - [x] Implement extraction formula for 2.5% SSCL.
- [ ] **9.2 Invoicing Rules**
    - [ ] Logic: Detect Registered Customer (VAT No).
    - [ ] Output: Switch Receipt format to "Tax Invoice".

## 💵 Phase 10: Payment & Checkout
*Goal: Flexible tender handling.*

- [x] **10.1 Payment UI**
    - [x] Design Payment Dialog (Big Total).
    - [x] "Smart Cash" Buttons (Exact, 1000, 5000).
- [ ] **10.2 Logic**
    - [ ] **Split Payment:** Cash + Card.
    - [ ] **Credit Sale:** Assign to Customer Debt.
    - [ ] **Change Calculation:** Live update.

## 👥 Phase 11: Customer Management (CRM)
*Goal: Repeat business.*

- [ ] **11.1 Customer DB**
    - [ ] CRUD for Customers (Name, Phone, VAT No).
    - [ ] Credit Limit logic.
- [ ] **11.2 Loyalty**
    - [ ] Points Engine (Earn X points per Y spent).
    - [ ] Redemption Logic at checkout.

## ⏲️ Phase 12: Shift Management
*Goal: Cash control and theft prevention.*

- [ ] **12.1 Cash Control**
    - [ ] **Float Entry:** Start of day cash.
    - [ ] **Cash In/Out:** Petty cash recording.
- [ ] **12.2 Reports**
    - [ ] **X-Read:** Mid-shift snapshot.
    - [ ] **Z-Read:** End of day reset & variance calculation.

## 🧾 Phase 13: Receipt Generation
*Goal: Professional physical output.*

- [ ] **13.1 Templating**
    - [ ] Create `ReceiptBuilder` class.
    - [ ] Header (Logo, Address).
    - [ ] Body (Items, Qty, Price).
    - [ ] Footer (Tax breakdown, Thank you message).
- [ ] **13.2 Routing**
    - [ ] Logic to print to Kitchen vs Counter based on Category.

## 📊 Phase 14: Reporting & Analytics
*Goal: Business insights.*

- [ ] **14.1 Dashboard**
    - [ ] Live Sales Ticker.
    - [ ] "Top Movers" Widget.
- [ ] **14.2 Core Reports**
    - [ ] Sales by Date/User/Category.
    - [ ] Inventory Valuation.
    - [ ] Tax Liability Report (Output VAT - Input VAT).
- [ ] **14.3 Export**
    - [ ] Export Table Data to Excel/CSV.

## ⚙️ Phase 15: Settings & Configuration
*Goal: User customizability.*

- [ ] **15.1 Config UI**
    - [ ] Hardware Setup (Select Printer/Scanner).
    - [ ] Business Details (Name, Address, Phone).
    - [ ] Tax Rates configuration.
- [ ] **15.2 Feature Flags**
    - [ ] Toggle features (e.g., Enable Loyalty, Enable Touch Mode).

## 🎨 Phase 16: Theme & Localization
*Goal: Ceylon Byte Branding.*

- [x] **16.1 Theme Engine**
    - [x] Implement `styles.qss`.
    - [ ] Create "Ceylon Night" and "Ceylon Day" themes.
- [ ] **16.2 Localization**
    - [ ] Generate `.ts` files for Qt Linguist.
    - [ ] Translate UI to Sinhala and Tamil.
    - [ ] Implement Runtime Language Switcher.

## 🔄 Phase 17: Data Management
*Goal: Safety and Portability.*

- [ ] **17.1 Backup System**
    - [ ] Manual Backup Button (Zip DB + Images).
    - [ ] Auto-Backup on Exit logic.
- [ ] **17.2 Data Tools**
    - [ ] "Factory Reset" (Clear Transactions, keep Items).
    - [ ] Database Optimizer (`VACUUM`).

## 🌐 Phase 18: Networking & Sync (Future Proofing)
*Goal: Multi-terminal readiness.*

- [ ] **18.1 API Hooks**
    - [ ] Prepare structure for REST API client.
- [ ] **18.2 Sync Worker**
    - [ ] Create background thread for potential cloud sync.

## 🧪 Phase 19: Quality Assurance
*Goal: Bug-free code.*

- [ ] **19.1 Unit Tests**
    - [ ] Test Math Engine (Rounding, Tax).
    - [ ] Test Cart Logic.
- [ ] **19.2 Integration Tests**
    - [ ] Test Database Transactions (Rollback).
- [ ] **19.3 Stress Tests**
    - [ ] Rapid Scan Test (50ms interval).
    - [ ] Large DB Load Test (50k items).

## 🚀 Phase 20: Packaging & Deployment
*Goal: Shipping the product.*

- [ ] **20.1 PyInstaller**
    - [ ] Create `cbpos.spec` file.
    - [ ] Handle hidden imports (SQLAlchemy, PyQt).
    - [ ] Bundle assets (Fonts/Icons).
- [ ] **20.2 Installer (InnoSetup)**
    - [ ] Create `setup.iss` script.
    - [ ] Register Desktop Shortcuts.
- [ ] **20.3 Licensing**
    - [ ] Implement Machine ID generation.
    - [ ] Create License Key verification logic.