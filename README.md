# CB POS - Industrial Retail System

![CB POS Logo](cbpos/assets/logo/CBPOS_Banner.png)

**CB POS** is a high-performance, industrial-grade Point of Sale system designed for the Sri Lankan retail market. Built with Python and PyQt6, it prioritizes speed, stability, and offline capability.

## 🚀 Features

### Core Operations
-   **Zero-Latency Checkout**: Optimized for sub-50ms barcode scans and instant UI transitions.
-   **Keyboard-First Design**: Full operation without a mouse for maximum cashier efficiency.
-   **Offline-First**: 100% local database (SQLite) ensures operations never stop, even without internet.

### Inventory & Financials
-   **Advanced Inventory**: Support for Composite Items (Bundles) and Weighted Products (kg/g).
-   **Stock Auditing**: Comprehensive `InventoryLog` tracks every stock adjustment with reasons.
-   **Financial Accountability**: Shift management (Start/End Float) and Cash Movement tracking (Petty Cash).

### Hardware Integration
-   **Direct Hardware Control**: Native support for ESC/POS Thermal Printers and USB Barcode Scanners.
-   **Status Monitoring**: Real-time indicators for Printer and Network status.

### Security & Compliance
-   **RBAC**: Role-Based Access Control (Admin, Manager, Cashier).
-   **Audit Trails**: Detailed logs for all critical actions (Voids, Price Overrides, Logins).
-   **Tax Compliance**: Built-in support for VAT and SSCL calculations.

## 🛠️ Tech Stack

-   **Language**: Python 3.12+
-   **GUI Framework**: PyQt6
-   **Database**: SQLite with SQLAlchemy 2.0 (ORM)
-   **Migrations**: Alembic
-   **Hardware**: `python-escpos`, `pyusb`
-   **Quality Assurance**: `pytest`, `black`, `flake8`, `pre-commit`

## 📦 Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/yourusername/cb-pos.git
    cd cb-pos
    ```

2.  **Create Virtual Environment**
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Initialize Database**
    ```bash
    alembic upgrade head
    python scripts/seed.py
    ```

## 🚀 Usage

### Running the App
```bash
python main.py
```

### Default Credentials
-   **Admin**: `admin` / `1234`
-   **Cashier**: `cashier` / `0000`

### Building Executable
To create a standalone `.exe` file:
```bash
pyinstaller cbpos.spec
```
The output will be in the `dist/` folder.

## 📂 Project Structure

```text
cbpos/
├── assets/             # Icons, Fonts, Logos
├── core/               # Business Logic & Data Layer
│   ├── models/         # SQLAlchemy Models
│   ├── services/       # Business Services (Auth, Transaction, Inventory)
│   └── database.py     # DB Connection
├── infrastructure/     # Hardware & External Systems
│   ├── hardware/       # Scanner & Printer Drivers
│   └── logging/        # System Logger
├── ui/                 # Presentation Layer
│   ├── dialogs/        # Popups (Payment, Stock, etc.)
│   ├── views/          # Main Screens (Login, Sales, Inventory)
│   ├── widgets/        # Reusable Components
│   └── styles/         # QSS Themes
└── main.py             # Entry Point
```

## 🛡️ License

**Proprietary Software**.
Copyright © 2026 Ceylon Byte. All Rights Reserved.
Unauthorized copying of this file, via any medium is strictly prohibited.
