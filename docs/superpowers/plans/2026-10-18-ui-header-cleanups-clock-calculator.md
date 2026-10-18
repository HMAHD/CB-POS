# Implementation Plan: UI Header Cleanups, POS Clock, Native Calculator & Sidepanel Modernization

**Plan Date:** 2026-10-18  
**Design Spec:** [docs/superpowers/specs/2026-10-18-ui-header-cleanups-clock-calculator-design.md](file:///Users/akash/Documents/CB-POS/docs/superpowers/specs/2026-10-18-ui-header-cleanups-clock-calculator-design.md)  
**Target Branch:** `feat/ui-header-cleanups-clock-calculator`  

---

## Task 1: Native Calculator Utility & Tests

### Files
- Create: `cbpos/infrastructure/system_tools.py`
- Create: `tests/unit/test_system_tools.py`

### Steps
1. Write unit tests in `tests/unit/test_system_tools.py` covering `open_native_calculator()`:
   - On `Darwin`: invokes `subprocess.Popen(["open", "-a", "Calculator"])`.
   - On `Windows`: invokes `subprocess.Popen(["calc.exe"], shell=True)`.
   - On `Linux`: locates valid calculator via `shutil.which` and executes.
   - On exception: catches, logs error, and returns `False` without raising.
2. Implement `open_native_calculator()` in `cbpos/infrastructure/system_tools.py`.
3. Run tests with `uv run pytest tests/unit/test_system_tools.py`.
4. Commit: `feat(infra): add cross-platform open_native_calculator utility`.

---

## Task 2: POS Sales Screen Clock & Calculator Integration

### Files
- Modify: `cbpos/ui/views/sales_view.py`
- Modify: `cbpos/i18n/en.json`, `cbpos/i18n/si.json`, `cbpos/i18n/ta.json`
- Modify: `cbpos/ui/styles/light.qss`, `cbpos/ui/styles/dark.qss`
- Create: `tests/unit/test_sales_header_clock_and_calculator.py`

### Steps
1. Write unit test in `tests/unit/test_sales_header_clock_and_calculator.py`:
   - Checks `sales_view.header_widget` contains `lbl_header_clock`.
   - Checks `sales_view.header_widget` contains `btn_calculator` with calculator icon and tooltip.
   - Clicking `btn_calculator` or pressing `Ctrl+Alt+C` calls `open_native_calculator()`.
   - Verifies clock updates on timer tick.
2. Update i18n files with `"calculator_tooltip": "Calculator (Ctrl+Alt+C)"` (or localized).
3. In `cbpos/ui/views/sales_view.py`:
   - In `init_ui()` inside `self.header_widget`:
     - Add `self.lbl_header_clock = QLabel()` (objectName `"SalesHeaderClock"`).
     - Add `self.btn_calculator = QToolButton()` (objectName `"HeaderCalculatorBtn"`).
     - Configure icon, tooltip, shortcut, and click handler.
     - Add `self._clock_timer = QTimer(self)` updating every 1000ms.
   - In `retranslate_ui()`, retranslate tooltip.
4. Update `light.qss` and `dark.qss` with styles for `#SalesHeaderClock` and `#HeaderCalculatorBtn`.
5. Run tests with `uv run pytest tests/unit/test_sales_header_clock_and_calculator.py`.
6. Commit: `feat(sales): add live clock and native calculator button to POS header`.

---

## Task 3: Modernize CollapsibleSidebar (Remove Bottom POS/Logout Cluster)

### Files
- Modify: `cbpos/ui/widgets/collapsible_sidebar.py`
- Modify: `cbpos/ui/views/management_view.py`
- Modify: `tests/unit/test_sidebar_fits_small_screens.py`
- Modify: `tests/unit/test_sidebar_button_icon_text_gap.py`
- Modify: `tests/unit/test_sidebar_pos_logout_no_padding_hack.py`

### Steps
1. Update existing tests in `test_sidebar_fits_small_screens.py`, `test_sidebar_button_icon_text_gap.py`, and `test_sidebar_pos_logout_no_padding_hack.py` to reflect removal of `btn_pos` and `btn_logout` from `CollapsibleSidebar`.
2. In `cbpos/ui/widgets/collapsible_sidebar.py`:
   - Remove `_bottom_widget`, `_bottom_divider`, `btn_pos`, and `btn_logout`.
   - Remove signals `pos_clicked` and `logout_clicked`.
   - Clean up `set_compact()`, `finalize()`, and `retranslate_pos_logout()`.
3. In `cbpos/ui/views/management_view.py`:
   - Remove connections to `self.sidebar.pos_clicked` and `self.sidebar.logout_clicked` (relying exclusively on `self.btn_header_pos` and `self.btn_header_logout`).
4. Run tests with `uv run pytest tests/unit/test_sidebar_*.py`.
5. Commit: `refactor(ui): remove bottom POS and Logout buttons from CollapsibleSidebar`.

---

## Task 4: Persistent Settings Header in SettingsView

### Files
- Modify: `cbpos/ui/views/settings_view.py`
- Modify: `cbpos/ui/styles/light.qss`, `cbpos/ui/styles/dark.qss`
- Create: `tests/unit/test_settings_header.py`

### Steps
1. Write unit test in `tests/unit/test_settings_header.py`:
   - Verifies `SettingsView` creates `SettingsHeader` with title, clock, `btn_header_pos`, and `btn_header_logout`.
   - Switching pages updates the breadcrumb title (`Settings / <Page Name>`).
   - Clicking `btn_header_pos` triggers `_on_pos_clicked()`.
   - Clicking `btn_header_logout` triggers `_on_logout_clicked()`.
2. In `cbpos/ui/views/settings_view.py`:
   - Construct `self.settings_header` above `self.stack`.
   - Add breadcrumb label `self.lbl_header_title`, live clock `self.lbl_header_clock` with 1s `QTimer`, `self.btn_header_pos`, and `self.btn_header_logout`.
   - Connect `switch_page` to update breadcrumb title.
   - Update `retranslate_ui()` for header texts.
3. Update `light.qss` and `dark.qss` to style `SettingsHeader`, `SettingsHeaderTitle`, `SettingsHeaderClock`, `SettingsHeaderPosBtn`, and `SettingsHeaderLogoutBtn`.
4. Run tests with `uv run pytest tests/unit/test_settings_header.py`.
5. Commit: `feat(settings): add persistent SettingsHeader with breadcrumbs, clock, and POS/Logout buttons`.

---

## Task 5: Remove Redundant PageHeader Across Management Views

### Files
- Modify: `cbpos/ui/views/dashboard_view.py`
- Modify: `cbpos/ui/views/inventory_view.py`
- Modify: `cbpos/ui/views/purchase_view.py`
- Modify: `cbpos/ui/views/credit_book_view.py`
- Modify: `cbpos/ui/views/reports/report_viewer.py`
- Modify: `cbpos/ui/views/document_view.py`
- Modify: `cbpos/ui/views/user_view.py`
- Modify: `cbpos/ui/views/pricelist_view.py`
- Modify: `cbpos/ui/views/promotion_view.py`
- Modify: `cbpos/ui/views/stock_take_view.py`
- Modify: `tests/unit/test_management_screens_page_header.py`

### Steps
1. Update `tests/unit/test_management_screens_page_header.py`:
   - Replace assertions checking for redundant `_page_header` with assertions confirming management views do not render `_page_header` and that `ManagementHeader` in `ManagementView` manages screen title breadcrumbs.
2. Remove `self._page_header` creation, layout addition, and retranslation across all 10 management views.
3. Run tests with `uv run pytest tests/unit/test_management_screens_page_header.py`.
4. Commit: `refactor(views): remove redundant PageHeader strip across all management views`.

---

## Task 6: Full Verification, Formatting & Linting

### Steps
1. Run full test suite: `uv run pytest tests/unit/test_system_tools.py tests/unit/test_sales_header_clock_and_calculator.py tests/unit/test_sidebar_*.py tests/unit/test_settings_header.py tests/unit/test_management_screens_page_header.py`.
2. Run ruff linter and formatter check: `uv run ruff check cbpos/ tests/` and `uv run ruff format --check cbpos/ tests/`.
3. Commit any formatting adjustments if required.
