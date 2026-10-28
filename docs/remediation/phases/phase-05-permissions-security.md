# Phase 5 — Permissions, Audit, Export Safety, Qt Lifecycle

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> This spec was verified against `origin/main` @ `4bcc837` on 2026-10-28. Re-verify every `file:line` before editing (§0.1 step 7).

## Phase brief

**Outcome (end state):**
- Every permission in the Permissions screen is enforced somewhere, or removed. A guardrail test keeps it that way.
- Tabs and actions are gated by their own least-privilege permissions. Nobody without Admin can make anyone (including themselves) Admin, or grow their own role.
- Every privileged path enforces the same check, whichever screen it starts from: refund, quantity reduction, GRN, CSV import, categories, reports, export, reprint.
- Secrets use a random key protected by Windows DPAPI. Exports never contain live formulas.
- Login never freezes the till. No `destroyed.connect(...)` remains outside `destroy_hooks.py`, enforced by a test.

**Depends on:** Phase 1 (AuthService split: `authenticate_pin`; the throttle). #911 reads Phase 3A's refund state. #889 uses Phase 3A's `RefundService` (if 3A isn't merged, gate the existing `process_refund` path; the check stays valid after 3A).
**Unblocks:** Phase 6 (report permissions), Phase 8 (honest Permissions screen in the docs).

### Issues

| # | Title | Sev | Size | Batch | Gate |
|---|---|---|---|---|---|
| #858 | Stock Take/Price Lists/Promotions need `admin.manage_users`; privilege escalation | high | M | 5.1 | agent |
| #894 | Eight permissions checked nowhere; CSV import/categories bypass `inventory.edit` | medium | M | 5.1 | agent |
| #880 | `reports.view_sales/view_profit` never enforced; Email/Print skip export permission | medium | S | 5.1 | agent |
| #889 | Refund from Documents skips `sales.refund` | medium | S | 5.1 | agent |
| #893 | Lowering a cart quantity skips void permission and audit | medium | S | 5.1 | agent |
| #896 | GRN commit has no permission check | medium | S | 5.1 | agent |
| #809 | Settings encryption key derived from hostname | medium | M | 5.2 | agent |
| #898 | Excel/CSV export writes formulas (injection) | medium | S | 5.2 | agent |
| #911 | Reprint prints voids/credit notes as "Cash Receipt", no permission/audit | low | M | 5.3 | agent |
| #917 | PIN login runs bcrypt per user on the UI thread | low | M | 5.4 | agent |
| #918 | Forbidden `destroyed` pattern in three places | low | S | 5.4 | decided (D12) |

### Subsystem map

**Permissions** — `cbpos/core/constants/permissions.py`:
- the `Permissions` class holds the codes (lines ~20–75);
- permission groups (~`:150`) for the Permissions dialog;
- `MANAGEMENT_TAB_PERMISSIONS` (`:157-169`, where pricelists, promotions and stock_take require `ADMIN_MANAGE_USERS`);
- `SETTINGS_PAGE_PERMISSIONS`.

Seeds:
- default role grants: `database_setup_service.py:109-123`;
- demo grants: `scripts/seed.py`.

**Checks:**
- `check_permission_with_override(code, parent) -> User | None` (`cbpos/core/utils/permission_helper.py:~40-80`) returns the authorising user, or None if cancelled or denied;
- `PermissionService.user_has_permission(user, code)`.

**Users and roles:**
- `UserService.create_user/update_user` (`user_service.py:138-198`);
- `RoleService` (`ADMIN_ROLE_NAME`, `role_service.py`);
- `PermissionService.update_role_permissions`;
- UI: `cbpos/ui/views/user_view.py:381-396`, `ui/dialogs/user_dialog.py:58-66`, and the Permissions dialog (`graft grep "class PermissionDialog"`).

**Report viewer** — `cbpos/ui/views/reports/report_viewer.py:698-760`, with report definitions in `cbpos/core/reports/definitions/*` and the registry `register_all_reports`.

**Privileged UI paths:**
- `document_view.py:903-952` (refund);
- `sales_view.py:1311-1320` (`change_line_quantity`) and `:1384-1395` (`remove_line_item`, gated);
- `purchase_view.py:862-946` (`commit_grn`; after Phase 4.3 this calls `PurchaseService.receive_goods`);
- `inventory_view.py:270-318` (Category, Unit and CSV buttons).

**Exports** — `cbpos/core/services/export_service.py:36-37,76-81` and `data_export_service.py:25-58`.

**Reprint:**
- `cbpos/ui/dialogs/receipt_reprint_dialog.py:318-348`;
- `sale_history_dialog.py:681,727-756`;
- `cbpos/core/services/sales_receipt_builder.py:251-264` (`_get_doc_title`);
- `document_view.py:794` (already blocks VOID reprint);
- `RefundReceiptBuilder` exists (`graft grep "class RefundReceiptBuilder"`).

**Secrets** — `ConfigService._get_fernet` (`config_service.py:213-235`), `_KEY_FILE`, `_SENSITIVE_KEYS` (`~:166-176`).

**Qt lifecycle** — `cbpos/core/utils/destroy_hooks.py` (`call_on_destroyed`), plus the violations at:
- `cbpos/ui/widgets/modal_dimmer.py:131,137`;
- `table_helpers.py:103-110`;
- `date_range_picker.py:151-152`.

The guardrail test file is `tests/unit/test_design_system_guardrails.py`, and the crash-shape test is `test_destroy_hooks_gc_safety.py`.

### Domain invariants

1. Every code in `Permissions` is enforced by at least one service or UI check, or listed in an explicit allow-list with a reason.
2. A privileged action has **one** service-level enforcement point. Every UI entry point to it calls `check_permission_with_override` and passes the approver's id to the service.
3. Only an Admin can grant the Admin role or change permissions of a role the actor holds.
4. Every override and every reprint is in `AuditLog`, with the approver's id.

### Batches

| Batch | Branch | Issues | Why grouped |
|---|---|---|---|
| 5.1 | `fix/p5-b1-permission-model` | #858, #894, #880, #889, #893, #896 | The permission catalogue, tab map and missing checks; one guardrail test closes them |
| 5.2 | `fix/p5-b2-secrets-spreadsheet-safety` | #809, #898 | Data-at-rest and export safety |
| 5.3 | `fix/p5-b3-reprint-truth` | #911 | Document truth plus audit |
| 5.4 | `fix/p5-b4-auth-perf-qt-lifecycle` | #917, #918 | Runtime safety |

---

## Batch 5.1 — Permission model repair

**Branch:** `fix/p5-b1-permission-model` · **Order:** #858 (tab map plus escalation), then #894 (catalogue audit and guardrail), then #880, #889, #893 and #896 (individual wiring; the guardrail from #894 goes green when all are done).

### #858 — Stock Take, Price Lists and Promotions need `admin.manage_users`, which allows privilege escalation

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** systematic-debugging → tdd → ponytail-review (security)

**Problem.** The default Manager can't open Stock Take, although the role has the stock-take permissions. The owner's only workaround is granting "manage users", which lets the Manager edit their own account to Admin and take over everything. The same applies to "manage roles": a non-admin can give their own role every permission.

**Evidence and root cause.**
- `permissions.py:166-168`: `pricelists`, `promotions` and `stock_take` all map to `(ADMIN_MANAGE_USERS,)`.
- `user_service.py:169-198` accepts any `role_id`, including Admin, from any caller with access.
- `user_dialog.py:58-66` lists all roles.
- `update_role_permissions` doesn't check the actor's own role.

**Fix design.**
1. **Tab map.**
   - `stock_take` → `(STOCK_TAKE_VIEW,)`. Inside the tab, Create needs `STOCK_TAKE_CREATE`, and Approve keeps `STOCK_TAKE_APPROVE`.
   - New codes `PRICING_MANAGE = "pricing.manage"` (Price Lists, bulk price adjust) and `PROMOTIONS_MANAGE = "promotions.manage"`. Map the tabs to them.
   - Seed both to Admin and Manager in `create_empty_database`, `scripts/seed.py` **and** an Alembic data migration that inserts the permission rows and grants them to existing roles that currently hold `admin.manage_users`, so no current user loses access.
2. **Escalation guards (service level, `UserService`):**
   - `create_user` / `update_user` take `acting_user_id`. If the target role is Admin and the actor isn't Admin, raise `ValueError("only_admin_can_grant_admin")`.
   - If `user_id == acting_user_id` and the role changes, raise `ValueError("cannot_change_own_role")`.
   - `PermissionService.update_role_permissions(role_id, codes, acting_user_id)`: if the actor isn't Admin and `role_id == actor.role_id`, raise `ValueError("cannot_edit_own_role")`. Also a non-Admin can't grant a permission they don't hold themselves: raise `ValueError("cannot_grant_unheld_permission")`.
   - The UI passes `AuthService.get_current_user().id`.
3. **UI:**
   - `UserDialog` hides the Admin role for non-Admin actors, and disables the role combo when editing yourself (tooltip).
   - The Permissions dialog disables checkboxes for permissions the actor lacks and for the actor's own role.

**Tests.**
- `test_issue_858_manager_sees_stock_take_tab`: use `MANAGEMENT_TAB_PERMISSIONS` with the seeded Manager role.
- `test_issue_858_non_admin_cannot_grant_admin_role`.
- `test_issue_858_cannot_change_own_role`.
- `test_issue_858_non_admin_cannot_edit_own_role_permissions`.
- `test_issue_858_migration_grants_pricing_to_existing_holders`.

**UI/UX.**
- Error keys:
  - `users.only_admin_can_grant_admin` "Only an Admin can give someone the Admin role."
  - `users.cannot_change_own_role` "You can't change your own role. Ask another Admin."
  - `roles.cannot_edit_own_role` "You can't change the permissions of your own role."
  - `roles.cannot_grant_unheld` "You can only give permissions that you have yourself."
- Permission labels for the new codes (`permissions.pricing_manage` "Manage price lists", `permissions.promotions_manage` "Manage promotions").
- Run the §0.7 UI gate.

**Acceptance.**
- [ ] The default Manager sees Stock Take, and approving still needs `stock_take.approve`.
- [ ] A non-Admin with `admin.manage_users` can't give anyone, including themselves, the Admin role (service test).
- [ ] A non-Admin with `admin.manage_roles` can't add permissions to their own role.

### #894 — Eight permissions are checked nowhere; CSV import and categories bypass `inventory.edit`

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail

**Root cause.** These codes have zero references outside `constants/permissions.py`:
- INVENTORY_VIEW, INVENTORY_DELETE;
- REPORTS_VIEW_SALES, REPORTS_VIEW_PROFIT;
- DOCUMENTS_CREATE_PROFORMA, DOCUMENTS_CONVERT_PROFORMA;
- DATA_SAFETY_MAINTENANCE;
- PURCHASE_VIEW, PURCHASE_CREATE_GRN;
- STOCK_TAKE_VIEW, STOCK_TAKE_CREATE;
- ADMIN_TOOLS.

`inventory_view.py:270-283` (Category, Unit) and `:312-318` (CSV import) have no check.

**Fix: decide each code, then enforce or remove it.**

| Code | Decision |
|---|---|
| `inventory.view` | Gate the Inventory tab (replace `_EVERYONE_IN_MANAGEMENT` for inventory with `(INVENTORY_VIEW, INVENTORY_EDIT)`). Data migration grants it to roles with `management.view` |
| `inventory.delete` | No delete path exists (products are deactivated). **Remove the code**, with a migration that deletes the permission row and role links |
| `inventory.edit` | Add checks to CSV import, Category manager, Unit manager and **service-level** checks in `ImportService.import_products`, `CategoryService` and `UnitService` mutators |
| `reports.view_sales` / `view_profit` | #880 |
| `documents.create_proforma` / `convert_proforma` | Wire to the proforma buttons (`graft grep "proforma" --in cbpos/ui`) and to the service methods |
| `data_safety.maintenance` | Gate the Maintenance tab's actions (vacuum, integrity) at the service (`maintenance_service.py`) and UI |
| `purchase.view` | Gate the Purchasing tab (as with inventory.view, plus a migration grant) |
| `purchase.create_grn` | #896 |
| `stock_take.view` / `create` | #858 |
| `admin.tools` | Gate the Admin Tools page/actions (it's in `_EVERYONE_IN_SETTINGS`; check every Admin Tools action requires it) |

**Guardrail test:** `tests/unit/test_permission_guardrails.py::test_every_permission_code_is_enforced`:
- AST-scan `cbpos/` (excluding `cbpos/core/constants/permissions.py`) for attribute access `Permissions.<NAME>`;
- assert every name in `Permissions` is referenced at least once, or is in `_ALLOW_UNREFERENCED = {...}` with a comment saying why;
- also assert every code in the DB seed exists in `Permissions`.

**Tests.**
- `test_issue_894_csv_import_requires_inventory_edit` (service level).
- `test_issue_894_category_create_requires_inventory_edit`.
- `test_issue_894_inventory_delete_code_removed_by_migration`.

**UI/UX.** Buttons without permission stay visible but disabled, with the tooltip `common.no_permission` "You don't have permission for this. Ask a manager." (use the existing key if one exists), or prompt for an override on click, matching how Add/Edit behave today. Be consistent. Run the §0.7 UI gate on Inventory as a cashier and as a manager.

**Acceptance.**
- [ ] A role without `inventory.edit` can't import a CSV or edit categories or units, at both service and UI.
- [ ] The guardrail test passes: every code is enforced or explicitly allow-listed.

### #880 — `reports.view_sales` / `view_profit` never enforced; Email and Print skip the export permission

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.**
- `report_viewer.py:698-716` lists every registered report.
- `:735-760` (email/print) check nothing. Only export checks `reports.export`.

**Fix.**
1. Each report definition declares `required_permission: str`:
   - profit, margin and COGS reports → `REPORTS_VIEW_PROFIT`;
   - sales, tax, cash and payment reports → `REPORTS_VIEW_SALES`;
   - stock reports → `INVENTORY_VIEW`.

   Add the attribute to the report base class, with the default `REPORTS_VIEW_SALES`.
2. `ReportService.available_reports(user)` filters by it, and the viewer lists only those.
3. `ReportService.run(report_id, params, user)` re-checks it (service enforcement). Find where the viewer runs a report and route it through this method.
4. Email and Print call `check_permission_with_override(REPORTS_EXPORT, self)` the same way Export does.
5. Scheduled auto-email reports (`scheduler_service.py`) run as the system, not a user. Leave them, but document it.

**Tests.**
- `test_issue_880_role_without_view_profit_cannot_list_or_run_pnl`.
- `test_issue_880_email_requires_export_permission` (pytest-qt with a patched override returning None, so no email is sent).

**Acceptance.**
- [ ] A role without `view_profit` can't see or run P&L.
- [ ] Emailing without export permission asks for an override.

### #889 — Refund from Management → Documents skips `sales.refund`

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.**
- `document_view.py:936` calls `TransactionService.process_refund(id, "Customer Return", current_user.id)` with no check and a fixed reason.
- The other entry points check it: `refund_dialog.py:254`, `sale_history_dialog.py:814`.

**Fix.**
- The Documents **Refund** button opens the same `RefundDialog` as the other entry points (Phase 3A's partial-refund dialog), with the sale preselected. Delete the direct `process_refund` call.
- One refund UI means one permission path, one reason prompt, and one audit format.
- Phase 3A also enforces `sales.refund` in `RefundService`, which provides defence in depth.

**Test.** pytest-qt `test_issue_889_documents_refund_opens_refund_dialog_and_checks_permission`: with a patched override returning None, no refund is created.

**Acceptance.**
- [ ] A user without `sales.refund` gets the override prompt, and cancelling it performs no refund.

### #893 — Lowering a cart line's quantity skips void permission and audit

**Severity:** medium · **Size:** S · **Gate:** agent

**Problem.** Removing a line needs void permission, but changing 10 to 1 doesn't. That's the classic way to under-ring a sale for a friend.

**Root cause.**
- `sales_view.py:1311-1320` (`change_line_quantity`) calls `update_quantity` with no check.
- `remove_line_item` (`:1384-1395`) checks `SALES_VOID`.

**Fix.**
- If `new_qty < current_qty`: `approver = check_permission_with_override(Permissions.SALES_VOID, self)`. If it returns None, abort.
- On success, the cart applies the change and the view calls a service to audit it. Make a `CartAuditService.record_line_reduction(product_id, from_qty, to_qty, user_id, approver_id)` (or reuse whatever `remove_line_item` uses to log a line void; prefer reuse), writing AuditLog `LINE_QTY_REDUCED`.
- **Exception:** a weighed item re-weighed within the same scan flow? No: keep it simple and gate every reduction. Weighed items usually come from the scale, not from manual reductions.

**Test.** pytest-qt `test_issue_893_reduce_qty_without_void_permission_cancelled`: cashier, override returns None, qty unchanged, no audit. Plus: with the override, one audit row.

**Acceptance.**
- [ ] Raising a quantity needs no approval. Lowering one asks for void permission or an override, and is logged.

### #896 — Committing a GRN has no permission check

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.**
- `purchase_view.py:862-946` (`commit_grn`) has no check.
- `PURCHASE_CREATE_GRN` is only defined.
- Supplier add, edit and deactivate are ungated.

**Fix.**
- The UI calls `check_permission_with_override(PURCHASE_CREATE_GRN, self)` before building the `GrnRequest`.
- The service checks it in `PurchaseService.receive_goods` (Phase 4.3), using the approver id passed in the request (`GrnRequest.approved_by`).
- Supplier CRUD: new code `SUPPLIERS_MANAGE = "suppliers.manage"`, seeded to Admin and Manager plus a migration grant to roles with `management.view` (so behaviour is unchanged for existing shops). Check it in `SupplierService` mutators and the UI buttons.

**Tests.**
- `test_issue_896_receive_goods_requires_permission`.
- pytest-qt `test_issue_896_commit_without_permission_prompts_override`.

**Acceptance.**
- [ ] A user without `purchase.create_grn` can't commit (override prompt shown, no GRN when cancelled).

---

## Batch 5.2 — Secret and spreadsheet safety

**Branch:** `fix/p5-b2-secrets-spreadsheet-safety`

### #809 — The settings encryption key is derived from the hostname

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** tdd → migration rules → ponytail-review (security)

**Problem.** If the key file is missing, the key used to encrypt the email password, the sync secret, the database password and the backup password is calculated from the PC name. Anyone who knows the PC name can decrypt them from `settings.json`.

**Evidence and root cause.** `config_service.py:218-231`: `seed = f"cbpos-{platform.node()}-{platform.system()}"` → `sha256` → key, which is then saved to `_KEY_FILE`.

**Fix design.**
1. **New key:** `Fernet.generate_key()` when no key file exists.
2. **Key at rest on Windows:** wrap it with DPAPI, user scope:
   - `win32crypt.CryptProtectData(key, "CB POS", None, None, None, 0)`;
   - store the base64 of the blob in `.encryption_key` with a prefix `dpapi:`;
   - unwrap with `CryptUnprotectData`.
   - Check that `pywin32` is in `pyproject.toml` dependencies for Windows (`pywin32; sys_platform == 'win32'`); add it with `uv add` if missing.
   - On other OSes, store it plain (`raw:` prefix) with `0600` permissions (`_write_restricted` already does that).
   - If DPAPI unwrap fails (different Windows user, or a restored file on a new PC), treat the key as lost and fall into #875's path: secrets become "needs re-entry" and a new key is generated. **Never** fall back to the hostname derivation for new data.
3. **One-time migration** in `ConfigService.load()`:
   - detect a legacy key: the file has no prefix, **and** it equals the hostname-derived value, **or** the file is missing and the encrypted values decrypt with the derived key;
   - decrypt every sensitive value with the legacy key, generate a new random key, re-encrypt, save the settings, and write the new key file;
   - log `INFO "Settings encryption key upgraded"`, without values;
   - a key file without a prefix that is **not** hostname-derived (an earlier random key? not possible today, but be safe) is just wrapped with DPAPI. Its value is unchanged.
4. Backup password storage (`_BACKUP_PASSWORD_FILE`) uses the same Fernet. Make sure it's re-encrypted in the migration too.

**Tests.**
- `test_issue_809_new_install_generates_random_key`: two fresh `tmp_path` dirs give different keys, and neither equals the hostname derivation.
- `test_issue_809_legacy_key_migrated_and_values_preserved`: write settings encrypted with the derived key; after load, values are readable, the key file differs, and the derived key can no longer decrypt the stored values.
- `test_issue_809_dpapi_wrap_roundtrip` (`@pytest.mark.skipif(sys.platform != "win32")`).
- `test_issue_809_dpapi_unwrap_failure_goes_to_reentry`: monkeypatch unwrap to raise.

**UI/UX.** None, unless the DPAPI failure path triggers #875's re-entry notice (reuse it). Run the §0.7 UI gate only if that notice shows.

**Do NOT.**
- Do not log keys or secrets.
- Do not keep the hostname derivation anywhere except inside the legacy-detection function, with a comment.

**Acceptance.**
- [ ] New installs generate a random key.
- [ ] Upgrades re-encrypt existing values with a new random key (one-time).
- [ ] On Windows, the key is DPAPI-wrapped.
- [ ] Tests for new-install and migration paths.

### #898 — Excel export writes text starting with "=" as live formulas

**Severity:** medium · **Size:** S · **Gate:** agent

**Root cause.** `export_service.py:36-37,76-81` and `data_export_service.py:25-58`. xlsxwriter defaults `strings_to_formulas=True`, and CSV writes raw strings.

**Fix.**
- **One helper** `cbpos/core/utils/spreadsheet_safety.py`:
  - `XLSX_WRITER_OPTIONS = {"strings_to_formulas": False, "strings_to_urls": False}`;
  - `def csv_safe(value) -> value`: for `str` values beginning with `= + - @ \t \r`, prefix `'`.
    - **Exception:** a string that parses fully as a number (e.g. "-150.00") is left alone, so negative numbers stay usable.
- Use them in every xlsx writer creation (`pd.ExcelWriter(..., engine_kwargs={"options": XLSX_WRITER_OPTIONS})` or `xlsxwriter.Workbook(path, XLSX_WRITER_OPTIONS)`) and on every CSV cell.
- Grep for all writers (`graft grep "ExcelWriter\|Workbook(\|csv.writer\|to_csv("`).
- The PDF and report exports in Phase 7 aren't affected.

**Tests.**
- `test_issue_898_xlsx_formula_text_is_string`: open the produced xlsx with `openpyxl` and assert the cell's `data_type == "s"`, or unzip and assert no `<f>` in `sheet1.xml`.
- `test_issue_898_csv_formula_text_prefixed`.
- `test_issue_898_negative_number_text_not_prefixed`.

**Acceptance.**
- [ ] A name starting with "=" exports as a string cell (no `<f>`), and the CSV cell is prefixed.

---

## Batch 5.3 — Reprint authorisation and document truth

**Branch:** `fix/p5-b3-reprint-truth`

### #911 — Reprint prints voided sales and credit notes as ordinary "Cash Receipt" duplicates

**Severity:** low · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (clarify)

**Problem.** A cashier can void a cash sale, pocket the money, then reprint the sale as a normal receipt. A refund also reprints as a "Cash Receipt" with negative amounts. Nothing records reprints.

**Evidence and root cause.**
- `sale_history_dialog.py:681` enables Reprint for every status.
- The reprint dialog (`receipt_reprint_dialog.py:318-348`) lists voids.
- `sales_receipt_builder.py:251-264` (`_get_doc_title`) ignores `payment_method == "REFUND"`.
- No reprint permission and no audit exist.
- `document_view.py:794` already blocks VOID reprints.

**Fix design.**
1. **One service:** `ReceiptReprintService.reprint(sale_id, user_id, approver_id) -> ReprintJob`. It:
   - refuses VOID sales (`ValueError("reprint_void")`);
   - chooses the builder: refund documents use `RefundReceiptBuilder` (credit-note title, original receipt number); sales use `SalesReceiptBuilder` with the `DUPLICATE` marker; partly refunded sales add a line "Part refunded — see {CN numbers}" (from Phase 3A `refund_state`);
   - writes AuditLog `REPRINT_RECEIPT` (doc number, user, approver);
   - returns the job for the peripherals port.
2. **Permission:** new `sales.reprint`, seeded to all three default roles plus a migration grant to roles with `sales.view` (or whatever cashiers have; keep current behaviour). A shop can then remove it from cashiers. All three entry points (Reprint dialog, Sale History, Documents) call `check_permission_with_override(SALES_REPRINT)` and then the service.
3. **UI:** VOID rows show a disabled Reprint with the tooltip "Voided sales can't be reprinted." The Reprint dialog's search keeps showing voids, so staff can find them, greyed out with a VOID pill.

**Tests.**
- `test_issue_911_reprint_void_refused`.
- `test_issue_911_credit_note_reprints_with_refund_title`.
- `test_issue_911_reprint_writes_audit`.
- `test_issue_911_reprint_requires_permission` (service called without permission → raises).

**UI/UX.**
- `reprint.void_blocked` "Voided sales can't be reprinted."
- `receipt.part_refunded_note` "Part refunded — see {numbers}".
- Run the §0.7 UI gate, including a printed credit-note duplicate photo ("⚠️ Verify on Windows" for the physical print).

**Acceptance.**
- [ ] Reprinting a VOID sale is blocked.
- [ ] A credit note reprints with the refund title.
- [ ] Each reprint writes an AuditLog row.

---

## Batch 5.4 — Authentication performance and Qt lifecycle guardrails

**Branch:** `fix/p5-b4-auth-perf-qt-lifecycle`

### #917 — PIN login runs one bcrypt check per user on the UI thread

**Severity:** low · **Size:** M · **Gate:** agent (decided below) · **Skills:** tdd (pytest-qt) → ponytail

**Problem.** Every wrong PIN, and every manager override, freezes the till for about 0.27 s per staff member. With 8 staff that's about 2 s of frozen screen.

**Evidence and root cause.** `auth_service.py:153-168` loops `bcrypt.checkpw` (cost 12) over all active users, called synchronously from `login_view.py:375` and `manager_override_dialog.py:63`.

**Fix (decided).** **Move PIN verification off the UI thread.** No new lookup scheme:
- Phase 1's lockout (#856) is the real protection for 4–6 digit PINs.
- A keyed lookup index would add key-sync complexity for LAN tills with no real security gain.
- Record a follow-up enhancement for a lookup index only if shops with more than 20 staff report slowness.

Implementation:
1. `cbpos/ui/workers.py`: `PinCheckWorker(QThread)` with `mode` in {"login", "authenticate", "check_own"} and the inputs. `run()` calls the matching `AuthService` method and emits `finished(result)`.

   **Important:** `AuthService.login` sets `_current_user`, a class attribute, from the worker thread. That's acceptable because the UI thread reads it only after `finished`. The worker must not touch widgets.
2. LoginView, ManagerOverrideDialog and ProfileDialog:
   - on submit, disable the PIN input, keypad and buttons, and show a small spinner or "Checking…";
   - start the worker;
   - on `finished`, re-enable and handle the result exactly as today.
   - Keep the worker as an instance attribute until `finished`, so it isn't garbage-collected.
   - Connect `finished` to bound methods. **Never** connect `destroyed` to a lambda.
3. If the dialog closes while the worker runs, ignore the result: use a generation counter, as #846 does in Phase 7.

**Tests.**
- pytest-qt `test_issue_917_login_does_not_block_ui_thread`: monkeypatch `_verify_against_hash` to sleep 0.3 s and count calls by thread. Assert zero calls on the GUI thread (`threading.current_thread() is threading.main_thread()` inside the patched function records the thread), and `qtbot.waitSignal(worker.finished)`.
- `test_issue_917_override_dialog_uses_worker`.

**UI/UX.** `login.checking` "Checking…". The keypad is disabled during the check. Run the §0.7 UI gate, with a quick video or screenshots of the checking state.

**Acceptance.**
- [ ] PIN verification never runs `checkpw` on the GUI thread (test with 10 users).

### #918 — The forbidden `destroyed` pattern in three places

**Severity:** low · **Size:** S · **Gate:** decided by **D12**: remove every forbidden hook, use `call_on_destroyed` or owner-bound callbacks, remove redundant cleanup, add a guardrail test
**Skills:** safe-refactor → tdd

**Evidence.**
- `cbpos/ui/widgets/modal_dimmer.py:131`: `target.destroyed.connect(lambda: self._on_target_destroyed(target))`.
- `:137`: `dialog.destroyed.connect(lambda: self._on_modal_hidden(dialog))`, which runs for **every modal in the app**.
- `table_helpers.py:110`: `table.destroyed.connect(_cleanup)`, which is redundant with `register_language_callback(..., owner=empty_widget)`.
- `date_range_picker.py:151-152`: `register_language_callback(self.retranslate_ui)` without `owner=`, plus `self.destroyed.connect(self._on_destroyed)`.

**Fix.**
1. Modal dimmer:
   - `call_on_destroyed(target, self._on_target_destroyed_by_id, id(target))`;
   - `call_on_destroyed(dialog, self._on_modal_hidden_by_id, id(dialog))`;
   - change the handlers to look up by `id`, and keep internal dicts keyed by `id()` so no strong reference to the widget is held;
   - read `destroy_hooks.py`'s docstring and follow its exact contract.
2. `table_helpers.py`: delete `_cleanup` and its connection.
3. `date_range_picker.py`: `register_language_callback(self.retranslate_ui, owner=self)`; delete `_on_destroyed` and its connection.
4. **Guardrail tests**, added to `tests/unit/test_design_system_guardrails.py` or a new `test_qt_lifecycle_guardrails.py`:
   - `test_no_destroyed_connect_outside_destroy_hooks`: **AST-based**, finding `Call` nodes whose func is `Attribute(attr="connect")` on `Attribute(attr="destroyed")`. A text grep would flag comments: `stock_take_view.py:329` and `action_panel.py:174` mention `destroyed.connect(` inside comments.
   - `test_every_register_language_callback_in_ui_passes_owner`: AST scan of `cbpos/ui` for calls to `register_language_callback` without an `owner` keyword.

**Tests.** The two guardrails, plus a dimmer behaviour test: showing and closing a modal still restores the dimmer state (`qtbot`).

**Acceptance.**
- [ ] No `destroyed.connect(` call outside `destroy_hooks.py` (AST test).
- [ ] Every `register_language_callback` in `cbpos/ui` passes `owner=` (AST test).

---

## Phase exit gate
- [ ] All 11 issues merged and **verified closed** with closing comments (§0.10). Epic checklists updated.
- [ ] Guardrail tests green: permission codes enforced, no forbidden `destroyed` hooks, `owner=` everywhere.
- [ ] Data migrations (new permission codes and grants, `inventory.delete` removal) tested on a seeded copy. Existing Manager users keep access to everything they had.
- [ ] Manual role walkthrough as the seeded Cashier, then Manager, then Admin: every tab and action matches the permission table in the PR.
- [ ] UI gate screenshots: disabled-with-tooltip buttons, the UserDialog for a non-admin, the "Checking…" login state, reprint blocked for a void.
- [ ] Full suite green once per batch, and `pre-commit` clean.
- [ ] PROGRESS.md updated.
