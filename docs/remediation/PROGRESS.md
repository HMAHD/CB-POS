# Remediation Progress

Live tracker for RELEASE_PLAN.md. **Update after every issue** (§0.4 step 8) and at every merge (§0.10).

Statuses: `todo` · `in-progress` · `blocked (Q#)` · `pr-open` · `done` (merged **and** verified closed on GitHub) · `wont-fix (D#)`.

**Spec status:** start a phase only when its spec file exists and is listed as written below. If it's missing, tell the human it isn't written yet. Don't improvise a spec.

| Phase | Spec |
|---|---|
| 1 | written |
| 2 | written |
| 3A | written |
| 3B | written |
| 4 | not yet written |
| 5 | not yet written |
| 6 | not yet written |
| 7 | not yet written |
| 8 | not yet written |
| 9 | not yet written |
| 10A | not yet written |
| 10B | not yet written |
| 10C | not yet written |

## Current position

- Phase: 1 · Batch: 1.1 · Branch: — · Last session: —

## Issues

### Phase 1 — [spec](phases/phase-01-safety-auth-recovery.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #833 | "Is setup needed?" answers yes on any DB error, so "Load Demo Data" can wipe … | critical | 1.1 | todo | | |
| #791 | First-run setup wizard never appears; admin PIN from wizard is never applied … | critical | 1.1 | todo | | |
| #835 | A manager override permanently logs the manager in, so the cashier keeps all … | critical | 1.2 | todo | | |
| #857 | Duplicate PINs are accepted, so a user can log in as a different, higher-priv… | high | 1.2 | todo | | |
| #856 | The login screen has no brute-force lockout; lockout code exists only in an u… | high | 1.2 | todo | | |
| #859 | The last active Admin can be deactivated or demoted, locking everyone out of … | high | 1.2 | todo | | |
| #860 | Logout and session timeout do not log the user out of AuthService, do not clo… | high | 1.2 | todo | | |
| #837 | A database without an `alembic_version` table is stamped at head and its migr… | high | 1.3 | todo | | |
| #838 | A corrupt or empty settings.json silently becomes defaults and the next save … | high | 1.3 | todo | | |
| #875 | Restoring on a replacement PC turns the encrypted SMTP password, sync secret … | medium | 1.3 | todo | | |
| #874 | A backup from a newer app version is accepted, and the app then refuses to st… | medium | 1.3 | todo | | |
| #839 | Backup, restore and maintenance work on the local SQLite file in network (Pos… | high | 1.3 | todo | | |
| #873 | After a restore the app keeps running with stale in-memory settings that over… | medium | 1.3 | todo | | |

### Phase 2 — [spec](phases/phase-02-network-multi-terminal.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #799 | PostgreSQL Network mode has no schema-upgrade path after an app update | high | 2.1 | todo | | |
| #904 | In network mode, `Database.get_session()` retries by yielding twice, so a dro… | medium | 2.1 | todo | | |
| #800 | LAN Sync: no TLS certificate verification, so the shared secret is exposed to… | high | 2.2 | todo | | |
| #866 | A till reinstalled, restored from a backup or re-created under the same termi… | high | 2.3 | todo | | |
| #867 | Terminal IDs are not unique: the default `TERM-01` on a till makes it overwri… | high | 2.3 | todo | | |
| #868 | Any promotion with a daily time window breaks catalog sync for every till | high | 2.3 | todo | | |
| #869 | Catalog rows created on a till get ids that clash with Main PC ids, poisoning… | high | 2.3 | todo | | |
| #836 | Product edits on the Main PC never reach a till, because the catalog merge fa… | critical | 2.4 | todo | | |
| #871 | Deletions on the Main PC never reach the tills: removed promotions, price-lis… | high | 2.4 | todo | | |
| #872 | Role permissions never sync, so revoking or granting a permission on the Main… | high | 2.4 | todo | | |
| #903 | Till audit logs and inventory logs never reach the Main PC | medium | 2.4 | todo | | |
| #870 | One idle TCP connection stalls the whole Main PC sync server, before any auth… | high | 2.5 | todo | | |
| #905 | The document sequence is found by string sort, so `{seq}` breaks at 10 and `{… | medium | 2.5 | todo | | |
| #906 | A push that fails on every cycle is invisible: pending count is never set, se… | medium | 2.5 | todo | | |
| #884 | Same cashier on two terminals: both open shifts count each other's sales | medium | 2.6 | todo | | |
| #886 | Dashboard charts fail in PostgreSQL mode (SQLite-only strftime) | medium | 2.6 | todo | | |
| #914 | Network mode has no lock or unique index, so two tills can refund or void the… | low | 2.6 | todo | | |

### Phase 3A — [spec](phases/phase-03a-money-ledger-refunds.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #834 | Every cash sale with change inflates the shift's expected cash by the change … | critical | 3A.1 | todo | | |
| #850 | The shift's expected cash never subtracts cash handed back on refunds | high | 3A.1 | todo | | |
| #854 | F12 Quick Pay records the payment as "CASH", so those sales are left out of t… | high | 3A.1 | todo | | |
| #885 | Expected cash matches only a method named exactly "Cash"; ignores PaymentMeth… | medium | 3A.1 | todo | | |
| #802 | Shift summary misses "Bank Transfer" sales (expects the name "Transfer") | medium | 3A.1 | todo | | |
| #849 | Refunding a credit sale that was overpaid on credit wipes more debt than the … | high | 3A.2 | todo | | |
| #851 | Over-tender is accepted on Credit (and other non-cash) payments; the customer… | high | 3A.2 | todo | | |
| #852 | A Credit payment is charged to the first customer in the list, not the custom… | high | 3A.2 | todo | | |
| #887 | Two CREDIT lines on one sale raise the debt by both but write only one ledger… | medium | 3A.2 | todo | | |
| #888 | A balance adjustment clamps the debt at 0, which wipes store credit the shop … | medium | 3A.2 | todo | | |
| #812 | Partial / item-level refunds and returns | medium | 3A.3 | todo | | |
| #847 | You can void a sale that was already refunded, which returns its stock twice … | high | 3A.3 | todo | | |
| #848 | You can void a refund (credit note), which takes the stock back out but leave… | high | 3A.3 | todo | | |
| #915 | Refunded sales still show as "Completed" with an active Refund button; a retr… | low | 3A.3 | todo | | |

### Phase 3B — [spec](phases/phase-03b-cart-checkout-controls.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #801 | Loyalty minimum-redeem setting is ignored (config key mismatch, regression of… | medium | 3B.1 | todo | | |
| #804 | Recalled held bills lose line discounts, price overrides and notes | medium | 3B.1 | todo | | |
| #853 | A failed sale leaves the loyalty redemption on the cart, so a later walk-in s… | high | 3B.1 | todo | | |
| #892 | An unexpected error during checkout fails silently: `process_sale` returns No… | medium | 3B.1 | todo | | |
| #913 | Loyalty reversal and redemption clamp points at 0 but write the unclamped led… | low | 3B.1 | todo | | |
| #792 | "Email receipt" button crashes: EmailService.send_receipt does not exist | high | 3B.2 | todo | | |
| #793 | F8 / Ctrl+D "Open cash drawer" does nothing under default settings, and is no… | high | 3B.2 | todo | | |
| #813 | Expose bill-level discount (% or amount) in the sales screen | medium | 3B.2 | todo | | |
| #855 | Service products (is_service) cannot be sold under the default "no negative s… | high | 3B.2 | todo | | |
| #890 | A barcode scan while any modal dialog is open (e.g. Payment) is routed to the… | medium | 3B.2 | todo | | |
| #891 | A FIXED line discount survives a quantity reduction and can exceed the max-di… | medium | 3B.2 | todo | | |
| #916 | A percentage promotion leaves an unrounded unit price, so the stored unit pri… | low | 3B.2 | todo | | |

### Phase 4 — [spec](phases/phase-04-inventory-purchasing.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #794 | Ad-hoc stock adjustment is unreachable and broken; product-editor stock edits… | high | 4.1 | todo | | |
| #861 | Stock take applies a stale delta, so sales or GRNs made between "Load Product… | high | 4.1 | todo | | |
| #862 | Saving the product editor silently overwrites current stock and cost with sta… | high | 4.1 | todo | | |
| #863 | Inventory screen shows and searches only the first 1,000 products | high | 4.1 | todo | | |
| #864 | Reorder → Purchase Order is unusable on any real (non-demo) database: supplie… | high | 4.2 | todo | | |
| #865 | CSV import maps columns by substring, so "Selling Price,Cost Price" imports t… | high | 4.2 | todo | | |
| #900 | CSV import silently imports nothing for files outside the user's home folder … | medium | 4.2 | todo | | |
| #901 | CSV import accepts negative prices, costs and stock | medium | 4.2 | todo | | |
| #895 | GRN "Date" field is ignored, so back-dated supplier invoices land in the wron… | medium | 4.3 | todo | | |
| #899 | AVCO gives an inflated or wrong cost when a GRN arrives against negative stock | medium | 4.3 | todo | | |
| #902 | New GRN grid is fully editable and unvalidated (product ID, negative qty or c… | medium | 4.3 | todo | | |
| #919 | Failed GRN commit leaves an orphan DRAFT purchase (and burns a GRN number) | low | 4.3 | todo | | |
| #920 | Supplier payable adjustment clamps the balance to 0 but writes the full amoun… | low | 4.4 | todo | | |
| #921 | Categories nested under a subcategory disappear from the Category Manager | low | 4.4 | todo | | |

### Phase 5 — [spec](phases/phase-05-permissions-security.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #858 | Stock Take, Price Lists and Promotions need `admin.manage_users`, so the defa… | high | 5.1 | todo | | |
| #880 | reports.view_sales / view_profit never enforced; Email/Print skip REPORTS_EXPORT | medium | 5.1 | todo | | |
| #889 | Refund from Management → Documents skips the `sales.refund` permission check | medium | 5.1 | todo | | |
| #893 | Lowering a cart line's quantity skips the void permission and leaves no audit… | medium | 5.1 | todo | | |
| #894 | Eight permissions in the Permissions screen are checked nowhere, and CSV impo… | medium | 5.1 | todo | | |
| #896 | Committing a GRN has no permission check (purchase.create_grn is defined but … | medium | 5.1 | todo | | |
| #809 | Settings encryption key is derived from hostname when missing (predictable) | medium | 5.2 | todo | | |
| #898 | Excel export writes text cells starting with "=" as live formulas (CSV/formul… | medium | 5.2 | todo | | |
| #911 | Reprint prints voided sales and credit notes as ordinary "Cash Receipt" dupli… | low | 5.3 | todo | | |
| #917 | PIN login runs one bcrypt check per active user on the UI thread, freezing th… | low | 5.4 | todo | | |
| #918 | Three places use the segfault-prone `destroyed` pattern that CLAUDE.md forbid… | low | 5.4 | todo | | |

### Phase 6 — [spec](phases/phase-06-tax-reports.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #797 | Tax-exempt categories cannot be set from the UI; exempt split is not stored o… | high | 6.1 | todo | | |
| #810 | Tax rounding uses banker's rounding (ROUND_HALF_EVEN); VAT rate field is inte… | medium | 6.1 | todo | | |
| #831 | SSCL: not calculated for non-VAT-registered liable shops (Rs 36M threshold fr… | high | 6.1 | todo | | |
| #795 | Tax Liability Report includes voided sales and hard-codes "VAT (18%)" / "SSCL… | high | 6.2 | todo | | |
| #796 | Tax Filing Summary: period selector not wired, Total Discounts always 0, SSCL… | high | 6.2 | todo | | |
| #811 | Invoice reprint shows the current tax % next to amounts stored at the old rate | low | 6.2 | todo | | |
| #798 | Profit & Loss report uses VAT-inclusive revenue, current cost and float math | high | 6.3 | todo | | |
| #843 | Refunds never appear in the Void/Refund report | high | 6.3 | todo | | |
| #844 | Cash Flow report adds refunds back (net too high by 2× refunds) | high | 6.3 | todo | | |
| #845 | Daily Sales, Cashier Performance, Sales by Category, Dashboard and the auto-e… | high | 6.3 | todo | | |
| #883 | Overdue Customers report resets the clock on every new credit sale | medium | 6.4 | todo | | |
| #897 | "Overdue suppliers" measures days since the last ledger entry of any type, so… | medium | 6.4 | todo | | |
| #907 | The thermal customer statement shows today's debt as both opening and closing… | low | 6.4 | todo | | |
| #909 | Low Stock report and dashboard count list every service item and bundle | low | 6.4 | todo | | |
| #910 | Sales by Category and the dashboard category chart drop uncategorized products | low | 6.4 | todo | | |
| #912 | Date filters ending at 23:59:59 or "midnight − 1s" drop sales in the last sec… | low | 6.4 | todo | | |

### Phase 7 — [spec](phases/phase-07-printing-i18n-hardware.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #731 | Verify report printing from the background thread on real Windows printers | medium | 7.1 | todo | | |
| #803 | Configured A4 printer is ignored; invoices go to the Windows default printer | medium | 7.1 | todo | | |
| #876 | `_validate_name` rejects common Windows printer names and 8.3 temp paths, and… | medium | 7.1 | todo | | |
| #840 | Product labels print without a barcode, because python-escpos rejects CODE128… | high | 7.2 | todo | | |
| #877 | Sinhala/Tamil lines that the builders don't wrap (shop address, customer name… | medium | 7.2 | todo | | |
| #878 | The receipt's CODE39 invoice barcode is wider than the paper at python-escpos… | medium | 7.2 | todo | | |
| #908 | With "Merge items" on, merged receipt lines print the first line's unit price… | low | 7.2 | todo | | |
| #841 | The scanner filter counts each keystroke once per widget the key propagates t… | high | 7.3 | todo | | |
| #842 | After one reprint from Management → Documents, the hidden Document view shows… | high | 7.3 | todo | | |
| #846 | Dashboard aborts the app (SIGABRT) when re-shown while a load is still running | high | 7.3 | todo | | |
| #805 | Thermal receipts always print English item names, whatever the receipt language | medium | 7.4 | todo | | |
| #806 | Report PDF export cannot render Sinhala/Tamil (Helvetica only) | medium | 7.4 | todo | | |
| #807 | Hard-coded English: crash dialog, daily report email, and 16 missing Tamil keys | low | 7.4 | todo | | |
| #879 | The A4 tax invoice PDF is built synchronously on the UI thread inside checkout | medium | 7.4 | todo | | |

### Phase 8 — [spec](phases/phase-08-release-legal-docs.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #808 | Update check: cannot be disabled, min_version ignored, release changelog alwa… | medium | 8.1 | todo | | |
| #881 | Exports to USB / another drive refused ("Export path outside allowed director… | medium | 8.1 | todo | | |
| #882 | Auto-report email resent every minute while a send is in progress or failing | medium | 8.1 | todo | | |
| #814 | Tax invoice compliance features listed in CHANGELOG are missing (serial forma… | high | 8.2 | todo | | |
| #816 | Add About dialog and help/report-issue links (CB POS website branding) | low | 8.3 | todo | | |
| #817 | Add EULA, privacy notice and third-party licence notices before public release | high | 8.3 | todo | | |
| #818 | Fix documentation drift found in the pre-release audit | medium | 8.4 | todo | | |
| #819 | Product labels: English-only names, fake barcode in preview, no label size se… | low | 8.4 | todo | | |

### Phase 9 — [spec](phases/phase-09-warranty.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #821 | Warranty W1: Warranty policies and assignment to products and categories | — | 9.1 | todo | | |
| #822 | Warranty W2: Register a warranty per sold unit and cascade on void or refund | — | 9.2 | todo | | |
| #823 | Warranty W3: Optional serial/IMEI capture at checkout | — | 9.3 | todo | | |
| #824 | Warranty W4: Print the warranty on the receipt, the A4 invoice and a standalo… | — | 9.3 | todo | | |
| #825 | Warranty W5: Warranty lookup by receipt, serial, phone or customer | — | 9.4 | todo | | |
| #826 | Warranty W6: Warranty claims: intake, inspection, resolution and collection | — | 9.4 | todo | | |
| #827 | Warranty W7: Claim replacement and refund with correct stock movements | — | 9.5 | todo | | |
| #828 | Warranty W8: Supplier and manufacturer RMA tracking | — | 9.5 | todo | | |
| #829 | Warranty W9: Extended warranty sold as a paid add-on | — | 9.6 | todo | | |
| #830 | Warranty W10: Warranty reports, dashboard alerts and expiry reminders | — | 9.6 | todo | | |

### Phase 10A — [spec](phases/phase-10a-packaging-printing.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #815 | Installer: 32-bit install mode (Program Files (x86)), unsigned binaries, no p… | medium | 10A.? | todo | | |
| #923 | Slim the font bundle from 6.4 MB to 1.9 MB (drop italics, subset Noto Sans to… | — | 10A.? | todo | | |
| #924 | A4 invoice: real vector Sinhala/Tamil text via ReportLab shaping (uharfbuzz) … | — | 10A.? | todo | | |
| #925 | Receipt font choice: short tested list (Clear/Noto default, Compact/Yaldevi) … | — | 10A.? | todo | | |

### Phase 10B — [spec](phases/phase-10b-shop-workflows.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #926 | Expiry dates and batches, with per-batch MRP (pharmacy, grocery, bakery) | — | 10B.? | todo | | |
| #930 | Supplier returns with debit note (pairs with expiry/batch) | — | 10B.? | todo | | |
| #931 | Price board: fast daily price editing for items flagged "price changes often" | — | 10B.? | todo | | |
| #932 | Power-cut safety: autosave the in-progress bill and restore it on restart | — | 10B.? | todo | | |
| #933 | Serial/IMEI capture (phone and electronics shops), linked to the warranty epic | — | 10B.? | todo | | |
| #936 | Size/colour variants and exchange (clothing) | — | 10B.? | todo | | |
| #937 | Unit conversion: buy by box, sell by piece; ft/m/sqft for hardware | — | 10B.? | todo | | |
| #941 | Deposits and empties (gas cylinders, bottles) | — | 10B.? | todo | | |

### Phase 10C — [spec](phases/phase-10c-comms-finance-onboarding.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #927 | WhatsApp bill and reminders via click-to-chat (no API, no cost) | — | 10C.? | todo | | |
| #928 | Daily summary to the owner at shift close (email / WhatsApp text) | — | 10C.? | todo | | |
| #929 | Cheque register: post-dated cheques, due list, returned-cheque handling | — | 10C.? | todo | | |
| #934 | SMS via the shop's own gateway account (text.lk / notify.lk / Dialog eSMS) | — | 10C.? | todo | | |
| #935 | Quotations → convert to bill (hardware, computer, bookshop school lists, cake… | — | 10C.? | todo | | |
| #938 | Backup to a Google Drive / OneDrive synced folder of the user's choice | — | 10C.? | todo | | |
| #939 | Customer display on a second monitor (items, total, the shop's LankaQR image) | — | 10C.? | todo | | |
| #940 | Owner-only anomaly report: voids, deletions after print, no-sale drawer opens… | — | 10C.? | todo | | |
| #942 | Shop-type presets at first run (Grocery, Pharmacy, Hardware, Clothing, Phone,… | — | 10C.? | todo | | |
| #943 | Parked ideas and do-not-build list (market research reference) | — | 10C.? | todo | | |

### Tracking epics

| # | Title | Closes when |
|---|---|---|
| #832 | Pre-release audit: fixes required before the first public build | all audit children (#791–#819, #831) and #922 closed |
| #922 | Pre-release bug hunt: 89 verified defects (2026-10-21) | all of #833–#921 closed |
| #820 | EPIC: Product warranty and repairs (policies, per-unit warranties, cla | #821–#830 closed |
| #944 | EPIC: Feature & printing backlog (researched, not scheduled) | its children closed or explicitly parked in #943 |

## Open questions (Stop & Ask, §0.5)

| Q# | Issue | Question | Asked | Answer → D# |
|---|---|---|---|---|
| Q1 | #914 | D11's unique index on `refund_of_sale_id` would block partial refunds (D5). Replace it with row locks plus a CHECK on `sale_items.refunded_qty`? (Recommended: yes, as D16) | 2026-10-28 (plan) | |
| Q2 | #812 | Partial-refund VAT proportional to value now, switching to line-level once #797 stores the per-line taxable flag? (Recommended: yes) | 2026-10-28 (plan) | |

## Discovered during remediation (§0.9)

| Issue | Title | Sev | Found while | Phase/Batch |
|---|---|---|---|---|

## i18n review list (keys with English fallback in si/ta, §0.2)

| Key | File(s) | Why unsure |
|---|---|---|

## ⚠️ Verify on Windows

| Issue | What to verify | Result |
|---|---|---|

## Handoff

_The last session's note to the next one: what's done, what's half-done (file:function), what's next, any surprise._
