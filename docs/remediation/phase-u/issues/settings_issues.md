# Settings Issues

> **Audit status:** Settings shell, System update entry point, Hardware page, and Admin Tools update/hardware paths traced against product code `69fd64a`.
> **Evidence limits:** no physical printer, drawer, scanner, or Windows execution was performed.

## U0-SETTINGS-001 — A diagnostic timeout allows a second hardware test while the first still runs

- **Risk:** R2 — important correctness and recovery defect.
- **State:** confirmed by code trace; focused regression still required before repair.
- **Affected paths:** Admin Tools test printer and test cash drawer.
- **Evidence:**
  - Each click creates and starts a new unparented `PrinterTestWorker` or `DrawerTestWorker` and stores only the newest worker reference (`cbpos/ui/views/admin_tools_view.py:936-947`, `964-975`).
  - After 15 seconds, the timeout handler re-enables the corresponding action when that worker is still running; it does not stop or wait for the worker (`cbpos/ui/views/admin_tools_view.py:949-956`, `977-984`).
  - The worker can still be blocked in `HardwareTestService`, which owns the driver open/test/disconnect sequence (`cbpos/core/services/hardware_test_service.py:60-119`).
- **Concrete scenario:** a printer connection remains blocked beyond 15 seconds. Admin Tools reports a timeout and re-enables Test Printer. The user clicks again. A second worker starts against the same printer while the first operation and its eventual result are still live. The drawer path has the same behavior.
- **Wrong behavior:** overlapping device operations are permitted, the single worker reference no longer describes all active work, and a late result can overwrite the status of the newer attempt.

### Smallest repair acceptance criteria

1. One printer test and one drawer test can have at most one in-flight operation per Admin Tools view.
2. A presentation timeout cannot make the action start another worker while the original worker is running.
3. If cancellation is introduced, the implementation waits for safe worker termination before replacement; otherwise the action stays disabled until the terminal signal.
4. A late result is associated with its originating attempt and cannot replace a newer attempt's status.
5. A focused Qt test uses a controllable long-running fake worker: advance through the 15-second timeout, click again, and prove only one worker was started. Cover printer and drawer paths.
6. No claim of physical-hardware success is made without owner-supplied evidence.

## Repeated update and hardware entry-point disposition

This trace did **not** find duplicate deep implementations:

- startup, About, System Settings, and Admin Tools update checks all use `check_for_updates_async()` and `UpdateService`;
- Settings Hardware and Admin Tools printer/drawer tests both use `PrinterTestWorker` / `DrawerTestWorker`, `HardwareTestService`, and the shared feedback mapper;
- Settings Hardware intentionally tests unsaved on-screen values, while Admin Tools intentionally tests saved configuration and adds scanner timing diagnostics.

The owner-approved map may remove redundant destinations, but it should reuse these existing seams rather than create replacement services.
