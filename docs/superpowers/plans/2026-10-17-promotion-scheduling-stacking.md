# Implementation Plan: Promotion Scheduling and Stacking (Fixes #636)

**Date**: 2026-10-17  
**Branch**: `feat/promotion-scheduling-stacking-636`  
**Issue**: #636 ([UI-062-C])  

---

## Task 1: Database Model & Alembic Migration
- **Files**:
  - `cbpos/core/models/__init__.py`: Add `daily_start` and `daily_end` (nullable `Time`) to `Promotion`.
  - `alembic/versions/<hash>_add_daily_time_window_to_promotions.py`: Create migration for `daily_start` and `daily_end`.
- **Verification**: Run `uv run alembic upgrade head` and verify SQLite schema.

## Task 2: ConfigService Default & SalesTaxPage Setting
- **Files**:
  - `cbpos/core/services/config_service.py`: Add `"promotion_stack_with_price_lists": False` to `DEFAULTS`.
  - `cbpos/ui/views/settings_pages/sales_tax.py`:
    - Add `self.chk_promo_stacking = QCheckBox()` in Tab 1 (Sales).
    - Wire into `load()`, `save()`, `restore_defaults()`, and `retranslate_ui()`.
- **Verification**: Verify setting loads and saves through `SalesTaxPage`.

## Task 3: PricingService Daily Window & Stacking Evaluation
- **Files**:
  - `cbpos/core/services/pricing_service.py`:
    - In `calculate_price()`, check `promo.daily_start` and `promo.daily_end` against `now.time()`.
    - Evaluate `promotion_stack_with_price_lists`:
      - If `False`: Compare best promo price calculated from standard retail price vs price list price, returning the minimum.
      - If `True`: Calculate promo price against price list price.
- **Verification**: Unit tests covering time windows and stacking modes.

## Task 4: PromotionService Updates & Overlap Detection
- **Files**:
  - `cbpos/core/services/promotion_service.py`:
    - Update `_promotion_fields()`, `create_promotion()`, and `update_promotion()` to handle `daily_start` and `daily_end`.
    - Implement `find_overlapping(start_time, end_time, days_of_week=None, daily_start=None, daily_end=None, category_id=None, exclude_id=None)`.
- **Verification**: Service unit tests for creation, updating, and overlap detection.

## Task 5: PromotionDialog UI Enhancements
- **Files**:
  - `cbpos/ui/dialogs/promotion_dialog.py`:
    - Add "All Day" checkbox (`self.chk_all_day`, default `True`).
    - Add `self.daily_start_time` and `self.daily_end_time` (`QTimeEdit`), visible/enabled when "All Day" is unchecked.
    - Add Price List Stacking disclosure label showing whether promotions stack or use best-of according to `ConfigService`.
    - Add overlap check before saving: if overlapping promotions are found, show an informative non-blocking warning explaining that the higher discount applies.
    - Update `get_data()` to include `daily_start` and `daily_end`.
    - Update form population when editing existing promotion.
- **Verification**: Manual/automated dialog tests checking field population and warning behavior.

## Task 6: Trilingual Translations
- **Files**:
  - `cbpos/i18n/en.json`
  - `cbpos/i18n/si.json`
  - `cbpos/i18n/ta.json`
- **Keys**:
  - `promotion.all_day_label`
  - `promotion.daily_time_window`
  - `promotion.daily_start_time`
  - `promotion.daily_end_time`
  - `promotion.daily_time_invalid`
  - `promotion.stacking_disclosure_best_of`
  - `promotion.stacking_disclosure_stack`
  - `promotion.overlap_warning_title`
  - `promotion.overlap_warning_message`
  - `sales_tax.promo_stack_with_price_lists`
  - `sales_tax.promo_stack_with_price_lists_hint`
- **Verification**: `tests/unit/test_translations_complete.py`.

## Task 7: Comprehensive Unit Tests & Visual Verification
- **Files**:
  - `tests/unit/test_promotion_scheduling_and_stacking.py`:
    - Daily time window active vs inactive hours.
    - Stacking on vs off behavior with price lists.
    - Overlap detection with matching/different categories, days of week, and daily hours.
  - Scratch script for dark/light screenshot verification.
- **Verification**: All unit tests pass, ruff lint and format pass.
