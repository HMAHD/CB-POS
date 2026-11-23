# Purchasing Issues

> **Audit status:** Purchasing responsibility, activation, data-loading, and GRN commit paths traced against product code `69fd64a`.
> **Evidence limits:** complete supplier/GRN/payables journey states, screenshots, and measured SQLite/PostgreSQL latency remain pending.

## Responsibility trace

`PurchaseView` is 2,038 lines because it currently owns four full screens inside one tab set:

| Area | Responsibilities | Representative lines |
|---|---|---|
| Suppliers | list, add, edit, deactivate, permission/read-only state | `purchase_view.py:360-417`, `773-887` |
| New GRN | supplier/product selection, editable lines, unit conversion, PO prefill, discrepancy confirmation, receive-goods commit | `419-540`, `889-1346` |
| GRN history | filters, model replacement, empty state, detail dialog | `542-618`, `739-771` |
| Payables | supplier list/search, detail header, ledger ranges, payment, adjustment | `1350-1929` |
| Cross-cutting | translation, activation reload, unit-conversion feature-state rebuild | `620-737`, `1931-2038` |

These are real responsibility seams, unlike a split based only on line count. They also align with the provisional Phase U purchasing hypotheses, but U.0 has not approved those implementations.

## U0-PURCHASE-001 — Purchasing loads and commits database work synchronously on the Qt UI thread

- **Risk:** R2 — important responsiveness and recovery defect.
- **State:** synchronous paths confirmed; latency measurement and focused regressions still required before repair.
- **Affected paths:** tab activation, supplier search/CRUD, GRN history, product/open-order loading, GRN commit, payable list/detail/ledger/payment/adjustment.
- **Evidence:**
  - `on_activated()` directly reloads the visible tab through service calls (`cbpos/ui/views/purchase_view.py:2025-2038`).
  - Supplier, history, product, order, and payable loaders call database-backed services synchronously (`purchase_view.py:739-775`, `889-914`, `1138-1183`, `1596-1742`).
  - Payables search calls `SupplierService.get_all_suppliers()` again for each filter invocation before filtering in memory (`purchase_view.py:1601-1611`).
  - `commit_grn()` performs a discrepancy query and then executes the atomic `PurchaseService.receive_goods()` transaction directly in the click handler (`purchase_view.py:1189-1346`).
- **Concrete scenario:** the shop uses network PostgreSQL and a query or row lock is slow. Entering Purchasing, switching tabs, typing in payable search, or confirming a GRN keeps the Qt event loop inside the service call. The window cannot repaint or accept keyboard/mouse input until it returns.
- **Wrong behavior:** a routine navigation/search action or stock-receipt commit can make the whole POS appear hung, with no responsive loading/committing state and no stale-result protection.

### Smallest repair acceptance criteria

1. Database-backed tab loading and GRN/payable mutations execute outside the Qt UI thread.
2. Each tab exposes loading, empty, error, permission-denied, success, cancellation/re-entry states as applicable; stale results from a previous tab/request are ignored.
3. Only one GRN commit can run at a time. The worker receives an immutable `GrnRequest`, never widgets, and returns detached result data.
4. Permission approval and discrepancy confirmation remain explicit; `PurchaseService.receive_goods()` remains the single atomic stock/payable/document seam.
5. Payable text filtering does not issue an unbounded database query per keystroke; reuse the loaded result or debounce one cancellable request.
6. Focused Qt regressions use controllable delayed services, prove a UI timer still fires, and assert database adapters ran outside `threading.main_thread()` for activation and commit paths.
7. PostgreSQL contention behavior is not claimed until the integration environment runs.
