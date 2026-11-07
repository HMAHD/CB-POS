# Security & Architectural Design Note: Issue #894 — Permission Catalogue Audit, Enforcement, and Guardrail

## 1. Problem Statement & Threat Model

CB POS defines a granular role-based access control (RBAC) catalogue in `cbpos.core.constants.permissions.Permissions`.
An adversarial audit revealed eight permissions defined in the catalogue without being checked anywhere in executable code:
1. `inventory.view`: Tab permission was grouped under `_EVERYONE_IN_MANAGEMENT`, allowing any management user to view inventory without `inventory.view`.
2. `inventory.delete`: A phantom permission. CB POS does not support hard-deleting products (products can only be deactivated). Exposing `inventory.delete` in the UI provides a false sense of security.
3. `inventory.edit`: Add/Edit product dialogs checked this, but CSV import (`ImportService`, `CsvImportDialog`) and Category/Unit mutations (`CategoryService`, `UnitService`, `CategoryManagerDialog`, `UnitManagerDialog`) had zero permission checks.
4. `documents.create_proforma` & `documents.convert_proforma`: Buttons and service methods in `ProformaService` and `DocumentView` had no permission checks.
5. `data_safety.maintenance`: Database vacuum and integrity check actions in `MaintenanceTabWidget` and `MaintenanceService` lacked permission gates.
6. `purchase.view`: The Purchasing tab was gated only by `_EVERYONE_IN_MANAGEMENT` rather than `purchase.view`.
7. `purchase.create_grn`: Tracked for full implementation in #896.
8. `reports.view_sales` & `reports.view_profit`: Tracked for full implementation in #880.
9. `admin.tools`: Included inappropriately in `_EVERYONE_IN_SETTINGS`, giving holders of `admin.tools` access to general shop settings while individual admin tools actions lacked explicit checks.

Threat vectors addressed:
- **T1: Catalogue pollution & false security.** Administrators configure role matrices believing actions are restricted when they are unblocked.
- **T2: Unchecked catalogue import and mutation.** A low-privilege user imports CSV product data, changing prices, stock quantities, and costs without `inventory.edit`.
- **T3: Unchecked category/unit restructuring.** Categories and units are altered or deleted by actors lacking inventory edit privileges.
- **T4: Unauthorized proforma quotation creation & conversion.** Unprivileged staff issue binding price quotations or convert proformas to cart sales without authorization.
- **T5: Maintenance abuse.** Destructive or resource-heavy database operations triggered by unauthorized users.

---

## 2. Invariants & Decision Matrix

| Permission Code | Target Decision & Enforcement Seam | UI Gate | Migration Action |
|---|---|---|---|
| `inventory.view` | In `MANAGEMENT_TAB_PERMISSIONS`: `inventory: (Permissions.INVENTORY_VIEW, Permissions.INVENTORY_EDIT)`. | Tab visibility restricted in `ManagementView` via `PermissionService.get_management_tab_permissions`. | Data migration grants `inventory.view` to all existing roles possessing `management.view`. |
| `inventory.delete` | **Removed from codebase**. Deprecated phantom permission. | Removed from `Permissions` constant and `Permissions.get_groups()`. | Alembic migration deletes `inventory.delete` from `role_permissions` and `permissions` tables. |
| `inventory.edit` | Enforced at service layer in `ImportService._import_csv`, `CategoryService` mutators (`create`, `update`, `delete`, `delete_with_descendants`, `reparent`), and `UnitService` mutators (`create`, `update`, `delete`). | Gated via `check_permission_with_override` in `InventoryView.import_csv`, `InventoryView.open_category_dialog`, `InventoryView.open_unit_manager`. Propagates `acting_user_id` into dialogs and workers. | None (existing permission). |
| `documents.create_proforma` | Enforced in `ProformaService.create_proforma` and `DocumentView.open_proforma_dialog`. | Prompt for override before opening `ProformaDialog`, passing `acting_user_id`. | None (already seeded to Admin/Manager). |
| `documents.convert_proforma` | Enforced in `ProformaService.convert_to_sale` and `DocumentView.convert_proforma`. | Prompt for override before executing conversion confirmation, passing `acting_user_id`. | None (already seeded to Admin/Manager). |
| `documents.void` | Enforced in `ProformaService.void_proforma`. | Already gated in `DocumentView.void_document`. | None (existing permission). |
| `data_safety.maintenance` | Enforced in `MaintenanceService.vacuum_database`. In `MaintenanceService.integrity_check`, accepts either `DATA_SAFETY_MAINTENANCE` OR `ADMIN_TOOLS`. | Gated in `MaintenanceTabWidget._run_vacuum` and `_run_integrity_check` with override prompt, passing `acting_user_id` to workers. | None (already seeded to Admin). |
| `purchase.view` | In `MANAGEMENT_TAB_PERMISSIONS`: `purchasing: (Permissions.PURCHASE_VIEW, Permissions.PURCHASE_EDIT, Permissions.PURCHASE_CREATE_GRN)`. | Tab visibility restricted in `ManagementView`. | Data migration grants `purchase.view` to all existing roles possessing `management.view`. |
| `admin.tools` | `_EVERYONE_IN_SETTINGS` pruned to `(SETTINGS_VIEW, ADMIN_SETTINGS)`. `admin_tools` page requires `(ADMIN_SETTINGS, ADMIN_TOOLS)`. | `SettingsView` sidebar button visibility; action handlers in `AdminToolsView` check `ADMIN_TOOLS`. | None (already seeded to Admin). |
| `reports.view_sales` / `reports.view_profit` | Tracked in #880. | Tracked in #880. | Tracked in #880. |
| `purchase.create_grn` | Tracked in #896. | Tracked in #896. | Tracked in #896. |

---

## 3. Service Layer Architecture & Fail-Closed Enforcement

### 3.1 User Resolution Protocol (Fail Closed — F-01 & F-02 Fix)

Every mutating service method accepts an explicit `acting_user_id: int | None = None` and a `system_context: bool = False`:
1. **Resolution:**
   - If `acting_user_id` is passed, resolve the actor `User` by ID.
   - If `acting_user_id` is None, fallback to `AuthService.get_current_user()`.
2. **Fail-Closed Validation:**
   - If an actor is resolved:
     - Check permission via `PermissionService.user_has_permission(actor, required_code)` (or `user_has_any_permission`).
     - If the actor lacks the required permission, raise `PermissionError(f"Permission denied: {required_code} required")`.
   - If **no actor can be resolved** (`actor is None`):
     - If `system_context is True` (explicit opt-in for internal migrations, system startups, or background scheduler tasks), allow execution.
     - Otherwise, fail closed: `raise PermissionError(f"Authentication required: {required_code} requires an active user context")`.

### 3.2 `ImportService` Enforcement

In `_import_csv(file_path, progress_callback=None, mapping=None, acting_user_id=None, system_context=False)`:
- Resolve actor and enforce `Permissions.INVENTORY_EDIT` before reading CSV content or initiating database sessions.
- In `import_products_from_csv` and `import_products_from_csv_with_progress`, accept and forward `acting_user_id` and `system_context`.

### 3.3 `CategoryService` & `UnitService` Mutators

Mutators:
- `CategoryService.create(name, parent_id=None, color=None, acting_user_id=None, system_context=False)`
- `CategoryService.update(category_id, name, parent_id=None, color=None, acting_user_id=None, system_context=False)`
- `CategoryService.delete(category_id, acting_user_id=None, system_context=False)`
- `CategoryService.delete_with_descendants(category_id, acting_user_id=None, system_context=False)`
- `CategoryService.reparent(category_id, new_parent_id, acting_user_id=None, system_context=False)`
- `UnitService.create(name, abbreviation, decimal_places=0, acting_user_id=None, system_context=False)`
- `UnitService.update(unit_id, name, abbreviation, decimal_places, acting_user_id=None, system_context=False)`
- `UnitService.delete(unit_id, acting_user_id=None, system_context=False)`
All enforce `Permissions.INVENTORY_EDIT`.

### 3.4 `ProformaService` Enforcement

- `create_proforma(items, customer_id=None, notes=None, validity_days=30, acting_user_id=None, system_context=False)`:
  Enforces `Permissions.DOCUMENTS_CREATE_PROFORMA`.
- `convert_to_sale(proforma_id, acting_user_id=None, system_context=False)`:
  Enforces `Permissions.DOCUMENTS_CONVERT_PROFORMA`.
- `void_proforma(proforma_id, reason_id=None, acting_user_id=None, system_context=False)`:
  Enforces `Permissions.DOCUMENTS_VOID` (F-06 fix).

### 3.5 `MaintenanceService` Enforcement & Privilege Realignment (F-05 Fix)

- `vacuum_database(acting_user_id=None, system_context=False)`:
  Enforces `Permissions.DATA_SAFETY_MAINTENANCE`.
- `integrity_check(acting_user_id=None, system_context=False)`:
  Enforces `Permissions.DATA_SAFETY_MAINTENANCE` OR `Permissions.ADMIN_TOOLS`. This allows diagnostic checks triggered from `AdminToolsView` by users with `admin.tools` without crashing.

---

## 4. UI Layer Integration & Override Propagation (F-02 & F-07 Fix)

### 4.1 `InventoryView` & Administration Dialogs

`CategoryManagerDialog` and `UnitManagerDialog` are strictly mutating administrative tools (they provide Create, Edit, Delete with no read-only browsing mode). Therefore, gating at launch boundary via `check_permission_with_override` is architecturally correct.
1. `import_csv()`:
   ```python
   user = check_permission_with_override(Permissions.INVENTORY_EDIT, self)
   if not user:
       return
   dialog = CsvImportDialog(self.import_service, parent=self, acting_user_id=user.id)
   if dialog.exec():
       self.load_data()
   ```
2. `CsvImportWorker`:
   Takes `acting_user_id` and passes it to `import_service.import_products_from_csv_with_progress(..., acting_user_id=self.acting_user_id)`.
3. `open_category_dialog()`:
   ```python
   user = check_permission_with_override(Permissions.INVENTORY_EDIT, self)
   if not user:
       return
   dialog = CategoryManagerDialog(parent=self, acting_user_id=user.id)
   dialog.exec()
   self.load_data()
   ```
   `CategoryManagerDialog` forwards `acting_user_id` to all `CategoryService` mutator calls.
4. `open_unit_manager()`:
   ```python
   user = check_permission_with_override(Permissions.INVENTORY_EDIT, self)
   if not user:
       return
   dialog = UnitManagerDialog(parent=self, acting_user_id=user.id)
   dialog.exec()
   ```
   `UnitManagerDialog` forwards `acting_user_id` to all `UnitService` mutator calls.

### 4.2 `DocumentView`

1. `open_proforma_dialog()`:
   ```python
   user = check_permission_with_override(Permissions.DOCUMENTS_CREATE_PROFORMA, self)
   if not user:
       return
   dialog = ProformaDialog(self, acting_user_id=user.id)
   if dialog.exec():
       self.load_documents()
   ```
2. `convert_proforma()`:
   ```python
   user = check_permission_with_override(Permissions.DOCUMENTS_CONVERT_PROFORMA, self)
   if not user:
       return
   # Confirmation prompt, then ProformaService.convert_to_sale(doc_id, acting_user_id=user.id)
   ```

### 4.3 `MaintenanceTabWidget` & `AdminToolsView`

1. `MaintenanceTabWidget._run_vacuum()`:
   Prompts `check_permission_with_override(Permissions.DATA_SAFETY_MAINTENANCE, self)`. Passes `acting_user_id` to `VacuumWorker(acting_user_id=user.id)`.
2. `MaintenanceTabWidget._run_integrity_check()`:
   Prompts `check_permission_with_override(Permissions.DATA_SAFETY_MAINTENANCE, self)`. Passes `acting_user_id` to `IntegrityCheckWorker(acting_user_id=user.id)`.
3. `AdminToolsView._check_integrity()`:
   Prompts `check_permission_with_override(Permissions.ADMIN_TOOLS, self)`. Passes `acting_user_id` to `IntegrityCheckWorker(acting_user_id=user.id)`.

---

## 5. Migration Specification (F-03 Fix)

Alembic revision `8e9f0a1b2c3d_permission_catalogue_audit.py`:

### Upgrade:
```python
def upgrade() -> None:
    conn = op.get_bind()

    # 1. Foreign-key safe deletion: delete role associations before permission row
    conn.execute(
        sa.text("""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'inventory.delete')
    """)
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'inventory.delete'"))

    # 2. Idempotent grant for roles holding management.view
    conn.execute(
        sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT DISTINCT r.id, p.id
        FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p_mgmt ON p_mgmt.id = rp.permission_id AND p_mgmt.code = 'management.view'
        CROSS JOIN permissions p
        WHERE p.code IN ('inventory.view', 'purchase.view')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp2
              WHERE rp2.role_id = r.id AND rp2.permission_id = p.id
          )
    """)
    )
```

### Downgrade:
```python
def downgrade() -> None:
    conn = op.get_bind()

    # 1. Re-insert inventory.delete
    res = conn.execute(sa.text("SELECT id FROM permissions WHERE code = 'inventory.delete'")).scalar_one_or_none()
    if not res:
        conn.execute(sa.text("INSERT INTO permissions (code) VALUES ('inventory.delete')"))
        perm_id = conn.execute(sa.text("SELECT id FROM permissions WHERE code = 'inventory.delete'")).scalar_one()
        admin_role_id = conn.execute(sa.text("SELECT id FROM roles WHERE name = 'Admin'")).scalar_one_or_none()
        if admin_role_id:
            conn.execute(
                sa.text(f"INSERT INTO role_permissions (role_id, permission_id) VALUES ({admin_role_id}, {perm_id})")
            )
```

---

## 6. AST Guardrail Architecture (F-04 Fix)

Test file: `tests/guardrails/test_permission_guardrails.py`
Method: `test_every_permission_code_is_enforced()`

1. **AST Scanner Coverage:**
   - Parse all `.py` files under `cbpos/`.
   - In `cbpos/core/constants/permissions.py`, skip ONLY the `class Permissions` definition body itself, so that `MANAGEMENT_TAB_PERMISSIONS` and `SETTINGS_PAGE_PERMISSIONS` are fully scanned.
   - Collect every attribute lookup matching `Permissions.<ATTR_NAME>`.
   - Collect any raw string constant matching a permission code string (e.g. `"inventory.edit"`), and assert that outside tests and migration files, permission references must use `Permissions.<ATTR_NAME>`.
2. **Exhaustive Attribute Verification:**
   - Retrieve all permission attributes defined on `Permissions`.
   - Temporary allow-list for tracked pending issues in this batch:
     ```python
     _ALLOW_UNREFERENCED = {
         "REPORTS_VIEW_SALES": "Tracked in #880 (Phase 5.1)",
         "REPORTS_VIEW_PROFIT": "Tracked in #880 (Phase 5.1)",
         "PURCHASE_CREATE_GRN": "Tracked in #896 (Phase 5.1)",
     }
     ```
   - Assert:
     `unreferenced = all_permission_attrs - referenced_attrs - set(_ALLOW_UNREFERENCED.keys())`
     `assert not unreferenced, f"Unreferenced permission codes found without justification: {unreferenced}"`
3. **Database Seed Parity:**
   - Verify every code in `PermissionService.DEFAULT_ROLE_PERMISSIONS` and DB seed corresponds to a valid `Permissions.<ATTR_NAME>` constant.
