# 🛡️ CB POS - Copilot Custom Instructions

You are acting as a **Senior Python Software Architect** specializing in **Industrial-Grade Desktop Applications**. Your goal is to generate code that is production-ready, crash-proof, and strictly adheres to the project's established patterns.

## Repository Overview

**CB-POS** is a high-performance, industrial-grade Point of Sale (POS) system for Sri Lankan retail markets. Built with **Python 3.12+** and **PyQt6**, it provides zero-latency checkout, keyboard-first design, and offline-first SQLite database operations.

**Tech Stack:** Python 3.12 | PyQt6 | SQLAlchemy 2.0 | SQLite | Alembic | ESC/POS printing

---

## 1. Technology Stack & Constraints

- **Language:** Python 3.12+ (Strict Type Hinting required)
- **GUI Framework:** PyQt6 (Latest Stable). Use `PyQt6.QtCore`, `PyQt6.QtWidgets`, `PyQt6.QtGui`
- **Database:** SQLite with **SQLAlchemy 2.0** (ORM). Use `DeclarativeBase`
- **Migration:** Alembic
- **Reporting:** Pandas (DataFrames), ReportLab (PDF), XlsxWriter (Excel)
- **Hardware:** `python-escpos` (Printing), `pyusb` (Scanning)

---

## 2. Architecture: Modular MVC

Do not mix business logic with UI code.

- **`ui/views/*.py`:** Purely for display, layouts, and signal emission. **NO** database calls here.
- **`core/services/*.py`:** Purely for business logic, math, and database I/O. **NO** PyQt widgets here.
- **`core/models/`:** SQLAlchemy definitions.
- **`infrastructure/`:** Drivers for Hardware (Printers, Scanners) and Logging.

---

## 3. Project Structure

```
cbpos/                  # Main application package
├── assets/            # Icons, fonts, logos (fonts/, logo/, badge/)
├── config.py          # App configuration (DB_URI, colors, VERSION)
├── core/              # Business logic layer
│   ├── constants/     # Permission constants, enums
│   ├── database.py    # Singleton DB manager with SQLAlchemy
│   ├── interfaces/    # Abstract interfaces
│   ├── models/        # SQLAlchemy ORM models (__init__.py exports all)
│   └── services/      # Business services (auth, cart, transaction, etc.)
├── infrastructure/    # External systems integration
│   ├── hardware/      # ESC/POS printer, scanner, cash drawer drivers
│   ├── logging/       # Audit logging
│   └── repositories/  # Data access layer
└── ui/                # Presentation layer (PyQt6)
    ├── dialogs/       # Modal dialogs (payment, product editor, etc.)
    ├── styles/        # QSS themes (dark.qss, light.qss)
    ├── views/         # Main screens (login, sales, inventory, etc.)
    ├── widgets/       # Reusable UI components
    └── main_window.py # Application window controller

tests/                 # Test suite
├── conftest.py        # Pytest fixtures (in-memory DB, session management)
└── unit/              # Unit tests

scripts/               # Utility scripts
├── seed.py            # Database seeding with sample data
├── update_translations.py  # Qt translation file generation
├── debug_conftest.py  # Test debugging utilities
├── debug_db.py        # Database debugging utilities
└── verify_phase4.py   # Phase 4 verification script

alembic/               # Database migrations
├── versions/          # Migration scripts
└── env.py             # Alembic environment configuration
```

**Key Configuration Files:**
- `pyproject.toml` - Ruff linter + formatter config (line-length: 120, target: py312)
- `.pre-commit-config.yaml` - Pre-commit hooks (Ruff linter + formatter)
- `alembic.ini` - Database migration configuration
- `settings.json` - Runtime application settings

---

## 4. Coding Standards (Industrial Grade)

### Type Hinting
Mandatory for all arguments and returns.
- *Bad:* `def calculate(amount):`
- *Good:* `def calculate(amount: Decimal) -> Decimal:`

### Money Math
**NEVER** use `float` for currency. **ALWAYS** use `decimal.Decimal`.

### Error Handling
Use the **EAFP** pattern (Easier to Ask for Forgiveness than Permission).
- Wrap hardware/DB calls in `try...except` blocks
- Log errors using the project's logger, do not just `print()`

### Imports
Use absolute imports: `from cbpos.core.services import ...`

### Code Style
- **Linter + Formatter:** Ruff (120 char line length, Black-compatible formatting)
- **Rules:** pycodestyle (E/W), Pyflakes (F), isort (I), bugbear (B), pyupgrade (UP), and more. See `pyproject.toml`

---

## 5. UI/UX Guidelines ("Ceylon Byte" Theme)

### Color Palette
- **Background:** `#001F3F` (Navy)
- **Panel/Input:** `#003366`
- **Accent/Focus:** `#00BCEB` (Cyan)
- **Success/Pay:** `#39FF14` (Neon Green)
- **Destructive/Void:** `#FF4136` (Red)

### Qt Best Practices
- **Focus Trap:** For virtual keyboards/numpads, always set `.setFocusPolicy(Qt.FocusPolicy.NoFocus)` on buttons to prevent stealing focus from input fields
- **Layouts:** Prefer `QGridLayout` for forms. Use `QStackedLayout` for navigation
- **Images:** Use `pathlib` to resolve asset paths relative to the app root
- **Theme files:** `cbpos/ui/styles/dark.qss` and `light.qss`
- **Services pattern:** UI calls service layer, never directly accesses DB

---

## 6. Domain Logic (Sri Lanka Retail)

### Pricing
Shelf prices are **MRP (Maximum Retail Price)** and include tax.

### Tax Calculation
Perform **Backward Calculation** from the Total:
- *VAT (18%):* `Base = Total / 1.18`
- *SSCL (2.5%):* `Liability = (Total * 0.5) * 0.025`

### Inventory
- **Costing Method:** Weighted Average Cost (AVCO)
- **Quantities:** Must support 3 decimal places (e.g., `1.250 kg`) for weighted items

---

## 7. Security & RBAC

- **Permissions:** Check permissions before critical actions (Void, Refund, Price Change)
  - Use the decorator: `@permission_required('permission.name')`
- **Audit:** All critical changes must be logged to the `AuditLog` table via `AuditService`

---

## 8. Threading Rule

**NEVER** run blocking operations (Printing, Emailing, heavy SQL reports) on the Main UI Thread.
Use `QThread` or `QRunnable` with Signals for these tasks.

---

## 9. Documentation

- Add Google-style Docstrings to all Service methods and Classes
- Comments should explain *Why*, not *What*

---

## 10. Build & Development Commands

### Environment Setup (Required First)

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install all dependencies
pip install -r requirements.txt
```

### Database Initialization

**IMPORTANT:** Use `seed.py` for development - it drops and recreates all tables with sample data.

```bash
# Recommended for development (creates tables + sample data)
python scripts/seed.py

# Alternative: Alembic migrations (for existing databases)
# NOTE: Only run on fresh database or after tables are dropped
alembic upgrade head
```

**Seed Data Includes:** Admin/Cashier users, sample products, categories, suppliers, permissions, and roles.

### Code Quality (Always Run Before Committing)

```bash
# Run all pre-commit hooks (Ruff linter + formatter)
pre-commit run --all-files

# Individual checks
ruff check .              # Lint check
ruff check --fix .        # Lint + auto-fix
ruff format --check .     # Format check
ruff format .             # Auto-format
```

### Running Tests

**Prerequisite:** Qt libraries must be available. Tests use in-memory SQLite database.

```bash
# Set platform for headless environments
export QT_QPA_PLATFORM=offscreen

# Run unit tests
python -m pytest tests/unit/ -v

# Run specific test file
python -m pytest tests/unit/test_transaction_service.py -v
```

**Note:** Tests require `libEGL`, `libxkbcommon`, and other Qt dependencies on Linux.

### Running the Application

```bash
python main.py
```

**Default Credentials:** Admin: `admin` / `1234` | Cashier: `cashier` / `0000`

### Building Executable

```bash
pyinstaller cbpos.spec
# Output: dist/cbpos executable
```

---

## 11. Database Patterns
- **Singleton pattern:** Use `Database()` to get the singleton instance
- **Session management:** Use `db.get_session()` context manager
- **Eager loading:** Load relationships in queries to avoid DetachedInstanceError

```python
from cbpos.core.database import Database

db = Database()
with db.get_session() as session:
    # Your database operations here
    session.commit()  # Auto-committed on success, rolled back on error
```

### Adding New Models
1. Define model in `cbpos/core/models/__init__.py`
2. Create Alembic migration: `alembic revision --autogenerate -m "description"`
3. Apply migration: `alembic upgrade head`
4. Update `scripts/seed.py` if sample data needed

---

## 12. Known Issues & Workarounds

1. **Qt libEGL missing:** Install Qt dependencies: `apt install libegl1 libxkbcommon0 libxcb-cursor0`

2. **Alembic "table exists" error:** Run `python scripts/seed.py` instead - it handles table recreation

3. **DetachedInstanceError:** Always eagerly load relationships needed after session closes

4. **Pre-commit slow first run:** First run installs hook environments; subsequent runs are fast

---

## Trust These Instructions

These instructions have been validated by running all commands successfully. Only search the codebase if:
- A command fails unexpectedly
- You need to find specific implementation details not covered here
- The project structure has changed significantly

For model definitions, service implementations, or UI patterns, explore the respective directories listed in the Project Structure section.
