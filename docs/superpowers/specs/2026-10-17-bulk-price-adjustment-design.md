# Design Specification: Price Lists Bulk Adjustment Tool ([REC-09] #544)

## 1. Intent & Why

Price lists in CB-POS are used for special occasions and targeted marketing campaigns (such as festive New Year discounts, wholesale tiers, or loyalty customer pricing). Store managers currently have to adjust items one by one (`SetItemPriceDialog`), which is tedious and error-prone when applying store-wide or category-wide promotional markdowns.

This feature provides a bulk adjustment dialog that allows managers to calculate, preview, and apply price updates across selected products, product categories, or entire price lists in a single atomic transaction—with automatic margin protection against selling below purchase cost.

---

## 2. Goals & Non-Goals

### Goals
- **Multi-scope targeting**:
  - `Selected`: Only the rows currently highlighted in the price list table.
  - `Category`: All products belonging to a chosen product category.
  - `All`: All products with price list entries (or all active catalog products).
- **Flexible pricing rules**:
  - `PERCENTAGE_OFF`: Base price discount (`new_price = base × (1 − x%)`).
  - `FIXED_OFF`: Base price fixed deduction (`new_price = max(0, base − amount)`).
  - `FIXED_MARKUP`: Base price fixed addition (`new_price = base + amount`).
  - `MARGIN_OVER_COST`: Markup over unit cost (`new_price = cost × (1 + margin%)`).
- **Rounding options**:
  - `EXACT`: Standard 2 decimal places (`Decimal("0.01")`).
  - `NEAREST_1`: Round to nearest whole rupee (`Rs. 1.00`).
  - `NEAREST_5`: Round to nearest `Rs. 5.00`.
  - `CHARM_99`: Charm pricing ending in `.99` (e.g. Rs. 499.99).
- **Below-cost margin protection**:
  - Compares every computed `new_price` against `product.cost`.
  - Displays a summary warning banner if any item drops below purchase cost.
  - Highlights affected products in the live preview table with a warning badge (`⚠️ Below Cost (-Rs. XX)`).
  - Prompts an explicit confirmation dialog if the manager chooses to proceed with below-cost prices.
- **Interactive live preview**:
  - Shows Product Name, Category, Cost, Base Price, Calculated New Price, and Margin/Warning badge.
  - Dynamically updates as inputs, rule types, or rounding selections change.
- **Single atomic transaction & audit entry**:
  - Executes updates in one database transaction; rolls back completely on any failure.
  - Writes exactly **one** consolidated Activity Log entry (`PRICE_LIST_BULK_ADJUST`) with details of the list, item count, rule parameters, and below-cost count.

### Non-Goals & Anti-Goals
- **Anti-Goal**: Must **never** modify master base prices (`Product.price`) or purchase costs (`Product.cost`). Only `PriceListItem.price` is modified or inserted.
- **Anti-Goal**: Never write separate individual audit log entries for each item during a bulk operation (which would pollute the audit log with dozens or hundreds of lines).
- **Anti-Goal**: Never allow prices below `0.00` (clamped to zero).
- **Non-Goal**: Does not schedule future automated price adjustments (handled by the Promotions module).

---

## 3. Architecture & Data Flow

### 3.1 Core Service: `PriceListService.bulk_adjust_prices()`

```python
class BulkAdjustmentRule:
    rule_type: str  # "PERCENTAGE_OFF", "FIXED_OFF", "FIXED_MARKUP", "MARGIN_OVER_COST"
    value: Decimal  # Percentage or rupee amount
    rounding: str  # "EXACT", "NEAREST_1", "NEAREST_5", "CHARM_99"
    scope: str  # "SELECTED", "CATEGORY", "ALL"
    category_id: int | None
    product_ids: list[int] | None


class BulkPreviewItem:
    product_id: int
    product_name: str
    category_name: str
    cost: Decimal
    base_price: Decimal
    old_list_price: Decimal | None
    new_list_price: Decimal
    margin_percent: Decimal
    is_below_cost: bool
    loss_amount: Decimal
```

1. **`calculate_preview(list_id: int, rule: BulkAdjustmentRule) -> list[BulkPreviewItem]`**:
   - Queries target products and their current `PriceListItem` (if any).
   - Computes candidate `new_list_price` and rounds according to `rule.rounding`.
   - Compares with `product.cost` to flag `is_below_cost`.
   - Pure read-only computation; does not write to database.

2. **`apply_bulk_adjust(list_id: int, items: list[BulkPreviewItem], rule_summary: str) -> int`**:
   - Executes inside a single `with self.db.get_session() as session:` block.
   - For each item, upserts `PriceListItem(price_list_id=list_id, product_id=p_id, price=new_price)`.
   - Logs **one** audit event via `LoggingService.add_change(session, "PRICE_LIST_BULK_ADJUST", PRICING_EVENT, list_name, ...)`.
   - Commits atomically.

### 3.2 UI Dialog: `BulkPriceAdjustDialog` (`cbpos/ui/dialogs/bulk_price_adjust_dialog.py`)

- **Left Panel (Inputs & Options)**:
  - Scope radio buttons (`Selected (N rows)`, `Category`, `All`).
  - Category combo box (enabled when `Category` scope selected).
  - Rule Type combo box & Numeric input field (`QDoubleSpinBox`).
  - Rounding options combo box.
  - Below-cost warning alert box (visible only when `below_cost_count > 0`).
- **Right Panel (Preview & Action)**:
  - Header showing Target Price List name and total items affected.
  - `QTableWidget` previewing candidate rows with columns: Product, Cost, Base Price, New Price, Margin / Warning.
  - Below-cost items highlighted with subtle amber/red background and warning badge.
  - Buttons: `Cancel`, `Apply Adjustments` (with confirmation prompt if below-cost items exist).

### 3.3 View Integration (`cbpos/ui/views/pricelist_view.py`)

- In `set_price_row` below the table, add `self.btn_bulk_adjust = QPushButton(_t("pricelist.btn_bulk_adjust"))`.
- Also add "Bulk Adjust..." to the right-click table context menu.
- Clicking opens `BulkPriceAdjustDialog(price_list, selected_product_ids, parent=self)`.
- On successful apply, refreshes the table data and updates `last_modified`.

### 3.4 Builder Decisions & Edge Case Handling

1. **"All Products" Scope Definition**:
   - When "All Products in List" is selected, it includes all active catalog products (`Product.is_active == True`), creating new `PriceListItem` overrides if none exist, or updating existing ones. This enables full store-wide campaigns (e.g., store-wide New Year 10% off) even if the price list was previously empty.
2. **Zero or Missing Cost (`cost <= 0`)**:
   - If an item's cost is `0.00` (e.g. services or uncosted items), `MARGIN_OVER_COST` calculation falls back to using the base selling price with a warning in the status column (`"Cost not set"`).
3. **Clamping & Decimals**:
   - All adjusted prices are strictly clamped at a minimum of `0.00` (`max(Decimal("0.00"), calculated_price)`).
4. **Button Placement & Hotkeys**:
   - Placed in `PriceListView`'s action row: `[Set Price] [Bulk Adjust...] [Remove Override]`.
   - Also accessible via table right-click context menu and keyboard shortcut (`Ctrl+B` or `Cmd+B`).

---

## 4. UI / UX Design & Theming

- **Dark & Light Theme**:
  - Themed via `dark.qss` and `light.qss` using existing design tokens.
  - Status badges use shared palette (`#4ade80` for safe positive margins, `#ef4444` for below-cost warnings).
- **Trilingual Localization**:
  - Complete translations in English (`en.json`), Sinhala (`si.json`), and Tamil (`ta.json`).
  - Currency headers rendered using `money_header(...)`.

---

## 5. Testing & Verification Plan

1. **Unit Tests (`tests/unit/test_bulk_price_adjust.py`)**:
   - `test_percentage_discount_calculation`: Verifies `-10%` on base price.
   - `test_fixed_discount_calculation`: Verifies `-Rs. 50` clamped at 0.00.
   - `test_margin_over_cost_calculation`: Verifies `Cost + 20%`.
   - `test_rounding_options`: Tests exact, nearest rupee, nearest 5, and `.99` charm.
   - `test_below_cost_warning_detection`: Verifies flag when `new_price < cost`.
   - `test_atomic_bulk_apply`: Verifies all items update in 1 transaction and only that price list is affected.
   - `test_single_audit_log_entry`: Confirms exactly 1 log entry is created.
   - `test_base_price_and_cost_untouched`: Ensures `Product.price` and `Product.cost` are unchanged.
2. **Visual Verification**:
   - Capture offscreen preview renders of `BulkPriceAdjustDialog` in Dark and Light themes.
