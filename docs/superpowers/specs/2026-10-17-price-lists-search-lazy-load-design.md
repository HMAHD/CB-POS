# Design Specification: Price Lists Search and Lazy Loading (#545)

## 1. Overview
In `PriceListView`, every time a price list is selected from the sidebar, the application synchronously fetches the entire product catalog (`get_all_products()`) and constructs `QTableWidgetItem` objects for all products in the database. In stores with catalogs of thousands of products (e.g., 5,000+ items), this freezes the UI thread for 2–4 seconds on every list switch, and provides no search capability to find specific items in the list.

This design introduces:
1. A **search box** above the price table to filter products instantaneously by name, barcode, or ID.
2. **Smooth infinite scrolling (incremental lazy loading)** that loads an initial batch (e.g., 50 items) immediately upon list selection and loads subsequent batches as the user scrolls down, ensuring instant responsiveness (< 20ms) regardless of catalog size.
3. **Catalog caching** in `PriceListView` so switching between price lists reuses the in-memory product list and only queries price list overrides.
4. **Trilingual localization** (English, Sinhala, Tamil) and light/dark theme compatibility.

---

## 2. Architecture & Data Flow

```
+-----------------------------------------------------------+
| PriceListView (QWidget)                                   |
|                                                           |
| +-------------------------------------------------------+ |
| | Header: Title | Status Badge | Dates                  | |
| +-------------------------------------------------------+ |
| | Toolbar: [Search Products... (QLineEdit)]             | |
| +-------------------------------------------------------+ |
| | PriceListDataTable (QTableWidget)                     | |
| |   [Batch 1: items 0..49 rendered]                     | |
| |   ... on scroll near bottom -> render items 50..99    | |
| +-------------------------------------------------------+ |
| | Actions: [Bulk Adjust] [Set Item Price] [Remove]      | |
| +-------------------------------------------------------+ |
| | Footer: Showing 50 of 5,000 products | Shortcut Hint  | |
+-----------------------------------------------------------+
```

### 2.1 Catalog Caching
- `self._cached_products: list[Product] | None`: Cached list of all active products.
- Populated on first demand via `ProductService.get_all_products()`.
- Invalidated when `load_lists()` or external catalog refreshes occur, or method `invalidate_catalog_cache()` is called.
- When switching between price lists, `self._cached_products` is reused, avoiding redundant database trips.

### 2.2 Search Filtering
- `self.search_input`: A `QLineEdit` placed directly below the header and above the table.
- Placeholder text: `_t("pricelist.search_placeholder")` ("Search products by name or barcode...").
- Connected to `textChanged` signal.
- In memory, filters `self._cached_products` against the lower-cased query:
  - `query in product.display_name.lower()`
  - `query in (product.barcode or "").lower()`
  - `query in str(product.id)`
  - Language name fields: `product.name_en`, `product.name_si`, `product.name_ta`.
- Resets the table scroll position and renders the first batch of matching products.

### 2.3 Incremental Lazy Loading
- Batch size: `BATCH_SIZE = 50`.
- Internal state:
  - `self._filtered_products: list[Product]`: Currently filtered products matching search.
  - `self._current_price_map: dict[int, Decimal]`: Overrides for the active price list.
  - `self._loaded_row_count: int`: Number of rows currently rendered in `self.table`.
- On list selection or search change:
  - `self.table.setRowCount(0)`
  - `self._loaded_row_count = 0`
  - `self._load_next_batch()` (renders up to 50 rows)
- On scroll:
  - `self.table.verticalScrollBar().valueChanged.connect(self._on_scroll)`
  - When `scroll_value >= scroll_bar.maximum() - 10` and `self._loaded_row_count < len(self._filtered_products)`:
    - Calls `self._load_next_batch()`, appending the next 50 rows.
- Performance:
  - Creating 50 `QTableWidgetItem` rows takes ~2-5ms, keeping the UI completely lag-free.
  - Even with 5,000 items, the user experience is silky smooth.

### 2.4 Footer Counter
- `self.lbl_product_count` displays:
  - If all items loaded: `_t("pricelist.total_products_count", count=total)` ("Total: 45 products").
  - If partially loaded (e.g., 50 of 5,000): `_t("pricelist.showing_count", count=loaded, total=total)` ("Showing 50 of 5,000 products").

---

## 3. Backward Compatibility & Test Invariants
- `self.table` remains a `QTableWidget` with the existing columns:
  - Col 0: Product ID (hidden)
  - Col 1: Product Name (stretch)
  - Col 2: Base Price
  - Col 3: List Price
- Existing methods (`edit_selected_item_price()`, `remove_selected_item_override()`, `_show_item_context_menu()`, `_on_table_selection_changed()`, `open_bulk_adjust_dialog()`) continue working seamlessly because they reference `self.table.item(...)` and row indices.
- All existing tests in `test_pricelist_*.py` pass without modification.

---

## 4. Localization
Keys to add:
- `pricelist.search_placeholder`:
  - `en`: "Search products by name or barcode..."
  - `si`: "නම හෝ බාර්කෝඩය මගින් නිෂ්පාදන සොයන්න..."
  - `ta`: "பெயர் அல்லது பார்கோடு மூலம் தயாரிப்புகளைத் தேடுங்கள்..."
- `pricelist.showing_count`:
  - `en`: "Showing {count} of {total} products"
  - `si`: "නිෂ්පාදන {total} න් {count} ක් පෙන්වයි"
  - `ta`: "{total} இல் {count} தயாரிப்புகள் காட்டப்படுகின்றன"
- `pricelist.total_products_count`:
  - `en`: "Total: {count} products"
  - `si`: "මුළු: නිෂ්පාදන {count}"
  - `ta`: "மொத்தம்: {count} தயாரிப்புகள்"
