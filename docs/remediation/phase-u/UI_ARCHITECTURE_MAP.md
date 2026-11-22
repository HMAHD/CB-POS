# Phase U.0 — UI Architecture and Ownership Map

> **Status:** provisional shell and owner-concern trace for #1041 against product code `69fd64a`.
> **Scope of this pass:** top-level navigation, permission/lifecycle ownership, Help/About, update checks, and hardware diagnostics. The remaining feature journeys and the final Phase 10B delta are still pending.

## Verified top-level flow

```text
main.py
└── MainWindow (owns the application QStackedWidget)
    ├── LoginView ──login_success──> SalesView
    ├── SalesView
    │   ├── SideMenu ──> ManagementView
    │   ├── SideMenu ──> SettingsView
    │   ├── SideMenu ──> ManagementView / Documents
    │   ├── SideMenu ──> AboutDialog
    │   └── F1 ──> ShortcutsHelpDialog
    ├── ManagementView
    │   └── lazy, permission-filtered feature stack
    └── SettingsView
        └── eager, permission-filtered settings/tool stack
```

`MainWindow` constructs all four top-level views once and owns their lifetime (`cbpos/ui/main_window.py:92-136`). Login propagates the user to Sales, Management, and Settings before showing Sales (`cbpos/ui/main_window.py:165-192`). The Sales side menu emits navigation intent; `MainWindow` performs the actual top-level switch (`cbpos/ui/main_window.py:99-134`, `302-341`).

## Shell ownership and lifecycle

| Surface | Constructed / owned by | Permission exposure | Refresh / activation behavior |
|---|---|---|---|
| `LoginView` | Eagerly by `MainWindow` | No logged-in user yet | Top-level stack entry |
| `SalesView` | Eagerly by `MainWindow`; owns `SideMenu` | Reached after successful login | Long-lived for the application session; owns POS shortcuts and modal workflow entry points |
| `SideMenu` | `SalesView`; signals consumed by `MainWindow` | Management and Settings buttons use `PermissionService.can_open_*`; warranty also follows its feature flag | User/permission state is refreshed at login/logout; active highlighting clears when hidden |
| `ManagementView` | Eagerly by `MainWindow` | Side-menu entry appears if at least one management tab is allowed; individual tabs use `MANAGEMENT_TAB_PERMISSIONS` | Child views are lazy. `switch_tab()` and `showEvent()` call the shared `activate()` seam |
| `SettingsView` | Eagerly by `MainWindow` | Side-menu entry appears if at least one settings page is allowed; individual pages use `SETTINGS_PAGE_PERMISSIONS` | All pages are eager. Config pages load once during construction and after explicit discard; no Settings-wide `activate()` dispatch exists |
| Modal dialogs | Their initiating view/dialog | The caller owns the permission gate unless the called service also enforces one | Normally constructed per use and destroyed after `exec()` returns |

The visibility maps are centralized in `cbpos/core/constants/permissions.py:189-221` and evaluated by `PermissionService.management_tabs()` / `settings_pages()` (`cbpos/core/services/permission_service.py:90-122`). This is navigation exposure, not proof that every mutation has its own service-level permission check; that is audited per journey.

### Management destinations

`ManagementView` creates a child only on first visit, stores it in `_view_widgets`, sets the current user where required, and then dispatches `activate()` (`cbpos/ui/views/management_view.py:236-328`).

| Index | Destination | Construction | Navigation gate |
|---:|---|---|---|
| 0 | Dashboard | lazy | `dashboard` permission map |
| 1 | Inventory | lazy | `inventory` permission map |
| 2 | Purchasing | lazy | `purchasing` permission map |
| 3 | Credit Book | lazy; feature-filtered | `credit_book` permission map |
| 4 | Reports | lazy | `reports` permission map |
| 5 | Documents | lazy; also directly reachable from Sales menu | `documents` permission map |
| 6 | Users | lazy | `users` permission map |
| 7 | Price Lists | lazy | `pricelists` permission map |
| 8 | Promotions | lazy | `promotions` permission map |
| 9 | Stock Take | lazy | `stock_take` permission map |
| 10 | Reorder | lazy; can route to Purchasing | `reorder` permission map |
| 11 | Warranty Policies | lazy; feature-filtered | `warranty` permission map |

`ManagementView.showEvent()` reactivates the current child when the user returns from another top-level surface (`cbpos/ui/views/management_view.py:417-429`).

### Settings destinations

`SettingsView` constructs seven config pages and four operational pages during application startup (`cbpos/ui/views/settings_view.py:91-188`). The config pages participate in one Settings-wide load/validate/save transaction; the operational pages save independently.

| Index | Destination | Ownership / lifecycle | Navigation gate |
|---:|---|---|---|
| 0 | Shop Information | eager config page | `shop_info` |
| 1 | Sales & Tax | eager config page | `sales_tax` |
| 2 | Documents | eager config page | `documents` |
| 3 | Hardware | eager config page | `hardware` |
| 4 | Receipts | eager config page | `receipt` |
| 5 | System | eager config page; owns one update-check entry point | `system` |
| 6 | Network | eager config page | `network` |
| 7 | Payment Methods | eager operational view in a scroll area | `payment_methods` |
| 8 | Data Safety | eager operational view in a scroll area | `data_safety` |
| 9 | Admin Tools | eager operational view in a scroll area; owns update and diagnostic entry points | `admin_tools` |
| 10 | Features | eager operational page in a scroll area | `features` |

Settings keeps edits across page switches and saves all seven config pages together (`cbpos/ui/views/settings_view.py:338-350`, `470-574`). Leaving through the Settings header's POS or Logout actions checks for unsaved changes. A successful save emits `close_requested`, and `MainWindow` returns to the last non-Settings top-level surface.

## Help, About, and contextual guidance

### Entry points and ownership

| Entry point | Current owner | Destination | Scope |
|---|---|---|---|
| Sales side-menu “Help & About” | `SideMenu` signal, handled by `MainWindow` | `AboutDialog` | Branding, version, user guide, feedback, update check, legal notices, source link |
| F1 | `SalesView` | `ShortcutsHelpDialog` | Sales keyboard shortcuts only |
| Field info icon | Individual settings page through `HelpIconButton` | Tooltip or `GuideDialog` | Contextual help for the field currently being edited |

The global About/support dialog is instantiated by `MainWindow`, but its only visible trigger is the Sales side menu (`cbpos/ui/widgets/side_menu.py:274-278`, `cbpos/ui/main_window.py:111`, `322-331`). No About/support destination exists in the Management or Settings navigation. A user already in either surface must return to Sales and open its side menu to reach documentation, feedback, legal information, or version details. This confirms the owner’s placement concern; disposition remains an owner decision after the full journey/visual audit.

F1 is a separate, useful contextual path declared by `SalesView` and opens only the Sales shortcut list (`cbpos/ui/views/sales_view.py:598-602`, `2518-2524`). Moving the global About/support destination must not remove or repurpose this Sales help path. `HelpIconButton` and `GuideDialog` are local guidance seams and are not duplicates of About or F1.

## Update checking

### Verified entry points

| Entry point | Mode | UI owner |
|---|---|---|
| Deferred startup check (`main.py:627-639`) | silent, after 3 seconds when enabled | application startup |
| About → Check for updates | manual, reports all outcomes | `AboutDialog` |
| Settings → System → Updates | manual, reports all outcomes | `SystemPage` |
| Settings → Admin Tools header | manual, reports all outcomes | `AdminToolsView` |

All four entry points share the same implementation seam:

```text
caller
└── check_for_updates_async()          cbpos/ui/dialogs/update_dialog.py
    └── _CheckThread
        └── UpdateService.check_for_update()
            └── remote manifest request + version decision
```

`check_for_updates_async()` owns process-wide in-flight deduplication, button state, translated outcome dialogs, and the `_CheckThread` lifecycle (`cbpos/ui/dialogs/update_dialog.py:261-339`). `UpdateService` owns the blocking network request and version rules (`cbpos/core/services/update_service.py:50-100`). Installer download is likewise run in `_DownloadThread`, not on the UI thread.

**Disposition of the duplication concern:** four entry points and three manual buttons are confirmed, but duplicate network/version/error implementations are not. They are thin adapters over one shared asynchronous controller and one service. U.0 should decide which manual destinations are useful; it should not create another update module.

Windows installer launch has only code/test evidence in this pass. No Windows installation was performed.

## Hardware diagnostics

### Verified entry points

| Entry point | Purpose | Target values |
|---|---|---|
| Sales no-printer notice | Routes to Settings → Hardware | configuration/recovery path |
| Settings → Hardware | Configure printers, drawer, paper, and scale; test printer/drawer | current on-screen values, including unsaved edits |
| Settings → Admin Tools → Hardware | Inspect saved printer details; test printer/drawer; test scanner keystroke timing | saved printer settings |

The receipt-printer and drawer paths share these seams:

```text
HardwarePage / AdminToolsView
└── PrinterTestWorker / DrawerTestWorker    cbpos/ui/workers.py
    └── HardwareTestService                 cbpos/core/services/hardware_test_service.py
        └── ESCPOSDriver

result
└── hardware_test_feedback.py               shared translation + status styling
```

`HardwareTestService` owns target resolution, driver connection, test commands, error classification, disconnect, and detached result data (`cbpos/core/services/hardware_test_service.py:38-168`). The workers keep device I/O off the UI thread (`cbpos/ui/workers.py:296-360`). Both UI surfaces use the shared feedback mapper. Settings passes its unsaved on-screen target; Admin Tools intentionally passes no override and reports/tests saved configuration.

**Disposition of the duplication concern:** two diagnostic surfaces are confirmed, but printer/drawer probing rules and result mapping are already shared. Admin Tools also contains scanner timing diagnostics, which Settings Hardware does not. Consolidation, if approved, should remove redundant entry points or UI orchestration rather than replace the service/worker seams.

One concrete lifecycle defect was found in Admin Tools: after its 15-second presentation timeout it re-enables the printer/drawer test button without stopping the still-running worker. A second click can therefore start a concurrent operation against the same device. Evidence and acceptance criteria are in `issues/settings_issues.md`.

Physical printer, drawer, scanner, and Windows behavior remain unverified in this pass.

## Current seam assessment

| Concern | Evidence-based status |
|---|---|
| Scattered top-level ownership | Shell ownership is explicit: `MainWindow` switches top-level surfaces; Management is lazy; Settings is eager. Feature-level tracing remains pending. |
| Help/About placement | Confirmed navigation gap: global support is only exposed through the Sales side menu; F1 is separate Sales context help. |
| Update duplication | Multiple entry points, one shared controller/service; no duplicate deep implementation found. |
| Hardware duplication | Two UI contexts, one service/worker/feedback stack; no duplicate device rules found. One Admin Tools timeout lifecycle defect found. |
| UI-thread blocking | Update network/download and printer/drawer tests use QThreads in the traced paths. Other paths remain pending. |

## Remaining architecture trace

- Trace every dialog caller and mark unreachable/stale surfaces.
- Trace the direct database import in `settings_pages/network.py` through its actual execution path.
- Map service and worker ownership for the remaining oversized responsibility candidates.
- Verify each feature journey’s service-level permission and mutation seam.
- Measure construction, activation, query, and worker lifetime behavior; file length is not performance evidence.
- Repeat this map against the exact final Phase 10B `main` SHA before owner approval.
