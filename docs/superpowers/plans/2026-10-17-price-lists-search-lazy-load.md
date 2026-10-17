# Implementation Plan: Price Lists Search and Lazy Loading (#545)

Implement search filter and smooth infinite scrolling (incremental lazy loading) in `PriceListView` for large product catalogs.

- **Issue**: #545 ([REC-10])
- **Branch**: `feat/price-lists-search-lazy-load-545`

---

## Task Breakdown

### Task 1: Add Translations (Trilingual)
- **Files**:
  - `cbpos/i18n/en.json`
  - `cbpos/i18n/si.json`
  - `cbpos/i18n/ta.json`
- Add keys:
  - `pricelist.search_placeholder`
  - `pricelist.showing_count`
  - `pricelist.total_products_count`

### Task 2: Implement Unit Tests for Search and Lazy Loading
- **File**: `tests/unit/test_pricelist_search_lazy_load.py`
- Test cases:
  1. `test_lazy_loading_initial_batch`: Catalog of 120 products loads first 50 rows into `table`.
  2. `test_lazy_loading_scroll_trigger`: Triggering scroll near bottom loads next 50 rows.
  3. `test_search_filter_by_name`: Entering query filters items by product name and updates table.
  4. `test_search_filter_by_barcode`: Filtering by barcode matches correct product.
  5. `test_search_clear_restores_catalog`: Clearing search input resets filter and loads initial batch of full catalog.
  6. `test_footer_counter_updates`: Verifies footer shows correct "Showing X of Y" or "Total: X".
  7. `test_responsive_with_5000_products`: Creating 5,000 products in database and selecting price list completes in < 500ms without freezing.

### Task 3: Implement Search Box and Lazy Loading in `PriceListView`
- **File**: `cbpos/ui/views/pricelist_view.py`
- Steps:
  1. In `init_ui()`: Add `self.search_input = QLineEdit()` above `self.table`. Connect to `self._on_search_text_changed`.
  2. Connect `self.table.verticalScrollBar().valueChanged` to `self._on_table_scroll`.
  3. Implement `_get_all_products_cached()` with caching in `self._cached_products`.
  4. In `load_items()`: Filter products according to `self.search_input.text()`, reset table rows to 0, and load initial batch (`BATCH_SIZE = 50`).
  5. Implement `_load_next_batch()` to insert the next chunk of rows into `self.table` with `setUpdatesEnabled(False/True)` for optimal rendering speed.
  6. In `retranslate_ui()`: Update `self.search_input.setPlaceholderText(...)` and re-render footer label.
  7. Add CSS styling if needed in `cbpos/ui/styles/dark.qss` and `light.qss`.

### Task 4: Verify All Existing Tests & Linting
- Run all price list tests:
  - `pytest tests/unit/test_pricelist*.py tests/unit/test_bulk_price_adjust.py`
- Run linting:
  - `ruff check cbpos/ tests/`
  - `ruff format --check cbpos/ tests/`

### Task 5: PR and Merge
- Commit changes.
- Push branch `feat/price-lists-search-lazy-load-545`.
- Create PR linking `Fixes #545`.
- Merge and verify issue closure.
