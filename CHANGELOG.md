# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2025-12-01

### Added
  - Implemented Advanced Receipt Engine with support for graphical logos, barcodes, item merging, and a visual previewer.
  - Added "Receipt" tab in Settings for customizing header, footer, logo, barcode, tax breakdown, item merging, and print options.
  - Added Visual Receipt Preview dialog that simulates the final receipt layout.
  - Implemented item merging logic for receipts.
  - Implemented Shift Closing & Z-Report features.
- **Theme & Localization** (Phase 16):
  - Implemented Dynamic Theme Switching (Dark/Light).
  - Created `ThemeService` for handling stylesheet application and variable injection.
  - Created `LanguageService` for managing application translations.
  - Added Theme and Language selectors to `SettingsView`.
  - Added `scripts/update_translations.py` to generate translation files.
- **Sales View Polish** (Phase 16.2):
  - Implemented `ActionPanel` with "Key-Corner" layout.
  - Added Horizontal Search Modes (All, Barcode, Code, Name).
  - Replaced layout with resizable `QSplitter`.
  - Fixed Header Logo.
- **Shift Closing & Z-Report** (Phase 12):
  - Implemented `ShiftService.get_shift_summary` for financial snapshots.
  - Created `DenominationWidget` for blind cash counting.
  - Developed `ShiftClosingDialog` wizard (Count -> Review -> Close).
  - Implemented `ShiftClosingDialog` wizard (Count -> Review -> Close).
  - Added Z-Report generation in `ReceiptService` with variance tracking.
- **Reporting & Automation** (Phase 14):
  - Implemented `ProfitLossReport` and `TaxLiabilityReport` (Financials).
  - Implemented `EmailService` with threaded SMTP support and PDF attachments.
  - Created `SchedulerService` for automated daily sales reports.
  - Enhanced `ReportViewer` with Direct Print and Email capabilities.
  - Added Automation Settings tab for configuring Auto-Report schedules and SMTP.
- **Comprehensive Settings** (Phase 15):
  - Implemented Modular Settings Architecture with `SettingsPage` base class.
  - Expanded `ConfigService` with Sales, Inventory, and Document settings.
  - Implemented "Negative Stock" prevention with recursive check for Composite Items.
  - Implemented "Default Search Mode" configuration for Sales View.
  - Migrated Hardware and Payment settings to modular pages.

### Refactored
- **Sales Screen Overhaul** (Phase 6):
  - Redesigned `SalesView` with a split-screen "Command Console" layout.
  - Implemented Left Panel (75%) for Cart, Search, and Totals.
  - Implemented Right Panel (25%) for Action Grid and Payment.
  - Styled Cart Table with borderless, alternating row colors and large text.
  - Added massive Green "PAY" button for improved usability.
- **Management Sidebar Polish**:
  - Refactored sidebar to be collapsible with smooth animations.
  - Implemented full-width navigation buttons with dynamic styling (Center vs Left align).
  - Added distinct styling for "POS / Sales" (Green) and "Logout" (Red) buttons.
  - Fixed User Badge loading logic and asset paths.
- **UI Architecture**:
  - Refactored `MainWindow` to act as a mode-switcher (Sales vs. Management) without a permanent sidebar.
  - Created `ManagementView` (`ui/views/management_view.py`) as the dedicated Back Office container with sidebar navigation.
  - Updated `SalesView` (`ui/views/sales_view.py`) with a top header and "Three Dots" menu button for navigation.
  - Implemented `SideMenu` (`ui/widgets/side_menu.py`) skeleton for future slide-out navigation overlay.
- **Side Menu Overlay**:
  - Implemented fully functional `SideMenu` widget with Navigation, User Profile, and System Toolbar.
  - Added slide-in/out animation in `SalesView`.
  - Implemented click-outside-to-close behavior using `eventFilter`.
  - Wired up navigation signals (`Management`, `Logout`, `Fullscreen`, `Power`) in `MainWindow`.
- **Code Review Remediation** (PR #4):
  - Refactored `ReceiptService` to restore header logic and improve safety.
  - Refactored `ShiftService` to correctly handle shift end times in summary calculations.
  - Refactored `DenominationWidget` for configurable currency and robust math.
  - Refactored `ShiftClosingDialog` for safe access and better styling.
  - Fixed linting errors (E231, F401).
- **Code Review Remediation** (Reports & Tests):
  - Renamed `CashFlowReport` to `CashMovementAuditReport` to resolve naming collision.
  - Deleted unused `ui/views/reports_view.py` after verifying `ManagementView` imports.
  - Fixed `test_purchase_service.py` to correctly match `PurchaseService` signature.

### Fixed
  - Resolved `QPainter` warnings by ensuring valid pixmaps and sizes in `ManagementView`.
  - Fixed asset paths for Logo and User Badges using `pathlib`.
  - Resolved persistent `E501` line length errors across multiple files.
  - Fixed `IndentationError` in `side_menu.py`.
  - Removed unused imports (`F401`) in `manager_override_dialog.py`.
  - Aligned `black` and `flake8` configuration to use 120 characters line length.
  - Fixed `E702` multiple statements on one line in `email_service.py` and `history_view.py`.
  - Fixed `E231` missing whitespace in `history_view.py`.
- **Code Review Remediation (Critical)**:
  - Synced Black and Flake8 line lengths to 120 characters (`pyproject.toml`).
  - Refactored `EmailService` to use `QThreadPool` for thread-safe email sending.
  - Restored missing `pin_input` field in `ManagerOverrideDialog`.
  - Restored missing Name and Price labels in `ProductCard` (Touch Widgets).

***

## [0.1.0] - 2025-11-29

### Added
- **Transaction History & Refunds** (Phase 8.3):
  - Implemented `HistoryView` with transaction filtering by date range and search.
  - Added full refund processing with automatic stock restoration.
  - Integrated refund tracking via `refund_of_sale_id` foreign key in `Sale` model.
  - Updated `ReceiptService` to format refund vouchers with `REFUND VOUCHER` header.
  - Added `TransactionService.process_refund()` method with validation and audit logging.
  - Supports refunds for both regular and composite products with proper stock restoration.
  - History view accessible via main window sidebar navigation.
- **Composite Products** (Phase 8.2):
  - Implemented bundle/hamper support in Product Editor.
  - Added `is_composite` flag to `Product` model for quick identification.
  - Created `ProductEditorDialog` with tabbed interface for managing compositions.
  - Stock deduction automatically handles child products when composite items are sold.

### Fixed
  - Resolved SQLite migration constraint naming issues for refund foreign key.
  - Fixed f-string format specifiers causing flake8 E231 errors.

***

## [0.1.0] - 2025-11-25

### Added
  - Initial project structure scaffolding.
  - Configuration files (`.gitignore`, `requirements.txt`).
  - Database layer (`core/database.py`) with Singleton pattern and SQLAlchemy 2.0.
  - Domain models (`core/models/__init__.py`) for `User`, `Category`, `Product`, `Sale`, `SaleItem`.
  - Seeding script (`scripts/seed.py`) with Sri Lankan retail data.
  - Authentication Service (`core/services/auth_service.py`) with PIN hashing.
  - Global Theme (`ui/styles/theme.qss`) implementing "Ceylon Byte" industrial design.
  - Login UI (`ui/views/login_view.py`) with custom Numpad and Split Screen layout.
- **Transaction Operations** (Phase 8):
  - Implemented **Hold/Recall Bill** functionality.
  - Implemented **Void Bill** (Clear Cart) functionality.
  - Added `SuspendedTransaction` model.
- **Hardware & Receipts** (Phase 5 & 9):
  - Implemented `IPrinter` interface and `ESCPOSDriver` (with Mock fallback).
  - Implemented `ReceiptBuilder` for formatting Sri Lankan compliant receipts.
  - Integrated printing and cash drawer kick into `TransactionService`.
- **Inventory & Security** (Phase 3 & 4):
  - Implemented `InventoryMasterView` (Advanced Grid with Search).
  - Implemented RBAC Models (`Role`, `Permission`, `RolePermission`, `AuditLog`).
  - Updated `User` model to use `role_id` relationship.
  - Standardized Development Environment (`setup_development_environment.py`).
  - **Fixed**: Resolved `DetachedInstanceError` in Login by eagerly loading `User` roles.
  - **Fixed**: Corrected attribute name mismatch (`stock_qty`) in Inventory View.
  - **Fixed**: Resolved `InvalidRequestError` in Product Service by using `session.expunge_all()`.
- **Transaction Ops & Security** (Phase 3 & 8):
  - Implemented `PermissionService` and `ManagerOverrideDialog`.
  - Enforced RBAC on Void operations (requires Manager PIN if unauthorized).
  - Enhanced Hold/Recall with list selection (`SuspendedTransaction`).
- **Advanced Payments & Auditing** (Phase 2 & 10):
  - Implemented Split Payments (Cash/Card/Credit).
  - Implemented Credit Sales with Customer Credit Limit checks.
  - Added `LoggingService` for database-backed Audit Logs.
  - Enabled Database Connection Pooling for performance.
- **Inventory Integrity & Speed/UX** (Phase 4, 5, 6):
  - Implemented Composite Items (Bundles/Hampers) with component stock deduction.
  - Added Stock Adjustment Tool with audit logging (`InventoryLog`).
  - Implemented Low Stock Indicators in Inventory Master.
  - Added Global Barcode Scanner Hook for instant input handling.
  - Added System Status Bar (Printer/Network status).
  - Refined Login Screen: Hidden Status Bar, Enabled Numpad Support.