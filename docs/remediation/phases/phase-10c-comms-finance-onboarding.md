# Phase 10C — Communication, Finance and Owner Features (former backlog)

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`, and Phase 10B's **Global rules** (they apply here too: off by default via `FeatureFlags` (#942), no extra cashier steps, invariants intact, native review of si/ta, full §0.7 UI gate).
> These are market-research features with weak direct owner evidence. **Every batch has a human go/no-go and scope confirmation** (§0.5) before work starts. Read each issue body for the user-facing design.

## Phase brief

**Outcome:**
- owners get free, offline-first communication: WhatsApp click-to-chat, own-gateway SMS, the daily summary;
- finance tools: a cheque register and quotations;
- safety and trust tools: cloud-folder backup, a customer display, the anomaly report.

None of this needs Ceylon Byte servers. The do-not-build list in #943 is binding.

**Depends on:**
- Phase 10B.0 (#942, feature flags);
- Phases 3A (payment kinds, refunds), 5 (permissions), 6 (reports), 7 (PDF and print job ids), 8 (#882 scheduler single-flight, #814 invoices, #817 privacy notice).

The privacy notice must be **updated** for every new network call (SMS gateways, WhatsApp links).

### Issues and batches

| Batch | Branch | Issue | Title | Size | Gate |
|---|---|---|---|---|---|
| 10C.1 | `feat/p10c-b1-anomaly-report` | #940 | Owner anomaly report | S | human (go) |
| 10C.2 | `feat/p10c-b2-whatsapp-click-to-chat` | #927 | WhatsApp bill and reminders (click-to-chat) | S–M | human |
| 10C.3 | `feat/p10c-b3-owner-daily-summary` | #928 | Daily summary to the owner at shift close | S | human |
| 10C.4 | `feat/p10c-b4-cheque-register` | #929 | Cheque register with PDCs and returned cheques | S–M | human |
| 10C.5 | `feat/p10c-b5-quotations` | #935 | Quotations → convert to bill | M | human |
| 10C.6 | `feat/p10c-b6-cloud-folder-backup` | #938 | Backup copy to a Drive/OneDrive folder | S | human |
| 10C.7 | `feat/p10c-b7-customer-display` | #939 | Customer display on a second monitor | S–M | human |
| 10C.8 | `feat/p10c-b8-own-sms-gateway` | #934 | SMS via the shop's own gateway | M | human |
| — | — | #943 | Parked ideas / do-not-build list | docs | owner keeps it current |
| — | — | #944 | EPIC: feature and printing backlog | — | closes when its children are closed or parked |

Order rationale: the anomaly report builds directly on the Phase 5 audit data and is cheap. WhatsApp and the summary come next (high value, no cost). Then finance features. SMS is last because it needs per-provider API work and secrets.

---

## 10C.1 — #940 Owner-only anomaly report

**Design:**
- A report definition (Phase 6 conventions: `sale_filters`, half-open ranges, `Decimal`, `required_permission = reports.view_anomalies`, a new code wired per the Phase 5 guardrail, seeded to Admin only).
- Rows by cashier × hour (or day), with these counts and values:
  - voids;
  - line removals (`LINE_VOID` audit);
  - quantity reductions (`LINE_QTY_REDUCED`, Phase 5 #893);
  - no-sale drawer opens (`NO_SALE_DRAWER_OPEN`, Phase 3B #793);
  - price overrides;
  - refunds (by `refund_documents()`);
  - manager overrides used (`OVERRIDE_AUTH`, Phase 1 #835);
  - reprints (`REPRINT_RECEIPT`, Phase 5 #911).
- **All the source events already exist** after Phases 1–5. This report only reads AuditLog plus sales. Confirm each `event_type` string with `graft grep` before writing the queries, and list them in one constant tuple.
- A highlight rule: a value is shown in warning colour when it exceeds 2× the cashier's own 30-day average. Keep it simple and explain it in the report header.
- In LAN-sync shops, the Main PC sees till audit rows because of Phase 2 #903. Add a Terminal column.

**Tests:** each event type is counted; the report is hidden without the permission.

## 10C.2 — #927 WhatsApp bill and reminders (click-to-chat)

**Design:**
- `WhatsAppLinkService.bill_link(sale_id, phone) -> str` builds `https://wa.me/94XXXXXXXXX?text=<url-encoded>`:
  - phone normalised to E.164 without the `+`; Sri Lankan mobiles `07X XXX XXXX` become `947XXXXXXXX`; anything invalid is refused with a translated message;
  - the text bill is in the **customer's language** if known, else the receipt language: shop, date, receipt number, lines (truncate past 20 lines with "+N more"), total, payment;
  - it always ends with the "Powered by CB POS · ceybyte.com" line (business requirement).
- Opened with `QDesktopServices.openUrl`. **Never** an API, never stored credentials (#943 do-not-build, item 4).
- Phone source: `Customer.phone`, or typed inline in the receipt options dialog. Offer "Save to customer" when a customer is attached.
- The same service gives `credit_reminder_link(customer_id)` (Credit Book), `po_link(purchase_order_id)` (to the supplier's phone) and `z_report_link(shift_id)` (to the owner number, from #928's setting).
- URL length: wa.me links over about 2,000 characters can fail on some clients, so cap the text and show "Send as PDF instead" (saves the PDF and opens the containing folder).
- Update `PRIVACY.md`: WhatsApp opens on the user's device, and CB POS sends nothing itself.

**Tests:** phone normalisation table; text in si/ta (fallback); the branding line is present; length cap.

## 10C.3 — #928 Daily summary to the owner

**Design:**
- Settings: owner email, owner WhatsApp number, send time (optional).
- The summary is built by one `OwnerSummaryService.build(day) -> Summary`, reusing Phase 6 report queries (no new SQL for figures that exist):
  - sales;
  - cash vs QR vs card (by `method_kind`);
  - credit given;
  - voids and refunds by cashier (#940 data);
  - low stock (Phase 6 #909 rule);
  - expiring items (if #926 is on).
- Sending:
  - email through the **Phase 8 #882 single-flight scheduler** (state, backoff, worker thread). Don't create a second scheduler;
  - WhatsApp as a prepared click-to-chat link (#927) shown at shift close with one button.
- Trigger at shift close (the Z-report flow) and optionally at the set time.

**Tests:** the summary figures equal the Daily Sales and Cash Flow figures for the same day (reconciliation); send state machine via #882's harness.

## 10C.4 — #929 Cheque register

**Design:**
- When a payment's `method_kind == CHEQUE` (Phase 3A), capture bank, cheque number and cheque date (post-dated allowed) in the payment dialog.
- A `Cheque` table: `id`, `sale_payment_id` nullable (customer cheques), `supplier_payment_id` nullable (cheques given), `bank`, `number`, `cheque_date`, `amount`, `status` (RECEIVED, DEPOSITED, CLEARED, RETURNED), `status_changed_at`, `fee`.
- **Mark returned** (permission `cheques.manage`) in one transaction:
  - the customer's debt increases by the amount, plus an optional fee, via ledger rows (`CHEQUE_RETURNED`, `CHEQUE_FEE`); ADR 0001, no clamping;
  - audit;
  - if the cheque paid a **cash-type** shift entry, nothing changes there: a cheque was never cash, because `method_kind` keeps it out of expected cash (3A).
- **Owner question:** a returned cheque from a walk-in customer (no customer record). Recommendation: require a customer for cheque payments. Show a prompt at payment: "Cheques need a customer, so a bounced cheque can be followed up."
- Screen: **Cheques** with tabs Due this week · Deposited · Cleared · Returned. Dashboard tile "N cheques due tomorrow".
- Supplier cheques: the same register, linked to supplier payments (Phase 4 supplier ledger).

**Tests:** the returned-cheque ledger equals the debt change; a walk-in cheque is refused (if the recommendation is accepted); the due list is correct across dates (half-open ranges).

## 10C.5 — #935 Quotations → bill

**Design:**
- A proforma already exists: the model at `models/__init__.py` has `ProformaInvoice` fields such as `validity_days`, `expiry_date` and `converted_sale_id`, and there is `ui/dialogs/proforma_dialog.py`. **Extend it, don't duplicate.** Rename user-facing text to "Quotation" (keep the model name), via i18n keys.
- **Save as quotation** from the cart, as an A4 PDF (Phase 7 PDF builder with shaping, branding).
- Quotation list with **Convert to bill**: load it into the cart through CartService. If current prices differ, keep the quoted price **only with** a price-override permission. Otherwise show the new prices with a notice (the same notice pattern as #804).
- Permissions `documents.create_proforma` / `convert_proforma` exist and were wired in Phase 5 #894, so reuse them.
- Send by WhatsApp (#927) or email (Phase 3B #792 email path).

**Tests:** round trip quotation → bill; price-change handling; expiry blocks conversion past `validity_days` unless overridden.

## 10C.6 — #938 Backup copy to a cloud folder

**Design:**
- Data Safety → Backup: "Also save a copy to: [folder]", which detects common folders: `%USERPROFILE%\Google Drive`, `G:\My Drive`, `%OneDrive%`.
- After a successful normal backup, copy the **already AES-encrypted** archive there, through Phase 8 #881's `ensure_writable_target`.
- Retention: keep the last N copies there (the existing `cleanup_old_backups`).
- It's a copy, so a failure is reported but doesn't fail the main backup.
- Network mode: refused, as Phase 1 #839 requires.
- Wording per the issue: "Your backup is encrypted with your backup password before it leaves this PC." It's true because Phase 1 requires a password for backups. Verify that, and refuse the copy if no password is set.

**Tests:** copy after backup; retention; a failing copy doesn't fail the backup; no copy without a password.

## 10C.7 — #939 Customer display

**Design:**
- An optional second window (`CustomerDisplayWindow`) on a chosen screen (`QGuiApplication.screens()`), frameless and full-screen. It shows:
  - the line items (last 8);
  - the total;
  - the change after payment;
  - an idle slideshow or logo;
  - the shop's **static** LankaQR image (uploaded in settings) during payment.
- It's driven by **signals from SalesView/CartService only**. No DB access in the window (MVC). It listens for cart-changed and payment-state signals.
- Theme: a high-contrast customer theme in both QSS files.
- Pole displays are out of scope (later).
- **Do NOT** integrate live LankaQR or bank APIs (#943 do-not-build, item 3).

**Tests:** the display updates on cart signals (pytest-qt); no DB imports in the module (AST check).

## 10C.8 — #934 SMS via the shop's own gateway

**Gate:** confirm the providers (text.lk, notify.lk, Dialog eSMS) and that the owner has test accounts. **Research** each provider's official API docs (current version, auth, Unicode support, error codes) and write `docs/research/sms-gateways.md` before coding.

**Design:**
- An `SmsProvider` interface with one adapter per provider: `send(to, text) -> SmsResult(ok, provider_message_id, error)`.
- API keys are stored as **sensitive settings** (Fernet + DPAPI, Phase 5 #809) and added to `_SENSITIVE_KEYS`.
- A live character and cost counter:
  - Unicode (si/ta) is 70 characters per unit (67 for multipart), GSM-7 is 160 (153);
  - the cost per unit is set by the owner in settings, defaulting to blank. **Don't hard-code prices**: the issue's Rs 0.64–0.84 is research data, not config.
- Sending happens on a worker thread and never without an explicit owner or cashier action.
- An opt-out list, `Customer.sms_opt_out`. The service refuses opted-out numbers.
- Uses: credit reminders, "order ready", promotions (bulk send requires `sms.bulk_send` permission and a confirm dialog showing the count and the estimated cost).
- Update `PRIVACY.md` with the provider names and what is sent.
- **Do NOT** resell SMS or run any server (#943 item 4).

**Tests:** encoding and unit counting tables; opt-out respected; adapter error mapping (mocked HTTP); keys never logged.

## #943 — Parked ideas / do-not-build list

This is documentation. Keep it current: when the owner parks a feature (e.g. #941 or #933), add it here with the date and reason. The **do-not-build list is binding** for all agents. Add a line to RELEASE_PLAN.md §0.3 pointing at it, if the owner agrees (Stop & Ask once).

## #944 — EPIC: feature and printing backlog

It closes when every child is closed or explicitly parked in #943 (decision recorded). Update its checklist as children close (§0.10 step 6).

---

## Phase exit gate
- [ ] Each issue is built (merged and **verified closed**) or parked by owner decision (D-number), with #943 and #944 updated.
- [ ] PRIVACY.md updated for every new external call (WhatsApp links, SMS providers, cloud folder).
- [ ] Reconciliation: the owner summary figures equal the report figures.
- [ ] UI gate screenshots for every new screen, plus a photo of the customer display on a real second monitor (⚠️ Verify on Windows).
- [ ] i18n review list submitted.
