# Phase U Issues Summary

> **Status:** U.0 inventory in progress for #1041. No product-code implementation is authorized.
> **Baselines:** product code `69fd64a`; Phase U record `504df7f`. Final Phase 10B delta is still required.

## Current evidence

| Area | Status | Evidence |
|---|---|---|
| Surface/navigation inventory | in progress | `UI_SURFACE_INVENTORY.md` + `evidence/ui_inventory.json` — reproducible AST baseline of 165 Python modules (143 class-bearing, 22 helper/package-only, 206 top-level classes); shell reachability traced |
| Architecture/ownership map | in progress | `UI_ARCHITECTURE_MAP.md` — top-level shell, permissions, lifecycle, Help/About, updates, and hardware |
| Journey audit | todo | — |
| Dark/light + EN/SI/TA visual audit | todo | — |
| Measured performance baseline | todo | — |
| Existing audit + #963–#975 reconciliation | todo | — |
| Retrospective integrity audit | todo | — |
| Owner-approved implementation map | blocked | waits for complete evidence and final Phase 10B delta |

## Findings

Five evidence-backed findings are recorded. File length remains an inventory signal only.

| Severity | Count |
|---|---:|
| R1 release/data-integrity blocker | 0 |
| R2 important correctness/recovery | 4 |
| R3 evidence gap/maintainability | 1 |

| ID | Risk | Surface | Finding | Evidence |
|---|---|---|---|---|
| U0-SETTINGS-001 | R2 | Admin Tools / Hardware | The 15-second timeout re-enables a hardware-test action while its worker still runs, allowing overlapping device operations | `issues/settings_issues.md` |
| U0-SETTINGS-002 | R2 | Settings / Network | Connection, schema, migration, and PIN operations run synchronously on the Qt UI thread | `issues/settings_issues.md` |
| U0-SALES-001 | R2 | Sales / Checkout | Normal payment and Quick Pay commit the database transaction synchronously on the Qt UI thread | `issues/sales_issues.md` |
| U0-PURCHASE-001 | R2 | Purchasing | Tab loads, payable search, and GRN receipt run database work synchronously on the Qt UI thread | `issues/purchasing_issues.md` |
| U0-SHELL-001 | R3 | Shell / Support | Global About/support is exposed only through the Sales side menu; a Settings move must preserve access for roles without Settings permission and keep Sales F1 | `issues/shell_support_issues.md` |

## Owner concerns tracker

| Concern | Status |
|---|---|
| Large view responsibilities | Sales and Purchasing responsibility clusters mapped; extraction decisions wait for journey/performance/test evidence |
| Full-product workflow and recovery UX | Sales checkout and Purchasing activation/GRN execution paths traced; remaining states and journeys pending |
| Scattered ownership | shell ownership and lifecycle traced; feature-level map pending |
| Opaque/mismatched text backgrounds | visual audit todo |
| Duplicate update/hardware checks | traced: multiple entry points share existing controller/service/worker seams; one Admin Tools worker-timeout defect recorded |
| Help/About placement with contextual F1 help | traced: global support is Sales-menu-only; preserve permission-independent access and Sales F1 when dispositioned |

## Provisional issue reconciliation

Issues #963–#975 remain open inputs. No item has been approved, rejected, expanded, or superseded yet.
