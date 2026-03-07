# Changelog

All notable changes to this project will be documented in this file. Never delete added changes; you may rewrite them, but never delete.

## [0.9.3] - 2026-03-07

### Improved — Receipt Layout & Preview Overhaul

- **Professional receipt layout**: Restructured receipt to match industrial POS standards — shop name (bold, centered), address, phone, TIN in header block; document title derived from payment method (CASH RECEIPT / CARD RECEIPT / CREDIT INVOICE); invoice number centered; date and time as clean split row without labels.
- **Item discount detection**: Discounts now detected by comparing `original_price` vs `unit_price` (persisted on SaleItem), not cart-only fields. Shows "Was Rs. X (-Y%)" with savings amount per line item.
- **Two-column split rows**: New `_split_row()` helper emits both `val` (space-padded for printer) and `left_val`/`right_val` (semantic split for preview HTML tables), ensuring parity between preview and print.
- **Payment & change section**: Receipt now shows PAID method + amount and CHANGE line with bold formatting.
- **Bold text support**: Receipt commands support `bold` flag; ESC/POS driver sets `bold=True` on printer; preview renders `<b>` tags.
- **Receipt preview rendering**: Rewrote `ReceiptPreviewWidget` with inline styles (no CSS classes) to work reliably in QTextBrowser's limited HTML 4 / CSS 2.1 engine. Separators use monospace characters with overflow clipping instead of unreliable `<hr>` tags.
- **Barcode only**: Removed QR code from entire system (builder, preview, settings, ESC/POS driver). Barcode encodes invoice number for return scanning.

### Fixed

- **Invisible preview text in dark theme**: Added `color: #000000` to QSS for `ReceiptPreviewBrowser` in both themes.
- **merge_items discount bug**: `ItemDisplay` now carries `original_price` so discount detection works when items are merged.
- **Bill-level discount calculation**: Percentage discounts now calculate actual amount from items subtotal instead of displaying raw percentage as currency.

### Changed — Discount Dialog

- **Redesigned discount dialog**: Updated to match Ceylon Byte system theme — segmented type selector, outlined cyan preset buttons, proper hover/pressed/disabled states in both dark and light themes.

## [0.9.2] - 2026-03-05

### Added — Receipt Settings Live Preview & UI Overhaul

- **Live receipt preview in settings**: Receipt settings page now uses a split-pane layout — settings on the left, live receipt preview on the right. Preview auto-updates on every change with 300ms debounce.
- **Reusable `ReceiptPreviewWidget`**: Extracted receipt rendering into `cbpos/ui/widgets/receipt_preview_widget.py` — accurate thermal paper simulation with monospace font, dashed separators, barcode/QR placeholders, and 80mm/58mm paper width support.
- **Section headers in settings pages**: New `_make_section_header()` base class helper with styled dividers (`SettingsSectionTitle` + `SettingsSectionLine`). Applied to Receipt and Hardware settings pages for visual grouping.
- **Realistic sample data**: Receipt preview uses 3 products (Paracetamol, Vitamin C, Hand Sanitizer) with realistic Sri Lankan pricing and document number format.

### Improved — Settings Page Layout

- **Receipt page redesign**: Replaced sparse QFormLayout with sectioned VBox layout — "Shop Logo", "Header & Footer" sections in Content tab; "Receipt Elements", "Staff & Terminal", "QR Code" sections in Display tab.
- **Hardware page redesign**: Applied same section-header pattern — "Printer Selection", "Print Behavior", "Test Hardware" in Printers tab; "Paper Cut", "Cash Drawer" in Cut & Drawer tab.
- **DRY preview rendering**: `ReceiptPreviewDialog` refactored to use `ReceiptPreviewWidget`, eliminating duplicate HTML rendering logic.
- **QSS theming**: Added styles for `ReceiptPreviewBrowser`, `ReceiptPreviewTitle`, `SettingsSectionTitle`, `SettingsSectionLine` in both dark and light themes.

## [0.9.1] - 2026-03-05

### Added — Receipt Printing Overhaul (Phase 31D)

- **Hardware settings controls**: Test Print and Open Drawer buttons in Settings > Hardware > Printers tab. New "Cut & Drawer" tab with auto-cut toggle, partial/full cut type, feed lines before cut (1-8), and drawer-on-cash-only setting (default: enabled).
- **Receipt content — Sri Lanka compliance**: Shop TIN/VAT number printed on receipts from existing `company_tax_id` config. Cashier name (from current session) and Terminal ID now printed when enabled.
- **QR code on receipt**: Configurable QR code (e.g. shop WhatsApp/website URL) — toggle + URL field in Settings > Receipt > Display.
- **VOID receipt template**: `build_void_receipt()` generates receipts with `*** VOIDED ***` header/footer, original sale reference, void reason, authorizer, and timestamp. Visually distinct with `===` border.
- **REFUND receipt template**: `build_refund_receipt()` generates receipts with `*** REFUND ***` header/footer, original sale reference, refund amount, authorizer, and timestamp.
- **Duplicate marking on reprints**: Reprinted receipts show `*** DUPLICATE — NOT FOR PAYMENT ***` at top and bottom. Reprint dialog passes `is_reprint=True` to ReceiptBuilder.
- **Printer error feedback**: `PrintWorker.error_occurred` signal connected to `SalesView` — shows non-blocking warning dialog with error message and "Check Settings > Hardware" guidance.
- **Receipt display toggles**: New settings in Receipt > Display: Show Cashier Name (default on), Show Terminal ID, Show QR Code, QR Content URL.

### Fixed — Printing Dead Code & ESC/POS Bugs

- **Removed duplicate `PrinterService._format_receipt()`**: Dead code that built raw ESC/POS bytes with hardcoded commands, wrong cut command (`ESC i` instead of `GS V`), and Windows-only `cmd /c copy` dispatch. `PrinterService` now routes through `ReceiptBuilder` + `PrintWorker`.
- **Partial/full cut support**: `ESCPOSDriver.print_commands()` handles `cut` command with `mode="PART"` or `mode="FULL"` based on config.
- **Cash drawer filtering**: Drawer kick passes payment methods; case-insensitive `CASH` comparison prevents drawer opening for card/credit-only transactions when `drawer_on_cash_only` is enabled.

### Improved — Code Quality (Review Feedback)

- **Logged broad exception handlers**: All `except Exception` fallbacks in `auth_service.py`, `cart_service.py`, and `receipt_builder.py` now log at `debug` level for troubleshooting.
- **Deterministic timestamps**: `build_void_receipt()` and `build_refund_receipt()` accept optional `void_timestamp` / `refund_timestamp` parameters — defaults to `datetime.now()` but injectable for testing.
- **Extracted shared receipt helpers**: `_append_header_block()`, `_append_branding()`, `_append_cut()`, `_get_conf()` reduce duplication across receipt builders.

## [0.9.0] - 2026-03-05

### Security — Permission System Enforcement (Phase 31A)

- **Fixed 3 mismatched permission codes**: `can_void_sale` → `sales.void_item`, `change_price` → `sales.change_price`, `can_refund` → `sales.refund` — previous codes silently failed, allowing anyone to void/refund/change prices.
- **Added 8 new permission codes**: `sales.refund`, `credit.receive_payment`, `credit.adjust_balance`, `purchase.adjust_payable`, `documents.void`, `inventory.delete`, `cash.open_drawer`, `reports.export`.
- **Enforced permission checks on 20+ critical operations**: discounts, user management, settings, backup/restore, inventory editing, credit adjustments, supplier payments, document voiding, stock take voiding, and data exports — all now gated via `check_permission_with_override()`.
- **Updated role seeds**: Manager gets Credit + Cash groups; Cashier gets `credit.receive_payment` and `cash.open_drawer`.

### Added — Payment & Settings Configuration (Phase 31B)

- **Payment Methods settings page**: Full CRUD management (add/edit/delete/toggle) for payment methods in Settings → Payments. Inline activate/deactivate toggle, compact action buttons, and QSS-themed table UI with proper row sizing.
- **Max Discount % setting**: New `max_discount_percent` (default 15%) in Sales & Tax → Sales. Enforced in `CartService` — raises `ValueError` when exceeded; UI catches and displays message.
- **Configurable login lockout**: `max_login_attempts` (default 5) and `lockout_duration_seconds` (default 300) in System → Security — `auth_service.py` now reads from config.
- **Loyalty points ratio setting**: `loyalty_points_ratio` (default Rs.100 per point) in Sales & Tax → Sales — `customer_service.py` reads from config.
- **Default credit limit setting**: `default_credit_limit` (default 0) in Sales & Tax → Sales.

### Fixed — Hardcoded Values & Polish (Phase 31C)

- **Replaced hardcoded payment lists**: `receive_payment_dialog.py` and `supplier_payment_dialog.py` now load methods from DB via `PaymentService.get_active_methods()` (excluding Credit).
- **Replaced CREDIT string comparisons**: 3 locations in `payment_dialog.py` and `transaction_service.py` now use `PaymentMethodType.CREDIT` constant instead of raw `"CREDIT"` string.
- **Payment method on receipts**: Receipt builder now shows payment breakdown (method + amount for each payment) with change calculation for cash overpayments.

## [0.8.11] - 2026-03-05

### Improved — Touch Product Grid UX Overhaul

- **Responsive card sizing**: Removed fixed 110×110px cards — cards now expand to fill available grid width with `MinimumSize(90, 100)` and `Expanding` size policy.
- **Product images**: Cards display product image (scaled 60×60) when `image_path` is set; gracefully omitted when no image exists.
- **Removed generic box icon**: Eliminated the identical box icon that wasted space on every card.
- **QSS-driven theming**: Removed all inline `setStyleSheet` calls from `ProductCard` and `CategoryButton` — styling now handled via `dark.qss` / `light.qss` using object names (`ProductCard`, `ProductCardName`, `ProductCardPrice`, `ProductCardImage`, `CategoryTab`).
- **Larger readable fonts**: Name 13px bold, price 15px bold (up from 12px/14px).
- **Wider grid panel**: Increased from 350px to 420px — fits 3 columns at ~130px each.
- **Dynamic column reflow**: Grid recalculates columns on resize (`max(2, width // 130)`) with even column stretch distribution.
- **Focus protection**: All card/button widgets set `NoFocus` policy to prevent stealing focus from barcode input.
- **CategoryButton**: Only minimal inline style retained for per-category dynamic checked background color.

## [0.8.10] - 2026-03-05

### Fixed — QFormLayout Field Growth Across All Dialogs

- **All QFormLayout instances** now use `ExpandingFieldsGrow` policy — input fields stretch to fill available dialog width instead of being narrow and centered.
- **Right-aligned labels** (`AlignRight`) applied globally for consistent visual alignment.
- **13 forms fixed across 13 files**: `customer_quick_add.py`, `category_dialog.py`, `profile_dialog.py`, `proforma_dialog.py`, `supplier_payment_dialog.py`, `receive_payment_dialog.py`, `stock_adjustment_dialog.py`, `setup_wizard.py` (3 forms), `data_export_dialog.py`, `backup_restore_dialog.py`, `category_manager.py`, `unit_manager.py`, `pricelist_view.py` (PriceListDialog).
- Previously fixed in `customer_editor.py` (3 forms) and `product_editor.py` (2 forms).

## [0.8.9] - 2026-03-04

### Changed — Report Viewer Redesign ("Data Observatory")

#### Bug Fixes
- **Duplicate report registration**: Added duplicate guard in `ReportRegistry.register()` — skips if `report_instance.id` already exists.
- **Missing reports**: Registered `CashMovementAuditReport` (Audit) and `CashFlowReport` (Financial) in `register_all_reports()`.
- **Duplicate viewer registrations**: Removed 4 duplicate `registry.register()` calls and stale imports from `report_viewer.py`.

#### Report Viewer — Full Rewrite (`report_viewer.py`)
- **Custom navigation sidebar**: Replaced generic QTreeWidget with a scrollable panel of styled QPushButtons grouped under category sections — full-width items with 40px+ click targets, cyan left-border accent on selection, count badges per category.
- **Empty state**: QPainter-rendered geometric bar chart icon (no emojis), centered text guidance.
- **Report header**: Shows report name + category when a report is selected, hidden until selection.
- **Filter bar**: Date edits and combo filters with Run Report button, hidden until report selected.
- **Data table**: QTableView with alternating rows, styled headers with cyan accent border, interactive column resize.
- **Action bar**: Row count label + Print/Excel/PDF/Email export buttons, hidden until data exists.
- **All inline setStyleSheet calls removed** — fully QSS-driven.

#### Filter Widget (`filter_widget.py`)
- Added objectNames: `ReportFilterWidget`, `ReportFilterLabel`, `ReportDateEdit`, `ReportFilterCombo`.

#### Dashboard View (`dashboard_view.py`)
- **SRP worker split**: Replaced monolithic `_DashboardWorker` with `_YearlyWorker` (Row 1) and `_PeriodicWorker` (Rows 3-4).
- **Added `refresh_periodic()` method**: Period refresh button now only re-fetches date-range data, not yearly data.
- **Year navigation optimized**: `_change_year()` now calls `_refresh_yearly()` only, not `refresh_all()`.

#### QSS (dark.qss + light.qss)
- Added ~150 lines per theme for Report Viewer: sidebar nav items, category labels, count badges, report header, filter bar, date edits, Run button, empty state, data table, action bar, export buttons.
- Dark: deep navy layers (`#0A1929` → `#112240` → `#0D2847`), cyan accents.
- Light: clean white/slate palette (`#FFFFFF` → `#F8FAFC` → `#EBF2FF`), blue accents.

## [0.8.8] - 2026-03-04

### Changed — Label Print Dialog, Product Editor & CSV Import UX Overhaul

#### Label Print Dialog (`label_print_dialog.py`)
- **QCompleter autocomplete**: Type-ahead search by product name or barcode (MatchContains, case-insensitive, max 10 items).
- **QStyledItemDelegate for Qty column**: Replaced setCellWidget approach with delegate — proper QSS rendering, validated integer input (1–999), centered bold text.
- **Preview Label button**: Opens thermal-label preview for selected product.
- **Completer + Enter key fix**: `activated` signal flag prevents double-add when selecting with arrow keys + Enter.

#### Label Preview Dialog (`label_preview_dialog.py`) — New
- **Thermal-label style preview**: White card on dark background, QPainter-rendered product name (bold), CODE128-style barcode bars (SHA256-based pattern), barcode text, and large price.
- **Theme-aware**: Uses `_get_text_color()` for dialog chrome; label card is always white.
- ObjectNames: `LabelPreviewDialog`, `LabelPreviewHeader`, `LabelPreviewHint`, `LabelCard`.

#### CSV Import Dialog (`csv_import_dialog.py`) — New
- **Two-step flow**: Step 1 downloads CSV template (headers + example row) via Save dialog; Step 2 picks and imports filled CSV with progress bar and results summary.
- **Background import**: Uses `CsvImportWorker` thread with progress/finished/error signals.
- Replaced direct `QFileDialog.getOpenFileName` in `inventory_view.py`.

#### Product Editor (`product_editor.py`)
- **Stock fields**: Replaced broken QDoubleSpinBox (buttons overlap under QSS) with QLineEdit + QDoubleValidator for Stock Qty, Reorder Point, Preferred Qty.
- **Supplier + Unit side-by-side**: Horizontal layout saves vertical space; works at small window sizes.
- **Item Type inline hints**: Checkbox + em-dash hint on same row (e.g. `☐ Weighted Item — sold by weight, cashier enters kg at checkout`). Reusable `ToggleHint` objectName pattern.
- **Image tab centered**: Placeholder and buttons centered both vertically and horizontally. Removed inline style — uses `ProductImagePreview` QSS objectName.

#### QSS (dark.qss + light.qss)
- Added styles for: `LabelPrintDialog`, `LabelQueueTable`, `LabelPreviewDialog`, `LabelPreviewHeader`, `LabelPreviewHint`, `CsvImportDialog`, `CsvImportSeparator`, `ToggleHint`, `ProductImagePreview`.

#### Import Service (`import_service.py`)
- Added `generate_template()` static method returning CSV headers + example row.

## [0.8.7] - 2026-03-04

### Changed — Comprehensive Dashboard with Animated Charts

#### Dashboard View — Full Redesign
- **Monthly Sales bar chart**: 12-month bar chart with per-month colors, year navigation arrows (◀ ▶), animated bar growth.
- **Yearly Summary panel**: Total Sales (large display) + Top Performing Month name and amount.
- **Date range selector**: Periodic Reports header with from/to date pickers and refresh button.
- **Top Products table**: Top 5 products by revenue within selected date range.
- **Hourly Sales bar chart**: Business hours (6AM–10PM) distribution with animated bars.
- **Quick Stats panel**: Average Order Value, Items Sold, Unique Customers, Transactions — all for selected period.
- **Top Selling Groups donut chart**: Category revenue breakdown with animated sweep, legend with percentages.
- **Top Customers horizontal bar chart**: Top 5 customers by spend with animated bars.
- **Auto-refresh on view switch**: `showEvent` triggers data reload.

#### Custom Chart Widgets (`cbpos/ui/widgets/charts.py`)
- **VerticalBarChart**: QPainter-rendered with rounded-top bars, Y-axis labels, grid lines, value labels on hover, grow animation (800ms OutCubic).
- **DonutChart**: Annular segments with sweep animation (900ms), center total, right-side legend with color swatches and percentages.
- **HorizontalBarChart**: Horizontal bars with labels, value text, grow animation (700ms).
- All charts are theme-aware via ThemeService (text/grid colors adapt to dark/light).

#### Dashboard Service — 7 New Methods
- `get_monthly_sales(year)` — 12-month totals using SQLite strftime.
- `get_yearly_summary(year)` — Total + top performing month.
- `get_period_top_products(start, end)` — Products by revenue in date range.
- `get_hourly_sales(start, end)` — Hourly distribution (6AM–10PM).
- `get_period_stats(start, end)` — Avg order, items sold, unique customers, txn count.
- `get_top_categories(start, end)` — Categories by revenue.
- `get_top_customers(start, end)` — Customers by spend.

#### QSS
- Added styles for 7 dashboard panels, yearly summary labels, quick stats, year nav buttons, period controls, and DashboardTable.
- Both dark.qss and light.qss fully themed.

## [0.8.6] - 2026-03-03

### Changed — Unified Settings Sidebar & Dashboard Redesign

#### Settings View
- **Rebuilt sidebar to match Management view**: Replaced QListWidget with QFrame + SidebarButton pattern — CB POS logo, hamburger collapse/expand animation (250px ↔ 70px), theme-aware icons.
- **Admin-only buttons**: Data Safety and Admin Tools hidden for non-admin users via `set_user()`.
- **Theme callback**: Sidebar icons and logo update on theme switch.

#### Dashboard View
- **Real-time KPI cards**: Today's Sales, Transactions, Average Sale, Items Sold — with yesterday % trend comparison.
- **Recent Transactions panel**: Last 10 sales with time, doc#, customer, payment method, total.
- **Top Selling Today panel**: Top 5 products by quantity with revenue.
- **Payment Methods panel**: Breakdown of payment method totals for today.
- **Removed**: Chart placeholder and hardcoded activity table.
- **Auto-refresh**: Dashboard refreshes on every `showEvent`.

#### Dashboard Service
- Added `get_yesterday_kpis()`, `get_recent_sales()`, `get_top_selling_today()`, `get_payment_breakdown()`.
- Extended `get_kpis()` with `items_sold` and `avg_sale`.

#### InfoCard Widget
- Changed from fixed 280×140 to responsive sizing (min 250×140, max height 160, expanding width).

#### QSS
- Added `RecentSalesPanel`, `TopProductsPanel`, `PaymentBreakdownPanel` + matching table styles.
- Removed dead `QListWidget#SettingsSidebar`, `QFrame#ChartPlaceholder`, `QTableWidget#ActivityTable` rules.

## [0.8.5] - 2026-03-03

### Fixed — Code Review Issues (#83–#96)

#### Critical
- **Double-click duplicate sale prevention (#83)**: Added `_processing` guard flag with try/finally in `process_payment()` and `quick_pay()`. Disabled FINISH SALE and PROCESS REFUND buttons during processing.
- **Thread-safe print queue (#84)**: Replaced plain `list` with `queue.Queue` in `PrintWorker` to prevent race conditions. Added `stop()` method and timeout-based dequeuing.
- **SQLite WAL mode + busy_timeout (#85)**: Added SQLAlchemy `connect` event listener to set `PRAGMA journal_mode=WAL`, `busy_timeout=30000`, and `foreign_keys=ON` for safe concurrent access.

#### High
- **Document number race condition (#86)**: Added `IntegrityError` retry loop with sequence increment for document number collisions.
- **Theme-aware dialog styles (#87)**: Removed all hardcoded navy-blue `setStyleSheet()` calls from BackupRestoreDialog and ValuationDialog. Replaced with `setObjectName()`/`setProperty("class", ...)` and QSS selectors in both dark.qss and light.qss.
- **Loading indicators (#88)**: Already implemented in Phase 26 — verified existing LoadingOverlay coverage.
- **Database indexes (#89)**: Added `index=True` to 12 frequently queried columns: Document.type/status/user_id, Sale.customer_id, SaleItem.sale_id/product_id, SalePayment.sale_id, PurchaseItem.purchase_id/product_id, Shift.user_id/status, CashMovement.shift_id.

#### Medium
- **Numeric precision (#90)**: Standardized all money columns from `Numeric(10,2)` to `Numeric(12,2)` across Sale, SaleItem, SalePayment, Purchase, PurchaseItem, Product, Customer, Shift, CashMovement, PriceListItem, Promotion, Proforma, ProformaItem.
- **Logger lazy formatting (#91)**: Converted 20+ `logger.error(f"...{e}")` calls to `logger.error("...%s", e)` across transaction_service, auth_service, user_service, and migration_service.
- **Legacy Query.get() → session.get() (#92)**: Replaced 24+ `session.query(Model).get(id)` calls with `session.get()` across 8 service files, including `joinedload` and `with_for_update` variants.
- **Proforma tax centralization (#93)**: Replaced hardcoded `Decimal("1.18")` tax math with `TaxService.calculate_taxes()` in proforma_service.
- **QThread memory cleanup (#94)**: Added `self.finished.connect(self.deleteLater)` to all 8 QThread workers.

#### Low
- **Decimal precision in receipts (#95)**: Replaced `float(entry.amount)` with `entry.amount` in receipt_builder to preserve Decimal precision.
- **Fernet encryption for credentials (#96)**: Replaced base64 encoding with `cryptography.fernet.Fernet` encryption using machine-derived key for stored passwords. Added legacy base64 migration fallback.

### Fixed — UI/UX Issues (#72–#81)
- **Integrity check async (#72)**: Replaced blocking `integrity_check()` with background `IntegrityCheckWorker` thread in Data Safety view.
- **Log row color coding (#73)**: Added background colors for WARNING (amber), ERROR (red), and CRITICAL (dark red) rows in error log table.
- **Secure backup password display (#74)**: Replaced plain `QMessageBox` with custom dialog featuring show/hide toggle and copy-to-clipboard button.
- **Hardware test timeout (#75)**: Added 15-second `QTimer.singleShot` timeout for printer and drawer test workers to prevent indefinite hangs.
- **Restore password visibility (#76)**: Added eye icon toggle button for password field in backup restore tab.
- **Docstring corrections (#77)**: Updated admin_tools_view and data_safety_view docstrings from "Management stack" to "Settings view".
- **Settings sidebar separator (#78)**: Added non-selectable visual separator between configuration pages and operational views in settings sidebar.
- **Log filter Enter key (#79)**: Connected `returnPressed` signal on log filter inputs for instant filtering on Enter.
- **Barcode scanner timing detection (#80)**: Added character timing analysis to distinguish scanner input (<50ms avg) from manual typing.
- **Inline data export (#81)**: Replaced stub Export Data tab with inline export UI featuring data type selector, format picker, date range, and direct export functionality.

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