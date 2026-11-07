# Security Design Note: Issue #858 — Tab Permissions & Privilege Escalation Prevention (Revised)

**Date:** 2026-11-07  
**Issue:** #858  
**Batch:** 5.1  
**Status:** Approved post-Goldfish review remediation  

## 1. Problem & Threat Model
In CB POS, `MANAGEMENT_TAB_PERMISSIONS` currently maps `stock_take`, `pricelists`, and `promotions` tabs to `(Permissions.ADMIN_MANAGE_USERS,)`.
- **Denial of legitimate access:** A standard Manager holding `stock_take.view`, `stock_take.create`, and `stock_take.approve` cannot view or access the Stock Take tab.
- **Privilege Escalation Vector 1:** To allow a Manager or Supervisor to perform stock counts, price updates, or promotions, an administrator must grant them `admin.manage_users`.
- **Privilege Escalation Vector 2 (Self-promotion):** Once a user possesses `admin.manage_users`, they can open Users management, edit their own user record, and change their role to `Admin`. `UserService.update_user` accepts any `role_id` without verifying the actor's identity or role.
- **Privilege Escalation Vector 3 (Admin Account Hijacking):** A user holding `admin.manage_users` could edit *another* user who is already an Admin, reset their PIN or username, or deactivate them, effectively taking over the system.
- **Privilege Escalation Vector 4 (Role Modification Escalation):** A user with `admin.manage_roles` can use `PermissionService.update_role_permissions` to grant their own role full administrative permissions or grant permissions they do not possess themselves.

## 2. Invariants
1. **Least Privilege for Navigation:** Each management tab is gated solely by permissions governing its domain (`stock_take.view`, `pricing.manage`, `promotions.manage`).
2. **Admin Role Isolation (Grant & Modify):**
   - Only an active user with the `Admin` role can grant the `Admin` role to any user (in `create_user` and `update_user`).
   - Only an active user with the `Admin` role can modify, rename, reset the PIN of, or deactivate an existing `Admin` user (`only_admin_can_modify_admin`).
3. **Self-Role Immutability:** No user can change their own role, even if they hold `admin.manage_users`. Another administrator must perform role modifications (`cannot_change_own_role`).
4. **Self-Permission Immutability:** A non-Admin user cannot edit the permissions of their own role (`cannot_edit_own_role`), nor modify the `Admin` role.
5. **Grant Delegation Boundary:** A non-Admin user cannot grant any permission to another role that they do not personally hold (`cannot_grant_unheld_permission`).
6. **Fail-Closed Actor Resolution:** Any privileged user/role mutation requires a valid authenticated actor (`effective_actor_id`), failing closed if no actor can be resolved.
7. **Dual-Layer Enforcement:** Every restriction is enforced in service layer business logic (`UserService`, `PermissionService`). UI controls (hiding options, disabling inputs, tooltips, diff-based saving) reflect these boundaries but are never solely relied upon.

## 3. Specification of Changes

### 3.1 Permission Constants & Tab Map
In `cbpos/core/constants/permissions.py`:
- Add `PRICING_MANAGE = "pricing.manage"`
- Add `PROMOTIONS_MANAGE = "promotions.manage"`
- In `Permissions.get_groups()`: include `PRICING_MANAGE` and `PROMOTIONS_MANAGE` under `"Inventory"`.
- In `MANAGEMENT_TAB_PERMISSIONS`:
  - `"stock_take"`: `(Permissions.STOCK_TAKE_VIEW,)`
  - `"pricelists"`: `(Permissions.PRICING_MANAGE,)`
  - `"promotions"`: `(Permissions.PROMOTIONS_MANAGE,)`

### 3.2 Seeding & Alembic Migration
- Update `DatabaseSetupService.create_empty_database()` and `scripts/seed.py`:
  - Manager role receives `PRICING_MANAGE` and `PROMOTIONS_MANAGE` via the `"Inventory"` group.
- Create Alembic migration (`versions/<id>_add_pricing_and_promotions_permissions.py`):
  - Idempotent upgrade: Inserts `pricing.manage` and `promotions.manage` into `permissions` if not already present.
  - Grants both new permissions to any existing role that has `admin.manage_users` or is named `Admin` or `Manager`, checking existence to prevent unique/PK violations.
  - Reversible downgrade: Safely deletes from `role_permissions` first before deleting from `permissions` to satisfy PostgreSQL foreign key constraints.

### 3.3 Service-Layer Escalation Guards
In `cbpos/core/services/user_service.py`:
- Helper to resolve actor:
  ```python
  effective_actor_id = (
      acting_user_id
      if acting_user_id is not None
      else (AuthService.get_current_user().id if AuthService.get_current_user() else None)
  )
  if effective_actor_id is None:
      raise ValueError("actor_required")
  ```
- `create_user(username: str, pin: str, role_id: int, acting_user_id: int | None = None) -> bool`:
  - Resolve actor and actor's role.
  - If target role is `Admin` (`Role.name == ADMIN_ROLE_NAME`) and actor is not `Admin`:
    `raise ValueError("only_admin_can_grant_admin")`
- `update_user(user_id: int, username: str, pin: str | None, role_id: int, is_active: bool, acting_user_id: int | None = None) -> bool`:
  - Resolve actor and actor's role.
  - Self-role immutability:
    `if user_id == effective_actor_id and user.role_id != role_id:`
        `raise ValueError("cannot_change_own_role")`
  - Target Admin protection (anti-takeover):
    `if user.role.name == ADMIN_ROLE_NAME and actor.role.name != ADMIN_ROLE_NAME:`
        `raise ValueError("only_admin_can_modify_admin")`
  - Admin grant protection:
    `if role_id != user.role_id and target_role.name == ADMIN_ROLE_NAME and actor.role.name != ADMIN_ROLE_NAME:`
        `raise ValueError("only_admin_can_grant_admin")`
  - Last active Admin protection (preserves existing check).

In `cbpos/core/services/permission_service.py`:
- Update `update_role_permissions(role_id: int, permission_ids: list[int], acting_user_id: int | None = None) -> bool`:
  - Resolve actor.
  - If actor is not Admin:
    - If `role.name == ADMIN_ROLE_NAME`: `raise ValueError("only_admin_can_modify_admin_role")`
    - If `role_id == actor.role_id`: `raise ValueError("cannot_edit_own_role")`
    - Check held permissions: If any ID in `permission_ids` is not in actor's held permissions, `raise ValueError("cannot_grant_unheld_permission")`

### 3.4 UI Guards
- `UserDialog`:
  - If actor is not Admin:
    - In create mode: omit `Admin` from `cmb_role`.
    - In edit mode: if target user is Admin, disable the entire dialog fields and show `_t("users.only_admin_can_modify_admin")`.
    - If editing current user (`user.id == actor.id`): disable `cmb_role` and attach tooltip `_t("users.cannot_change_own_role")`.
  - Pass `acting_user_id=current_user.id` to `UserService`.
  - Map `ValueError` codes to translated warning dialogs.
- `UserView`:
  - When non-Admin selects an Admin user, disable the Edit button or show a tooltip.
- `PermissionDialog`:
  - Identify non-Admin actor.
  - Omit or lock the `Admin` column and actor's own role column (`LOCKED_CELL_ROLE`).
  - Store initial check states in `ORIGINAL_CHECK_STATE_ROLE = Qt.ItemDataRole.UserRole + 2`.
  - In `_restore_locked_descendants`, restore each locked child to its `ORIGINAL_CHECK_STATE_ROLE`.
  - In `save_changes`:
    - Save only roles whose permission sets have actually changed.
    - Skip actor's own role and `Admin` role if actor is non-Admin.
    - Pass `acting_user_id=current_user.id`.

### 3.5 i18n
Keys added to `en.json`, `si.json`, `ta.json`:
- `users.only_admin_can_grant_admin`
- `users.only_admin_can_modify_admin`
- `users.cannot_change_own_role`
- `roles.cannot_edit_own_role`
- `roles.cannot_grant_unheld`
- `permissions.pricing_manage`
- `permissions.promotions_manage`

## 4. Rollback & Migration Safety
- SQLite and PostgreSQL compatible batch migration.
- Clean rollback order: delete from `role_permissions` where permission is in (`pricing.manage`, `promotions.manage`), then delete from `permissions`.
