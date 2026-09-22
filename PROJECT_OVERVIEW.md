# CB-POS - Complete Project Overview

> Industrial-grade Point of Sale system for Sri Lankan retail markets.
> Built with Python 3.12+ | PyQt6 | SQLAlchemy 2.0 | SQLite | Alembic | ESC/POS printing

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Directory Structure](#2-directory-structure)
3. [Boot Sequence](#3-boot-sequence)
4. [Database Layer](#4-database-layer)
5. [Models](#5-models)
6. [Service Layer](#6-service-layer)
7. [User Interface Layer](#7-user-interface-layer)
8. [Infrastructure Layer](#8-infrastructure-layer)
9. [Reports System](#9-reports-system)
10. [Database Migrations](#10-database-migrations)
11. [Scripts & Utilities](#11-scripts--utilities)
12. [Testing Framework](#12-testing-framework)
13. [Configuration Files](#13-configuration-files)
14. [Critical Business Rules](#14-critical-business-rules)
15. [Architectural Patterns](#15-architectural-patterns)
16. [Performance Optimizations](#16-performance-optimizations)
17. [Security Features](#17-security-features)
18. [Hardware Support](#18-hardware-support)
19. [Internationalization](#19-internationalization)
20. [Network Multi-Terminal Support](#20-network-multi-terminal-support)
21. [Module Interconnections](#21-module-interconnections)
22. [File Counts Summary](#22-file-counts-summary)

---

## 1. Architecture

### Modular MVC Pattern

```
┌─────────────────────────────────────────────────────┐
│                     main.py                         │
│  Fonts → Theme → Reports → MainWindow → Event Loop │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────┐
│              UI Layer (cbpos/ui/)                    │
│  24 Views │ 36 Dialogs │ 12 Widgets │ 2 QSS Themes │
│  LoginView → SalesView → ManagementView → Settings  │
└────────────────────────┬────────────────────────────┘
                         │ Signals/Slots (NO DB calls)
┌────────────────────────┴────────────────────────────┐
│           Service Layer (cbpos/core/services/)      │
│  52 Services: Transaction, Cart, Tax, Stock,        │
│  Auth, Pricing, Receipt, Shift, Report, etc.        │
└────────────────────────┬────────────────────────────┘
                         │ SQLAlchemy Sessions
┌────────────────────────┴────────────────────────────┐
│          Data Layer (cbpos/core/models/)             │
│  26 Models in 1 file │ Document Polymorphism        │
│  Singleton Database │ Alembic Migrations (21)       │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────┐
│        Infrastructure (cbpos/infrastructure/)       │
│  ESC/POS Printer │ Barcode Scanner │ Session Timer  │
│  Resource Loader │ Input Manager                    │
└─────────────────────────────────────────────────────┘
```

**Strict Separation Rules:**

- `cbpos/ui/views/*.py` — Purely for display, layouts, and signal emission. **NO** database calls.
- `cbpos/core/services/*.py` — Purely for business logic, math, and database I/O. **NO** PyQt widgets.
- `cbpos/core/models/` — SQLAlchemy ORM definitions.
- `cbpos/infrastructure/` — Drivers for hardware (printers, scanners) and system utilities.

---

## 2. Directory Structure

```
/CB-POS/
├── main.py                    # Application entry point
├── cbpos.db                   # SQLite database
├── cbpos.spec                 # PyInstaller build specification
├── requirements.txt           # Python dependencies (24 packages)
├── pyproject.toml             # Black & Flake8 configuration
├── alembic.ini                # Alembic migration configuration
├── settings.json              # Runtime settings (auto-generated)
├── settings.json.example      # Example settings template
├── README.md                  # Project documentation
├── CLAUDE.md                  # Development guidelines
├── CHANGELOG.md               # Version history
├── Roadmap.md                 # Feature roadmap
│
├── cbpos/                     # Main application package
│   ├── __init__.py
│   ├── config.py              # Global configuration constants
│   │
│   ├── assets/                # Static resources
│   │   ├── fonts/             # Noto Sans (En, Si, Ta)
│   │   │   ├── Noto_Sans/
│   │   │   ├── Noto_Sans_Sinhala/
│   │   │   └── Noto_Sans_Tamil/
│   │   ├── logo/              # Ceylon Byte branding
│   │   └── badge/             # UI icons
│   │
│   ├── i18n/                  # Internationalization
│   │   ├── __init__.py        # _t(), register/unregister callbacks
│   │   ├── translation_service.py  # Thread-safe TranslationService
│   │   ├── en.json            # English (2,090 keys — complete)
│   │   ├── si.json            # Sinhala translations
│   │   └── ta.json            # Tamil translations
│   │
│   ├── core/                  # Business logic layer
│   │   ├── database.py        # Singleton Database Manager
│   │   ├── models/
│   │   │   └── __init__.py    # All 26 models (single file)
│   │   ├── services/          # 52 business services
│   │   ├── constants/
│   │   │   └── permissions.py # Permission codes
│   │   ├── interfaces/
│   │   │   └── iprinter.py    # Printer interface
│   │   ├── reports/
│   │   │   ├── base_report.py # Abstract report base
│   │   │   ├── registry.py    # Report registry singleton
│   │   │   └── definitions/   # Concrete report implementations
│   │   └── utils/
│   │       └── formatters.py  # Currency/date formatting
│   │
│   ├── infrastructure/        # External systems layer
│   │   ├── resource_loader.py # Font/asset loading
│   │   ├── input_manager.py   # Global keyboard/scanner input
│   │   ├── session_watchdog.py# Inactivity timeout (5 min)
│   │   ├── hardware/
│   │   │   ├── escpos_driver.py  # ESC/POS printer driver
│   │   │   └── scanner.py        # Barcode scanner event filter
│   │   ├── database/
│   │   ├── logging/
│   │   └── repositories/
│   │
│   └── ui/                    # Presentation layer
│       ├── main_window.py     # QStackedWidget navigation
│       ├── views/             # 24 main screens
│       ├── dialogs/           # 36 popup dialogs
│       ├── widgets/           # 12 reusable components
│       ├── styles/            # QSS themes (dark.qss, light.qss)
│       ├── resources/
│       │   ├── icons.py       # QtAwesome icon loader
│       │   └── translations/
│       └── assets/
│
├── alembic/                   # Database migrations
│   ├── env.py                 # Alembic environment config
│   └── versions/              # 21 migration files
│
├── scripts/                   # Utility scripts
│   ├── seed.py                # Database seeding
│   ├── validate_translations.py # i18n param/brace/key validation
│   ├── update_translations.py # i18n string extraction
│   └── debug_db.py            # Database inspection tool
│
├── tests/                     # Test suite (17 files)
│   ├── conftest.py            # pytest config (in-memory DB)
│   ├── unit/                  # Unit tests
│   │   ├── test_transaction_service.py
│   │   ├── test_translation_service.py
│   │   └── ... (15 more)
│   ├── test_logic_layer.py
│   └── test_purchasing.py
│
└── docs/                      # Documentation
    ├── PRD.md                 # Product Requirements Document
    ├── TAX.md                 # Sri Lankan tax guide
    ├── Docs.md                # Technical documentation
    └── onboarding.md
```

---

## 3. Boot Sequence

**File:** `main.py`

| Step | Action | Details |
|------|--------|---------|
| 1 | Qt Message Handler | Filters internal Qt warnings |
| 2 | QApplication Init | Sets app name "CB POS" |
| 3 | Global Input Manager | Installs event filter for keyboard/scanner routing |
| 4 | Font Loading | **CRITICAL** — Loads Noto Sans fonts before any UI |
| 5 | Application Font Set | Forces Noto Sans as default font |
| 6 | Theme Loading | Applies saved theme from ConfigService (default: Dark) |
| 7 | Report Registration | Registers all report classes with ReportRegistry |
| 8 | MainWindow Launch | Creates and shows maximized window |
| 9 | Event Loop | Starts Qt event loop |

---

## 4. Database Layer

**File:** `cbpos/core/database.py`

### Singleton Pattern

```python
class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
```

### Features

- **Dual Mode**: SQLite (standalone) and PostgreSQL (network)
- **Engine Factory**: Creates appropriate engine based on `db_mode` setting
- **Session Management**: Context manager with auto-commit/rollback
- **Connection Pooling**: QueuePool for PostgreSQL (size=10, overflow=20)
- **Optimistic Locking**: `expire_on_commit=False` prevents DetachedInstanceError

### Usage

```python
from cbpos.core.database import Database

db = Database()
with db.get_session() as session:
    product = session.query(Product).filter_by(barcode="123").first()
    # Auto-commits on success, rolls back on exception
```

### Configuration Sources

| Mode | Connection String |
|------|-------------------|
| SQLite | `sqlite:///cbpos.db` |
| PostgreSQL | Built from ConfigService (host, port, dbname, user, password) |

---

## 5. Models

**File:** `cbpos/core/models/__init__.py` — 26 models, single file, SQLAlchemy 2.0 `mapped_column` syntax.

### Authentication & Authorization

| Model | Purpose |
|-------|---------|
| **Role** | RBAC roles (Admin, Manager, Cashier) with `access_level` hierarchy |
| **Permission** | Granular permissions grouped by category (Sales, Inventory, Admin) |
| **User** | PIN-based authentication with role assignment |

### Pricing Engine

| Model | Purpose |
|-------|---------|
| **PriceList** | Customer-specific pricing (Standard, Wholesale, Happy Hour) |
| **PriceListItem** | Product prices per price list |
| **Promotion** | Time-based promotions (PERCENTAGE, FIXED_AMOUNT, BOGO) |

### Document Polymorphism (Joined Table Inheritance)

| Model | Purpose |
|-------|---------|
| **VoidReason** | Standardized void/cancellation reasons |
| **Document** (Base) | Common fields: `document_number`, `type`, `date`, `user_id`, `status`, `void_reason_id` |
| **Sale** (extends Document) | Tax calculations, payment method, customer, refund tracking |
| **Purchase** (extends Document) | Supplier, total cost |

### Core Business Entities

| Model | Purpose |
|-------|---------|
| **Category** | Hierarchical product categories with color coding |
| **Product** | Core inventory item — multilingual names, stock tracking (Decimal 10,3), composite item support, optimistic locking |
| **Customer** | B2B/B2C — credit management, loyalty points, price lists |
| **CustomerContact** | Additional customer contacts |
| **Supplier** | Procurement vendors |

### Transaction Details

| Model | Purpose |
|-------|---------|
| **SaleItem** | Sale line items with discounts |
| **SalePayment** | Split payment support (Cash, Card, Credit) |
| **PurchaseItem** | Purchase order line items |
| **StockMovement** | Complete audit trail (SALE, PURCHASE, ADJUSTMENT, VOID) |
| **CompositeItem** | Bundle/kit definitions (parent-child relationships) |

### Audit & Operations

| Model | Purpose |
|-------|---------|
| **AuditLog** | User actions (LOGIN, LOGOUT, TIMEOUT, TRANSACTION) |
| **InventoryLog** | Stock adjustments with reasons |
| **Shift** | Cashier shift management (start/end cash, variance) |
| **CashMovement** | Safe drops, payouts, cash IN/OUT |
| **SuspendedTransaction** | Hold/recall bills (JSON cart data) |
| **PaymentMethod** | Configurable payment types |

### Design Patterns

- **Polymorphic Documents**: Single sequence for all document types
- **Optimistic Locking**: `Product.version_id` prevents concurrent stock updates
- **Soft Deletes**: `is_active` flags instead of hard deletes
- **Audit Trails**: Every critical action logged to AuditLog
- **Decimal Precision**: All money/quantity fields use `Decimal` (never float)

---

## 6. Service Layer

**Location:** `cbpos/core/services/` — 52 services total.

### Core Transaction Services

| Service | Key Methods | Responsibility |
|---------|-------------|----------------|
| **transaction_service.py** (543 lines) | `process_sale()`, `hold_bill()`, `recall_bill()`, `void_sale()`, `process_refund()` | Atomic sale processing, suspend/resume, void with stock reversal, composite item stock deduction |
| **cart_service.py** | In-memory cart state | Customer-aware pricing, line/cart discounts, price override with audit logging |
| **tax_service.py** | `calculate_taxes()` | Sri Lankan backward tax calculation (VAT 18%, SSCL 2.5% on 50% of revenue) |
| **stock_service.py** | `record_movement()` | Atomic stock updates with movement logging, optimistic locking, balance tracking |

### Authentication & Security

| Service | Responsibility |
|---------|----------------|
| **auth_service.py** | PIN-based auth (SHA-256), session management, audit logging |
| **permission_service.py** | Permission checking decorators, RBAC |

### Inventory Management

| Service | Responsibility |
|---------|----------------|
| **inventory_service.py** | Product CRUD, composite items, low stock alerts, stock adjustment |
| **product_service.py** | Product search (barcode, name, code), weighted barcode parsing |
| **purchase_service.py** | Purchase order processing, auto stock increase, AVCO calculation |

### Financial Services

| Service | Responsibility |
|---------|----------------|
| **shift_service.py** | Open/close cashier shifts, expected vs actual cash variance |
| **cash_control_service.py** | Safe drops, petty cash, cash IN/OUT |
| **payment_service.py** | Split payment handling, credit balance management |

### Customer & Pricing

| Service | Responsibility |
|---------|----------------|
| **customer_service.py** | B2B/B2C management, credit limit enforcement, loyalty points |
| **pricing_service.py** | Multi-tier pricing (base, price list, promotion), time-based validation |
| **price_list_service.py** | Customer-specific price lists, bulk updates |
| **promotion_service.py** | Time-window promotions, day-of-week restrictions, discount types |

### Hardware Integration

| Service | Responsibility |
|---------|----------------|
| **receipt_service.py** | Receipt text/image generation, multilingual support |
| **receipt_builder.py** | ESC/POS command generation |
| **printer_service.py** | Printer queue management, USB/Network support |
| **scale_service.py** | Scale barcode parsing (prefix "20"), weight extraction |

### Configuration & System

| Service | Responsibility |
|---------|----------------|
| **config_service.py** | JSON-based settings persistence (76 defaults) |
| **theme_service.py** | QSS theme loading, change callbacks |
| **language_service.py** | i18n support (EN, SI, TA) |
| **migration_service.py** | Alembic migration orchestration |
| **backup_service.py** | Database backup/restore, auto-backup on close |
| **maintenance_service.py** | Database maintenance and optimization |
| **update_service.py** | Application update checking |

### Reports & Export

| Service | Responsibility |
|---------|----------------|
| **report_service.py** | Report generation orchestration, filter application |
| **export_service.py** | Excel/CSV/PDF export (pandas, xlsxwriter, xhtml2pdf) |
| **dashboard_service.py** | Today's sales, top products, low stock |

### Data & Import/Export

| Service | Responsibility |
|---------|----------------|
| **import_service.py** | CSV/bulk data import |
| **data_export_service.py** | Data export orchestration |
| **label_service.py** | Product label generation |
| **statement_service.py** | Customer statement generation |

### Document & CRM

| Service | Responsibility |
|---------|----------------|
| **document_service.py** | Document number sequencing |
| **document_browser_service.py** | Document search and browsing |
| **proforma_service.py** | Proforma invoice management |
| **customer_credit_service.py** | Credit book and balance management |
| **supplier_payable_service.py** | Supplier payable tracking |

### Other Services

| Service | Responsibility |
|---------|----------------|
| **email_service.py** | SMTP email sending |
| **invoice_service.py** | A4 invoice generation |
| **user_service.py** | User CRUD |
| **supplier_service.py** | Supplier management |
| **category_service.py** | Category tree management |
| **unit_service.py** | Unit of measure management |
| **logging_service.py** | Application logging |
| **error_log_service.py** | Error tracking and reporting |
| **license_service.py** | License validation |
| **scheduler_service.py** | Background task scheduling |
| **sound_service.py** | UI sound feedback |
| **hardware_test_service.py** | Printer/scanner diagnostics |
| **stock_count_service.py** | Stock take/counting operations |

---

## 7. User Interface Layer

### 7.1 MainWindow

**File:** `cbpos/ui/main_window.py`

**Navigation (QStackedWidget):**

| Index | View | Purpose |
|-------|------|---------|
| 0 | LoginView | PIN authentication |
| 1 | SalesView | Main POS interface (default after login) |
| 2 | ManagementView | Inventory, customers, reports |
| 3 | SettingsView | Application configuration |

**Key Components:**

- **BarcodeScanner**: Global event filter routes scans to active view
- **SessionWatchdog**: 5-minute inactivity timeout → auto-logout
- **Side Menu**: Animated slide-out (300ms `QPropertyAnimation`)
- **Fullscreen Toggle**: F11/Escape shortcuts

**Navigation Flow:**
Login → SalesView → Management/Settings (via side menu) → Back returns to last view

### 7.2 Views (24 Files)

| View | File | Description |
|------|------|-------------|
| **LoginView** | `login_view.py` | PIN pad entry, `login_success(user)` signal |
| **SalesView** | `sales_view.py` | Search modes (ALL/BARCODE/CODE/NAME), cart table, context menu, autocomplete, barcode processing |
| **ManagementView** | `management_view.py` | Tab-based (Inventory, Customers, Purchases, Reports, Users, Documents) |
| **SettingsView** | `settings_view.py` | Category-based settings, live theme preview |
| **DashboardView** | `dashboard_view.py` | Real-time KPIs, low stock alerts |
| **InventoryView** | `inventory_view.py` | Product CRUD, stock adjustment, category assignment |
| **CustomerView** | `customer_view.py` | Customer management, credit tracking |
| **CreditBookView** | `credit_book_view.py` | Customer credit ledger and balance tracking |
| **PurchaseView** | `purchase_view.py` | Purchase orders, supplier selection, auto stock increase |
| **HistoryView** | `history_view.py` | Transaction history, void/refund capabilities |
| **DocumentView** | `document_view.py` | Unified document browser (sales, purchases, credit notes) |
| **UserView** | `user_view.py` | User CRUD, role assignment, PIN management |
| **AdminToolsView** | `admin_tools_view.py` | Admin utilities and system tools |
| **PricelistView** | `pricelist_view.py` | Price list management, bulk updates |
| **PromotionView** | `promotion_view.py` | Promotion CRUD, time-window configuration |
| **ReorderView** | `reorder_view.py` | Low stock report, purchase order suggestions |
| **StockTakeView** | `stock_take_view.py` | Physical stock count and reconciliation |
| **PaymentMethodsView** | `payment_methods_view.py` | Payment method configuration |
| **DataSafetyView** | `data_safety_view.py` | Backup/restore and data management |
| **ReportViewer** | `reports/report_viewer.py` | Pandas DataFrame display, export |
| **SettingsPages** | `settings_pages.py` | Individual settings page implementations |
| **PandasModel** | `pandas_model.py` | QAbstractTableModel for DataFrame display |
| **FilterWidget** | `reports/filter_widget.py` | Report filter input components |

### 7.3 Dialogs (36 Files)

**Payment & Checkout:**

| Dialog | Purpose |
|--------|---------|
| `payment_dialog.py` | Split payment UI (Cash, Card, Credit) |
| `receipt_options_dialog.py` | Print/Email receipt options |
| `receipt_preview_dialog.py` | Receipt preview before print |
| `receipt_reprint_dialog.py` | Reprint previous receipt |
| `receive_payment_dialog.py` | Receive credit payment |
| `refund_dialog.py` | Process refund/return |
| `quantity_dialog.py` | Quantity input for items |

**Customer:**

| Dialog | Purpose |
|--------|---------|
| `customer_selection_dialog.py` | Customer lookup |
| `customer_quick_add.py` | Fast customer creation |
| `customer_editor.py` | Full customer form |
| `customer_statement_dialog.py` | Customer statement generation |
| `supplier_payment_dialog.py` | Supplier payment recording |

**Inventory:**

| Dialog | Purpose |
|--------|---------|
| `product_editor.py` | Product CRUD form |
| `category_dialog.py` | Category creation |
| `category_tree_dialog.py` | Hierarchical category selector |
| `category_manager.py` | Category tree management |
| `stock_adjustment_dialog.py` | Manual stock adjustment |
| `stock_history_dialog.py` | Product movement history |
| `valuation_dialog.py` | Inventory valuation |
| `csv_import_dialog.py` | CSV data import |
| `unit_manager.py` | Unit of measure management |
| `label_print_dialog.py` | Product label printing |
| `label_preview_dialog.py` | Label print preview |

**Sales & Documents:**

| Dialog | Purpose |
|--------|---------|
| `discount_dialog.py` | Line/cart discount entry |
| `advanced_search_dialog.py` | Multi-criteria product search |
| `proforma_dialog.py` | Proforma invoice management |
| `data_export_dialog.py` | Data export configuration |

**Cash Management:**

| Dialog | Purpose |
|--------|---------|
| `shift_closing_dialog.py` | Cash count and variance |
| `cash_movement_dialog.py` | Safe drop/payout |

**System & Security:**

| Dialog | Purpose |
|--------|---------|
| `manager_override_dialog.py` | Permission elevation |
| `permission_dialog.py` | Permission assignment |
| `profile_dialog.py` | User profile editor |
| `setup_wizard.py` | First-run setup wizard |
| `shortcuts_help_dialog.py` | Keyboard shortcuts reference |
| `update_dialog.py` | Application update notification |

### 7.4 Widgets (12 Reusable Components)

| Widget | Purpose |
|--------|---------|
| `side_menu.py` | Animated slide-out navigation |
| `order_bar.py` | Order summary footer (item count, total) |
| `action_panel.py` | Quick action buttons |
| `info_card.py` | Dashboard KPI cards |
| `custom_widgets.py` | Custom QLineEdit, QTableWidget |
| `denomination_widget.py` | Cash denomination counter |
| `pagination_widget.py` | Table pagination controls |
| `receipt_preview_widget.py` | Live receipt preview renderer |
| `charts.py` | Dashboard chart components |
| `loading_overlay.py` | Loading spinner overlay |

### 7.5 Themes

**Files:** `cbpos/ui/styles/dark.qss` (1,529 lines) | `cbpos/ui/styles/light.qss` (1,574 lines)

**Ceylon Byte Color Palette (Dark Theme):**

| Role | Color | Hex |
|------|-------|-----|
| Background | Navy | `#001F3F` |
| Panel/Input | Dark Blue | `#003366` |
| Accent/Focus | Cyan | `#00BCEB` |
| Success/Pay | Neon Green | `#39FF14` |
| Destructive/Void | Red | `#FF4136` |

**Theme Switching:** ConfigService stores current theme → `ThemeService.apply_theme()` reloads QSS → callbacks update logo variants.

---

## 8. Infrastructure Layer

### 8.1 Resource Management

**File:** `cbpos/infrastructure/resource_loader.py`

- Recursively loads all `.ttf`/`.otf` from `cbpos/assets/fonts/`
- Priority: Noto Sans > First loaded > Segoe UI (fallback)
- Returns primary font family for QSS usage
- **Must be called BEFORE any UI initialization**

### 8.2 Hardware Integration

**ESC/POS Printer Driver** (`cbpos/infrastructure/hardware/escpos_driver.py`):

- **MockPrinter**: Development mode (console output)
- **ESCPOSDriver**: Real USB/Network thermal printers via `python-escpos`
- Command types: text, image, barcode, feed, cut
- Cash drawer kick via `cashdraw(2)`
- **PrintWorker**: QThread for async printing (prevents UI freeze)

**Barcode Scanner** (`cbpos/infrastructure/hardware/scanner.py`):

- Global event filter on QApplication
- Detects rapid keystroke bursts (scanner vs keyboard)
- 50ms timeout for burst detection
- Emits `barcode_scanned(str)` signal
- MainWindow routes to active view's `process_barcode_external()`

### 8.3 Session Management

**Session Watchdog** (`cbpos/infrastructure/session_watchdog.py`):

- Monitors keyboard, mouse, touch events
- 5-minute inactivity timer
- Emits `session_expired` → MainWindow.logout()
- Logs timeout to AuditLog

**Input Manager** (`cbpos/infrastructure/input_manager.py`):

- Global input coordinator (event filter)
- Scanner buffer accumulation
- Enter key routing (decentralized to views)

---

## 9. Reports System

### Architecture

```
BaseReport (ABC)
  ├── id, name, category
  ├── get_filter_definitions()
  └── generate() → pandas.DataFrame

ReportRegistry (Singleton)
  └── Stores all reports by category

Registration: register_all_reports() called in main.py
```

### Report Definitions

| File | Reports |
|------|---------|
| `sales_reports.py` | Daily/weekly/monthly sales |
| `inventory_reports.py` | Stock levels, valuation |
| `financial_reports.py` | Profit/loss, tax summaries |
| `cash_flow_report.py` | Cash movements |
| `audit_reports.py` | User activity logs |

### Output

- All reports return `pandas.DataFrame`
- Export formats: Excel (xlsxwriter), CSV, PDF (xhtml2pdf)
- UI: `report_viewer.py` displays DataFrame in QTableView

---

## 10. Database Migrations

**Tool:** Alembic | **Config:** `alembic.ini` → `alembic/env.py`

- `render_as_batch=True` for SQLite ALTER TABLE support
- Imports `cbpos.core.models.Base` for autogenerate

### Migration History (21 files)

| Migration | Description |
|-----------|-------------|
| `50ffff66bd6a` | Initial migration — base schema |
| `1195fb9ad667` | Extended models and document polymorphism |
| `b8a7c1d34f92` | Optimistic locking (`version_id`) |
| `aa29f0271e58` | Advanced inventory (composite items) |
| `aa9e82761ac2` | Customer B2B fields and pricing |
| + 16 more | Incremental schema changes (shift management, cash movements, payment methods, supplier payables, etc.) |

### Commands

```bash
alembic upgrade head                           # Apply all
alembic revision --autogenerate -m "msg"       # Generate new
```

---

## 11. Scripts & Utilities

| Script | Purpose |
|--------|---------|
| `scripts/seed.py` | Full database reset + seed data (users, products, categories, suppliers, permissions, roles, payment methods) |
| `scripts/validate_translations.py` | Translation validation — checks format params, malformed braces, missing keys. Supports `--strict` for CI |
| `scripts/update_translations.py` | i18n string extraction |
| `scripts/debug_db.py` | Database inspection tool |
| `scripts/debug_conftest.py` | Test configuration debugging |
| `scripts/verify_phase4.py` | Manual testing script |

### Seed Data (via `seed.py`)

| Entity | Data |
|--------|------|
| **Users** | admin/1234, manager/5678, cashier/0000 |
| **Roles** | Admin (lvl 9), Manager (lvl 5), Cashier (lvl 1) |
| **Categories** | Biscuits, Beverages, Essentials, Vegetables |
| **Suppliers** | Munchee Distributors, City Imports |
| **Products** | Munchee Crackers, Highland Milk, etc. |
| **Price Lists** | Standard, Wholesale, Happy Hour |
| **Void Reasons** | MISTAKE, RETURN, DAMAGED, etc. |
| **Payment Methods** | Cash, Card, Credit |

---

## 12. Testing Framework

**Config:** `tests/conftest.py`

- **In-Memory SQLite**: `sqlite:///:memory:` for all tests
- **Session Fixture**: Transactional tests with automatic rollback
- **Patches**: `Database.SessionLocal` redirected to test session
- **Pytest-Qt**: `qapp` fixture for PyQt6 tests

### Test Files (17 files)

| File | Coverage |
|------|----------|
| `test_transaction_service.py` | Sale processing, void, refund |
| `test_translation_service.py` | Fallback chain, interpolation, callbacks, thread safety |
| `test_logic_layer.py` | Business logic validation |
| `test_purchasing.py` | Purchase flow tests |
| + 13 more | Cart, tax, stock, pricing, customer, permissions, etc. |

### Running Tests

```bash
export QT_QPA_PLATFORM=offscreen
python -m pytest tests/unit/ -v
python -m pytest tests/unit/test_transaction_service.py -v
python -m pytest tests/unit/test_transaction_service.py::TestTransactionService::test_create_sale -v
```

---

## 13. Configuration Files

### requirements.txt (24 packages)

| Category | Packages |
|----------|----------|
| UI | PyQt6>=6.7.0 |
| ORM | SQLAlchemy>=2.0.30, alembic>=1.13.1 |
| Database | psycopg2-binary (PostgreSQL) |
| Validation | pydantic>=2.7.0 |
| Printing | python-escpos>=3.1 |
| Reports | reportlab, pandas, xlsxwriter, xhtml2pdf |
| Testing | pytest, pytest-qt |
| Code Quality | black, flake8, pre-commit |

### pyproject.toml

- Black: 120 char line length, Python 3.12 target
- Flake8: max 120 chars, ignore E203 (black compatibility)

### settings.json (76 configurable settings)

- Shop details, tax rates, printer config
- Database mode (standalone/network)
- Feature flags (loyalty)
- Document numbering formats

### cbpos.spec (PyInstaller)

- Bundles: assets, styles, alembic
- Hidden imports: SQLAlchemy internals, escpos
- Output: Single-file executable

---

## 14. Critical Business Rules

### Money Handling

**ALWAYS `Decimal`, NEVER `float`.**

- All currency fields: `Numeric(10, 2)`
- All quantity fields: `Numeric(10, 3)` (supports 1.250 kg)

### Sri Lankan Tax (Backward Calculation from MRP)

Shelf prices are MRP (Maximum Retail Price) and include tax.

```python
from decimal import Decimal

# VAT (18%)
vat_base = mrp / Decimal("1.18")
vat_amount = mrp - vat_base

# SSCL (2.5% on 50% of revenue)
sscl_amount = (mrp * Decimal("0.5")) * Decimal("0.025")

# Net Revenue
net_revenue = mrp - vat_amount - sscl_amount
```

### Inventory Costing — Weighted Average Cost (AVCO)

```python
new_cost = (old_cost * old_qty + purchase_cost * purchase_qty) / (old_qty + purchase_qty)
```

### Stock Movement Tracking

- Every stock change → `StockMovement` record
- Types: `SALE`, `PURCHASE`, `ADJUSTMENT`, `RETURN`, `VOID`
- Balance snapshot stored after each movement

### Composite Items

- Parent product has zero stock
- Sale deducts from child products
- Example: "Meal Deal" = Burger + Fries + Drink

### Permissions

- `@permission_required('sales.void')` decorator
- Roles have `access_level` (1-9)
- Permission groups: Sales, Inventory, Reports, Admin

### Document Polymorphism

- All transactional documents inherit from `Document`
- Unified numbering: `REC-XXXXXXXX`, `GRN-XXXXXXXX`, `CN-XXXXXXXX`
- Void tracking via `void_reason_id`

---

## 15. Architectural Patterns

### Singleton Patterns

- `Database()` — Single DB engine instance
- `ReportRegistry()` — Central report repository
- `AuthService._current_user` — Session state

### Repository Pattern (Emerging)

- `cbpos/infrastructure/repositories/` directory exists but is currently empty
- Services access models directly

### Dependency Injection

- Services receive session parameter where needed
- Example: `StockService.record_movement(..., session=session)`

### Event-Driven Architecture

- Qt Signals/Slots for view communication
- `barcode_scanned` signal from scanner to views
- `login_success`, `logout_requested` signals

### Command Pattern

- PrintWorker job queue: `add_job(type, data)`
- Receipt commands: `[{type: 'text', val: '...'}]`

---

## 16. Performance Optimizations

| Optimization | Details |
|--------------|---------|
| **Eager Loading** | `joinedload()` to prevent N+1 queries |
| **Optimistic Locking** | `version_id` on Product prevents concurrent updates |
| **Connection Pooling** | PostgreSQL mode uses QueuePool (size=10, overflow=20) |
| **Async Printing** | PrintWorker QThread prevents UI freeze |
| **In-Memory Cart** | CartService holds state, no DB writes until checkout |
| **Index Strategy** | Unique indexes on barcode, phone, email for fast lookups |

---

## 17. Security Features

| Feature | Implementation |
|---------|---------------|
| **PIN Authentication** | SHA-256 hashing (not plain text) |
| **RBAC** | 3-tier access control (Admin, Manager, Cashier) |
| **Audit Logging** | All critical actions logged with user_id, timestamp |
| **Session Timeout** | 5-minute inactivity auto-logout |
| **Permission Checks** | Method-level decorators enforce access control |
| **Manager Override** | Elevate permissions for specific actions |
| **Void Reasons** | Mandatory reason codes for transaction cancellations |

---

## 18. Hardware Support

### Printers

- USB Thermal (via VID:PID)
- Network Thermal (via IP address)
- ESC/POS command support
- Cash drawer kick (pulse pin 2)

### Barcode Scanners

- USB HID (keyboard emulation)
- Global event filter captures rapid input
- Prefix detection for scale barcodes (prefix "20")

### Scales

- Barcode format: `20PPPPPWWWWW` (P=product code, W=weight)
- Configurable decimal places

---

## 19. Internationalization

### Supported Languages

| Language | Code | Font | Translation Status |
|----------|------|------|--------------------|
| English | `en` | Noto Sans | Complete (2,090 keys) |
| Sinhala | `si` | Noto Sans Sinhala | 97%+ translated (2,032/2,090 keys) |
| Tamil | `ta` | Noto Sans Tamil | 97%+ translated (2,030/2,090 keys) |

### Architecture

**Translation Service** (`cbpos/i18n/translation_service.py`):

- Thread-safe singleton with `threading.Lock`
- Dot-notation key lookup: `_t("login.title")` → "Login" / "පිවිසුම" / "உள்நுழைவு"
- Fallback chain: Current language → English → raw key
- `{parameter}` interpolation: `_t("common.items", count=5)` → "Items: 5"
- `translate_in(lang, key)` for language-specific lookup without switching (used for receipts)
- WeakMethod callbacks prevent memory leaks on Qt widget destruction
- Live language switching — no restart required

**JSON Files** (`cbpos/i18n/en.json`, `si.json`, `ta.json`):

- 70 sections, 2,090 keys (English complete; Sinhala/Tamil 97%+ translated)
- Flat or nested JSON, flattened to dot notation at load time
- Keys starting with `_` are metadata (skipped)

**UI Integration Pattern:**

```python
from cbpos.i18n import _t, register_language_callback, unregister_language_callback


class MyView(QWidget):
    def __init__(self):
        super().__init__()
        self._init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def retranslate_ui(self):
        self._title.setText(_t("my_view.title"))
```

**Validation** (`scripts/validate_translations.py`):

- Checks format parameters preserved across translations (`{error}`, `{name}`, etc.)
- Detects malformed braces (mismatched `{` and `}`)
- Reports missing keys per language
- `--strict` mode exits with code 1 for CI integration

### Product Multilingual Names

- Product model: `name_en`, `name_si`, `name_ta`
- Receipt printing: Image mode for Unicode (Sinhala/Tamil)
- Independent receipt language setting (print in different language than UI)

---

## 20. Network Multi-Terminal Support

### Database Modes

| Mode | Backend | Use Case |
|------|---------|----------|
| Standalone | SQLite (`cbpos.db`) | Single terminal |
| Network | PostgreSQL | Multi-terminal |

### Configuration

- Host, port, database name, user, password in `settings.json`
- Connection testing via `Database.test_connection()`
- Migration service handles database mode switching

### Concurrency Handling

- Optimistic locking on Product (`version_id`)
- `StaleDataError` triggers transaction retry
- Terminal ID in audit logs

---

## 21. Module Interconnections

```
main.py
  ├── ResourceLoader.load_fonts()
  ├── ThemeService.apply_theme()
  ├── register_all_reports()
  └── MainWindow
        ├── BarcodeScanner (global)
        ├── SessionWatchdog (global)
        └── QStackedWidget
              ├── LoginView
              │     └── AuthService.verify_pin()
              ├── SalesView
              │     ├── CartService (in-memory)
              │     ├── ProductService.get_by_barcode()
              │     ├── PricingService.calculate_price()
              │     └── TransactionService.process_sale()
              │           ├── TaxService.calculate_taxes()
              │           ├── StockService.record_movement()
              │           ├── ReceiptService.build_receipt()
              │           └── PrintWorker (QThread)
              │                 └── ESCPOSDriver
              ├── ManagementView
              │     ├── InventoryView → InventoryService
              │     ├── CustomerView → CustomerService
              │     ├── PurchaseView → PurchaseService → StockService
              │     └── ReportViewer
              │           ├── ReportRegistry.get_report_by_id()
              │           └── ExportService (Excel/PDF)
              └── SettingsView
                    └── ConfigService (settings.json)
```

---

## 22. File Counts Summary

| Component | Count |
|-----------|-------|
| Python files | 230 |
| Total lines of code | ~43,000 |
| Core services | 52 |
| UI views | 24 |
| UI dialogs | 36 |
| UI widgets | 12 |
| Database models | 26 (in 1 file) |
| Report definitions | 9 |
| Alembic migrations | 21 |
| Test files | 17 |
| Translation keys | 1,827 (67 sections) |
| QSS theme lines | 3,103 (Dark: 1,529, Light: 1,574) |
| Configurable settings | 76 |
| Dependencies | 24 packages |
