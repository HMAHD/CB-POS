# Phase U — UI System: Shared Components and Screen Migration

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0 (especially §0.7, the UI gate), `docs/remediation/UI_SYSTEM_AUDIT.md`, and decisions D16–D20 in `DECISIONS.md`.
> **Two tracks.**
> - **Foundation (UF-x)** is built by Claude (D19). Don't start a foundation item.
> - **Migration (UM-x)** is yours. Each one lists the foundation items it needs. **Don't start a migration until its foundation items are merged.** Check that the component exists in `cbpos/ui/components/`; if it doesn't, tell the human.
> Verified against `main` @ `393d377` on 2026-10-29.

## Goal

Every screen is built from the same few components. A change to one component, or to `cbpos/ui/styles/tokens.py`, restyles every screen the same way. No screen gets one-off styling, colours or layouts (D16).

## Already done (don't redo)

| Item | Where | Issue |
|---|---|---|
| View lifecycle: views reload when shown (`Activatable.on_activated`) | `cbpos/ui/components/activation.py` | #959 (closed) |
| Colour tokens: QSS uses `{{TOKEN}}` only; `ThemeService.render_stylesheet()` | `cbpos/ui/styles/tokens.py` | merged in #960 |
| Theme callbacks bound to their widget (`register_theme_callback(cb, owner=self)`) | `theme_service.py` | #953 (closed) |
| Column layouts survive `setModel` (`configure_table_columns`) | `cbpos/ui/widgets/table_helpers.py` | #961 (PR #962) |
| Button variants: `class="primary" / "secondary" / "danger" / "accent" / "warning" / "link"` | both QSS files | already existed; **use them, don't add new ones** |

## Rules for every UI item in this phase

1. **Reuse first:**
   - the components in `cbpos/ui/components/`;
   - the button classes above;
   - `make_dialog_footer` (`cbpos/ui/widgets/dialog_footer.py`);
   - `configure_table_columns` and `batch_table_update` (`table_helpers.py`);
   - icons from `cbpos/ui/resources/icons.py`.

   A new widget style is a design-system change: ask (§0.5).
2. **No colour literals.** No hex in Python UI code or QSS. Use QSS `objectName` or `class` selectors, and tokens for colours. The guardrails (`tests/guardrails/test_colour_tokens.py`, `test_design_system_guardrails.py`) must stay green.
3. **Green means success or money-in, red means danger or money-owed.** Neither is used for ordinary buttons, titles or plain figures. Primary actions use `class="primary"`.
4. **Every management view implements `on_activated()`**, enforced by `tests/ui/shell/test_view_activation.py`.
5. **Run the §0.7 UI gate for every item:**
   - screenshots in dark and light, in English and Sinhala/Tamil, at 1366×768;
   - a keyboard-only walkthrough;
   - every state covered: loading, empty, error, permission-denied.

---

## Track 1 — Foundation (Claude)

### UF-1 — DataTable and ContextMenu builder

- **Fixes:** A4, A5, E2.
- **Builds:** `cbpos/ui/components/data_table.py`.
  - A `QTableView` plus `ColumnSpec(key, header_key, align, stretch|fit, format)`, built on `configure_table_columns`.
  - Hidden row header, a search box option, and empty, loading and error states (via `attach_table_empty_state`).
  - Double-click runs the default action.
  - Row actions are declared once (`RowAction(key, label_key, icon, permission, default=False, danger=False)`). They drive the right-click menu (with icons and shortcuts), the action bar's enabled state (selection-aware), and permission hiding.
- **Builds:** `cbpos/ui/components/context_menu.py`, `build_menu(actions, parent)`, so every menu shows icons.
- **Done when:** Suppliers runs on it as the pilot, and a guardrail requires every `QMenu.addAction` in `cbpos/ui` to pass an icon.

### UF-2 — PageHeader and DetailHeader

- **Fixes:** C1, C2.
- **Builds:** `PageHeader(title_key, subtitle_key=None, actions=[...])` for list pages, and `DetailHeader(title, back_action, figures=[(label_key, value, meaning)], actions=[...])` for detail pages such as the supplier ledger or customer statement.
  - `meaning` is one of neutral, success or danger, and drives token colours through QSS properties.
  - There is one title style across the app. The one-off rules `#PayablePageTitle` and `#CreditPageTitle` are deleted.

### UF-3 — FormDialog

- **Fixes:** B1, C5–C7.
- **Builds:** `FormDialog(title_key)` with:
  - a two-column form grid (label column of fixed width, fields full width);
  - optional sections and inline field errors;
  - `make_dialog_footer` (primary + cancel);
  - Enter submits and Esc cancels.
- No duplicate in-body title: the window title is the title.

### UF-4 — FilterBar and DateRangeFilter

- **Fixes:** E5, F4.
- **Builds:** `DateRangeFilter`, built on the existing `cbpos/ui/widgets/date_range_picker.py` (keep its API):
  - presets: Today, Yesterday, This week, This month, Last month, Custom;
  - a half-open range (Phase 6 #912);
  - a styled, readable calendar popup;
  - emits `range_changed`.
- **Builds:** `FilterBar(search=…, date_range=…, choices=[…])`, which emits one `FilterState`.
- **Debounce:** the filter bar fires once per user change, not once per keystroke.

---

## Track 2 — Migration (Gemini)

Each item: read the linked audit rows, use the named components, and pass the UI gate. Sizes: S < 1 day, M 1–3 days, L > 3 days.

### UM-1 — Purchasing tabs and a Purchase Orders screen

**Needs:** UF-1, UF-3 · **Size:** L · **Audit:** B3, B4 · **Decision:** D17

- **Problem.** A Purchase Order can only be created from Reorder, for one supplier. Nothing lets a user see, edit, print, send or cancel a PO, and "Receive against Order" on the GRN tab is a bare dropdown.
- **Tabs:** Suppliers | **Purchase Orders** | Goods Received | Payables. The tab index constants and `PurchaseView.on_activated` must follow.
- **Purchase Orders tab** (a DataTable):
  - columns: number, supplier, date, status (Draft, Ordered, Partly received, Received, Cancelled), items, total;
  - row actions: Open, Edit (Draft only), Mark ordered, Print/PDF, **Receive goods** (opens New GRN prefilled), Cancel (with a reason; audited);
  - `New PO` opens a FormDialog: supplier (searchable), lines (product, qty, expected cost), notes.
- **Service:** extend `PurchaseOrderService` (`cbpos/core/services/purchase_order_service.py`) with `list_orders(filter)`, `update_draft`, `mark_ordered`, `cancel(reason, user)`. Status changes write AuditLog entries, and permissions are checked at the service level (`purchase.create_po`, new; follow the Phase 5 guardrail).
- **Goods Received tab:** the GRN list, as today's history, plus `New GRN` as an action (UM-2). "Receive goods" from a PO sets the existing `prefill_grn_items(items, purchase_order_id)` (`purchase_view.py:~788`).
- **Don't:**
  - create a second PO model;
  - let Reorder keep its own PO dialog. Reorder's "Create Purchase Order" opens this same form, prefilled.
- **Tests:**
  - service: draft → ordered → partly received → received, and cancel;
  - UI: Receive goods from a PO prefills the GRN.

### UM-2 — New GRN as a focused form

**Needs:** UF-3 · **Size:** M · **Audit:** B1, B2 · **Builds on:** Phase 4.3 (`PurchaseService.receive_goods`) if merged

- **Header section:** Supplier (searchable), Supplier invoice no., Invoice date (calendar popup, max today), Linked PO (read-only when started from a PO). Two columns on wide screens, one on narrow.
- **Lines section:** a DataTable with product, qty, unit cost and line total; qty and cost are validated (Phase 4 #902); remove-line works.
- **Footer:** totals (subtotal, input VAT, total) right-aligned, then `[Receive goods] [Cancel]`.

### UM-3 — Supplier payment dialog

**Needs:** UF-3 · **Size:** M · **Audit:** C5–C9

- FormDialog fields: Amount (with a "Pay full balance" **link button**, not a coloured button), Payment date (default today, not in the future), Method, Reference, Note.
- **The reference label follows the method:**
  - "Cheque number" for CHEQUE;
  - "Transfer reference" for TRANSFER;
  - hidden for cash.
- **A live summary line:** "Outstanding Rs X → after this payment Rs Y". If the amount is more than outstanding, an inline warning appears: "This pays Rs Z more than you owe. The supplier will owe you this amount." It's allowed, consistent with Phase 4 #920.
- **Methods by kind, not name:** list methods whose kind isn't CREDIT, using Phase 3A `method_kind` once merged. Until then, keep the current behaviour and mark it `shortcut: name-based until #854-family kinds land`.
- The service records the payment date.

### UM-4 — Payables list and supplier ledger

**Needs:** UF-1, UF-2 · **Size:** M · **Audit:** C1–C4

- **List:** a PageHeader (no cyan title) and a DataTable (supplier, phone, payable, overdue days, last payment).
- **Detail:**
  - a DetailHeader with back, supplier name, Payable (danger meaning only when > 0), Overdue, Last payment, and actions Make payment and Adjust;
  - a ledger DataTable where the Description/Doc column stretches and Debit, Credit and Balance are right-aligned;
  - a footer totals row in neutral text.

### UM-5 — Stock Control section

**Needs:** UF-1 · **Size:** M · **Audit:** D1–D3 · **Decision:** D18

- **Sidebar:** one **Stock Control** entry replaces Stock Take and Reorder, with tabs **Reorder | Stock Count | Adjustments**.
  - Rename "Stock Take" to "Stock Count" in all three languages; keys are already translated, so follow §0.12 P7.
  - Adjustments uses the Phase 4 #794 dialog. Until that lands, the tab shows an empty state pointing to Inventory → Adjust stock.
- **Reorder:**
  - rows grouped by supplier;
  - row actions: Create PO for this supplier (opens UM-1's form, prefilled), Adjust reorder level, Open product;
  - "Create purchase orders" with a mixed selection creates **one PO per supplier**, after a confirmation that lists them.

  It never shows the old "single supplier" error. Prevent, don't error.
- **Navigation:** keep `MANAGEMENT_TAB_PERMISSIONS` correct (Phase 5 #858) and update the view index map in `management_view.py`.

### UM-6 — Management header bar

**Needs:** nothing · **Size:** S · **Audit:** F1, F2, E4

- **POS / Sales:** `class="primary"`.
- **Logout:** `class="secondary"`, with a danger-coloured icon only.
- **Clock:** `TEXT_SECONDARY` token, tabular figures, at least 13 px.
- **Text backgrounds:** labels on themed surfaces get `background: transparent` through one generic rule (`QLabel { background: transparent; }` where safe). Fix the specific offenders and list them in the PR.

### UM-7 — Dashboard date filter

**Needs:** UF-4 · **Size:** S · **Audit:** F3

- Replace the dashboard's own From/To edits (`dashboard_view.py:~286-330`) with `DateRangeFilter`.
- A range change reloads the period data automatically, through the existing worker (no Refresh needed), and saves the range as today (`dashboard_periodic_date_*` settings).

### UM-8 — Colours in Python UI code and inline stylesheets

**Needs:** nothing · **Size:** M · **Audit:** E3 · **Includes:** #956

- 176 hex literals in 36 Python files under `cbpos/ui`, plus 8 inline `setStyleSheet` calls (#956).
- Move each one to QSS (`objectName`, `class`, or a dynamic property plus the shared property-refresh helper, #694), using tokens.
- Where Python truly needs a colour value (charts, painted delegates), read it from `THEME_TOKENS[ThemeService.current_theme]`.
- Add a guardrail: no hex in `cbpos/ui/**/*.py` outside `styles/tokens.py`, with an allow-list that may only shrink.

### UM-9 — Reports module rebuild

**Needs:** UF-1, UF-4 · **Size:** L (epic) · **Audit:** G · **Supersedes:** #950 (layout)

- Follow the **architecture** in `docs/remediation/report_enhace.md`:
  - a registry of `ReportDefinition`s;
  - a hub (card grid) and a viewer;
  - one `QAbstractTableModel`;
  - a controller off the UI thread, with request-id cancellation;
  - one PDF engine and one Excel exporter;
  - a pinned totals row;
  - KPIs that follow the filtered rows.
- **Don't take from it**, because it conflicts with locked rules (audit G):
  - its colours, `float`, Helvetica, `cb_pos/modules` paths, `QSettings` favourites and the "CeyByte.com" spelling;
  - English literals.

  Use tokens, `Decimal`, the Phase 7 #806 shaped Noto fonts, `cbpos/core/reports/` and `cbpos/ui/views/reports/`, the existing favourites (#542), "CB POS · ceybyte.com" and `_t()`.
- **Report semantics follow Phase 6:** `sale_filters`, half-open dates, `required_permission`.
- **Batches:**
  1. the registry plus the existing reports ported;
  2. hub and viewer;
  3. exporters;
  4. remove the old viewer.

  When the old viewer is gone, close #950 as superseded, provided the new viewer passes the same 1024 px and 1366 px layout tests.

---

## Issue map

| Item | Issue | Owner | Needs |
|---|---|---|---|
| UF-1 | #963 | Claude | — |
| UF-2 | #964 | Claude | — |
| UF-3 | #965 | Claude | — |
| UF-4 | #966 | Claude | — |
| UM-1 | #967 | Gemini | UF-1, UF-3 |
| UM-2 | #968 | Gemini | UF-3 |
| UM-3 | #969 | Gemini | UF-3 |
| UM-4 | #970 | Gemini | UF-1, UF-2 |
| UM-5 | #971 | Gemini | UF-1 |
| UM-6 | #972 | Gemini | — |
| UM-7 | #973 | Gemini | UF-4 |
| UM-8 | #974 | Gemini | — |
| UM-9 | #975 | Gemini | UF-1, UF-4 |

## Exit gate

- [ ] All UF and UM items merged and closed with closing comments (§0.10).
- [ ] Guardrails green: colour tokens (QSS and Python), menus with icons, views implement `on_activated`.
- [ ] Remove the strict-xfail markers for #950 and #956.
- [ ] Screenshots of every migrated screen in both themes plus si/ta attached to its PR.
- [ ] `UI_SYSTEM_AUDIT.md` updated: each finding marked fixed with its PR number.
