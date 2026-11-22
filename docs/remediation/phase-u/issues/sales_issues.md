# Sales Issues

> **Audit status:** Sales responsibility map and checkout execution path traced against product code `69fd64a`.
> **Evidence limits:** complete Sales journey/state screenshots and measured SQLite/PostgreSQL latency remain pending.

## Responsibility trace

`SalesView` is 2,530 lines, but the finding below comes from execution ownership—not file length. The class currently owns these distinct orchestration areas:

| Responsibility | Representative methods / lines | Existing deep seams |
|---|---|---|
| Screen composition, translation, theme, responsive layout | `init_ui`, `retranslate_ui`, `resizeEvent` (`sales_view.py:160-761`) | shared widgets, `ThemeService` |
| Barcode, scale, search, autocomplete | `process_barcode`, `_add_scale_item`, `setup_autocomplete` (`787-868`, `1590-1646`) | `ProductService`, `ScaleService`, `AutocompleteLoadWorker` |
| Cart rendering and totals | `update_cart_display` (`870-1065`) | `CartService`, `TaxService` |
| Power-cut autosave and recovery | `_schedule_autosave` through `check_autosave_recovery` (`1094-1245`) | `CartAutosaveService`, `CartAutosaveWorker` |
| Customer selection and cart customer state | `select_customer` through `clear_customer` (`1247-1298`) | `CustomerService`, customer dialogs |
| Payment, sale commit, and post-sale completion | `process_payment`, `_finalize_sale`, `quick_pay` (`1300-1413`, `2381-2505`) | `PaymentDialog`, `TransactionService`, receipt/peripheral modules |
| Held bills, session exit, multi-order switching | `hold_bill` through `void_bill`; order methods (`1415-1586`, `2171-2244`) | `SuspendedTransactionService`, autosave seam |
| Cart mutation, permissions, discounts, serials | context menu through serial editing (`1648-2169`) | Cart methods, permission helper, serial dialogs/services |
| Operational dialog launchers | receive payment, reprint, refund, warranty, price board, history, shift (`2235-2341`) | feature dialogs and services |
| Cash drawer and print error feedback | `open_cash_drawer`, `_on_print_error` (`2343-2379`) | `CashDrawerService`, `PrintWorker` |

This establishes natural responsibility clusters for later design. It does not prove that each cluster should become a new file or class. Existing services already hold most business rules; U.0 still needs journey, state, performance, and test-surface evidence before proposing an extraction.

## U0-SALES-001 — Sale commits run synchronously on the Qt UI thread

- **Risk:** R2 — important checkout responsiveness and recovery defect.
- **State:** synchronous path confirmed; latency measurement and focused regression still required before repair.
- **Affected paths:** Payment dialog completion (F5/F10) and Quick Pay (F12).
- **Evidence:**
  - `process_payment()` invokes `TransactionService.process_sale()` directly from the Payment dialog's finish callback (`cbpos/ui/views/sales_view.py:1327-1402`).
  - `quick_pay()` invokes the same service directly from its shortcut handler (`sales_view.py:2440-2505`).
  - `TransactionService.process_sale()` immediately enters `_execute_sale()` (`cbpos/core/services/transaction_service.py:75-114`). `_execute_sale()` opens a database session, queries payment methods and products, takes stock/customer row locks, writes the sale and related history, and commits (`transaction_service.py:583-724`).
- **Concrete scenario:** a network PostgreSQL connection is slow, another transaction holds a required row lock, or SQLite is temporarily busy. The cashier confirms payment. The Qt event loop remains inside the database transaction, so the payment/POS window cannot repaint or respond until the database call succeeds or fails.
- **Wrong behavior:** the release-critical checkout surface appears hung at the moment payment is committed, with no responsive in-progress state or cancellation-safe failure presentation.

### Smallest repair acceptance criteria

1. Sale persistence executes outside the Qt UI thread for both normal payment and Quick Pay.
2. Only one commit attempt can run at a time; payment/cart controls remain disabled until one terminal result is handled.
3. The worker receives an immutable checkout snapshot and never reads or mutates Qt widgets.
4. Success returns detached sale/receipt data needed by `_finalize_sale`; failure keeps the cart and payment context intact and presents the existing translated error.
5. Existing autosave generation/invalidation, tax-invoice, proforma-conversion, loyalty, serial, warranty, receipt, and cash-drawer ordering invariants remain covered.
6. A focused Qt regression replaces `TransactionService.process_sale` with a controllable wait, proves a Qt timer still fires, and asserts the service ran outside `threading.main_thread()` for both entry points.
7. PostgreSQL contention behavior is not claimed until the integration environment runs.
