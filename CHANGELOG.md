# Changelog

All notable changes to this project will be documented in this file. Never delete added changes; you may rewrite them, but never delete.

## [0.8.4] - 2026-03-02

### Changed — Streamlined Sale Completion Flow
- **Removed success popup**: Eliminated blocking "Sale processed successfully!" QMessageBox that required an OK click after every sale.
- **Conditional receipt printing**: When receipt dialog is OFF (new default), receipt auto-prints and sale completes instantly with zero popups. When receipt dialog is ON, auto-print is skipped and the dialog handles printing.
- **Receipt dialog default OFF**: `show_receipt_dialog` default changed from `True` to `False` for frictionless checkout flow.
- **process_sale() returns Sale object**: `TransactionService.process_sale()` now returns the `Sale` object (or `None` on failure) instead of `bool`, eliminating an extra `get_last_sale()` DB query.
- **Print Receipt button works**: Receipt Options Dialog "Print Receipt" button now actually prints via `PrintWorker` (text or image based on language) and closes the dialog. Previously was a placeholder.

### Fixed
- **DetachedInstanceError in receipt dialog**: Fixed crash when clicking "Email Receipt" — `sale.customer` is now eager-loaded before session closes, with a fallback try/except in the dialog.

## [0.8.3] - 2026-03-02

### Redesigned — Receipt Options Dialog
- **Receipt Options Dialog**: Full redesign to match system dark/light theme. Replaced old navy-blue background and garish cyan/orange/gray buttons with proper theme surfaces (#1E1E1E dark, #F8F9FA light). New layout: success checkmark icon (48px), "Transaction Completed!" title, order info card with document number and bold total, icon-prefixed action buttons (Print with cyan accent border, Email with subtle border), centered ghost Close button. All selectors use objectName IDs instead of property-based class selectors.

### Fixed — Side Menu & Action Panel
- **Side Menu Layout**: Changed nav tiles from 2-column grid to single-column vertical list with uniform 20px spacing. Removed QGridLayout in favor of QVBoxLayout for cleaner item-by-item navigation.
- **Action Panel Visibility**: Fixed action panel not reappearing when returning to POS view from Management/Settings/Documents. `showEvent()` now closes the side menu and restores the action panel automatically.

## [0.8.2] - 2026-03-01

### Redesigned — Payment Dialog & Advanced Search
- **Payment Dialog**: Full redesign with new two-column layout (920×700). Left column: method tiles (2×3 grid with 12px gap, active tile gets accent border), searchable customer combo (type-to-filter with QCompleter, MatchContains), compact applied payments list with red SVG cross remove buttons. Right column: 28px amount input (auto-fills remaining for all methods), 72px touch-friendly numpad (fixed-size container with uniform 8px spacing), ADD PAYMENT button.
- **Numpad**: Wrapped in fixed-size container widget to prevent QGridLayout stretching. Buttons use NoFocus policy to avoid stealing focus from amount input. "C" clears, "." adds decimal, digits replace selected text.
- **Enter Key Fix**: Parent SalesView's QShortcut(Key_Return/Key_Enter) was stealing Enter presses before the dialog could handle them. Fixed by disabling parent shortcuts on dialog open and re-enabling in done() (same pattern as QuantityDialog).
- **Customer Search**: Made customer combo editable with QCompleter (CaseInsensitive + MatchContains). Placeholder "Type to search..." for quick lookup in large customer lists. Validates typed name exists before accepting credit payment.
- **Remove Payments**: Each applied payment has a red cross icon button (x-red.svg). Click removes that entry and recalculates balance. Full border visibility with proper margins (14px right, 8px vertical, 48px item height).
- **Advanced Search Dialog**: Added objectName "AdvancedSearchDialog" for QSS targeting. Replaced QFormLayout with horizontal filter rows (search + category + supplier row, price range row). Added result count label. All table items get explicit theme-aware foreground color (fixes invisible text in dark theme). Min size increased to 950×620.
- **QSS Themes**: Replaced all navy-blue (#0A1929, #132F4C) Payment Dialog styles with system theme colors (#1E1E1E/#252526 dark, #F8F9FA/#FFFFFF light). Added selected state for method tiles, BtnRemovePayment, PaymentListItemWidget/Label, AdvancedSearchDialog styles for both themes.

### Fixed
- **Export Path Validation**: `ExportService._validate_export_path()` now uses `tempfile.gettempdir()` instead of hardcoded `/tmp`. Fixes auto-report failure on macOS where temp dir is `/var/folders/.../T/`.

## [0.8.1] - 2026-03-01

### Fixed — UI/UX Polish
- **Login Screen**: Rewrote numpad layout with fixed-width container (294px) to fix button spacing. Added PIN heading, inline error label, help hint, and tagline. Removed QMessageBox for login errors.
- **POS Action Panel**: Fixed invisible button text in dark theme — added `setObjectName("ActionGridBtn")` so QSS exclusion rules work. Buttons now use flexible width (`SizePolicy.Expanding`) to prevent clipping.
- **POS Cart**: Fixed column mismatch in `update_cart_display()` — discount and total now populate correct columns. Merged duplicate `update_cart_ui()`/`update_cart_display()` into single method.
- **Payment Dialog**: Redesigned with dark-theme-native colors (deep navy palette), proper input/list styling, and two-line method buttons with shortcut labels.
- **Totals Area**: Added missing `DiscountLabel` objectName so discount label matches Subtotal/Tax styling.
- **Hamburger Menu**: Increased icon size (24px) and button size (42px) with hover effect.
- **ConfigService.get() crashes**: Fixed `TypeError` in `SoundService.play()` and `SalesView.quick_pay()` — removed invalid default argument from `ConfigService.get()` calls.
- **Receipt dialog bug**: Fixed `show_receipt_dialog` bool-vs-string comparison (`True == "True"` is `False` in Python).
- **QSS**: Moved ActionGridBtn from `[class=...]` attribute selector to `#ActionGridBtn` objectName selector for reliable specificity. Added NumpadContainer, PayMethodBtn, PaymentSeparator styles.
- **Action Button Labels (dark theme)**: Set label colors directly in Python (`_apply_theme_styles()`) since Qt QSS descendant selectors don't reliably cascade to child QLabels inside QPushButton. Added `refresh_theme()` method.
- **Side Menu**: Tightened layout — reduced nav margins (40→16px top), user section (30→20px), avatar (64→52px), spacing (5→2px). Moved Sign Out to separate container. Simplified `update_all_icons()`.
- **Settings View**: Removed unused `_CONFIG_PAGE_COUNT` and save/cancel visibility toggle.
- **Scheduler Service**: Fixed `ConfigService.update()` → `ConfigService.set()` method name.

## [0.8.0] - 2026-02-28

### Added — Phase 27: Admin Tools
- **Database Info (27.1)**: Admin Tools view with Database tab showing file path, size, last modified date, SQLite version, and table row counts. New `MaintenanceService.get_full_database_info()` method. Admin Tools sidebar button in Management view (admin-only).
- **Error Log Viewer (27.2)**: File-based logging via `RotatingFileHandler` (5 MB, 3 backups) writing WARNING+ to `logs/cbpos.log`. `ErrorLogService` for parsing, filtering, and exporting log entries. Error Logs tab with level/date/search filters, color-coded table (yellow warnings, red errors), stats summary, export to text file, and clear logs.
- **Hardware Test Page (27.3)**: `HardwareTestService` for testing receipt printer (sends test print), cash drawer (kick signal), and reading printer config. Background workers (`PrinterTestWorker`, `DrawerTestWorker`) keep UI responsive. Hardware tab shows printer configuration, test buttons with success/failure status, and barcode scanner test input field.
- **Permissions**: `admin.tools` permission code added to Admin group.

## [0.7.0] - 2026-02-28

### Added — Phase 22: Advanced Purchase & Inventory
- **GRN History (22.1)**: Browse all past Goods Received Notes with filters for supplier, status, and date range. Double-click opens read-only GRN detail dialog showing header info and items table with barcodes, quantities, costs, and line totals.
- **Physical Stock Take (22.2)**: Full count-compare-adjust workflow with StockCount/StockCountItem models. Create stock count, load all products or scan individual items, enter physical counts in editable table with real-time variance calculation (color-coded red/green). Three-stage lifecycle: Draft (counting) → Counted (finalized, pending approval) → Completed (stock adjustments applied via ADJUSTMENT movements). Variance report dialog for completed counts. Stock Take sidebar entry in Management view (admin-only).
- **Supplier Payment Tracking (22.3)**: Track supplier payables with SupplierPayment and SupplierLedgerEntry models. Automatic payable increase when GRN is committed. Two-panel Payables tab in Purchasing view (mirroring Credit Book pattern): supplier list with color-coded payable status, supplier ledger with debit/credit entries, date filters, and footer summary. Make Payment dialog with Pay Full button, payment method, reference, and note. Balance adjustment support. Payment terms field added to Supplier model and dialog.
- **Permissions**: Purchase group (purchase.view, purchase.create_grn, purchase.make_payment) and Stock Take group (stock_take.view, stock_take.create, stock_take.approve) permission codes. Admin and Manager roles updated with new permissions.
- **Migrations**: Alembic migrations for stock_counts, stock_count_items, supplier_payments, and supplier_ledger tables plus supplier column additions.

## [0.6.0] - 2026-02-28

### Added — Phase 26: UI Polish
- **Keyboard Shortcuts (26.1)**: F8/Ctrl+D to open cash drawer, F10 as payment alias, F12 quick close with full cash payment (skips dialog), PgUp/PgDn to select first/last cart item. F8 action panel button wired to PrintWorker kick_drawer. Updated shortcuts help dialog (F1) with all new shortcuts.
- **Sound Effects (26.2)**: SoundService with programmatically generated WAV tones — scan_success, scan_error, payment_complete, error. Audio feedback on barcode scan (success/fail), payment completion, and quick pay. Enable/disable toggle in Settings > System > POS Behavior. Graceful fallback when QtMultimedia is unavailable.
- **Loading Indicators (26.3)**: Reusable LoadingOverlay widget with animated spinner and status text. Integrated into report viewer (generation + export), inventory view (CSV import with row progress), and data safety view (backup/restore/vacuum). Replaces cursor-based wait indicators with visual overlay.

### Added — Phase 19: Quality Assurance
- **Math Engine Tests (19.1)**: 16 tests for TaxService (VAT backward calculation, SSCL on turnover, net revenue) and 24 tests for CartService (add/remove items, line discounts, cart discounts, price overrides, totals, rounding).
- **Transaction Service Tests (19.2)**: 8 new tests for void sale (double-void prevention, stock restoration, VOID movement audit trail) and refund workflow (full refund, voided sale rejection, double-refund prevention, refund-of-refund rejection).
- **Credit Service Tests (19.3)**: 19 tests for CustomerCreditService covering payment recording, credit sale ledger entries, balance adjustments (positive/negative/floor-at-zero), ledger querying, and customer summary.
- **Integration Tests (19.4)**: 8 end-to-end tests with real database: cash sale full workflow, credit sale with ledger, split payment, sale-then-void cycle, sale-then-refund cycle, insufficient payment rejection, credit limit enforcement, and tax breakdown accuracy.

### Fixed
- **Refund SaleItem missing original_price**: Fixed `process_refund` in TransactionService creating SaleItem without required `original_price` field, causing NOT NULL constraint failures.

### Added — Phase 17: Data Safety
- **Backup System (17.2)**: Complete backup/restore with AES-256 encryption. BackupRestoreDialog with Backup, Restore, Maintenance, and Export tabs. Backup list table, create/verify/restore operations. Auto-backup on app close with configurable retention (keep last N backups). Pre-restore safety snapshots. Data Safety sidebar button in Management view.
- **Database Maintenance (17.3)**: MaintenanceService with VACUUM (AUTOCOMMIT isolation), integrity check (PRAGMA integrity_check), and database info display (size, record counts). Maintenance tab in Data Safety dialog.
- **Data Export (17.4)**: DataExportService building pandas DataFrames for Products, Customers, and Sales with date filtering. DataExportDialog with checkboxes, date range pickers, and format selector (CSV/Excel/PDF). Export tab in Data Safety dialog.
- **Permissions**: DATA_SAFETY_BACKUP, DATA_SAFETY_RESTORE, DATA_SAFETY_MAINTENANCE permission codes.
- **Settings**: Backup settings group in System page — auto-backup toggle, retention count spinner, backup directory browser.
- **Tests**: 31 new unit tests covering backup (18), maintenance (5), and data export (8) services.

## [0.5.0] - 2026-02-27

### Added — Phase 31: Polish & Hardening
- **Returns/Refund UI (31.1)**: RefundDialog for processing returns against original sales with receipt lookup, reason entry, and manager override permission check. Stock automatically restored on refund.
- **Customer Account Statements (31.2)**: StatementService and CustomerStatementDialog for viewing/printing date-filtered account statements with debit/credit breakdown and running balances.
- **Barcode Label Printing (31.3)**: LabelService generating CODE128 barcode labels. LabelPrintDialog for batch printing with product search and quantity selection. Print Labels button added to inventory view.
- **End-of-Day Backup (31.4)**: BackupService that creates timestamped zip backups of the database, product images, and settings. Backup prompt integrated into ShiftClosingDialog after Z-report.
- **Receipt Reprint (31.5)**: ReceiptReprintDialog for searching past sales by document number or date range and reprinting receipts on thermal printer.
- **Manager Override Helper (31.7)**: `check_permission_with_override()` utility that checks user permissions and automatically shows ManagerOverrideDialog when access is denied. Refactored void_bill and change_line_price to use it.
- **Touch Visual Product Grid (31.8)**: ProductGridPanel with scrollable category tabs and product button grid for touch/visual POS mode. Collapsible panel in SalesView toggled via More button.
- **Branding on All Outputs (31.9)**: "Powered by CB POS — ceybyte.com" footer added to all receipts, invoices, PDF/Excel exports, and Z-reports. Invoice company details now read from ConfigService instead of hardcoded values.
- **Trilingual Receipt Strings (31.10)**: Receipt labels (Total, Date, Tax Breakdown, etc.) now use translated strings for English, Sinhala, and Tamil based on language configuration.
- **Units of Measurement CRUD (31.11)**: Unit model with name, abbreviation, and decimal places. UnitManagerDialog for creating, editing, and soft-deleting units with product guard. Unit selector in ProductEditor. Inventory table shows unit abbreviation. 8 default seed units (Piece, Kilogram, Gram, Liter, Meter, Pack, Box, Dozen).
- **Side Menu Enhancements**: Added Reprint Receipt and Refund buttons to POS side menu for quick access.

## [0.4.0] - 2026-02-27

### Added
- **Credit Book & Customer Payments**:
  - Credit Book view with customer ledger, outstanding balances, and payment history
  - Receive Payment dialog for recording customer credit payments (Cash, Card, Transfer, Cheque)
  - Customer Ledger Entry model for double-entry credit tracking
  - Overdue report for aged receivables
- **Proforma Invoices**:
  - Create, edit, and manage proforma/quotation documents
  - One-click conversion of proforma to sale (loads items into POS cart)
  - Proforma model with validity/expiry tracking
- **Document Browser**:
  - Unified document browser with filtering by type, status, and date range
  - Document details panel with receipt generation
  - Accessible from both Management sidebar and POS side menu
- **Category Manager**:
  - Full category manager dialog with tree view, color indicators, and product counts
  - Add/edit/delete categories with subcategory hierarchy support
  - Delete guard prevents removing categories with assigned products
- **System Settings Page**:
  - New "System" section in Settings consolidating session, POS behavior, inventory, and feature toggles
  - Configurable inactivity timeout (default: disabled, 0 = no auto-lock, 1-60 minutes)
  - Moved quick pay, void reason, receipt dialog, negative stock, auto barcodes, loyalty, touch mode settings into System page
- **Setup Wizard**:
  - First-run setup wizard for shop info, tax, and printer configuration
- **Keyboard Shortcuts Help**:
  - Shortcuts help dialog accessible from POS side menu

### Changed
- **Settings Overhaul**:
  - Consolidated settings pages: removed standalone Inventory page (merged into System)
  - Simplified Sales & Tax page to search mode + tax configuration only
  - Payment method expansion with configurable payment types
- **Product Editor UX Improvements**:
  - Reordered fields: product name first, then barcode, category, pricing
  - Added Rs. currency prefix on price/cost inputs
  - Grouped inventory fields with QGroupBox sections (Stock, Supplier, Item Type)
  - Fixed dark theme on image label (was hardcoded light background)
  - Fixed component remove handler with stable row index pattern
  - Added Enter key support in composition barcode input
  - Improved validation messages with field-specific focus navigation
- **Session Watchdog**:
  - Now reads timeout from config instead of hardcoded 5 minutes
  - Disabled by default (0 = no auto-lock) for uninterrupted POS usage

### Fixed
- Removed redundant "Edit Profile" sidebar button (Users tab provides full user editing)
- Removed BtnProfile QSS rules from dark theme
- Removed unused badge UI code and fixed receipt preview crash
- Security hardening: removed PyQt imports from service layer, standardized Decimal precision
- Escaped LIKE patterns in search queries, added sale error handling, limited history query size
- Added pagination, threading for heavy operations, input validation, SSL support, statement timeout
- Standardized DB session patterns, replaced print statements with proper logging
- Fixed detached object errors with eager loading

## [0.3.0] - 2026-02-18

### Added
- **LAN & Multi-Terminal Architecture** (Phase 18):
  - Network database mode supporting PostgreSQL for multi-terminal shared database
  - Network settings page with connection testing and server configuration
  - One-click data migration from SQLite to PostgreSQL
  - Terminal ID configuration for multi-register identification
  - Database mode switching (Standalone/Network) with restart handling

### Changed
- Introduced module-level logging throughout codebase
- Centralized network config extraction
- Bound parameters for sequence reset operations

### Fixed
- Prevented transaction abort on sequence reset
- Trigger application restart when db_mode changes
- Network PR review feedback fixes
- Space-efficient layout improvements
- Multiple UI fix iterations for settings and management views

## [0.2.0] - 2026-02-17

### Added
- **Dynamic Theme System**:
  - Dark theme ("Ceylon Night") and Light theme ("Ceylon Day")
  - ThemeService for stylesheet application with font variable injection
  - ResourceLoader for Qt font registration before UI initialization
- **Localization**:
  - LanguageService with English, Sinhala, Tamil support
  - Translation file generation script
- **Sales View Enhancements**:
  - ActionPanel with keyboard shortcut grid layout
  - Horizontal search modes (All, Barcode, Code, Name)
  - Resizable QSplitter-based layout
  - Side menu overlay with slide animation
- **Reporting & Automation** (Phase 14):
  - Profit & Loss report and Tax Liability report
  - EmailService with threaded SMTP and PDF attachments
  - SchedulerService for automated daily sales reports
  - ReportViewer with direct print and email capabilities
- **Shift Management**:
  - Shift closing wizard with blind cash counting
  - Z-Report generation with variance tracking
  - DenominationWidget for configurable currency counting

### Changed
- Refactored MainWindow as mode-switcher (Sales vs Management)
- Created ManagementView with collapsible sidebar and smooth animations
- Redesigned settings dialog with VS Code-inspired sidebar
- Standardized form layouts across all settings pages

### Fixed
- QPainter warnings from invalid pixmaps
- Asset paths for logo and user badges using pathlib
- Linting alignment between Black (120 chars) and Flake8

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
  - Styled Cart Table with borderless, alternating row colors and large text.
  - Added massive Green "PAY" button for improved usability.
  - Created `SchedulerService` for automated daily sales reports.
  - Enhanced `ReportViewer` with Direct Print and Email capabilities.
  - Added Automation Settings tab for configuring Auto-Report schedules and SMTP.

### Refactored
- **Settings Dialog UX Overhaul (Phase 3 - Vertical Alignment Fix)**:
  - Fixed vertical centering issue where content floated in the middle of the page.
  - Wrapped all FormLayout pages in VBoxLayout containers with AlignTop alignment.
  - Content now properly aligns to the top of the settings area for all pages.
  - Improved QComboBox and QSpinBox arrow visibility with larger CSS triangles and better colors (#CCCCCC for dark, #495057 for light).
- **Settings Dialog UX Overhaul (Phase 2 - Field Expansion Fix)**:
  - Fixed short input fields issue by implementing `QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow` across all settings pages.
  - Standardized form layouts with right-aligned labels and consistent spacing (15px vertical, 20px horizontal).
  - Removed redundant page headers inside content areas (headers were causing visual clutter).
  - Improved sidebar width to 260px for better proportions (25% sidebar, 75% content).
  - Enhanced input field styling with 32px minimum height and proper border radius (4px).
  - Updated all 10 settings pages (General, Sales, Tax, Inventory, Documents, Receipt, Hardware, Payment, Automation, Profile).
  - Ensured QTextEdit fields also expand properly with matching styles.
  - Applied industrial enterprise-standard form layouts with optimal margins (30px).
- **Settings Dialog UX Overhaul (Phase 1)**:
  - Removed redundant floating header (window title is sufficient).
  - Redesigned sidebar with VS Code-inspired styling (#252526 background).
  - Implemented active item indicator with 3px Cyan left border and cyan text.
  - Improved content area input styling with proper heights, consistent padding (10px left), and focus states.
  - Enhanced form label alignment and contrast (#DDDDDD on dark theme, #495057 on light theme).
  - Unified footer bar with better spacing and right-aligned action buttons.
  - Updated both dark.qss and light.qss for consistent industrial appearance.
- **Sales Screen Overhaul** (Phase 6):
  - Redesigned `SalesView` with a split-screen "Command Console" layout.
  - Implemented Left Panel (75%) for Cart, Search, and Totals.
  - Implemented Right Panel (25%) for Action Grid and Payment.
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
  - Refactored `EmailService` to use `QThreadPool` for thread-safe email sending.
  - Restored missing `pin_input` field in `ManagerOverrideDialog`.
  - Restored missing Name and Price labels in `ProductCard` (Touch Widgets).
    - Deleted unused `ui/views/reports_view.py` after verifying `ManagementView` imports.
  - Fixed `test_purchase_service.py` to correctly match `PurchaseService` signature.

### Fixed
-   Resolved `QPainter` warnings by ensuring valid pixmaps and sizes in `ManagementView`.
-   Fixed asset paths for Logo and User Badges using `pathlib`.
### Added
- **Theme & Localization** (Phase 16):
    -   Implemented Dynamic Theme Switching (Dark/Light).
    -   Created `ThemeService` for handling stylesheet application and variable injection.
    -   Created `LanguageService` for managing application translations.
    -   Added Theme and Language selectors to `SettingsView`.
    -   Added `scripts/update_translations.py` to generate translation files.
- **Sales View Polish** (Phase 16.2):
    -   Implemented `ActionPanel` with "Key-Corner" layout.
    -   Added Horizontal Search Modes (All, Barcode, Code, Name).
    -   Replaced layout with resizable `QSplitter`.
    -   Fixed Header Logo.
- **Light Theme Overhaul** (Phase 16):
    -   Rewrote `light.qss` with "Enterprise Light" aesthetic (Borders, High Contrast).
    -   Implemented "Restart Required" strategy for theme changes to ensure asset integrity.
    -   Updated `ThemeService` to provide dynamic assets (Logo/Icons) based on theme.
    -   Fixed `CartService` crash by ensuring `tax` key defaults to Decimal.
    -   Refactored `SalesView` layout to ensure Header visibility.
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
  - Enforced validation on `HardwarePage` (`settings_pages.py`) so that **Scale Barcode Prefix** must be exactly 2 digits.
  - Updated `SettingsView.save_all` (`settings_view.py`) to catch validation errors and show a warning message instead of crashing or saving invalid data.
  - Switched `UserService.update_user_profile` (`user_service.py`) from `print` to `logging.error` for proper error logging.
  - Ran `pre-commit run --all-files` and confirmed it passes; verified changes match the requested logic.
  - Optimized `TransactionService` to use batch queries, eliminating N+1 performance issues.
  - Secured `ThemeService` against CSS injection by validating font size.

  - Hardened `UserService` with PIN validation, input sanitization, and added `get_recent_activity`.
  - Fixed `AttributeError` in `SalesView` by updating `update_cart_ui` to use `CartService.get_totals()`.
  - Fixed `AttributeError` in `SalesView` by renaming `total_label` to `lbl_total` to match usage.
  - Refactored `SalesView` summary panel to include `lbl_item_count`, `lbl_subtotal`, `lbl_tax`, and `lbl_discount`.
  - Fixed `TypeError` in `UserService.get_recent_activity` by making `user_id` optional.
  - Resolved `DetachedInstanceError` in `UserService` by eager loading user relationship.
  - Implemented missing `UserService` methods (`get_all_users`, `get_all_roles`, `create_user`, `update_user`).
  - Fixed `TypeError` in `SettingsView` by correcting boolean value in `settings.json`.

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