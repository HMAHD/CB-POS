# Technical Design: Warranty Policies, Product/Category Assignment & Feature Gating (#821)

**Phase:** 9 · **Batch:** 9.1  
**Issue:** #821 (Warranty W1) · **Epic:** #820  
**Owner:** CB POS Remediation Team  
**Date:** 2026-11-12  
**Status:** APPROVED (Post-EGM & Review Fixes Applied)  

---

## 1. Context & Objectives

Epic #820 introduces end-to-end product warranty and repairs for Sri Lankan retailers selling electronics, appliances, phones, and hardware goods. 

**Batch 9.1 (#821, W1)** delivers the architectural foundation:
1. Reusable **Warranty Policies** (`WarrantyPolicy` model) specifying duration, calendar units, provider, type, remedy, terms, exclusions, and supplier coverage.
2. Explicit tri-state **Product Assignment** (`INHERIT`, `NONE`, `POLICY`) and **Category Default Policy** assignment, with strict inheritance precedence and weighted-item exclusion.
3. A deep, centralized **`WarrantyService` seam** owning feature gating, CRUD operations, fail-closed permission enforcement, validation, resolution, calendar-aware date calculation, and atomic audit logging.
4. **Feature Gating**: Disabled by default; fresh databases seed inactive templates that keep all warranty UI hidden until explicitly toggled on in Settings -> System or configured by the shop owner. Custom policies (even inactive) preserve accessibility so shop owners can reactivate them.
5. **Multi-Terminal LAN Sync**: Policy catalog synchronization (Main PC master → tills read-only), protocol bump to `1.3`, and deletion tombstone support.

Subsequent batches (#822–#830) build on this foundation without modifying W1's contracts.

---

## 2. Architecture & Domain Seam (`WarrantyService`)

Following the 10 Non-Negotiable Rules of CB POS (Part 0 §0.2):
- **UI (`cbpos/ui/**`)**: Pure display and presentation. Never queries the ORM or database directly; interacts solely through services. Prompts for manager override via `check_permission_with_override` before invoking restricted service actions.
- **Service Layer**:
  - `WarrantyService`: Deep module owning all warranty policy CRUD, validation, resolution, and calendar arithmetic.
  - Fail-closed permission checking via `_resolve_actor(acting_user_id, permission_code) -> int`: If `acting_user_id` is None, falls back to `AuthService.get_current_user()`. If no current user or user lacks permission, raises `PermissionError`. Never skips permission checks on missing actor.
  - Multi-terminal catalog write protection (`require_catalog_writable`) on all mutations.
  - Audit logging (`AuditLog`) using the resolved integer `user_id` (never None).
- **Service Mutation Boundaries**:
  - Direct assignment via `WarrantyService.set_product_warranty()` and `WarrantyService.set_category_default_warranty()`.
  - In `InventoryService.create_product()` / `update_product()` and `CategoryService.create()` / `update()`: any modification to warranty fields (`warranty_override`, `warranty_policy_id`, `default_warranty_policy_id`) enforces `warranty.edit`, validates the assignment (rejecting weighted products and rejecting *new* assignments to inactive policies), and records an atomic `WARRANTY` event in `AuditLog` within the caller's transaction.
- **Atomic Operations**: All policy and assignment mutations with their audit entries commit within a single database transaction. All mutation methods accept an optional `session` parameter to participate in outer caller transactions.

### 2.1 Service Interface (`WarrantyService`)
```python
class WarrantyService:
    @staticmethod
    def is_enabled(session: Session | None = None) -> bool:
        """Single source of truth: is warranty functionality enabled?

        Evaluates quickly:
        1. Config 'warranty_enabled' is True -> return True.
        2. Cached active status -> return True.
        3. Database check:
           - Any active policy exists (is_active == True), OR
           - Any non-template user/synced policy exists (is_template == False).

        Returns False on a fresh DB where only inactive template policies exist.
        """
        ...

    @staticmethod
    def compute_end_date(start_date: date, duration: int, unit: str) -> date:
        """Calculate inclusive coverage end date: start + duration - 1 day.

        Uses calendar-aware dateutil.relativedelta.
        Units: 'DAYS', 'MONTHS', 'YEARS'.
        """
        ...

    @staticmethod
    def resolve_policy(product: Any, session: Session | None = None) -> WarrantyPolicy | None:
        """Resolve effective warranty policy for a product.

        Precedence:
        1. Weighted products (is_weighted == True) -> None.
        2. Product explicit 'NONE' -> None (stops category inheritance).
        3. Product explicit 'POLICY' -> returns assigned policy (even if deactivated).
        4. Product 'INHERIT' (or unset):
           - Category default_warranty_policy (if active).
           - Parent category default_warranty_policy (if active).
           - None if none found.
        """
        ...

    @classmethod
    def list_policies(cls, include_inactive: bool = False, session: Session | None = None) -> list[WarrantyPolicy]:
        """List policies ordered by name. Inactive policies excluded by default."""
        ...

    @classmethod
    def get_policy(cls, policy_id: int, session: Session | None = None) -> WarrantyPolicy | None: ...

    @classmethod
    def create_policy(
        cls,
        data: dict[str, Any],
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> WarrantyPolicy:
        """Create policy. Requires warranty.manage_policies and catalog writability."""
        ...

    @classmethod
    def update_policy(
        cls,
        policy_id: int,
        data: dict[str, Any],
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> WarrantyPolicy:
        """Update policy. Requires warranty.manage_policies and catalog writability."""
        ...

    @classmethod
    def deactivate_policy(
        cls,
        policy_id: int,
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> WarrantyPolicy:
        """Deactivate policy (soft deactivation; never hard deleted once created/used)."""
        ...

    @classmethod
    def activate_policy(
        cls,
        policy_id: int,
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> WarrantyPolicy:
        """Re-activate an inactive policy."""
        ...

    @classmethod
    def set_product_warranty(
        cls,
        product_id: int,
        override: str,  # 'INHERIT' | 'NONE' | 'POLICY'
        policy_id: int | None = None,
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> Product:
        """Set product warranty assignment. Rejects weighted items."""
        ...

    @classmethod
    def set_category_default_warranty(
        cls,
        category_id: int,
        policy_id: int | None = None,
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> Category:
        """Set category default warranty policy."""
        ...
```

---

## 3. Data Model & Alembic Migration

### 3.1 Schema Definition
Current Alembic head: `d4e5f6a7b8c9` (`add_tax_invoices.py`).
New migration: `alembic/versions/e1f2a3b4c5d6_add_warranty_policies.py`.

```python
# In upgrade():
# 1. Create warranty_policies table
op.create_table(
    "warranty_policies",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("name", sa.String(length=100), nullable=False),
    sa.Column("name_si", sa.String(length=100), nullable=True),
    sa.Column("name_ta", sa.String(length=100), nullable=True),
    sa.Column("warranty_type", sa.String(length=20), nullable=False),
    sa.Column("duration", sa.Integer(), nullable=False),
    sa.Column("duration_unit", sa.String(length=10), nullable=False),
    sa.Column("remedy", sa.String(length=30), nullable=False),
    sa.Column("provider_name", sa.String(length=100), nullable=True),
    sa.Column("terms_text", sa.Text(), nullable=True),
    sa.Column("terms_text_si", sa.Text(), nullable=True),
    sa.Column("terms_text_ta", sa.Text(), nullable=True),
    sa.Column("exclusions_text", sa.Text(), nullable=True),
    sa.Column("exclusions_text_si", sa.Text(), nullable=True),
    sa.Column("exclusions_text_ta", sa.Text(), nullable=True),
    sa.Column("supplier_cover_months", sa.Integer(), server_default="0", nullable=False),
    sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
    sa.Column("is_template", sa.Boolean(), server_default="0", nullable=False),
    sa.Column("synced", sa.Boolean(), server_default="0", nullable=False),
    sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("last_modified", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("duration > 0", name="ck_warranty_policy_duration"),
    sa.CheckConstraint("duration_unit IN ('DAYS', 'MONTHS', 'YEARS')", name="ck_warranty_policy_unit"),
    sa.CheckConstraint("warranty_type IN ('SHOP', 'MANUFACTURER', 'EXTENDED')", name="ck_warranty_policy_type"),
    sa.CheckConstraint(
        "remedy IN ('REPAIR_OR_REPLACE', 'REPAIR_ONLY', 'REPLACE_ONLY', 'REFUND')", name="ck_warranty_policy_remedy"
    ),
    sa.CheckConstraint("supplier_cover_months >= 0", name="ck_warranty_policy_supplier_cover_months"),
    sa.PrimaryKeyConstraint("id"),
)
op.create_index("ix_warranty_policies_active", "warranty_policies", ["is_active"])
op.create_index("ix_warranty_policies_last_modified", "warranty_policies", ["last_modified"])

# 2. Alter categories (batch mode for SQLite)
with op.batch_alter_table("categories") as batch_op:
    batch_op.add_column(sa.Column("default_warranty_policy_id", sa.Integer(), nullable=True))
    batch_op.create_foreign_key(
        "fk_categories_default_warranty_policy_id", "warranty_policies", ["default_warranty_policy_id"], ["id"]
    )
    batch_op.create_index("ix_categories_default_warranty_policy_id", ["default_warranty_policy_id"])

# 3. Alter products (batch mode for SQLite)
with op.batch_alter_table("products") as batch_op:
    batch_op.add_column(sa.Column("warranty_policy_id", sa.Integer(), nullable=True))
    batch_op.add_column(sa.Column("warranty_override", sa.String(length=10), server_default="INHERIT", nullable=False))
    batch_op.add_column(sa.Column("serial_mode", sa.String(length=10), server_default="OFF", nullable=False))
    batch_op.create_foreign_key("fk_products_warranty_policy_id", "warranty_policies", ["warranty_policy_id"], ["id"])
    batch_op.create_index("ix_products_warranty_policy_id", ["warranty_policy_id"])
    batch_op.create_check_constraint(
        "ck_products_warranty_override",
        "warranty_override IN ('INHERIT', 'NONE', 'POLICY')",
    )
    batch_op.create_check_constraint(
        "ck_products_serial_mode",
        "serial_mode IN ('OFF', 'OPTIONAL', 'REQUIRED')",
    )
    batch_op.create_check_constraint(
        "ck_products_warranty_policy_coherence",
        "(warranty_override = 'POLICY' AND warranty_policy_id IS NOT NULL) OR (warranty_override != 'POLICY' AND warranty_policy_id IS NULL)",
    )

# 4. Seed new permissions for existing installations (Rule 8)
permissions_table = sa.table(
    "permissions",
    sa.column("code", sa.String),
    sa.column("description", sa.String),
    sa.column("group", sa.String),
)
op.bulk_insert(
    permissions_table,
    [
        {"code": "warranty.view", "description": "View Warranty Policies", "group": "Warranty"},
        {"code": "warranty.edit", "description": "Assign Warranty Policies", "group": "Warranty"},
        {"code": "warranty.manage_policies", "description": "Manage Warranty Policies", "group": "Warranty"},
    ],
)
```

### 3.2 Rollback / Downgrade Plan
- Downgrade removes referencing grants from `role_permissions` before deleting the 3 permissions from `permissions` (`DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN (...))`).
- Downgrade deletes the 3 seeded permissions from `permissions` table (`DELETE FROM permissions WHERE code IN (...)`).
- Removes columns `warranty_policy_id`, `warranty_override`, `serial_mode` and check constraints from `products` via `batch_alter_table`.
- Removes `default_warranty_policy_id` from `categories` via `batch_alter_table`.
- Drops table `warranty_policies`.

---

## 4. Policy Inheritance, Templates & Date Rules

### 4.1 Inactive Default Templates (Clean Baseline)
In `DatabaseSetupService` and `scripts/seed.py`, 4 standard templates are seeded:
1. **7 days shop replacement**:
   - `warranty_type`: `SHOP`, `duration`: 7, `duration_unit`: `DAYS`, `remedy`: `REPLACE_ONLY`, `is_active`: False, `is_template`: True.
2. **6 months shop warranty**:
   - `warranty_type`: `SHOP`, `duration`: 6, `duration_unit`: `MONTHS`, `remedy`: `REPAIR_OR_REPLACE`, `is_active`: False, `is_template`: True.
3. **1 year shop warranty**:
   - `warranty_type`: `SHOP`, `duration`: 1, `duration_unit`: `YEARS`, `remedy`: `REPAIR_OR_REPLACE`, `is_active`: False, `is_template`: True.
4. **1 year manufacturer warranty**:
   - `warranty_type`: `MANUFACTURER`, `duration`: 1, `duration_unit`: `YEARS`, `remedy`: `REPAIR_OR_REPLACE`, `is_active`: False, `is_template`: True.

**Legal Caution & Root Fix H (NEW-1)**: To avoid seeding unverified legal commitments before legal counsel review, prewritten legal terms and exclusions are stripped from these default templates (`terms_text=None, exclusions_text=None`). Merchants enter their own terms or use standard store receipts.

In a fresh database, all 4 templates have `is_active = False` and `is_template = True`, guaranteeing `WarrantyService.is_enabled()` evaluates to `False`.

### 4.2 Tri-State Product Assignment
To eliminate ambiguity between "not configured" and "intentionally no warranty":
- `INHERIT`: Resolves from Category default (or parent category). Default for all products.
- `NONE`: Explicitly blocks warranty coverage. Even if the category has a 2-year warranty, this product receives None.
- `POLICY`: Explicitly binds to `warranty_policy_id`. Coherence constraint strictly requires `warranty_policy_id IS NOT NULL` when override is `POLICY`, and `NULL` otherwise.

### 4.3 Deactivation Semantics & Assignment Preservation
- Deactivated policies (`is_active = False`) are hidden from selection dropdowns for new assignments.
- Attempting a *new* assignment of an inactive policy raises `ValueError`.
- Products and categories already assigned to a deactivated policy retain their assignment and display as `"<Policy Name> (inactive)"`.
- Resolving a product with an inactive assigned policy returns that policy so existing stock/warranties remain truthful. Category inheritance will never silently replace an explicitly assigned inactive policy.
- **W2 Owner Gate (Comments 3 & 33)**: In W1, policy resolution preserves explicit facts. In W2 (#822), an owner decision gate will determine checkout behavior for items referencing inactive policies (e.g. prompt cashier vs fail).

### 4.4 Validation Rules
- English Name (`name`) is mandatory. Sinhala and Tamil names fall back to English if omitted.
- Duration must be a positive integer (`> 0`).
- Supplier cover months must be non-negative (`>= 0`).
- If Sinhala or Tamil terms/exclusions are entered, the English source must also be present.
- Weighted products (`is_weighted == True`) cannot be assigned a warranty policy; validation raises `ValueError` with clear localized guidance.
- Policies cannot be hard-deleted once created or referenced; deactivation is the only supported archival method. Re-activation is supported via `activate_policy()`.

### 4.5 Date Arithmetic
Inclusive coverage end date formula:
$$\text{EndDate} = \text{StartDate} + \text{relativedelta}(\text{unit}=\text{duration}) - 1\text{ day}$$
Examples:
- 12 Months from `2026-10-21` $\rightarrow$ `2027-10-20`.
- 1 Month from `2026-01-31` $\rightarrow$ `2026-02-27` (`date(2026, 1, 31) + relativedelta(months=1)` clamps to `2026-02-28`; minus 1 day = `2026-02-27`).
- 1 Year from leap day `2024-02-29` $\rightarrow$ `2025-02-27` (`date(2024, 2, 29) + relativedelta(years=1)` gives `2025-02-28`; minus 1 day = `2025-02-27`).
- 7 Days from `2026-10-21` $\rightarrow$ `2026-10-27`.

Direct dependency `python-dateutil` is pinned in `pyproject.toml`.

---

## 5. Permissions, Security & Audit

### 5.1 Permissions Added
In `cbpos/core/constants/permissions.py`:
- `Permissions.WARRANTY_VIEW = "warranty.view"`: View warranty policies, list, and status.
- `Permissions.WARRANTY_EDIT = "warranty.edit"`: Assign policies to products and categories.
- `Permissions.WARRANTY_MANAGE_POLICIES = "warranty.manage_policies"`: Create, edit, and deactivate policies.

Group `"Warranty"` registered in `Permissions.get_groups()`.  
`"warranty"` tab added to `MANAGEMENT_TAB_PERMISSIONS = (Permissions.WARRANTY_VIEW, Permissions.WARRANTY_EDIT, Permissions.WARRANTY_MANAGE_POLICIES)`.  
Default seeds:
- `Admin`: All permissions.
- `Manager`: Added `"Warranty"` to `manager_groups`.
- `Cashier`: No policy management permissions in W1.

Enforcement boundary:
- UI triggers `check_permission_with_override` before restricted operations.
- Fail-Closed Actor Resolution (`_resolve_actor(acting_user_id, permission_code) -> int`):
  - If `acting_user_id` is passed: check `PermissionService.user_has_permission(acting_user, permission_code)`.
  - If `acting_user_id` is None: fall back to `AuthService.get_current_user()`. If authenticated and has permission, resolve actor ID.
  - If no actor or unauthorized: raise `PermissionError`. Missing actor never bypasses authorization.
- `AuditLog(user_id=actor_id)` always receives the resolved integer actor ID (never None).
- **Service Mutation Boundaries (Root Fix B & Root Fix I / NEW-2)**:
  - Direct assignment via `WarrantyService.set_product_warranty()` and `WarrantyService.set_category_default_warranty()`.
  - When mutating products in `InventoryService.create_product()` / `update_product()` or categories in `CategoryService.create()` / `update()`: modifying warranty fields checks `warranty.edit` via `_resolve_actor`, validates the assignment (rejects weighted items; rejects *new* assignments to inactive policies), and creates an atomic `WARRANTY` event in `AuditLog` within the caller transaction. Category warranty assignment fails closed immediately if actor is unauthenticated.

### 5.2 Activity Audit Logging
In `cbpos/core/constants/audit.py`:
- `WARRANTY_EVENT = "WARRANTY"`
Actions logged atomically with mutations:
- `CREATE_POLICY`: `{id, name, duration, unit, type, remedy}`
- `UPDATE_POLICY`: `{id, changed_fields}`
- `DEACTIVATE_POLICY`: `{id, name}`
- `ACTIVATE_POLICY`: `{id, name}`
- `PRODUCT_WARRANTY_ASSIGNMENT`: `{product_id, override, policy_id}`
- `CATEGORY_DEFAULT_WARRANTY`: `{category_id, policy_id}`

---

## 6. Multi-Terminal LAN Sync Protocol

1. **Protocol Version Bump**:
   - `SYNC_PROTOCOL_VERSION` bumped from `"1.2"` to `"1.3"` in `cbpos/core/services/sync_protocol.py`.
2. **Catalog Table Ordering**:
   - `CATALOG_TABLES`: Insert `"warranty_policies"` before `"categories"` and `"products"`.
   - `CATALOG_DELETION_ORDER`: Insert `"warranty_policies"` after `"categories"`.
3. **Model Mapping**:
   - `_TABLE_MODEL_MAP["warranty_policies"] = WarrantyPolicy`.
4. **Till Read-Only Guard**:
   - `require_catalog_writable()` invoked at the entry of `create_policy`, `update_policy`, `deactivate_policy`, `activate_policy`, `set_product_warranty`, and `set_category_default_warranty`. Secondary tills (`terminal_mode == "terminal"`) cannot mutate warranty policies or assignments.
5. **Deletion Tombstones**:
   - Covered automatically by `sync_change_tracking.py` `before_flush` hook for all tables in `CATALOG_TABLES`.

---

## 7. UI Experience & Gating (W1 Scope)

### 7.1 Feature Gating Visibility
- If `not WarrantyService.is_enabled()`:
  - Management sidebar tab "Warranty & Repairs" is completely hidden.
  - Product editor "Warranty" tab is hidden.
  - Category dialog "Default warranty" selector is hidden.
  - Side menu contains no warranty entry.
- Settings $\rightarrow$ System:
  - Houses the `"Warranty & Repairs"` switch (`warranty_enabled`). This is the explicit entry point on a fresh DB.
  - Toggling this switch or creating a policy enables the feature system-wide.
  - Even if the switch is off, custom non-template policies keep the feature accessible so shop owners can view and reactivate them.

### 7.2 Management $\rightarrow$ Warranty & Repairs $\rightarrow$ Policies
- `WarrantyPoliciesView` (`cbpos/ui/views/warranty_policies_view.py`):
  - Table showing: Name, Type, Duration, Remedy, Provider, Status (Active/Inactive), Actions.
  - Standard `batch_table_update`, empty state placeholder, theme styling.
  - Error state handling: on loading failure, preserve existing table rows, display a translated error banner with a Retry button, and disable the "New Policy" button.
  - "New Policy" button (checked against `warranty.manage_policies`).
  - Action buttons: "Edit", "Deactivate" / "Activate".
  - Deactivate confirmation: prompts user via `QMessageBox.question` with translated warning before deactivating.
  - Double-click handler: respects `warranty.manage_policies` permission and catalog read-only state.

### 7.3 `WarrantyPolicyDialog` (`cbpos/ui/dialogs/warranty_policy_dialog.py`)
- Clean modal form with `install_wheel_guard(self)`.
- Trilingual Name: English (mandatory), Sinhala (optional), Tamil (optional).
- Type combo: Shop, Manufacturer, Extended.
- Duration & Unit: Positive integer spinbox (min 1) + Days/Months/Years combo.
- Remedy combo: Repair or Replace, Repair Only, Replace Only, Refund.
- Provider Name (text).
- Terms and Exclusions: EN (required if translated versions present), SI, TA text areas.
- Supplier Cover Months spinbox (min 0, default 0).
- Standard dialog footer via `make_dialog_footer` (`[Save]`, `[Cancel]`).

### 7.4 Product Editor Warranty Tab
- Located in `cbpos/ui/dialogs/product_editor.py`.
- Radio / Combo selector:
  - `Use category default (<Name or None>)`
  - `No warranty`
  - `Specific policy` $\rightarrow$ dropdown of active policies.
  - If currently assigned policy is inactive, appends and selects `"<Name> (inactive)"` without reverting to None.
- Live preview line: Localized calculation showing coverage duration, type, remedy, and end date for a sale made today.
- Serial mode selector: Stays hidden in W1 (unlocked in W3 #823).

### 7.5 Category Dialog & Category Manager Warranty Selector
- Located in `cbpos/ui/dialogs/category_dialog.py` and `category_manager.py`.
- Dropdown: `None` or active warranty policy.
- Inactive policy preservation: If existing category has an inactive policy assigned, appends `"<Name> (inactive)"` and keeps it selected.
- If warranty selector was omitted from dialog (e.g. feature disabled), `update()` omits `default_warranty_policy_id` argument to prevent unintentional clearing.

### 7.6 i18n Key Namespaces
- `warranty.policy.*`: `title`, `name`, `type`, `duration`, `unit`, `remedy`, `provider`, `terms`, `exclusions`, `supplier_cover`, `status_active`, `status_inactive`, `deactivate_confirm_title`, `deactivate_confirm_msg`, `load_error_banner`, `retry`
- `warranty.types.*`: `shop`, `manufacturer`, `extended`
- `warranty.units.*`: `days`, `months`, `years`
- `warranty.remedies.*`: `repair_or_replace`, `repair_only`, `replace_only`, `refund`
- `product_editor.warranty_*`: `tab_title`, `override_inherit`, `override_none`, `override_policy`, `preview_format`, `weighted_item_notice`
- `category_dialog.warranty_default`: "Default Warranty"

---

## 8. Verification & Test Plan

1. **Unit & Domain Tests (`tests/domain/test_warranty_service.py`)**:
   - `test_compute_end_date_inclusive_calendar_math`: days, months, leap year (2024-02-29 + 1Y - 1D = 2025-02-27), month-end clamps.
   - `test_resolve_policy_precedence`: product explicit policy, category default, parent category default, None.
   - `test_resolve_policy_explicit_none_blocks_category`: confirms explicit NONE halts inheritance.
   - `test_resolve_policy_weighted_product_rejected`: weighted items return None and cannot be assigned.
   - `test_deactivated_policy_remains_on_assigned_products`: inactive policy still resolves on already-assigned product.
   - `test_feature_gating_fresh_db_hidden`: fresh DB with inactive templates reports disabled.
   - `test_feature_gating_active_or_user_policy_enables`: user policy enables without manual config switch.
   - `test_feature_gating_inactive_custom_policy_keeps_accessible`: custom non-template policy keeps feature accessible even if inactive.
   - `test_unauthenticated_mutation_fails_closed`: unauthenticated mutations without current user raise `PermissionError`.
   - `test_current_user_fallback_writes_id_to_audit_log`: actor ID properly recorded in `AuditLog`.
   - `test_new_assignment_to_inactive_policy_rejected`: `set_product_warranty` and `set_category_default_warranty` reject new inactive assignments.
   - `test_supplier_cover_months_negative_rejected`: reject negative supplier cover months.
   - `test_service_permission_enforcement`: `warranty.manage_policies` and `warranty.edit` verified.
   - `test_audit_trail_created_atomically`: audit logs verified for create, update, deactivate, activate, assign.
   - `test_policy_mutation_failure_injection_rollback`: Rule 4 failure injection proving complete rollback when inner step fails.
2. **Cross-Service Mutation & Audit Tests (`tests/domain/test_inventory_service.py`, `tests/domain/test_category_service.py`)**:
   - `test_inventory_service_create_and_update_enforces_warranty_edit_and_writes_audit`: creating/updating product with warranty fields checks `warranty.edit` and writes atomic `WARRANTY` audit.
   - `test_inventory_service_preserves_existing_inactive_warranty_assignment`: updating non-warranty fields on product with inactive warranty assignment preserves it.
   - `test_category_service_create_and_update_enforces_warranty_edit_and_writes_audit`: creating/updating category with default warranty checks `warranty.edit` and writes atomic `WARRANTY` audit.
   - `test_category_service_omitted_warranty_preserves_default_policy`: omitting warranty policy argument preserves existing default.
3. **Integration & Sync Tests (`tests/integration/test_sync_warranty_policies.py`)**:
   - Two-machine sync test: Main PC policy and assignments propagate to Till database.
   - Till rejects direct policy mutation via `require_catalog_writable()`.
   - Protocol version 1.3 verification.
4. **UI Tests (`tests/ui/inventory/test_warranty_ui.py`)**:
   - Policy editor dialog creation and validation errors.
   - Product editor warranty tab visibility under enabled/disabled states.
   - Inactive policy display as `"<Name> (inactive)"` and preservation in ProductEditor and CategoryDialog.
   - Policy view error state preserves rows and shows retry.
   - Policy view deactivation prompts confirmation dialog.
   - Policy view double-click respects permission and catalog read-only state.
   - Settings toggle persistence.
5. **Migration Verification**:
   - Test upgrade and downgrade on temporary SQLite database and PostgreSQL test harness.
