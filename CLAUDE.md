# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

CB-POS is a high-performance, industrial-grade Point of Sale system for Sri Lankan retail markets. Built with Python 3.12+ and PyQt6, it provides zero-latency checkout, keyboard-first design, and offline-first SQLite database operations.

**Tech Stack:** Python 3.12+ | PyQt6 | SQLAlchemy 2.0 | SQLite | Alembic | ESC/POS printing | Inno Setup (Windows installer)

**License:** GNU General Public License v3.0 (GPLv3) — free and open source with corresponding source for every release.

**Codebase:** ~54 services, 38 dialogs, 21 views, 13 widgets, 21 migrations, 13 test files

## Development Commands

### Environment Setup (Required First)
```bash
# Install uv (https://docs.astral.sh/uv/) if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/Mac
# powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows

# Install dependencies (creates .venv, installs exact versions from uv.lock)
uv sync
```
Dependencies and their version constraints live in `pyproject.toml` (`[project.dependencies]` for runtime, `[dependency-groups]` for `dev`/`build` tools) — `uv.lock` pins the exact resolved versions and is committed to git. Run `uv add <package>` to add a runtime dependency, `uv add --group dev <package>` for a dev-only tool, or `uv add --group build <package>` for packaging-only tools, then commit the updated `pyproject.toml` and `uv.lock` together.

### Database Initialization
```bash
# Recommended for development (drops tables + creates fresh DB + sample data)
uv run python scripts/seed.py

# Alternative: Alembic migrations (for existing databases only)
uv run alembic upgrade head
```

**Seed Data:** Admin (`admin`/`1234`), Manager (`manager`/`5678`), Cashier (`cashier`/`0000`), 80+ products, 15 customers, 8 suppliers, 30+ sales, permissions, roles, and more.

### Running the Application
```bash
uv run python main.py
```

### Code Quality (Always Run Before Committing)
```bash
# Run all pre-commit hooks (Ruff linter + formatter)
uv run pre-commit run --all-files

# Individual checks
uv run ruff check .              # Lint check
uv run ruff check --fix .        # Lint + auto-fix
uv run ruff format --check .     # Format check
uv run ruff format .             # Auto-format
```

**Formatting Standards:**
- Ruff: 120 character line length, target Python 3.12, Black-compatible formatting
- Linting: Pyflakes (F) + pycodestyle (E, W) + isort (I) + bugbear (B) + pyupgrade (UP) + more. Config in `pyproject.toml`

### Running Tests
```bash
# Set platform for headless environments
export QT_QPA_PLATFORM=offscreen

# Fast loop while working: domain + guardrail layers (~15 s)
uv run python -m pytest -m "domain or guardrails" -q -n auto

# Full suite: all four layers (~6 min parallel); once per batch, and in CI
uv run python -m pytest -q -n auto

# Single process (when debugging one failure)
uv run python -m pytest -v

# Run specific test file
uv run python -m pytest tests/domain/test_transaction_service.py -v

# Run specific test
uv run python -m pytest tests/domain/test_transaction_service.py::TestTransactionService::test_create_sale -v
```

**Layers** (`tests/<layer>/`, auto-marked by `tests/conftest.py`; a test outside a layer folder fails collection):
- `domain`: service behaviour through public interfaces on the in-memory DB
- `guardrails`: codebase-wide static rules (AST checks)
- `ui`: pytest-qt flows (wiring, keyboard, enabled state, permissions). Never colours or pixel sizes
- `integration`: two-machine sync, PostgreSQL, real threads

New regression tests go into the existing file for that service or screen, not a new file per issue. See `docs/remediation/TEST_ARCHITECTURE.md`.

**Note:** Tests require Qt libraries (`libEGL`, `libxkbcommon`, etc. on Linux). Tests use in-memory SQLite database configured via conftest.py.

### Building & Packaging
```bash
# Build PyInstaller executable (installs the `build` dependency-group first)
uv sync --locked --no-dev --group build
uv run pyinstaller cbpos.spec
# Output: dist/cbpos.exe

# Build Windows installer (requires Inno Setup 6 on Windows)
iscc /DMyAppVersion=1.3.0 installer/cbpos.iss
# Output: dist/installer/CBPOSSetup-1.3.0.exe
```

## Architecture

### Modular MVC Pattern
**DO NOT mix business logic with UI code.**

- **`cbpos/ui/views/*.py`**: Purely for display, layouts, and signal emission. **NO** database calls here.
- **`cbpos/ui/dialogs/*.py`**: Modal dialogs (payment, refund, sale history, setup wizard, etc.). **NO** database calls here.
- **`cbpos/ui/widgets/*.py`**: Reusable UI components (side menu, action panel, order bar, product grid, etc.).
- **`cbpos/core/services/*.py`**: Purely for business logic, math, and database I/O. **NO** PyQt widgets here.
- **`cbpos/core/models/__init__.py`**: All SQLAlchemy ORM definitions (single file).
- **`cbpos/core/constants/`**: Permission codes, status enums, etc.
- **`cbpos/core/utils/`**: Formatters, permission helpers, validators.
- **`cbpos/infrastructure/`**: Drivers for Hardware (Printers, Scanners), Logging, Session Watchdog.
- **`cbpos/i18n/`**: Translation system with JSON files (en.json, si.json, ta.json).

### Application Startup Flow (`main.py`)

1. `ensure_data_dir()` — Create data directory, migrate legacy data from install dir to AppData if needed
2. Single-instance check via `QtSingleApplication` / local socket (`cbpos_app_socket`)
3. `setup_logging()` — Rotating file handler (5 MB, 3 backups) in `DATA_DIR/logs/`
4. Initialize `QApplication`, load fonts, apply saved language and theme, show startup splash screen
5. **Schema Migration** — `SchemaMigrationService.migrate_to_head()` applies any pending Alembic revisions; startup blocks if migration fails
6. Register reports (`register_all_reports()`)
7. **Network Schema Gate** (`NetworkSchemaGate.check_and_gate()`) — blocks startup if network PostgreSQL schema is incompatible (#799)
8. **First-Run Setup & DB Check** — checks `DatabaseSetupService.needs_setup()` (#833) and `ConfigService.get("setup_completed")` (#791):
   - Launches `SetupWizard` to collect shop details, hardware, and admin PIN
   - Initializes database via `DatabaseSetupService` ("Start Fresh" or "Load Demo Data") with the admin PIN
9. Start background scheduler timer (`SchedulerService`)
10. Launch `MainWindow` (maximized)
11. Deferred update check (3s delay, non-blocking via `UpdateWorker`)

### Data Directory Strategy (`cbpos/config.py`)

User data (database, settings, encryption key, logs, backups) is stored **outside** the install directory:

| Environment | Data Location |
|-------------|---------------|
| **Windows (installed)** | `%LOCALAPPDATA%\CB POS` |
| **macOS (installed)** | `~/Library/Application Support/CB POS` |
| **Linux (installed)** | `~/.local/share/cbpos` |
| **Development** | Project root (same as `BASE_DIR`) |

This ensures Inno Setup updates never touch user data. On first launch after an update, `ensure_data_dir()` in `main.py` migrates `cbpos.db`, `settings.json`, and `.encryption_key` from the old install-relative location.

### Navigation Flow
1. **LoginView** → authenticates user via `AuthService`
2. **SalesView** → main POS interface (cart, checkout, barcode scanning)
3. **ManagementView** → inventory, customers, reports, purchases (tabbed: Dashboard, Inventory, Customers, Credit Book, Purchase, Documents, Reports, Stock Take, Promotions, Price Lists, Users, Data Safety)
4. **SettingsView** → application configuration, theming, localization, Payment Methods, Admin Tools, Receipts, Network, System

The `MainWindow` class ([cbpos/ui/main_window.py](cbpos/ui/main_window.py)) uses `QStackedWidget` for navigation. It manages:
- Global barcode scanner (`BarcodeScanner`) that routes scans to active view
- Session watchdog (configurable inactivity timeout)
- Side menu signal wiring (management, documents, history, refund, reprint, etc.)
- View switching logic and back-button history

### Database Patterns

**Singleton Pattern:** Use `Database()` to get the singleton instance.

```python
from cbpos.core.database import Database

db = Database()
with db.get_session() as session:
    # Your database operations here
    # Auto-committed on success, rolled back on error
```

**Session Management:**
- Always use `db.get_session()` context manager
- Sessions are automatically committed on success, rolled back on exceptions
- Use `expire_on_commit=False` (configured in `Database` class) to prevent DetachedInstanceError

**Eager Loading:**
Load relationships in queries to avoid DetachedInstanceError. Some models use `lazy="joined"` at the model level (e.g., Product → unit, category):
```python
from sqlalchemy.orm import joinedload

with db.get_session() as session:
    sale = (
        session.query(Sale)
        .options(
            joinedload(Sale.items).joinedload(SaleItem.product),
            joinedload(Sale.customer),
            joinedload(Sale.payments),
        )
        .filter_by(id=1)
        .first()
    )
    session.expunge(sale)  # Detach before returning
```

**First-Run Database Setup:**
`DatabaseSetupService` handles initial database creation:
- `needs_setup()` — checks if DB file exists and has users
- `create_empty_database()` — tables + minimal data (admin user, roles, permissions, void reasons, payment methods, units)
- `create_demo_database()` — runs `scripts/seed.py` for full sample data

### Internationalization (i18n)

All user-facing text uses the translation system. **NEVER** hardcode English strings in UI code.

```python
from cbpos.i18n import _t, set_language, get_language
from cbpos.i18n import register_language_callback, unregister_language_callback
from cbpos.i18n import translate_in

# Basic translation with parameter interpolation
label.setText(_t("sale_history.refund_header", receipt="REC-123", amount="Rs. 2,450"))

# Translate in a specific language (e.g., for receipts)
receipt_text = translate_in("si", "receipt.header")

# Live language switching — long-lived views register callbacks with owner=self;
# the callback is unregistered automatically when the widget is destroyed.
register_language_callback(self.retranslate_ui, owner=self)

# NEVER connect `obj.destroyed` to a lambda or nested function yourself: if gc runs
# between deleteLater() and the deferred delete, PyQt can call the gc-cleared function
# and segfault (#392, #718). For other destroy-time cleanup use
# `call_on_destroyed(owner, callback, *args)` from cbpos/core/utils/destroy_hooks.py.
```

- **Translation files:** `cbpos/i18n/en.json`, `si.json`, `ta.json` (~2,000 keys each)
- **Key format:** Dot notation — `"section.subsection.key"`
- **Fallback:** Missing keys fall back to English, then return raw key
- **Dialogs:** Short-lived, call `retranslate_ui()` in `__init__` but don't register callbacks
- **Views/Widgets:** Long-lived, register `retranslate_ui` callback for live switching

### Document Polymorphism

All transactional documents (Sales, Purchases) inherit from `Document` base class using SQLAlchemy's Joined Table Inheritance:

- **Document**: Base class with common fields (document_number, type, date, user_id, status, void_reason_id)
- **Sale**: Extends Document with customer, payments, items, tax calculations
- **Purchase**: Extends Document with supplier, purchase items, total cost

This enables unified document numbering, voiding logic, and audit trails across all transaction types.

### Resource Loading

The `ResourceLoader` class ([cbpos/infrastructure/resource_loader.py](cbpos/infrastructure/resource_loader.py)) must be called **before** any UI initialization:

```python
from cbpos.infrastructure.resource_loader import ResourceLoader

# Load fonts first (returns primary font family name)
primary_font = ResourceLoader.load_fonts()

# Then initialize UI components
```

This ensures fonts from `cbpos/assets/fonts/` are registered with Qt before use in QSS themes.

## Critical Domain Rules

### Money Math
**NEVER** use `float` for currency. **ALWAYS** use `decimal.Decimal`.

### Sri Lankan Tax Calculation (Backward Calculation from MRP)
Shelf prices are **MRP (Maximum Retail Price)** and include tax (both VAT and SSCL are off until "VAT registered" is enabled in settings).
Per the Social Security Contribution Levy Act s.3(3)(b), **SSCL turnover excludes VAT**.

```python
from decimal import Decimal
from cbpos.core.utils.money import round_money

# VAT (18% backward calculation)
vat = round_money(taxable_mrp * Decimal("0.18") / Decimal("1.18"))

# SSCL base is VAT-exclusive turnover (for retail preset: 50% turnover rate, 2.5% tax)
sscl_base = taxable_mrp / Decimal("1.18")
sscl = round_money(sscl_base * Decimal("0.50") * Decimal("0.025"))

# Net Revenue (what the shop keeps)
net_revenue = round_money(total_mrp) - vat - sscl

# Example on Rs 100.00 gross:
# VAT: Rs 15.25 | SSCL: Rs 1.06 | Net Revenue: Rs 83.69
```

### Inventory Costing
- **Costing Method:** Weighted Average Cost (AVCO)
- **Quantities:** Support 3 decimal places (e.g., `1.250 kg`) for weighted items
- All stock changes tracked in `StockMovement` table with type: SALE, PURCHASE, ADJUSTMENT, RETURN, VOID

### Permissions & Audit
- Check permissions before critical actions (Void, Refund, Price Change) using `check_permission_with_override()` from `cbpos/core/utils/permission_helper.py`
- All critical changes logged to `AuditLog` table via services
- Permission codes defined in `cbpos/core/constants/permissions.py`

## UI/UX Guidelines

### Color Palette

**Dark Theme (`dark.qss`):**
- **Background:** `#1E1E1E` (Global) / `#252526` (Surface)
- **Text:** `#FFFFFF` (Primary) / `#AAAAAA` (Secondary)
- **Border:** `#3E3E42`
- **Accent/Focus:** `#00BCEB` (Cyan)
- **Success/Pay:** `#39FF14` (Neon Green)
- **Warning:** `#FFDC00` (Yellow)
- **Destructive/Void:** `#FF4136` (Red)

**Light Theme (`light.qss`):**
- **Background:** `#F8F9FA` (Global) / `#FFFFFF` (Surface)
- **Accent:** `#0D6EFD` (Blue)
- **Success:** `#198754` (Green)
- **Error:** `#DC3545` (Red)

### Qt Best Practices
- **Focus Management:** Set `.setFocusPolicy(Qt.FocusPolicy.NoFocus)` on buttons in virtual keyboards/numpads to prevent stealing focus from input fields
- **Layouts:** Prefer `QGridLayout` for forms, `QStackedLayout` for view navigation
- **Asset Paths:** Use `pathlib` to resolve asset paths relative to app root
- **Themes:** `cbpos/ui/styles/dark.qss` and `light.qss` — loaded via `ThemeService`
- **Object Names:** Set `setObjectName()` on dialogs/widgets for QSS targeting (e.g., `#SaleHistoryDialog`, `#QuickFilterBtn`)
- **Icons:** Use `qtawesome` via `cbpos/ui/resources/icons.py` — centralized FontAwesome icon references

### Threading Rule
**NEVER** run blocking operations (Printing, Emailing, heavy SQL reports) on the Main UI Thread.

```python
# Pattern 1: QThread for long-running tasks
from PyQt6.QtCore import QThread, pyqtSignal


class PrinterThread(QThread):
    finished = pyqtSignal()

    def run(self):
        # Blocking print operation
        self.finished.emit()


# Pattern 2: QTimer for deferred/periodic tasks
from PyQt6.QtCore import QTimer

QTimer.singleShot(3000, self._deferred_check)  # One-shot delay

scheduler_timer = QTimer(app)
scheduler_timer.timeout.connect(SchedulerService.check_automation)
scheduler_timer.start(60_000)  # Periodic (every 60s)
```

## Type Hinting & Code Style

### Type Hinting (Mandatory)
```python
# Bad
def calculate(amount):
    return amount * 0.18


# Good
from decimal import Decimal


def calculate(amount: Decimal) -> Decimal:
    return amount * Decimal("0.18")
```

### Error Handling (EAFP Pattern)
```python
# Use try/except for hardware and DB operations
try:
    printer.print_receipt(receipt)
except Exception as e:
    logger.error(f"Printer error: {e}")
    # Show user-friendly message
```

### Imports
Use absolute imports: `from cbpos.core.services import ...`

## Adding New Features

### Adding a New Model
1. Define model in [cbpos/core/models/\_\_init\_\_.py](cbpos/core/models/__init__.py) (all models are in one file)
2. Create Alembic migration: `alembic revision --autogenerate -m "description"`
3. Apply migration: `alembic upgrade head`
4. Update [scripts/seed.py](scripts/seed.py) if sample data needed
5. Update `DatabaseSetupService.create_empty_database()` if the model needs default data

### Adding a New Service
1. Create service file in `cbpos/core/services/`
2. Import `Database` singleton for DB access
3. Add Google-style docstrings to all methods
4. Follow existing service patterns (see [transaction_service.py](cbpos/core/services/transaction_service.py) for reference)

### Adding a New View
1. Create view file in `cbpos/ui/views/`
2. Inherit from `QWidget` and define signals for navigation
3. Call service layer methods — never access DB directly
4. Register view in [main_window.py](cbpos/ui/main_window.py)'s `init_views()`
5. Implement `retranslate_ui()` and register with `register_language_callback()`

### Adding a New Dialog
1. Create dialog file in `cbpos/ui/dialogs/`
2. Inherit from `QDialog`, set `setObjectName()` for QSS targeting
3. Implement `retranslate_ui()` — call in `__init__`, no callback registration needed (short-lived)
4. Add i18n keys to all three JSON files (`en.json`, `si.json`, `ta.json`)
5. Add QSS styles to both `dark.qss` and `light.qss`

### Adding i18n Keys
1. Add keys to `cbpos/i18n/en.json` (English — required, always complete)
2. Add matching keys to `si.json` and `ta.json` (use English values as fallback)
3. Use dot notation: `"section.key"` — group by feature/dialog
4. Use `{parameter}` syntax for interpolation: `"Hello, {name}!"`

## CI/CD & Release Pipeline

### GitHub Actions (`.github/workflows/release.yml`)
- **Trigger:** Git tags (`v*.*.*`) or manual workflow dispatch
- **Build job:** Python 3.12 (via `astral-sh/setup-uv`) → `uv sync --locked --no-dev --group build` → version stamp → PyInstaller → Inno Setup → SHA-256 checksum
- **Publish job:** Push installer + `latest.json` to public releases repo ([ceybyte/cbpos-releases](https://github.com/ceybyte/cbpos-releases))

### PyInstaller (`cbpos.spec`)
- One-dir mode (creates `dist/cbpos/cbpos.exe`)
- Bundles: `cbpos/assets`, `cbpos/ui/styles`, `cbpos/i18n`, `alembic`, `LICENSE`, `PRIVACY.md`, `THIRD_PARTY_NOTICES.txt`
- Collects all for: `escpos`, `qtawesome`
- Icon: `cbpos/assets/ico/cbpos_multi.ico`

### Inno Setup (`installer/cbpos.iss`)
- Installs to `{autopf}\CB POS` (Program Files)
- User data in `%LOCALAPPDATA%\CB POS` (never touched by installer)
- Detects running instance via mutex
- Version injected at build time: `iscc /DMyAppVersion=X.Y.Z`

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `PyQt6` | GUI framework |
| `SQLAlchemy` | ORM + database |
| `alembic` | Database migrations |
| `python-escpos` | Thermal receipt printing |
| `qtawesome` | FontAwesome icons in UI |
| `bcrypt` | PIN hashing |
| `pandas` | Report data processing |
| `xlsxwriter` / `openpyxl` | Excel export/import |
| `reportlab` / `xhtml2pdf` | PDF generation |
| `Pillow` | Image processing (receipt images, labels) |
| `python-barcode` / `qrcode` | Barcode/QR generation |
| `pyzipper` | Encrypted ZIP backups |
| `pyusb` | USB thermal receipt printing only (barcode scanners are USB HID keyboards; scales use serial/COM) |

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Agent skills

### Issue tracker

Issues live in GitHub Issues for HMAHD/CB-POS (use the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root (created lazily). See `docs/agents/domain.md`.
