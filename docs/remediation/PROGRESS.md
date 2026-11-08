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
| 4 | written |
| 5 | written |
| 6 | written |
| 7 | written |
| 8 | written |
| 9 | written |
| 10A | written |
| 10B | written |
| 10C | written |
| U | written |

## Current position

- Phase: 5 · Batch: 5.3 · Branch: fix/p5-b3-reprint-truth · PR: #1000 · Last session: 2026-11-07

## Issues

### Phase 1 — [spec](phases/phase-01-safety-auth-recovery.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #948 | CI runs no tests or lint: every job in ci.yml is commented out | high | 1.0 | done | #977 | 972c7a4 · restored CI workflow and quarantined 11 baseline failures under D21 |
| #833 | "Is setup needed?" answers yes on any DB error, so "Load Demo Data" can wipe … | critical | 1.1 | done | #978 | 65e7356 · fail closed on DB errors and guard demo data against wiping live DB |
| #791 | First-run setup wizard never appears; admin PIN from wizard is never applied … | critical | 1.1 | done | #978 | f2b43a8 · restore first-run setup wizard and apply admin PIN |
| #835 | A manager override permanently logs the manager in, so the cashier keeps all … | critical | 1.2 | done | #979 | 5f7613c · split login and authenticate_pin, preserve cashier session |
| #857 | Duplicate PINs are accepted, so a user can log in as a different, higher-priv… | high | 1.2 | done | #979 | 77586b4 · enforce unique active PINs and require new PIN on reactivation |
| #856 | The login screen has no brute-force lockout; lockout code exists only in an u… | high | 1.2 | done | #979 | a150ed7 · terminal-scoped lockout in login_throttle with countdown UI and dialog alerts |
| #859 | The last active Admin can be deactivated or demoted, locking everyone out of … | high | 1.2 | done | #979 | c0c8da2 · guard against deactivating or demoting last active admin in UserService and UserDialog |
| #860 | Logout and session timeout do not log the user out of AuthService, do not clo… | high | 1.2 | done | #979 | c6cd353, 92b18b5 · close modal dialogs, auto-hold cart, and end AuthService session with audit on logout/timeout |
| #837 | A database without an `alembic_version` table is stamped at head and its migr… | high | 1.3 | done | #980 | 0772c71 · SchemaMigrationService fingerprinting for legacy unstamped databases |
| #838 | A corrupt or empty settings.json silently becomes defaults and the next save … | high | 1.3 | done | #980 | 884bace · quarantine corrupted settings to settings.json.corrupt-<timestamp> and atomic write |
| #875 | Restoring on a replacement PC turns the encrypted SMTP password, sync secret … | medium | 1.3 | done | #980 | 775b3a7 · clear undecryptable ciphertext secrets and prompt for re-entry |
| #874 | A backup from a newer app version is accepted, and the app then refuses to st… | medium | 1.3 | done | #980 | 85f389f · reject backups from newer schema versions with newer_version |
| #839 | Backup, restore and maintenance work on the local SQLite file in network (Pos… | high | 1.3 | done | #980 | 55bedfe · disable local backup and maintenance in network mode with informative card |
| #873 | After a restore the app keeps running with stale in-memory settings that over… | medium | 1.3 | done | #980 | de0ab2d, 3cefa15 · reload settings, freeze writes, migrate restored DB, force restart, prevent test process leaks |

### Phase 2 — [spec](phases/phase-02-network-multi-terminal.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #799 | PostgreSQL Network mode has no schema-upgrade path after an app update | high | 2.1 | done | #981 | b408f6f · ShopMeta table, advisory lock 727001, guided stepper, startup gate |
| #904 | In network mode, `Database.get_session()` retries by yielding twice, so a dro… | medium | 2.1 | done | #981 | f5d1588 · yield session once and map connection lost errors |
| #800 | LAN Sync: no TLS certificate verification, so the shared secret is exposed to… | high | 2.2 | done | #984 | 57a79ce · TLS certificate pinning, zero-token fetch, pairing dialog, fingerprint verification |
| #866 | A till reinstalled, restored from a backup or re-created under the same termi… | high | 2.3 | done | #985 | f185f3e, 4319eb8 · local identity UUID, sync_terminals, protocol 1.1, restore idempotency |
| #867 | Terminal IDs are not unique: the default `TERM-01` on a till makes it overwri… | high | 2.3 | done | #985 | dbea579 · alphanumeric terminal ID receipt prefixes (TERM01, TILL01), ID validation and release |
| #868 | Any promotion with a daily time window breaks catalog sync for every till | high | 2.3 | done | #985 | 553a194 · support time serialization in sync protocol for daily promotion windows |
| #869 | Catalog rows created on a till get ids that clash with Main PC ids, poisoning… | high | 2.3 | done | #985 | 984aab9, 4319eb8 · require_catalog_writable guard on 34 service methods, ReadOnlyBanner UI |
| #836 | Product edits on the Main PC never reach a till, because the catalog merge fa… | critical | 2.4 | done | #986 | e7b37b9 · pop version_id before merge, hold watermark on error |
| #871 | Deletions on the Main PC never reach the tills: removed promotions, price-lis… | high | 2.4 | done | #986 | e7b37b9 · sync_deletions table, reverse FK deletion order, soft-delete fallback, Admin Tools reload |
| #872 | Role permissions never sync, so revoking or granting a permission on the Main… | high | 2.4 | done | #986 | e7b37b9 · permissions before roles, permission_codes sync, roles_changed signal refreshes current user |
| #903 | Till audit logs and inventory logs never reach the Main PC | medium | 2.4 | done | #986 | e7b37b9 · synced column on inventory_logs, _FLAT_PUSH_TABLES, terminal_id filter in Activity Log UI |
| #870 | One idle TCP connection stalls the whole Main PC sync server, before any auth… | high | 2.5 | done | #987 | 6b154a8 · do_handshake_on_connect=False, per-thread handshake timeout, 16-worker throttle |
| #905 | The document sequence is found by string sort, so `{seq}` breaks at 10 and `{… | medium | 2.5 | done | #987 | 6b154a8 · numeric sequence extraction via regex scan; collision retry increments sequence |
| #906 | A push that fails on every cycle is invisible: pending count is never set, se… | medium | 2.5 | done | #987 | 6b154a8 · pending_changed signal, persistent push error state, distinct terminals count, sync details dialog with retry |
| #884 | Same cashier on two terminals: both open shifts count each other's sales | medium | 2.6 | done | #988 | 49fada0, 6e192a8 · sales.shift_id, get_shift_summary isolated by shift_id, stale banner, force-close dialog |
| #886 | Dashboard charts fail in PostgreSQL mode (SQLite-only strftime) | medium | 2.6 | done | #988 | fc72a6c, 6e192a8 · extract(month/hour) and half-open date range replacing strftime |
| #914 | Network mode has no lock or unique index, so two tills can refund or void the… | low | 2.6 | done | #988 | 8b447fd, 6e192a8 · D23: with_for_update=True on Sale in void/refund, refusing void on refunded sale |

### Phase 3A — [spec](phases/phase-03a-money-ledger-refunds.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #834 | Every cash sale with change inflates the shift's expected cash by the change … | critical | 3A.1 | done | #989 | acaac07 · `_normalise_payments`, store applied amount, tendered_amount snapshot, SalesReceiptBuilder |
| #850 | The shift's expected cash never subtracts cash handed back on refunds | high | 3A.1 | done | #991 | a36d066, ca5f632 · xfail removed; expected cash reflects cash refunds |
| #854 | F12 Quick Pay records the payment as "CASH", so those sales are left out of t… | high | 3A.1 | done | #989 | fedf9d6 · `PaymentService.get_default_cash_method()` replaces hardcoded CASH |
| #885 | Expected cash matches only a method named exactly "Cash"; ignores PaymentMeth… | medium | 3A.1 | done | #989 | c43860c · ShiftService groups by `method_kind`, counting all CASH-kind methods |
| #802 | Shift summary misses "Bank Transfer" sales (expects the name "Transfer") | medium | 3A.1 | done | #989 | c43860c · ShiftService groups by `method_kind`, unifying Transfer and Bank Transfer |
| #849 | Refunding a credit sale that was overpaid on credit wipes more debt than the … | high | 3A.2 | done | #990 | a6694ea · cap credit reversal at sale.total_amount |
| #851 | Over-tender is accepted on Credit (and other non-cash) payments; the customer… | high | 3A.2 | done | #990 | d0fec1f · clamp non-cash over-tender in dialog, reject in service |
| #852 | A Credit payment is charged to the first customer in the list, not the custom… | high | 3A.2 | done | #990 | 3ea1717 · lock to cart customer or require pick by id, propagate to SalesView |
| #887 | Two CREDIT lines on one sale raise the debt by both but write only one ledger… | medium | 3A.2 | done | #990 | 20dca8d · accumulate credit lines in `_charge_credit`, write single consolidated ledger row |
| #888 | A balance adjustment clamps the debt at 0, which wipes store credit the shop … | medium | 3A.2 | done | #990 | 52ccceb, cf2d030 · remove 0-floor on adjustments, support store credit across UI & ledger |
| #812 | Partial / item-level refunds and returns | medium | 3A.3 | done | #991 | d423766, 9f3f791, cc50ec9, 22a601a · RefundService, migration refund_lines, manager override, RefundDialog UI |
| #847 | You can void a sale that was already refunded, which returns its stock twice … | high | 3A.3 | done | #991 | 3462a50 · raise ValueError("sale_has_refund") in void_sale; points < 0 in already_reversed |
| #848 | You can void a refund (credit note), which takes the stock back out but leave… | high | 3A.3 | done | #991 | e98a0ae · raise ValueError("cannot_void_refund") on refund docs; disable Void in Document Browser |
| #915 | Refunded sales still show as "Completed" with an active Refund button; a retr… | low | 3A.3 | done | #991 | cd78fb7 · derived refund states in SaleHistory, History, DocumentBrowser; guard buttons |

### Phase 3B — [spec](phases/phase-03b-cart-checkout-controls.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #801 | Loyalty minimum-redeem setting is ignored (config key mismatch, regression of… | medium | 3B.1 | done | #992 | e043fd9, 13e3526 · LoyaltyService.min_redeem_points(), ConfigService migration |
| #804 | Recalled held bills lose line discounts, price overrides and notes | medium | 3B.1 | done | #992 | 238608c · held bill format v2, restore line overrides/discounts/notes, notice on changed price |
| #853 | A failed sale leaves the loyalty redemption on the cart, so a later walk-in s… | high | 3B.1 | done | #992 | cfd7d3f · don't mutate live cart redemption, ignore redemption if no customer |
| #892 | An unexpected error during checkout fails silently: `process_sale` returns No… | medium | 3B.1 | done | #992 | d400b8e · propagate checkout errors with logging, PaymentDialog stays open with entered payments |
| #913 | Loyalty reversal and redemption clamp points at 0 but write the unclamped led… | low | 3B.1 | done | #992 | a098dcc · remove at most current points, ledger matches actual change per ADR 0001 |
| #792 | "Email receipt" button crashes: EmailService.send_receipt does not exist | high | 3B.2 | done | #993 | b97d6dc · implement EmailService.send_receipt background worker with A4 invoice PDF and guard unconfigured SMTP |
| #793 | F8 / Ctrl+D "Open cash drawer" does nothing under default settings, and is no… | high | 3B.2 | done | #993 | f924581, 537720c · permission-gate manual open with override, audit NO_SALE_DRAWER_OPEN, support manual kick payload and classify payment methods |
| #813 | Expose bill-level discount (% or amount) in the sales screen | medium | 3B.2 | done | #993 | 9a02216, 537720c · BillDiscountDialog with Ctrl+B shortcut, persist discount on sale, display discount row on cart |
| #855 | Service products (is_service) cannot be sold under the default "no negative s… | high | 3B.2 | done | #993 | 72e899b · allow service items to sell under no negative stock setting |
| #890 | A barcode scan while any modal dialog is open (e.g. Payment) is routed to the… | medium | 3B.2 | done | #993 | 0fd40de · ignore barcode scans while modal dialog is open in ScannerFilter and SalesView |
| #891 | A FIXED line discount survives a quantity reduction and can exceed the max-di… | medium | 3B.2 | done | #993 | 5ff604b · scale fixed discounts on quantity changes and guard discount cap |
| #916 | A percentage promotion leaves an unrounded unit price, so the stored unit pri… | low | 3B.2 | done | #993 | 6849f39 · quantize final_price with round_money to reconcile stored lines |

### Phase 4 — [spec](phases/phase-04-inventory-purchasing.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #794 | Ad-hoc stock adjustment is unreachable and broken; product-editor stock edits… | high | 4.1 | done | #994 | 1d0ce36 · InventoryService.adjust_stock, StockAdjustmentDialog with make_dialog_footer, Ctrl+J and context menu in InventoryView |
| #861 | Stock take applies a stale delta, so sales or GRNs made between "Load Product… | high | 4.1 | done | #994 | bcade1e, 2c95ce8 · snapshot expected_qty on first count, enforce_non_negative=False on approve, secondary count info/tooltip |
| #862 | Saving the product editor silently overwrites current stock and cost with sta… | high | 4.1 | done | #994 | 6625cf7 · read-only stock/cost for existing products, set_cost with permission/audit, StaleProductError optimistic lock |
| #863 | Inventory screen shows and searches only the first 1,000 products | high | 4.1 | done | #994 | dfc6560 · InventoryService.list_products server-side paging & trilingual search, 300ms debounce, batch_table_update |
| #864 | Reorder → Purchase Order is unusable on any real (non-demo) database: supplie… | high | 4.2 | done | #995 | 894654f · resolve default_supplier or suppliers[0], split into POs per supplier with dialog prompt, hint unassigned items |
| #865 | CSV import maps columns by substring, so "Selling Price,Cost Price" imports t… | high | 4.2 | done | #995 | 6a10f9e · canonical alias mapping, reject duplicates, CsvImportDialog 2-step wizard with preview table |
| #900 | CSV import silently imports nothing for files outside the user's home folder … | medium | 4.2 | done | #995 | 009bd7f · support non-home file paths (USB/external), cp1252 auto-fallback, atomic batch rollback on failure |
| #901 | CSV import accepts negative prices, costs and stock | medium | 4.2 | done | #995 | afbd59a · shared ProductValidator for price/cost/stock, record OPENING stock movements on product creation |
| #895 | GRN "Date" field is ignored, so back-dated supplier invoices land in the wron… | medium | 4.3 | done | #996 | 5378a44 · pass date_received to GrnRequest, clamp date_input max to today, reject future dates |
| #899 | AVCO gives an inflated or wrong cost when a GRN arrives against negative stock | medium | 4.3 | done | #996 | 88dfc73 · Invariant 2: if old_qty <= 0 then unit_cost, else round_money weighted average |
| #902 | New GRN grid is fully editable and unvalidated (product ID, negative qty or c… | medium | 4.3 | done | #996 | a78b995 · GrnNumericDelegate for qty/cost, non-editable ID/Name/Total columns, itemChanged recalculation, remove-line action |
| #919 | Failed GRN commit leaves an orphan DRAFT purchase (and burns a GRN number) | low | 4.3 | done | #996 | c9abaef · atomic PurchaseService.receive_goods with GrnRequest, validate before service, rollback on failure |
| #920 | Supplier payable adjustment clamps the balance to 0 but writes the full amoun… | low | 4.4 | done | #997 | c59fe3a · remove 0-floor clamp on adjustments, display negative payable as supplier.credit_balance in UI |
| #921 | Categories nested under a subcategory disappear from the Category Manager | low | 4.4 | done | #997 | ca25103, 00b60da · parent combo top-level only, reject category_too_deep, migration reparents grandchildren, exit gate test |

### Phase 5 — [spec](phases/phase-05-permissions-security.md)

| # | Title | Sev | Batch | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #858 | Stock Take, Price Lists and Promotions need `admin.manage_users`, so the defa… | high | 5.1 | done | #998 | 8e4ed10 · Tab permissions (stock_take.view, pricing.manage, promotions.manage), migration, prevent non-admin privilege escalation |
| #880 | reports.view_sales / view_profit never enforced; Email/Print skip REPORTS_EXPORT | medium | 5.1 | done | #998 | 8e4ed10 · Report view permissions (view_sales, view_profit, inventory.view), service enforcement in available_reports/run, export check for Print/Email |
| #889 | Refund from Management → Documents skips the `sales.refund` permission check | medium | 5.1 | done | #998 | 8e4ed10 · Route Documents refund through shared RefundDialog flow with preselected sale and override check |
| #893 | Lowering a cart line's quantity skips the void permission and leaves no audit… | medium | 5.1 | done | #998 | 8e4ed10 · Require sales.void or override when lowering cart quantity, audit LINE_QTY_REDUCED via CartAuditService |
| #894 | Eight permissions in the Permissions screen are checked nowhere, and CSV impo… | medium | 5.1 | done | #998 | 8e4ed10 · Permission catalogue audit, remove inventory.delete, gate CSV/categories/units/proforma/maintenance, AST guardrail |
| #896 | Committing a GRN has no permission check (purchase.create_grn is defined but … | medium | 5.1 | done | #998 | 8e4ed10 · Enforce purchase.create_grn on GRN commit, add suppliers.manage and migration |
| #809 | Settings encryption key is derived from hostname when missing (predictable) | medium | 5.2 | done | #999 | e8d78e6 · Random Fernet key, DPAPI/raw protection at rest, atomic legacy migration, unwrap quarantine |
| #898 | Excel export writes text cells starting with "=" as live formulas (CSV/formul… | medium | 5.2 | done | #999 | e8d78e6 · Prevent formula injection via XLSX_WRITER_OPTIONS and csv_safe escaping |
| #911 | Reprint prints voided sales and credit notes as ordinary "Cash Receipt" dupli… | low | 5.3 | pr-open | #1000 | ReceiptReprintService, sales.reprint permission & migration, refund document receipt truth, part-refunded note, void disable & tooltip |
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
| #942 | Shop-type presets at first run (Grocery, Pharmacy, Hardware, Clothing, Phone,… | — | 10B.0 | todo | | |
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
| #943 | Parked ideas and do-not-build list (market research reference) | — | 10C.? | todo | | |

### Phase U — [spec](phases/phase-U-ui-system.md)

| # | Title | Owner | Item | Status | PR | Notes |
|---|---|---|---|---|---|---|
| #963 | DataTable + ContextMenu builder | Claude | UF-1 | todo | | needs — |
| #964 | PageHeader + DetailHeader | Claude | UF-2 | todo | | needs — |
| #965 | FormDialog | Claude | UF-3 | todo | | needs — |
| #966 | FilterBar + DateRangeFilter | Claude | UF-4 | todo | | needs — |
| #967 | Purchase Orders screen + Purchasing tabs | Gemini | UM-1 | todo | | needs UF-1, UF-3 |
| #968 | New GRN focused form | Gemini | UM-2 | todo | | needs UF-3 |
| #969 | Supplier payment dialog | Gemini | UM-3 | todo | | needs UF-3 |
| #970 | Payables list + ledger | Gemini | UM-4 | todo | | needs UF-1, UF-2 |
| #971 | Stock Control section | Gemini | UM-5 | todo | | needs UF-1 |
| #972 | Management header bar | Gemini | UM-6 | todo | | needs — |
| #973 | Dashboard date filter | Gemini | UM-7 | todo | | needs UF-4 |
| #974 | Colours out of Python UI code (+#956) | Gemini | UM-8 | todo | | needs — |
| #975 | Reports rebuild (supersedes #950) | Gemini | UM-9 | todo | | needs UF-1, UF-4 |

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
| Q1 | #914 | D11's unique index on `refund_of_sale_id` would block partial refunds (D5). Replace it with row locks plus a CHECK on `sale_items.refunded_qty`? (Recommended: yes; record as the next free D-number) | 2026-10-28 (plan) | 2026-11-04 → D23 |
| Q2 | #812 | Partial-refund VAT proportional to value now, switching to line-level once #797 stores the per-line taxable flag? (Recommended: yes) | 2026-10-28 (plan) | 2026-11-05 → D24 |
| Q3 | #817 | D8 says GPLv3 (publish source) but product notes say free + closed code. Choose GPLv3 / PyQt6 commercial licence / PySide6 migration (lawyer review) | 2026-10-28 (plan) | |
| Q4 | #831 | VAT-exempt items: SSCL on full MRP unless the category is also SSCL-exempt? (Recommended: yes, independent flags; accountant to confirm) | 2026-10-28 (plan) | |

## Discovered during remediation (§0.9)

| Issue | Title | Sev | Found while | Phase/Batch |
|---|---|---|---|---|
| #950 | Reports: Run Report wraps below filters; export labels clipped | medium | measuring the suite (2026-10-28) | U / UM-9 (superseded by the rebuild) |
| #953 | Theme callbacks never unregistered (deleted widgets called) | medium | diagnosing log noise | **done** (PR #954) |
| #956 | 8 inline setStyleSheet calls (guardrail failing on main) | low | test restructure | U / UM-8 |
| #959 | Management screens show stale data until Refresh | medium | UI review | **done** (PR #960) |
| #961 | Table column layouts lost on setModel (Suppliers squeezed) | medium | UI review | pr-open (#962) |
| #948 | CI runs no tests or lint (ci.yml fully commented out) | high | writing the remediation plan (2026-10-28) | 1 / 1.0 |

## i18n review list (keys with English fallback in si/ta, §0.2)

| Key | File(s) | Why unsure |
|---|---|---|

## ⚠️ Verify on Windows

| Issue | What to verify | Result |
|---|---|---|
| #911 | Physical thermal print of duplicate receipt (SalesReceiptBuilder & RefundReceiptBuilder duplicate markers) | pending |

## Handoff
Phase 5.2 (Secret and spreadsheet safety) is fully completed and merged (PR #999, e8d78e6). Both issues (#809, #898) are verified closed on GitHub and ticked in epic #922. Settings encryption uses random Fernet keys protected by Windows DPAPI / raw 0600 on POSIX with atomic legacy migration, and spreadsheet exports prevent formula injection. Ready to start Batch 5.3 (Reprint authorisation and document truth: #911) on branch `fix/p5-b3-reprint-truth`.

