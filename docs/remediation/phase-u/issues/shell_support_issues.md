# Shell and Support Issues

> **Audit status:** top-level Help/About and Sales F1 paths traced against product code `69fd64a`.
> **Evidence limits:** no dark/light or trilingual screenshot pass yet.

## U0-SHELL-001 — Global support is exposed only through the Sales side menu

- **Risk:** R3 — UX ownership and discoverability.
- **State:** provisional; owner disposition required after visual/journey evidence.
- **Evidence:**
  - `SideMenu` always creates the Help & About tile (`cbpos/ui/widgets/side_menu.py:274-278`).
  - `MainWindow` connects only that signal to `AboutDialog` (`cbpos/ui/main_window.py:111`, `322-331`).
  - Management and Settings contain no About/support destination.
  - `AboutDialog` owns documentation, feedback, update, legal, source, version, and branding actions (`cbpos/ui/dialogs/about_dialog.py:41-319`).
- **Concrete scenario:** a user working in Management or Settings needs the user guide, version, legal notice, or problem-report link. They must leave that surface, return to Sales, open its side menu, and choose Help & About. A global support surface is therefore presented as a checkout action rather than application-level information.
- **Important relocation constraint:** Help & About is currently available regardless of role, while the Settings toolbar button is hidden when `PermissionService.can_open_settings(user)` is false (`cbpos/ui/widgets/side_menu.py:478-497`). Moving the only entry point behind the current Settings permission gate would remove support/legal access from cashiers and other restricted users.
- **Do not merge with F1:** Sales owns F1 and opens the Sales shortcut list (`cbpos/ui/views/sales_view.py:598-602`, `2518-2524`). That contextual keyboard path solves a different task and must remain fast and keyboard-accessible.

### Proposed acceptance criteria for the owner-approved map

1. Application support/about remains discoverable by keyboard and mouse from outside the checkout task.
2. Every authenticated role retains access to version, legal, documentation, and feedback information; access does not depend on administrative Settings permissions.
3. Sales F1 continues to open Sales shortcuts without first opening Settings or About.
4. Existing `AboutDialog` actions and safe external-link handling are reused; no second About implementation is created.
5. Dark/light and EN/SI/TA evidence at 1366×768 confirms the chosen placement and text expansion.

## Verified non-findings

- `ShortcutsHelpDialog` is contextual Sales help, not a duplicate `AboutDialog`.
- `HelpIconButton` plus `GuideDialog` is field-level guidance, not another global support implementation.
