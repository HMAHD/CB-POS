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

---

## Index

| ID | Title | Screen | Severity | Status |
|----|-------|--------|----------|--------|
| [UX-001](#ux-001-empty-cart-hides-the-entire-table-including-its-header) | Empty cart hides the entire table, including its header | POS main (Sales) | P1 | 🔴 Open |
| [UX-002](#ux-002-cart-table-numeric-columns-are-inconsistently-aligned-discounted-price-format-doesnt-match-regular-one) | Cart table numeric columns are inconsistently aligned, discounted price format doesn't match regular one | POS main (Sales) | P1 | 🔴 Open |
| [UX-003](#ux-003-customer-card-and-loyalty-points-are-two-disconnected-elements) | Customer card and loyalty points are two disconnected elements | POS main (Sales), ActionPanel | P1 | 🔴 Open |
| [UX-004](#ux-004-discount-highlight-only-tints-one-cell-of-the-row) | Discount highlight only tints one cell of the row | POS main (Sales) | P2 | 🔴 Open |
| [UX-005](#ux-005-empty-cart-placeholder-is-plain-text-with-no-visual-anchor) | Empty cart placeholder is plain text with no visual anchor | POS main (Sales) | P3 | 🔴 Open |
| [UX-006](#ux-006-customer-icon-bypasses-the-centralized-icon-system-no-points-icon-registered) | Customer icon bypasses the centralized icon system; no points icon registered | `cbpos/ui/widgets/action_panel.py` | P3 | 🔴 Open |
| [UX-007](#ux-007-applied-payments-list-is-hard-capped-at-160px-so-it-scrolls-and-clips-the-boundary-rows-remove-button-instead-of-expanding) | Applied Payments list is hard-capped at 160px, so it scrolls and clips the boundary row's remove button instead of expanding | Payment dialog | P1 | 🔴 Open |
| [UX-008](#ux-008-change-quantitychange-price-on-a-cart-line-use-a-raw-native-dialog-instead-of-the-apps-own-styled-one) | "Change Quantity"/"Change Price" on a cart line use a raw native dialog instead of the app's own styled one | POS main (Sales), cart line actions | P1 | 🔴 Open |
| [UX-009](#ux-009-select-customer-dialog-cannot-be-confirmed-from-the-keyboard-at-all) | Select Customer dialog cannot be confirmed from the keyboard at all | Select Customer dialog | P1 | 🔴 Open |
| [UX-010](#ux-010-select-customer-table-truncates-real-customer-names) | Select Customer table truncates real customer names | Select Customer dialog | P1 | 🔴 Open |
| [UX-011](#ux-011-select-customer-header-alignment-doesnt-match-cell-alignment-same-pattern-as-ux-002) | Select Customer header alignment doesn't match cell alignment — same pattern as UX-002 | Select Customer dialog | P2 | 🔴 Open |
| [UX-012](#ux-012-select-customer-table-skips-3-conventions-every-other-table-in-the-app-follows) | Select Customer table skips 3 conventions every other table in the app follows | Select Customer dialog | P2 | 🔴 Open |
| [UX-013](#ux-013-periodic-reports-date-picker-calendar-popup-renders-broken-reproduced-exactly) | Periodic Reports date-picker calendar popup renders broken (reproduced exactly) | Dashboard | P1 | 🔴 Open |
| [UX-014](#ux-014-total-sales-kpi-number-appears-clipped-in-the-reported-screenshot-couldnt-reproduce-yet) | Total Sales KPI number appears clipped in the reported screenshot (couldn't reproduce yet) | Dashboard | P1 | 🔴 Open |
| [UX-015](#ux-015-both-dashboard-background-workers-swallow-errors-silently-and-leave-the-ui-stuck) | Both dashboard background workers swallow errors silently and leave the UI stuck | Dashboard | P1 | 🔴 Open |
| [UX-016](#ux-016-periodic-reports-date-range-has-no-sanity-bounds-and-isnt-remembered) | Periodic Reports date range has no sanity bounds and isn't remembered | Dashboard | P2 | 🔴 Open |
| [UX-017](#ux-017-inventory-table-truncates-product-names-third-confirmed-instance-of-the-ux-010-pattern) | Inventory table truncates product names — third confirmed instance of the UX-010 pattern | Inventory | P1 | 🔴 Open |
| [UX-018](#ux-018-three-different-numeric-input-conventions-in-the-app-one-of-them-flagged-as-broken-in-its-own-code-comment-and-still-used-for-price) | Three different numeric-input conventions in the app — one of them flagged as broken in its own code comment, and still used for Price | Product Editor + app-wide | P1 | 🔴 Open |
| [UX-019](#ux-019-label-preview-dialog-has-a-hardcoded-navy-background-that-doesnt-match-the-dark-theme) | Label Preview dialog has a hardcoded navy background that doesn't match the dark theme | Label Preview dialog | P1 | 🔴 Open |
| [UX-020](#ux-020-csv-import-dialog-floating-thumbnail-investigated-likely-not-an-app-bug) | CSV Import dialog floating thumbnail — investigated, likely not an app bug | Import CSV dialog | ⚪ N/A | ⚪ Won't Fix |
| [UX-021](#ux-021-category-manager-tree-has-no-column-resize-mode-configured-causing-a-horizontal-scrollbar-and-a-squeezed-header) | Category Manager tree has no column resize-mode configured, causing a horizontal scrollbar and a squeezed header | Category Manager dialog | P2 | 🔴 Open |
| [UX-022](#ux-022-secondarydanger-button-class-convention-is-inconsistently-applied-across-3-dialogs) | Secondary/danger button class convention is inconsistently applied across 3 dialogs | Category Manager, Unit Manager, Label Print | P3 | 🔴 Open |
| [UX-023](#ux-023-management-view-shows-a-completely-blank-screen-until-the-first-sidebar-click-confirmed-regression) | Management view shows a completely blank screen until the first sidebar click (confirmed regression) | Management (all tabs) | P1 | 🔴 Open |
| [UX-024](#ux-024-management-sidebar-gets-permanently-stuck-collapsed-across-restarts-confirmed-root-cause) | Management sidebar gets permanently stuck collapsed across restarts (confirmed root cause) | Management, `CollapsibleSidebar` | P1 | 🔴 Open |
| [UX-025](#ux-025-add-supplier-dialog-has-zero-dialog-specific-styling-no-objectname-no-size-no-qss-at-all) | Add Supplier dialog has zero dialog-specific styling — no objectName, no size, no QSS at all | Suppliers tab | P1 | 🔴 Open |
| [UX-026](#ux-026-new-grn-add-product-search-is-a-genuinely-broken-feature-not-just-unpolished) | New GRN "Add Product" search is a genuinely broken feature, not just unpolished | New GRN tab | P0 | 🔴 Open |
| [UX-027](#ux-027-new-grn-header-row-supplierrefdate-has-no-width-balancing-date-field-looks-tiny) | New GRN header row (Supplier/Ref#/Date) has no width balancing — Date field looks tiny | New GRN tab | P2 | 🔴 Open |
| [UX-028](#ux-028-supplier-selection-combos-in-purchasing-are-plain-non-searchable-comboboxes) | Supplier-selection combos in Purchasing are plain, non-searchable comboboxes | New GRN, GRN History tabs | P1 | 🔴 Open |
| [UX-029](#ux-029-grn-history-status-filter-shows-all-suppliers-instead-of-all-statuses) | GRN History "Status" filter shows "All Suppliers" instead of "All Statuses" | GRN History tab | P2 | 🔴 Open |
| [UX-030](#ux-030-grn-history-and-payables-tables-have-no-empty-state-message) | GRN History and Payables tables have no empty-state message | GRN History, Payables tabs | P2 | 🔴 Open |
| [UX-031](#ux-031-payables-uses-a-deliberate-but-undocumented-navy-sub-theme-shared-with-credit-book) | Payables uses a deliberate but undocumented navy sub-theme, shared with Credit Book | Payables tab (+ likely Credit Book) | P2 | 🔴 Open |
| [UX-032](#ux-032-payables-supplier-list-is-double-click-only-same-pattern-as-ux-009) | Payables supplier list is double-click-only — same pattern as UX-009 | Payables tab | P1 | 🔴 Open |
| [UX-033](#ux-033-payables-ledger-shows-zero-entries-despite-a-non-zero-balance-needs-one-live-check-to-fully-confirm) | Payables ledger shows zero entries despite a non-zero balance (needs one live check to fully confirm) | Payables tab | P1 | 🔴 Open |

---

## Entries

<!-- New entries are appended below this line, most recent last. -->

### UX-001: Empty cart hides the entire table, including its header

**Screen:** POS main screen (Sales view), cart area — screenshot 1 (empty cart)
**Severity:** P1 · **Status:** 🔴 Open

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
**Severity:** P0 · **Status:** 🔴 Open

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

**Screen:** Payables tab (and very likely Credit Book — not yet reviewed
directly, but built from the identical shared QSS)
**Severity:** P2 · **Status:** 🔴 Open

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

**Why it matters:** whatever the original intent, the result today is that
two specific screens look like they belong to a different app, with no
visible reason (no theme toggle, no "you're in a special mode" indicator)
— which is exactly what reads as inconsistent to a user moving between
tabs.

**Suggested fix:** this is a product decision, not a quick color swap —
either commit to the navy ledger theme and extend it deliberately (with a
name and a reason, and probably applied more broadly if it's meant to
signal "financial ledger" screens), or retire it in favor of the standard
surface colors used everywhere else. Worth deciding intentionally rather
than leaving it as an accident of history. If retired, `credit_book_view.py`
should be checked and fixed in the same pass, since it shares every rule.

---

### UX-032: Payables supplier list is double-click-only — same pattern as UX-009

**Screen:** Payables tab
**Severity:** P1 · **Status:** 🔴 Open

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
