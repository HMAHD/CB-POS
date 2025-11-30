# Changelog
All notable changes to this project will be documented in this file.

## [Unreleased] - 2025-11-30
### Refactored
- **Sales Screen Overhaul** (Phase 6):
    -   Redesigned `SalesView` with a split-screen "Command Console" layout.
    -   Implemented Left Panel (75%) for Cart, Search, and Totals.
    -   Implemented Right Panel (25%) for Action Grid and Payment.
    -   Styled Cart Table with borderless, alternating row colors and large text.
    -   Added massive Green "PAY" button for improved usability.
- **Management Sidebar Polish**:
    -   Refactored sidebar to be collapsible with smooth animations.
    -   Implemented full-width navigation buttons with dynamic styling (Center vs Left align).
    -   Added distinct styling for "POS / Sales" (Green) and "Logout" (Red) buttons.
    -   Fixed User Badge loading logic and asset paths.
- **UI Architecture**:
    -   Refactored `MainWindow` to act as a mode-switcher (Sales vs. Management) without a permanent sidebar.
    -   Created `ManagementView` (`ui/views/management_view.py`) as the dedicated Back Office container with sidebar navigation.
    -   Updated `SalesView` (`ui/views/sales_view.py`) with a top header and "Three Dots" menu button for navigation.
    -   Implemented `SideMenu` (`ui/widgets/side_menu.py`) skeleton for future slide-out navigation overlay.
    -   **Side Menu Overlay**:
        -   Implemented fully functional `SideMenu` widget with Navigation, User Profile, and System Toolbar.
        -   Added slide-in/out animation in `SalesView`.
        -   Implemented click-outside-to-close behavior using `eventFilter`.
        -   Wired up navigation signals (`Management`, `Logout`, `Fullscreen`, `Power`) in `MainWindow`.
### Fixed
-   Resolved `QPainter` warnings by ensuring valid pixmaps and sizes in `ManagementView`.
-   Fixed asset paths for Logo and User Badges using `pathlib`.
- **Theme & Localization** (Phase 16):
    -   Implemented Dynamic Theme Switching (Dark/Light).
    -   Created `ThemeService` for handling stylesheet application and variable injection.
    -   Created `LanguageService` for managing application translations.
    -   Added Theme and Language selectors to `SettingsView`.
    -   Added `scripts/update_translations.py` to generate translation files.

## [0.1.0] - 2025-11-29
### Added
- **Transaction History & Refunds** (Phase 8.3):
    - Implemented HistoryView with transaction filtering by date range and search.
    - Added full refund processing with automatic stock restoration.
    - Integrated refund tracking via refund_of_sale_id foreign key in Sales model.
    - Updated ReceiptService to format refund vouchers with REFUND VOUCHER header.
    - Added TransactionService.process_refund() method with validation and audit logging.
    - Supports refunds for both regular and composite products with proper stock restoration.
    - History view accessible via main window sidebar navigation.
- **Composite Products** (Phase 8.2):
    - Implemented bundle/hamper support in Product Editor.
    - Added is_composite flag to Product model for quick identification.
    - Created ProductEditorDialog with tabbed interface for managing compositions.
    - Stock deduction automatically handles child products when composite items sold.
### Fixed
- Resolved SQLite migration constraint naming issues for refund foreign key.
- Fixed f-string format specifiers causing flake8 E231 errors.

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
## [Unreleased]
### Added
- **Pricing Engine**:
    - Implemented `PriceListService` and `PriceListView`.
    - Support for multiple price lists with date ranges.
    - Product-specific price overrides per list.
- **Promotions Module**:
    - Implemented `PromotionService` and `PromotionView`.
    - Support for time-based and day-based campaigns.
- **UI**:
    - Added "Price Lists" and "Promotions" to Management Sidebar.

### Fixed
- **Critical**: Resolved `ModuleNotFoundError: No module named 'cbpos.core.services.price_list_service'`.
- **Critical**: Resolved `sqlite3.OperationalError` by fixing Alembic migrations for `customers` table.
- Refactored `CustomerEditor` out of `CustomerView`.

## [0.1.0] - 2025-11-29
### Added
- **Transaction History & Refunds** (Phase 8.3):
    - Implemented HistoryView with transaction filtering by date range and search.
    - Added full refund processing with automatic stock restoration.
    - Integrated refund tracking via refund_of_sale_id foreign key in Sales model.
    - Updated ReceiptService to format refund vouchers with REFUND VOUCHER header.
    - Added TransactionService.process_refund() method with validation and audit logging.
    - Supports refunds for both regular and composite products with proper stock restoration.
    - History view accessible via main window sidebar navigation.
- **Composite Products** (Phase 8.2):
    - Implemented bundle/hamper support in Product Editor.
    - Added is_composite flag to Product model for quick identification.
    - Created ProductEditorDialog with tabbed interface for managing compositions.
    - Stock deduction automatically handles child products when composite items sold.
### Fixed
- Resolved SQLite migration constraint naming issues for refund foreign key.
- Fixed f-string format specifiers causing flake8 E231 errors.

## [0.0.1] - 2025-11-25
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
