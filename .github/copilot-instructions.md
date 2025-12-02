# Copilot Coding Agent Instructions for CB-POS

## Repository Overview

**CB-POS** is a high-performance, industrial-grade Point of Sale (POS) system for Sri Lankan retail markets. Built with **Python 3.12+** and **PyQt6**, it provides zero-latency checkout, keyboard-first design, and offline-first SQLite database operations.

**Tech Stack:** Python 3.12 | PyQt6 | SQLAlchemy 2.0 | SQLite | Alembic | ESC/POS printing

---

## Project Structure

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
- `pyproject.toml` - Black formatter config (line-length: 88, target: py312)
- `.pre-commit-config.yaml` - Pre-commit hooks (Black, Flake8)
- `.flake8` - Flake8 per-file ignores
- `alembic.ini` - Database migration configuration
- `settings.json` - Runtime application settings

---

## Build & Development Commands

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
# Run all pre-commit hooks (Black + Flake8)
pre-commit run --all-files

# Individual checks
black --check .           # Format check
black .                   # Auto-format
flake8 . --max-line-length=120 --ignore=E203,W503
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

## Development Guidelines

### Code Style
- **Formatter:** Black (88 char line length)
- **Linter:** Flake8 (max 120 chars, ignore E203, W503)
- **Imports:** Use absolute imports from `cbpos.*`
- **Type hints:** Use modern Python 3.12 syntax

### Database Patterns
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

### UI Development
- **Theme files:** `cbpos/ui/styles/dark.qss` and `light.qss`
- **Views inherit from:** `QWidget` with specific layouts
- **Services pattern:** UI calls service layer, never directly accesses DB

---

## Known Issues & Workarounds

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
