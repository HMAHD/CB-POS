# DOCUMENT 1: SOFTWARE ARCHITECTURE DOCUMENT (SAD)

**Project:** CB POS (Ceylon Byte Point of Sale)
**Version:** 1.0
**Status:** Approved

## 1\. Architectural Pattern: MVCS (Model-View-Controller-Service)

We are using a modified MVC pattern optimized for PyQt6’s Signal/Slot mechanism.

  * **Model (Data Layer):** `SQLAlchemy` ORM classes. Pure Python. Zero UI logic.
  * **View (Presentation Layer):** `PyQt6` Widgets. Dumb components that only display data and emit signals (e.g., `btn_pay.clicked`).
  * **Controller (Logic Layer):** Connects Views to Services. Handles input signals (e.g., "Pay Button Clicked" -\> Call `PaymentService`).
  * **Service (Business Layer):** The heavy lifters. Contains pure business logic (Tax Math, Cart Rules, Hardware Calls). *This is what makes the system "Industrial"—logic is isolated from the GUI.*

## 2\. System Context & Concurrency

  * **Main Thread (GUI):** Handles UI rendering and user input only. **Strict Rule:** No database writes or hardware calls on the Main Thread.
  * **Worker Threads (`QThread`):**
      * `PrinterWorker`: Handles ESC/POS commands (prevents UI freeze during printing).
      * `ScannerWorker`: Listens for HID/Serial input.
      * `SyncWorker`: Background cloud synchronization.

## 3\. Directory Structure (The "Standard")

```text
cbpos/
├── main.py                   # Application Entry Point (Bootstrapper)
├── config.py                 # ENV Variables, Constants, Feature Flags
├── assets/                   # Icons (.svg), Fonts (.ttf), Sounds
├── core/                     # THE BRAINS (Business Logic)
│   ├── database.py           # DB Connection & Session Management
│   ├── models.py             # SQLAlchemy Tables (User, Product, Sale)
│   ├── services/             # Pure Python Logic
│   │   ├── cart_service.py   # Add/Remove, Totals, Discounts
│   │   ├── tax_service.py    # Sri Lankan SSCL/VAT Backward Calc
│   │   └── auth_service.py   # PIN Hashing, Permissions
│   └── signals.py            # Global QtSignals (App-wide events)
├── infrastructure/           # THE HANDS (Hardware/IO)
│   ├── printer.py            # ESC/POS Driver abstraction
│   ├── scanner.py            # PyUSB / Keyboard Hook logic
│   └── logger.py             # Rotating File Logger (Error Tracking)
├── ui/                       # THE FACE (PyQt6)
│   ├── theme.qss             # CSS-like Styling (Navy/Cyan/Green)
│   ├── windows/              # Main Screens (MainWindow, LoginWindow)
│   ├── widgets/              # Reusable (Numpad, ProductTile, CartRow)
│   └── dialogs/              # Popups (PaymentDialog, ErrorDialog)
└── tests/                    # THE SAFETY NET
    ├── unit/                 # Math/Logic tests
    └── integration/          # DB/Hardware tests
```

-----

# DOCUMENT 2: DATABASE DESIGN SPECIFICATION (DDS)

**Engine:** SQLite (Local) / PostgreSQL (Server)
**ORM:** SQLAlchemy 2.0

## 1\. Naming Conventions (Industrial Standard)

  * **Tables:** Plural, snake\_case (e.g., `sales_transactions`, `inventory_logs`).
  * **Primary Keys:** `id` (BigInteger, Autoincrement).
  * **Foreign Keys:** `parent_id` (e.g., `category_id`, `cashier_id`).
  * **Timestamps:** Every table must have `created_at` (UTC) and `updated_at`.

## 2\. Core Schema Definitions

### Table: `products`

*The inventory master. Supports weighted items and variants.*

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | |
| `barcode` | String(50) | Unique, Index | The scan key. |
| `name_en` | String(100) | Not Null | English Name. |
| `name_si` | String(100) | Nullable | Sinhala Name. |
| `price_mrp` | Decimal(10,2)| Not Null | **Tax Inclusive** Selling Price. |
| `cost_price` | Decimal(10,2)| Not Null | For Profit Calculation. |
| `stock_qty` | Decimal(10,3)| Not Null | Supports `0.500` kg. |
| `is_weighted`| Boolean | Default False| If True, prompts for weight. |
| `is_active` | Boolean | Default True | Soft delete flag. |

### Table: `sales_transactions`

*The header for every sale.*

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | |
| `receipt_no` | String(20) | Unique | Format: `POS01-20231025-001`. |
| `cashier_id` | Integer | FK(users) | Who made the sale. |
| `total_gross`| Decimal(12,2)| Not Null | Total Collected (MRP). |
| `tax_vat` | Decimal(10,2)| Not Null | **Computed Backward** (18%). |
| `tax_sscl` | Decimal(10,2)| Not Null | **Computed Backward** (2.5%). |
| `status` | Enum | 'COMPLETED', 'VOID', 'HOLD' | Transaction State. |
| `sync_status`| Enum | 'PENDING', 'SYNCED' | Cloud Sync State. |

### Table: `sales_items`

*The individual lines in a receipt. Must snapshot data.*

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK | |
| `sale_id` | Integer | FK(sales) | |
| `product_id` | Integer | FK(products)| |
| `qty` | Decimal(10,3)| Not Null | |
| `unit_price` | Decimal(10,2)| Not Null | **Snapshot** of MRP at moment of sale. |
| `line_total` | Decimal(12,2)| Not Null | `qty * unit_price`. |

-----

# DOCUMENT 3: MASTER TEST PLAN (MTP)

**Framework:** `pytest` (Logic) + `pytest-qt` (GUI Interaction)
**Coverage Goal:** 90% Business Logic, 100% Critical Paths (Money/Stock).

## 1\. Testing Strategy (The "Shift-Left" Approach)

We do not wait until the end to test. We test **modules** as we build them.

### Level 1: Unit Testing (The "Money Math")

*Focus: Does the math work?*

  * **Test Case 01: Backward Tax Calculation:**
      * Input: Sale of Rs. 1000.
      * Expected: VAT = 152.54, SSCL = 12.50 (approx), Net = 834.96.
      * *Pass Criteria: Accurate to 2 decimal places.*
  * **Test Case 02: Weighted Quantity:**
      * Input: 0.500kg @ Rs. 200/kg.
      * Expected: Line Total = Rs. 100.
  * **Test Case 03: Cart Logic:**
      * Action: Scan same item twice.
      * Expected: 1 Line Item, Qty = 2 (Not 2 Line Items).

### Level 2: Integration Testing (Hardware Simulation)

*Focus: Does the code handle hardware failure?*

  * **Test Case 04: Printer Disconnect:**
      * Action: Unplug printer, click Pay.
      * Expected: App **must not crash**. Show "Printer Error" toast, save sale, log error.
  * **Test Case 05: Scanner Input:**
      * Action: Simulate rapid keyboard input (50ms interval).
      * Expected: App detects "Scanner Mode" vs "Manual Typing".

### Level 3: User Acceptance Testing (UAT - The "Cashier" Test)

*Focus: Is it usable?*

  * **Test Case 06: Mouse-Free Sale:**
      * Action: Complete a sale (Scan -\> Pay -\> Enter Amount -\> Confirm) using **ONLY** the keyboard.
      * *Pass Criteria: Zero mouse clicks required.*
  * **Test Case 07: Power Failure (The Acid Test):**
      * Action: Kill the process (`Alt+F4`) immediately after hitting "Pay".
      * Expected: Upon restart, Database must be consistent (Either Sale exists AND Stock deducted, OR Neither). No "Half-Saved" records.

