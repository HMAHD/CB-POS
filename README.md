# CB POS - Industrial Retail System

![CB POS Logo](cbpos/assets/logo/CBPOS_Banner.png)

**CB POS** is a high-performance, industrial-grade Point of Sale system designed for the Sri Lankan retail market. Built with Python and PyQt6, it prioritizes speed, stability, and offline capability.

**Free software** for small-to-medium shop owners — grocery, pharmacy, hardware, clothing, and more.

## Features

### Core Operations
- **Zero-Latency Checkout**: Optimized for sub-50ms barcode scans and instant UI transitions.
- **Keyboard-First Design**: Full operation without a mouse for maximum cashier efficiency.
- **Offline-First**: 100% local database (SQLite) ensures operations never stop, even without internet.
- **Cart Safety Net**: Warns before closing the app with items still in the cart (Hold & Exit / Exit Without Saving / Cancel).

### Inventory & Financials
- **Advanced Inventory**: Composite items (bundles), weighted products (kg/g), stock take/count.
- **Stock Auditing**: Comprehensive `InventoryLog` tracks every stock adjustment with reasons.
- **Financial Accountability**: Shift management (start/end float), cash movement tracking (petty cash, safe drops).
- **Purchase Orders**: Supplier management with auto stock increase and weighted average cost (AVCO) calculation.
- **Credit Book**: Customer credit tracking with statements and payment recording.

### Hardware Integration
- **Direct Hardware Control**: Native support for ESC/POS thermal printers and USB barcode scanners.
- **Multilingual Receipts**: Print receipts in Sinhala, Tamil, or English (independent of UI language).
- **Label Printing**: Product label generation and printing.

### Security & Compliance
- **RBAC**: Role-Based Access Control (Admin, Manager, Cashier) with granular permissions.
- **Audit Trails**: Detailed logs for all critical actions (voids, price overrides, logins).
- **Sri Lankan Tax Compliance**: Built-in VAT (18%) and SSCL (2.5%) backward calculation from MRP.
- **Manager Override**: Permission elevation for restricted operations.

### Internationalization (i18n)
- **Trilingual Support**: English, Sinhala (සිංහල), Tamil (தமிழ்).
- **1,827 Translation Keys**: Comprehensive coverage across all UI screens.
- **Live Language Switching**: Change language without restarting the application.
- **Independent Receipt Language**: Print receipts in a different language than the UI.
- **Format Parameter Safety**: Validated `{parameter}` interpolation across all translations.

### Reporting & Export
- **9 Report Definitions**: Sales, inventory, financial, cash flow, and audit reports.
- **Export Formats**: Excel, CSV, PDF.
- **Dashboard**: Real-time KPIs, top products, low stock alerts.

## Tech Stack

- **Language**: Python 3.12+
- **GUI Framework**: PyQt6
- **Database**: SQLite with SQLAlchemy 2.0 (ORM) | PostgreSQL for multi-terminal
- **Migrations**: Alembic (21 migrations)
- **Hardware**: `python-escpos`, `pyusb`
- **Reports**: `pandas`, `xlsxwriter`, `xhtml2pdf`, `reportlab`
- **Quality Assurance**: `pytest` (32 test files), `black`, `flake8`, `pre-commit`

## Installation

1. **Clone the Repository**
    ```bash
    git clone https://github.com/HMAHD/cb-pos.git
    cd cb-pos
    ```

2. **Create Virtual Environment**
    ```bash
    python -m venv .venv
    # Windows
    .\.venv\Scripts\activate
    # Linux/Mac
    source .venv/bin/activate
    ```

3. **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4. **Initialize Database**
    ```bash
    # Recommended: Fresh database with sample data
    python scripts/seed.py

    # Alternative: Alembic migrations (for existing databases)
    alembic upgrade head
    ```

5. **Configuration**
    Copy the example settings file and update it with your local configuration:
    ```bash
    cp settings.json.example settings.json
    ```

## Usage

### Running the App
```bash
python main.py
```

### Default Credentials
- **Admin**: `admin` / `1234`
- **Manager**: `manager` / `5678`
- **Cashier**: `cashier` / `0000`

### Building Executable
```bash
pyinstaller cbpos.spec
# Output: dist/cbpos executable
```

### Code Quality Checks
```bash
pre-commit run --all-files
```

### Running Tests
```bash
export QT_QPA_PLATFORM=offscreen  # Linux/Mac headless
python -m pytest tests/unit/ -v
```

### Translation Validation
```bash
python scripts/validate_translations.py          # Report issues
python scripts/validate_translations.py --strict  # Fail on issues (CI)
```

## Project Structure

```text
cbpos/
├── assets/             # Icons, fonts (Noto Sans EN/SI/TA), logos
├── i18n/               # Translation files (en.json, si.json, ta.json)
├── core/               # Business Logic & Data Layer
│   ├── models/         # 26 SQLAlchemy models (single file)
│   ├── services/       # 52 business services
│   ├── reports/        # 9 report definitions
│   └── database.py     # Singleton DB connection
├── infrastructure/     # Hardware & External Systems
│   ├── hardware/       # ESC/POS printer & barcode scanner drivers
│   └── ...             # Session watchdog, resource loader, input manager
├── ui/                 # Presentation Layer
│   ├── views/          # 24 main screens
│   ├── dialogs/        # 36 popup dialogs
│   ├── widgets/        # 12 reusable components
│   └── styles/         # QSS themes (dark + light)
├── main.py             # Entry point
├── alembic/            # 21 database migrations
├── scripts/            # Seed, validation, debug utilities
└── tests/              # 32 test files
```

## License

**Proprietary Software**.
Copyright 2026 Ceylon Byte. All Rights Reserved.
Unauthorized copying of this file, via any medium is strictly prohibited.
