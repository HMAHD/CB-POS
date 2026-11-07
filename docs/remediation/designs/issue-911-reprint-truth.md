# Design Note: Issue #911 — Receipt Reprint Authorisation and Document Truth

## Context & Security Risk
A cashier can void a cash sale or process a refund and subsequently print an ordinary "CASH RECEIPT / DUPLICATE" with no indication of void or refund status, pocketing cash undetected. No permission gates reprints and no audit log captures duplicate receipt issuance.

## Architecture & Service Seam
Introduce a single service: `ReceiptReprintService` in `cbpos/core/services/receipt_reprint_service.py`:
- Method signature: `reprint(sale_id: int, user_id: int, approver_id: int | None = None) -> ReprintJob`
- Enforces `Permissions.SALES_REPRINT` on the effective authorizer (approver if present, else user).
- Refuses voided sales: raises `ValueError("reprint_void")`.
- Dispatches to appropriate builder:
  - Refund documents (`refund_of_sale_id` set, `payment_method == "REFUND"`, or `CN-*` document number) render via `RefundReceiptBuilder` with credit-note title, original receipt reference, and `DUPLICATE` marking.
  - Regular sales render via `SalesReceiptBuilder` with `is_reprint=True` (`DUPLICATE` header and footer).
  - Partially refunded sales (derived from `RefundService.refund_state(sale_id) == "PARTIAL"`) query active credit note numbers and append `"Part refunded — see {numbers}"` (`receipt.part_refunded_note`).
- Writes an `AuditLog` record: `action="REPRINT_RECEIPT"`, `event_type="TRANSACTION"`, recording document number, actor user ID, and approver ID.
- Returns `ReprintJob(commands=..., document_number=..., is_refund=...)` to decouple print command generation from asynchronous printing drivers.

## Permissions & Migration
- Add `Permissions.SALES_REPRINT = "sales.reprint"` under the `Sales` group.
- Update `DatabaseSetupService` and `scripts/seed.py` to grant `sales.reprint` to Admin, Manager, and Cashier default roles.
- Add Alembic migration granting `sales.reprint` to any role currently holding `sales.view`.
- Add translations in `en.json`, `si.json`, and `ta.json` for `permissions.sales_reprint`, `reprint.void_blocked`, and `receipt.part_refunded_note`.

## UI Integration
- Entry points: `ReceiptReprintDialog`, `SaleHistoryDialog`, and `DocumentBrowserView`.
- Each calls `check_permission_with_override(Permissions.SALES_REPRINT, self)` and routes execution to `ReceiptReprintService.reprint(...)`.
- VOID sales remain visible for searching and tracking, displayed with a VOID status pill, with Reprint button disabled and tooltip `"Voided sales can't be reprinted."` (`reprint.void_blocked`).

