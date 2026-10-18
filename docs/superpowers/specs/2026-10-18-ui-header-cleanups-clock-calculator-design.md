# Design Spec: UI Header Cleanups, POS Clock, Native Calculator & Sidepanel Modernization

**Date:** 2026-10-18  
**Status:** Approved  
**Author:** Pair Programming Agent  

---

## 1. Problem Statement & Motivation

During recent UI modernization, a persistent top header was added to the Management screen (`ManagementHeader`) featuring the active breadcrumb (`Management / <Screen>`), a live clock, a `POS / Sales` button, and a `Logout` button.

However, several UI redundancies and missing features remained:
1. **Redundant Sidebar Exit Buttons**: The `CollapsibleSidebar` still had a pinned bottom section containing `POS / Sales` and `Logout` buttons (`btn_pos` and `btn_logout`), occupying ~120px of vertical space. Because `ManagementHeader` already provides these buttons, this bottom cluster is redundant in `ManagementView` and constrains the vertical space available for the navigation buttons on smaller/standard screens.
2. **SettingsView Navigation Parity**: `SettingsView` also uses `CollapsibleSidebar`, and relied on the sidebar's `btn_pos` and `btn_logout` to exit back to POS or log out. Removing them from `CollapsibleSidebar` requires providing a clean, persistent top header (`SettingsHeader`) in `SettingsView` matching `ManagementHeader`.
3. **Redundant PageHeader Strip**: All 10 management views (Dashboard, Inventory, Purchasing, Customers, Reports, Documents, Users, Price Lists, Promotions, Stock Take, Reorder) each render a `PageHeader` widget (icon + screen title) at the very top of their internal content area. This duplicates the breadcrumb already visible in the top header and squanders ~50px of vertical display height.
4. **Missing POS Header Clock**: The live clock was only implemented on `ManagementHeader`. Cashiers operating the primary `SalesView` (POS sale screen) also need a clear date and time display.
5. **Missing POS Native Calculator**: Cashiers frequently need an OS calculator for quick manual math (e.g. bulk weights, customer change, custom discounts). They need a dedicated calculator button in the POS header that launches the operating system's native calculator without needing a reimplemented in-app calculator.

---

## 2. Proposed Architecture & Design

### 2.1 Sidepanel Modernization (`CollapsibleSidebar`)
- Remove `self._bottom_widget`, `self._bottom_divider`, `self.btn_pos`, and `self.btn_logout`.
- Remove `pos_clicked` and `logout_clicked` signals from `CollapsibleSidebar`.
- Allow the scrollable navigation list (`nav_scroll`) to occupy the full vertical height of the sidebar below the logo/toggle header.
- Clean up `set_compact()`, `finalize()`, and `retranslate_pos_logout()` to eliminate obsolete button references.

### 2.2 Persistent Settings Header (`SettingsHeader`)
- In `SettingsView`, introduce a top header frame `self.settings_header = QFrame()` (`setObjectName("SettingsHeader")`) above the stacked config pages, mirroring `ManagementHeader`:
  - **Left**: `lbl_header_title` (`setObjectName("SettingsHeaderTitle")`) displaying `"Settings / <Page Name>"` (e.g., `Settings / Shop Info`), dynamically updated on `switch_page()`.
  - **Stretch spacer**.
  - **Right**:
    - `btn_header_pos`: QToolButton ("POS / Sales") triggering `self._on_pos_clicked` (which checks for unsaved changes before returning).
    - `btn_header_logout`: QToolButton ("Logout") triggering `self._on_logout_clicked`.
- Styled in `light.qss` and `dark.qss` using the same visual tokens and hierarchy as `ManagementHeader`.

### 2.3 Elimination of Redundant `PageHeader` in Management Views
- Remove `self._page_header = PageHeader(...)` from:
  1. `cbpos.ui.views.dashboard_view.DashboardView`
  2. `cbpos.ui.views.inventory_view.InventoryView`
  3. `cbpos.ui.views.purchase_view.PurchaseView`
  4. `cbpos.ui.views.credit_book_view.CreditBookView`
  5. `cbpos.ui.views.reports.report_viewer.ReportViewer`
  6. `cbpos.ui.views.document_view.DocumentBrowserView`
  7. `cbpos.ui.views.user_view.UserView`
  8. `cbpos.ui.views.pricelist_view.PriceListView`
  9. `cbpos.ui.views.promotion_view.PromotionView`
  10. `cbpos.ui.views.stock_take_view.StockTakeView`
- Maintain the reusable `PageHeader` class in `page_header.py` for potential standalone dialogs/views, but remove it from the 10 management views.
- Update tests in `test_management_screens_page_header.py` to assert that views do not contain redundant headers and that management header handles breadcrumbs.

### 2.4 Clock & Calculator in POS Sales Screen (`SalesView`)
- **OS Native Calculator Integration**:
  - Implement `open_native_calculator() -> bool` in `cbpos.infrastructure.system_tools`:
    - macOS (`Darwin`): `subprocess.Popen(["open", "-a", "Calculator"])`
    - Windows (`Windows`): `subprocess.Popen(["calc.exe"], shell=True)`
    - Linux (`Linux`): searches `shutil.which()` for `["gnome-calculator", "kcalc", "galculator", "mate-calc", "xcalc"]` and spawns the first available.
    - Error-resilient: catches exceptions, logs warnings, returns False instead of crashing.
- **POS Header Bar (`SalesView.header_widget`)**:
  - Insert between logo stretch and hamburger menu button:
    1. `self.lbl_header_clock`: `QLabel` displaying current date and time formatted as `ddd, d MMM yyyy  hh:mm:ss`, refreshed every 1000ms via `QTimer`. Styled matching `ManagementHeaderClock`.
    2. `self.btn_calculator`: `QToolButton` (`setObjectName("HeaderCalculatorBtn")`) with icon `Icons.get("fa5s.calculator", ...)` and tooltip `sales.calculator_tooltip`. On click, invokes `open_native_calculator()`.
    3. Shortcut: `Ctrl+Alt+C` keyboard shortcut registered on `SalesView` to launch calculator.
    4. `self.menu_button`: hamburger menu button.

---

## 3. Scope & Non-Goals

### Goals
- Completely remove bottom POS and Logout buttons from `CollapsibleSidebar`.
- Add persistent `SettingsHeader` with breadcrumb, POS button, and Logout button in `SettingsView`.
- Remove redundant `PageHeader` from all 10 management views.
- Add live clock and native calculator launch button to `SalesView` header bar.
- Update unit tests and QSS stylesheets accordingly.

### Non-Goals
- Changing the layout or business logic of the management child views.
- Implementing an in-app software calculator widget (native OS calculator meets requirement cleanly and reliably).

---

## 4. Verification & Testing Strategy
- Unit tests verifying:
  - `open_native_calculator()` handles platform detection and error handling without raising.
  - `CollapsibleSidebar` has no bottom POS/Logout buttons, and full height is dedicated to nav items.
  - `SettingsView` renders `SettingsHeader` with breadcrumb and functional POS/Logout buttons.
  - Management child views no longer contain redundant `_page_header` instances.
  - `SalesView` header contains clock and calculator button.
- Clean execution of pytest test suite and `ruff check cbpos/`.
