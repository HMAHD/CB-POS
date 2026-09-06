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
