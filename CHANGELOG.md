# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2025-11-26
### Fixed
- **Font Rendering**: Resolved "OpenType support missing" errors by implementing robust ResourceLoader.
    - Created `infrastructure/resource_loader.py` with recursive font loading.
    - Updated `main.py` to load fonts before UI initialization and set global default font.
    - Modified `theme.qss` with wildcard selector for font enforcement.
    - System now properly retrieves and uses font family names (e.g., "Noto Sans") instead of falling back to "Segoe UI".
- **Startup Crash**: Fixed `TypeError: QFontDatabase... not enough arguments` by using static methods only (PyQt6 requirement).
- **Login UX**: 
    - Set `NoFocus` policy on all numpad buttons to prevent focus stealing from PIN input.
    - Added `showEvent` override to force focus on PIN input field when view becomes visible.
    - Both physical keyboard Enter and virtual numpad Enter now trigger login correctly.

### Improved
- **Console Output**: Cleaned startup logging for production readiness.
    - Reduced ResourceLoader verbosity to summary-only (shows file count instead of individual fonts).
    - Implemented Qt message handler to suppress internal "OpenType support missing" warnings.
    - Real Qt errors and warnings still display for debugging.

## [0.1.0] - 2025-11-25
### Added
- Initial project structure scaffolding.
- Configuration files (.gitignore, requirements.txt).
- Database layer (`core/database.py`) with Singleton pattern and SQLAlchemy 2.0.
- Domain models (`core/models/__init__.py`) for User, Category, Product, Sale, SaleItem.
- Seeding script (`scripts/seed.py`) with Sri Lankan retail data.
- Authentication Service (`core/services/auth_service.py`) with PIN hashing.
- Global Theme (`ui/styles/theme.qss`) implementing "Ceylon Byte" industrial design.
- Login UI (`ui/views/login_view.py`) with custom Numpad and Split Screen layout.
- Transaction Operations (Phase 8):
    -   Implemented **Hold/Recall Bill** functionality.
    -   Implemented **Void Bill** (Clear Cart) functionality.
    -   Added `SuspendedTransaction` model.
- Hardware & Receipts (Phase 5 & 9):
    -   Implemented `IPrinter` interface and `ESCPOSDriver` (with Mock fallback).
    -   Implemented `ReceiptBuilder` for formatting Sri Lankan compliant receipts.
    -   Integrated printing and cash drawer kick into `TransactionService`.
- Inventory & Security (Phase 3 & 4):
    -   Implemented `InventoryMasterView` (Advanced Grid with Search).
    -   Implemented RBAC Models (`Role`, `Permission`, `RolePermission`, `AuditLog`).
    -   Updated `User` model to use `role_id` relationship.
    -   Standardized Development Environment (`setup_development_environment.py`).
    -   **Fixed**: Resolved `DetachedInstanceError` in Login by eagerly loading User roles.
    -   **Fixed**: Corrected attribute name mismatch (`stock_qty`) in Inventory View.
    -   **Fixed**: Resolved `InvalidRequestError` in Product Service by using `session.expunge_all()`.
- Transaction Ops & Security (Phase 3 & 8):
    -   Implemented `PermissionService` and `ManagerOverrideDialog`.
    -   Enforced RBAC on Void operations (requires Manager PIN if unauthorized).
    -   Enhanced Hold/Recall with list selection (`SuspendedTransaction`).
- Advanced Payments & Auditing (Phase 2 & 10):
    -   Implemented Split Payments (Cash/Card/Credit).
    -   Implemented Credit Sales with Customer Credit Limit checks.
    -   Added `LoggingService` for database-backed Audit Logs.
    -   Enabled Database Connection Pooling for performance.
- Inventory Integrity & Speed/UX (Phase 4, 5, 6):
    -   Implemented Composite Items (Bundles/Hampers) with component stock deduction.
    -   Added Stock Adjustment Tool with audit logging (`InventoryLog`).
    -   Implemented Low Stock Indicators in Inventory Master.
    -   Added Global Barcode Scanner Hook for instant input handling.
    -   Added System Status Bar (Printer/Network status).
    -   Refined Login Screen: Hidden Status Bar, Enabled Numpad Support.
# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2025-11-25
### Added
- Initial project structure scaffolding.
- Configuration files (.gitignore, requirements.txt).
- Database layer (`core/database.py`) with Singleton pattern and SQLAlchemy 2.0.
- Domain models (`core/models/__init__.py`) for User, Category, Product, Sale, SaleItem.
- Seeding script (`scripts/seed.py`) with Sri Lankan retail data.
- Authentication Service (`core/services/auth_service.py`) with PIN hashing.
- Global Theme (`ui/styles/theme.qss`) implementing "Ceylon Byte" industrial design.
- Login UI (`ui/views/login_view.py`) with custom Numpad and Split Screen layout.
- Transaction Operations (Phase 8):
    -   Implemented **Hold/Recall Bill** functionality.
    -   Implemented **Void Bill** (Clear Cart) functionality.
    -   Added `SuspendedTransaction` model.
- Hardware & Receipts (Phase 5 & 9):
    -   Implemented `IPrinter` interface and `ESCPOSDriver` (with Mock fallback).
    -   Implemented `ReceiptBuilder` for formatting Sri Lankan compliant receipts.
    -   Integrated printing and cash drawer kick into `TransactionService`.
- Inventory & Security (Phase 3 & 4):
    -   Implemented `InventoryMasterView` (Advanced Grid with Search).
    -   Implemented RBAC Models (`Role`, `Permission`, `RolePermission`, `AuditLog`).
    -   Updated `User` model to use `role_id` relationship.
    -   Standardized Development Environment (`setup_development_environment.py`).
    -   **Fixed**: Resolved `DetachedInstanceError` in Login by eagerly loading User roles.
    -   **Fixed**: Corrected attribute name mismatch (`stock_qty`) in Inventory View.
    -   **Fixed**: Resolved `InvalidRequestError` in Product Service by using `session.expunge_all()`.
- Transaction Ops & Security (Phase 3 & 8):
    -   Implemented `PermissionService` and `ManagerOverrideDialog`.
    -   Enforced RBAC on Void operations (requires Manager PIN if unauthorized).
    -   Enhanced Hold/Recall with list selection (`SuspendedTransaction`).
- Advanced Payments & Auditing (Phase 2 & 10):
    -   Implemented Split Payments (Cash/Card/Credit).
    -   Implemented Credit Sales with Customer Credit Limit checks.
    -   Added `LoggingService` for database-backed Audit Logs.
    -   Enabled Database Connection Pooling for performance.
- Inventory Integrity & Speed/UX (Phase 4, 5, 6):
    -   Implemented Composite Items (Bundles/Hampers) with component stock deduction.
    -   Added Stock Adjustment Tool with audit logging (`InventoryLog`).
    -   Implemented Low Stock Indicators in Inventory Master.
    -   Added Global Barcode Scanner Hook for instant input handling.
    -   Added System Status Bar (Printer/Network status).
    -   Refined Login Screen: Hidden Status Bar, Enabled Numpad Support.
    -   Fixed Font Loading: Dynamically loading Noto Sans from assets to resolve warnings.
    -   Fixed Login Enter Key: Enhanced key handling for robust submission.
- DevOps & Financial Infrastructure (Phase 4):
    -   Implemented `pre-commit` hooks for automated code quality (Black, Flake8).
    -   Added `Shift` and `CashMovement` models for financial accountability.
    -   Implemented `CashControlService` and `CashMovementDialog`.
    -   Fixed Alembic migration indentation issues.
- Updated `black` version to 24.1.1 for Python 3.12 support.
- **QA**: Established `pytest` framework with `conftest.py` and `pytest-qt`.
- **QA**: Implemented critical path unit tests for `TransactionService` (Atomic Sale, Tax, Void).
- **Deployment**: Configured `cbpos.spec` for single-file executable build.
- **Deployment**: Added `create_installer.py` script for automated building.
- Prepared Deployment Artifacts: `cbpos.spec` (PyInstaller) and `LicenseService` stub.
    -   **Fixed**: Sanitized `auth_service.py` to resolve reported SyntaxError.
