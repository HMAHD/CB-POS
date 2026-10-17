# Promotion Scheduling & Stacking Design

**Issue**: #636 ([UI-062-C])  
**Date**: 2026-10-17  
**Status**: Proposed  

---

## 1. Intent and Why
Currently, promotions only store an absolute `start_time` and `end_time` (datetime). A "Happy Hour" running from Oct 1 to Oct 7 with time set to 17:00–19:00 ends up running 24 hours a day across that whole date range because there is no concept of a daily recurring time window.
Additionally, when a customer has a custom Price List (e.g., Wholesale) and an item has an active Promotion, checkout silently stacks the discounts without disclosure.
Furthermore, when two promotions overlap on the same category/store, the weaker one silently never applies with no warning given to store managers during creation or editing.

---

## 2. User Decisions
1. **Daily Time Window**: Add an "All Day" toggle (default `True`). When unchecked, store managers can configure a recurring daily time window (`daily_start` to `daily_end`, e.g., 17:00 to 19:00).
2. **Price List Stacking Setting**: Add a setting in Settings (`promotion_stack_with_price_lists`, default `False` = "Best Price / Non-stacking"). When `False`, customers receive the lower price between the price list price and the promotion discount from retail price. When `True`, promotions stack on top of the price list price. In `PromotionDialog`, disclose the active stacking rule clearly.
3. **Overlapping Promotions Warning**: Non-blocking warning banner in `PromotionDialog` naming any overlapping promotions and explaining that CB-POS applies whichever discount produces the lower price.

---

## 3. Goals, Non-Goals, Anti-Goals

### Goals
- Add nullable `daily_start: Time` and `daily_end: Time` columns to the `promotions` table via an Alembic migration.
- Update `pricing_service.py` to evaluate the daily time window against the current time of day (`now.time()`) when specified.
- Update `pricing_service.py` to respect `ConfigService.get("promotion_stack_with_price_lists")` (default `False`).
- Update `PromotionDialog`:
  - "All Day" checkbox (checked by default).
  - Daily start/end `QTimeEdit` pickers visible/enabled when "All Day" is unchecked.
  - Price list stacking disclosure label based on the current setting.
  - Non-blocking overlap warning when saving or changing dates/times/category.
- Add `find_overlapping()` method to `PromotionService`.
- Add `promotion_stack_with_price_lists` toggle to `SalesTaxPage` (Tab 1: Sales).
- Complete trilingual localization in `en.json`, `si.json`, and `ta.json`.
- Comprehensive unit and integration test coverage.

### Non-Goals
- Changing promotion types (`PERCENTAGE`, `FIXED_AMOUNT`).
- Multiple disjoint daily windows per single promotion (a single daily window per promotion is standard and sufficient).

### Anti-Goals
- Do NOT break existing promotions in databases (nullable columns, default `None` / "All day" preserves exact legacy behavior).
- Do NOT block saving when promotions overlap (non-blocking informative warning).

---

## 4. Architecture and Schema Changes

### A. Database Model & Migration
In `cbpos/core/models/__init__.py`:
```python
class Promotion(Base):
    ...
    daily_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    daily_end: Mapped[time | None] = mapped_column(Time, nullable=True)
```
Alembic migration `xxxx_add_daily_time_window_to_promotions.py` adding `daily_start` and `daily_end` (sa.Time, nullable=True) to table `promotions`.

### B. Pricing Service (`cbpos/core/services/pricing_service.py`)
In `calculate_price()`:
1. Daily time window check:
   ```python
   if promo.daily_start and promo.daily_end:
       current_time = now.time()
       if not (promo.daily_start <= current_time <= promo.daily_end):
           continue
   ```
2. Stacking check:
   Read `stack_with_price_lists = ConfigService.get("promotion_stack_with_price_lists")` (default `False`).
   - If `stack_with_price_lists` is `False` (default):
     - Calculate promo price from base retail `product.price`.
     - Compare with `price_list_item.price` (if any).
     - Pick the minimum (best-of).
   - If `True`:
     - Calculate promo price from `price_list_item.price` (stacked).

### C. Promotion Service (`cbpos/core/services/promotion_service.py`)
- Update `create_promotion` and `update_promotion` to accept `daily_start` and `daily_end`.
- Add `find_overlapping(session, start_time, end_time, days_of_week=None, daily_start=None, daily_end=None, category_id=None, exclude_id=None) -> list[Promotion]`.

### D. Settings View (`cbpos/ui/views/settings_pages/sales_tax.py`)
- Add setting `promotion_stack_with_price_lists` (default `False`) in `ConfigService.DEFAULTS`.
- Add checkbox/setting row in `SalesTaxPage` Tab 1 (Sales):
  `self.chk_promo_stacking = QCheckBox()` with label `_t("sales_tax.promo_stack_with_price_lists")`.

### E. Promotion Dialog (`cbpos/ui/dialogs/promotion_dialog.py`)
- UI elements:
  - `self.chk_all_day = QCheckBox(_t("promotion.all_day_label"))`
  - `self.daily_start_time = QTimeEdit()`
  - `self.daily_end_time = QTimeEdit()`
  - Overlap warning banner (`QFrame` with warning icon and text, initially hidden, shown if overlapping promotions exist).
  - Stacking disclosure note:
    Explains whether promo discounts stack or use best-of.
- On save:
  - If daily window specified and `daily_start >= daily_end`, show validation error.
  - Check for overlaps via `PromotionService.find_overlapping()`. If overlapping promotions are found, show confirmation dialog or banner explaining that the bigger discount applies.

---

## 5. Verification Plan
- Unit tests in `tests/unit/test_promotion_scheduling_and_stacking.py`:
  - Daily time window applies promotion during window and skips outside window.
  - "All day" promotions apply at all hours.
  - Price list stacking setting: when False, best-of is applied; when True, promo stacks on price list.
  - Overlap detection finds overlapping active promotions by date range, category, days of week, and daily time window.
  - Exclusion of `exclude_id` during edit.
- Settings page tests: `SalesTaxPage` loads and saves `promotion_stack_with_price_lists`.
- Trilingual translation completeness test.
- Visual inspection & screenshot capture in dark and light modes.
