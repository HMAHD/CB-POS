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

## U0-SETTINGS-002 — Network setup performs blocking database and authentication work on the UI thread

- **Risk:** R2 — important responsiveness and recovery defect.
- **State:** confirmed by caller trace; focused regressions still required before repair.
- **Affected paths:** Network connection test, schema inspection, SQLite→PostgreSQL copy, Start Empty, and Make Main PC & Update.
- **Evidence:**
  - Button clicks call `_test_connection()`, `_on_copy_data_clicked()`, `_on_start_empty_clicked()`, and `_on_make_main_update_clicked()` directly (`cbpos/ui/views/settings_pages/network.py:240-282`).
  - `_test_connection()` calls blocking `Database.test_connection()` synchronously after one `QApplication.processEvents()` (`network.py:893-939`); the database adapter opens a real connection and runs `SELECT 1` (`cbpos/core/database.py:94-140`).
  - The success path immediately performs remote schema inspection through `SchemaMigrationService` and SQLAlchemy (`network.py:941-1023`).
  - Copy Data calls the complete table-by-table migration synchronously while only showing an indeterminate `QProgressDialog` (`network.py:1139-1214`; `cbpos/core/services/migration_service.py:97-236`).
  - Start Empty runs PIN authentication, SQLAlchemy `create_all`, Alembic stamping, and owner writes synchronously (`network.py:1031-1070`). Make Main PC likewise authenticates and runs the locked Alembic upgrade synchronously (`network.py:1072-1108`).
  - The same page already uses `SyncTestWorker` for its sync-server test (`network.py:1363-1383`), proving an established asynchronous adapter exists for blocking checks.
- **Concrete scenario:** the PostgreSQL host is slow or unreachable, or a shop database contains many rows. The user clicks Test Connection or Copy Data. The main Qt event loop enters the network/database operation; painting, keyboard input, cancellation, and other window events stop until the call returns. The displayed progress dialog cannot remain responsive because the migration itself runs on that same thread.
- **Wrong behavior:** a settings workflow can make the entire POS appear hung during an unbounded connection attempt, schema operation, bcrypt PIN check, or full data copy.

### Smallest repair acceptance criteria

1. Network connection, schema inspection, data copy, schema creation/stamping/upgrading, and PIN verification execute outside the Qt UI thread.
2. UI code gathers inputs and handles signals only; SQLAlchemy/Alembic orchestration moves behind a service/controller seam rather than another view helper.
3. Only one setup operation can run at a time. Relevant controls remain disabled until one terminal success/failure/cancel result is handled.
4. Workers never read or mutate widgets and return detached result data without credentials.
5. Focused Qt regressions replace each blocking adapter with a controllable wait, prove a UI-thread timer still fires, and assert the adapter ran outside `threading.main_thread()`.
6. PostgreSQL and Windows behavior remain explicitly unverified until their required environments run.

## Repeated update and hardware entry-point disposition

This trace did **not** find duplicate deep implementations:

- startup, About, System Settings, and Admin Tools update checks all use `check_for_updates_async()` and `UpdateService`;
- Settings Hardware and Admin Tools printer/drawer tests both use `PrinterTestWorker` / `DrawerTestWorker`, `HardwareTestService`, and the shared feedback mapper;
- Settings Hardware intentionally tests unsaved on-screen values, while Admin Tools intentionally tests saved configuration and adds scanner timing diagnostics.

The owner-approved map may remove redundant destinations, but it should reuse these existing seams rather than create replacement services.
