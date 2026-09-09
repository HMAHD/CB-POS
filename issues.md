# CB-POS UI/UX Issue Catalog

Running log of UI/UX issues found during manual review. This is a **cataloging
document only** — nothing here gets fixed until we explicitly move to a fixing
pass. Each entry below is analyzed as if by a desktop-app UI/UX engineer:
what's wrong, why it matters to the actual end user (a non-technical Sri
Lankan shop owner/cashier), the concrete fix, and any feature idea the issue
surfaces along the way.

**How this works:** you send a screenshot + your notes on what's wrong → I
analyze it (checking the real code/behavior where relevant, not just guessing
from the picture) → I append a new entry below → we move to the next one.
Nothing gets "fixed" here, only logged.

## Status legend

- 🔴 `Open` — logged, not yet fixed
- 🟡 `In Progress` — actively being fixed
- 🟢 `Fixed` — fixed and verified
- ⚪ `Won't Fix` — reviewed, decided not to change (with reason)

## Severity legend

- **P0** — blocks or actively harms core POS workflow (checkout, sales)
- **P1** — clearly wrong/confusing, workaround exists
- **P2** — polish, inconsistency, or minor friction
- **P3** — nice-to-have / feature idea, not a defect

## Standing decisions

Product decisions made mid-catalog that apply going forward, so they
don't need re-litigating every time a new screen surfaces the same issue.

- **Only two themes: Dark and Light. No third "navy" sub-theme.**
  Decided 2026-09-06. Full context and confirmed scope in
  [UX-031](#ux-031-payables-uses-a-deliberate-but-undocumented-navy-sub-theme-shared-with-credit-book)
  — 6 locations found so far (Payables, Credit Book, Reports, Document
  Browser, Price Lists, Payment Methods). If a new screen under review
  turns out to use the `#001F3F`/`#0A1929`/`#0D2137`/`#112240`/`#00BCEB`
  palette, log it as a confirmed instance of this same decided fix, not
  as a new open question.
- **Table header/column alignment is a critical, app-wide design defect —
  flagged 2026-09-06 as something to address as one coordinated fix when
  the fixing phase starts, not table-by-table.** Full context and the
  confirmed scope (12+ tables so far) in
  [UX-077](#ux-077-nearly-every-table-in-the-app-has-the-same-headercontent-alignment-defect).
  If a new screen under review shows a table with truncated/misaligned
  headers or columns, log it as a confirmed instance of this already-known
  systemic pattern, not as an isolated one-off.

---

## Index

| ID | Title | Screen | Severity | Status | GitHub |
|----|-------|--------|----------|--------|--------|
| [UX-001](#ux-001-empty-cart-hides-the-entire-table-including-its-header) | Empty cart hides the entire table, including its header | POS main (Sales) | P1 | 🔴 Open | [#256](https://github.com/HMAHD/CB-POS/issues/256) |
| [UX-002](#ux-002-cart-table-numeric-columns-are-inconsistently-aligned-discounted-price-format-doesnt-match-regular-one) | Cart table numeric columns are inconsistently aligned, discounted price format doesn't match regular one | POS main (Sales) | P1 | 🔴 Open | [#350](https://github.com/HMAHD/CB-POS/issues/350) |
| [UX-003](#ux-003-customer-card-and-loyalty-points-are-two-disconnected-elements) | Customer card and loyalty points are two disconnected elements | POS main (Sales), ActionPanel | P1 | 🔴 Open | [#255](https://github.com/HMAHD/CB-POS/issues/255) |
| [UX-004](#ux-004-discount-highlight-only-tints-one-cell-of-the-row) | Discount highlight only tints one cell of the row | POS main (Sales) | P2 | 🔴 Open | [#265](https://github.com/HMAHD/CB-POS/issues/265) |
| [UX-005](#ux-005-empty-cart-placeholder-is-plain-text-with-no-visual-anchor) | Empty cart placeholder is plain text with no visual anchor | POS main (Sales) | P3 | 🔴 Open | [#257](https://github.com/HMAHD/CB-POS/issues/257) |
| [UX-006](#ux-006-customer-icon-bypasses-the-centralized-icon-system-no-points-icon-registered) | Customer icon bypasses the centralized icon system; no points icon registered | `cbpos/ui/widgets/action_panel.py` | P3 | 🔴 Open | [#266](https://github.com/HMAHD/CB-POS/issues/266) |
| [UX-007](#ux-007-applied-payments-list-is-hard-capped-at-160px-so-it-scrolls-and-clips-the-boundary-rows-remove-button-instead-of-expanding) | Applied Payments list is hard-capped at 160px, so it scrolls and clips the boundary row's remove button instead of expanding | Payment dialog | P1 | 🔴 Open | [#267](https://github.com/HMAHD/CB-POS/issues/267) |
| [UX-008](#ux-008-change-quantitychange-price-on-a-cart-line-use-a-raw-native-dialog-instead-of-the-apps-own-styled-one) | "Change Quantity"/"Change Price" on a cart line use a raw native dialog instead of the app's own styled one | POS main (Sales), cart line actions | P1 | 🔴 Open | [#268](https://github.com/HMAHD/CB-POS/issues/268) |
| [UX-009](#ux-009-select-customer-dialog-cannot-be-confirmed-from-the-keyboard-at-all) | Select Customer dialog cannot be confirmed from the keyboard at all | Select Customer dialog | P1 | 🔴 Open | [#264](https://github.com/HMAHD/CB-POS/issues/264) |
| [UX-010](#ux-010-select-customer-table-truncates-real-customer-names) | Select Customer table truncates real customer names | Select Customer dialog | P1 | 🔴 Open | [#351](https://github.com/HMAHD/CB-POS/issues/351) |
| [UX-011](#ux-011-select-customer-header-alignment-doesnt-match-cell-alignment-same-pattern-as-ux-002) | Select Customer header alignment doesn't match cell alignment — same pattern as UX-002 | Select Customer dialog | P2 | 🔴 Open | [#352](https://github.com/HMAHD/CB-POS/issues/352) |
| [UX-012](#ux-012-select-customer-table-skips-3-conventions-every-other-table-in-the-app-follows) | Select Customer table skips 3 conventions every other table in the app follows | Select Customer dialog | P2 | 🔴 Open | [#353](https://github.com/HMAHD/CB-POS/issues/353) |
| [UX-013](#ux-013-periodic-reports-date-picker-calendar-popup-renders-broken-reproduced-exactly) | Periodic Reports date-picker calendar popup renders broken (reproduced exactly) | Dashboard | P1 | 🔴 Open | [#364](https://github.com/HMAHD/CB-POS/issues/364) |
| [UX-014](#ux-014-total-sales-kpi-number-appears-clipped-in-the-reported-screenshot-couldnt-reproduce-yet) | Total Sales KPI number appears clipped in the reported screenshot (couldn't reproduce yet) | Dashboard | P1 | 🔴 Open | [#269](https://github.com/HMAHD/CB-POS/issues/269) |
| [UX-015](#ux-015-both-dashboard-background-workers-swallow-errors-silently-and-leave-the-ui-stuck) | Both dashboard background workers swallow errors silently and leave the UI stuck | Dashboard | P1 | 🔴 Open | [#270](https://github.com/HMAHD/CB-POS/issues/270) |
| [UX-016](#ux-016-periodic-reports-date-range-has-no-sanity-bounds-and-isnt-remembered) | Periodic Reports date range has no sanity bounds and isn't remembered | Dashboard | P2 | 🔴 Open | [#271](https://github.com/HMAHD/CB-POS/issues/271) |
| [UX-017](#ux-017-inventory-table-truncates-product-names-third-confirmed-instance-of-the-ux-010-pattern) | Inventory table truncates product names — third confirmed instance of the UX-010 pattern | Inventory | P1 | 🔴 Open | [#354](https://github.com/HMAHD/CB-POS/issues/354) |
| [UX-018](#ux-018-three-different-numeric-input-conventions-in-the-app-one-of-them-flagged-as-broken-in-its-own-code-comment-and-still-used-for-price) | Three different numeric-input conventions in the app — one of them flagged as broken in its own code comment, and still used for Price | Product Editor + app-wide | P1 | 🔴 Open | [#263](https://github.com/HMAHD/CB-POS/issues/263) |
| [UX-019](#ux-019-label-preview-dialog-has-a-hardcoded-navy-background-that-doesnt-match-the-dark-theme) | Label Preview dialog has a hardcoded navy background that doesn't match the dark theme | Label Preview dialog | P1 | 🔴 Open | [#272](https://github.com/HMAHD/CB-POS/issues/272) |
| [UX-020](#ux-020-csv-import-dialog-floating-thumbnail-investigated-likely-not-an-app-bug) | CSV Import dialog floating thumbnail — investigated, likely not an app bug | Import CSV dialog | ⚪ N/A | ⚪ Won't Fix | [#273](https://github.com/HMAHD/CB-POS/issues/273) |
| [UX-021](#ux-021-category-manager-tree-has-no-column-resize-mode-configured-causing-a-horizontal-scrollbar-and-a-squeezed-header) | Category Manager tree has no column resize-mode configured, causing a horizontal scrollbar and a squeezed header | Category Manager dialog | P2 | 🔴 Open | [#355](https://github.com/HMAHD/CB-POS/issues/355) |
| [UX-022](#ux-022-secondarydanger-button-class-convention-is-inconsistently-applied-across-3-dialogs) | Secondary/danger button class convention is inconsistently applied across 3 dialogs | Category Manager, Unit Manager, Label Print | P3 | 🔴 Open | [#274](https://github.com/HMAHD/CB-POS/issues/274) |
| [UX-023](#ux-023-management-view-shows-a-completely-blank-screen-until-the-first-sidebar-click-confirmed-regression) | Management view shows a completely blank screen until the first sidebar click (confirmed regression) | Management (all tabs) | P1 | 🔴 Open | [#275](https://github.com/HMAHD/CB-POS/issues/275) |
| [UX-024](#ux-024-management-sidebar-gets-permanently-stuck-collapsed-across-restarts-confirmed-root-cause) | Management sidebar gets permanently stuck collapsed across restarts (confirmed root cause) | Management, `CollapsibleSidebar` | P1 | 🔴 Open | [#276](https://github.com/HMAHD/CB-POS/issues/276) |
| [UX-025](#ux-025-add-supplier-dialog-has-zero-dialog-specific-styling-no-objectname-no-size-no-qss-at-all) | Add Supplier dialog has zero dialog-specific styling — no objectName, no size, no QSS at all | Suppliers tab | P1 | 🔴 Open | [#277](https://github.com/HMAHD/CB-POS/issues/277) |
| [UX-026](#ux-026-new-grn-add-product-search-is-a-genuinely-broken-feature-not-just-unpolished) | New GRN "Add Product" search is a genuinely broken feature, not just unpolished | New GRN tab | P0 | 🟢 Fixed | [#278](https://github.com/HMAHD/CB-POS/issues/278) |
| [UX-027](#ux-027-new-grn-header-row-supplierrefdate-has-no-width-balancing-date-field-looks-tiny) | New GRN header row (Supplier/Ref#/Date) has no width balancing — Date field looks tiny | New GRN tab | P2 | 🔴 Open | [#279](https://github.com/HMAHD/CB-POS/issues/279) |
| [UX-028](#ux-028-supplier-selection-combos-in-purchasing-are-plain-non-searchable-comboboxes) | Supplier-selection combos in Purchasing are plain, non-searchable comboboxes | New GRN, GRN History tabs | P1 | 🔴 Open | [#280](https://github.com/HMAHD/CB-POS/issues/280) |
| [UX-029](#ux-029-grn-history-status-filter-shows-all-suppliers-instead-of-all-statuses) | GRN History "Status" filter shows "All Suppliers" instead of "All Statuses" | GRN History tab | P2 | 🔴 Open | [#281](https://github.com/HMAHD/CB-POS/issues/281) |
| [UX-030](#ux-030-grn-history-and-payables-tables-have-no-empty-state-message) | GRN History and Payables tables have no empty-state message | GRN History, Payables tabs | P2 | 🔴 Open | [#258](https://github.com/HMAHD/CB-POS/issues/258) |
| [UX-031](#ux-031-payables-uses-a-deliberate-but-undocumented-navy-sub-theme-shared-with-credit-book) | Payables uses a deliberate but undocumented navy sub-theme, shared with Credit Book — DECIDED: retire app-wide, 6 locations confirmed | Payables, Credit Book, Reports, Document Browser, Price Lists, Payment Methods | P1 | 🔴 Open | [#260](https://github.com/HMAHD/CB-POS/issues/260) |
| [UX-032](#ux-032-payables-supplier-list-is-double-click-only-same-pattern-as-ux-009) | Payables supplier list is double-click-only — same pattern as UX-009 | Payables tab | P1 | 🔴 Open | [#372](https://github.com/HMAHD/CB-POS/issues/372) |
| [UX-033](#ux-033-payables-ledger-shows-zero-entries-despite-a-non-zero-balance-needs-one-live-check-to-fully-confirm) | Payables ledger shows zero entries despite a non-zero balance (needs one live check to fully confirm) | Payables tab | P1 | 🔴 Open | [#282](https://github.com/HMAHD/CB-POS/issues/282) |
| [UX-034](#ux-034-credit-book-outstanding-debt-column-header-is-clipped-to-tstanding-di) | Credit Book "Outstanding Debt" column header is clipped to "TSTANDING DI" | Credit Book | P1 | 🔴 Open | [#356](https://github.com/HMAHD/CB-POS/issues/356) |
| [UX-035](#ux-035-credit-book-customer-list-is-double-click-only-same-pattern-as-ux-009ux-032) | Credit Book customer list is double-click-only — same pattern as UX-009/UX-032 | Credit Book | P1 | 🔴 Open | [#373](https://github.com/HMAHD/CB-POS/issues/373) |
| [UX-036](#ux-036-adjust-balance-button-uses-the-apps-warning-color-for-a-routine-action) | "Adjust Balance" button uses the app's warning color for a routine action | Credit Book, customer detail | P2 | 🔴 Open | [#283](https://github.com/HMAHD/CB-POS/issues/283) |
| [UX-037](#ux-037-credit-book-ledger-shows-zero-entries-despite-a-non-zero-debt-same-pattern-as-ux-033-now-confirmed-on-a-second-screen) | Credit Book ledger shows zero entries despite a non-zero debt — same pattern as UX-033, now confirmed on a second screen | Credit Book, customer detail | P1 | 🔴 Open | [#284](https://github.com/HMAHD/CB-POS/issues/284) |
| [UX-038](#ux-038-new-customer-dialogs-commercial-tab-has-mismatched-field-widths-recurring-pattern-to-watch-for) | New Customer dialog's Commercial tab has mismatched field widths — recurring pattern to watch for | Customer Editor, Commercial tab | P1 | 🔴 Open | [#367](https://github.com/HMAHD/CB-POS/issues/367) |
| [UX-039](#ux-039-only-2-of-15-date-pickers-in-the-app-have-any-styling-at-all) | Only 2 of 15 date pickers in the app have any styling at all | App-wide (`QDateEdit`) | P1 | 🔴 Open | [#262](https://github.com/HMAHD/CB-POS/issues/262) |
| [UX-040](#ux-040-customer-statement-dialog-has-uneven-filter-row-and-summary-spacing) | Customer Statement dialog has uneven filter-row and summary spacing | Print Statement dialog | P2 | 🔴 Open | [#285](https://github.com/HMAHD/CB-POS/issues/285) |
| [UX-041](#ux-041-reports-screen-is-a-third-independent-navy-themed-screen-not-shared-with-ux-031) | Reports screen is a third, independent navy-themed screen — not shared with UX-031 | Reports | P1 | 🔴 Open | [#345](https://github.com/HMAHD/CB-POS/issues/345) |
| [UX-042](#ux-042-reports-category-panel-scales-far-wider-than-its-content-needs) | Reports category panel scales far wider than its content needs | Reports | P2 | 🔴 Open | [#286](https://github.com/HMAHD/CB-POS/issues/286) |
| [UX-043](#ux-043-no-shared-empty-state-component-every-screen-hand-builds-its-own) | No shared empty-state component — every screen hand-builds its own | App-wide | P3 | 🔴 Open | [#254](https://github.com/HMAHD/CB-POS/issues/254) |
| [UX-044](#ux-044-current-nav-item-highlight-is-much-weaker-when-the-sidebar-is-collapsed) | Current nav item highlight is much weaker when the sidebar is collapsed | Main sidebar (all screens) | P2 | 🔴 Open | [#287](https://github.com/HMAHD/CB-POS/issues/287) |
| [UX-045](#ux-045-pos-logout-buttons-still-use-the-leftover-string-padding-hack) | POS / Logout buttons still use the leftover string-padding hack | Main sidebar (all screens) | P3 | 🔴 Open | [#288](https://github.com/HMAHD/CB-POS/issues/288) |
| [UX-046](#ux-046-sidebar-widthexpanded-header-in-the-screenshot-doesnt-match-the-widths-in-code-needs-a-live-render-to-confirm) | Sidebar width/expanded header in the screenshot doesn't match the widths in code (needs a live render to confirm) | Main sidebar (all screens) | P2 | 🔴 Open | [#289](https://github.com/HMAHD/CB-POS/issues/289) |
| [UX-047](#ux-047-reports-date-picker-has-a-near-invisible-click-target-and-no-fixed-display-format) | Reports date picker has a near-invisible click target and no fixed display format | Reports | P1 | 🔴 Open | [#365](https://github.com/HMAHD/CB-POS/issues/365) |
| [UX-048](#ux-048-report-tables-last-column-always-stretches-truncating-the-first-columns-labels) | Report table's last column always stretches, truncating the first column's labels | Reports | P1 | 🔴 Open | [#357](https://github.com/HMAHD/CB-POS/issues/357) |
| [UX-049](#ux-049-every-report-type-shares-one-generic-renderer-with-zero-report-specific-treatment) | Every report type shares one generic renderer with zero report-specific treatment | Reports | P2 | 🔴 Open | [#290](https://github.com/HMAHD/CB-POS/issues/290) |
| [UX-050](#ux-050-pagination-controls-render-even-when-there-is-only-one-page) | Pagination controls render even when there is only one page | Reports | P3 | 🔴 Open | [#291](https://github.com/HMAHD/CB-POS/issues/291) |
| [UX-051](#ux-051-one-dialog-has-three-different-names-for-the-same-feature) | One dialog has three different names for the same feature | Document Browser | P1 | 🔴 Open | [#292](https://github.com/HMAHD/CB-POS/issues/292) |
| [UX-052](#ux-052-document-browser-table-has-three-competing-stretch-columns-truncating-type-and-total) | Document Browser table has three competing stretch columns, truncating TYPE and TOTAL | Document Browser | P1 | 🔴 Open | [#358](https://github.com/HMAHD/CB-POS/issues/358) |
| [UX-053](#ux-053-document-browser-doesnt-explain-what-its-for-or-why-to-use-it) | Document Browser doesn't explain what it's for or why to use it | Document Browser | P2 | 🔴 Open | [#293](https://github.com/HMAHD/CB-POS/issues/293) |
| [UX-054](#ux-054-proforma-dialogs-customer-field-looks-searchable-but-isnt) | Proforma dialog's Customer field looks searchable but isn't | Proforma/Quotation dialog | P1 | 🔴 Open | [#294](https://github.com/HMAHD/CB-POS/issues/294) |
| [UX-055](#ux-055-proforma-dialogs-validity-field-uses-the-same-known-broken-spinbox-stepper-pattern) | Proforma dialog's Validity field uses the same known-broken spinbox stepper pattern | Proforma/Quotation dialog | P2 | 🔴 Open | [#368](https://github.com/HMAHD/CB-POS/issues/368) |
| [UX-056](#ux-056-proforma-dialogs-line-items-table-has-no-empty-state-message) | Proforma dialog's line-items table has no empty-state message | Proforma/Quotation dialog | P2 | 🔴 Open | [#259](https://github.com/HMAHD/CB-POS/issues/259) |
| [UX-057](#ux-057-users-table-shows-the-same-id-number-twice) | Users table shows the same ID number twice | Users | P3 | 🔴 Open | [#295](https://github.com/HMAHD/CB-POS/issues/295) |
| [UX-058](#ux-058-no-ui-exists-to-createrenamedelete-a-role-even-though-the-backend-already-fully-supports-it) | No UI exists to create/rename/delete a role, even though the backend already fully supports it | Users | P1 | 🔴 Open | [#296](https://github.com/HMAHD/CB-POS/issues/296) |
| [UX-059](#ux-059-manage-permissions-save-changes-calls-a-method-that-doesnt-exist-every-save-will-crash) | "Manage Permissions" Save Changes calls a method that doesn't exist — every save will crash | Users, Manage Permissions dialog | P0 | 🟢 Fixed | [#297](https://github.com/HMAHD/CB-POS/issues/297) |
| [UX-060](#ux-060-permission-manager-isnt-missing-permissions-its-hiding-most-of-them-below-the-fold) | Permission Manager isn't missing permissions — it's hiding most of them below the fold | Users, Manage Permissions dialog | P2 | 🔴 Open | [#298](https://github.com/HMAHD/CB-POS/issues/298) |
| [UX-061](#ux-061-activity-log-details-column-is-forced-to-the-same-width-as-every-other-column) | Activity Log DETAILS column is forced to the same width as every other column | Users, Activity Log | P1 | 🔴 Open | [#359](https://github.com/HMAHD/CB-POS/issues/359) |
| [UX-062](#ux-062-the-apps-one-central-audit-logging-method-is-dead-code-and-would-crash-if-called-and-a-live-caller-has-the-same-bug) | The app's one central audit-logging method is dead code and would crash if called — and a live caller has the same bug | App-wide (audit logging) | P0 | 🟢 Fixed | [#299](https://github.com/HMAHD/CB-POS/issues/299) |
| [UX-063](#ux-063-void-refund-permission-changes-purchasing-and-credit-adjustments-have-zero-audit-trail) | Void, Refund, Permission changes, Purchasing, and Credit adjustments have zero audit trail | App-wide (audit logging) | P1 | 🔴 Open | [#300](https://github.com/HMAHD/CB-POS/issues/300) |
| [UX-064](#ux-064-activity-log-has-no-color-or-icon-coding-by-event-type) | Activity Log has no color or icon coding by event type | Users, Activity Log | P2 | 🔴 Open | [#301](https://github.com/HMAHD/CB-POS/issues/301) |
| [UX-065](#ux-065-activity-log-is-hardcoded-to-the-10-most-recent-rows-with-no-filter-ui) | Activity Log is hardcoded to the 10 most recent rows, with no filter UI | Users, Activity Log | P2 | 🔴 Open | [#302](https://github.com/HMAHD/CB-POS/issues/302) |
| [UX-066](#ux-066-valid-na-to-na-is-real-and-once-set-a-price-lists-dates-can-never-be-changed) | "Valid: N/A to N/A" is real, and once set, a price list's dates can never be changed | Price Lists | P1 | 🔴 Open | [#303](https://github.com/HMAHD/CB-POS/issues/303) |
| [UX-067](#ux-067-price-editing-is-double-click-only-and-reuses-the-same-known-broken-spinbox-stepper) | Price editing is double-click-only, and reuses the same known-broken spinbox stepper | Price Lists | P1 | 🔴 Open | [#369](https://github.com/HMAHD/CB-POS/issues/369) |
| [UX-068](#ux-068-a-price-list-cant-be-renamed-and-a-product-override-cant-be-removed-once-set) | A price list can't be renamed, and a product override can't be removed once set | Price Lists | P1 | 🔴 Open | [#304](https://github.com/HMAHD/CB-POS/issues/304) |
| [UX-069](#ux-069-new-price-list-dialogs-date-fields-work-but-are-unstyled-app-wide-gap) | New Price List dialog's date fields work but are unstyled (app-wide gap) | Price Lists | P2 | 🔴 Open | [#366](https://github.com/HMAHD/CB-POS/issues/366) |
| [UX-070](#ux-070-status-column-shows-the-same-static-list-level-value-on-every-product-row) | STATUS column shows the same static, list-level value on every product row | Price Lists | P2 | 🔴 Open | [#305](https://github.com/HMAHD/CB-POS/issues/305) |
| [UX-071](#ux-071-price-list-sidebar-is-cramped-plain-text-with-no-visual-hierarchy) | Price List sidebar is cramped, plain text with no visual hierarchy | Price Lists | P2 | 🔴 Open | [#306](https://github.com/HMAHD/CB-POS/issues/306) |
| [UX-072](#ux-072-promotions-arent-wired-into-checkout-at-all-the-feature-currently-affects-zero-real-sales) | Promotions aren't wired into checkout at all — CORRECTED: already worked, now proven by tests | Promotions & Campaigns | P0 | 🟢 Verified | [#307](https://github.com/HMAHD/CB-POS/issues/307) |
| [UX-073](#ux-073-promotions-have-zero-crud-beyond-create-no-edit-delete-or-deactivate-exists-anywhere) | Promotions have zero CRUD beyond Create — no edit, delete, or deactivate exists anywhere | Promotions & Campaigns | P1 | 🔴 Open | [#308](https://github.com/HMAHD/CB-POS/issues/308) |
| [UX-074](#ux-074-status-is-a-stored-flag-set-once-at-creation-and-never-re-evaluated-every-promotion-shows-active-forever) | STATUS is a stored flag set once at creation and never re-evaluated — every promotion shows "Active" forever | Promotions & Campaigns | P1 | 🔴 Open | [#309](https://github.com/HMAHD/CB-POS/issues/309) |
| [UX-075](#ux-075-promotions-name-column-truncates-the-same-global-stretch-pattern-found-repeatedly-elsewhere) | Promotions NAME column truncates — the same global-stretch pattern found repeatedly elsewhere | Promotions & Campaigns | P1 | 🔴 Open | [#360](https://github.com/HMAHD/CB-POS/issues/360) |
| [UX-076](#ux-076-create-promotion-dialog-is-generic-and-cant-actually-target-specific-products) | Create Promotion dialog is generic, and can't actually target specific products | Promotions & Campaigns | P1 | 🔴 Open | [#310](https://github.com/HMAHD/CB-POS/issues/310) |
| [UX-077](#ux-077-nearly-every-table-in-the-app-has-the-same-headercontent-alignment-defect) | Nearly every table in the app has the same header/content alignment defect | App-wide (every table reviewed so far) | P1 | 🔴 Open | [#261](https://github.com/HMAHD/CB-POS/issues/261) |
| [UX-078](#ux-078-the-counted-column-collapses-to-almost-nothing-making-its-own-input-editor-nearly-invisible) | The COUNTED column collapses to almost nothing, making its own input editor nearly invisible | Stock Take | P1 | 🔴 Open | [#361](https://github.com/HMAHD/CB-POS/issues/361) |
| [UX-079](#ux-079-stock-take-button-colors-contradict-the-apps-own-documented-palette-and-each-other) | Stock Take button colors contradict the app's own documented palette, and each other | Stock Take | P2 | 🔴 Open | [#311](https://github.com/HMAHD/CB-POS/issues/311) |
| [UX-080](#ux-080-draft-stock-counts-in-history-are-orphaned-no-way-to-resume-edit-or-delete-them) | DRAFT stock counts in History are orphaned — no way to resume, edit, or delete them | Stock Take | P1 | 🔴 Open | [#312](https://github.com/HMAHD/CB-POS/issues/312) |
| [UX-081](#ux-081-save-draft-is-a-no-op-counts-are-already-auto-saved-per-keystroke) | "Save Draft" is a no-op — counts are already auto-saved per keystroke | Stock Take | P2 | 🔴 Open | [#313](https://github.com/HMAHD/CB-POS/issues/313) |
| [UX-082](#ux-082-sidebar-nav-icons-and-labels-have-zero-gap-correcting-ux-045) | Sidebar nav icons and labels have zero gap (correcting UX-045) | Main sidebar (all screens) | P1 | 🔴 Open | [#314](https://github.com/HMAHD/CB-POS/issues/314) |
| [UX-083](#ux-083-sidebar-redesign-dull-flat-treatment-and-poslogout-need-real-visual-hierarchy) | Sidebar redesign: dull flat treatment, and POS/Logout need real visual hierarchy | Main sidebar (all screens) | P2 | 🔴 Open | [#315](https://github.com/HMAHD/CB-POS/issues/315) |
| [UX-084](#ux-084-management-screens-use-4-different-navigation-patterns-with-no-consistent-page-title) | Management screens use 4 different navigation patterns, with no consistent page title | App-wide (Management section) | P1 | 🔴 Open | [#316](https://github.com/HMAHD/CB-POS/issues/316) |
| [UX-085](#ux-085-settings-footer-bar-being-hidden-not-reserved-creates-a-70px-height-jump-between-pages) | Settings' footer bar being hidden (not reserved) creates a 70px height jump between pages | Settings | P2 | 🔴 Open | [#317](https://github.com/HMAHD/CB-POS/issues/317) |
| [UX-086](#ux-086-settings-appearance-tab-has-3-mismatched-field-widths-and-the-same-broken-spinbox-stepper) | Settings Appearance tab has 3 mismatched field widths, and the same broken spinbox stepper | Settings | P2 | 🔴 Open | [#370](https://github.com/HMAHD/CB-POS/issues/370) |
| [UX-087](#ux-087-report-time-and-sales-tax-fields-have-the-same-mismatched-width-problem-the-fix-is-already-in-the-same-file) | Report Time and Sales Tax fields have the same mismatched-width problem — the fix is already in the same file | Settings | P2 | 🔴 Open | [#371](https://github.com/HMAHD/CB-POS/issues/371) |
| [UX-088](#ux-088-good-pattern-worth-reusing-the-gmail-help-guide-should-become-the-apps-standard-for-technical-fields) | Good pattern worth reusing: the Gmail help guide should become the app's standard for technical fields | Settings, app-wide | P3 | 🔴 Open | [#318](https://github.com/HMAHD/CB-POS/issues/318) |
| [UX-089](#ux-089-checkbox-hover-is-already-universal-in-css-the-perceived-inconsistency-traces-to-ux-060-instead) | Checkbox hover is already universal in CSS — the perceived inconsistency traces to UX-060 instead | Settings, app-wide | P3 | 🔴 Open | [#319](https://github.com/HMAHD/CB-POS/issues/319) |
| [UX-090](#ux-090-daily-auto-report-has-two-independent-reliability-bugs-confirming-your-suspicion) | Daily Auto-Report has two independent reliability bugs, confirming your suspicion | Settings → Shop Info → Email | P1 | 🔴 Open | [#320](https://github.com/HMAHD/CB-POS/issues/320) |
| [UX-091](#ux-091-cut-drawer-tab-label-is-silently-eaten-by-qts-mnemonic-parser) | "Cut & Drawer" tab label is silently eaten by Qt's mnemonic parser | Settings → Hardware | P1 | 🔴 Open | [#321](https://github.com/HMAHD/CB-POS/issues/321) |
| [UX-092](#ux-092-copies-field-box-proportions-make-its-value-easy-to-misread-as-blank-couldnt-confirm-a-code-level-bug) | "Copies" field box proportions make its value easy to misread as blank (couldn't confirm a code-level bug) | Settings → Hardware | P2 | 🔴 Open | [#322](https://github.com/HMAHD/CB-POS/issues/322) |
| [UX-093](#ux-093-printer-list-never-rescans-a-newly-connected-printer-needs-a-full-app-restart-to-appear) | Printer list never rescans — a newly connected printer needs a full app restart to appear | Settings → Hardware | P2 | 🔴 Open | [#323](https://github.com/HMAHD/CB-POS/issues/323) |
| [UX-094](#ux-094-good-pattern-already-built-the-section-divider-helper-should-be-reused-in-the-sidebar-redesign) | Good pattern already built: the section-divider helper should be reused in the sidebar redesign | Settings → Hardware, app-wide | P3 | 🔴 Open | [#324](https://github.com/HMAHD/CB-POS/issues/324) |
| [UX-095](#ux-095-receipt-preview-never-reflects-the-actual-configured-paper-width-always-renders-at-80mm) | Receipt preview never reflects the actual configured paper width — always renders at 80mm | Settings → Receipt | P1 | 🔴 Open | [#325](https://github.com/HMAHD/CB-POS/issues/325) |
| [UX-096](#ux-096-preview-and-real-thermal-print-use-two-independent-text-renderers-for-free-form-headerfooter-text) | Preview and real thermal print use two independent text renderers for free-form header/footer text | Settings → Receipt | P1 | 🔴 Open | [#326](https://github.com/HMAHD/CB-POS/issues/326) |
| [UX-097](#ux-097-a-real-print-preview-dialog-already-exists-in-the-codebase-but-is-completely-unwired) | A real print-preview dialog already exists in the codebase, but is completely unwired | Settings → Receipt | P2 | 🔴 Open | [#327](https://github.com/HMAHD/CB-POS/issues/327) |
| [UX-098](#ux-098-qr-code-support-is-fully-documented-in-the-receipt-schema-but-never-actually-emitted) | QR code support is fully documented in the receipt schema, but never actually emitted | Settings → Receipt | P3 | 🔴 Open | [#328](https://github.com/HMAHD/CB-POS/issues/328) |
| [UX-099](#ux-099-receipt-preview-barcode-is-explicitly-decorative-and-not-scannable-by-the-codes-own-admission) | Receipt preview barcode is explicitly decorative and not scannable, by the code's own admission | Settings → Receipt | P3 | 🔴 Open | [#329](https://github.com/HMAHD/CB-POS/issues/329) |
| [UX-100](#ux-100-shop-logo-has-no-size-guidance-and-no-real-dithering-step-for-thermal-print-quality) | Shop Logo has no size guidance and no real dithering step for thermal print quality | Settings → Receipt | P2 | 🔴 Open | [#330](https://github.com/HMAHD/CB-POS/issues/330) |
| [UX-101](#ux-101-receipt-customization-is-fragmented-across-3-disconnected-settings-pages) | Receipt customization is fragmented across 3 disconnected Settings pages | Settings → Receipt, Hardware, Documents | P2 | 🔴 Open | [#331](https://github.com/HMAHD/CB-POS/issues/331) |
| [UX-102](#ux-102-system-security-tab-field-truncation-couldnt-reproduce-from-code-same-widget-class-as-ux-092) | System Security tab field truncation — couldn't reproduce from code, same widget class as UX-092 | Settings → System | P2 | 🔴 Open | [#332](https://github.com/HMAHD/CB-POS/issues/332) |
| [UX-103](#ux-103-network-mode-icon-is-a-raw-emoji-not-the-apps-icon-system-explaining-the-black-background) | Network mode icon is a raw emoji, not the app's icon system — explaining the black background | Settings → Network | P2 | 🔴 Open | [#333](https://github.com/HMAHD/CB-POS/issues/333) |
| [UX-104](#ux-104-network-page-has-almost-no-explanatory-text-which-is-exactly-why-mode-vs-lan-sync-reads-as-redundant) | Network page has almost no explanatory text, which is exactly why Mode vs. LAN Sync reads as redundant | Settings → Network | P1 | 🔴 Open | [#334](https://github.com/HMAHD/CB-POS/issues/334) |
| [UX-105](#ux-105-lan-sync-tab-hardcodes-english-strings-bypassing-i18n-entirely) | LAN Sync tab hardcodes English strings, bypassing i18n entirely | Settings → Network | P2 | 🔴 Open | [#335](https://github.com/HMAHD/CB-POS/issues/335) |
| [UX-106](#ux-106-payment-method-cards-are-a-7th-confirmed-instance-of-the-navy-palette) | Payment method cards are a 7th confirmed instance of the navy palette | Settings → Payments | P2 | 🔴 Open | [#346](https://github.com/HMAHD/CB-POS/issues/346) |
| [UX-107](#ux-107-cashs-narrower-button-row-breaks-column-alignment-across-payment-method-rows) | Cash's narrower button row breaks column alignment across payment method rows | Settings → Payments | P2 | 🔴 Open | [#336](https://github.com/HMAHD/CB-POS/issues/336) |
| [UX-108](#ux-108-only-cash-shows-a-shortcutbehavior-tag-because-only-cash-was-ever-seeded-with-one) | Only Cash shows a shortcut/behavior tag — because only Cash was ever seeded with one | Settings → Payments | P3 | 🔴 Open | [#337](https://github.com/HMAHD/CB-POS/issues/337) |
| [UX-109](#ux-109-cashs-tag-labels-arent-translated-in-sinhala-or-tamil) | Cash's tag labels aren't translated in Sinhala or Tamil | Settings → Payments | P3 | 🔴 Open | [#338](https://github.com/HMAHD/CB-POS/issues/338) |
| [UX-110](#ux-110-backup-list-loads-synchronously-with-no-loading-indicator-despite-the-pattern-already-existing-in-the-same-file) | Backup list loads synchronously with no loading indicator, despite the pattern already existing in the same file | Settings → Data Safety | P2 | 🔴 Open | [#339](https://github.com/HMAHD/CB-POS/issues/339) |
| [UX-111](#ux-111-the-18-pre-restore-backups-shown-are-very-likely-a-test-isolation-bug-leaking-into-a-real-user-folder) | The 18 pre-restore backups shown are very likely a test-isolation bug leaking into a real user folder | Settings → Data Safety | P2 | 🔴 Open | [#340](https://github.com/HMAHD/CB-POS/issues/340) |
| [UX-112](#ux-112-pre-restore-backups-are-permanently-exempt-from-cleanup-and-have-no-delete-option-anywhere) | Pre-restore backups are permanently exempt from cleanup, and have no delete option anywhere | Settings → Data Safety | P1 | 🔴 Open | [#341](https://github.com/HMAHD/CB-POS/issues/341) |
| [UX-113](#ux-113-database-file-path-is-visually-truncated-by-a-qformlayout-sizing-bug-not-a-data-bug) | Database file path is visually truncated by a QFormLayout sizing bug, not a data bug | Settings → Admin Tools | P2 | 🔴 Open | [#342](https://github.com/HMAHD/CB-POS/issues/342) |
| [UX-114](#ux-114-admin-tools-hardware-tab-duplicates-two-test-buttons-already-on-settings-hardware) | Admin Tools' Hardware tab duplicates two test buttons already on Settings → Hardware | Settings → Admin Tools | P3 | 🔴 Open | [#343](https://github.com/HMAHD/CB-POS/issues/343) |
| [UX-115](#ux-115-a-working-database-integrity-check-already-exists-but-is-never-wired-to-any-button) | A working database integrity-check already exists, but is never wired to any button | Settings → Admin Tools | P3 | 🔴 Open | [#344](https://github.com/HMAHD/CB-POS/issues/344) |

---

## Entries

<!-- New entries are appended below this line, most recent last. -->

### UX-001: Empty cart hides the entire table, including its header

**Screen:** POS main screen (Sales view), cart area — screenshot 1 (empty cart)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#256](https://github.com/HMAHD/CB-POS/issues/256) (sub-issue of [#254](https://github.com/HMAHD/CB-POS/issues/254))

**What you see:** With no items scanned, the whole cart area is just a large
black rectangle with centered gray text, "Scan or search to add items." No
column structure (ITEM / PRICE / QTY / DISC / TOTAL) is visible anywhere.

**Root cause (verified in code):** `cbpos/ui/views/sales_view.py:236-245`. The
cart isn't one table that's merely empty — it's a `QStackedWidget` holding two
*entirely separate* widgets: page 0 is a plain `QLabel` ("empty_cart_label"),
page 1 is the real `cart_table` (header row included). `update_cart_display()`
(`sales_view.py:616-618`) flips `cart_stack.setCurrentIndex(1 if has_items else 0)`.
So the header row isn't hidden independently — it doesn't exist on screen at
all until the first item lands, because the entire `QTableWidget` is swapped
out for the label.

**Why it matters:** This is a keyboard-first, high-speed checkout tool used
by cashiers who are scanning constantly. The column headers are part of how
a cashier learns the shape of the cart at a glance ("price here, qty there").
Hiding them until the first scan means the very first thing a new cashier
sees is a screen that looks broken/unfinished, not "ready and waiting." It
also makes the empty state feel like dead space rather than a working part
of the screen.

**Suggested fix:** Stop swapping the *whole table* for the placeholder. Keep
`cart_table` (and its header) always visible; show the "Scan or search to add
items" message as an overlay centered over the table's row area only, e.g. a
`QLabel` parented to `cart_table.viewport()` with `setVisible(rowCount == 0)`
toggled in `update_cart_display()`, positioned via `resizeEvent`/`move()` to
stay centered (a couple of lines — a raw `QLabel` doesn't participate in
layout as a child of a viewport, so it needs manual centering, but that's
the same technique already used elsewhere in this file for the undo toast).
Net effect: header stays visible at all times, empty state renders as "an
empty table with a hint," not "no table at all."

---

### UX-002: Cart table numeric columns are inconsistently aligned, discounted price format doesn't match regular one

**Screen:** POS main screen (Sales view), cart table — screenshot 2 (item added)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#350](https://github.com/HMAHD/CB-POS/issues/350) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**What you see:** With an item in the cart, PRICE/QTY/DISC/TOTAL feel cramped
and don't read as a clean table — values look like they're floating rather
than lining up under their headers, and the discounted price ("~~110.00~~
60.00") looks different in style from a plain price.

**Root cause (verified in code), `sales_view.py`, `update_cart_display()`:**
- **Alignment is inconsistent across the same column depending on state.**
  When a price is *not* discounted, it's a plain `QTableWidgetItem` with no
  `setTextAlignment()` call at all (line 638-641) → defaults to **left**-aligned.
  When it *is* discounted, it's a `QLabel` cell widget explicitly set to
  **right**-aligned (line 633-636). So the exact same column visually jumps
  from left to right alignment row to row depending on whether that one item
  has a discount.
- **QTY, DISC, and TOTAL columns never set alignment at all** (lines 660-674)
  → all default to left-aligned Qt items, which reads oddly for numbers in
  narrow (50-140px) fixed-width columns — numbers conventionally read easier
  right-aligned (decimal points line up vertically as more items are added).
- **The column headers themselves have no explicit alignment either** — there's
  no `#CartTable QHeaderView::section` override in `dark.qss`/`light.qss` at
  all (the cart table inherits the generic navy `QHeaderView::section` rule at
  `dark.qss:354`, which doesn't set text alignment, so it defaults to
  left-aligned too). Left-aligned header labels sitting above
  inconsistently-aligned data is exactly what reads as "not lined up."
- **The discounted-price text skips `format_currency()` entirely** — it's a
  raw `"{:.2f}".format(...)` (line 634), so a discounted line shows `110.00
  60.00` with no currency prefix, while every other price/total in the same
  table (via `format_currency()`) shows `Rs. 60.00`. One column, two visual
  formats depending on data.

**Why it matters:** In a checkout screen a cashier and a customer both look
at, wobbly alignment reads as "unpolished" even when every number is
mathematically correct — and worse, the missing "Rs." prefix on discounted
lines could genuinely confuse a customer glancing at the screen about
whether that number is even a price.

**Suggested fix:**
1. Right-align QTY, DISC, and TOTAL `QTableWidgetItem`s (`setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)`), matching the already-right-aligned discounted-price widget.
2. Right-align the plain (non-discounted) price item too, so PRICE doesn't flip alignment depending on discount state.
3. Set the header's default section alignment to match — via `cart_table.horizontalHeaderItem(col).setTextAlignment(...)` for columns 1-4 (ITEM stays left), not a table-wide `setDefaultAlignment()` (that would also shift the ITEM header).
4. Route the discounted-price label through `format_currency()` for both the struck-through and current price, so it always shows `Rs.` regardless of discount state.
5. While touching this: give the numeric columns a little more breathing room in the fixed widths (currently Qty/Disc are only 50px, `setMinimumSectionSize(55)` is already *larger* than that fixed width, which is a bit contradictory) — 60-65px for Qty/Disc would give the discount `%` and 3-decimal quantities a bit more room without needing to shrink the font.

---

### UX-003: Customer card and loyalty points are two disconnected elements

**Screen:** POS main screen (Sales view) → `ActionPanel` widget, right sidebar
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#255](https://github.com/HMAHD/CB-POS/issues/255)

**What you see:** The customer name/phone row sits inside a nicely-styled
bordered card, but "Points: 150" renders as small yellow text *below and
outside* that card, with no border/background tying it to the customer
info above it. Visually it reads as two unrelated pieces of information, not
one "this is what I know about this customer" unit.

**Root cause (verified in code):** `cbpos/ui/widgets/action_panel.py:142-182`.
`QFrame#CustomerPanel` (the actual bordered/rounded card — styled at
`dark.qss:763-767` with `background-color: #252528; border: 1px solid
#3E3E42; border-radius: 8px;`) contains only the icon + name/phone + Select
button. `self.lbl_points` (`QLabel#PointsLabel`, styled at `dark.qss:797-802`)
is added directly to the panel's *outer* layout, as a sibling **after**
`customer_frame`, not as a child inside it (line 176 vs 179-182). It has its
own independent center-alignment and no shared background/border with the
card above. It's also never `setVisible(False)`-toggled — for the Walk-in
default it's just set to an empty string (`clear_customer_info()`, line
282-283), so it still reserves its line of vertical space even when showing
nothing.

**Why it matters:** You asked for this one directly, and it's a real
"it looks like two features bolted together" problem, not just taste — a
loyalty program is more persuasive when it visually *belongs* to the
customer's identity card (same frame, same border), not floating text
underneath it that a cashier could easily miss entirely on a fast scroll of
the screen.

**Suggested fix — unify into one card, reusing only colors already in the
palette (`#00BCEB` cyan, `#FFDC00` points-yellow, `#252526`/`#252528`
surface, `#3E3E42` border — nothing new introduced):**

Restructure `QFrame#CustomerPanel` into a single card with two internal rows,
both inside the same frame/border:
- **Row 1 (unchanged):** icon + name/phone + Select button — exactly as today.
- **Row 2 (new, inside the same frame):** a thin `1px solid #3E3E42` divider,
  then a small pill/badge: a star icon (see UX-006) + "150 points" in
  `#FFDC00`, e.g. `background-color: rgba(255, 220, 0, 0.12); border-radius:
  10px; padding: 2px 10px;` — a "badge," not another full-width label, so it
  doesn't dominate the card. Left-aligned under the name, not centered (the
  current centering is part of why it looks unattached — it doesn't line up
  under anything above it).
- For Walk-in Customer (no loyalty points), **hide row 2 entirely**
  (`setVisible(False)`) instead of clearing it to an empty string, so the
  default state doesn't carry a blank strip of unused vertical space.

This keeps every color already established in the theme; it just moves the
points into the card's own boundary and gives it a deliberate, badge-like
treatment instead of looking like leftover text.

**Feature idea while we're in here:** since this card is prime, always-visible
real estate, consider surfacing one more signal a cashier actually acts on —
e.g. a small "Credit: Rs. X owed" chip (reusing the existing Credit Book
feature) when the customer has an outstanding balance, using the same
badge treatment in the existing danger red (`#FF4136`). Not required, just
noting the card redesign creates room for it if there's appetite later.

---

### UX-004: Discount highlight only tints one cell of the row

**Screen:** POS main screen (Sales view), cart table
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#265](https://github.com/HMAHD/CB-POS/issues/265)

**Not from your notes — flagged during code review.** When a cart line has a
discount or manual price override, only the **name** cell gets a background
tint (`sales_view.py:644-646`, dark green `QColor(0, 50, 0)` in dark theme) —
PRICE, QTY, DISC, and TOTAL cells on that same row stay the table's plain
background. A single colored cell in an otherwise plain row reads as
half-finished rather than "this whole line is discounted."

**Suggested fix:** Apply the same background tint to all five cells on a
discounted row (name/price-widget/qty/disc/total), not just the name cell —
one extra `setBackground()`/palette call per cell already being built in the
same loop, no new mechanism needed.

---

### UX-005: Empty cart placeholder is plain text with no visual anchor

**Screen:** POS main screen (Sales view), cart area — screenshot 1
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#257](https://github.com/HMAHD/CB-POS/issues/257) (sub-issue of [#254](https://github.com/HMAHD/CB-POS/issues/254))

**Not from your notes — flagged during code review, ties into UX-001.**
Right now the empty state is just gray text centered in a large black
rectangle (`QLabel#EmptyCartLabel`, `dark.qss:673-678`) — functionally fine,
but visually the least-designed part of the whole screen.

**Suggested fix (once UX-001's overlay approach is in place):** pair the
existing text with a large, muted icon above it — the app already has
`Icons.SALES = "fa5s.shopping-cart"` registered and in use elsewhere, so
reusing it here (rendered large, low-opacity, in the existing muted gray
`#555555`) costs nothing new in the icon system and gives the empty state an
actual focal point instead of just type on black.

---

### UX-006: Customer icon bypasses the centralized icon system; no points icon registered

**Screen:** `cbpos/ui/widgets/action_panel.py` (code-quality note, not visible to the end user)
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#266](https://github.com/HMAHD/CB-POS/issues/266)

**Not from your notes — flagged during code review.** `cbpos/ui/resources/icons.py`
is this project's own established convention for centralizing every
qtawesome icon reference as a class constant (`Icons.DASHBOARD`,
`Icons.SEARCH`, etc.) — but the customer card's icon
(`action_panel.py:152`, `Icons.get("fa5s.user-circle", "#00BCEB")`) passes
a raw qtawesome string literal instead of going through a registered
constant, the only place in the codebase that does this for an icon still
in active use.

**Suggested fix:** add `CUSTOMER = "fa5s.user-circle"` and `POINTS =
"fa5s.star"` to the `Icons` class (needed for UX-003's badge anyway), and
use `Icons.CUSTOMER` at `action_panel.py:152` instead of the inline string —
purely a consistency cleanup, zero visible behavior change.

---

### UX-007: Applied Payments list is hard-capped at 160px, so it scrolls and clips the boundary row's remove button instead of expanding

**Screen:** Payment dialog, "Applied Payments" section
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#267](https://github.com/HMAHD/CB-POS/issues/267)

**What you flagged:** two things — (a) the applied-payments container doesn't
grow as more split payments are added, and (b) one row's remove ("×") button
only shows a border on 3 sides, like the bottom edge is missing.

**These are the same bug, confirmed by actually reproducing it** (constructed
the dialog, added 4 cash payments, rendered it):

`cbpos/ui/dialogs/payment_dialog.py:161`:
```python
self.list_payments.setMaximumHeight(160)
```
160px is a hard ceiling, not a starting size — the comment above it even says
"compact, grows only as needed" (line 158), but `setMaximumHeight` overrides
whatever the size policy (`Expanding, Preferred`, line 162) would otherwise
allow. At ~55-60px per row, 160px only ever fits ~2.5 rows, so a 3rd+ payment
forces internal scrolling — **and the row sitting right at that 160px cutoff
is the one that gets visually clipped**, its remove button's own red border
cut off mid-render exactly where the list's viewport ends. That's the "3
sides only" row you marked — it's not a separate rendering/alignment bug on
that specific button, it's this same row being cut off by the container
boundary. Reproduced exactly in a screenshot: rows 1-2 render fully, row 3
("Cash: Rs. 70.00") is sliced in half by the list's bottom edge, button
border included.

Compounding it: `left_layout.addStretch()` right after the list
(`payment_dialog.py:165`) means any vertical space the dialog *does* have
below the Applied Payments list is deliberately handed to empty stretch
instead of the list — there's visibly a large empty black gap between the
list and the Cancel/Finish Sale bar in the screenshot, space that could
easily fit 2 more full rows.

**Why it matters:** split payments (cash + card, multiple cash tenders,
etc.) are a normal Sri Lankan retail pattern, not an edge case — a cashier
splitting a bill 3-4 ways is common, and the one thing they need to check
before finishing the sale (what's been applied so far) is the thing getting
clipped.

**Suggested fix:**
1. Raise the cap significantly (e.g. 260-300px, or compute it from the
   dialog's actual available height at construction time, the same way
   `_BTN_SIZE` for the numpad is already computed from screen geometry) so
   4-5 typical split payments fit without scrolling.
2. Remove (or shrink) the trailing `addStretch()` so the list is the thing
   that claims freed-up vertical space in that column, not empty space below
   it — matches the "grows only as needed" comment that's already there but
   currently not true.
3. Keep the QListWidget's native scrollbar as a fallback for the rare case
   of more splits than even a generous cap can show — just make the common
   case (2-5 payments) not need it.

---

### UX-008: "Change Quantity"/"Change Price" on a cart line use a raw native dialog instead of the app's own styled one

**Screen:** POS main screen, cart line context menu / F4 shortcut ("Qty" in
the Orders panel)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#268](https://github.com/HMAHD/CB-POS/issues/268)

**What you flagged:** the up/down steppers next to the quantity field look
disconnected from the input (a visible gap + odd dividing line between
them), and Cancel/OK have no visual hierarchy — OK doesn't look like the
button you're supposed to press.

**Root cause (verified in code) — this is not the dialog you'd expect.**
CB-POS already has a well-built, fully-styled `QuantityDialog`
(`cbpos/ui/dialogs/quantity_dialog.py`) — a big centered `QLineEdit`
(`#QtyInput`, 44px tall, 24px bold text, cyan focus ring, styled at
`dark.qss:1192-1204`), product name shown above it, unit hint below, Enter
bound to confirm. It's used for **adding** a product to the cart
(`sales_view.py:587, 1171`).

But the F4 "Change Quantity" action on an *existing* cart line — the exact
screen in your screenshot — doesn't use it. `sales_view.py:1032-1050`,
`change_line_quantity()`:
```python
qty, ok = QInputDialog.getDouble(
    self, _t("cart.change_qty_title"), _t("cart.change_qty_prompt"),
    value=float(current_qty), min=0.001, max=999999, decimals=3,
)
```
`QInputDialog.getDouble()` is a **stock Qt dialog** — its embedded spin box
and OK/Cancel buttons are native widgets with no `objectName`, so none of
this app's QSS can reach them at all. What you're seeing — the gap between
the field and the stepper, the dividing line between the two arrow buttons,
both buttons looking identically plain — is just the OS's default rendering
of an unstyled `QAbstractSpinBox`, not a CSS bug to patch. `change_line_price()`
(`sales_view.py:1082-1112`, the Manager-only price override) has the exact
same problem, same root cause, one line away.

**Why it matters:** a cashier who's just used the polished add-to-cart
quantity prompt sees a completely different, native-OS-styled dialog show up
for what feels like the identical task (typing a number for a cart line) —
inconsistent even within the same screen, and it's the one place in the cart
workflow that still looks unfinished next to everything else.

**Suggested fix:** reuse `QuantityDialog` for `change_line_quantity()`
instead of `QInputDialog.getDouble()`. It needs one small capability it
doesn't have yet: today it always starts the input at `"1"` (its docstring
says it's built for "adding a product to the cart"); changing an *existing*
line needs to open pre-filled with the current quantity. That's a small,
additive change to its constructor (an optional `initial_qty` parameter),
not a rebuild. For `change_line_price()`, either build an equivalent
small "Change Price" dialog following the exact same visual pattern
(large centered input, product name, styled OK/Cancel with OK using the
existing `class="primary"` green), or generalize `QuantityDialog` into a
shared "single numeric value" prompt reusable for both — worth deciding
which, once we're in the fixing pass. Either way, giving OK the `primary`
green treatment (the same convention `DiscountDialog`'s "Apply Discount"
button already uses) fixes the "no visual hierarchy" complaint for free.

**Related, not pictured:** `add_line_note()` (`sales_view.py:1022-1030`)
uses `QInputDialog.getText()` for the same reason — a third native dialog
in the same cluster of cart-line actions. Lower priority (plain text input
doesn't have the stepper-button styling problem), but worth folding into
the same pass for consistency.

---

### UX-009: Select Customer dialog cannot be confirmed from the keyboard at all

**Screen:** Select Customer dialog
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#264](https://github.com/HMAHD/CB-POS/issues/264) — parent issue, tracks sub-issues for each confirmed location

**Not from your notes — flagged during code review, but directly relevant
to this app's own "keyboard-first" design principle.**
`customer_selection_dialog.py:51-54` builds the button row with **only a
Cancel button** — there is no Select/OK button at all. The only way to
confirm a selection is `self.table.doubleClicked.connect(self.select_customer)`
(line 48) — a mouse-only interaction. There is no `Key_Return`/`Key_Enter`
binding anywhere in the file. Compare with `AdvancedSearchDialog`, which
gets this right: it has both a visible "Select" button *and*
`QShortcut(Qt.Key.Key_Return, self).activated.connect(self.on_select)`.

**Why it matters:** this app is explicitly built keyboard-first for speed —
a cashier can arrow-key down to the right row, but then has nothing to
press to confirm it. They're forced to reach for the mouse specifically at
the one moment they were otherwise moving entirely by keyboard. That's a
real workflow interruption, not a cosmetic gap.

**Suggested fix:** add a "Select" button (styled `class="primary"`, matching
the rest of the app's confirm-action convention) next to Cancel, and bind
Enter/Return to the same `select_customer()` handler — both small, exactly
matching the pattern `AdvancedSearchDialog` already establishes elsewhere in
this codebase.

---

### UX-010: Select Customer table truncates real customer names

**Screen:** Select Customer dialog
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#351](https://github.com/HMAHD/CB-POS/issues/351) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**What you'd see if you searched further** — "Malini ..." and "Chaminda ..."
in the screenshot aren't abbreviations, they're mid-name truncation. This is
a genuine usability problem: the one thing this dialog exists to do is let
a cashier tell customers apart, and it's cutting off the exact information
that would do that.

**Root cause (verified in code):** `customer_selection_dialog.py:44` sets
resize mode with the no-column-index overload —
`self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)`
— which applies `Stretch` **uniformly to all 3 columns**. ID, NAME, and
PHONE all fight for an equal one-third share of the table's width, even
though ID only ever needs ~2 digits and PHONE is always exactly 10 digits —
so NAME, the one column with genuinely variable-length content, gets
starved down to the same width as the shortest column. No `setColumnWidth`
override exists anywhere in the file, and Qt's default elide mode
(`ElideRight`) just quietly truncates whatever doesn't fit, with no tooltip
showing the full name on hover.

**Suggested fix:** give NAME a stretch column (`Stretch` mode, same as the
cart table's ITEM column) and make ID + PHONE `ResizeToContents` or a
sensible fixed width (ID: ~50px, PHONE: ~120px) — the same "one flexible
column, N-1 sized-to-content" pattern already used correctly in the cart
table (`sales_view.py:208-218`) and the Reorder Report. As a cheap
complementary safety net, also set a tooltip with the full name on each
row (`item.setToolTip(customer.name)`) so a name is still recoverable even
in a narrow window.

**Feature idea while we're in here:** see UX-012 below for the ID column
itself — showing a raw internal database key here isn't obviously useful to
a cashier; the freed-up width from fixing this could go toward something a
cashier would actually act on.

---

### UX-011: Select Customer header alignment doesn't match cell alignment — same pattern as UX-002

**Screen:** Select Customer dialog
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#352](https://github.com/HMAHD/CB-POS/issues/352) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**Not from your notes — flagged during code review.** Same defect class as
UX-002 (cart table), confirmed here too:
`customer_selection_dialog.py:72-74` never calls `setTextAlignment()` on
any `QTableWidgetItem`, so ID/NAME/PHONE cell data defaults to Qt's
left-aligned item style. The column headers, meanwhile, get no alignment
override either and fall back to Qt's own default **center** alignment for
header text. Center-aligned "ID / NAME / PHONE" sitting directly above
left-aligned data is the exact same header/data mismatch already logged for
the cart table — this is the second table in the app with it, which makes
it worth treating as a shared pattern rather than two unrelated one-off
bugs once we get to fixing.

**Suggested fix:** left-align both the NAME/PHONE headers and their data
(natural reading alignment for text); ID can stay center or move to
right-aligned if it's kept as a numeric-looking column at all (see UX-012).
Whichever convention we land on while fixing UX-002, apply the same one
here for consistency across the app's tables.

---

### UX-012: Select Customer table skips 3 conventions every other table in the app follows

**Screen:** Select Customer dialog
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#353](https://github.com/HMAHD/CB-POS/issues/353) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**Not from your notes — flagged during code review.** Three small things,
grouped here because they're all "this table didn't follow the pattern
already established everywhere else," best fixed together:

1. **No alternating row colors.** `setAlternatingRowColors(True)` is called
   by 24 other tables across this codebase (cart table, unit manager,
   refund dialog, sale history, category manager, purchase view, and more)
   — this is the outlier that skips it, making a 7+ row result list harder
   to scan row-to-row than every comparable list elsewhere in the app.
2. **Row-number gutter left visible and unstyled.** The dark-navy,
   cyan-bordered column of `1, 2, 3...` on the left in your screenshot isn't
   a deliberate design — it's Qt's default vertical header, left showing
   because `verticalHeader().setVisible(False)` is never called. Five other
   comparable tables in the app (`sales_view.py`'s cart table,
   `proforma_dialog.py`, `sale_history_dialog.py` ×2,
   `shortcuts_help_dialog.py`) explicitly hide it. It's not useful
   information to a cashier (a row's position in a scrolled list isn't
   meaningful) and it's currently the most visually dominant color block in
   the dialog purely by accident.
3. **No `objectName` set on the table at all**, so it can't be targeted by
   any dialog-specific QSS rule even if we wanted to fix any of the above
   through the stylesheet rather than code — worth giving it one
   (e.g. `#CustomerSelectTable`) as part of the same pass.

**Separately, a robustness note on the ID column:** `select_customer()`
(`customer_selection_dialog.py:76-81`) re-parses the customer ID by reading
it back out of the *displayed cell text* (`int(self.table.item(row, 0).text())`)
rather than storing it as item data (`Qt.ItemDataRole.UserRole`) — it happens
to work today only because the ID column shows nothing but the raw integer.
If the ID column's presentation ever changes (padding, a `#` prefix, i18n
formatting), this parse breaks silently. Worth storing the ID as UserRole
data on the row instead of round-tripping it through display text, regardless
of what happens with the ID column itself.

---

### UX-013: Periodic Reports date-picker calendar popup renders broken (reproduced exactly)

**Screen:** Dashboard, "Periodic Reports" date range fields
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#364](https://github.com/HMAHD/CB-POS/issues/364) (sub-issue of [#262](https://github.com/HMAHD/CB-POS/issues/262))

**What you flagged:** the calendar popup doesn't display properly.

**Reproduced pixel-for-pixel** — constructed the real `DashboardView`,
opened `date_from`'s calendar popup, and grabbed it. Weekday header shows
"..." repeated across every column; day-number cells (including a "3", "4"
in red, and a stray "1") render past the popup's own right edge, overlapping
whatever sits next to it on screen — exactly what your screenshot shows.

**Root cause (verified in code):** `dashboard_view.py:238-254` sets
`date_from`/`date_to` up as plain `QDateEdit(setCalendarPopup(True))` —
there's no custom calendar subclass, just Qt's stock `QCalendarWidget`. A
`grep -ni "calendar"` across `dark.qss` returns **zero matches** — nothing
in this app's stylesheet targets `QCalendarWidget` at all. But the popup
isn't actually unstyled either: its internal day-grid is a `QTableView`
subclass and its weekday-name row is a `QHeaderView`, both of which match
**fully unscoped, global** rules meant for completely different widgets
elsewhere in the app:
```css
/* dark.qss:354-361 — meant for real data tables, matches every QHeaderView::section in the app */
QHeaderView::section {
    padding: 10px;
    font-weight: bold;
    border-bottom: 2px solid #00BCEB;
    ...
}
/* dark.qss:1769-1786 — meant for real data tables */
QTableView::item { padding: 8px; border: none; }
```
Qt computes the calendar popup's window size (`sizeHint()` in my repro:
224×171 — tiny) *before* factoring in stylesheet padding. Once `padding:
10px` lands on every header cell and `padding: 8px` on every day cell, the
content those cells need no longer fits the geometry Qt already locked in —
the header text gets elided down to "...", and the day-grid's true rendered
width exceeds the popup's fixed window width, so cells past a certain
column spill out past its edge entirely.

**Why it matters:** this isn't just visually broken — it's genuinely
unusable. You can't reliably tell what date a bleeding-out cell corresponds
to, so picking a date via this calendar is as likely to select the wrong
one as the right one. (See UX-016 — this is almost certainly how the report
range ended up a year in the future in your screenshot.)

**Suggested fix:** add a real, scoped stylesheet block for the calendar
popup specifically — e.g. `QCalendarWidget QAbstractItemView` /
`QCalendarWidget QTableView::item` / `QCalendarWidget QHeaderView::section`
overrides with padding/font-size sized to actually fit a fixed small popup,
*and* give the popup itself a bit more room via
`calendarWidget().setMinimumSize(...)` after `setCalendarPopup(True)` (Qt
does respect an explicit minimum size on the calendar widget itself, unlike
the auto-computed default). Test at the exact size chosen, the same way I
just did — this can't be eyeballed from QSS alone, it needs a rendered
check.

**Feature idea:** most of the time a cashier or owner wants "This Month" /
"Last Month" / "This Year" / "Last 7 Days," not an arbitrary custom range —
a small row of preset-range buttons next to the date fields would cover the
common case without needing the calendar popup at all, and make the
custom-range calendar a rarely-used fallback rather than the primary
interaction. Worth considering alongside the fix, not instead of it (a
custom range is still a real, legitimate need).

---

### UX-014: Total Sales KPI number appears clipped in the reported screenshot (couldn't reproduce yet)

**Screen:** Dashboard, top-right summary panel
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#269](https://github.com/HMAHD/CB-POS/issues/269)

**What you flagged:** "Rs. 161,749." cuts off right after the decimal point
— no cents digits visible, like the text is too big for its box.

**Being upfront about what I could and couldn't confirm:** I checked the
code and rendered the real dashboard twice — once standalone, once inside
the full `ManagementView` at the exact 2880×1800 resolution your screenshot
was taken at — and in both renders `format_currency()` correctly produces
`"Rs. 161,749.00"` and it displays in full, not clipped. So I can't yet
reproduce what your screenshot shows, which means either it's specific to
the real device (HiDPI/Retina font-metric rounding is a very plausible
culprit — the `SummaryBigValue` label is a large 32px font with no
`setWordWrap`, no `setMaximumWidth`, and no elide-mode set, so it has zero
safety margin if font metrics come out even slightly different than my
offscreen render assumes), or the real total in your data has more digits
than my test value did and tips it over some threshold mine didn't reach.

**Root cause candidate (confirmed in code, even if I couldn't trigger the
visible symptom):** `dashboard_view.py:190-221` builds this value as
`QLabel#SummaryBigValue`, styled at `dark.qss:1635-1640`:
```css
QLabel#SummaryBigValue { font-size: 32px; font-weight: bold; }
```
— more than double `QLabel#SummarySubValue`'s 14px (the "Rs. 136,423.58"
right below it, which isn't clipped in your screenshot). Neither label has
any wrapping, elision, or width safety net, so whichever one is closer to
its container's actual limit is the one that has no fallback if it's ever
1 pixel too wide.

**Suggested fix, regardless of exact root cause:** don't rely on a fixed
32px working out — either enable `setWordWrap(True)` with a two-line
layout the panel already has room for, or (better, matching this app's
existing responsive-font mechanism already used for the theme's
`{{FONT_SIZE}}` system) scale the font down slightly for wider numbers, or
set an explicit `setMinimumWidth` on the summary panel generous enough for
worst-case totals (7-8 digits) at 32px. Whatever we pick, it needs to be
checked on the actual target device/resolution before calling it fixed —
this is exactly the kind of thing that looks fine in one environment and
clips in another.

---

### UX-015: Both dashboard background workers swallow errors silently and leave the UI stuck

**Screen:** Dashboard (whole screen)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#270](https://github.com/HMAHD/CB-POS/issues/270)

**Not from your notes — flagged as the system-engineer pass you asked for.**
This is the same bug *class* already found and fixed in the print/reprint
flows earlier in this review (issues #244/#248 from the prior GitHub-issue
batch): a background worker that only reports success, with no path back
to the UI on failure.

`dashboard_view.py`'s `_YearlyWorker.run()` (lines 52-60) and
`_PeriodicWorker.run()` (lines 73-85) both wrap their DB calls in a bare
`try/except Exception: logger.exception(...)` — **neither emits its
`finished` signal on failure.** Since `_on_yearly_ready()` /
`_on_periodic_ready()` are the only places that hide the monthly-chart
loading overlay, re-enable the prev/next-year buttons, re-enable the
`date_from`/`date_to` pickers, and reset the refresh button off its
hourglass icon — if either query throws for any reason (a transient DB
hiccup, a bad date range, anything), those elements **stay stuck exactly as
they were mid-load, permanently**, with zero indication to the user that
anything went wrong or what to do about it.

**Why it matters:** a dashboard that silently freezes mid-refresh, with no
error and no way to tell it's stuck versus just slow, is the kind of bug
that generates a support call rather than a bug report — the owner has no
idea it's broken, they just see numbers that never update again until they
restart the app.

**Suggested fix:** give both workers an `error_occurred = pyqtSignal(str)`
(mirroring the pattern already established for `PrintWorker`), emit it in
the `except` branch instead of only logging, and connect it in
`DashboardView` to re-enable whatever that worker's success path would have
re-enabled, plus a lightweight, non-blocking error indicator (a small inline
message where the KPI/chart would be is enough — this doesn't need a modal).

---

### UX-016: Periodic Reports date range has no sanity bounds and isn't remembered

**Screen:** Dashboard, "Periodic Reports" date range fields
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#271](https://github.com/HMAHD/CB-POS/issues/271)

**Directly answers your "get more accurate data" ask.** Two related gaps,
both confirmed in code:

1. **No min/max bounds on the date pickers at all** — `dashboard_view.py`
   never calls `setMaximumDate`/`setMinimumDate` on either field. There's no
   sales data from the future, so a report range that can end next year (as
   yours did) or start before the shop existed produces a query that's
   technically "valid" but never meaningfully correct. I verified the
   *initial* default computed at construction (`Jan 1 of current year` →
   `today`) is correct — there's no date-math bug there — so a value like
   `06.09.2027` almost certainly came from a stray click that landed on the
   wrong cell, which UX-013's broken popup makes very easy to do by
   accident.
2. **The chosen range isn't a remembered preference** — `dashboard_view.py`
   has no `ConfigService` usage anywhere; the date range lives purely in
   the widget's in-memory state for as long as the view instance is alive,
   reset to today's default only on a fresh app start. If the owner checks
   "Last Month" every morning, they re-pick it every morning too.

**Suggested fix:**
1. Cap `date_to` at `QDate.currentDate()` and set a sensible `date_from`
   floor (e.g. the shop's earliest recorded sale, or just "not before
   `date_to`") so an accidental future/reversed range is structurally
   impossible rather than just unlikely.
2. Persist the last-used range (or which preset was active, if UX-013's
   preset-buttons idea is adopted) via `ConfigService`, restored on next
   dashboard load — small change, meaningfully less repetitive for daily use.

---

### UX-017: Inventory table truncates product names — third confirmed instance of the UX-010 pattern

**Screen:** Inventory
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#354](https://github.com/HMAHD/CB-POS/issues/354) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**What you'd see** — "Atlas A5 Exercise Book 80 ...", "Comfort Fabric Softener
...", "Dettol Antiseptic Liquid ...", "Elephant House Cream So..." in the
NAME column all cut off mid-word, same as the Select Customer dialog
(UX-010).

**Root cause (verified in code) — literally the same bug, confirmed
independently in a second file:** `inventory_view.py:136`:
```python
self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
```
The no-column-index overload again — BARCODE/NAME/CATEGORY/PRICE/STOCK/UNIT
all get an equal forced share of the table's width, so NAME (the one column
with genuinely variable-length content) gets squeezed exactly like the
Select Customer table did. No `setToolTip` is set anywhere in this file
either (confirmed via the model's `data()` method — it only implements
`DisplayRole`/`BackgroundRole`, no `ToolTipRole`), so there's no hover
fallback to recover a cut-off name. The table also has no `objectName` set,
so it can't be targeted by dialog-specific QSS even if we wanted to.

**Why it matters:** same as UX-010 — this is the main product list a shop
owner scans through daily; not being able to read a full product name
defeats the point of the screen.

**Suggested fix:** identical to UX-010 — give NAME the `Stretch` column and
size BARCODE/CATEGORY/PRICE/STOCK/UNIT to content or a sensible fixed width
instead of uniform stretch, add `ToolTipRole` to the model's `data()` method
so a full name is always recoverable on hover, and give the table an
`objectName` while touching this code. **Worth fixing UX-010 and this one
together** — same bug, same fix, two files.

---

### UX-018: Three different numeric-input conventions in the app — one of them flagged as broken in its own code comment, and still used for Price

**Screen:** Product Editor dialog (Selling Price / Cost Price), app-wide pattern
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#263](https://github.com/HMAHD/CB-POS/issues/263) — parent issue, tracks sub-issues for each confirmed location

**What prompted this** — the Selling Price/Cost Price fields' +/- steppers
in your screenshot visually resemble the raw, unstyled native dialog already
found in UX-008, so I checked whether this was the same problem. It isn't
quite — but what I found is arguably a bigger finding: **the developers
already knew about a QSS rendering problem with this exact widget, fixed it
in three places in the same file, and left it broken in two more.**

**Root cause (verified in code):** `product_editor.py:120-128` builds
Selling Price/Cost Price as plain `QDoubleSpinBox()` instances (no
`objectName`, reached only by the generic `QSpinBox, QDoubleSpinBox` QSS
rule at `dark.qss:119-191`). A few lines later, `product_editor.py:142-143`,
right above the Stock/Reorder Point/Preferred Qty fields:
```python
# Stock group — QLineEdit instead of QDoubleSpinBox for clean
# rendering (QDoubleSpinBox +/- buttons break under QSS)
```
— an explicit developer comment stating `QDoubleSpinBox` steppers are known
to render badly under this app's stylesheet, with `QLineEdit` +
`QDoubleValidator` adopted as the fix for Stock/Reorder Point/Preferred Qty
(lines 149-162). **Selling Price and Cost Price were never migrated** and
still use the flagged-as-broken widget — same dialog, same known issue,
inconsistently applied. The Composition tab's component-quantity field
(`comp_qty_input`) has the same gap.

Zooming out, this app has accumulated **three unrelated workarounds** for
the same underlying problem (numeric entry that needs to look right under
this stylesheet), each invented independently:
1. `QDoubleSpinBox` with steppers, generic-QSS-styled (Price/Cost/Composition
   qty in `product_editor.py`, Decimal Places in `unit_manager.py`).
2. Plain `QLineEdit` + `QDoubleValidator`, no steppers at all
   (Stock/Reorder/Preferred Qty in `product_editor.py`, the entire
   `quantity_dialog.py` from UX-008).
3. A custom `QStyledItemDelegate` editor with a `setStyleSheet()` applied
   directly per-instance, because — per its own comment,
   `label_print_dialog.py:45-49` — "delegate editors inside a
   globally-styled QTableWidget cannot be reached by QSS selectors" at all.

**Why it matters:** beyond the visual inconsistency, this is real
maintenance debt — three different patterns for the same UI concept means
three different places that can independently drift, break, or need
fixing, and no single component to fix once.

**Suggested fix:** finish the migration this file already started —
Selling Price/Cost Price/Composition qty to the same `QLineEdit` +
`QDoubleValidator` pattern already proven in the Stock group and
`quantity_dialog.py`. Longer-term, worth extracting one shared "currency/
numeric input" widget (validated `QLineEdit`, optional +/- buttons drawn
consistently, one QSS target) used everywhere a number is entered in this
app, rather than three ad-hoc conventions competing.

---

### UX-019: Label Preview dialog has a hardcoded navy background that doesn't match the dark theme

**Screen:** Print Labels → Label Preview dialog
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#272](https://github.com/HMAHD/CB-POS/issues/272)

**What you flagged** — the preview popup's background is a distinct navy
blue instead of matching the rest of the dark UI.

**Root cause (confirmed exactly):** `dark.qss:2334-2341`:
```css
/* ── Label Preview Dialog ── */
QDialog#LabelPreviewDialog {
    background-color: #001F3F;
}
```
`#001F3F` is `Config.COLOR_NAVY` (`cbpos/config.py:37`) — a real, named
constant, not a stray typo — but grepping the codebase shows it's **never
referenced from Python anywhere** (dead constant) and in QSS it's used
~20+ times almost exclusively as *button text color for contrast on bright
buttons* (e.g. green/cyan/yellow primary buttons use `color: #001F3F` so
dark text reads against a bright background), not as a surface/background
tone. `LabelPreviewDialog` is the one dialog left in the app using it as a
full *background* — its immediate neighbor in the same stylesheet file uses
the correct convention:
```css
/* ── CSV Import Dialog ── */
QDialog#CsvImportDialog {
    background-color: #1E1E1E;
}
```
(`dark.qss:2355-2358`). The white label mockup card inside the preview *is*
intentional — it's custom-`QPainter`-drawn to look like a real printed
label (correctly white) — only the dialog's own surrounding background is
wrong.

**Why it matters:** small, but it's the one screen in the whole app that
visibly breaks theme consistency for no functional reason — an easy, safe,
high-confidence fix.

**Suggested fix:** change `dark.qss:2336` (and check `light.qss` for the
same rule) from `#001F3F` to the standard dialog surface color (`#1E1E1E`,
matching `CsvImportDialog` right next to it).

---

### UX-020: CSV Import dialog floating thumbnail — investigated, likely not an app bug

**Screen:** Import CSV dialog
**Severity:** N/A · **Status:** ⚪ Won't Fix (pending your confirmation)
**GitHub:** [#273](https://github.com/HMAHD/CB-POS/issues/273)

**What you flagged** — a small, unexplained thumbnail-like image floating
in the dialog's bottom-right corner.

**Investigated thoroughly, logging the result rather than skipping it.**
I read the full widget tree of `csv_import_dialog.py` and grepped for every
mechanism that could plausibly produce a floating image: `QPixmap`, `QIcon`,
`QMovie`, drag-and-drop handlers, a shared base-dialog class that might
inject a watermark — all zero matches. There is no `QLabel` holding an
image anywhere in this dialog, and `CsvImportWorker` (`cbpos/ui/workers.py`)
has no pixmap/preview code either. Nothing in the code can produce what's
in the screenshot.

**Most likely explanation:** an OS-level or screenshot-tool artifact (e.g.
a window-picker/Mission Control thumbnail caught mid-capture), not
something this app rendered. Marking as Won't Fix rather than leaving it
open indefinitely — flag it again if it reproduces in a plain screen
recording (not a static screenshot), since that would rule out the capture-
artifact explanation.

---

### UX-021: Category Manager tree has no column resize-mode configured, causing a horizontal scrollbar and a squeezed header

**Screen:** Manage Categories dialog
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#355](https://github.com/HMAHD/CB-POS/issues/355) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**What you'd see** — a horizontal scrollbar at the bottom of the category
tree, and the "Products" column header squeezed down to showing just "P".

**Root cause (code-corroborated, not fully pixel-verified):**
`category_manager.py:64-70` sets `setColumnWidth(0, 280)` for the
"Category" column but **never calls `setSectionResizeMode`** for either
column — column 1 ("Products") is left entirely to Qt's default sizing.
Compare with `unit_manager.py` (its sibling "manager" dialog), which
explicitly sets `Stretch` for its Name column and `ResizeToContents` for
the rest (lines 55-57) — Category Manager is the one dialog in this pair
that skips this configuration. With the dialog's `setMinimumSize(640, 500)`
giving the tree panel only a 2:1 share of a fairly compact window, plus
`setRootIsDecorated(True)` + `expandAll()` adding per-level indentation on
top of the fixed 280px first column, there's a plausible, code-supported
path to the tree's true content width exceeding its viewport — matching
both symptoms in your screenshot. I couldn't verify the exact pixel
breakdown without a live render, so flagging this as strongly
code-supported rather than 100% certain.

**Suggested fix:** add explicit resize modes the same way `unit_manager.py`
already does — `Stretch` (or a sized minimum) for "Category", `Stretch` or
`ResizeToContents` for "Products" — removing the competition between a
too-generous fixed column and an unconfigured one.

---

### UX-022: Secondary/danger button class convention is inconsistently applied across 3 dialogs

**Screen:** Category Manager, Unit Manager, Label Print
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#274](https://github.com/HMAHD/CB-POS/issues/274)

**Not from your notes — flagged during code review, a straightforward
consistency cleanup.** This app has an established button-class convention
(`class="primary"` green, `class="danger"` red, `class="secondary"` neutral
outlined — the last one added earlier in this same review pass, originally
for `ValuationDialog`'s Close button). Three dialogs skip it for buttons
that clearly fit an existing class:

- **Category Manager** (`category_manager.py:106-137`) and **Unit Manager**
  (`unit_manager.py:94-127`, confirmed structurally identical code, same
  stacked vertical button layout, same gaps) — "Save"/"Update" correctly
  uses `class="primary"`, "Delete Selected" correctly uses `class="danger"`,
  but **"Clear/New" and "Close" have no class set at all**, falling back to
  plain default styling instead of the `class="secondary"` treatment that
  exists specifically for neutral dismiss/reset actions like these.
- **Label Print** (`label_print_dialog.py:164-178`) — "Print Labels"
  correctly uses `class="primary"`, but **"Remove Selected", "Clear All",
  and "Preview Labels" all have no class set**, so a destructive action
  (Remove/Clear) and a safe, non-destructive one (Preview) render visually
  identically as plain gray buttons, with no differentiation between them.

**Why it matters:** low severity on its own, but it's the kind of thing
that quietly erodes the "clean, deliberate" feel across dialogs a shop
owner uses often (Inventory tools especially) — every other button in
these dialogs already looks intentional; these are the ones that don't.

**Suggested fix:** apply `class="secondary"` to Clear/New and Close in both
manager dialogs, and `class="danger"` to Remove Selected/Clear All +
`class="secondary"` (or leave Preview as the neutral default, but
deliberately, not by omission) in Label Print. While touching these,
worth a quick judgment call on whether the stacked-full-width button
column (shared identically by both manager dialogs) is still the right
layout, or whether a side-by-side row (matching Product Editor's
Cancel/Save convention) reads more consistently with the rest of the app —
not a defect either way, just worth a deliberate decision rather than
whatever the copy-paste happened to produce.

---

### UX-023: Management view shows a completely blank screen until the first sidebar click (confirmed regression)

**Screen:** Management (Dashboard tab specifically, but affects entry into
Management as a whole)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#275](https://github.com/HMAHD/CB-POS/issues/275)

**What you flagged:** entering Management after a fresh app restart shows
nothing at all — no Dashboard, no content, until a sidebar item is clicked.

**Reproduced and root-caused with certainty** — this is a real functional
regression, and worth being upfront: it's one I introduced myself earlier
in this same review, in the fix for issue #227 ("lazy management-view
construction," merged in PR #253).

Constructed a real `MainWindow`, called `switch_to_management()` (the exact
method the side menu's "Management" button triggers), and checked the
internal state directly:
```
management_view.stack.count(): 0
management_view.stack.currentWidget(): None
```
**The stack genuinely has zero widgets in it** — not just "showing the
wrong one." `main_window.py:166-169`:
```python
def switch_to_management(self):
    self.stack.setCurrentWidget(self.management_view)
    self.sales_view.side_menu.setVisible(False)
```
Compare with its sibling right below it, `switch_to_documents()`
(`main_window.py:171-174`), which explicitly does
`self.management_view.switch_tab(5)` before showing the view.
`switch_to_management()` has no equivalent call for the Dashboard tab
(index 0). Since `ManagementView`'s 10 sub-views are now built lazily —
only `_get_or_create_view(index)`, called from `switch_tab()`, ever adds a
widget to the internal stack (`management_view.py:115-118, 150-164`) — and
nothing calls `switch_tab(0)` by default anywhere in `ManagementView.__init__()`
either, the very first entry into Management has genuinely nothing in its
stack until the user manually clicks a sidebar icon, which is the first
thing that ever populates it.

Before the #227 lazy-construction fix, all 10 views were built eagerly in
a fixed order at `ManagementView` construction time, so `QStackedWidget`
defaulted to showing the first one added (Dashboard, index 0) automatically
— that implicit default silently disappeared when construction became
lazy, and nothing was added to replace it.

**Suggested fix:** either add `self.switch_tab(0)` at the end of
`ManagementView.__init__()` (matching the "always land on Dashboard"
default the eager version had for free), or have `switch_to_management()`
call it explicitly the same way `switch_to_documents()` already does for
index 5 — the second option is more consistent with how the Documents
shortcut already handles this exact class of problem.

---

### UX-024: Management sidebar gets permanently stuck collapsed across restarts (confirmed root cause)

**Screen:** Management, `CollapsibleSidebar`
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#276](https://github.com/HMAHD/CB-POS/issues/276)

**What you flagged:** the sidebar shows icon-only, no text labels, on this
same fresh-restart-then-Management screen.

**Reproduced and root-caused with certainty — a second, independent bug on
the same screenshot, not a side effect of UX-023.** Confirmed the button
labels themselves are set correctly (`btn_dashboard.text()` returns
`"Dashboard"`, not empty) — the icon-only appearance is entirely because
`CollapsibleSidebar.is_collapsed` is `True`, and it stays `True` **even when
the actual window is a genuinely wide 2880px** (tested directly: resized
the real `MainWindow` to 2880×1800, switched to Management, and the sidebar
was still collapsed — so this isn't legitimate responsive behavior kicking
in at a narrow width, it's stuck).

**Root cause, `cbpos/ui/widgets/collapsible_sidebar.py`:**
```python
# line 44 — initial state read directly from persisted config, not current width
self.is_collapsed = bool(ConfigService.get("sidebar_collapsed"))
```
```python
# lines 178-193, toggle() — persists on every call, no matter what triggered it
def toggle(self) -> None:
    ...
    ConfigService.set("sidebar_collapsed", self.is_collapsed)
```
```python
# lines 212-223, handle_resize() — auto-collapse/expand based on width
def handle_resize(self, width: int) -> None:
    if width < RESPONSIVE_BREAKPOINT and not self.is_collapsed:
        self.set_collapsed(True)          # -> toggle() -> persists!
    elif width >= RESPONSIVE_BREAKPOINT and self.is_collapsed:
        if not ConfigService.get("sidebar_collapsed"):   # blocked once poisoned
            self.set_collapsed(False)
```
`ManagementView` is laid out once while still narrow (confirmed: width was
640px right after construction, before the window reaches its final size)
— a perfectly normal, transient moment during startup layout. `handle_resize(640)`
correctly auto-collapses the sidebar for that instant... but `set_collapsed()`
calls the same `toggle()` used for a deliberate manual click, which
**permanently writes `sidebar_collapsed = true` to the settings file** —
treating a transient, automatic, responsive-layout collapse as if it were
the user's own explicit preference. From that point on, the auto-*expand*
branch's own guard (`if not ConfigService.get("sidebar_collapsed")`)
refuses to fire, because the flag it's checking is the exact one the
auto-collapse just wrote — so even a later, completely valid wide-window
resize event can never re-expand it. And since it's a persisted setting,
it survives exactly the "close and reopen the app" scenario you described,
every time, forever, until something manually toggles it back.

**Why it matters:** once triggered, this doesn't self-correct — a shop
owner would need to know to manually click a collapse/expand toggle to fix
what looks like a broken layout, with no indication that's the cause.

**Suggested fix:** only persist to `ConfigService` when the collapse was a
genuine user action (a manual toggle-button click), not when it's the
automatic result of `handle_resize()`. Concretely: give `set_collapsed()`
a way to change the visual/internal state without writing to config (e.g.
an internal helper that `toggle()` and `handle_resize()` both call, with
only `toggle()`'s manual-click path doing the `ConfigService.set(...)`),
so a responsive, temporary layout adjustment can never masquerade as a
permanent preference.

---

### UX-025: Add Supplier dialog has zero dialog-specific styling — no objectName, no size, no QSS at all

**Screen:** Purchasing → Suppliers → Add Supplier
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#277](https://github.com/HMAHD/CB-POS/issues/277)

**What you flagged:** too small, not user-friendly, lacks visuals, not a
clean UI.

**Root cause (verified in code):** `SupplierDialog.init_ui()`
(`purchase_view.py:245-287`) never calls `setObjectName()` at all — the
only dialog in this whole review, across ~15 dialogs checked so far, that
skips it entirely. Every other dialog gets a dedicated `dark.qss` block
keyed to its objectName (`QDialog#PaymentDialog`, `QDialog#DiscountDialog`,
`QDialog#AdvancedSearchDialog`, etc.); this one gets **none**, so it falls
back to bare generic widget rules only. There's also no
`setFixedSize`/`setMinimumSize`/`resize()` call anywhere in the class —
compare with `GRNDetailDialog` right above it in the same file, which does
set `setMinimumSize(700, 500)`. And the layout itself is a bare
`QFormLayout(self)` with Save/Cancel appended as *just another form row*
(`self.form_layout.addRow(btn_box)`), not a docked button bar — no
sectioning, no visual hierarchy at all.

**Also flagged:** Payment Terms uses a raw `QSpinBox` (line 253) — the
exact widget class this app's own `product_editor.py:142-143` comment
already documents as "break[ing] under QSS," the same finding as UX-018.
One more place that migration never reached.

**Suggested fix:** give it a real `objectName` and a proper `dark.qss`
block (background surface color, minimum size, section spacing) matching
the treatment every other data-entry dialog in this app already gets;
move Save/Cancel into a proper button row instead of a form row; migrate
Payment Terms to the same `QLineEdit` + validator pattern proposed in
UX-018 rather than adding a 4th inconsistent numeric-input convention.

---

### UX-026: New GRN "Add Product" search is a genuinely broken feature, not just unpolished

**Screen:** Purchasing → New GRN
**Severity:** P0 · **Status:** 🟢 Fixed — regression tests added, verified against the real completer and cache resolution
**GitHub:** [#278](https://github.com/HMAHD/CB-POS/issues/278)

**What you flagged:** doesn't show products when typing.

**Confirmed as a real, unambiguous bug — not a threshold/sensitivity
issue.** `purchase_view.py:399-401`:
```python
self.completer = QCompleter()
self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
self.product_search.setCompleter(self.completer)
```
`QCompleter()` is constructed with **no model and no string list at all**
— not here, not anywhere else in the file (`self.completer` is never
touched again after these 3 lines). A completer with nothing to complete
against can never show a popup, no matter what's typed — this isn't a
tuning problem, the feature has no data source. There's also **no
`textChanged` connection** on `product_search` — the only signal wired is
`returnPressed.connect(self.add_product_to_grid)` (line 396), so nothing
happens at all until Enter is pressed, despite the placeholder text
("Scan Barcode or Type Product Name...") implying live search.

**And once Enter *is* pressed, it's still not what it looks like it should
be** — `add_product_to_grid()` (lines 633-661) calls
`ProductService.search(query)` and, if anything matches, **silently takes
`products[0]`** with no picker shown for disambiguating between multiple
matches. Compare with the correct, working pattern one file over —
`sales_view.py`'s `setup_autocomplete()` builds its `QCompleter` from a
real, async-loaded product-name list and sets `PopupCompletion` mode
explicitly; none of that exists here.

**Why P0, not P1:** this directly blocks a core Purchasing workflow —
receiving stock via GRN — for anyone who doesn't already know to type a
name and press Enter, and even then it silently guesses which product you
meant.

**Suggested fix:** wire this the same way `sales_view.py` already does:
build the completer from a real product-name source (async-loaded, same
`AutocompleteLoadWorker` pattern already proven there), connect
`textChanged` for live filtering, and either show a small results list to
pick from or require an exact/barcode match before adding — don't silently
take the first fuzzy match for something as consequential as receiving
stock into inventory.

---

### UX-027: New GRN header row (Supplier/Ref#/Date) has no width balancing — Date field looks tiny

**Screen:** Purchasing → New GRN
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#279](https://github.com/HMAHD/CB-POS/issues/279)

**What you flagged:** top element alignments "way off," specifically the
date selector.

**Root cause (verified in code):** `purchase_view.py:373-391` — a plain
`QHBoxLayout` with `Supplier` combo, `Ref #` line edit, and `Date`
(`QDateEdit`) added with **no stretch factors and no width constraints on
any of the three**. `QComboBox`/`QLineEdit` both grow to fill available
space by Qt default; `QDateEdit` has no `setCalendarPopup(True)` and no
size-policy override, so it renders at its bare natural sizeHint — just
wide enough for the date text plus its always-visible spin arrows — next
to two widgets that are stretching to fill the row. Not an explicit "make
this one small" bug, just nothing balancing the row at all.

**Suggested fix:** give the row explicit stretch factors (e.g. Supplier
2, Ref# 2, Date 1, rather than leaving it to whatever each widget's bare
sizeHint happens to be), or set a sensible `setMinimumWidth` on the date
field so it doesn't read as an afterthought next to the other two.

---

### UX-028: Supplier-selection combos in Purchasing are plain, non-searchable comboboxes

**Screen:** New GRN, GRN History tabs
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#280](https://github.com/HMAHD/CB-POS/issues/280)

**What you flagged:** with 100+ suppliers, a plain dropdown becomes hard to
use — needs to support typing to filter.

**Confirmed, and there's already a working pattern in this exact codebase
to copy.** `purchase_view.py:376` (New GRN) and lines 442/447 (GRN
History's supplier + status filters) are all plain `QComboBox()` —
populated via `.addItem(...)`, no `setEditable(True)`, no `QCompleter`
anywhere. Meanwhile `payment_dialog.py:330-342` already implements exactly
what's needed, for the Payment dialog's customer selector:
```python
self.cmb_customer.setEditable(True)
self.cmb_customer.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
self.cmb_customer.lineEdit().setPlaceholderText(_t("payment.search_customer_placeholder"))
completer = QCompleter(names, self)
completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
completer.setFilterMode(Qt.MatchFlag.MatchContains)
self.cmb_customer.setCompleter(completer)
```
**Suggested fix:** apply this exact recipe to the New GRN supplier combo
(and GRN History's supplier filter) — same file already proves the
pattern works, this is a copy, not an invention.

---

### UX-029: GRN History "Status" filter shows "All Suppliers" instead of "All Statuses"

**Screen:** Purchasing → GRN History
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#281](https://github.com/HMAHD/CB-POS/issues/281)

**Not from your notes, but visible in the same screenshot — a small,
concrete copy-paste bug.** `purchase_view.py:530` (populating the Status
combo) and line 610 (populating the Supplier combo) both call the exact
same translation key:
```python
self.history_status_combo.addItem(_t("purchase.all_suppliers"), None)
...
self.history_supplier_combo.addItem(_t("purchase.all_suppliers"), None)
```
There is no `purchase.all_statuses` key anywhere in `en.json`/`si.json`/
`ta.json` — it was never created; the Status combo's default row was
copy-pasted from the Supplier combo and the key was never swapped.

**Suggested fix:** add a `purchase.all_statuses` → "All Statuses" key
(en/si/ta) and use it at line 530 instead of `purchase.all_suppliers`.

---

### UX-030: GRN History and Payables tables have no empty-state message

**Screen:** GRN History, Payables tabs
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#258](https://github.com/HMAHD/CB-POS/issues/258) (sub-issue of [#254](https://github.com/HMAHD/CB-POS/issues/254))

**Not from your notes — flagged during code review.** `refresh_history()`
(`purchase_view.py:571-590`) and the Payables supplier table both render a
completely blank table body when there are zero rows — just headers, no
message, matching the empty screenshots. This app already has an
established convention for this: `customer_view.py:97-107`,
`pricelist_view.py`, `inventory_view.py`, and `reports/report_viewer.py`
all insert a single spanning, centered, gray placeholder row
(`_t("...empty_state")`) when a list is empty. GRN History and Payables
never adopted it.

**Suggested fix:** apply the same spanning-empty-row pattern already used
in those 4 other views — it's a small, already-proven snippet, not a new
mechanism.

---

### UX-031: Payables uses a deliberate but undocumented navy sub-theme, shared with Credit Book

**Screen:** Payables, Credit Book, Reports, Document Browser, Price Lists,
Payment Methods — confirmed app-wide, see the full scope list below
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#260](https://github.com/HMAHD/CB-POS/issues/260) — parent issue, tracks sub-issues for each confirmed location

**What you flagged:** the whole Payables screen is blue, not a good look.

**Worth getting the framing right — this is not the same class of mistake
as UX-019's `LabelPreviewDialog`.** That one was a single stray rule,
clearly a forgotten leftover. This one is comprehensive and internally
consistent: `dark.qss:2666-2900`, explicitly titled in a comment as
`/* CREDIT BOOK VIEW — Drill-down Navigation */`, contains ~20 rule blocks
covering essentially every widget in both Payables pages (search input,
supplier table + selection state, header card, name/phone/balance labels,
action buttons, date filters, ledger table, footer totals) — and **every
single `Payable*` selector is paired 1:1 with an equivalent `Credit*`
selector** for `credit_book_view.py`'s Customer Credit Book feature (e.g.
`QTableWidget#CreditCustomerTable, QTableWidget#PayableSupplierTable`,
`QFrame#CreditHeaderCard, QFrame#PayableHeaderCard`, one rule, two
features). This was authored once, deliberately, as a distinct "ledger
drill-down" visual language (navy `#0A1929`/`#0D2137` surfaces, `#112240`
borders, `#00BCEB` cyan accents) and reused across two unrelated features
— it just never got reconciled with the rest of the app's actual standard
dark theme (`#1E1E1E`/`#252526`).

**Update — confirmed directly against `credit_book_view.py`:**
`dark.qss:2704-2732` styles `QTableWidget#CreditCustomerTable,
QTableWidget#CreditLedgerTable, QTableWidget#PayableSupplierTable,
QTableWidget#PayableLedgerTable` as one combined rule (same for the header
card, back button, and pay button at lines 2772/2787/2826) — it's the exact
same rule set, not just a similar one. Credit Book is not a separate case to
investigate later; it's the same bug, same fix, same decision.

**Why it matters:** whatever the original intent, the result today is that
two specific screens look like they belong to a different app, with no
visible reason (no theme toggle, no "you're in a special mode" indicator)
— which is exactly what reads as inconsistent to a user moving between
tabs.

**DECIDED (2026-09-06):** you've ruled directly on this — "there
shouldn't be a navy theme system, only have dark and white theme for now."
This is no longer an open product question; it's a confirmed fix, scoped
below.

**Full confirmed scope — every screen carrying this exact palette
(`#001F3F`/`#0A1929`/`#0D2137`/`#112240`/`#00BCEB`), found via a
full-codebase grep prompted by your decision, not just the screens
already reviewed by screenshot:**

| Screen | objectName(s) | QSS location |
|---|---|---|
| Payables + Credit Book | `Payable*`/`Credit*` (shared 1:1 rule set) | `dark.qss:2666-2900` |
| Reports | `ReportViewer`, `ReportSidebarPanel`, `ReportCategoryCount`, `ReportNavItem` | `dark.qss:2387-2464` (UX-041) |
| Document Browser (main table) | `DocTable` | `dark.qss:2980-3002` (UX-052/053) |
| Document Browser (detail panel) | `DocDetailCloseBtn`, `DocItemsTable`, `DocInfoLabel`, `DocReprintBtn`, `DocRefundBtn`/`DocVoidBtn`, `DocPrevBtn`/`DocNextBtn` | `dark.qss:3020-3124` — not yet reviewed by screenshot, found in this audit |
| Price Lists | `PriceListSidebarPanel`, `PriceListNavItem`, `PriceListContentPanel`, `PriceListHeader`, `PriceListDataTable`, `PriceListFooter` | `dark.qss:3120-3289` — now confirmed by screenshot too (see UX-066/071) |
| Payment Methods (card list) | `PMCard` (`payment_methods_view.py:139`) | `dark.qss:3290-3305` — now confirmed by screenshot too (see UX-106); lighter touch (card background + `#00BCEB` hover border only, not a full-screen background) |

That's **6 confirmed locations**, not the 2-3 found so far by screenshot
review alone — this was never just a Payables/Credit Book quirk.

**Suggested fix — no longer a choice, this is the plan:** retire the navy
sub-theme everywhere it appears above, converting every listed selector
to the app's two real themes (`#1E1E1E`/`#252526` dark surfaces,
matching Light theme equivalents) — same structural rules, just the
standard palette instead of the one-off navy. Price Lists and Payment
Methods haven't had a full UI/UX pass yet (no screenshot reviewed), so
when either of those screens comes up for review, this theme fix is
already known and doesn't need rediscovering — just apply the same
conversion. This should land as one focused pass across all 6 locations
during the fixing phase, not 6 separate patches, since it's the same
color swap repeated.

---

### UX-032: Payables supplier list is double-click-only — same pattern as UX-009

**Screen:** Payables tab
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#372](https://github.com/HMAHD/CB-POS/issues/372) (sub-issue of [#264](https://github.com/HMAHD/CB-POS/issues/264))

**What you flagged:** the only way to open a supplier's ledger is
double-clicking a row, and a user might never discover that.

**Confirmed, identical pattern to UX-009 (Select Customer dialog).**
`purchase_view.py:770-782` wires exactly one interaction:
```python
self.payable_supplier_table.doubleClicked.connect(self._on_payable_supplier_double_click)
```
No button, no Enter/Return key handling, no context menu — the same gap
already logged for Select Customer, now confirmed a second time in a
completely different part of the app.

**Suggested fix:** same as UX-009 — add a visible "Open"/"View Ledger"
button and bind Enter to the same handler, rather than relying on an
undiscoverable mouse gesture.

---

### UX-033: Payables ledger shows zero entries despite a non-zero balance (needs one live check to fully confirm)

**Screen:** Payables tab, supplier detail view
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#282](https://github.com/HMAHD/CB-POS/issues/282)

**What you'd notice** — the header shows "Payable: Rs. 62,000.00" in red,
but the ledger table below is completely empty and the footer shows
"Purchases: Rs. 0.00 / Payments: Rs. 0.00 / Closing: Rs. 0.00" — directly
contradicting the number right above it on the same screen.

**Most likely explanation, and it's a real code-confirmed distinction:
the header and the ledger table read from two different places.** The
header (`_update_payable_header`, `purchase_view.py:989-1007`) shows
`Supplier.current_payable` — a **denormalized running-total column with no
date filter at all**. The ledger table (`reload_payable_ledger`,
`purchase_view.py:1009-1033`) queries `SupplierLedgerEntry` rows **within
whatever date range is selected**, defaulting to `today − 1 month`
(`pay_date_from`/`pay_date_to`, lines 866/876) — matching the screenshot's
"From: 2026-08-06 To: 2026-09-06." If the purchase(s) that produced this
Rs. 62,000 balance happened more than a month before the screenshot, the
ledger for "last month" legitimately shows nothing while the unfiltered
header total is still correct — these can disagree by design, not by bug.

There's already an "All" button (`btn_pay_all` → `show_all_payable_dates`,
line 1035) that calls the same query with no date bounds — if clicking it
reveals the missing entries, this confirms the default-filter explanation
above and the fix is just a friendlier default (see below). **I could not
verify this against live data** (didn't query the database), so I'm
flagging the one thing that would fully settle it: **click "All" on this
exact supplier — if the Rs. 62,000 worth of entries appears, it's the
filter; if it's still empty, the write path that creates `SupplierLedgerEntry`
rows when a purchase is committed (`supplier_payable_service.py:97-130`,
called from `PurchaseService.commit_purchase`) needs tracing next, since
that would mean the ledger table is never actually getting written for
this data.**

**Suggested fix (assuming the filter explanation holds):** a header
balance with a completely empty ledger and a contradicting "Rs. 0.00"
footer, with no date-range indicator drawing attention to *why*, is
confusing regardless of correctness — either default the range wider (e.g.
this year, not last month), or show an inline hint when the visible range
doesn't account for the full balance ("Showing 0 of Rs. 62,000 — try
expanding the date range").

---

### UX-034: Credit Book "Outstanding Debt" column header is clipped to "TSTANDING DI"

**Screen:** Credit Book, customer list
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#356](https://github.com/HMAHD/CB-POS/issues/356) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**What you flagged:** the credit book is "as like before" — the customer
list has the same rough edges as the tables reviewed earlier.

**Root cause (verified in code):** `credit_book_view.py:99-102`:
```python
self.customer_table.setColumnCount(5)
self.customer_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
self.customer_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
self.customer_table.setColumnHidden(0, True)
```
Only Name (1) and Phone (2) get an explicit resize mode. The Debt column
(3) — whose header text is `"customer_header_debt": "Outstanding Debt"`
(`cbpos/i18n/en.json:629`, set at `credit_book_view.py:297`) — is left on
Qt's default `Interactive` mode, so its width is whatever Qt guesses from
row content, not from the header label. Since the numeric values ("2500.00")
are shorter than the header text, the column ends up narrower than the
label needs, and the header text gets clipped — exactly the "TSTANDING DI"
seen in the screenshot (the start of "OU" and end of "T" are cut off).

**Why it matters:** this is the same class of bug as UX-010/UX-017 (both
already logged as truncating real data) — the third confirmed instance,
now on a column header rather than a cell.

**Suggested fix:** give the Debt and Credit Limit columns an explicit
resize mode too — `ResizeToContents` sized off the header label
specifically (or a fixed minimum width computed from the longest expected
value/header), not just Name and Phone.

---

### UX-035: Credit Book customer list is double-click-only — same pattern as UX-009/UX-032

**Screen:** Credit Book, customer list
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#373](https://github.com/HMAHD/CB-POS/issues/373) (sub-issue of [#264](https://github.com/HMAHD/CB-POS/issues/264))

**What you flagged:** "the only way to select a customer is double click,
as again it keeps going" — you've now hit this exact gap on three separate
screens.

**Root cause (verified in code):** `credit_book_view.py:108`:
```python
self.customer_table.doubleClicked.connect(self._on_customer_double_click)
```
No button, no Enter/Return key binding, no context menu, anywhere in
`_build_customer_list_page` (lines 70-125) — identical to UX-009 (Select
Customer dialog) and UX-032 (Payables supplier list). This is now the
**third** confirmed instance of the exact same interaction gap, in three
different parts of the app, built independently of each other.

**Why it matters:** at this point it isn't three isolated oversights, it's
a missing convention. A user who's never been told "double-click a row to
open it" — and the app never says so — has no way to discover this
anywhere in the UI.

**Suggested fix:** the fix here shouldn't be three separate patches. Worth
adding a small shared helper/pattern (e.g. a `TableSelectMixin` or just a
documented convention in CLAUDE.md) that every "list → drill into row"
table follows: a visible action button bound to the current selection, and
Enter/Return wired to the same handler, applied consistently to Select
Customer, Payables, and Credit Book in one pass.

---

### UX-036: "Adjust Balance" button uses the app's warning color for a routine action

**Screen:** Credit Book, customer detail page
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#283](https://github.com/HMAHD/CB-POS/issues/283)

**Not from your notes — found while reviewing the customer detail page you
sent.** Look at the 4 action buttons: Receive Payment (cyan, active),
Print Statement (navy), **Adjust Balance (dark-gold background, bold
yellow text)**, Edit Customer (navy). Adjust Balance visually reads as a
warning or destructive action — the same yellow CLAUDE.md defines as the
**Warning** color (`#FFDC00`) — even though it's a routine, legitimate
action (correcting a data-entry mistake), no more dangerous than Edit
Customer sitting right next to it in plain navy.

**Root cause (verified in code):** `credit_book_view.py:189-207` gives
each of the 4 buttons its own unique `setObjectName()` (not a shared
`class=` property), and only `CreditAdjustBtn`'s QSS rule
(`dark.qss:2854-2867`) sets `background-color: #332800; color: #FFDC00;`
— a one-off style nothing else in the row shares.

**Why it matters:** color is a signal. A yellow/gold button next to three
neutral ones tells the user "be careful here" even when there's no
particular reason to be more careful adjusting a balance than editing a
customer's other details — it also doesn't match the semantic case where
yellow *should* mean something (e.g. an actual warning state).

**Suggested fix:** give Adjust Balance the same neutral/secondary styling
as Print Statement and Edit Customer, unless there's a deliberate reason
to flag it — in which case make that reason visible too (e.g. a tooltip
explaining why it needs extra care), not just an unexplained color change.

---

### UX-037: Credit Book ledger shows zero entries despite a non-zero debt — same pattern as UX-033, now confirmed on a second screen

**Screen:** Credit Book, customer detail page (e.g. Saman Kumara: "Debt:
Rs. 7,200.00" header, but the ledger table and footer all read Rs. 0.00)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#284](https://github.com/HMAHD/CB-POS/issues/284)

**What you flagged:** "last two images is customer selected and that also
bluish, need to fix and check that UI/UX issues as well."

**Root cause (verified in code) — this is the exact same two-source split
already logged as UX-033 for Payables, now confirmed in Credit Book too:**
- Header "Debt" value: `update_header()` reads
  `CustomerCreditService.get_customer_summary(customer.id)["current_debt"]`
  → `Customer.current_debt`, a running total with **no date filter**.
- Ledger table: `reload_ledger()` (`credit_book_view.py:439-463`) always
  applies `date_from`/`date_to` from the two `QDateEdit` widgets, which
  default to `QDate.currentDate().addMonths(-1)` through today (lines
  225/235) — a fixed one-month window that resets **every time a customer
  is opened**, with no persisted preference. `show_all_dates()` (465-471)
  correctly bypasses the filter when "All" is clicked — matching the same
  "All" escape hatch already found in Payables.

**Why it matters:** this is no longer a one-off — the same
header-vs-filtered-ledger split now shows up on **both** money-ledger
screens in the app (Payables and Credit Book), sourced from parallel
service methods (`SupplierPayableService`/`CustomerCreditService`) that
were clearly built from the same template. Fixing one and not the other
would just leave the same confusing gap on the second screen.

**Suggested fix:** same as UX-033 — default the range wider (e.g. this
year, or "since account opened" up to a reasonable cap) or show an inline
hint when the visible range can't account for the full balance. Worth
fixing both screens together in the same pass, since they share the root
cause.

---

### UX-038: New Customer dialog's Commercial tab has mismatched field widths — recurring pattern to watch for

**Screen:** Credit Book → "+ Add Customer" → Commercial tab
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#367](https://github.com/HMAHD/CB-POS/issues/367) (sub-issue of [#263](https://github.com/HMAHD/CB-POS/issues/263))

**What you flagged:** "Credit Limit, Payment Terms, Price List — those
[fields] not aligned properly and not clean UI/UX... not just here, if
you find similar elements somewhere, those need to align properly,
remember that."

**Root cause (verified in code):** `customer_editor.py:106-142`,
`create_commercial_tab()`, uses a real `QFormLayout` (line 108,
`setLabelAlignment(AlignRight)`), so the **label column** is actually
fine — Qt auto-sizes it to the widest label and right-aligns every label
against it. The misalignment you're seeing is in the **field column**:
none of TIN (`QLineEdit`, line 117), Credit Limit (`QDoubleSpinBox`, line
120), Payment Terms (`QSpinBox`, line 124), or Price List (`QComboBox`,
line 128) get an explicit `setMinimumWidth`/`setFixedWidth`. With the
form's `ExpandingFieldsGrow` policy (line 112), the `QLineEdit` stretches
to fill the available width while the two spin boxes stay at their native,
stepper-driven minimum size and the combo sits at yet a third width — so
TIN reads much wider than Credit Limit/Payment Terms, which read narrower
still than Price List, with no shared column to anchor the eye.

**A second, compounding issue on the same two fields:** Credit Limit and
Payment Terms use plain `QDoubleSpinBox`/`QSpinBox` with native +/-
steppers. `product_editor.py:142-143` has an explicit code comment about
this exact widget class: `# Stock group — QLineEdit instead of
QDoubleSpinBox for clean rendering (QDoubleSpinBox +/- buttons break under
QSS)`, and that dialog migrated its own numeric fields to `QLineEdit` +
validator specifically to avoid it. This dialog was never updated to match
— it's the same known-broken pattern already logged as UX-018, now found
a second place it was never fixed.

**Why it matters — and why "remember that" is the right instinct:** this
isn't a one-dialog fix. Any `QFormLayout` in the app that mixes a
free-stretching `QLineEdit`/`QComboBox` with a native-sized spin box in
the same field column will show this same "some fields wide, some
narrow, none aligned to a shared edge" look. Worth treating as a form
convention to check across the app, not a single-dialog patch.

**Suggested fix:** give every field in a given `QFormLayout` a consistent
minimum width (e.g. `setMinimumWidth(200)` on the field column, or a
shared constant used across all editor dialogs), and replace the Credit
Limit/Payment Terms spin boxes with `QLineEdit` + validator, matching the
fix already applied in `product_editor.py` — same convention, same look,
same behavior, wherever a numeric field appears in a form.

---

### UX-039: Only 2 of 15 date pickers in the app have any styling at all

**Screen:** App-wide — Credit Book, Payables, Documents, Reports,
Dashboard, Stock Take, Data Export, Sale History Reprint, Admin Tools,
Data Safety
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#262](https://github.com/HMAHD/CB-POS/issues/262) — parent issue, tracks sub-issues for each confirmed location

**What you flagged:** "print statement dialog... date picker not good
throughout application, have a date picker either fix that widget perfect
for everywhere and works accurately and match style, or fix it separately,
either way your choice, you're the expert."

**Investigated app-wide, not just the one dialog — and it's worse than
one broken widget, it's one un-themed widget class used in 15 places.**
Every `QDateEdit` construction site in `cbpos/ui/`:

| File | objectName | Styled in QSS? |
|---|---|---|
| `dashboard_view.py:238,249` | `PeriodDateEdit` | ✅ yes (`dark.qss:1692`) |
| `reports/filter_widget.py:55,58` | `ReportDateEdit` | ✅ yes (`dark.qss:2507-2524`) |
| `credit_book_view.py:222,232` | `CreditDateEdit` | ❌ no — dead name, no matching rule |
| `document_view.py:114,123` | `DocDateEdit` | ❌ no — dead name, no matching rule |
| `purchase_view.py:863,873` | `PayableDateEdit` | ❌ no — dead name, no matching rule |
| `receipt_reprint_dialog.py`, `data_export_dialog.py`, `customer_statement_dialog.py`, `admin_tools_view.py`, `data_safety_view.py`, `history_view.py`, `stock_take_view.py`, `pricelist_view.py:411,415`, `purchase_view.py:452,459` | *(none set)* | ❌ no |
| `purchase_view.py:378` (`date_input`) | no `setCalendarPopup` call found — worth a direct check, this could be a functional gap (field may not open a picker at all), not just styling | none | ❌ no |

**Root cause (verified in code):** exactly 2 of the 5 distinct
`QDateEdit` objectNames used in the app have a matching QSS rule —
`#PeriodDateEdit` (`dark.qss:1692`, `light.qss:1735`) and `#ReportDateEdit`
(`dark.qss:2507-2524`, `light.qss:2407-2424`) — covering the 2 Dashboard
and 2 Reports fields (4 widgets across 2 of the 15 file-sites). There is
**no generic `QDateEdit { ... }` type-selector rule** in either QSS file,
so the other 13 sites fall back to Qt's bare native styling, including 3
with their own dead objectName (`CreditDateEdit`, `DocDateEdit`,
`PayableDateEdit`) that nothing in either QSS file ever matches — and
there is **no `QCalendarWidget` rule anywhere**, so the calendar popup
itself is unstyled everywhere in the app, including on the 2 screens that
do have a styled input field (this is the same broken popup already
logged as UX-013, now confirmed to be a symptom of this wider gap, not a
one-off). None of the 15 sites set `setMinimumDate`/`setMaximumDate`.

**Correction:** the table above originally undercounted the "no
objectName" bucket by 2 sites (`pricelist_view.py:411,415` and
`purchase_view.py:378`) — now added back in. `pricelist_view.py`'s two
fields are confirmed functional (`setCalendarPopup(True)` is called,
re-verified directly while reviewing UX-069) — just unstyled, same as
the rest of the bucket. `purchase_view.py:378` (`date_input`) is still an
open question — no `setCalendarPopup` call was found for it, which would
mean that field can't open a picker at all, a functional bug rather than
a styling one — flagged here for a direct check next time Purchasing's
New GRN tab comes up again, rather than asserted as confirmed.

**Why it matters:** you're right that it "isn't good throughout the
application" — a shop owner filtering Credit Book, then Payables, then
Reports sees a differently-dressed date field on every screen (some
native-grey, one themed), and every calendar popup that opens looks
broken/unstyled regardless of which field opened it.

**Suggested fix — my recommendation as the one to make:** don't keep
patching per-instance objectNames (`CreditDateEdit`, `DocDateEdit`,
`PayableDateEdit` already exist and are just never matched — that's dead
naming, not a fix waiting to happen). Add **one**
generic `QDateEdit { ... }` rule plus a matching `QCalendarWidget { ... }`
+ `QCalendarWidget QAbstractItemView { ... }` rule block to both
`dark.qss`/`light.qss`, styled once to match the app's real theme, and let
every instance inherit it automatically — including the ones with no
objectName at all. This fixes all 15 places (and any future one) in a
single pass instead of 13 separate patches, and finally makes the
already-broken calendar popup (UX-013) render correctly everywhere instead
of just being patched on the Dashboard.

**Feature idea:** while touching this, consider a shared `DateRangeWidget`
(From/To + a row of quick presets: Today, This Week, This Month, This
Year, All) as a reusable component — Credit Book, Payables, and Reports
all hand-build a near-identical from/to + "All" row today (each with its
own default-window gap, see UX-033/UX-037); one shared widget would fix
the styling, the missing bounds, and the default-window confusion in one
place instead of three.

---

### UX-040: Customer Statement dialog has uneven filter-row and summary spacing

**Screen:** Credit Book → customer detail → "Print Statement"
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#285](https://github.com/HMAHD/CB-POS/issues/285)

**What you flagged:** "print statement dialog have lot issues" (grouped
with the date-picker complaint above — the date-picker part is now
UX-039; this entry covers what's specific to this dialog's own layout).

**Root cause (verified in code):** `customer_statement_dialog.py` uses the
same `QDateEdit` pair as Credit Book (lines 67-78, no bounds, same
`addMonths(-1)`→today default — inherits UX-039 and UX-037's gaps
directly). Beyond the date pickers:
- The filter row (line 63, one `QHBoxLayout`) packs `class="transparent"`
  labels (65, 73) next to the date fields and an accent-styled refresh
  button (81) with no explicit per-row margin/spacing — it only inherits
  the dialog's blanket `layout.setSpacing(10)` (line 46), so nothing in
  this row was actually tuned for its own content.
- The summary line (89-103) mixes four different `class` properties
  (`transparent`, `debit`, `credit`, `bold`) packed left-to-right with a
  stretch, but no column/grid alignment — so the labels and their values
  don't line up into a predictable visual rhythm the way a small
  `QGridLayout` would give them.

**Why it matters:** this is a lower-severity, "looks slightly off" issue
rather than a functional one, but it's the kind of thing that reads as
unpolished specifically because the layout was assembled ad hoc
(`QHBoxLayout` + manual classes) rather than with the same structured
layout (`QFormLayout`/`QGridLayout`) used elsewhere in the app.

**Suggested fix:** rebuild the filter row and summary line with a small
`QGridLayout` (label column, value column) instead of packed
`QHBoxLayout`s — same fix direction as UX-038, applied to a second
dialog.

---

### UX-041: Reports screen is a third, independent navy-themed screen — not shared with UX-031

**Screen:** Reports (category sidebar + content pane)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#345](https://github.com/HMAHD/CB-POS/issues/345) (sub-issue of [#260](https://github.com/HMAHD/CB-POS/issues/260))

**What you flagged:** "same blue problem" — you spotted this on sight,
correctly, as the same family of issue already logged for Payables/Credit
Book.

**Worth getting the framing exactly right, because it's a slightly
different bug than UX-031, not the same one:** UX-031 is one shared QSS
rule block reused by two screens (`Credit*`/`Payable*` selectors paired
1:1 in the same rule). Reports is **not** wired into that block — it has
its own, separately-written objectNames and rules using the same navy
palette:
- `#ReportViewer { background-color: #001F3F; }` (`dark.qss:2387-2389`)
- `#ReportSidebarPanel { background-color: #0A1929; }` (`dark.qss:2398-2401`)
- `#ReportCategoryCount` (the "3"/"4"/"2" badges) → `background-color:
  #112240;` (`dark.qss:2431-2439`)
- checked nav item → `background-color: #0D2847;` accent `#00BCEB`
  (`dark.qss:2459-2464`)

**Why it matters:** this is now the **third** screen carrying this exact
navy palette (`#001F3F`/`#0A1929`/`#112240`/`#00BCEB`), each one coded
independently rather than sharing a single reusable style — meaning it
isn't a one-off leftover (UX-019) or even a single deliberate decision
applied twice (UX-031). It looks like an unnamed "financial/data drill-down"
house style that's been hand-copied every time someone builds a screen like
this, with no shared class or documented name anywhere. That makes it
harder, not easier, to fix consistently — three separate rule blocks to
change instead of one.

**Update — make that "six, and it's decided":** Document Browser
(UX-052/053), Price Lists, and Payment Methods all carry the identical
palette too — see the full 6-location table now recorded in UX-031, which
also carries the decision: **you've ruled this out entirely — "there
shouldn't be a navy theme system, only dark and white for now."** This is
no longer an open question anywhere in this catalog.

**A smaller, compounding issue on the same block:** the category header
label (`ReportCategoryLabel`) is plain transparent text
(`dark.qss:2423-2429`) while its count badge (`ReportCategoryCount`) gets
its own pill background — two different visual treatments for what reads
as one header row — and the badge's text color (`#3A5A7A` on `#112240`) is
low-contrast, borderline hard to read.

**Suggested fix:** same fix as UX-031, decided — retire this palette here
too, converting `#ReportViewer`/`#ReportSidebarPanel`/`#ReportCategoryCount`/
the checked nav-item rule to the standard `#1E1E1E`/`#252526` surface
colors, in the same pass as the other 5 confirmed locations rather than
as a separate cleanup.

---

### UX-042: Reports category panel scales far wider than its content needs

**Screen:** Reports, middle category panel
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#286](https://github.com/HMAHD/CB-POS/issues/286)

**What you flagged:** "report list is too wide."

**Root cause (verified in code):** `report_viewer.py:114` — a `QSplitter`
(`objectName="ReportSplitter"`) with:
```python
splitter.setSizes([280, 720])       # report_viewer.py:282
sidebar.setMinimumWidth(260)        # report_viewer.py:284
```
No `setStretchFactor()` is ever called. A plain `QSplitter` without stretch
factors keeps its panels' **proportional ratio** (roughly 28:72) as the
window resizes, rather than pinning the category list to a sensible fixed
width and giving all the extra space to the report content on the right.
On a large monitor (the screenshots are 2880px wide) that stretches the
category panel — whose actual content is short labels like "AUDIT" and
"Stock Movement Audit" — into far more width than it needs, which is
exactly the "too wide, lots of dead space" look in the screenshot. Nothing
inside the panel (`ReportNavContainer`, lines 135-145) sets a max-width
either, so there's nothing to stop it from growing.

**Why it matters:** wasted horizontal space in a navigation list isn't
just cosmetic here — the whole right pane (where the actual report table/
chart needs the room) is the one that gets shortchanged as a result.

**Suggested fix:** set explicit stretch factors —
`splitter.setStretchFactor(0, 0)` (sidebar doesn't grow) and
`splitter.setStretchFactor(1, 1)` (content takes all extra space) — and
add a `setMaximumWidth(320-360)` on the sidebar panel so it stays a fixed,
comfortable list width regardless of monitor size, exactly like a
professional 3-pane app (email client, IDE) would.

---

### UX-043: No shared empty-state component — every screen hand-builds its own

**Screen:** App-wide (Reports' "Select a Report" placeholder used as the
trigger for this review)
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#254](https://github.com/HMAHD/CB-POS/issues/254) — parent issue, tracks sub-issues for each confirmed location

**Not from your notes — found while checking whether Reports' "Select a
Report" placeholder reused an existing pattern.** It doesn't. Reports
builds its own: a custom-painted bar-chart icon (`_ReportPlaceholderIcon`,
`report_viewer.py:53-93`) + `ReportEmptyText`/`ReportEmptySubtext` labels
(198-217). Checking around the app for the "empty state" pattern already
referenced in UX-001/UX-030 turns up **three different implementations**,
not one shared one:
- Reports: icon + title + subtext, custom widget (above).
- `customer_view.py:97-107`: a single spanned `QTableWidgetItem` with gray
  text *inside* the table — a completely different technique.
- `pricelist_view.py`, `sales_view.py`: their own variations again, per a
  grep across the codebase.

**Why it matters:** for an app aiming at an "industry-grade, every screen
looks intentional" bar, empty states are one of the highest-visibility
places this shows — a shop owner sees them constantly (no products, no
customers yet, no report run yet), and right now every screen that has one
looks and behaves slightly differently, with no shared visual language.

**Suggested fix / feature idea:** extract one reusable `EmptyStateWidget`
(icon + title + optional subtext + optional action button) into
`cbpos/ui/widgets/`, themed once in QSS, and swap every ad hoc empty-state
implementation in the app over to it — Reports, POS cart (UX-001/UX-005),
GRN History/Payables (UX-030), and any table view that currently shows
nothing or a bare text row when empty.

---

### UX-044: Current nav item highlight is much weaker when the sidebar is collapsed

**Screen:** Main sidebar, both collapsed and expanded states, every screen
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#287](https://github.com/HMAHD/CB-POS/issues/287)

**Not from your notes — found while investigating the expand/collapse
complaint below.** Comparing your two screenshots: collapsed, the current
section (Reports) is marked only by a thin blue left-edge bar next to its
icon; expanded, it gets that same bar **plus** a full-width grey background
box behind the icon+label. That's a real, noticeable difference in how
easy it is to tell which section you're on.

**Root cause (verified in code):** `dark.qss:581-586` — there is only
**one** checked/active rule, meant to apply the same in both states:
```css
QToolButton#SidebarButton:checked, QToolButton#SidebarButton[active="true"] {
    background-color: #2A2A2A;
    color: #00BCEB;
    border-left: 4px solid #00BCEB;
    font-weight: bold;
}
```
The `[collapsed="true"]` rule right below it only adjusts padding/text
alignment, not background — so the grey box is *supposed* to render in
collapsed mode too. It most likely doesn't reliably because `QToolButton`
in `ToolButtonIconOnly` display mode is known to not always paint a
stylesheet background over its full rect — a Qt rendering quirk, not a
second intentional design. On top of that, `set_active()`
(`custom_widgets.py:79-81`) only calls `setChecked()` — it never recolors
the qtawesome icon glyph itself, so in collapsed mode (where there's no
text to turn cyan) **nothing about the icon's color changes at all**;
the thin left bar is the only signal.

**Why it matters:** collapsed mode is presumably the more common state
once someone's used the app for a while (it's the more efficient use of
screen space) — and that's exactly the state where "which section am I
in" is hardest to tell at a glance.

**Suggested fix:** recolor the icon glyph itself on the checked state
(swap the qtawesome icon's color, not just the button's QSS), so the
signal survives in icon-only mode instead of relying on a background fill
that Qt may not paint reliably in that display mode.

---

### UX-045: POS / Logout buttons still use the leftover string-padding hack

**Screen:** Main sidebar, bottom section, every screen
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#288](https://github.com/HMAHD/CB-POS/issues/288)

**Not from your notes — found while checking sidebar label spacing.**
Every regular nav button (Dashboard, Inventory, Reports, etc.) gets its
icon/text spacing from real layout + QSS padding
(`add_nav_button`, no hack). But `retranslate_pos_logout()`
(`collapsible_sidebar.py:171-172`) still does this:
```python
self.btn_pos.setText("   " + _t("management.sidebar_pos"))
self.btn_logout.setText("   " + _t("management.sidebar_logout"))
```
Three literal space characters faking icon-text spacing, on exactly the
two buttons that sit at the bottom of every sidebar screenshot you've
sent (POS/Sales in green, Logout in red) — while every other button in
the same list does it properly.

**Why it matters:** it's a small thing, but it means these two labels
won't line up pixel-identically with the rest of the list at every font/
DPI setting the way a real layout spacing would, and it's dead code
duplicating what the rest of the file already does correctly.

**Suggested fix:** drop the string-padding hack on these two buttons and
route them through the same layout-spacing mechanism `add_nav_button`
already gives every other item.

---

### UX-046: Sidebar width/expanded header in the screenshot doesn't match the widths in code (needs a live render to confirm)

**Screen:** Main sidebar, collapsed vs expanded
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#289](https://github.com/HMAHD/CB-POS/issues/289)

**What you flagged:** "when sidebar open to show text instead icon, UX is
very bad" — pointing at the expanded state specifically.

**Two things I found that don't obviously reconcile, so I'm logging both
honestly rather than asserting a root cause I haven't rendered and
confirmed:**

1. **Width discrepancy.** `collapsible_sidebar.py:20-22` defines
   `EXPANDED_WIDTH = 250`, `COLLAPSED_WIDTH = 70` (300ms animated
   transition, `QPropertyAnimation` on min/max width, lines 106-113/195-201).
   Your screenshots look noticeably wider than that in both states. This
   could just be the screenshot's own scale (2880px source, described as
   "displayed at 2000x1250, multiply by 1.44") making a visual estimate
   unreliable — but it's worth a real render to confirm the constants
   actually in this codebase are what's running, rather than guessing from
   a scaled screenshot the way UX-014 stayed honestly unconfirmed.

2. **Header layout.** `collapsible_sidebar.py:54-75` builds the logo +
   hamburger as a single `QHBoxLayout` row (logo, stretch, toggle button),
   fixed at 60px height — there's no code path that stacks the hamburger
   above the logo on its own line. Your expanded screenshot appears to
   show exactly that stacked look (hamburger on one line, "C3 CEYLON
   BYTES" logo below it). If real, that's most likely the 60px header
   being too short once the full logo pixmap + wordmark render at 250px
   width, forcing a wrap — but I haven't rendered it to confirm, so I'm
   not asserting that as the fix yet.

**Suggested fix:** before changing anything, render `CollapsibleSidebar`
offscreen at both collapsed and expanded widths (the same
`QT_QPA_PLATFORM=offscreen` + `.grab()` technique used earlier for the
Applied Payments and Dashboard calendar bugs) to see the real pixel output
next to these numbers, then adjust whichever of the two (stale constants,
or header height) turns out to be the actual cause.

---

### UX-047: Reports date picker has a near-invisible click target and no fixed display format

**Screen:** Reports, Date Range filter
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#365](https://github.com/HMAHD/CB-POS/issues/365) (sub-issue of [#262](https://github.com/HMAHD/CB-POS/issues/262))

**What you flagged:** "this date picker is weird, can't pick date
correctly, UI/UX not good and unfriendly."

**Root cause (verified in code) — three compounding problems, all on the
same widget:**

1. **The click target to open the calendar is nearly invisible.**
   `filter_widget.py:55-60` sets `setCalendarPopup(True)` but nothing else
   — and `dark.qss:2521-2524`:
   ```css
   #ReportDateEdit::drop-down {
       border: none;
       width: 20px;
   }
   ```
   `border: none` removes any visual box around the drop-down arrow, so
   the only clickable spot that opens the calendar is an unmarked 20px
   sliver on the right edge of the field — the rest of the field (padded
   6px/10px, `dark.qss:2512-2513`) just looks like plain, uninteractive
   text. There's nothing telling the user "click here" to get a calendar.

2. **No fixed display format.** `filter_widget.py` never calls
   `setDisplayFormat(...)`, so the field falls back to Qt's locale-default
   format rather than a deliberate, unambiguous one — and with no
   `setReadOnly()`/input mask either, the user can type directly over any
   of the day/month/year segments freely, making it easy to land on an
   invalid or unintended date by accident.

3. **The calendar popup itself is unstyled.** No `QCalendarWidget` rule
   exists in either theme file (confirmed by grep) — so even once a user
   finds the tiny drop-down, the popup that opens renders in plain,
   unthemed Qt/OS styling, clashing visibly against the rest of the dark
   UI. This is the same root gap already logged as UX-013/UX-039, now
   confirmed to affect Reports directly, not just Dashboard.

**Why it matters:** this is exactly the kind of small, everyday friction
that erodes trust in "clean, modern, industry-grade" software — a date
field that looks unclickable, accepts free-typed invalid input, and pops
open something that looks broken, on one of the screens business owners
would use most (running financial reports).

**Suggested fix:** as part of the shared `QDateEdit`/`QCalendarWidget` fix
already recommended in UX-039 — give the drop-down button a visible
background/border so it reads as a button, call `setDisplayFormat("yyyy-MM-dd")`
explicitly (matching the format already shown in the screenshot) so typed
input can't drift into an ambiguous format, and style the calendar popup
to match the app's dark theme.

---

### UX-048: Report table's last column always stretches, truncating the first column's labels

**Screen:** Reports, results table (e.g. Cash Flow Report)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#357](https://github.com/HMAHD/CB-POS/issues/357) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**What you flagged:** "alignments are way off" — you're right, and it has
an exact, single-line cause.

**Root cause (verified in code):** `report_viewer.py:226-227`:
```python
self.table_view.horizontalHeader().setStretchLastSection(True)
self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
```
`setStretchLastSection(True)` unconditionally forces whichever column
happens to be *last* to absorb 100% of the remaining width — in the Cash
Flow Report that's TYPE, whose actual content ("Inflow"/"Outflow"/"Net")
is a few characters long, so it ends up stretched across most of the
screen while sitting almost entirely empty. Meanwhile CATEGORY (first
column) is left on Qt's default `Interactive` width (~100px), too narrow
for "Net Cash Flow" — no `resizeColumnsToContents()` call exists anywhere
in the file — so it truncates to "Net Cas..." in the screenshot. This is
the same missing-resize-mode truncation pattern already logged 3 times
(UX-010/017/034), but this time the mechanism is the *opposite*: it's not
that no column got a resize mode, it's that the wrong column got forced
to stretch regardless of its content.

**Why it matters:** every report built from this shared table (not just
Cash Flow) inherits the same problem — whichever column is positioned
last will always look bloated, and whichever holds longer labels will
always be at risk of truncating, independent of what that report
actually contains.

**Suggested fix:** replace the blanket `setStretchLastSection(True)` with
per-column sizing driven by content: `resizeColumnsToContents()` after
data loads, then let the app pick which column (if any) should absorb
extra space based on what's actually the "detail" column for that report
— not a hardcoded assumption that it's always the last one.

---

### UX-049: Every report type shares one generic renderer with zero report-specific treatment

**Screen:** Reports, all report types
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#290](https://github.com/HMAHD/CB-POS/issues/290)

**What you flagged:** "reports look very generic and don't show details
clearly."

**Root cause (verified in code):** every report — Cash Flow, P&L, Stock
Movement Audit, all of them — is rendered through one shared
`QTableView`/`PandasModel` pair (`report_viewer.py:222-231`), with
`_on_report_finished`/`_show_current_page` (lines 401/426) just calling
`self.table_model.set_data(page_df)` on the raw dataframe. There is no
report-specific formatting anywhere in that path:
- No highlighted/bold total row — "Net Cash Flow" renders as a plain
  table row identical in style to "Refunds"/"Expenses", even though it's
  the one number that actually answers the report's question.
- No color-coding for Inflow vs. Outflow (a near-universal convention in
  financial reporting software — green for money in, red for money out).
- No currency formatting — `pandas_model.py:24-30` renders amounts as
  plain `"{:.2f}"` (e.g. `"500.00"`), with no "Rs." prefix and no
  thousands separator, even though every other money value in the app
  (POS, Credit Book, Payables) is formatted as currency.

**Why it matters:** this is precisely why the reports "don't show details
clearly" — a shop owner scanning a Cash Flow Report has to read every row
carefully to find the number that matters, instead of it visually
standing out the way a real financial report would.

**Suggested fix:** introduce a small per-report-type rendering layer on
top of the shared table — a way to mark a row as a "total" (bold/tinted
background), tag a column as a signed/directional amount (color by
positive/negative or by an explicit Inflow/Outflow tag), and format money
columns through the app's existing currency formatter instead of raw
`.2f`. This doesn't need a rewrite — just a thin config per report type
(which row is the total, which columns are currency, which column
carries a color tag) fed into the existing `PandasModel`.

---

### UX-050: Pagination controls render even when there is only one page

**Screen:** Reports, results table footer
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#291](https://github.com/HMAHD/CB-POS/issues/291)

**Not from your notes — found while checking the report table's footer
controls.** The screenshot shows "Showing 1-4 of 4" with a fully-rendered
Previous / "Page 1 of 1" / Next control row, for a report that has
exactly one page of results.

**Root cause (verified in code):** `PaginationWidget._update_controls`
(`pagination_widget.py:126-133`) only hides the whole control when
`total == 0` — with any data at all, even a single page, it calls
`self.setVisible(True)` and renders the full Previous/Page/Next row
regardless of whether paging is actually possible.

**Why it matters:** small, but it's exactly the kind of "generic, not
polished" detail you flagged — a disabled-looking-but-not-disabled
Previous/Next pair with "Page 1 of 1" is UI noise for a 4-row report;
industry-grade software hides pagination entirely when there's nothing
to paginate.

**Suggested fix:** hide the pagination row (not just disable its buttons)
whenever `total_pages <= 1`, showing it only when there's an actual
second page to go to.

---

### UX-051: One dialog has three different names for the same feature

**Screen:** Document Browser → "+ New Quotation"
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#292](https://github.com/HMAHD/CB-POS/issues/292)

**What you flagged:** "truth to be told I don't even know what the use of
it and how valuable this is to my app, so how would users know?" — that
reaction is the direct, predictable result of a real naming bug, not a
vague first impression.

**Root cause (verified in code) — confirmed, not a mismatched parameter,
the naming is simply hardcoded three different ways in one class:**
- The button you clicked: `document_view.py:82-85`, text set at line 287
  via `_t("document_browser.btn_new_quotation")` → `"+ New Quotation"`
  (`en.json:769`).
- The dialog that opens: `open_proforma_dialog()`
  (`document_view.py:855-861`) constructs `ProformaDialog(self)` — no
  document-type argument at all, because `ProformaDialog.__init__` has
  none (`proforma_dialog.py:35`).
- The dialog's window title: hardcoded `_t("proforma.title")` →
  `"Proforma Invoice"` (`proforma_dialog.py:37`, `en.json:1713`).
- The confirm button: hardcoded `_t("proforma.btn_create")` →
  `"Create Proforma"` (`proforma_dialog.py:125-126`, `en.json:1726`).
- The success message on save says "Quotation" again
  (`proforma_dialog.py:281`) — a **third** label for the same action.

So in one flow: you click something called Quotation, open a dialog
titled Proforma Invoice, click a button that says Create Proforma, and
get a success message about a Quotation. There's no `doc_type` switch
being ignored — there's just one hardcoded name at each of the 4 points,
and they were never made to agree.

**Why it matters:** this isn't cosmetic — a shop owner (you, by your own
account) genuinely can't tell what this feature *is* when the app itself
can't settle on what to call it. Quotations and Proforma Invoices are
also two different real-world business documents in Sri Lankan retail
(a quotation is a price estimate with no commitment; a proforma invoice
is a formal pre-sale document, often used for advance payment or customs/
import purposes) — if this dialog is meant to produce a Quotation,
"Proforma Invoice"/"Create Proforma" is actively the wrong term, not just
an inconsistent one; if it's meant to produce a Proforma Invoice, the
trigger button is the wrong one.

**Suggested fix:** first, a product decision — decide which one document
this dialog actually produces (or whether it should support both, in
which case it does need the `doc_type` parameter that doesn't exist yet,
with the title/button/success-message all keyed off it). Then make the
button, window title, confirm button, and success message agree
everywhere. This is worth fixing before anything else on this screen —
right now the feature can't be evaluated because it doesn't know its own
name.

---

### UX-052: Document Browser table has three competing stretch columns, truncating TYPE and TOTAL

**Screen:** Document Browser, main table
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#358](https://github.com/HMAHD/CB-POS/issues/358) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**What you flagged:** shown as part of the same screenshot — the TYPE
column reads "STOCK_C..." and several TOTAL cells read "Rs. ..." with
both truncated by ellipsis.

**Root cause (verified in code) — a different shape of bug than the
Reports table (UX-048), but the same family:** `document_view.py:149-152`
sets an explicit resize mode on only 2 of 7 columns — DOC # (1) and PARTY
(3), both `Stretch`. TYPE (2), TOTAL (4), STATUS (5), and USER (6) get
**no resize mode call at all**, defaulting to Qt's `Interactive` mode. On
top of that, `setStretchLastSection` is never disabled, so Qt's own
default (`stretchLastSection=True`) makes column 6 (USER) stretch too —
meaning there are **three** columns simultaneously competing for extra
width (1, 3, and the implicit last column 6), squeezing the untouched
`Interactive` columns (TYPE, TOTAL) into whatever's left over — which is
too little for "STOCK_COUNT" or a full "Rs. 1,621.44".

**Why it matters:** TOTAL is arguably the single most important column in
a document ledger — truncating it to "Rs. ..." on multiple rows defeats
the table's entire purpose for a user scanning for how much a document
was worth.

**Suggested fix:** give every column an explicit, deliberate resize mode
— `ResizeToContents` (or a sensible fixed minimum) for DATE, TYPE, TOTAL,
STATUS, USER, and reserve `Stretch` for exactly one column that should
actually absorb extra space (PARTY makes sense; DOC # doesn't need to
stretch). Also call `setStretchLastSection(False)` explicitly so USER
stops competing by accident.

---

### UX-053: Document Browser doesn't explain what it's for or why to use it

**Screen:** Document Browser
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#293](https://github.com/HMAHD/CB-POS/issues/293)

**What you flagged, directly:** "truth to be told I don't even know what
the use of it and how valuable this is to my app."

**This is worth logging as its own issue, separate from UX-051's naming
bug** — even with perfect naming, nothing on this screen currently
explains *why* a shop owner would come here. It's a flat table of every
document type the app produces (quotations, invoices, GRNs, stock counts,
receipts) with filter controls, but no header subtitle, no empty-state
guidance, no tooltip — nothing that answers "what am I looking at and
when would I use this" for someone encountering it for the first time.
For an app built for non-technical shop owners who "learn through
practice, not manuals," a screen whose own creator says "I don't even
know what the use of it" is a signal that real end users won't either.

**Why it matters:** a feature nobody understands the value of is a
feature nobody uses — regardless of how well it's eventually styled or
how correctly its bugs get fixed, if the "why" isn't communicated on the
screen itself, this work risks going unused.

**Suggested fix / feature idea:** add a one-line subtitle under
"Document Browser" explaining its purpose in plain language (e.g. "Search
and reprint any document your business has ever created — invoices,
quotations, purchase orders, and more, all in one place"), and consider
whether the "+ New Quotation" action even belongs on a *browsing* screen
at all, versus living wherever quotations are naturally created in the
sales flow — a browse/search screen and a create-new-document action are
two different jobs bolted together here, which may be part of why the
screen's purpose feels unclear even to you.

---

### UX-054: Proforma dialog's Customer field looks searchable but isn't

**Screen:** Document Browser → "+ New Quotation" dialog
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#294](https://github.com/HMAHD/CB-POS/issues/294)

**Not from your notes — found while reviewing the dialog's fields.** The
Customer field shows a text cursor and looks like you can type to search
— but there's no actual filtering behind it.

**Root cause (verified in code):** `proforma_dialog.py:56-59` —
`self.customer_combo = QComboBox()` with only `setEditable(True)` set. No
`QCompleter` is attached, no `setInsertPolicy`, no placeholder text. This
is the same gap already logged for Purchasing's supplier combos
(UX-028) — contrast with the correct, already-working pattern in
`payment_dialog.py:330-341`: `setInsertPolicy(NoInsert)`, a real
`QCompleter(names, self)` with `MatchContains`, and a placeholder.

**Why it matters:** a shop with more than a handful of customers gives
the user a text box that accepts typing but never narrows the dropdown —
which is worse than a plain non-editable combo, because it invites typing
that then does nothing.

**Suggested fix:** apply the exact same fix already recommended for
UX-028 — wire this field to the same searchable-combo pattern already
proven correct in `payment_dialog.py`.

---

### UX-055: Proforma dialog's Validity field uses the same known-broken spinbox stepper pattern

**Screen:** Document Browser → "+ New Quotation" dialog
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#368](https://github.com/HMAHD/CB-POS/issues/368) (sub-issue of [#263](https://github.com/HMAHD/CB-POS/issues/263))

**Not from your notes — found while reviewing the dialog's fields.** The
Validity field ("30 days") shows the same odd stacked +/- stepper buttons
already flagged elsewhere.

**Root cause (verified in code):** `proforma_dialog.py:61-64` —
`self.validity_spin = QSpinBox()`, no `setObjectName()`, no explicit
width, so it falls back to the generic `QSpinBox`/`QDoubleSpinBox` QSS
rule (`dark.qss:120-187`). This is the exact widget class
`product_editor.py:142-143`'s own code comment already identifies as
broken under QSS ("`QDoubleSpinBox` +/- buttons break under QSS") — this
is now the fourth confirmed place (after Product Editor's stock fields,
Customer Editor's Commercial tab (UX-038), and here) where a native
stepper spinbox was used instead of the `QLineEdit` + validator pattern
the codebase already knows is the correct workaround.

**Why it matters:** at four confirmed instances, this isn't a per-dialog
oversight anymore — it's a widget choice that needs to stop being made by
default across the whole app.

**Suggested fix:** same as UX-038 — replace with `QLineEdit` + an integer
validator, matching the pattern already proven in `product_editor.py`.

---

### UX-056: Proforma dialog's line-items table has no empty-state message

**Screen:** Document Browser → "+ New Quotation" dialog
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#259](https://github.com/HMAHD/CB-POS/issues/259) (sub-issue of [#254](https://github.com/HMAHD/CB-POS/issues/254))

**Not from your notes — found while reviewing the dialog.** Before any
product is added, the PRODUCT/QTY/UNIT PRICE/DISC TYPE/DISC VALUE/TOTAL
table is just a blank dark rectangle under the headers.

**Root cause (verified in code):** `refresh_table()`
(`proforma_dialog.py:192-223`) calls `setRowCount(0)` when `self.items` is
empty, with no placeholder row or message — the same gap already logged
for GRN History/Payables (UX-030), now confirmed a third place.

**Why it matters:** a blank table with no guidance leaves a first-time
user unsure whether the table is broken, still loading, or genuinely
empty — small, but part of the same "doesn't explain itself" theme as
UX-053 on this same screen.

**Suggested fix:** once UX-043's shared `EmptyStateWidget` exists, use it
here too (e.g. "No products added yet — search above to add one").

---

### UX-057: Users table shows the same ID number twice

**Screen:** Users, main table
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#295](https://github.com/HMAHD/CB-POS/issues/295)

**What you flagged:** "a few alignment [issues]" on this screen —
this is the concrete one.

**Root cause (verified in code):** `user_view.py:164-171` builds the
table with Qt's default vertical header left visible (no
`verticalHeader().setVisible(False)` call anywhere in the file), which
already shows a row-number gutter (the cyan "1, 2, 3, 4" on the far
left). A separate "ID" data column is then populated at
`user_view.py:212` with the raw `user.id` primary key. Since users are
created sequentially, the PK almost always equals the row number — so the
table shows the same number twice, once as Qt's built-in row label and
once as an actual column with a header taking up real width.

**Why it matters:** small, but it's a wasted column on a 4-column table
where every bit of width matters, and it reads as an oversight rather
than a deliberate "here's the record ID" column (which would make sense
if it *didn't* match the row number).

**Suggested fix:** drop the redundant vertical header (`setVisible(False)`)
and keep the ID column if the raw database ID is genuinely useful
information to show, or drop the ID column and keep the row-number gutter
if it isn't — not both.

---

### UX-058: No UI exists to create/rename/delete a role, even though the backend already fully supports it

**Screen:** Users
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#296](https://github.com/HMAHD/CB-POS/issues/296)

**What you flagged:** "there is no option to CRUD user roles, and every
user created has a role, so [the ability to manage] roles needs to be
added — able to add a role, and those roles should be editable, deletable."

**Confirmed, and worth knowing this is a pure UI gap, not a data-model
limitation:** `cbpos/core/models/__init__.py:38-57` — `Role` is already a
real, normal database table (`roles`: `id`, unique `name`, `access_level`,
plus a many-to-many `permissions` relationship). `User.role_id`
(line 66) is a proper foreign key, and the "Add User" dialog's role
picker already queries this table live (`user_view.py:50-53` —
`UserService.get_all_roles()`, no hardcoded "Admin"/"Manager"/"Cashier"
strings anywhere). A full grep across every dialog/view for role-related
CRUD logic (add/edit/delete a role) turned up nothing — `PermissionDialog`
only *toggles permissions for existing roles*, it never creates one.

**Why it matters:** the app already fully supports custom roles at the
data layer (e.g. a shop could want a "Supervisor" role between Manager
and Cashier) — the only thing standing in the way is that nothing in the
UI lets an admin actually create one, so the feature is invisible even
though it's almost entirely already built.

**Suggested fix:** add a small Role management panel next to the existing
Users table — a list of roles with Add/Rename/Delete, each wired to
`UserService`'s existing role plumbing (which already has to exist in
some form, since `get_all_roles()` is already called elsewhere) — this
should be a comparatively small addition given the data layer is already
done. Deleting a role in use by existing users needs a guard (reassign or
block deletion), which is worth deciding as part of this fix.

---

### UX-059: "Manage Permissions" Save Changes calls a method that doesn't exist — every save will crash

**Screen:** Users → "Manage Permissions" dialog
**Severity:** P0 · **Status:** 🟢 Fixed — regression tests added, watched fail against the original code before fixing
**GitHub:** [#297](https://github.com/HMAHD/CB-POS/issues/297)

**Not from your notes — found while investigating whether the Permission
Manager "lacks a lot more permissions" as you suspected. It doesn't (see
UX-060) — but I found something more serious while checking: the save
button is completely broken.**

**Root cause (verified in code):** `permission_dialog.py`'s
`save_changes()` (line 112) calls:
```python
PermissionService.update_role_permission(role.id, perm_id, is_checked)
```
— singular `update_role_permission`. `permission_service.py` only defines
`update_role_permissions` (**plural**, line 48), which takes a completely
different signature (`role_id, permission_ids: list[int]`). The singular
method the dialog calls does not exist anywhere in the codebase (confirmed
by grep — zero definitions). This means **every single click of "Save
Changes" raises an `AttributeError`** — no permission change made in this
dialog has ever been able to save successfully in this build.

**Why it matters:** this is the most severe finding across the entire
catalog so far — Permission Manager is the app's access-control screen,
and its one action (saving changed permissions) cannot work at all,
silently or with a crash, every single time. Any admin who opens this
dialog to actually change what a Cashier or Manager can do is currently
unable to, full stop — this is a genuinely broken feature, not an
unpolished one (same class as UX-026's broken product search).

**Suggested fix:** fix the call to use the existing plural
`update_role_permissions(role_id, permission_ids)` method (collecting all
checked permission IDs for that role first), or add the missing singular
method to `PermissionService` if per-permission granularity is actually
wanted — either way, this needs a real test click-through before it's
considered fixed, not just a code read, since it's the kind of bug that's
invisible until you actually press the button.

---

### UX-060: Permission Manager isn't missing permissions — it's hiding most of them below the fold

**Screen:** Users → "Manage Permissions" dialog
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#298](https://github.com/HMAHD/CB-POS/issues/298)

**What you flagged:** "I think that can be optimized more to get the best
UI/UX, and lacks a lot more permissions there."

**Worth correcting the framing before fixing anything — the permissions
aren't actually missing, they're just poorly surfaced:**
`cbpos/core/constants/permissions.py:66-118` defines **10 groups, 36
permission codes** in total — Sales, Inventory, Reports, Documents,
Credit, Data Safety, Purchase, Stock Take, Cash, and Admin. The dialog
(`permission_dialog.py:48-62`) genuinely renders all of them — it queries
the DB-backed `Permission` table dynamically via
`PermissionService.get_all_permissions()`, with no hardcoded category
list of its own. Your screenshot only shows 5 of the 10 groups (Sales,
Inventory, Reports, Documents, Credit) because the dialog cuts off there
— Data Safety, Purchase, Stock Take, Cash, and Admin are all below the
fold, reachable only by scrolling a thin, easy-to-miss scrollbar with no
visual hint that there's more content beneath it. That's exactly why it
*reads* as "lacks a lot more permissions" even though the data is all
there.

**Three real, compounding UX gaps on top of the visibility problem:**
1. **No bulk actions.** Built as a `QTreeWidget` (`permission_dialog.py:29-31`)
   with one checkbox per permission per role — 36 × 3 = 108 individual
   checkboxes, with no "select all in this category" or "select all for
   this role" convenience anywhere.
2. **Unstyled checkboxes.** These aren't real `QCheckBox` widgets — they're
   `QTreeWidgetItem.setCheckState()` calls (lines 83, 91), rendered by
   Qt's native tree-item delegate. The app already has a fully themed
   `QCheckBox::indicator` style elsewhere (`dark.qss:194-227`, rounded,
   cyan-filled), but tree-item check states don't pick up that rule at
   all — so these render as plain grey native OS squares, visually
   inconsistent with every other checkbox in the app.
3. **No search/filter**, and no dirty-state tracking on "Save Changes" —
   confirmed no `QLineEdit` filter exists, and the button is always
   clickable regardless of whether anything actually changed.

**A smaller architectural note worth flagging (not a currently-visible
bug):** the dialog only renders whatever `Permission` rows exist in the
database, which are populated by seeding from `permissions.py`'s
constants (`scripts/seed.py:77`, `database_setup_service.py:93`). If a
future code change adds a new permission constant without a matching
migration/reseed, it will silently never appear as a checkbox anywhere —
worth a startup consistency check at some point.

**Why it matters:** once UX-059's crash is fixed and this dialog actually
works, its core usability problem is that it looks incomplete and is
tedious to operate for exactly the reason you sensed — not because
permissions are missing, but because the dialog doesn't help you see or
manage all 36 of them efficiently.

**Suggested fix:** make the dialog resizable/taller by default so more
groups are visible without scrolling, add a "select all" checkbox per
role column and per category row, add a simple text filter across
permission names, and either switch to real `QCheckBox` widgets embedded
per cell or apply an explicit tree-item-checkbox QSS rule so they match
the rest of the app.

---

### UX-061: Activity Log DETAILS column is forced to the same width as every other column

**Screen:** Users → Activity Log tab
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#359](https://github.com/HMAHD/CB-POS/issues/359) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**What you flagged:** "logs not clear" — the free-text reason column is
exactly the part that needs the most room, and it's the part that's
cut off ("Reason: Damaged goods — spoiled d...").

**Root cause (verified in code):** `user_view.py:178`:
```python
self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
```
Called with no column index — this is the single-argument overload,
which sets the *default* resize mode for **all 5 columns at once** (TIME,
USER, EVENT, TERMINAL, DETAILS), forcing them all to equal width
regardless of content. DETAILS needs far more room than a fixed
timestamp or a short event name — this is the same missing-per-column-
resize-mode pattern already logged repeatedly (Reports, Document Browser),
just via a different mechanism (blanket default instead of an unset
`Interactive` fallback).

**Why it matters:** DETAILS is the one column that actually explains what
happened — squeezing it to 1/5 of the table width defeats the log's whole
purpose.

**Suggested fix:** set explicit per-column modes — `ResizeToContents` for
TIME/USER/EVENT/TERMINAL, `Stretch` only for DETAILS (using the per-column
overload: `setSectionResizeMode(column_index, mode)`).

---

### UX-062: The app's one central audit-logging method is dead code and would crash if called — and a live caller has the same bug

**Screen:** App-wide (audit logging infrastructure)
**Severity:** P0 · **Status:** 🟢 Fixed — reproduced the real IntegrityError with a test before fixing
**GitHub:** [#299](https://github.com/HMAHD/CB-POS/issues/299)

**Not from your notes — found while checking your suspicion that
"functionally wise it doesn't work across the full application." You
were right, and it's more serious than missing coverage — there's an
active crash risk in a real workflow.**

**Root cause (verified in code):** `cbpos/core/services/logging_service.py:16-31`
defines `LoggingService.log_action()` — clearly intended as *the* central
audit-logging API. It has **zero callers anywhere in the repository**
(confirmed by grep) — every real call site instead hand-rolls its own
`AuditLog(...)` construction independently, duplicated across ~7 places.
Worse, `log_action()` itself never sets `event_type`, which is
`nullable=False` on the `AuditLog` model
(`cbpos/core/models/__init__.py:435-448`) — calling it as written would
raise an `IntegrityError` on commit. It's not just unused, it's broken.

**The same exact bug already exists in a live, reachable code path:**
`InventoryService.adjust_stock` (`inventory_service.py:114-121`) builds
its own `AuditLog(action="STOCK_ADJUSTMENT", ...)` and **also** omits
`event_type`. Its surrounding `try/except` (lines 124-128) only catches
`StaleDataError` — an `IntegrityError` from the missing `event_type` is
not caught, so it propagates and rolls back the entire session per
`Database.get_session()`'s exception handling
(`cbpos/core/database.py:173`). In practice, this means **a stock
adjustment is likely to fail outright** when this code path runs, not
just fail to log quietly.

**Why it matters:** this isn't "the audit trail has gaps" (that's
UX-063) — this is a live bug that can break a core Inventory action
(stock adjustment) the moment it's exercised, because the code that's
supposed to record the adjustment can throw and roll back the very
change it was meant to log.

**Suggested fix:** fix `adjust_stock`'s `AuditLog(...)` call to include
`event_type` (should be quick — pattern is already correct in the other
~7 call sites), and either wire every hand-rolled `AuditLog(...)`
construction through the existing `LoggingService.log_action()` (fixing
its missing `event_type` first) or delete it if it's not going to be the
real shared path — dead code that would crash if anyone ever called it is
worse than no shared helper at all, since it looks safe to reach for.
This needs a real click-through test (trigger a stock adjustment, confirm
it commits), not just a code read, given the exact same class of bug
already went unnoticed in UX-059.

---

### UX-063: Void, Refund, Permission changes, Purchasing, and Credit adjustments have zero audit trail

**Screen:** App-wide (audit logging coverage)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#300](https://github.com/HMAHD/CB-POS/issues/300)

**What you flagged:** "I don't think functionally wise it works across
the full application" — confirmed, and CLAUDE.md's own documented claim
("All critical changes logged to `AuditLog` table via services") doesn't
hold up against what's actually implemented.

**Root cause (verified in code) — a full trace of every `event_type`
ever written anywhere in the codebase:** only `LOGIN`, `LOGOUT`, `TIMEOUT`,
`TRANSACTION` (only for `TRANSFER_ORDER`), and `SECURITY` (tax rate
changes, profile updates, user create/update) are ever recorded. Grepping
the services that should be the most security-sensitive in the entire
app turns up **zero** `AuditLog` writes:
- `transaction_service.py`'s `void_sale` and `process_refund`
  (lines 298-451) — void only calls `logger.info(...)`, a plain file-log
  line, never a database `AuditLog` row.
- `PermissionService`/`permission_dialog.py` — no `AuditLog` reference
  anywhere (consistent with UX-059's finding that saving permissions is
  currently broken outright, so there's doubly nothing to trace here yet).
- `purchase_service.py` — no audit entry when a GRN/purchase is committed.
- `customer_credit_service.py` — no audit entry for credit adjustments or
  payments received (including `record_adjustment`).

**Why it matters:** these are precisely the actions a shop owner would
most want a trail for — someone voiding a sale, refunding a customer,
changing what a Cashier is allowed to do, or adjusting a customer's
credit balance. Right now, routine logins are tracked in detail while the
actually consequential actions leave no record at all — the opposite of
what an audit log is for.

**Suggested fix:** once UX-062's central logging path is fixed, wire
`void_sale`, `process_refund`, permission changes (after UX-059 is
fixed), purchase/GRN commits, and credit adjustments through it — each
with enough `details` to reconstruct what happened (who, what, why, for
how much).

---

### UX-064: Activity Log has no color or icon coding by event type

**Screen:** Users → Activity Log tab
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#301](https://github.com/HMAHD/CB-POS/issues/301)

**What you flagged:** "can we add some colored tag to identify logs
properly."

**Root cause (verified in code):** `load_logs()` (`user_view.py:226-239`)
builds every row as a plain `QTableWidgetItem(...)` with no
`setForeground()`/icon/badge logic at all — LOGIN, LOGOUT, TRANSACTION,
and SECURITY events all render identically in plain white text. Worth
noting this isn't a new pattern for the codebase to learn — the sibling
Users tab in the very same file already does exactly this kind of thing
(`load_users()`, lines 222-224, sets red foreground text for inactive
user status) — it just wasn't applied here.

**Why it matters:** a shop owner scanning for something unusual (a void,
a permission change, a failed login) has to read every row's EVENT text
individually today — color/icon coding is exactly what makes an activity
log scannable at a glance, which is the whole point of the feature.

**Suggested fix:** tag each event type with a color (e.g. LOGIN/LOGOUT
neutral, SECURITY amber, and — once UX-063 adds them — VOID/REFUND red,
PERMISSION_CHANGE amber/bold) using the same `setForeground()` approach
already proven in `load_users()`, or a small colored dot/icon prefix on
the EVENT cell.

---

### UX-065: Activity Log is hardcoded to the 10 most recent rows, with no filter UI

**Screen:** Users → Activity Log tab
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#302](https://github.com/HMAHD/CB-POS/issues/302)

**Not from your notes — found while checking this tab's data loading.**
`UserService.get_recent_activity(user_id=None, limit=10)`
(`user_service.py:74-94`) already supports filtering by a specific user —
but `load_logs()` calls it with **zero arguments**
(`user_view.py:227`), so it always shows exactly the 10 most recent
audit rows system-wide, with no date range, no event-type filter, and no
way to page further back — despite the filtering capability already
existing one layer down.

**Why it matters:** an activity log that can only ever show its 10 most
recent entries stops being useful the moment there's been any real
activity since — you can't look up "what did the cashier do yesterday"
or "when was this customer's credit last adjusted" at all.

**Suggested fix:** surface a user filter (the service already supports
it — this part is nearly free), a date range, and basic pagination or a
"load more" control, matching the filter conventions already used
elsewhere in the app (Document Browser's Type/Status/From/To row is a
close template).

---

### UX-066: "Valid: N/A to N/A" is real, and once set, a price list's dates can never be changed

**Screen:** Price Lists
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#303](https://github.com/HMAHD/CB-POS/issues/303)

**What you flagged:** "top right corner shows Valid N/A N/A, that should
be [a] date, it doesn't show."

**Root cause (verified in code) — the display logic is actually
correct, the data really is empty:** `pricelist_view.py:277-279` builds
the label with a proper None-guard (`if price_list.start_date else
"N/A"`), and `PriceList.start_date`/`end_date`
(`cbpos/core/models/__init__.py:84-85`) are nullable. The three demo
lists really do have no dates — `scripts/seed.py:147-150` creates
`PriceList(name="Standard", is_active=True)` etc. with no date arguments
at all. So "N/A to N/A" is an honest reflection of the data, not a
formatting bug.

**The deeper problem — this can never be fixed after the fact:**
`PriceListService` has no update/edit method at all (only
`create_price_list`, `get_all_lists`, `get_active_lists`,
`set_item_price`, `delete_price_list`, `get_items`). Dates can only ever
be entered once, at creation time, through `PriceListDialog`
(confirmed working — see UX-069). Once a price list exists — with wrong
dates, or none — there is no way to correct them short of deleting the
whole list and recreating it (losing every product price override set on
it in the process).

**Why it matters:** a "Happy Hour" or seasonal price list is exactly the
kind of thing whose validity dates *will* need adjusting — extend a
promotion, fix a typo'd end date — and right now that requires destroying
and rebuilding the entire list.

**Suggested fix:** add an edit capability for a price list's name and
date range (a small "Edit List" action next to Add/Delete), backed by a
new `PriceListService.update_price_list(...)` method.

---

### UX-067: Price editing is double-click-only, and reuses the same known-broken spinbox stepper

**Screen:** Price Lists
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#369](https://github.com/HMAHD/CB-POS/issues/369) (sub-issue of [#263](https://github.com/HMAHD/CB-POS/issues/263))

**What you flagged:** "the only way to do changes to product price is
double click."

**Root cause (verified in code) — two compounding, already-familiar
patterns, confirmed here a fifth time each:**
1. `pricelist_view.py:166` disables native cell editing entirely
   (`setEditTriggers(NoEditTriggers)`), and `pricelist_view.py:169` wires
   **only** `doubleClicked` to `edit_item_price` — no button, no Enter
   key, no context menu. Same gap as UX-009/032/035.
2. `edit_item_price` (`pricelist_view.py:367-393`) opens the price input
   via `QInputDialog.getDouble(...)` (lines 379-386) — Qt implements this
   dialog's numeric field as an internal `QDoubleSpinBox`, which renders
   the same unstyled +/- steppers already logged 4 times (UX-018/025/038/055),
   and — because it's `QInputDialog`'s own internal widget — it can't even
   be reached by objectName for a future QSS fix without replacing the
   whole dialog.

**Why it matters:** setting prices is the single most common action on
this screen, and it's both undiscoverable (no visible affordance) and
built on the one native-Qt shortcut (`QInputDialog`) that can't be styled
to match the rest of the app even if someone tried.

**Suggested fix:** add a visible "Edit Price" button/Enter-key binding
matching UX-009's fix, and replace `QInputDialog.getDouble` with the
app's own styled dialog pattern (a small custom `QDialog` with a
`QLineEdit` + validator, matching `QuantityDialog`'s already-correct
approach) instead of a native Qt convenience dialog.

---

### UX-068: A price list can't be renamed, and a product override can't be removed once set

**Screen:** Price Lists
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#304](https://github.com/HMAHD/CB-POS/issues/304)

**What you flagged:** "lack of CRUD operations."

**Root cause (verified in code) — confirmed, two real gaps beyond
UX-066's date problem:**
- The sidebar only wires `+ Add` → `add_price_list` and `Delete` →
  `delete_price_list` (`pricelist_view.py:90,95`) — there is no
  rename/edit-name handler anywhere in the file, and (per UX-066)
  `PriceListService` has no update method to support one even if the
  button existed.
- `set_item_price` (`price_list_service.py:48-66`) only ever
  upserts — there is no `delete_item_price`/remove-override method
  anywhere in the service, and `edit_item_price` never offers a "clear"
  option. Once a LIST PRICE is set for a product, it can only ever be
  changed to a different number — it can never be reverted back to "-"
  (i.e., back to using the base price with no override).

**Why it matters:** this is a real, everyday limitation for managing
price lists — renaming "Happy Hour" to "Weekend Special," or undoing a
mistaken product-specific override, are both things a shop owner will
want to do and currently can't, without deleting and rebuilding.

**Suggested fix:** add `update_price_list(name=...)` for renaming
(pairs with UX-066's date-edit fix — likely the same dialog/service
change), and add a "Remove Override" option in `edit_item_price` (or a
right-click action) that deletes the `PriceListItem` row entirely,
falling back to the product's base price.

---

### UX-069: New Price List dialog's date fields work but are unstyled (app-wide gap)

**Screen:** Price Lists → "+ Add"
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#366](https://github.com/HMAHD/CB-POS/issues/366) (sub-issue of [#262](https://github.com/HMAHD/CB-POS/issues/262))

**What you flagged:** "new price list creation tab has date selection,
same date picker problem there also."

**Root cause (verified in code) — good news, the fields work; this is
purely the already-tracked styling gap, not a second broken widget:**
`PriceListDialog.init_ui` (`pricelist_view.py:402-432`) builds
`start_date`/`end_date` as `QDateEdit` with `setCalendarPopup(True)`
called on both (lines 413, 417) — the calendar does open and function.
Neither field gets a `setObjectName()`, though, so they fall into the
same unstyled bucket as 10+ other date fields across the app — now
folded into [UX-039](#ux-039-only-2-of-15-date-pickers-in-the-app-have-any-styling-at-all)'s
confirmed scope (see its correction note).

**Why it matters:** covered by UX-039's broader fix — noted here mainly
so this specific screen doesn't get rediscovered as a separate mystery
later.

**Suggested fix:** same as UX-039 — a shared `QDateEdit`/`QCalendarWidget`
QSS rule fixes this location along with the rest.

---

### UX-070: STATUS column shows the same static, list-level value on every product row

**Screen:** Price Lists, product table
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#305](https://github.com/HMAHD/CB-POS/issues/305)

**Not from your notes — found while checking what STATUS actually
represents.** Every one of the 80 product rows shows "Active" —
identically.

**Root cause (verified in code):** `_get_price_list_status`
(`pricelist_view.py:223-238`) computes exactly **one** status for the
whole price list (based on its start/end dates vs. now), and
`load_items` (lines 300, 324-326) applies that same single value to
every row in the loop. It's not a per-product or per-override flag —
`PriceListItem` has no `is_active` field at all, so there's no real
per-row state for this column to represent yet.

**Why it matters:** a column that repeats the exact same value 80 times
reads as either broken or pointless — right now it's neither, it's just
showing list-level information at the row level, which is misleading
framing more than a bug.

**Suggested fix:** either move this into the header (next to the
existing "Active" badge, since that's genuinely where it belongs — it's
already shown there) and drop the per-row column entirely, or give
`PriceListItem` a real per-product active/inactive flag if that's
actually a feature worth having (e.g. temporarily disable one product's
override without deleting it) — in which case the column becomes
meaningful data instead of a repeated constant.

---

### UX-071: Price List sidebar is cramped, plain text with no visual hierarchy

**Screen:** Price Lists, left sidebar
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#306](https://github.com/HMAHD/CB-POS/issues/306)

**What you flagged:** "price list [shown] in sidebar is too close
[together], items — make [it] creative, it [keep space and] looks
clean."

**Root cause (verified in code):** `dark.qss:3148-3157`
(`QPushButton#PriceListNavItem`) sets `padding: 10px 12px;` with no icon
support, and `pricelist_view.py:78` sets only 2px between buttons
(`setSpacing(2)`). The label itself is a single plain string
(`pricelist_view.py:260`: `f"{pl.name}  [{status_text}]"`) — no icon
widget, no count badge, no section header, no separators. Contrast with
the Reports category sidebar reviewed earlier, which at least has
section headers and count badges — Price Lists has neither, just three
tightly-packed text buttons.

**Why it matters:** with only 3 items today this is mild, but it already
reads as an afterthought compared to Reports' sidebar, and it won't
scale gracefully if a shop ends up with 8-10 price lists (seasonal,
wholesale tiers, staff discount, etc.).

**Suggested fix:** give nav items more breathing room (16-20px vertical
padding, more spacing between buttons), move the "[Active]"/inactive
status into a small colored badge instead of bracketed text (matching
the pattern the "Standard" header status pill already uses, just visible
in the sidebar too), and consider a small icon per list for quicker visual
scanning once there are more than a handful.

---

### UX-072: Promotions aren't wired into checkout at all — the feature currently affects zero real sales

**Screen:** Promotions & Campaigns
**Severity:** P0 · **Status:** 🟢 Verified working — original finding was wrong, see correction below
**GitHub:** [#307](https://github.com/HMAHD/CB-POS/issues/307) (closed)

**Not from your notes directly, but it's the finding that reframes
everything else you flagged here.** You said "promotions and campaigns
lacks everything" — that's more literally true than it might have
seemed: this isn't a promotions feature with rough edges, it's a
promotions **table** with a create-only screen in front of it, entirely
disconnected from the sale flow.

**Root cause (verified in code):** `PromotionService`,
`get_active_promotions()`, and the `Promotion` model are referenced
**nowhere** in `transaction_service.py` or anywhere else in the checkout/
sale/discount code path (confirmed by grep across the whole `cbpos/`
tree — zero matches tying promotions to a real transaction). There's no
relationship from `Promotion` to `Sale`/`SaleItem`/`Document` in the model
either (`cbpos/core/models/__init__.py:104-115`). A cashier ringing up
"Sunlight Products" today gets no Rs.50 discount, a "Weekend 5% Off"
promotion never reduces a snack's price — none of the 3 promotions in
your screenshot can currently do anything to a real sale, regardless of
whether they're within their date window or not.

**Why it matters:** this is the single biggest gap on this screen — every
other issue here (CRUD, status display, dialog polish) is about managing
data that, right now, has no effect on the business it's meant to
influence. Fixing the smaller issues first would polish a feature that
still doesn't work.

**Suggested fix:** this needs a real design/implementation pass, not a
quick patch — wire promotion lookup into the sale/cart calculation
(checking `get_active_promotions()`'s date-and-flag filter, once UX-074's
stored-flag bug is also fixed) so an eligible promotion actually applies
its discount at checkout, matching the tax/discount calculation
conventions already used for manual discounts in `sales_view.py`.

**Correction (2026-09-09) — this finding was wrong, and it's worth
recording exactly how, since it's a good lesson for this whole catalog:**
the original investigation grepped for "promo"/"discount" tied to the
`Promotion` model across `transaction_service.py` and broadly under
`cbpos/` — and missed `pricing_service.py` entirely. It exists,
`PricingService.calculate_price()` already implements complete promotion
matching (active window, day-of-week, PERCENTAGE/FIXED_AMOUNT, picks the
best discount for the customer), and `CartService.add_item()` — the real
path every product-add in `sales_view.py` goes through — already calls
it for every item. **This has been true in the code all along.** The
actual gap was that this path had zero test coverage anywhere
(`test_cart_service.py` mocks `PricingService` out entirely, "no
promotions"), so nothing had ever verified it end to end — including this
catalog's own investigation, which read code rather than running it.

7 regression tests were added
(`tests/unit/test_pricing_service_promotions.py`) against the real,
unmocked service and a real database, confirming percentage and
fixed-amount promotions both discount correctly, inactive/wrong-day
promotions correctly don't apply, the best of multiple active promotions
is chosen, price never goes negative, and the discounted price flows all
the way into a real cart line. **No production code changed** — the
"fix" was proving the feature already works, not building it.

Two things worth still tracking, both filed separately rather than
folded into this correction:
- `PromotionService.get_active_promotions()` is genuinely dead code (zero
  callers) — `PricingService` has its own separate, undocumented inline
  duplicate of that same query. Worth consolidating whenever UX-074 (the
  STATUS-display bug) is fixed.
- Writing these tests surfaced a real, general test-isolation bug (rows
  created in one test can leak into unrelated tests in other files,
  regardless of what they're about) — filed as its own issue
  ([#385](https://github.com/HMAHD/CB-POS/issues/385)), out of scope
  here.

---

### UX-073: Promotions have zero CRUD beyond Create — no edit, delete, or deactivate exists anywhere

**Screen:** Promotions & Campaigns
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#308](https://github.com/HMAHD/CB-POS/issues/308)

**What you flagged:** "no CRUD operations whatsoever."

**Confirmed, at every layer:** `promotion_view.py` has exactly one write
path — `add_promotion()` (lines 91-99), wired only to the "Create
Promotion" button. There is no `edit_promotion`/`delete_promotion`/
`update_promotion`/`deactivate_promotion` method anywhere in the file.
The table itself (`promotion_view.py:54-58`) has
`setEditTriggers(NoEditTriggers)` and no double-click or right-click
wiring at all — no way to even open an existing promotion, let alone
change it. `PromotionService` mirrors this exactly: only
`create_promotion`, `get_active_promotions`, `get_all_promotions` exist —
there is no update/delete method at the service layer either. Your
description is accurate to the letter: this screen can only ever add
rows, never touch existing ones.

**Why it matters:** a promotion with a typo'd name, a wrong value, or a
date range that needs adjusting (see UX-074) can currently only be fixed
by leaving the wrong one in the table forever and creating a new,
separate one — there's no way to correct or retire anything.

**Suggested fix:** add edit and delete/deactivate actions (a button row
or right-click menu) backed by new `PromotionService.update_promotion(...)`/
`delete_promotion(...)` methods — this is foundational enough that it
should land in the same pass as UX-072's checkout wiring, since a
promotion nobody can correct or turn off is especially risky once it
actually starts affecting real prices.

---

### UX-074: STATUS is a stored flag set once at creation and never re-evaluated — every promotion shows "Active" forever

**Screen:** Promotions & Campaigns
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#309](https://github.com/HMAHD/CB-POS/issues/309)

**What you flagged:** "promotions should time out automatically when
dates hit, I don't think that also works correctly." Confirmed — it
doesn't.

**Root cause (verified in code):** `is_active`
(`cbpos/core/models/__init__.py:114`) is a plain stored boolean, set to
`True` once at creation (`promotion_service.py:30`) and **never flipped
anywhere in the codebase** — no scheduled job, no query-time check, no
code path sets it back to `False`. The STATUS column in the table reads
this raw flag directly (`promotion_view.py:88`:
`_t("common.active") if p.is_active else _t("common.inactive")`), not a
computed comparison against `start_time`/`end_time`. Every promotion you
create will show "Active" forever, regardless of whether its end date
passed a year ago.

**A correct implementation already exists, just unused:**
`get_active_promotions()` (`promotion_service.py:38-49`) properly filters
`is_active AND start_time <= now AND end_time >= now` — but it's never
called from anywhere, including the view itself (which calls
`get_all_promotions()` instead, `promotion_view.py:76`). The 60-second
scheduler timer (`main.py:294-299` → `SchedulerService.check_automation()`)
only handles report emailing — there's no promotion-expiry job either.

**Why it matters:** even setting aside UX-072 (promotions not affecting
real sales yet), this display bug alone is actively misleading — an
admin scanning this table has no way to tell, from the STATUS column,
which promotions are actually still within their date window and which
quietly expired weeks ago.

**Suggested fix:** stop trusting the stored flag for display — compute
STATUS at render time the same way `get_active_promotions()` already
does (or switch the view to call that method), so "Active" genuinely
means "within its date range today."

---

### UX-075: Promotions NAME column truncates — the same global-stretch pattern found repeatedly elsewhere

**Screen:** Promotions & Campaigns, main table
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#360](https://github.com/HMAHD/CB-POS/issues/360) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**What you flagged:** as part of "lot of UI/UX issues" — visible directly
in the screenshot ("Evening Happy Hour - 10% Off ..." cut off).

**Root cause (verified in code):** `promotion_view.py:56`:
```python
self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
```
Called on the whole header with no column index — all 6 columns (NAME/
TYPE/VALUE/START/END/STATUS) get equal stretch width regardless of
content. NAME needs by far the most room of any column here; with
nothing giving it priority, longer promotion names clip. This is the
same root pattern already logged on the Activity Log, Reports, and
Document Browser tables — same fix, different screen.

**Why it matters:** promotion names are free text a shop owner writes
themselves to describe an offer — clipping them defeats the point of
letting them be descriptive.

**Suggested fix:** per-column resize modes, giving NAME `Stretch` (or a
generous minimum width) and `ResizeToContents` for the shorter columns
(TYPE, VALUE, STATUS) — same fix already recommended for the other 3
tables with this exact bug.

---

### UX-076: Create Promotion dialog is generic, and can't actually target specific products

**Screen:** Promotions & Campaigns → "Create Promotion"
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#310](https://github.com/HMAHD/CB-POS/issues/310)

**What you flagged:** "create promotion popup also very generic, needs
attention, clean UI, proper alignment and date picker."

**The single biggest gap in this dialog, worth leading with:** there is
**no product or category picker anywhere** — `PromotionDialog.get_data()`
(`promotion_view.py:147-155`) and `create_promotion()`
(`promotion_service.py:13-36`) only ever take `name, type, value,
start_time, end_time, days_of_week`. Every promotion is necessarily
store-wide by construction. Your own screenshot shows a promotion named
"Rs.50 Off Sunlight Products" — a name that implies product-specific
targeting the feature has no way to actually enforce; today, that's just
a label a cashier has to interpret and apply manually, not a rule the
system understands or restricts.

**Smaller, compounding issues on the same dialog (verified in code):**
- **Missing promotion type**: the model already defines a `BOGO` type
  (`models/__init__.py:112`), but the dialog's type combo only offers
  PERCENTAGE/FIXED_AMOUNT (`promotion_view.py:116`) — a third of the
  data model's own promotion types can never be created through the UI.
- **Unconstrained field widths**: only the dialog itself gets a
  `setMinimumWidth(400)` (line 106) — `value_input`, `start_dt`, `end_dt`,
  and the free-text `days_input` have no explicit width, so they stretch
  to fill available space via `QFormLayout`'s default growth policy, the
  same unconstrained-field pattern already logged in the Customer Editor
  (UX-038) and elsewhere.
- **Date pickers work but are unstyled**: both `start_dt`/`end_dt`
  (`QDateTimeEdit`, lines 122-128) do call `setCalendarPopup(True)` —
  they open correctly — but neither has an `objectName`, so they fall
  into the same unstyled bucket already tracked in UX-039.
- **No `start < end` validation**: `create_promotion()` inserts whatever
  it's given with no comparison check — a promotion with an end date
  before its start date would be silently created and just never apply
  (once UX-072 is fixed) or never show as active.
- **"Days of week" is unstructured free text**: `days_input`
  (line 130-131) is a plain `QLineEdit` with only a placeholder hint, no
  actual day picker (checkboxes for Mon-Sun would be the obvious fit) and
  no format validation.

**Why it matters:** "Rs.50 off Sunlight Products" and "Weekend 5% Off All
Snacks" are exactly the kind of targeted promotions a small retailer
actually wants to run — a feature that can only create untargeted,
store-wide discounts under a descriptive-but-unenforced name doesn't
match what it's advertising itself as capable of.

**Suggested fix:** add a product/category multi-select to the dialog and
matching scope fields to the model/service (this is the core feature gap
to close before anything else here matters much), add the missing BOGO
option or remove it from the model if it's not planned, constrain field
widths, add `start < end` validation, and replace the free-text days
field with 7 day-of-week checkboxes.

---

### UX-077: Nearly every table in the app has the same header/content alignment defect

**Screen:** App-wide — every screen with a table reviewed so far
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#261](https://github.com/HMAHD/CB-POS/issues/261) — parent issue, tracks sub-issues for each confirmed location

**What you flagged:** "every table I see in the app have misalignment,
row headers doesn't match with content it appears — that's critical, it
makes the application [look un-]pure design, and needs to be addressed
when fixing."

**You're right, and it's worth stating plainly: this is not a collection
of unrelated small bugs. It is one recurring implementation mistake,
made independently on nearly every screen that has a table, because
there is no shared "build a table correctly" convention anywhere in the
codebase for anyone to reach for.** Every table gets its column sizing
hand-rolled from scratch, and it goes wrong in one of two mechanically
distinct ways:

**Mechanism 1 — a resize mode is set once, with no column index, applying
the same rule to every column regardless of content:**
| Screen | Entry | Where |
|---|---|---|
| POS main cart | UX-002 | `sales_view.py` |
| Select Customer dialog | UX-010/011/012 | `customer_selection_dialog.py:36-49,44` |
| Inventory table | UX-017 | `inventory_view.py:136` |
| Credit Book customer list | UX-034 | `credit_book_view.py:99-102` |
| Activity Log | UX-061 | `user_view.py:178` |
| Promotions table | UX-075 | `promotion_view.py:56` |
| Category Manager tree | UX-021 | no resize mode set at all (`category_manager.py:64-70`) |
| Stock Take BARCODE column | — | `stock_take_view.py`'s `item_table`/`history_table`, no min width on BARCODE/STK#/DATE columns |
| Stock Count Report dialog | — | only 1 of 6 columns gets a resize mode (`stock_take_view.py:203`), causing the "479600900..." truncation |

**Mechanism 2 — the opposite failure: `setStretchLastSection(True)` (or
an explicit `Stretch` on the wrong column) forces one column to bloat
while others starve, regardless of which one actually holds the longest
content:**
| Screen | Entry | Where |
|---|---|---|
| Reports results table | UX-048 | `report_viewer.py:226-227` |
| Document Browser table | UX-052 | `document_view.py:149-152` |

**Mechanism 3 — new, found on Stock Take: a column *does* get an
explicit per-column resize mode, but `ResizeToContents` computed at load
time against an empty/short column stays too narrow even for what the
column is about to hold** (a live-typed value, not just static text) —
see [UX-078](#ux-078-the-counted-column-collapses-to-almost-nothing-making-its-own-input-editor-nearly-invisible)
for the full writeup; this is the same family of bug but distinct enough
mechanically (correct-looking code, wrong result) to name separately.

**A fourth, related symptom — header text alignment not matching cell
alignment** (numbers left-aligned in the header but right-aligned in
cells, or vice versa) was called out specifically in UX-011.

That's **15 confirmed tables** across the catalog so far, from 3
mechanically distinct root-cause patterns — and this is very likely an
undercount, since it's been found incidentally on nearly every screen
reviewed, not from a dedicated table-by-table audit.

**Why it matters — agreeing with your framing:** a POS used all day by
non-technical staff lives or dies on whether its data is legible at a
glance. Truncated headers, clipped totals, and columns that don't match
their content are the single most visible signal that software wasn't
carefully built, even to someone who couldn't name why it looks off. This
is exactly the kind of defect that undermines trust in "clean, modern,
industry-grade" faster than almost anything else, because it shows up
constantly, on nearly every screen, not just once.

**Suggested fix — treat this as one fix, not fifteen:** before touching
individual tables, define one small shared helper (e.g.
`configure_table_columns(table, {col_index: mode_or_width, ...})` in
`cbpos/ui/widgets/` or a table-utils module) that makes the *correct*
per-column pattern the easy, obvious thing to reach for — explicit
`ResizeToContents` for short/fixed-format columns (IDs, dates, statuses,
totals), `Stretch` reserved for exactly the one column that should
actually absorb extra space (usually a name/description/details field),
`setStretchLastSection(False)` set explicitly every time so Qt's default
can't quietly reintroduce this bug on a 16th table, and — per UX-078's
Mechanism 3 finding — an explicit `setMinimumSectionSize()` or a fixed
minimum width on any column that can ever hold a live-typed value, so
`ResizeToContents` can't collapse it based on an empty initial state.
Then sweep every table listed above (and any found later) through it in
one pass — this is a small, mechanical, high-leverage fix precisely
because it's the same few-line mistake repeated over a dozen times, not
15 different problems needing 15 different solutions.

---

### UX-078: The COUNTED column collapses to almost nothing, making its own input editor nearly invisible

**Screen:** Stock Take → New Count
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#361](https://github.com/HMAHD/CB-POS/issues/361) (sub-issue of [#261](https://github.com/HMAHD/CB-POS/issues/261))

**What you flagged:** "the important thing to fix here is the way count
can be added — as you can see, the second image top product line shows a
blue circular-y place, that's what it currently has, not good, hard to
do, not visible, even hard to identify, need an industrial-grade proper
solution and fix."

**Root cause (verified in code) — a genuinely new variant of UX-077's
pattern, worth understanding precisely because the code looks
reasonable and still produces a bad result:** the New Count table
(`item_table`, a `QTableView` bound to a custom `StockCountItemModel`) is
not built with `setCellWidget()` or any custom editor — it uses Qt's
default, transient item-delegate editing. Only the COUNTED column is
marked editable (`flags()`, lines 131-135), and Qt spawns a plain
`QLineEdit` editor only for the exact cell being actively double-clicked
or typed into — that's the "blue oval" you saw, not a permanent widget.
Column 3 (COUNTED) is set to `ResizeToContents` (line 322) — which
sounds correct — but it's computed **immediately after loading**, when
every COUNTED cell is still empty (`counted_qty is None → ""`). Qt sizes
the column to fit an empty string, so it collapses to roughly the width
of the header text alone. The transient editor that later appears for
that cell is then squeezed into that same too-narrow column, rendered
with the app's generic `QLineEdit` focus styling (`dark.qss:35-44`: 8px
padding, cyan focus border) — which is exactly what reads as a tiny,
barely-visible cyan pill rather than a proper input field.

**Why it matters more than a typical truncation bug:** every other
UX-077 instance is about *displaying* data that's already there. This one
is about *entering* data — COUNTED is the single column a warehouse
worker interacts with dozens or hundreds of times during a real stock
count, and right now the box they need to type into is nearly impossible
to see or aim for. This is the core interaction of the entire feature,
not a side detail.

**Suggested fix:** give the COUNTED column a fixed, generous minimum
width (not `ResizeToContents` on an always-initially-empty column) — see
UX-077's updated Suggested Fix for the general version of this rule.
Beyond sizing, for a "type a number many times in a row" workflow, worth
considering a dedicated numeric-entry pattern instead of Qt's bare
transient editor — e.g. a persistent, larger inline input per visible
row (not one that disappears the instant you click away), or a
"select row → type in a fixed count-entry box at the bottom → Enter
advances to the next row" flow, which would also be faster for someone
counting 79+ items in a row than double-clicking each cell individually.

---

### UX-079: Stock Take button colors contradict the app's own documented palette, and each other

**Screen:** Stock Take → New Count
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#311](https://github.com/HMAHD/CB-POS/issues/311)

**What you flagged:** "other UI/UX issues can be identified, I see some
unmatching elements to our system on other pages."

**Root cause (verified in code) — a genuine mess, not just a "could be
better":**
| Button | Class/style | Color |
|---|---|---|
| Load Products | `class="primary"` | green `#2ECC40` |
| Save Draft | `class="accent"` | cyan `#00BCEB` dark / `#0099CC` light |
| Finalize Count | `class="primary"` | green `#2ECC40` — **same as Load Products** |
| Approve & Apply | hardcoded inline `setStyleSheet(...)` | neon green `#39FF14` — **a third, different green, and bypasses the class system entirely** |
| Void | `class="danger"` | red `#FF4136` — consistent |
| New Count | no class/objectName at all | plain native grey |
| Refresh (History tab) | `class="primary"` | green — same as Load Products/Finalize |

Two distinct problems: first, three semantically different actions
(fetching products, completing a count, refreshing a list) all render
identically green because they all reach for the same `primary` class —
color stops meaning anything when everything is the same color. Second,
`class="primary"` itself resolving to green rather than the app's
documented cyan accent (`#00BCEB`) is a mismatch between CLAUDE.md's own
color palette section and what's actually implemented — and
Approve & Apply then adds a *fourth* shade of green on top by hardcoding
its own style rather than using any class at all. Also worth a small
separate note: Save Draft's light-theme color (`#0099CC`) doesn't match
either the dark theme's `#00BCEB` or CLAUDE.md's documented light accent
(`#0D6EFD`) — a small but real cross-theme inconsistency.

**Why it matters:** color is supposed to be a fast visual cue for what
kind of action a button performs — right now, on this one screen, green
means "load data," "finish and commit," and "approve and apply to
inventory" all at once, which is exactly the kind of inconsistency that
undermines the "clean, industry-grade" bar across every screen, not just
this one.

**Suggested fix:** reserve one distinct color per action *category*, not
per button — e.g. neutral/secondary for data-fetch actions (Load
Products, Refresh), a single clear "commit/complete" color for
Finalize/Approve (ideally the *same* one, since both are "make this
count official" actions), and route Approve & Apply through the class
system instead of an inline `setStyleSheet` override so it can't drift
from the rest again.

---

### UX-080: DRAFT stock counts in History are orphaned — no way to resume, edit, or delete them

**Screen:** Stock Take → History
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#312](https://github.com/HMAHD/CB-POS/issues/312)

**Not from your notes — found while checking the History tab's row
actions.** The screenshot shows 3 stock counts, all in DRAFT status.

**Root cause (verified in code):** `on_history_double_click`
(lines 716-721) only ever opens the read-only `StockCountReportDialog` —
there is no edit, resume, void, or delete action reachable from a History
row at all. `Void` (line 358) only acts on `self.current_stock_count`,
the in-memory count from the active session — once that session ends
(app restart, navigating away), a DRAFT count sitting in History has no
way back into an editable state and no way to be discarded either. It
just accumulates.

**Why it matters:** a "Draft" that can never be resumed or removed isn't
really a draft — it's permanent, unfinishable clutter. Given the app
already created 3 of these in quick succession during this review alone,
this will accumulate quickly in real use if a stock count is ever started
and not finished in the same session.

**Suggested fix:** add a "Resume" action on a DRAFT row (reload it into
`item_table` as the active count, replacing New Count's "start from
scratch" flow) and a "Delete Draft" action for ones that are genuinely
abandoned.

---

### UX-081: "Save Draft" is a no-op — counts are already auto-saved per keystroke

**Screen:** Stock Take → New Count
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#313](https://github.com/HMAHD/CB-POS/issues/313)

**Not from your notes — found while tracing what "Save Draft" actually
does.** It's misleading in a specific, checkable way.

**Root cause (verified in code):** `save_draft()` (lines 588-590) is
just a message box — it performs no save action itself. That's because
every counted value is already persisted the moment it's typed, via
`update_count()` inside the model's `setData()` (line 117) — the count is
saved continuously, per keystroke, whether or not "Save Draft" is ever
clicked.

**Why it matters:** a button labeled "Save Draft" implies that without
clicking it, your work might be lost — which isn't true here, but a user
has no way to know that, and might avoid closing the screen or worry
unnecessarily believing they need to click it first. Mislabeled buttons
that do nothing (or do less than they claim) erode trust in exactly the
same way a broken one does.

**Suggested fix:** either remove the button (since saving is already
automatic and continuous) or repurpose it into something it can honestly
do — e.g. an explicit "pause and return to this later" action that's
distinct from the auto-save already happening, if that's a real
behavior worth having.

---

### UX-082: Sidebar nav icons and labels have zero gap (correcting UX-045)

**Screen:** Main sidebar, every screen (expanded state)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#314](https://github.com/HMAHD/CB-POS/issues/314)

**What you flagged:** "as you can see, name and icon have no space" —
confirmed directly from your screenshot, every nav row (Dashboard,
Inventory, Purchasing, Credit Book, Reports, Documents, Users, Price
Lists, Promotions, Stock Take) shows the icon touching the label text
with no visible gap at all.

**Correction to UX-045 — I got this wrong earlier and want to be
upfront about it.** That entry claimed "every regular nav button gets
its icon/text spacing from real layout + QSS padding (`add_nav_button`,
no hack)," treating only the POS/Logout buttons' `"   " + text` string
hack as broken. Your screenshot proves that framing wrong: the "correct"
buttons have **no real gap either**.

**Root cause (verified in code):** `SidebarButton`
(`cbpos/ui/widgets/custom_widgets.py:56-70`) is a plain `QToolButton` in
`ToolButtonTextBesideIcon` mode with `setIconSize(QSize(24, 24))` —
nothing else controls icon-to-text spacing. The only relevant QSS rule,
`QToolButton#SidebarButton` (`dark.qss:562-574`), sets:
```css
padding-left: 20px;
```
This is the padding between the **button's left border and the icon** —
it has nothing to do with the gap between the icon and the label text
that follows it. Once any stylesheet is applied to a `QToolButton`, Qt's
CSS-based style engine takes over the button's internal layout and does
not reliably insert its native icon-text spacing on its own — and
nothing in this QSS rule (or anywhere else) supplies one. So the
"correct" buttons and the "hacky" POS/Logout buttons both lack a real
gap; the 3 literal spaces in the POS/Logout hack were, ironically, doing
*something* — likely why the disparity wasn't obvious before seeing this
exact screenshot.

**Why it matters:** this is the app's primary navigation, visible on
every single screen — icon and label reading as one glued blob undercuts
the very first impression of the app on every screen transition.

**Suggested fix:** add an explicit, deliberate gap — either a QSS
`spacing` treatment isn't reliably supported for `QToolButton`, so the
more robust fix is to stop relying on the built-in icon+text layout
entirely: build each nav button's content as an explicit `QHBoxLayout`
(icon `QLabel` + spacing + text `QLabel`) inside a flat, checkable
container, or increase `padding-left` further and additionally pad the
icon's own pixmap with transparent margin so the visual gap becomes
real and consistent at every DPI — then remove UX-045's leftover
string-padding hack entirely, since a real fix here makes it fully
redundant rather than just inconsistent.

---

### UX-083: Sidebar redesign: dull flat treatment, and POS/Logout need real visual hierarchy

**Screen:** Main sidebar, every screen
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#315](https://github.com/HMAHD/CB-POS/issues/315)

**What you flagged:** "sidebar [is] just a bit dull, need modern clean
aesthetic that matches the system... logout and back to POS button also
need proper view and best looking for better UX, be creative, add
suitable style dark and light both, make it pretty awesome and
responsive."

**Where it stands today (verified in code):** the sidebar is flat and
functional but visually thin — `QToolButton#SidebarButton` (`dark.qss:562-586`)
gives every state a flat solid-color background change and a 4px left
border accent, with no rounded corners, no icon-container treatment, no
transition/elevation on hover beyond an instant color swap, and no
grouping — all 10 nav items sit in one undifferentiated vertical list
with equal visual weight, from "Dashboard" down to "Stock Take." The
bottom POS/Logout section (`btn_pos`/`btn_logout`,
`collapsible_sidebar.py:87-99`) reuses the exact same `SidebarButton`
row treatment as regular nav items, just with a solid green/red fill —
visually, "go back to POS" and "log out" read as two more items in the
same list rather than the two most consequential actions on the screen
(one is a full context switch, the other ends the session).

**My recommendation, as the one making the call here:**
- **Group the list.** A subtle section break (a thin divider + faint
  uppercase label, similar to what Reports' category sidebar already
  does) between operational screens (Dashboard, Inventory, Purchasing,
  Credit Book) and management/admin ones (Users, Price Lists, Promotions,
  Stock Take, Reports, Documents) gives the eye a resting point instead
  of one flat 10-item list.
- **Give the active state real weight, not just a border.** A soft
  rounded-rect background behind the active item (matching the app's
  existing 6px radius convention used elsewhere), rather than a flat
  square block with a hairline accent, reads as noticeably more modern
  with almost no extra code.
- **Add a real hover transition.** Even a simple `background-color`
  cross-fade (a short `QPropertyAnimation` on a custom paint, or at
  minimum a slightly softer intermediate hover tone) feels considerably
  more polished than an instant flat-color swap — small effort,
  disproportionate perceived-quality gain.
- **Treat POS/Logout as a distinct, separated "exit" cluster**, not two
  more list rows: pull them visually away from the nav list (a clearer
  gap plus a top divider is already partly there via `addSpacing(10)`,
  worth making more deliberate), keep them as solid-color pills but with
  rounded corners and a subtle icon badge rather than a full-width flat
  bar — since these two are context-ending actions, their shape should
  say so before you even read the label.
- **Light theme needs its own pass, not an inverted dark theme** — check
  that hover/active states in `light.qss` get equivalent treatment once
  the dark-theme redesign is settled, not just inverted colors.
- **Responsive**: this ties directly to UX-046 (the collapsed/expanded
  width discrepancy still needing a live-render check) — whatever
  redesign lands here should be verified at both the 250px expanded and
  70px collapsed widths, and at the narrow-window auto-collapse
  breakpoint (1024px), so "doesn't affect with display sizes" is
  actually verified, not just assumed.

**Suggested fix:** the concrete direction above — grouped sections,
rounded active-state pill, real hover transition, a visually distinct
POS/Logout cluster — implemented consistently across both themes and
tested at collapsed/expanded/narrow-window states before calling it
done.

---

### UX-084: Management screens use 4 different navigation patterns, with no consistent page title

**Screen:** App-wide (every top-level Management screen)
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#316](https://github.com/HMAHD/CB-POS/issues/316)

**What you asked:** "how about your idea in this tab-based pages in this
application, is it good design or bad as an industry-grade top-level
design application, what are the suggestions... I see some pages use
full width/height and some have a top page name, all pages don't have
consistent style and matching appearance, that need to be addressed as
well. I like full, but what matters is good UI/UX so your call."

**Here's my honest answer, and it's grounded in what's actually in the
code, not a general impression:** the tab-vs-sidebar choice itself isn't
the problem — it's actually reasonable that different screens use
different secondary navigation, because the content shapes are
genuinely different. The real problem is that **every one of these
patterns skips a different amount of "where am I" context**, and there
are more of them than you'd expect:

| Pattern | Screens | Top-level page title? |
|---|---|---|
| Flat single page, dedicated title bar | Document Browser (`DocBrowserTitle`), Promotions (`promotion.title`), Credit Book (`credit_book.title`) | ✅ yes |
| Top tabs, no page title at all | Users (`UserView`, `QTabWidget` at line 123, no title label anywhere in the class), Stock Take (`StockTakeView`, same), Purchasing (`PurchaseView`, same — its only title, `PayablePageTitle`, is scoped to one internal tab, not the screen) | ❌ no |
| Secondary left sidebar with a small-caps label | Reports ("REPORTS"), Price Lists ("PRICE LISTS") | ❌ no page title — only a compact sidebar-header label |
| Flat single page, no title at all | Dashboard, Inventory | ❌ no |

That's **4 distinct patterns**, confirmed directly in each view's own
code (grep for a page-title label object in each file) — not 2 or 3.
Tabs make sense for Users (2 fixed, always-relevant peer views) and
sidebar-lists make sense for Price Lists (a variable, user-created list
of items). That part of the design is defensible. What isn't defensible
is that **a third of these screens (Users, Stock Take, Purchasing) show
literally nothing identifying the screen you're on** beyond the sidebar's
own highlighted item — open Stock Take and the very first thing you see
is "New Count | History," with no "Stock Take" text anywhere on the
visible screen.

**My actual recommendation, since you asked for the call:** keep the
tabs and sidebar-lists exactly where they already make sense for their
content — don't force everything into one navigation widget. But make
**one thing** universal across every top-level Management screen: a
slim, consistent title strip at the very top (the same treatment
Document Browser/Promotions/Credit Book already use), *before* whatever
secondary navigation follows it — tabs, a sidebar, or straight into
content. This doesn't have to cost real estate: it can be a compact
single-line header (icon + screen name, nothing else), not the full
~80px title block those 3 screens currently use. That resolves the
tension in your own question directly — you can keep full-width/height
content below it (which you said you like) while still never leaving a
screen with zero identifying context at the top. Right now the
inconsistency isn't "tabs vs. sidebar," it's "title vs. no title," and
that's the one piece worth standardizing everywhere.

**Suggested fix:** add a shared, compact `PageHeader` widget (icon +
screen name, one consistent height/style in both themes) and place it at
the top of every Management screen that currently has none (Users,
Stock Take, Purchasing, Dashboard, Inventory, Reports, Price Lists) —
Reports/Price Lists can keep their sidebar's own internal label as a
secondary element, but should still get this same top-level strip so
their header treatment matches Document Browser/Promotions/Credit
Book's, rather than being a fourth pattern of its own.

---

### UX-085: Settings' footer bar being hidden (not reserved) creates a 70px height jump between pages

**Screen:** Settings, every sidebar section
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#317](https://github.com/HMAHD/CB-POS/issues/317)

**What you flagged:** "the Save Changes and Cancel buttons don't appear
on Payments, Data Safety, and Admin Tools — it's okay for them to be
there [on other pages], but it makes the sidebar [look] short; how about
[the footer] starts from the page, not from that end, so it doesn't
affect the sidebar? Let's keep Management and Settings sidebar styles
identical."

**Two things worth separating here, one confirmed, one that needed
correcting after checking the actual layout code:**

**First — the sidebar is already identical, nothing to "keep in sync":**
`settings_view.py:59` builds `self.sidebar = CollapsibleSidebar()` with
the exact same zero-argument construction as
`management_view.py:47`. It's not two similar sidebars that could drift
apart — it's the literal same shared widget class, so every sidebar fix
already logged (UX-044/045/046/082/083) already covers Settings
automatically, with no separate work needed to "match" them.

**Second — the footer bar's hide/show does cause a real inconsistency,
but not the one it looks like at first glance.** `footer_frame`
(`settings_view.py:119-141`, fixed height 70px, holding Save Changes/
Cancel) is built once and sits as a **sibling of the sidebar+content
row** in the outer layout — not scoped to content width, and not part of
the sidebar at all. `_update_footer_visibility`
(`settings_view.py:202-204`) hides it entirely
(`setVisible(index < len(self.pages))`) for exactly the 3 pages you
named — Payments, Data Safety, Admin Tools sit outside the indexed range
of pages that get a footer. Because Qt's layout system reclaims space
from a hidden widget, hiding this 70px bar should make the row
*containing* the sidebar **taller**, not shorter — so the specific
"buttons missing → sidebar looks short" causation doesn't hold up
against the actual widget tree. What's real is simpler: **the total
visible content area is ~70px taller on those 3 pages than on the other
7**, which is exactly the kind of inconsistency that would read as "this
page feels different" even if "shorter sidebar" isn't the literal
mechanism.

**Why it matters:** whether or not the sidebar itself moves, a
±70px jump in usable content height depending on which of 10 sidebar
items is selected is a real, fixable inconsistency — three sections
suddenly get noticeably more vertical room than the other seven for no
reason a user would understand.

**Suggested fix:** don't hide the footer bar — keep its 70px of space
reserved on every page (even if the buttons inside it are disabled/blank
for Payments/Data Safety/Admin Tools, or simply always show Save/Cancel
there too if those pages have anything save-able), so every Settings
section renders at the same total height regardless of which sidebar
item is active.

---

### UX-086: Settings Appearance tab has 3 mismatched field widths, and the same broken spinbox stepper

**Screen:** Settings → Shop Info → Appearance
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#370](https://github.com/HMAHD/CB-POS/issues/370) (sub-issue of [#263](https://github.com/HMAHD/CB-POS/issues/263))

**What you flagged:** "in the Appearance tab you can see several
issues, UI/UX not clean and modern — it shows 3 sizes, need proper size
and matching each, carefully designed."

**Confirmed, and this is exactly the pattern UX-038 predicted would keep
showing up "wherever similar elements are found":** `settings_pages.py`'s
Appearance tab (lines 277-301) uses a `QFormLayout` with
`ExpandingFieldsGrow` (`_build_form_tab()`, line 104) — the same
mechanism already logged for the Customer Editor's Commercial tab and
the Proforma dialog. None of the three fields (`spin_font_size`, line
280; `combo_theme`, line 286; `combo_language`, line 290) get an explicit
width, so each one sizes to its own content — the spinbox to "12 px",
the theme combo to its longest item text ("Ceylon Night (Dark)"), the
language combo to its own ("English (en)") — three different widths,
exactly the "3 sizes" you're seeing, with no shared column to anchor
them.

**On top of that, Font Size is a plain `QSpinBox`** (line 280-282, range
8-24, `" px"` suffix) — the same native-stepper widget already flagged
as breaking under this app's QSS in 5 other places (UX-018/025/038/055/067).
This is now the sixth confirmed instance.

**One thing that is working correctly, for contrast:** the "(Font Size
and Language changes require restart)" hint is real and present
(`settings_pages.py:297-299`, `en.json:1250`) — that part of the design
is fine, just the fields above it aren't.

**Suggested fix:** same as UX-038 — give every field in this form a
consistent minimum width, and replace the Font Size spinbox with a
`QLineEdit` + integer validator, matching the pattern already proven
correct in `product_editor.py`.

---

### UX-087: Report Time and Sales Tax fields have the same mismatched-width problem — the fix is already in the same file

**Screen:** Settings → Shop Info → Email tab, and Sales Tax page
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#371](https://github.com/HMAHD/CB-POS/issues/371) (sub-issue of [#263](https://github.com/HMAHD/CB-POS/issues/263))

**What you flagged:** "Report Time is hard to see, lacks UI/UX skill...
Sales Tax page also has the same unmatching-size problem."

**Report Time (confirmed):** `settings_pages.py:248-251` builds
`time_auto_report` as a plain `QTimeEdit` with `setDisplayFormat("HH:mm")`
and no width set at all — same `_build_form_tab()` /
`ExpandingFieldsGrow` mechanism as UX-086, so the full-width Admin
Email/SMTP text fields below it stretch while this one stays at its tiny
native size. Same root cause, seventh confirmed instance across the app.

**Sales Tax — confirmed, and genuinely more revealing than a typical
instance of this bug:** `SalesTaxPage` (`settings_pages.py:485-562`) has
**six** numeric/combo fields across its Sales and Tax sub-tabs. Three of
them — `spin_max_discount` (line 502), `spin_vat` (line 534), `spin_sscl`
(line 542), `spin_sscl_turnover` (line 550) — already get an explicit
`setFixedWidth(200)`. The other two — `combo_search_mode` (line 494),
`spin_loyalty_ratio` (line 510), `spin_default_credit` (line 516) — get
no width at all and stretch full-width. **This means the correct fix
(`setFixedWidth(200)`) already exists as a convention in this exact
file** — it just wasn't applied consistently to every field in the same
class.

**Why it matters:** this is the easiest version of this bug to fix
anywhere in the app — there's no design decision left to make, no new
convention to invent, just applying the width value already sitting three
lines away to the fields that were skipped.

**Suggested fix:** apply `setFixedWidth(200)` (or promote it to a shared
named constant, since it's clearly already the house convention for this
kind of field) to `combo_search_mode`, `spin_loyalty_ratio`,
`spin_default_credit`, and `time_auto_report` — closing out this specific
instance of UX-038's pattern with the least effort of any table/dialog
found so far.

---

### UX-088: Good pattern worth reusing: the Gmail help guide should become the app's standard for technical fields

**Screen:** Settings → Shop Info → Email tab
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#318](https://github.com/HMAHD/CB-POS/issues/318)

**What you flagged, positively:** "I love that — we could use that
style when we have to add info or help, to make things easy for the
user."

**You're right to want more of this — confirmed it's a genuinely
well-built pattern, not just good-looking:** `settings_pages.py` wires
two complementary things together, not one. "Use Gmail" (`btn_gmail`,
line 224) actually does something on click —
`_prefill_gmail()` (line 367-372) auto-fills SMTP Host with
`smtp.gmail.com` and Port with `587`, then focuses the User field —
plus a tooltip explaining what it does. The blue info-circle
(`btn_help`, line 232-240) both shows a hover tooltip *and*, on click,
opens a real 4-step numbered guide dialog (`_show_smtp_guide()`,
lines 374-411) walking through enabling 2-Step Verification, generating
a Gmail App Password, and where to paste it — genuinely useful,
task-specific help, not a generic "?" that just repeats the label.

**Why it's worth calling out as a feature idea, not just a compliment:**
this app has several other fields across the catalog so far that are
exactly as unfamiliar to a non-technical shop owner as SMTP settings —
Purchasing's Payment Terms, Price Lists' date ranges, tax calculation
fields on this same Sales Tax page (VAT/SSCL) — none of which currently
get any equivalent help affordance.

**Suggested fix (feature idea):** extract this into a small reusable
`HelpIconButton` widget (icon + tooltip + optional click-to-open guide
dialog) and deliberately place it next to any other field in the app
where a non-technical user is likely to need the same kind of "what do I
put here and why" guidance — this is a good candidate for a genuinely
new, small shared component, not just a one-off worth admiring on this
one screen.

---

### UX-089: Checkbox hover is already universal in CSS — the perceived inconsistency traces to UX-060 instead

**Screen:** Settings, app-wide
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#319](https://github.com/HMAHD/CB-POS/issues/319)

**What you flagged:** "settings have toggles, but only a few have a
hover effect — I'd like all of them to have that."

**Worth correcting the premise before "fixing" the wrong thing:**
checked the actual QSS — `dark.qss:201-227` (mirrored in `light.qss`)
defines `QCheckBox::indicator:unchecked:hover` and
`QCheckBox::indicator:checked:hover` with **no objectName or class
qualifier at all** — it's already a fully generic rule. A full-repo grep
confirms **no checkbox anywhere in the app has `setObjectName()` called
on it** — "Enable Daily Auto-Report" and every other real `QCheckBox` in
the codebase (Sales Tax's VAT/exemption checkboxes, Product Editor,
Customer Editor, Users, Payment Methods) should already get this hover
effect identically, since there's nothing in the stylesheet that could
scope it to only some of them.

**So where's the inconsistency actually coming from? Most likely the
same root cause already logged as UX-060.** Not every checkbox-*looking*
control in this app is a real `QCheckBox` widget — UX-060 found that
Permission Manager's checkboxes are `QTreeWidgetItem.setCheckState()`
calls, rendered by Qt's native tree-item delegate, which **never**
receives `QCheckBox::indicator` QSS at all, hover included. If similar
non-`QCheckBox` check controls exist elsewhere (worth a quick sweep next
time one is spotted), that would fully explain "only some have the
effect" without any scoping bug in the stylesheet itself — the rule
genuinely is universal for the widgets it can reach.

**Why it matters:** worth flagging so effort doesn't get spent hunting
for a scoping bug in `dark.qss` that isn't there — the actual fix, if
this is confirmed, is the same one already proposed in UX-060 (use real
`QCheckBox` widgets, or apply matching QSS to whatever custom check
control is being used instead).

**Suggested fix:** none needed at the CSS layer — if a specific
non-hovering checkbox-like control turns up on a future screen, log it
as another confirmed instance of UX-060's pattern rather than a new
mystery.

---

### UX-090: Daily Auto-Report has two independent reliability bugs, confirming your suspicion

**Screen:** Settings → Shop Info → Email tab
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#320](https://github.com/HMAHD/CB-POS/issues/320)

**What you flagged:** "also check that it works or not — [the] report
timer, I think that functionality [is] not properly set up and
connected." You were right, and it's two separate bugs, not one.

**Bug 1 — enabling the feature mid-session does nothing until the app
restarts.** `main.py:292-302` only creates the scheduler `QTimer` if
`ConfigService.get("auto_report_enabled")` was already `True` **at
process startup**:
```python
if ConfigService.get("auto_report_enabled"):
    ...
    scheduler_timer.start(60_000)
```
There is no code anywhere in `settings_view.py` or `main_window.py` that
starts or stops this timer when the setting is changed (confirmed by
grep — zero matches). So the normal way anyone would actually discover
and turn on this feature — opening Settings, checking the box, clicking
Save Changes, during a running session — **has no effect at all** until
the next full app restart, with nothing in the UI indicating this.

**Bug 2 — a failed send is invisible to the user.**
`SchedulerService.check_automation()` (`scheduler_service.py`) correctly
reads the same `auto_report_enabled`/`auto_report_time`/`admin_email`
config keys the UI writes, and correctly guards against re-sending
within the same day (a stored `auto_report_last_run` date flag) — this
part is sound. But `EmailService.send_email_with_pdf` fires the actual
send on a detached `threading.Thread` with no completion callback
(`email_service.py:86-96`), and `scheduler_service.py:77` logs
`"Auto-Report sent to %s"` **immediately**, before the thread has
actually attempted delivery — so that log line is written regardless of
whether the email ever really went out. If SMTP genuinely fails (wrong
password, unreachable host), the only trace is
`logger.error(...)` inside the background thread
(`email_service.py:56-57`), written to the rotating log file only — no
`AuditLog` entry, no UI notification, nothing a shop owner would ever
see. The report can silently never arrive, with the log even claiming
it did.

**Why it matters:** this is exactly the kind of feature that erodes
trust once discovered — a checkbox that appears to work (no error, no
warning) but doesn't actually schedule anything until a restart, feeding
into a send path whose one failure signal is a file nobody but a
developer would ever open.

**Suggested fix:** have Settings' save handler start/stop the scheduler
`QTimer` directly when the checkbox changes, instead of only reading the
flag once at process launch; and have `EmailService` report real
success/failure back to the scheduler (via a callback or by making the
send synchronous within the already-background-safe scheduler context)
so a failure can be written to `AuditLog` and surfaced somewhere a user
would actually see it — a small banner or the existing Activity Log
(once UX-062/063's audit-logging fixes land) would both work.

---

### UX-091: "Cut & Drawer" tab label is silently eaten by Qt's mnemonic parser

**Screen:** Settings → Hardware, sub-tab bar
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#321](https://github.com/HMAHD/CB-POS/issues/321)

**What you flagged:** "tab names are not showing" — the second tab
reads "Cut Dra..." instead of its full name.

**Two separate causes found, one certain and one platform-dependent —
worth keeping them distinct rather than treating this as one bug:**

**The certain one:** `cbpos/i18n/en.json:1309` (and the matching key in
`si.json`/`ta.json`) defines this tab's label as:
```json
"tab_cut_drawer": "Cut & Drawer"
```
A literal, unescaped `&`. Qt's `QTabBar` (like `QPushButton` and every
other Qt widget that supports mnemonics) treats a single `&` as an
accelerator marker — it gets consumed by Qt's mnemonic parser instead of
being rendered as a visible character. So "Cut & Drawer" doesn't display
as "Cut & Drawer" at all — the `&` vanishes and the next letter would
normally get an underline accelerator hint. This is a genuine content bug,
platform-independent, and fully reproducible — not a maybe.

**The platform-dependent one (secondary contributor):** no code anywhere
sets `setElideMode`, a min/max width, or a font override on this
`QTabWidget`/`QTabBar` (confirmed by grep — nothing constrains it).
Rendered headless, the tab bar's own `elideMode()` defaults to `ElideNone`
with `usesScrollButtons() == True` — nothing in this codebase asks Qt to
truncate. The "..." you're seeing most likely comes from the **native OS
widget style's** own truncation behavior (Windows' Vista/11 styles elide
long tab labels when the bar is narrower than its tabs' natural width;
other styles like Fusion don't) — meaning this part is real on the
Windows build this app ships for, but isn't something reproducible from
the code alone in every environment, similar to UX-014/UX-046's
platform-dependent findings.

**Why it matters:** between the two, at least one (the `&` mnemonic bug)
is guaranteed to be visibly wrong for every user on every platform —
worth fixing regardless of how the width-truncation question resolves.

**Suggested fix:** escape the ampersand in the i18n string (`"Cut &&
Drawer"` — Qt's convention for a literal `&`) across all three language
files, and separately, give the sub-tab bar enough width or an explicit
elide policy so labels don't get cut off due to native style truncation
on narrower windows.

---

### UX-092: "Copies" field box proportions make its value easy to misread as blank (couldn't confirm a code-level bug)

**Screen:** Settings → Hardware → Printers → Print Behavior
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#322](https://github.com/HMAHD/CB-POS/issues/322)

**What you'd likely flag if pressed on it — the "Copies" field looks
completely empty in the screenshot, just a box with +/- steppers and no
visible number.**

**Investigated thoroughly, and being upfront that I could not confirm an
actual invisible-text bug — this is worth logging honestly rather than
asserting a defect I can't prove, the same discipline as UX-014.**
`spin_copies` (`settings_pages.py:775-776`) is a `QSpinBox` with
`setRange(1, 5)` — its minimum is 1, not 0, so it can never render a
literal blank/zero value, and its default is explicitly loaded as
`settings.get("receipt_copies", 1)` (line 933). I rendered this exact
widget headless with the app's real compiled QSS and it displayed "1"
clearly — I could not reproduce a genuine color/contrast collision in
either theme (`dark.qss:889-899` and `light.qss:948-950`, the
ID-scoped rules that apply here, both have clearly contrasting text/
background colors).

**My best working theory, not a confirmed cause:** the same QSS rule
that sizes this spinbox reserves `min-height: 32-36px` and
`padding-right: 35px` (for the stacked +/- buttons), producing a
noticeably tall box for a single digit — the value likely renders small
in the top-left corner with a lot of visually "dead" space below it,
which could easily read as "empty" in a screenshot or at a glance,
without the text itself actually being invisible.

**Why it matters either way:** whether it's a genuine rendering bug or
just a proportions problem, a field a cashier needs to trust before
printing multiple receipt copies shouldn't be ambiguous about its own
value at a glance.

**Suggested fix:** before changing anything, this needs a real visual
check on the actual target platform (Windows, the app's primary build
target) rather than further code reading — if the value truly isn't
visible there, it's a live styling bug; if it's just small/high in a
tall box, tightening the box height or centering the value vertically
would resolve the "looks blank" impression either way.

---

### UX-093: Printer list never rescans — a newly connected printer needs a full app restart to appear

**Screen:** Settings → Hardware → Printers
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#323](https://github.com/HMAHD/CB-POS/issues/323)

**Not from your notes — found while checking the "No printers found"
state shown in your screenshot (which is itself a legitimate, expected
placeholder in an environment with no physical printer attached, not a
bug on its own).**

**Root cause (verified in code):** `settings_pages.py:735`:
```python
available_printers = QPrinterInfo.availablePrinterNames() or [_t("settings.hardware.no_printers")]
```
This detection runs exactly **once**, inside `HardwarePage.__init__()`.
`HardwarePage` itself is constructed exactly once per app session
(`settings_view.py:92`) and kept alive in a `QStackedWidget` for the rest
of that session. There is no "Refresh"/"Detect Printers" button anywhere
on this tab, and no other call to `availablePrinterNames()` exists in the
file. So if a shop owner plugs in a receipt printer *after* opening the
app (a very plausible real-world sequence — printer wasn't on, or wasn't
plugged in, at boot), simply re-opening Settings won't pick it up — the
whole application needs to be restarted.

**Why it matters:** hardware setup is exactly the kind of task where a
non-technical user will plug something in, look for it in the list, not
see it, and have no idea a full app restart (not just navigating away
and back) is what's actually required.

**Suggested fix:** add a small "Refresh" button next to the printer
combos that re-runs `QPrinterInfo.availablePrinterNames()` and
repopulates them without needing a restart.

---

### UX-094: Good pattern already built: the section-divider helper should be reused in the sidebar redesign

**Screen:** Settings → Hardware (and every other Settings page); relevant to the sidebar redesign discussed in UX-083
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#324](https://github.com/HMAHD/CB-POS/issues/324)

**Not from your notes — found while reviewing this page's section
headers ("Printer Selection," "Print Behavior," "Test Hardware"), and
worth flagging as good news, not a new bug to fix.**

**What's already built:** `SettingsPage._make_section_header()`
(`settings_pages.py:143-165`) is a small, reusable, already-DRY helper —
a `QWidget` with a bold `QLabel` (`SettingsSectionTitle`) plus an
`HLine`-shaped `QFrame` (`SettingsSectionLine`) that stretches to fill
the remaining row width. Every section on this page (and presumably
others in Settings) is just one call:
`form.addRow(self._make_section_header(_t(...)))`. It's a clean,
lightweight way to group related fields with a visible label + divider,
and it already exists as a single shared method, not duplicated
per-screen.

**Why this matters right now:** UX-083 (the sidebar redesign) recommended
adding subtle section grouping to the main nav list (splitting
operational screens from admin/management ones) as a "modern, clean"
improvement. This is exactly that pattern, already built, already
proven, and already themed for both light and dark — no new component
needs to be designed or QSS written from scratch.

**Suggested fix / feature idea:** when implementing UX-083's sidebar
redesign, reuse (or adapt) `_make_section_header()`'s visual language for
the sidebar's section dividers instead of inventing a new one — same
visual system, less new code, guaranteed consistency between Settings
and the main navigation.

---

### UX-095: Receipt preview never reflects the actual configured paper width — always renders at 80mm

**Screen:** Settings → Receipt
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#325](https://github.com/HMAHD/CB-POS/issues/325)

**What you flagged:** you called this one of the most important features
in the app and asked for a precise, thorough review — this is the single
most concrete bug that came out of it.

**Root cause (verified in code):** `ReceiptPreviewWidget.__init__`
(`cbpos/ui/widgets/receipt_preview_widget.py:54`) hardcodes
`self._paper_width = "80mm"`. There's a real setter,
`set_paper_width()` (line 86), but `ReceiptPage.init_ui()`
(`settings_pages.py:1041`, `self._preview = ReceiptPreviewWidget()`)
**never calls it** — confirmed by grep, the only two references to
`ReceiptPreviewWidget` in the whole codebase are its own file and this
one construction call, with no setter invocation anywhere. Meanwhile the
real paper width lives on a completely different page —
`combo_paper_width` on the Hardware tab (`settings_pages.py:756-759`),
saved as config key `"paper_width"` (line 954).

**The text content is actually correct — only the visual container is
wrong, which makes this worse, not better:** the underlying receipt
builder does read the real `"paper_width"` config and correctly wraps
two-column rows to 32 characters (58mm) or 42 (80mm)
(`base_receipt_builder.py:81-82`). But the preview's rendered container
width is a fixed pixel value (`_PAPER_PX = {"80mm": 302, "58mm": 220}`,
line 48) that stays at 302px regardless, because the setter that would
switch it is never called. So a shop with a real 58mm printer sees
correctly-wrapped 32-character-wide text floating inside a visibly wider
80mm-shaped preview canvas — the exact opposite of what "preview updates
live" (this page's own subtitle) promises.

**Why it matters:** this directly undermines the one feature this page
is built around. A shop owner configuring their actual 58mm thermal
printer has no way to see, before printing a real receipt, how narrow
their lines will actually be — the preview actively misrepresents it.

**Suggested fix:** read the real `"paper_width"` config value when
building the preview and call `set_paper_width()` with it — one missing
call away from being correct, since both the setter and the correct
underlying text-wrapping logic already exist.

---

### UX-096: Preview and real thermal print use two independent text renderers for free-form header/footer text

**Screen:** Settings → Receipt
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#326](https://github.com/HMAHD/CB-POS/issues/326)

**Not from your notes directly, but squarely inside what you asked me to
check — whether this "is far below industry-grade" functionally, not
just visually.**

**Good news first: the underlying content is genuinely single-source-of-
truth.** `ReceiptPage._refresh_preview()` (`settings_pages.py:1238-1244`)
and the real print path,
`PrinterService._print_thermal_receipt()`
(`cbpos/core/services/printer_service.py:66-88`), both build their
receipt from the exact same `ReceiptBuilder.build_receipt(...)`
(`cbpos/core/services/receipt_builder.py:21-30` →
`sales_receipt_builder.py:34-235`) — header/footer/logo/toggle text
can't drift between the two paths at the data level.

**But the two paths *render* that shared content with two independently-
written engines, and free-form text isn't pre-wrapped for either:** the
preview renders via HTML `<div>`s inside a fixed-width table cell
(`receipt_preview_widget.py:116-224`, Courier New 11.5px), letting Qt's
own HTML/CSS engine decide where lines break. The real printer path
hands the same string to `python-escpos`'s `printer.text()`
(`escpos_driver.py:109-113`), which wraps according to the physical
ESC/POS thermal head's own font metrics. Only pre-formatted, fixed-width
fields (two-column price rows via `_two_col`/`_split_row`,
`base_receipt_builder.py:116-138`) are guaranteed identical between the
two. Free-form **Header Text**/**Footer Text** is appended completely
unwrapped (`base_receipt_builder.py:86-88`,
`sales_receipt_builder.py:222-225`) — each renderer wraps it on its own,
so a long header/footer is not guaranteed to break at the same point on
screen as it will on paper.

**Compounding this: there's no guidance telling the user how much room
they actually have.** Both fields are multi-line `QTextEdit`s
(`settings_pages.py:1086-1094`) with no `setMaxLength`, no character
counter, and the 32/42-character-per-line budget
(`base_receipt_builder.py:82`) exists only as an internal constant —
never surfaced anywhere in the UI. A shop owner can type an arbitrarily
long greeting with zero warning that it'll wrap unpredictably, and
differently, on the two things they're comparing (the preview and the
real receipt).

**Why it matters:** the whole value of a live preview is trusting that
what you see is what prints — for the one type of content most likely to
be genuinely custom-written (a shop's own greeting/thank-you message),
that promise doesn't fully hold.

**Suggested fix:** pre-wrap free-form header/footer text to the real
character budget (32/58mm or 42/80mm) once, in the shared builder, so
both renderers receive already-line-broken text instead of wrapping it
independently — and surface a live character-count indicator under each
field so the user can see the real limit while typing.

---

### UX-097: A real print-preview dialog already exists in the codebase, but is completely unwired

**Screen:** App-wide (sales flow — where a real print preview would
belong)
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#327](https://github.com/HMAHD/CB-POS/issues/327)

**Not from your notes — found while tracing the preview/print pipeline.**
`cbpos/ui/dialogs/receipt_preview_dialog.py` defines a
`ReceiptPreviewDialog` — a genuine "see the real receipt before it
prints" surface. A full-repo grep found **no caller instantiating it
anywhere** — it's built, but dead. There is currently no "preview before
you print" step anywhere in the live sales flow; the only preview a user
ever sees is the mock on this Settings page, built from a dummy sale,
not the receipt about to actually print.

**Why it matters:** this is exactly the kind of feature a shop owner
would expect from an industry-grade POS (confirm before committing paper
to a mistake) — the work to build it already happened, it's just never
been connected to anything.

**Suggested fix:** either wire `ReceiptPreviewDialog` into the real
checkout flow (e.g. an optional "Preview before printing" toggle, or
always show it before the first print of a session) or, if it's
intentionally being retired in favor of the Settings-page mock, remove
the dead file rather than leave a half-built feature sitting unreferenced.

---

### UX-098: QR code support is fully documented in the receipt schema, but never actually emitted

**Screen:** Settings → Receipt
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#328](https://github.com/HMAHD/CB-POS/issues/328)

**Not from your notes — found while checking receipt content types
against what's actually used.** `base_receipt_builder.py:22` explicitly
documents `'code': 'QR'` as a supported command type in the receipt
schema's own comment — but a full-repo grep shows it is **never emitted
anywhere**; only `"CODE39"` barcodes are ever built
(`sales_receipt_builder.py:219`). There's no toggle for it on the
Display tab either (confirmed against the full 5-checkbox list in
UX-101's investigation).

**Why it matters (feature idea, not a defect):** a QR code linking to a
digital receipt, a review page, or a loyalty signup is a standard,
high-value feature on modern receipts — the schema was clearly designed
with this in mind and then never finished.

**Suggested fix:** finish what was started — add a Display-tab toggle
and an actual `'code': 'QR'` emission (e.g. linking to a digital copy of
the receipt, or the shop's page), since the plumbing for it already
exists in the schema.

---

### UX-099: Receipt preview barcode is explicitly decorative and not scannable, by the code's own admission

**Screen:** Settings → Receipt
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#329](https://github.com/HMAHD/CB-POS/issues/329)

**Not from your notes — found while checking barcode rendering fidelity.**
`_generate_barcode_bars()` (`receipt_preview_widget.py:226-245`) contains
its own comment stating this is "purely decorative — it is NOT scannable
but looks like a barcode in the preview." So toggling "Show Barcode" on
and looking at the preview tells you nothing about whether the barcode
that actually prints will scan correctly — the preview can't be used to
verify that at all.

**Why it matters:** low severity since it doesn't affect the real print
output, but worth documenting clearly so nobody (including future me,
reviewing this page again later) mistakes the preview as validating
barcode print quality.

**Suggested fix:** none required functionally — optionally, a small
"preview only" label/tooltip on the barcode area would prevent this from
ever being mistaken for a real scannability check.

---

### UX-100: Shop Logo has no size guidance and no real dithering step for thermal print quality

**Screen:** Settings → Receipt → Content
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#330](https://github.com/HMAHD/CB-POS/issues/330)

**Not from your notes — found while checking how the logo actually gets
from a file picker to a thermal printout.** `browse_logo()`
(`settings_pages.py:1250-1258`) only opens a file dialog filtered to
PNG/JPG/BMP and sets the path — no file-size check, no dimension check,
no re-validation of the image at all.

**On the print side:** `ESCPOSDriver.print_commands()`
(`escpos_driver.py:115-127`) only does a width-based downscale if the
image exceeds a configured max pixel width (`printer_image_max_width`,
default 500px) — there is no grayscale conversion or dithering done in
CB-POS's own code; whatever monochrome conversion happens is left
entirely to `python-escpos`'s internal `printer.image()` call, not
something this app controls, previews, or lets the user tune. There's
also no resizing tied to the actual configured paper width's dot-column
count (58mm/80mm have different physical dot widths) — just one fixed
pixel cap regardless of paper size.

**One thing that does work correctly, for contrast:** the preview *does*
render the real selected logo file (`receipt_preview_widget.py:178-186`,
embeds the actual image), so what you see in this Settings page really
is that image — it just doesn't show you how it'll look once converted
to 1-bit thermal dots, which is the part that commonly looks bad on real
hardware if the source image isn't already high-contrast.

**Why it matters:** a logo that looks fine as a full-color PNG in the
picker can turn into an unreadable grey blob once naively converted to
monochrome thermal dots — exactly the kind of print-quality problem a
shop owner would only discover after printing (and wasting) real receipt
paper.

**Suggested fix:** add basic guidance (recommended dimensions, "high
contrast black & white works best") next to the Logo field, and
consider doing an explicit dithering pass (e.g. Floyd-Steinberg via
Pillow) before handing the image to `python-escpos`, so the preview and
the app have actual control over — and can show — how the logo will
really look in 1-bit thermal output.

---

### UX-101: Receipt customization is fragmented across 3 disconnected Settings pages

**Screen:** Settings → Receipt, Hardware, Documents
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#331](https://github.com/HMAHD/CB-POS/issues/331)

**Not from your notes — found while cataloging everything actually
configurable for receipts, in response to your ask to find "the most
important details."**

**What's on the Receipt page itself (confirmed complete list):**
Content tab — Shop Logo, Header Text, Footer Text, Print Language.
Display tab, 5 checkboxes across 2 groups
(`settings_pages.py:1123-1167`): Show Barcode, Merge Items, Tax
Breakdown (VAT+SSCL), Show Cashier Name, Show Terminal ID.

**But two settings that are just as much "receipt customization" live on
entirely different pages, with no link or cross-reference between
them:** number of copies to print / auto-print behavior is on the
**Hardware** tab (`spin_copies`, `settings_pages.py:775-778`), and the
receipt/document numbering format (e.g. how sale/purchase/return
document numbers are formatted) is on the **Documents** tab
(`input_fmt_sale/purchase/return`, lines 659-669). Someone customizing
"how my receipts look and behave" has to already know to check two other,
unrelated-sounding sidebar sections to find the rest of what governs
that.

**Why it matters:** this is a discoverability problem specific to what
you called out as one of the most important features — a shop owner
tuning their receipt is likely to set the header/footer/logo, feel done,
and never realize copy count or numbering format are configured
somewhere else entirely.

**Suggested fix:** at minimum, add a short cross-reference note on the
Receipt page ("Copies & auto-print: see Hardware. Numbering format: see
Documents.") — or, more thoroughly, consider consolidating all
receipt-related settings onto this one page, since that's clearly the
mental model a user already brings to it.

---

### UX-102: System Security tab field truncation — couldn't reproduce from code, same widget class as UX-092

**Screen:** Settings → System → Security
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#332](https://github.com/HMAHD/CB-POS/issues/332)

**What you flagged:** "the system settings page also isn't correctly
aligned with each other, because of that text doesn't show up
properly" — pointing at "Inactivity Timeout" reading `:abled (no
auto-lock)`, "Max Login Attempts" showing only `!`, and "Lockout
Duration" showing `300 se`.

**Investigated thoroughly, and being honest that I could not confirm a
code-level defect — same discipline as UX-014/UX-046/UX-092.** All three
fields are `QSpinBox` (`settings_pages.py:1355,1365,1370`), not
`QComboBox` as the truncated text might suggest. None gets an explicit
width — same "bare `QSpinBox`, no width call" pattern already found for
the Copies field (UX-092). But rendered headless with the app's real
compiled QSS at a normal window width, all three displayed their full
text with no clipping: "Disabled (no auto-lock)" (the exact special-value
string at `en.json:1392`, confirming that's what the screenshot's
`:abled...` fragment is the tail of), "3"–"20" for Max Login Attempts,
and "300 sec" for Lockout Duration (the suffix is `" sec"`, not
`" seconds"` — so `300 se` is one character short of the true label, not
an oversized-suffix problem).

**What this means:** there's no hardcoded narrow width or suffix-
measurement bug in this code to point to — so if this is genuinely
happening on the real target platform, it's most likely an environment-
specific factor (Windows DPI/scale-factor rounding, an actual narrower
window, or a first-paint-before-QSS-polish geometry glitch) rather than
something fixable by reading the source further. Worth flagging plainly
as unconfirmed rather than asserting a line-level cause I can't back up.

**One thing that is confirmed working well here, for contrast:** all
four fields on this tab already have tooltips
(`settings_pages.py:1459,1461,1463,1465`) — this page already does the
thing UX-104 finds completely missing on Network, two tabs away in the
same file.

**Suggested fix:** this needs a real screenshot/render from the actual
Windows target environment (matching the DPI/scale settings a real
install would use) before deciding what to change — if it reproduces
there, the underlying fix is the same shared one already proposed for
UX-092 (explicit minimum widths on bare `QSpinBox` fields across
Settings, sized to their real content including any suffix).

---

### UX-103: Network mode icon is a raw emoji, not the app's icon system — explaining the black background

**Screen:** Settings → Network → Mode
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#333](https://github.com/HMAHD/CB-POS/issues/333)

**What you flagged:** "under [the] text [there's a] black background and
an emoji — that's not professional."

**Root cause (verified in code) — confirmed, and it's the first place in
this entire review where the app departs from its own icon system:**
`settings_pages.py:1556`:
```python
self.lbl_mode_icon = QLabel("\U0001f4bb")  # 💻
```
A literal Unicode emoji character in a plain `QLabel`, swapped for
`"\U0001f310"` (🌐) when switching to Network mode
(`settings_pages.py:1974,1978`). Every other icon anywhere else in this
app goes through `Icons.get()` (qtawesome, theme-colored vector icons) —
this is the only place a raw emoji glyph is used instead. `QLabel#StatusIcon`
(`dark.qss:1930-1933`) only sets font-size/min-width — no background —
confirming the black box you're seeing is the emoji glyph's own
fallback-font rendering, not something the app's QSS is drawing; emoji
characters render via the OS's own emoji font/rendering path, which
doesn't respect the app's theme colors the way a qtawesome icon would.

**Why it matters:** this is a small, isolated inconsistency, but it's
exactly the kind of detail that reads as unpolished specifically because
every other icon in the app looks and behaves consistently — one emoji
breaks that pattern visibly.

**Suggested fix:** replace both emoji with real qtawesome icons via
`Icons.get()` — e.g. `fa5s.desktop` for Standalone, `fa5s.network-wired`
for Network mode — matching every other icon in the app.

---

### UX-104: Network page has almost no explanatory text, which is exactly why Mode vs. LAN Sync reads as redundant

**Screen:** Settings → Network
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#334](https://github.com/HMAHD/CB-POS/issues/334)

**What you flagged:** "I'm a bit confused now — do Mode and LAN Sync do
the same thing, or are they separate? Also, settings pages need some
kind of tooltip to explain what they do — that would be very helpful."

**Good news on the substance — they're genuinely not redundant, I
checked precisely:** Mode + Server + Migration (`settings_pages.py:1546-1730`)
configure switching the whole app to a **shared PostgreSQL backend** —
`db_mode` is read directly in `cbpos/core/database.py:47-64`, branching
the SQLAlchemy engine between SQLite and PostgreSQL. LAN Sync
(`settings_pages.py:1732-1852`) is a **completely different mechanism**:
peer-to-peer HTTP queue-replication between independent SQLite
databases, with its own `terminal_mode` (Standalone/Main PC/Terminal),
sync port, main PC address, and shared secret — read in `main.py:322-364`,
which actually starts real `SyncServer`/`SyncClient` threads
(`cbpos/infrastructure/sync_client.py`, `sync_server.py`). Both are real,
independently wired multi-terminal strategies, not a naming leftover or
half-built duplicate.

**But your confusion is completely understandable, because the page
gives you almost nothing to go on:** across the whole Network page's
~15+ fields (database host/port/user/password, terminal mode, terminal
ID, sync port, main PC address, sync interval, shared secret), exactly
**one** has a tooltip (`btn_forget_main`, line 1839). There's no summary
text anywhere distinguishing "this is for one shared database" from
"this is for syncing separate databases between terminals" — two
genuinely different, non-obvious infrastructure concepts sitting on
adjacent tabs with zero framing between them.

**Why it matters — and why this is exactly the ask you made:** you
specifically asked for tooltips/explanations on settings pages, and this
is the strongest possible example of why: a real, correctly-implemented
feature became confusing not because it's broken, but because nothing on
the page tells you what problem each tab actually solves. Worth noting
`SystemPage`'s Security tab — a few clicks away in the same file — already
does exactly what's being asked for (tooltips on every field); Network
just didn't get the same treatment.

**Suggested fix:** add a one-line explanation at the top of each of the 4
tabs (e.g. Mode/Server/Migration: "Share one database across multiple
computers on your network"; LAN Sync: "Keep separate databases on each
computer in sync automatically"), and add tooltips to the remaining ~14
untouched fields — following the exact pattern `SystemPage` already
established, not a new one.

---

### UX-105: LAN Sync tab hardcodes English strings, bypassing i18n entirely

**Screen:** Settings → Network → LAN Sync
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#335](https://github.com/HMAHD/CB-POS/issues/335)

**Not from your notes — found while reading the LAN Sync tab's labels.**
CLAUDE.md is explicit: "All user-facing text uses the translation
system. **NEVER** hardcode English strings in UI code" — this tab does
exactly that.

**Root cause (verified in code):** unlike every other tab in this file
(which route every label through `_t(...)`), LAN Sync's labels are
literal Python strings — e.g. `QLabel("Terminal Mode:")`
(`settings_pages.py:1761`) and the tab's own title, `"LAN Sync"`
(line 1880), set directly with no `_t()` call.

**Why it matters:** this is the one place in Settings where a Sinhala or
Tamil-language user would suddenly see raw English regardless of their
chosen UI language — breaking the trilingual guarantee the rest of the
app maintains, on what is otherwise a fully real, working feature.

**Suggested fix:** add the missing i18n keys to `en.json`/`si.json`/
`ta.json` and route every hardcoded label and the tab title through
`_t(...)`, matching the other 3 tabs on the same page.

---

### UX-106: Payment method cards are a 7th confirmed instance of the navy palette

**Screen:** Settings → Payments
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#346](https://github.com/HMAHD/CB-POS/issues/346) (sub-issue of [#260](https://github.com/HMAHD/CB-POS/issues/260))

**What you flagged:** "this page's payment methods show as a dark blue
color that doesn't match with system styling, fix it."

**Confirmed — and this location was actually already found via the
code-only audit that produced UX-031's decision, now confirmed directly
by your screenshot too.** `payment_methods_view.py:139` sets
`objectName("PMCard")`, styled at `dark.qss:3294-3298` with the same
`#112240` background already tracked (33 other sites use this exact
color across the app, `#0A1929` at 9, `#00BCEB` at 30+) — not a separate
or new color, the same already-decided-to-retire palette.

**Why it matters / status:** no new decision needed — this is simply one
more confirmed location for the fix already scoped in UX-031 (now 7
locations: Payables, Credit Book, Reports, Document Browser, Price
Lists, Payment Methods, plus Network's header rules noted earlier).

**Suggested fix:** include `#PMCard` in the same retirement pass as the
other 6 locations — no separate decision required, this is already
covered by the standing decision at the top of this document.

---

### UX-107: Cash's narrower button row breaks column alignment across payment method rows

**Screen:** Settings → Payments
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#336](https://github.com/HMAHD/CB-POS/issues/336)

**Not from your notes — found while checking for row-to-row
inconsistencies, per your "mark any other UI/UX issues" ask.**

**Root cause (verified in code):** Cash is the only payment method
without a Delete button — gated by `if not self.method.is_cash`
(`payment_methods_view.py:209-215`), correctly matching the footer note
"Cash method cannot be deleted." But the button group has no fixed width
or spacer reserving room for a missing third button, and the row is
right-anchored only via a stretch factor on the info column
(`layout.addLayout(info_layout, 1)`, line 170) — so Cash's narrower
2-button block still sits flush against the right margin, landing its
"Edit" button in a different horizontal position than every other row's
"Edit" button. Across 6 rows, 5 line up and 1 doesn't.

**Why it matters:** small, but a list of rows where the buttons don't
form a straight column is exactly the kind of detail that reads as
unpolished, especially on a settings page a shop owner might visit
often to toggle payment methods on/off.

**Suggested fix:** reserve a fixed-width slot for the Delete button
position on every row (rendering it disabled/hidden-but-space-reserved
for Cash) instead of omitting it from the layout entirely, so every
row's button group has identical width regardless of which buttons are
actually clickable.

---

### UX-108: Only Cash shows a shortcut/behavior tag — because only Cash was ever seeded with one

**Screen:** Settings → Payments
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#337](https://github.com/HMAHD/CB-POS/issues/337)

**Not from your notes — found while checking why only Cash has a
subtitle ("Cash · Opens Drawer · F12") and the other 5 methods don't.**

**Good news: the architecture is fine, this is a data gap, not a code
bug.** The subtitle is built generically from real per-method fields —
`is_cash`, `open_drawer`, `shortcut` — all genuine columns on the
`PaymentMethod` model (`cbpos/core/models/__init__.py:616-625`), with no
hardcoded `if method.name == "Cash"` special case anywhere
(`payment_methods_view.py:156-168`). The keyboard-shortcut mechanism is
similarly generic — `payment_dialog.py:321-328` wires a `QShortcut` for
*whichever* method has one set. It's just that seed data
(`scripts/seed.py:1640-1646`, and the fresh-install path in
`database_setup_service.py:149-154`) only ever assigns a shortcut/
drawer-open flag to Cash — Card/Credit/QR/Cheque/Transfer are seeded
with none.

**Why it matters:** a shop owner who wants a fast keyboard shortcut for
Card payments (a very plausible real want) already *can* set one via the
existing Edit dialog — the UI would render it correctly the moment it's
set — this just isn't obvious from the current screen, since it looks
like Cash is special rather than "any method can have this."

**Suggested fix:** no code change required — consider seeding one more
common default (e.g. a shortcut for Card) so the pattern is visible out
of the box, and maybe a one-line hint on the Add/Edit dialog ("Set a
keyboard shortcut and drawer-open behavior for faster checkout") so
admins know this is available for every method, not just Cash.

---

### UX-109: Cash's tag labels aren't translated in Sinhala or Tamil

**Screen:** Settings → Payments
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#338](https://github.com/HMAHD/CB-POS/issues/338)

**Not from your notes — found while checking the tag-building code from
UX-108.** `tag_cash`/`tag_opens_drawer` i18n keys are left as literal
untranslated English ("Cash"/"Opens Drawer") in both `si.json:1032-1033`
and `ta.json:1032-1033` — unlike the neighboring `status_active`/
`status_inactive` keys, which are properly localized.

**Why it matters:** a small but real gap in the trilingual guarantee —
a Sinhala or Tamil-language admin would see these two specific words in
English regardless of their chosen language.

**Suggested fix:** add real Sinhala/Tamil translations for these two
keys, matching the standard already met by their neighbors in the same
file.

---

### UX-110: Backup list loads synchronously with no loading indicator, despite the pattern already existing in the same file

**Screen:** Settings → Data Safety → Backup
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#339](https://github.com/HMAHD/CB-POS/issues/339)

**What you flagged:** "the main thing is it takes time to show — at
least show a skeleton and load the data."

**Root cause (verified in code) — and worth noting the fix pattern is
already built and used elsewhere in this exact file:**
`_refresh_backup_list` (`data_safety_view.py:152-167`) calls
`BackupService.list_backups(backup_dir)` **synchronously on the main UI
thread** — no `QThread`/worker, unlike every other operation on this
page (create backup, restore, vacuum, integrity check, export all
already use dedicated workers imported at line 42). The app's own
`LoadingOverlay` widget is used for all of those
(`self._overlay.show_loading(...)`, e.g. lines 185, 433, 587, 619) — but
it is **never called** around the backup-list scan, which runs
unguarded from `showEvent` (line 63, every time this tab becomes
visible), the Refresh button (line 144), after a backup completes
(line 197), and after Clean Old Backups (line 283).

**Why it matters:** the UI appears to freeze with zero feedback while
this scan runs — exactly the "takes time to show" you're describing —
even though the app already has the right tool for this, just not
applied here.

**Suggested fix:** wrap `_refresh_backup_list`'s call in the same
`LoadingOverlay`/worker-thread pattern already used for every other
operation on this page — this isn't a new pattern to build, just one
call site that was missed.

---

### UX-111: The 18 pre-restore backups shown are very likely a test-isolation bug leaking into a real user folder

**Screen:** Settings → Data Safety → Backup
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#340](https://github.com/HMAHD/CB-POS/issues/340)

**What you asked:** "are those really there, or does it just show
without a backup — check the functionality."

**Investigated precisely, and the honest answer is: these specific 18
files are very likely not genuine user-initiated restores, but they are
real files on disk (not a display bug) — caused by a test-isolation
defect, which is itself worth fixing.** `restore_backup()`
(`backup_service.py:98-188`) correctly creates one pre-restore snapshot
per real restore action, and the only app-level caller is
`DataSafetyView._restore_backup()` — genuinely one snapshot per actual
restore, if that were the only caller.

**But there's a second caller: the test suite.**
`tests/unit/test_backup_service.py:229` (`test_restore_backup`) calls
the same `restore_backup()`. That test mocks `Config.DATA_DIR`/`BASE_DIR`
to a temp directory — but the snapshot path is **not** derived from
`Config` at all: `backup_service.py:136` builds it from
`BackupService.get_default_backup_dir()`
(`backup_service.py:324-327`), which is **hardcoded** to
`Path.home() / "Documents" / "CB-POS-Backups"`, completely bypassing the
test's own mock. Every run of this one test writes a real
`.pre_restore.zip`, built from a tiny fabricated "database" (an ~18-byte
string), into the developer's **actual** home-directory backup folder —
exactly matching the pattern seen (many files, same day, tight time
window, all showing "0.0 MB", which is legitimate rounding of that
genuinely tiny fabricated file, not a size-computation bug).

**Why it matters:** re-running this test (or the suite) repeatedly during
development pollutes a real, production-shaped user data directory with
fake artifacts — a test-hygiene bug with a real side effect, not
something a genuine end user would ever trigger 18 times in 15 minutes.

**Suggested fix:** make `get_default_backup_dir()` (or the snapshot path
specifically) actually honor the mocked `Config` in tests — likely by
deriving the default from `Config.DATA_DIR` instead of a hardcoded
`Path.home()` call, so the test suite can never write outside its own
temp directory again.

---

### UX-112: Pre-restore backups are permanently exempt from cleanup, and have no delete option anywhere

**Screen:** Settings → Data Safety → Backup
**Severity:** P1 · **Status:** 🔴 Open
**GitHub:** [#341](https://github.com/HMAHD/CB-POS/issues/341)

**What you flagged:** "there is no option to delete a backup, rather
than 'Clean Old Backups' — give a delete option, with a user-friendly
warning."

**This is the real, production-relevant bug behind what you're seeing —
separate from UX-111's dev-environment explanation for this specific
screenshot.** `cleanup_old_backups()` (`backup_service.py:236-270`)
keeps the `keep_count` most recent **regular** backups and deletes the
rest — but explicitly excludes every pre-restore file from
consideration at all: `backup_service.py:256`,
`if ".pre_restore" not in f.name`. Combined with the fact that no
per-row delete action exists anywhere in `data_safety_view.py` (confirmed
by grep — the only deletion path in the whole file is this one bulk
method), **pre-restore snapshots can never be removed by any means
built into the app**, in any real installation, ever. Every genuine
restore a shop owner ever performs leaves behind a file that will sit on
disk forever.

**Why it matters — this is a real, unbounded-growth problem on the
app's own data-safety feature, which is exactly the kind of thing that
should be reliable:** a shop that restores from backup periodically
(recovering from a bad import, testing a migration, etc.) will
accumulate an ever-growing pile of pre-restore snapshots with no way to
ever clean them up short of manually deleting files outside the app.

**Suggested fix:** exactly what you asked for — add a per-row Delete
button with a clear confirmation warning (e.g. "This backup will be
permanently deleted and cannot be recovered — are you sure?"), and
either let it also apply to pre-restore files, or add pre-restore files
to `cleanup_old_backups()`'s own retention logic (keep the last N
pre-restore snapshots too, rather than excluding them entirely) so they
don't need manual attention to stay bounded.

---

### UX-113: Database file path is visually truncated by a QFormLayout sizing bug, not a data bug

**Screen:** Settings → Admin Tools → Database
**Severity:** P2 · **Status:** 🔴 Open
**GitHub:** [#342](https://github.com/HMAHD/CB-POS/issues/342)

**What you'd notice from the screenshot:** "Path:" shows only
`/Users/akash/` — looks like the filename itself is missing.

**Investigated and given a definitive answer: the underlying data is
correct, this is purely a display defect.** The real path is computed
correctly with the filename included —
`maintenance_service.py:101`: `db_path = Config.DATA_DIR / "cbpos.db"`,
passed through unmodified at `maintenance_service.py:135`. It's rendered
as-is, with no slicing (`admin_tools_view.py:186`:
`self.lbl_db_path.setText(info.get("path", "--"))`). The widget is a
plain `QLabel` with `setWordWrap(True)` inside a `QFormLayout`
(`admin_tools_view.py:131-135`), with no `setMinimumWidth` anywhere on
the label or its containing group — the classic `QFormLayout` +
word-wrapped-`QLabel` sizing defect, where the field column doesn't get
allocated enough width/height for the wrapped text, so only the first
line/fragment paints visibly.

**Why it matters:** this is an admin-diagnostic screen — the whole point
of showing the database file path is to let someone confirm exactly
where their data lives, which this currently fails to do.

**Suggested fix:** give `lbl_db_path` (or its containing group box) an
explicit minimum width sized to a realistic full path, or switch to a
selectable multi-line `QTextEdit`/`QPlainTextEdit` sized to its content
instead of relying on `QFormLayout`'s field-column sizing for wrapped
text.

---

### UX-114: Admin Tools' Hardware tab duplicates two test buttons already on Settings → Hardware

**Screen:** Settings → Admin Tools → Hardware
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#343](https://github.com/HMAHD/CB-POS/issues/343)

**Not from your notes — found while checking whether this tab overlaps
with the main Hardware settings page, per your "are there features that
should be here" ask.**

**Confirmed real duplication, but with a clear distinction worth
keeping:** both this tab and Settings → Hardware have a "Test Print" and
"Open Drawer"/cash-drawer-test button, both calling the exact same
`HardwareTestService` methods (`test_receipt_printer()`/
`test_cash_drawer()`). The unique value this tab actually adds is a
read-only configuration summary (printer type/path, current receipt/A4
printer, paper width) and a Barcode Scanner keystroke-timing diagnostic
that exists nowhere else. Settings → Hardware remains the only place to
actually *change* printer selection/paper width — this tab never edits
anything, it only displays and tests.

**Why it matters:** low severity — it's not wrong to be able to test
hardware from two places, but two identical buttons calling the same
method on two different screens is duplicated surface area worth
noting.

**Suggested fix:** consider whether Admin Tools' printer/drawer test
buttons should simply link over to Settings → Hardware instead of
duplicating the buttons, keeping this tab focused on its unique value
(read-only diagnostics + the scanner test).

---

### UX-115: A working database integrity-check already exists, but is never wired to any button

**Screen:** Settings → Admin Tools → Database
**Severity:** P3 · **Status:** 🔴 Open
**GitHub:** [#344](https://github.com/HMAHD/CB-POS/issues/344)

**Not from your notes — found while checking for missing industry-grade
admin features, per your explicit ask.**

**Good news: this isn't a missing feature, it's an unconnected one.**
`MaintenanceService.integrity_check()` (`maintenance_service.py:143`) is
a real, working method — it's just never called from anywhere in
`admin_tools_view.py` (confirmed by grep). Also confirmed absent from
this screen entirely: a VACUUM/optimize-database action, a combined
diagnostic-bundle export (DB info + logs + hardware info in one
shareable file for support), and a raw SQL query console — none of
these exist anywhere in the file, unlike the integrity check, which is
sitting there half-wired.

**Why it matters:** "Check Database Integrity" is exactly the kind of
button a shop owner troubleshooting a problem (or a support agent
walking them through one) would expect on this screen — and the backend
work to support it is already done.

**Suggested fix:** add a "Check Database Integrity" button on the
Database tab that calls the existing `integrity_check()` method and
shows its result — this should be one of the cheapest features to add
in this entire catalog, since the actual logic already exists and works.
