# Price Lists: Bulk Adjust List Prices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bulk adjustment tool for price lists allowing managers to apply percentage discounts, fixed reductions, or margin-over-cost rules across selected items, categories, or entire price lists in a single atomic transaction with below-cost warning protection and consolidated audit logging.

**Architecture:** Decouple preview calculations from persistence in `PriceListService`. Provide an interactive `BulkPriceAdjustDialog` that computes live preview rows and below-cost warnings as managers alter rules or rounding, and executes the batch update in a single atomic database transaction with exactly one consolidated Activity Log entry.

**Tech Stack:** Python 3.12, PyQt6, SQLAlchemy, SQLite, Decimal arithmetic.

**Spec:** [docs/superpowers/specs/2026-10-17-bulk-price-adjustment-design.md](file:///Users/akash/Documents/CB-POS/docs/superpowers/specs/2026-10-17-bulk-price-adjustment-design.md)

## Global Constraints

- Must never modify master retail prices (`Product.price`) or purchase costs (`Product.cost`). Only `PriceListItem.price` is inserted or updated.
- Every bulk adjustment must execute in a single database transaction and write exactly one consolidated `PRICE_LIST_BULK_ADJUST` entry in the Activity Log.
- All monetary calculations must use `Decimal` with rounding options (`EXACT`, `NEAREST_1`, `NEAREST_5`, `CHARM_99`) and clamp prices at minimum `0.00`.
- If any calculated item price is below `product.cost`, a visible warning must be displayed in the preview and require explicit manager confirmation before saving.
- Complete trilingual localization across English (`en`), Sinhala (`si`), and Tamil (`ta`).
- Dark and Light theme styling matching the CB-POS design system.

## Review Focus

- When an item's unit cost is zero or negative (`product.cost <= 0`), `MARGIN_OVER_COST` must fall back to regular base price with a `"Cost not set"` flag without throwing a division-by-zero or calculation error.
- When an adjustment rule calculates a negative price (e.g. `base - 100` on a Rs. 50 item), the price must clamp to `Decimal("0.00")` instead of saving a negative number.
- When a price list already has overrides for some items, a bulk adjustment across "All Products" must update existing overrides and insert overrides for products without one, preserving atomic integrity.
- If a database failure occurs mid-batch during apply, the transaction must roll back completely so no partial prices are saved.
- Changing live language (`retranslate_ui`) while `PriceListView` is open must keep the bulk adjust button, headers, and dialog strings properly localized.

---

### Task 1: Core Service - Pricing Calculations & Preview Generation

**Files:**
- Modify: `cbpos/core/services/price_list_service.py`
- Test: `tests/unit/test_bulk_price_adjust.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass
  class BulkAdjustmentRule:
      rule_type: str        # "PERCENTAGE_OFF", "FIXED_OFF", "FIXED_MARKUP", "MARGIN_OVER_COST"
      value: Decimal
      rounding: str         # "EXACT", "NEAREST_1", "NEAREST_5", "CHARM_99"
      scope: str            # "SELECTED", "CATEGORY", "ALL"
      category_id: int | None = None
      product_ids: list[int] | None = None

  @dataclass
  class BulkPreviewItem:
      product_id: int
      product_name: str
      category_name: str
      cost: Decimal
      base_price: Decimal
      old_list_price: Decimal | None
      new_list_price: Decimal
      margin_percent: Decimal | None
      is_below_cost: bool
      loss_amount: Decimal

  def calculate_preview(self, list_id: int, rule: BulkAdjustmentRule) -> list[BulkPreviewItem]
  ```

- [ ] **Step 1: Write the failing unit tests for calculations and preview**

```python
# tests/unit/test_bulk_price_adjust.py
from decimal import Decimal
import pytest
from cbpos.core.services.price_list_service import BulkAdjustmentRule, PriceListService
from cbpos.core.models import Product, PriceList, Category


def test_percentage_discount_calculation(db_session):
    service = PriceListService()
    # verify base * (1 - 0.10) with EXACT rounding
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_bulk_price_adjust.py -v`
Expected: FAIL with `ImportError: cannot import name 'BulkAdjustmentRule'`

- [ ] **Step 3: Implement calculation algorithms and `calculate_preview` in `cbpos/core/services/price_list_service.py`**

Implement `BulkAdjustmentRule`, `BulkPreviewItem`, and rounding helpers:
- `EXACT`: `quantize(Decimal("0.01"))`
- `NEAREST_1`: round to nearest `Decimal("1.00")`
- `NEAREST_5`: round to nearest `Decimal("5.00")`
- `CHARM_99`: `Decimal(int(val)) + Decimal("0.99")` (clamping at 0.00)
- Below-cost detection: `is_below_cost = new_list_price < cost if cost > 0 else False`

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_bulk_price_adjust.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cbpos/core/services/price_list_service.py tests/unit/test_bulk_price_adjust.py
git commit -m "feat(pricing): add bulk price adjustment preview calculations and rounding rules (#544)"
```

---

### Task 2: Core Service - Atomic Batch Apply & Single Audit Entry

**Files:**
- Modify: `cbpos/core/constants/audit.py`
- Modify: `cbpos/core/services/price_list_service.py`
- Test: `tests/unit/test_bulk_price_adjust.py`

**Interfaces:**
- Consumes: `BulkPreviewItem` from Task 1
- Produces:
  ```python
  def apply_bulk_adjust(self, list_id: int, items: list[BulkPreviewItem], rule_summary: str) -> int
  ```

- [ ] **Step 1: Write the failing unit tests for atomic apply and audit log**

```python
# In tests/unit/test_bulk_price_adjust.py
def test_atomic_bulk_apply_and_single_audit_entry(db_session):
    # Verify all items update in 1 transaction
    # Verify Product.price and Product.cost are completely untouched
    # Verify exactly 1 Activity Log entry with action "PRICE_LIST_BULK_ADJUST"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_bulk_price_adjust.py -k test_atomic_bulk_apply -v`
Expected: FAIL with `AttributeError: 'PriceListService' object has no attribute 'apply_bulk_adjust'`

- [ ] **Step 3: Add `PRICE_LIST_BULK_ADJUST` constant and implement `apply_bulk_adjust`**

In `cbpos/core/constants/audit.py`:
- Add `PRICE_LIST_BULK_ADJUST = "PRICE_LIST_BULK_ADJUST"`

In `cbpos/core/services/price_list_service.py`:
- Implement `apply_bulk_adjust(list_id, items, rule_summary)`:
  - Open session transaction.
  - Upsert `PriceListItem` for each item.
  - Update `PriceList.last_modified = datetime.now()`.
  - Call `LoggingService.add_change(session, "PRICE_LIST_BULK_ADJUST", PRICING_EVENT, price_list.name, snapshot_changes({"items_updated": len(items), "rule": rule_summary, "below_cost_count": below_cost_count}))`.
  - Commit atomically.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_bulk_price_adjust.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cbpos/core/constants/audit.py cbpos/core/services/price_list_service.py tests/unit/test_bulk_price_adjust.py
git commit -m "feat(pricing): implement atomic bulk price list apply with consolidated audit logging (#544)"
```

---

### Task 3: Localization (Trilingual) & Styling

**Files:**
- Modify: `cbpos/i18n/en.json`
- Modify: `cbpos/i18n/si.json`
- Modify: `cbpos/i18n/ta.json`
- Modify: `cbpos/ui/styles/dark.qss`
- Modify: `cbpos/ui/styles/light.qss`
- Test: `tests/unit/test_bulk_price_adjust.py`

**Interfaces:**
- Produces: i18n keys under `pricelist.bulk_*` and styling classes for bulk dialog.

- [ ] **Step 1: Write test verifying trilingual translations exist**

```python
def test_bulk_adjust_i18n_keys_exist(language):
    # Check all pricelist.bulk_* keys in en, si, ta
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_bulk_price_adjust.py -k test_bulk_adjust_i18n -v`
Expected: FAIL on missing translation keys.

- [ ] **Step 3: Add translation keys and QSS stylesheets**

Add complete translations in `en.json`, `si.json`, `ta.json`:
- `pricelist.btn_bulk_adjust`: "Bulk Adjust..." / "තොග වශයෙන් සකසන්න..." / "மொத்தமாக சரிசெய்..."
- Dialog titles, scopes, rules, rounding, warning banners, confirmation messages.
Add dark and light theme styles in `dark.qss` and `light.qss`:
- `#BulkPriceAdjustDialog`, `#BulkWarningBanner`, `#BulkPreviewTable`, `#BulkScopeGroup`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_bulk_price_adjust.py -k test_bulk_adjust_i18n -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cbpos/i18n/ cbpos/ui/styles/ tests/unit/test_bulk_price_adjust.py
git commit -m "feat(i18n): add trilingual translations and styles for bulk price adjust (#544)"
```

---

### Task 4: UI Dialog (`BulkPriceAdjustDialog`) & PriceListView Integration

**Files:**
- Create: `cbpos/ui/dialogs/bulk_price_adjust_dialog.py`
- Modify: `cbpos/ui/views/pricelist_view.py`
- Test: `tests/unit/test_bulk_price_adjust_ui.py`

**Interfaces:**
- Consumes:
  - `PriceListService.calculate_preview()`
  - `PriceListService.apply_bulk_adjust()`
- Produces:
  - `BulkPriceAdjustDialog` class
  - `PriceListView.open_bulk_adjust_dialog()`
  - `self.btn_bulk_adjust` in `PriceListView`

- [ ] **Step 1: Write failing UI tests**

```python
# tests/unit/test_bulk_price_adjust_ui.py
def test_bulk_price_adjust_dialog_preview_and_apply(qtbot, db_session):
    # Test dialog initialization with selected items
    # Test changing rule recalculates preview table
    # Test confirmation when below cost
    # Test applying saves overrides and refreshes PriceListView
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_bulk_price_adjust_ui.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cbpos.ui.dialogs.bulk_price_adjust_dialog'`

- [ ] **Step 3: Implement `BulkPriceAdjustDialog` and integrate into `PriceListView`**

1. Create `cbpos/ui/dialogs/bulk_price_adjust_dialog.py`:
   - Left panel: Scope radios, Category combo, Rule combo, Value input, Rounding combo, Below-cost alert.
   - Right panel: Header info, Preview `QTableWidget` with colored margin/warning badges, Cancel and Apply buttons.
   - Signal/slot connections: triggers `_recalculate_preview()` on any input edit.
   - Confirmation dialog on Apply if `below_cost_count > 0`.
2. Update `cbpos/ui/views/pricelist_view.py`:
   - Add `self.btn_bulk_adjust` in `set_price_row`.
   - Add "Bulk Adjust..." action in `_show_item_context_menu`.
   - Add `QShortcut(QKeySequence("Ctrl+B"), self.table)` connected to `open_bulk_adjust_dialog`.
   - On accept, reload price list table.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_bulk_price_adjust_ui.py tests/unit/test_bulk_price_adjust.py -v`
Expected: PASS

- [ ] **Step 5: Visual verification**

Render offscreen screenshots of `BulkPriceAdjustDialog` in Dark and Light themes:
- `bulk_price_adjust_dark_1000x650.png`
- `bulk_price_adjust_light_1000x650.png`
Inspect with `view_file`.

- [ ] **Step 6: Commit**

```bash
git add cbpos/ui/dialogs/bulk_price_adjust_dialog.py cbpos/ui/views/pricelist_view.py tests/unit/test_bulk_price_adjust_ui.py
git commit -m "feat(pricelist): integrate bulk price adjustment dialog with live preview and safety warnings (#544)"
```
