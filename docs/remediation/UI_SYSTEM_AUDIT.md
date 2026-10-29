# UI System Audit — Purchasing, Stock, Dashboard, Reports and Cross-Cutting Design

**Date:** 2026-10-29 · **Source:** owner's screenshots and notes, traced to code on `main` @ `5a45f5b`.
**Status:** analysis complete; decisions pending (see the end of this file).

## The one root cause

CB POS has no **design system layer** between screens and Qt. Each screen builds its own tables, headers, filters, menus, dialogs and colours. So:
- the same thing looks different on every screen;
- one fix doesn't fix anything else;
- every new screen adds new variations.

Evidence:
- 172 distinct hex colours in `dark.qss`, 150 in `light.qss`, and 176 hard-coded hex values in 36 Python UI files;
- one-off title styles;
- 11 hand-rolled date filters;
- 11 context menus, only 1 with icons;
- 21 screens with no shared "load when shown" behaviour.

## Findings

### A. Purchasing → Suppliers (screenshot 1)

| # | Problem | Root cause (code) |
|---|---|---|
| A1 | Columns are squeezed to the left with "Munchee …" truncation, and a large empty area sits to the right | The column resize modes are set on an empty header (`purchase_view.py:291`). `load_suppliers` then calls `setModel(...)` (`:641`) on every refresh, and the new model's sections fall back to defaults. Configuration runs before the data exists |
| A2 | Grey gutter on the left of the table | The vertical (row-number) header isn't hidden |
| A3 | Internal database **ID** shown as the first column | IDs mean nothing to a shop owner. Show the supplier code or name |
| A4 | No search or filter on the supplier list, and no double-click-to-edit | Table built by hand; no shared table component |
| A5 | Edit and Deactivate are always enabled; Deactivate is a solid red primary-size button | No selection-aware action state. The destructive action gets the same weight as Add |

### B. Purchasing → New GRN (screenshot 2)

| # | Problem | Root cause |
|---|---|---|
| B1 | Form looks unstructured: labels of different widths, a giant Ref # field, Date squeezed to the right, Supplier, Ref and Date crammed into one row | Hand-built `QHBoxLayout` rows instead of a form grid or section layout |
| B2 | The Date field shows tiny spin arrows, with no calendar | `QDateEdit` without `setCalendarPopup(True)`; no shared date input |
| B3 | **"Receive against Order" has no workflow behind it.** A Purchase Order can only be created from Reorder, for one supplier (`reorder_view.py:181-233`). There is **no Purchase Orders screen** to create, view, edit, send, print or cancel a PO, and the GRN dropdown (`purchase_view.py:341, 818-822`) only lists document numbers | The PO lifecycle exists in the service (`PurchaseOrderService.create_purchase_order`, `get_open_orders`) but has no UI |
| B4 | New GRN is a tab next to lists, so it reads as "a place" instead of "an action" | Information architecture: creating a document should be an action launched from the GRN list |

### C. Purchasing → Payables and the Make Supplier Payment dialog (screenshot 3)

| # | Problem | Root cause |
|---|---|---|
| C1 | The "Supplier Payables" title is 22 px **bold cyan**, a style used nowhere else | One-off QSS rules `QLabel#CreditPageTitle, QLabel#PayablePageTitle` (`dark.qss:3846`). The shared `PageHeader` widget exists but only 1 file uses it (most page headers were removed in 0e94b07) |
| C2 | The supplier ledger header looks improvised: a "< Back to Suppliers" text link, a grey card, a red "Payable", stray phone and "Last Payment" text, solid cyan buttons | No shared "detail page header" (title, key figures, actions) |
| C3 | Ledger columns cluster: Date and Type on the left, Debit, Credit and Balance far right, with a wide empty middle | The description/doc column doesn't stretch; per-table column config |
| C4 | Footer totals in red and green text | Semantic colour used for plain figures. Red should mean "problem", not "purchases" |
| C5 | Dialog title shown twice (window title bar and body heading) | The dialog adds its own title label (`supplier_payment_dialog.py:53`) on top of `setWindowTitle` |
| C6 | Method combo is narrow while the other fields are full width; "Pay Full" is a cyan accent button unlike any other secondary action | Hand-built form rows and button styles |
| C7 | The footer is hand-rolled (`:145`), with two equally weighted big buttons | Doesn't use `make_dialog_footer`, the standard footer |
| C8 | No payment date (always "now"), no "balance after payment" preview, no warning when paying more than outstanding, and the Reference field doesn't change with the method (cheque number vs transfer reference) | Missing form behaviour |
| C9 | Methods are filtered by **name** ("excluding Credit") | The same name-matching bug class as Phase 3A; use the payment-method kind |

### D. Stock Take and Reorder

| # | Problem |
|---|---|
| D1 | Stock Take and Reorder are separate sidebar entries, though both are "keep stock right" tasks. The owner wants them under one section, with Stock Take renamed to match what it does (counting) |
| D2 | Reorder lists low-stock items with **no context menu and no row actions**. The only action is "Create Purchase Order", which fails with "Select items from a single supplier…", a rule the screen never explains before the click (prevent, don't error: §0.7) |
| D3 | Phase 4 #864 already specifies grouping by supplier and "one PO per supplier"; the UI should present it that way from the start |

### E. Cross-cutting behaviour

| # | Problem | Root cause |
|---|---|---|
| E1 | **Data appears only after pressing Refresh** | Management views are created once and cached (`management_view.py:_get_or_create_view`). `switch_tab` (`:227-233`) only changes the visible page; views get no "activated" call. 21 views have load methods and no reload-on-show |
| E2 | Context menus have no icons (1 of 11 has) | No shared menu builder |
| E3 | Colours everywhere | No token layer: hex values in QSS and Python |
| E4 | Some labels show a dark background on light or themed surfaces | Labels inherit a non-transparent background from broad QSS rules; there's no "text on surface" rule |
| E5 | Date/time filters differ on every screen | The shared `DateRangePicker` is used in only 3 files; 11 others build their own |

### F. Header and Dashboard

| # | Problem |
|---|---|
| F1 | "POS / Sales" is a solid **green** button found nowhere else; Logout is a red outline. The header has no consistent button language (`#ManagementHeaderPosBtn`, `#ManagementHeaderLogoutBtn`) |
| F2 | Date and time are hard to read: low contrast, small |
| F3 | Dashboard date filter does nothing until Refresh is pressed. The From/To edits only constrain each other (`dashboard_view.py:310-311`); data reloads only on `btn_refresh` |
| F4 | The calendar popup is cramped and shows few numbers: the default `QCalendarWidget`, unstyled and unsized |

### G. Reports (`docs/remediation/report_enhace.md`)

The **architecture** in that document is right and should be adopted:
- a declarative report registry (`ReportDefinition`, `ColumnDef`, `KpiDef`, `FilterConfig`);
- one hub (card grid) plus one viewer;
- one table model (`QAbstractTableModel`, never `QTableWidget`);
- one query controller off the UI thread, with request-id cancellation;
- one PDF engine and one Excel exporter;
- a pinned totals row;
- KPIs that follow the filtered rows.

What must **not** be taken from it, because it conflicts with locked rules:
- **Its colour tokens** (`#16191D`…). Use the system tokens (§H).
- **`float()` in `format_cell_value`.** Money must use `Decimal` and `round_money` (D4).
- **Helvetica in the PDF.** It can't render Sinhala or Tamil. Use the Noto fonts with shaping (Phase 7 #806).
- **The `cb_pos/modules/...` paths.** The repo uses `cbpos/core/reports/` (definitions) and `cbpos/ui/views/reports/`.
- **Favourites in `QSettings`.** Reuse the existing favourites (#542).
- **The "CeyByte.com" spelling.** Branding is "CB POS · ceybyte.com" (§0.2).
- **Hard-coded English labels.** Everything goes through `_t()`.

Related open bugs that this rebuild should close: #950 (filter bar layout), #806, #843–#845, #880.

## Proposed foundation (H): a design system layer

1. **Tokens.** One file of named tokens per theme: surfaces 0–3, text primary/secondary/muted, border, accent, success, warning, danger, info, focus, and spacing and radius steps. `dark.qss` and `light.qss` reference **only** tokens through the existing `{{TOKEN}}` template mechanism. A guardrail bans hex outside the tokens file (QSS and Python).
2. **Components** (`cbpos/ui/components/`), each styled once:
   - `PageHeader`: title, optional subtitle and key figures, plus an action area.
   - `ActionBar`: buttons in the primary, secondary, ghost and danger variants, selection-aware.
   - `DataTable`: `QTableView` plus a column spec (format, alignment, stretch), with search, empty, loading and error states, a context menu with icons and shortcuts, double-click to open, hidden row header and persisted widths.
   - `FilterBar`: search, a `DateRangeFilter` with presets, and dropdowns. It emits one `FilterState`, and the same component is used by the dashboard, reports, documents and ledgers.
   - `KpiStrip`.
   - `FormDialog`: header, a two-column form grid, and the standard footer.
   - `EntityPicker`: a searchable combo.
   - `StatusPill`.
   - `ContextMenu` builder: icon, label, shortcut and permission per action.
3. **View lifecycle contract.** Every management view implements `on_activated()`. `ManagementView.switch_tab` and inner tab widgets call it. A view reloads if it is stale; a change signal such as "suppliers changed" marks dependent views stale.
4. **Information architecture.**
   - Purchasing tabs: **Suppliers | Purchase Orders (new) | Goods Received | Payables**. New PO and New GRN are actions with focused forms, and a GRN can be started from a PO.
   - The sidebar gets one **Stock Control** section with tabs **Reorder | Stock Count | Adjustments**. Adjustments comes from Phase 4 #794.
5. **Guardrails** to keep it consistent:
   - no hex outside the tokens file;
   - no `QTableWidget` in new code;
   - every management view implements `on_activated`;
   - every `QMenu` action has an icon;
   - every dialog uses the standard footer.

## Decisions (filled in from the owner's answers)

_See the bottom of the conversation's decision log; recorded as D-numbers in DECISIONS.md once answered._
