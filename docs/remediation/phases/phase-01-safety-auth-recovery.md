# Phase 1 — Destructive Safety, Authentication, Recovery

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> This spec was verified against `origin/main` @ `4bcc837` on 2026-10-28. Re-verify every `file:line` before editing (§0.1 step 7).

## Phase brief

**Outcome (end state):**
- A fresh install always runs the Setup Wizard. The admin PIN the owner chooses is the real admin PIN, and `1234` never survives first run.
- No database error, network hiccup or missing local file can make CB POS offer "Load Demo Data" over a live shop. Demo loading refuses to touch a database that has data.
- A manager override approves **one** action. It never logs the manager in. Wrong PINs lock the terminal after the configured number of attempts. No two users share a PIN. The last Admin cannot be removed.
- Logout and idle timeout really end the session: AuthService is cleared, open dialogs close, the cart is held (not inherited), and the audit log records it with the right terminal.
- Upgrading an old database migrates it instead of stamping it. A corrupt `settings.json` is preserved, never silently replaced. Backup, restore and maintenance never claim success on the wrong database. A restore reloads settings, migrates, restarts, and tells the user which secrets must be re-entered.

**Depends on:** nothing. This phase goes first.
**Unblocks:** every other phase. Batches 1.1 and 1.2 must merge before Phases 2–5 start (RELEASE_PLAN.md §1.2).

### Issues

| # | Title | Sev | Size | Batch | Gate |
|---|---|---|---|---|---|
| #948 | CI runs no tests or lint (ci.yml fully commented out) | high | S | 1.0 | agent (branch protection: owner) |
| #833 | "Is setup needed?" says yes on any DB error, so demo load can wipe a live DB | critical | M | 1.1 | agent |
| #791 | Setup wizard never appears; wizard admin PIN never applied | critical | M | 1.1 | agent |
| #835 | Manager override permanently logs the manager in | critical | M | 1.2 | agent |
| #857 | Duplicate PINs accepted | high | S | 1.2 | agent |
| #856 | No brute-force lockout on PIN login | high | M | 1.2 | agent |
| #859 | Last active Admin can be deactivated or demoted | high | S | 1.2 | agent |
| #860 | Logout/timeout don't clear AuthService, close dialogs, or protect the cart | high | M | 1.2 | agent (cart: recommended answer given) |
| #837 | Unversioned DB stamped at head, migrations skipped | high | M | 1.3 | agent |
| #838 | Corrupt settings.json silently becomes defaults and is overwritten | high | M | 1.3 | agent |
| #839 | Backup/restore/maintenance act on local SQLite in network mode | high | M | 1.3 | agent |
| #873 | Restore keeps stale in-memory settings and an unmigrated schema | medium | M | 1.3 | agent |
| #874 | Backup from a newer app version is accepted, then the app can't start | medium | S | 1.3 | agent |
| #875 | Restored encrypted secrets become ciphertext, then double-encrypted | medium | S | 1.3 | agent |

### Subsystem map (read before any batch)

**Startup** — `main.py:main()` (`main.py:289`). The order matters for this phase:
1. `ensure_data_dir()`
2. `run_migrations()` (`main.py:110`; SQLite only, uses `Config.DB_URI`)
3. `ConfigService.get("language")` at `main.py:361`. **This is the first ConfigService access, and it creates `settings.json` with defaults** (`config_service.py:323-325`).
4. Theme, then `register_all_reports()` (`main.py:420-425`)
5. Setup Wizard check, `main.py:429`
6. `DatabaseSetupService.needs_setup()` → `DatabaseSetupDialog`, `main.py:439-458`
7. Ledger and loyalty backfill, `main.py:461+`
8. `MainWindow`

**Settings** — `cbpos/core/services/config_service.py`:
- `ConfigService` is a class-level singleton dict `_settings`.
- `load()` is at `:306-325` and `save()` at `:404`. `get()` at `:440` lazily calls `load()`.
- Sensitive keys are Fernet-encrypted with a key from `_get_fernet()` (`:213-235`, key file `_KEY_FILE`). `_decode_sensitive()` is at `:244-256`.
- Atomic write: `_write_restricted()` (`~:190-206`, `mkstemp` + `os.replace`).

**Database** — `cbpos/core/database.py`:
- `Database()` is a singleton. `_initialize()` reads `db_mode` (`:46`): `standalone` uses SQLite at `Config.DB_URI`, `network` uses PostgreSQL from the `network_db_*` settings (`:94-117`).
- `get_session()` is at `:172`.

**First-run DB setup** — `cbpos/core/services/database_setup_service.py`:
- `needs_setup()` `:55-70`
- `create_empty_database()` `:73-177`, which creates admin with PIN `"1234"` at `:136`
- `create_demo_database()` `:180+`, which runs `scripts/seed.py`, which calls `Base.metadata.drop_all` (`scripts/seed.py:~62`)
- `stamp_alembic_head()` `:35-52`

**Auth** — `cbpos/core/services/auth_service.py`:
- `verify_pin(pin)` `:139-250`: loops over all active users, bcrypt-checks each, **sets `_current_user`** at `:196`, and writes a LOGIN audit row.
- `verify_pin_for_user()` `:253-311` has per-user lockout but is **unused** in app code.
- `logout()` `:319-340` writes a LOGOUT audit row but has **no callers**.
- Lockout settings: `_get_max_attempts()` `:14` (default 5) and `_get_lockout_duration()` `:25` (default 300 s).
- Callers of `verify_pin`:
  - `ui/views/login_view.py:375`
  - `ui/dialogs/manager_override_dialog.py:63`
  - `ui/dialogs/profile_dialog.py:86`

**Users** — `cbpos/core/services/user_service.py`:
- `create_user` `~:138-166`, `update_user` `~:169-198`, `update_user_profile`, `update_admin_pin` `:58-69` (returns False when no admin; callers ignore it)
- UI: `ui/dialogs/user_dialog.py`, `ui/dialogs/profile_dialog.py`

**Session** — `cbpos/ui/main_window.py:187-195`: `logout()` only clears `self.user` and switches the page.
- `cbpos/infrastructure/session_watchdog.py:87-114`: `on_timeout()` writes a TIMEOUT audit row with `terminal_id="TERM-01"` hard-coded (`:105`), then emits `session_expired`.
- Cart: `SalesView.hold_bill()` (`ui/views/sales_view.py:1086`) → `SuspendedTransactionService.hold_bill(cart_service)`.

**Backup/restore** — `cbpos/core/services/backup_service.py`:
- `create_backup` `:72`, which always zips `Config.DATA_DIR/"cbpos.db"` (`:96`)
- `_copy_database` `:162` (sqlite3), `run_auto_backup` `:183`
- `restore_backup` `:210-305`, `_validate_database` `:373-393` (checks only `_EXPECTED_TABLES` `:52`)
- `verify_backup` `:603`
- Maintenance: `cbpos/core/services/maintenance_service.py`
- UI: `cbpos/ui/views/data_safety/` (`restore_tab.py`, …)
- Restart helper: `cbpos/ui/app_restart.py:29` `restart_application(window)`

**Helpers to reuse:**
- `check_permission_with_override()` in `cbpos/core/utils/permission_helper.py`
- `translate_error()` in `cbpos/core/utils/error_messages.py`
- `make_dialog_footer` in `cbpos/ui/widgets/dialog_footer.py`
- `restart_application` in `cbpos/ui/app_restart.py`
- `BackupError(code, detail)` in `backup_service.py:~60`: the UI already maps `code` to i18n via `data_safety.error_<code>`. Verify the mapping location with `graft grep "error_" --in cbpos/ui/views/data_safety`.

### Domain invariants this phase must preserve

1. A code path that can destroy data (`drop_all`, file replace, restore) runs only on a target **positively identified** as safe: empty, or explicitly confirmed by the user with a snapshot taken first. "I couldn't tell" means **stop**, never "assume empty".
2. Authenticating a PIN and logging in are different operations. Only `LoginView` logs in.
3. `AuthService.get_current_user()` is always the person at the keyboard who logged in, or None after logout or timeout.
4. Every active user's PIN is unique among active users.
5. At least one active user always holds the Admin role.
6. Settings on disk are never replaced by defaults without a preserved copy of the previous file.
7. Backup and restore operate on the database the app actually uses, or refuse.
8. After a restore, nothing in memory from before the restore can be written back to disk.

### Batches (one PR each)

| Batch | Branch | Issues (in order) | Why grouped |
|---|---|---|---|
| 1.0 | `fix/p1-b0-restore-ci` | #948 | Every later merge rule ("merge when CI is green") depends on CI existing |
| 1.1 | `fix/p1-b1-setup-safety` | #833, #791 | Both live in the first-run path (`main.py` + `DatabaseSetupService`). #833 changes `needs_setup()`, which #791's new order depends on |
| 1.2 | `fix/p1-b2-auth-session` | #835, #857, #856, #859, #860 | All in AuthService/UserService and session lifecycle. #835 creates `authenticate_pin`, which #856 builds its throttle into |
| 1.3 | `fix/p1-b3-migration-backup-restore` | #837, #838, #875, #874, #839, #873 | Startup migration, settings durability and the restore pipeline. #873 needs #837 (migrate after restore) and #838/#875 (settings reload) |

---

## Batch 1.0 — Restore CI (do this first)

**Branch:** `fix/p1-b0-restore-ci` · **Issues:** #948

### #948 — CI runs no tests or lint: every job in ci.yml is commented out

**Severity:** high · **Size:** S · **Gate:** agent. Branch protection is a repo setting the owner switches on.
**Skills:** ponytail → verification-before-completion

**Problem.** No GitHub Actions job checks pushes or PRs, so every merge to `main` goes in unverified. The release gate and §0.10's "merge once CI is green" rule both depend on CI.

**Evidence.**
- `.github/workflows/ci.yml` is entirely commented out. Last edits: f17daa6 and af741ba.
- The commented block runs the old path `cbpos/tests` and ends in `|| true`, which hides failures.

**Fix.** Rewrite `ci.yml`:
- triggers: `on: push: branches [main]` and `pull_request`;
- job `lint`: `astral-sh/setup-uv` (exact pinned version, matching `release.yml`), `uv sync --locked`, `uv run pre-commit run --all-files`;
- job `unit` (ubuntu-latest): install the Qt libraries listed in the old commented block (`libegl1`, `libxkbcommon-x11-0`, the `libxcb-*` set), then `uv sync --locked`, then `QT_QPA_PLATFORM=offscreen uv run python -m pytest -q -n auto`. **No `|| true`.**
- Cache the uv dir. Delete the commented-out legacy block (git history keeps it).
- Phase 2 #799 later adds a `postgres` job next to these.

**Tests.** The workflow is the test:
1. Open the PR. CI must be green.
2. Push a throwaway commit to the branch with `assert False` in a new test. CI must go red.
3. Revert it.

Paste both run links in the PR.

**Acceptance.**
- [ ] A clean PR is green for lint and the unit suite. A failing test turns CI red.
- [ ] The owner enables branch protection on `main`, requiring the `lint` and `unit` checks (ask them; it's a repo setting).

**Stop & Ask if.** The unit suite fails on Linux CI for reasons unrelated to any code change (missing system libs, fonts). Report the failing tests, and don't skip them.

---

## Batch 1.1 — Setup and destructive-operation safety

**Branch:** `fix/p1-b1-setup-safety` · **Issues:** #833, #791 · **Order:** #833 first. #791 reorders startup around the new `needs_setup()` result.

### #833 — "Is setup needed?" answers yes on any DB error, so "Load Demo Data" can wipe a live shop

**Severity:** critical · **Size:** M · **Type:** bug (data loss) · **Gate:** agent
**Skills:** systematic-debugging → tdd → ponytail; ponytail-review on the diff

**Problem.** At startup CB POS asks "does this database need first-run setup?". Today the answer is "yes" whenever the user count query throws, for any reason: a missing column after an old upgrade (#837), a locked file, corruption, or a PostgreSQL server that is down for a moment. The owner then sees "Start Fresh / Load Demo Data" over their real shop. Clicking Load Demo Data runs `drop_all` and erases every sale, product, customer and credit record. In network mode it erases the shared database for every till.

**Evidence and root cause.**
- `cbpos/core/services/database_setup_service.py:55-70` (`needs_setup`):
  ```python
  db_path = Config.DATA_DIR / "cbpos.db"
  if not db_path.exists():
      return True
  try:
      ... count = session.query(User).count()
      return count == 0
  except Exception:
      return True
  ```
  Two root causes:
  - (a) It treats *every* exception as "empty".
  - (b) It checks the **local SQLite file** even when `db_mode == "network"`, where data lives in PostgreSQL (`cbpos/core/database.py:46-54`). A network till with no local file always gets "needs setup".
- `create_demo_database()` (`database_setup_service.py:180+`) calls the seeder, which runs `Base.metadata.drop_all(db.engine)` (`scripts/seed.py:~62`) with no "is this database empty?" guard.
- `main.py:442-458` acts on `needs_setup()` with no error path.

**Fix design.**
- *Recommended:* make the question three-valued and fail closed.
  - Add `class SetupState(Enum): NEEDS_SETUP, READY` in `database_setup_service.py`.
  - Add `DatabaseSetupService.check_setup_state() -> SetupState`, which **raises** `DatabaseUnavailableError` (a new exception defined in the same module) on any failure to inspect.
  - Decide using `sqlalchemy.inspect(Database().engine)`, not an ORM query. That makes it work in both modes, because `Database().engine` is already the right engine.
    1. If the engine is SQLite and the DB file does not exist → `NEEDS_SETUP`.
    2. If `"users"` is not in `inspector.get_table_names()` → `NEEDS_SETUP`, but only if **no** other CB POS table exists either. If some tables exist and `users` is missing, raise `DatabaseUnavailableError("partial_schema")`.
    3. Otherwise run `SELECT COUNT(*) FROM users` through a Core `text()` query. That avoids ORM column selection, so a missing column elsewhere cannot break it. Zero rows → `NEEDS_SETUP`, more → `READY`. Any exception propagates as `DatabaseUnavailableError` with the original error chained.
  - Keep `needs_setup()` as a thin wrapper that returns `check_setup_state() is SetupState.NEEDS_SETUP`, so existing tests and callers keep working. It now **raises** instead of returning True on errors.
  - Add a destructive-operation guard: `DatabaseSetupService._assert_database_empty()`. It counts rows in `users`, `documents` (sales/purchases), `products` and `customers`, using `text()` and skipping tables that don't exist. If any count is > 0 it raises `DatabaseNotEmptyError`. Call it as the **first line** of `create_demo_database()`, and in `create_empty_database()` before inserting the admin user, so a second run cannot duplicate admins.
  - In `main.py`, wrap the setup check: on `DatabaseUnavailableError`, close the splash and show a translated critical dialog, then `sys.exit(1)`. **Never** show the setup dialog in this case.
- *Rejected alternatives:*
  - "Catch only `OperationalError`": still says yes for locked or corrupt DBs, which are OperationalErrors too.
  - "Ask the user to confirm before demo load": the user cannot tell their DB is live when the app says it is empty. The guard has to be in code.
  - "Add the guard only in the dialog": UI-only guard, rule §0.3.
- *Data/schema:* none.
- *Sync/network impact:* in network mode the check now runs against PostgreSQL. A till whose server is unreachable shows the error dialog instead of the setup dialog. Phase 2 (#799) adds the guided Network Setup. This phase only has to fail closed.

**Implementation steps.**
1. `database_setup_service.py`:
   - Add `SetupState`, `DatabaseUnavailableError(Exception)` (with a `code: str` attribute: `"unreachable"`, `"partial_schema"` or `"unreadable"`) and `DatabaseNotEmptyError(Exception)`.
   - Implement `check_setup_state()` as designed above. Get the engine via `Database().engine`. Confirm the attribute name with `graft skeleton cbpos/core/database.py`.
   - Rewrite `needs_setup()` as the wrapper.
2. In the same file add `_assert_database_empty()` and call it first in `create_demo_database()`. In `create_empty_database()`, call it right after `create_all()` and before inserting rows. `create_all()` is safe: it only creates missing tables.
3. `main.py:439-458`: call `DatabaseSetupService.check_setup_state()` inside `try/except DatabaseUnavailableError as e`. On error:
   - `_close_splash()`
   - `QMessageBox.critical(None, _t("db_setup.unavailable_title"), _t("db_setup.unavailable_body"))`
   - log the cause with `logger.error`
   - `sys.exit(1)`

   Batch 1.1 #791 restructures this block further, so do #833 first and then #791 builds on it.
4. Grep for other `needs_setup()` callers (`graft callers needs_setup`) and make sure each one handles the raise.

**Tests (write first).** File `tests/domain/test_database_setup_service.py`. Create it if missing, copying the fixture style from `tests/ui/test_backup_restore_safety.py`, which builds throwaway SQLite files in `tmp_path` and points `Config.DATA_DIR` at them via `monkeypatch`.
- `test_issue_833_populated_db_with_missing_column_is_not_setup`:
  - Given a seeded throwaway DB where `ALTER TABLE` removed or renamed a column used by the `User` ORM model. In SQLite, rebuild `users` without `locked_until`.
  - When `check_setup_state()` runs.
  - Then it returns `READY`.
  - Today `needs_setup()` returns True.
- `test_issue_833_query_error_raises_not_setup`: monkeypatch the count execution to raise `OperationalError("database is locked")`. Assert `DatabaseUnavailableError` is raised.
- `test_issue_833_demo_load_refuses_populated_db`:
  - Given a DB with one customer named "REAL SHOP CUSTOMER".
  - When `create_demo_database()` runs.
  - Then `DatabaseNotEmptyError` is raised and the customer row still exists.
- `test_issue_833_network_mode_does_not_use_local_file`: monkeypatch `ConfigService.get("db_mode")` to `"network"` and the engine to a SQLite engine with users. With no local `cbpos.db` present, assert `READY`.
- `test_issue_833_empty_file_and_missing_file_need_setup`: both return `NEEDS_SETUP`.

**UI/UX spec.** One new error dialog at startup, shown before any window exists:
- Keys:
  - `db_setup.unavailable_title` → "Can't open the shop database"
  - `db_setup.unavailable_body` → "CB POS couldn't read your shop's data, so it has stopped to keep it safe. Nothing has been changed or deleted.\n\nIf this computer uses a Main PC, check that the Main PC is on and connected, then open CB POS again. If the problem continues, restore your latest backup from another computer or contact support."
- The dialog uses a single **OK** button, which exits.
- Use `QMessageBox.critical` because no theme is guaranteed yet at this point; the theme is applied at `main.py:401`, before this, so it will be styled.
- Run the §0.7 UI gate on the message text, checking si/ta length in the message box.

**Do NOT.**
- Do not keep a bare `except Exception: return True` anywhere in this path.
- Do not check `Config.DATA_DIR / "cbpos.db"` in network mode.
- Do not put the emptiness guard in `DatabaseSetupDialog`. It belongs in the service.
- Do not change `scripts/seed.py`'s developer behaviour (`uv run python scripts/seed.py` still resets a dev DB). The guard lives in `create_demo_database()`.
- Do not "repair" a partial schema automatically here.

**Edge cases.**
- A 0-byte `cbpos.db` (no tables) → `NEEDS_SETUP`.
- Tables exist but there are 0 users while products exist → `create_empty_database()` must raise `DatabaseNotEmptyError` rather than re-seed. Show the unavailable dialog with code `partial_schema`.
- A PostgreSQL DB with no tables yet (first network install) → `NEEDS_SETUP`.

**Acceptance criteria.**
- [ ] A populated DB with a missing column, or a DB whose query raises, never yields "needs setup".
- [ ] `create_demo_database()` on a DB with any users, documents, products or customers raises and changes nothing.
- [ ] Network mode with no local `cbpos.db` does not show the setup dialog.
- [ ] Startup shows the translated "Can't open the shop database" dialog and exits on an unreadable DB.

**Verify.**
- Run `uv run python -m pytest tests/domain/test_database_setup_service.py -v`.
- Manual check:
  1. Copy a seeded `cbpos.db`.
  2. In the copy, run `sqlite3 cbpos.db "ALTER TABLE users RENAME TO users_x"`.
  3. Launch the app and confirm the error dialog appears and no setup dialog.

**Stop & Ask if.** None expected.

### #791 — First-run setup wizard never appears; the admin PIN from the wizard is never applied

**Severity:** critical · **Size:** M · **Type:** security · **Gate:** agent
**Skills:** systematic-debugging → tdd → ponytail; impeccable (clarify) for wizard copy

**Problem.** A new shop never sees the Setup Wizard, so it never enters its name, printer or admin PIN, and `admin` / `1234` stays the login forever. Anyone who reads the public README can log in as Admin. Even when the wizard does show, the PIN is thrown away, because the wizard runs before the database exists.

**Evidence and root cause.**
- `main.py:361`: `saved_language = ConfigService.get("language") or "en"` is the first ConfigService access. `config_service.py:323-325` (`load()`'s `else` branch) then writes a default `settings.json`.
- `main.py:429`: `if not os.path.exists(ConfigService.SETTINGS_FILE):` is therefore always False, so the wizard never opens. Root cause: first-run is inferred from a file that startup itself creates earlier.
- `cbpos/ui/dialogs/setup_wizard.py:307-343` (`finish_wizard`) calls `UserService.update_admin_pin(self.input_pin.text())` at `:336` and ignores the bool it returns.
- `user_service.py:58-69` returns False when there is no `admin` row. On a fresh install the DB doesn't exist yet, because DB setup runs after the wizard (`main.py:439-458`).
- `database_setup_service.py:136` then creates `admin` with `_hash_pin("1234")`.
- The demo path (`scripts/seed.py`) also creates admin/1234, manager/5678 and cashier/0000.

**Fix design.**
- *Recommended:*
  - An explicit, durable `setup_completed` flag in settings.
  - The wizard **collects** the PIN but doesn't apply it.
  - The PIN is applied **inside** database creation.
  - The flag is set only after both succeed.

  Concretely:
  1. `ConfigService.DEFAULTS["setup_completed"] = False`.
  2. In `ConfigService.load()`, when an existing file is loaded **and** has no `setup_completed` key, set it to `True` and mark it changed. Every existing install predates the flag and is already set up. A file created from defaults gets `False`.
  3. In `main.py`:
     - Compute `first_run = not ConfigService.get("setup_completed")` and `db_state = DatabaseSetupService.check_setup_state()` (from #833).
     - If `first_run`, open `SetupWizard(ask_admin_pin=(db_state is SetupState.NEEDS_SETUP))`.
     - **Security rule:** the wizard asks for, and may set, the admin PIN only when a new database is being created in this run. A user who deletes or corrupts `settings.json` on a live shop must not be able to reset the admin PIN through the wizard. Hide the security page when `ask_admin_pin` is False.
  4. `SetupWizard.finish_wizard()` saves shop and printer settings as today, and stores the PIN only on the dialog (`self.admin_pin: str | None`). Remove the `UserService.update_admin_pin` call from the wizard.
  5. Change `create_empty_database(admin_pin: str | None = None)` and `create_demo_database(admin_pin: str | None = None)`:
     - When `admin_pin` is given, the admin user is created with, or updated to, `AuthService.hash_pin(admin_pin)` in the same session as creation.
     - For demo: run the seeder, then in one session update `admin`'s `pin_hash`.
     - If the update finds no admin, raise `RuntimeError`. Never return False silently.
  6. After the DB step succeeds, `ConfigService.set("setup_completed", True)`. If the user cancels the DB dialog, or creation raises, the flag stays False, so the wizard runs again next launch.
  7. When `first_run` is False but `db_state` is `NEEDS_SETUP` (settings exist, DB missing), show only the DB dialog. That's today's behaviour, but without a PIN the admin would be 1234. Make `DatabaseSetupDialog` collect an admin PIN in that case: either reuse the wizard's security page as a standalone `AdminPinDialog`, or show the wizard with only the security page. **Recommended:** extract the PIN page into `cbpos/ui/dialogs/admin_pin_dialog.py`, use it from both places, and reuse the wizard's existing validation (`setup_wizard.py:242-258`: 4–6 digits, confirm match).
  8. Delete or deprecate `UserService.update_admin_pin` if it has no other callers (`graft callers update_admin_pin`).
- *Rejected alternatives:*
  - "Check `os.path.exists(SETTINGS_FILE)` before line 361": fragile, because any future early `ConfigService` call re-breaks it. Also, a settings file deleted on a live shop would re-open the PIN page and allow a PIN reset.
  - "Apply the PIN in the wizard after creating the DB inside the wizard": the UI would own DB creation, breaking MVC.
- *Data/schema:* none. Only a settings key.
- *Sync/network impact:* in network mode, the till's wizard must never set a PIN on the shared PostgreSQL DB unless it created that DB. The `ask_admin_pin` rule covers this.

**Implementation steps.**
1. `config_service.py`: add the `"setup_completed": False` default, and the legacy-file rule in `load()` next to `_migrate_receipt_printer`.
2. `database_setup_service.py`: add the `admin_pin` parameter to both create methods. `create_empty_database` hashes with `AuthService.hash_pin` (it currently uses its own `_hash_pin` at `:27-28`; use `AuthService.hash_pin` so the hashing scheme lives in one place).
3. New `cbpos/ui/dialogs/admin_pin_dialog.py` (`AdminPinDialog(QDialog)`, objectName `AdminPinDialog`):
   - two password fields, the wizard's validation, and `make_dialog_footer`
   - a `pin()` accessor
   - `retranslate_ui()` called in `__init__`
4. `setup_wizard.py`:
   - Add the constructor flag `ask_admin_pin: bool = True`.
   - When False, skip the security page (check how pages are stacked in `__init__` and remove that page from navigation).
   - `finish_wizard` stores `self.admin_pin` and stops calling `UserService`.
5. `main.py`: implement the flow in steps 3, 6 and 7 of the design. Keep `_close_splash()` before any dialog. If `create_*` raises, show `QMessageBox.critical` with `_t("db_setup.create_failed", error=translate_error(str(e)))` and exit without setting the flag.
6. `public-releases-readme.md:139-145`: replace "log in with admin / 1234" with "use the admin PIN you chose in the Setup Wizard. The demo data also has Manager (5678) and Cashier (0000) users for trying things out. Change or deactivate them before real use."
7. Update CLAUDE.md's "Seed Data" line only if it claims something no longer true. `scripts/seed.py` itself is unchanged.

**Tests (write first).**
- `tests/domain/test_database_setup_service.py::test_issue_791_empty_db_uses_given_admin_pin`: `create_empty_database(admin_pin="482913")`. Then `AuthService.verify_pin("482913").username == "admin"` and `verify_pin("1234") is None`. (After #835, use `authenticate_pin`.)
- `::test_issue_791_demo_db_uses_given_admin_pin`: the same, with `create_demo_database`.
- `tests/domain/test_config_service.py::test_issue_791_new_settings_file_is_not_setup_completed` and `::test_issue_791_legacy_settings_file_is_setup_completed`. Point `SETTINGS_FILE` at `tmp_path`. A legacy file is written without the key.
- `tests/domain/test_setup_wizard.py::test_issue_791_wizard_without_pin_page_never_sets_pin` (pytest-qt): `SetupWizard(ask_admin_pin=False)` has no security page, and `admin_pin is None` after finish.

**UI/UX spec.**
- Setup Wizard: unchanged pages when creating a new DB.
- Final page copy (existing keys; re-check that they say this): "This PIN unlocks everything in CB POS. Keep it private."
- `AdminPinDialog`, shown when settings exist but the database is new:
  - title: `admin_pin.title` → "Choose the admin PIN"
  - body: `admin_pin.body` → "This is a new shop database. Choose a 4–6 digit PIN for the admin account. You'll use it to manage users and settings."
  - two fields with the existing `setup_wizard.admin_pin` / `confirm_pin` labels
  - footer `[Save PIN] [Cancel]`. Cancel exits the app: no DB without an admin PIN.
- Enter submits and Esc cancels. Focus starts in the first field.
- Copy the visual pattern of the wizard's security page.
- New error key `db_setup.create_failed` → "Couldn't create the shop database: {error}. Nothing was saved. Close CB POS and try again."
- Run the §0.7 UI gate, including a screenshot of the wizard running on a clean data dir.

**Do NOT.**
- Do not let the wizard or `AdminPinDialog` change the PIN of an **existing** admin.
- Do not keep `1234` as a silent fallback anywhere. If the PIN can't be applied, creation fails.
- Do not call `UserService` or `DatabaseSetupService` from inside `SetupWizard.finish_wizard`.
- Do not set `setup_completed=True` before the database step succeeds.

**Edge cases.**
- The user cancels the wizard: exit, flag stays False.
- The user cancels the DB dialog after the wizard: shop settings are saved but the flag stays False, so the wizard runs again (pre-filled from settings).
- A network till: `db_state` is READY (the Main PC already created the DB), so the wizard runs without the PIN page.
- An existing install upgrading: the legacy rule sets the flag, so no wizard appears.

**Acceptance criteria.**
- [ ] A fresh data dir shows the wizard, then the DB dialog. The wizard's PIN logs in as admin, and `1234` does not, for both Start Fresh and Demo.
- [ ] A PIN application failure shows an error and does not complete setup.
- [ ] Deleting `settings.json` on a live shop shows the wizard **without** a PIN page and does not change any PIN.
- [ ] `public-releases-readme.md` no longer tells users to log in with admin/1234.

**Verify.**
- Run the tests above.
- Manual: `CBPOS` data dir → a fresh temp dir (see `cbpos/config.py` for the dev override, or run from a copy of the repo). Launch and walk the wizard by keyboard only, then log in with the chosen PIN.

**Stop & Ask if.**
- The wizard's page structure makes hiding the security page awkward, needing more than ~40 lines changed:

  QUESTION (#791): Show the admin PIN as a separate dialog after the DB step instead of as a wizard page?
  Recommendation: yes, use `AdminPinDialog` for both paths and remove the page from the wizard. It's the simpler, single path.

---

## Batch 1.2 — Authentication and session ownership

**Branch:** `fix/p1-b2-auth-session` · **Issues:** #835, #857, #856, #859, #860 · **Order:** #835 first (it creates the authentication API the others use), then #857, #856, #859 and #860.

**Design for the whole batch.** After this batch `AuthService` has exactly these public entry points. Write them first, then move every caller onto them.

| Method | Changes `_current_user`? | Audit | Throttled (#856)? | Used by |
|---|---|---|---|---|
| `login(pin) -> User \| None` (rename of `verify_pin`; keep `verify_pin` as a deprecated alias that calls `login`) | yes | `LOGIN` | yes | `LoginView` only |
| `authenticate_pin(pin) -> User \| None` | **no** | `OVERRIDE_AUTH` on success, nothing on failure (the throttle audits failures) | yes | `ManagerOverrideDialog` |
| `check_own_pin(user_id, pin) -> bool` | no | none | yes | `ProfileDialog` (current-PIN check) |
| `logout(reason: str = "LOGOUT") -> None` | sets None | `LOGOUT` or `TIMEOUT` with the real `terminal_id` | n/a | `MainWindow.logout` |
| `is_pin_in_use(pin, exclude_user_id=None) -> bool` | no | none | no | `UserService` (#857) |

All PIN matching goes through **one** private helper, `_match_active_user(session, pin) -> User | None`, so #917 (Phase 5: faster login) can optimise one place later. Keep the legacy SHA-256 → bcrypt migration inside that helper.

### #835 — A manager override permanently logs the manager in

**Severity:** critical · **Size:** M · **Type:** security · **Gate:** agent
**Skills:** systematic-debugging → tdd → ponytail; ponytail-review

**Problem.** When a manager types their PIN to approve one void or price change for a cashier, CB POS actually logs the manager in. From then on:
- every permission check passes silently;
- every sale is stamped with the manager's name;
- shift and audit rows name the wrong person.

The screen still shows the cashier, so nobody notices. The profile dialog has the same flaw: a wrong "current PIN" that belongs to another user switches the session to that user.

**Evidence and root cause.**
- `cbpos/ui/dialogs/manager_override_dialog.py:63`: `user = AuthService.verify_pin(pin)`.
- `auth_service.py:196`: `AuthService._current_user = user` inside `verify_pin`, which also writes a `LOGIN` audit row (`:234-242`).
- `cbpos/ui/dialogs/profile_dialog.py:86`: `verified_user = AuthService.verify_pin(current_pin)`. When `verified_user.id != user.id` it shows "invalid PIN", but the session has already switched.
- Root cause: credential verification and session login are one function.

**Fix design.**
- *Recommended:* split them, as in the batch table above. `authenticate_pin` runs the same match and lockout logic as `login` but never touches `_current_user`. It writes an `AuditLog(event_type="OVERRIDE_AUTH", action="Manager Override Authenticated", user_id=<manager>, details="for <cashier username>")`. Use the current user from `get_current_user()` for `details`.
  - The permission-action audit row that `check_permission_with_override()` already writes stays as is. Confirm it does by reading `permission_helper.py:49-60`. If it doesn't record who approved, add `approved_by_user_id` to the details string.
  - `check_own_pin(user_id, pin)` loads exactly that user and bcrypt-checks only their hash. This also fixes the "wrong user's PIN" switch.
- *Rejected alternatives:* "save `_current_user` and restore it after the dialog" fails if an exception happens between the two steps, and it still writes a false LOGIN row.
- *Data/schema:* none. `event_type` is a free string column; confirm with `graft grep "event_type" --in cbpos/core/models`.
- *Sync/network impact:* audit rows sync like other audit rows (see #903 in Phase 2). Nothing else changes.

**Implementation steps.**
1. In `auth_service.py`:
   - Extract the user-matching loop of `verify_pin` (`:151-176`) into `_match_active_user(session, pin)`.
   - Implement `login`, which is today's body plus `_current_user`. Keep `verify_pin = login` as an alias with a docstring note.
   - Implement `authenticate_pin` and `check_own_pin`.
2. `manager_override_dialog.py:63`: call `AuthService.authenticate_pin(pin)`.
3. `profile_dialog.py:86-90`: call `if not AuthService.check_own_pin(user.id, current_pin):` and show the same `profile.invalid_pin` error.
4. `login_view.py:375`: call `AuthService.login(pin)`.
5. Run `graft callers verify_pin` and confirm that only tests call the alias. Update tests in a separate commit only if their intent was "log in".

**Tests (write first).** Use `tests/domain/test_auth_service_permissions.py` for its existing seeded-roles setup, or a new `tests/domain/test_auth_override.py` modelled on it.
- `test_issue_835_override_does_not_change_current_user`:
  - Given: log in as cashier (PIN `0000`).
  - When: `authenticate_pin("5678")` (manager).
  - Then: `get_current_user().username == "cashier"`.
  - Also: no `AuditLog` row with `event_type="LOGIN"` and `user_id=manager.id`, and exactly one `OVERRIDE_AUTH` row.
- `test_issue_835_sale_after_override_is_cashier_sale`: after the override, complete a sale with `TransactionService` the way an existing sale test does (copy from `tests/domain/test_transaction_service.py`). Assert `sale.cashier_id == cashier.id`.
- `test_issue_835_profile_wrong_users_pin_does_not_switch_session`: logged in as cashier, `check_own_pin(cashier.id, "5678")` is False and the current user is unchanged.

**UI/UX spec.** No visible change, except that the override dialog now prompts again on the next protected action, which is the correct behaviour. Keep the existing dialog. Run the §0.7 UI gate with a quick keyboard walkthrough: line void → override PIN → Enter, then a second void prompts again.

**Do NOT.**
- Do not save and restore `_current_user` around the dialog.
- Do not write a LOGIN audit row for an override.
- Do not make `ProfileDialog` scan all users.

**Edge cases.**
- The manager's PIN is correct but they lack the permission. Today's flow already handles this after authentication (`manager_override_dialog.py:64-74`), and the current user still must not change.
- The override is entered while the terminal is locked out (#856): refuse with the lockout message.

**Acceptance criteria.**
- [ ] After a successful override, `get_current_user()` is still the cashier, and the next protected action prompts again.
- [ ] A sale completed after an override has `cashier_id` equal to the cashier.
- [ ] No `LOGIN` audit row is written for an override.

**Verify.** Run the focused tests. Manually: log in as cashier, void a line with the manager PIN, void a second line, and confirm it asks again.

**Stop & Ask if.** None expected.

### #857 — Duplicate PINs are accepted

**Severity:** high · **Size:** S · **Type:** security · **Gate:** agent
**Skills:** tdd → ponytail

**Problem.** Login uses the PIN alone. If two users share a PIN, CB POS logs in whichever matches first. A cashier given the manager's PIN by mistake, or one who picks the admin's PIN as their own, becomes that user.

**Evidence and root cause.**
- `user_service.py:138-166` (`create_user`), `:169-198` (`update_user`) and `:18-55` (`update_user_profile`) never compare the new PIN against other users.
- Matching returns the first hit in unspecified row order (`auth_service.py:160-167`).

**Fix design.**
- *Recommended:* add `AuthService.is_pin_in_use(pin, exclude_user_id=None)`.
  - It bcrypt-checks the PIN against every **active** user except `exclude_user_id`. Inactive users are excluded because a deactivated user's PIN cannot log in.
  - **Reactivating** a user must re-check their PIN against active users. Uniqueness can't be proven from the stored hash alone (bcrypt needs the plaintext), so in `update_user`, when `is_active` changes False → True, **require a new PIN** and check it with `is_pin_in_use`. The UI asks for a new PIN on reactivation.
  - Call it in `create_user`, in `update_user` (when `pin` is given), and in `update_user_profile` (when `new_pin` is given). On conflict raise `ValueError("pin_in_use")`.
  - The UI maps that to a generic message that doesn't reveal whose PIN it is.
- *Rejected alternatives:* a unique DB index on `pin_hash` doesn't work, because bcrypt salts make every hash different.
- *Data/schema:* none.
- *Sync/network impact:* in network mode users live in the shared DB, so the check covers all tills. In LAN-sync mode users are edited on the Main PC only (Phase 2 owns that).

**Implementation steps.**
1. Add `is_pin_in_use` to `auth_service.py`. Reuse `_verify_against_hash`.
2. `user_service.py`:
   - Call the check in the three methods, before any write.
   - These methods currently return `bool` and swallow exceptions (`except Exception … return False`; read each one). Let `ValueError` propagate **through** that handler: add `except ValueError: raise` before the generic `except`.
   - For reactivation, if `is_active` goes False → True and `pin` is None, raise `ValueError("pin_required_on_reactivate")`.
3. `user_dialog.py` (`~:90-113`) and `profile_dialog.py`:
   - wrap the service call;
   - on `ValueError`, show `QMessageBox.warning` with `_t("users.pin_in_use")` or `_t("users.pin_required_on_reactivate")`;
   - focus the PIN field.

**Tests (write first).** `tests/domain/test_user_service.py` (create it if missing; use the `db_session` fixture and seed roles the way `test_auth_service_permissions.py` does).
- `test_issue_857_create_user_with_existing_pin_raises`.
- `test_issue_857_update_user_to_existing_pin_raises`.
- `test_issue_857_profile_pin_change_to_existing_pin_raises`.
- `test_issue_857_same_user_keeping_own_pin_is_allowed`.
- `test_issue_857_reactivation_requires_new_pin`.

**UI/UX spec.**
- `users.pin_in_use` → "That PIN can't be used. Please choose a different PIN."
- `users.pin_required_on_reactivate` → "Enter a new PIN to turn this user back on."
- The message is shown inline as a warning box over the dialog. The dialog stays open and the PIN field is focused and selected.
- Run the §0.7 UI gate for the User and Profile dialogs.

**Do NOT.**
- Do not tell the user which account owns the PIN.
- Do not compare hashes as strings.
- Do not do the check only in the dialog.

**Edge cases.**
- An inactive user holds the PIN: allowed, because they can't log in, but blocked again at reactivation.
- Legacy SHA-256 hashes: `_verify_against_hash` already handles both formats.

**Acceptance criteria.**
- [ ] Creating, editing or self-changing to a PIN another active user holds is refused with a generic, translated message.
- [ ] `create_user("x", <existing PIN>, ...)` raises `ValueError`.

**Verify.** Focused tests, plus a manual check in User Management.

**Stop & Ask if.** None expected.

### #856 — The login screen has no brute-force lockout

**Severity:** high · **Size:** M · **Type:** security · **Gate:** agent
**Skills:** tdd → migration rules (§0.2 Schema) → ponytail; impeccable (harden) for the locked state

**Problem.** Anyone at the till can try PINs forever. The code has lockout logic and settings for it (`max_login_attempts`, `lockout_duration_seconds`), but they sit in a function nothing calls, so the owner believes protection exists when it doesn't.

**Evidence and root cause.**
- `auth_service.py:169-172`: on no match, `verify_pin` only logs a warning and returns None. It never records the failure.
- The per-user counters (`_record_failed_attempt_db` `:93-106`, `users.failed_login_attempts` / `locked_until` in `cbpos/core/models/__init__.py:86-87`) are used only by `verify_pin_for_user` (`:253-311`), which has no app callers.
- Root cause: PIN-only login can't attribute a failure to a user, so per-user lockout can never work on this path. The throttle has to be **per terminal**.

**Fix design.**
- *Recommended:* a persisted, per-terminal throttle shared by `login`, `authenticate_pin` and `check_own_pin`.
  - New model `LoginThrottle` (table `login_throttle`) in `cbpos/core/models/__init__.py`, with these columns:
    - `terminal_id: str` (primary key)
    - `consecutive_failures: int` (default 0)
    - `locked_until: datetime | None`
    - `updated_at: datetime`
  - Alembic migration `add_login_throttle`: create the table, with a downgrade that drops it. It works on SQLite and PostgreSQL.
  - `AuthService._throttle_check(session) -> int`: returns the remaining lockout seconds for this terminal (`ConfigService.get("terminal_id")`), 0 if not locked.
  - On every PIN attempt:
    1. If locked, return None immediately, without running bcrypt.
    2. On a miss, increment `consecutive_failures`. When it reaches `_get_max_attempts()`, set `locked_until = now + _get_lockout_duration()`, write `AuditLog(event_type="LOCKOUT", user_id=None, terminal_id=…, details="<n> wrong PINs")`, and reset the counter to 0.
    3. On a hit, reset the counter.
  - Add `AuthService.get_terminal_lockout_seconds() -> int` for the UI.
  - Remove the unused `verify_pin_for_user` and `get_remaining_lockout_seconds(username)`. The one test that calls it (`tests/domain/test_auth_service_permissions.py:54`) moves to `login()`. Do that in its own commit with the message "test: drop verify_pin_for_user, which no app code used (#856)".
  - Stop skipping per-user `locked_until` in the match loop. Those columns stay in the schema, unused (no destructive migration).
  - Make `AuditLog.user_id` accept None. Check whether it is nullable: `graft grep "class AuditLog" --in cbpos/core/models`. If it isn't nullable, put the LOCKOUT row under `user_id` of no one... **Stop & Ask** (pre-written below).
- *Rejected alternatives:*
  - An in-memory counter: an app restart resets it.
  - `settings.json`: easy to delete, and not in the audit trail.
  - Per-user lockout: impossible to attribute on PIN-only login.
- *Data/schema:* new table plus migration. Add it to `create_empty_database()`. `create_all` covers it automatically; confirm the model is imported.
- *Sync/network impact:* in network mode the row lives in the shared DB, keyed by terminal, which is correct. LAN sync: local-only table. Exclude it from sync (confirm the sync service syncs an explicit list of tables; if not, note it for Phase 2).

**Implementation steps.**
1. Add the model and migration (`uv run alembic revision -m "add login_throttle"`, written by hand). Run `alembic upgrade head` on a seeded copy.
2. Add the throttle helpers to `auth_service.py`, and call them inside `login`, `authenticate_pin` and `check_own_pin` via the shared match path.
3. `login_view.py` (around `:370-390`): when `login` returns None, check `AuthService.get_terminal_lockout_seconds()`.
   - If it is > 0, disable the PIN pad and input, show `_t("login.locked", seconds=…)`, and start a 1-second `QTimer` that counts down and re-enables at 0.
   - Otherwise show the existing wrong-PIN message, with `_t("login.attempts_left", count=…)` once 2 or fewer attempts remain. That needs `AuthService.get_terminal_failures_remaining()`.
4. In `manager_override_dialog.py` and `profile_dialog.py`, show the same `login.locked` message when locked.
5. Fix the `AuthService` class docstring so it describes the real behaviour.

**Tests (write first).** `tests/domain/test_auth_lockout.py`.
- `test_issue_856_correct_pin_refused_after_max_failures`: set `max_login_attempts=3` via monkeypatched `ConfigService.get`, make 3 wrong `login()` calls, then the correct PIN returns None.
- `test_issue_856_lockout_expires`: freeze time with monkeypatched `datetime` in auth_service, or set `locked_until` in the past directly. The correct PIN then works.
- `test_issue_856_lockout_persists_across_restart`: after lockout, reset `AuthService` class state (simulating a restart). The row is still there and the correct PIN is still refused.
- `test_issue_856_lockout_writes_audit_row`.
- `test_issue_856_override_attempts_count_toward_lockout`: wrong `authenticate_pin` calls lock the terminal.

**UI/UX spec.**
- Login view locked state:
  - The PIN input and keypad are disabled (grey, using the existing disabled QSS). The error label shows `login.locked` → "Too many wrong PINs. Try again in {seconds} seconds.", updated every second.
  - When it reaches 0, re-enable, clear the message and focus the PIN input.
- `login.attempts_left` → "Wrong PIN. {count} tries left before this till locks."
- Keep the existing wrong-PIN shake or colour behaviour if there is one.
- In si/ta, check that the countdown label doesn't clip at 1366×768.
- Run the §0.7 UI gate, including a screenshot of the locked state in both themes.

**Do NOT.**
- Do not run bcrypt while locked out.
- Do not reveal whether a PIN "almost" matched.
- Do not count lockouts per user.
- Do not store the counter in memory only.

**Edge cases.**
- Clock change (the till's time set back): `locked_until` far in the future. Cap the remaining time at `lockout_duration` (`min(remaining, duration)`).
- `max_login_attempts` set to 0 or garbage: `_get_max_attempts` falls back to 5. Keep that behaviour.

**Acceptance criteria.**
- [ ] After `max_login_attempts` wrong PINs, the correct PIN is refused until the lockout expires, and the login screen shows the remaining time.
- [ ] The lockout survives an app restart and is written to `AuditLog`.
- [ ] Override and profile PIN attempts count toward the same lockout.

**Verify.** Focused tests, `alembic upgrade head` on a copy of a seeded DB, then manually enter 5 wrong PINs and watch the countdown.

**Stop & Ask if.**
- `AuditLog.user_id` is NOT NULL:

  QUESTION (#856): LOCKOUT audit rows have no user. Make `audit_logs.user_id` nullable (migration), or attribute them to the Admin user?
  Recommendation: make it nullable. Attributing a stranger's attempts to the Admin pollutes the audit trail.

### #859 — The last active Admin can be deactivated or demoted

**Severity:** high · **Size:** S · **Type:** data-integrity · **Gate:** agent
**Skills:** tdd → ponytail

**Problem.** An owner who is the only Admin can untick "Active" on themselves or switch themselves to Cashier, and the change is saved. After that nobody can manage users, roles, settings or restores. The only way back is editing the database by hand.

**Evidence and root cause.**
- `user_service.py:169-198` (`update_user`) writes `role_id` and `is_active` with no guard.
- `RoleService` protects the Admin **role** (`role_service.py:77,121`, `ADMIN_ROLE_NAME`), but nothing protects the last Admin **user**.

**Fix design.**
- *Recommended:* in `update_user`, before writing, check whether this change would leave zero active Admins:
  - the user is currently active with `role.name == ADMIN_ROLE_NAME`, and
  - after the change they would not be (deactivated or a different role), and
  - `count(active users whose role is Admin, excluding this user) == 0`.

  If so, raise `ValueError("last_admin")`. Import `ADMIN_ROLE_NAME` from `role_service`. Apply the same guard in any user-delete path; run `graft grep "session.delete(user" --in cbpos/core/services`.
- *Rejected alternatives:* disabling the controls in the dialog only is a UI-only guard (§0.3). Do the dialog part as well, as UX.
- *Data/schema:* none.

**Implementation steps.**
1. Add the guard in `update_user`, and let `ValueError` propagate through the generic handler, as in #857.
2. `user_dialog.py:68-73` and `:90-113`:
   - map `ValueError("last_admin")` to `_t("users.last_admin")`;
   - also proactively disable the Active checkbox and role combo when editing the only active Admin, with a tooltip explaining why. That needs `UserService.is_last_active_admin(user_id) -> bool`.

**Tests (write first).** `tests/domain/test_user_service.py`.
- `test_issue_859_sole_admin_cannot_be_deactivated`.
- `test_issue_859_sole_admin_cannot_be_demoted`.
- `test_issue_859_one_of_two_admins_can_be_deactivated`.

**UI/UX spec.**
- `users.last_admin` → "This is the only active Admin. Make another user an Admin first, then you can change this one."
- The same text is the tooltip on the disabled Active checkbox and role combo.
- Run the §0.7 UI gate on the User dialog in both themes.

**Do NOT.** Do not count inactive Admins, and do not count users whose role merely has admin-like permissions. The rule is about the Admin role, which `PermissionService` keeps fully privileged.

**Edge cases.** An Admin renaming themselves: allowed. Changing their PIN: allowed.

**Acceptance criteria.**
- [ ] Deactivating or demoting the only active Admin is refused with a translated message, and the controls are disabled up front.
- [ ] With two active Admins, one can be deactivated or demoted.

**Verify.** Focused tests, plus a manual check in User Management.

**Stop & Ask if.** None expected.

### #860 — Logout and session timeout don't end the session

**Severity:** high · **Size:** M · **Type:** security · **Gate:** agent (the cart behaviour below has a recommended default; apply it)
**Skills:** systematic-debugging → tdd (pytest-qt) → ponytail; impeccable (harden)

**Problem.** Logout, shift close and the idle timeout only switch to the login screen. Several things then go wrong:
- The signed-in user stays signed in inside `AuthService`, and no logout is recorded.
- A dialog left open (payment, refund, restore, user edit) stays usable on top of the login screen under the old user. The idle lock does nothing in exactly the case it exists for.
- The next cashier inherits the previous cashier's cart, including manager-approved price overrides, and finishes it under their own name.
- The timeout audit row always says `TERM-01`.

**Evidence and root cause.**
- `cbpos/ui/main_window.py:187-195` (`logout`) sets `self.user = None`, stops the watchdog and switches the stack. Nothing else.
- `AuthService.logout()` (`auth_service.py:319-340`) has no callers.
- No `QApplication.activeModalWidget()` handling exists.
- `SalesView` has no logout hook, so the cart lives on in `cart_service`.
- `cbpos/infrastructure/session_watchdog.py:105` uses `terminal_id="TERM-01"`. The infrastructure layer also writes AuditLog directly (`:92-108`), duplicating AuthService.

**Fix design.**
- *Recommended:* one session-end sequence, owned by `MainWindow.logout(reason="LOGOUT")`:
  1. **Close modals.** `while (w := QApplication.activeModalWidget()) is not None: w.reject()`.
     - Guard against a dialog that refuses to close: try at most 10 iterations, then `w.close()`; log any that stay open.
     - Also close non-modal top-level dialogs owned by this window: `for w in QApplication.topLevelWidgets(): if isinstance(w, QDialog) and w.isVisible(): w.reject()`.
  2. **Protect the cart.** Call `self.sales_view.end_session(reason)`. If the cart has items, it holds the bill through the existing `SuspendedTransactionService.hold_bill(cart_service)`, with a note "Auto-held at sign-out (<username>)", then clears the cart and customer.
     - **Recommended default (apply it):** auto-hold on both logout and timeout. Nothing is lost, and the next cashier starts empty.
     - The held bill keeps its lines. #804 (Phase 3B) makes held bills preserve discounts and overrides. Until then, overrides are dropped on recall, which is the safe direction.
  3. **End the auth session.** `AuthService.logout(reason)` writes `LOGOUT` or `TIMEOUT` with `ConfigService.get("terminal_id")` and clears `_current_user`.
  4. Then do what the method already does (clear `self.user`, side menu, stop the watchdog, show the login view).
  - `SessionWatchdog.on_timeout()` stops writing AuditLog itself and just emits `session_expired`. Connect that signal (`graft grep "session_expired"`) to a bound method `self._on_session_expired`, which calls `self.logout(reason="TIMEOUT")`.
- *Rejected alternatives:*
  - "Clear the cart": loses a customer's half-scanned basket when the cashier steps away.
  - "Leave it for the next user": that is the bug.
- *Data/schema:* none. Check that `SuspendedTransaction` has a note field (`graft grep "class SuspendedTransaction"`). If not, skip the note; don't add a column in this batch.
- *Sync/network impact:* none.

**Implementation steps.**
1. `auth_service.py`: `logout(reason: str = "LOGOUT")`. Set `event_type=reason` and `action` to "User Logout" or "Session Timeout".
2. `session_watchdog.py:87-114`: remove the DB write and keep `stop_monitoring()` plus `emit`.
3. `sales_view.py`: add `end_session(self) -> None`. If `self.cart_service.items` is non-empty, call `SuspendedTransactionService.hold_bill(self.cart_service)`; on success clear the cart, customer and display (reuse the body of `hold_bill()` at `:1086-1104` minus the info box). On failure log an error and still clear, because session security wins. The bill can't be saved, so tell the next login by writing a warning to the log; that's acceptable.
4. `main_window.py`: implement the sequence and wire `watchdog.session_expired` to it with reason TIMEOUT. Find where logout is triggered from shift close and the logout button (`graft callers logout --in cbpos/ui`). Each one passes the right reason.

**Tests (write first).** `tests/domain/test_session_end.py` (pytest-qt; copy the `MainWindow` construction from an existing main-window test such as `tests/ui/test_app_restart.py`, or the nearest test that builds `MainWindow`).
- `test_issue_860_logout_clears_auth_and_writes_audit`: after `main_window.logout()`, `AuthService.get_current_user() is None`, and a `LOGOUT` row exists with the configured `terminal_id` (set it to `"TILL-7"` in the test).
- `test_issue_860_timeout_closes_open_modal`: open a `QDialog` with `.open()` (modal), trigger `watchdog.on_timeout()`, then `qtbot.waitUntil(lambda: not dlg.isVisible())`, and check a `TIMEOUT` audit row with the right terminal.
- `test_issue_860_next_user_starts_with_empty_cart`: add an item, logout, and assert `cart_service.items == []` and that one suspended transaction exists.

**UI/UX spec.**
- On the login screen after an auto-hold, show a one-line info note above the PIN field: `login.bill_held` → "The open bill was saved as Held Bill #{id}. Recall it with F7." It shows until the next login.
- No modal on logout.
- Run the §0.7 UI gate: timeout with the Payment dialog open must land on a clean login screen with the note.

**Do NOT.**
- Do not write audit rows from `session_watchdog.py`.
- Do not hard-code `TERM-01` anywhere. Run `graft grep "TERM-01"` and leave a comment in the PR listing the other occurrences for Phase 2 (#867).
- Do not connect `destroyed` to a lambda.
- Do not discard a non-empty cart.

**Edge cases.**
- Logout during a running print or worker thread: closing a dialog must not delete a QThread still running. Check `dlg.reject()` paths in the payment dialog for worker cleanup.
- Timeout while a `QMessageBox` is open: it's an active modal, so the loop handles it.
- Shift-close logout: the reason is LOGOUT.

**Acceptance criteria.**
- [ ] After logout or timeout, `get_current_user()` is None, and a LOGOUT or TIMEOUT row exists with the right `terminal_id`.
- [ ] A timeout with a modal dialog open closes the dialog.
- [ ] The next user does not inherit the previous user's cart; it's held and can be recalled.

**Verify.** Focused tests. Manually: set the idle timeout to 1 minute, open Payment, wait, and confirm the login screen, the held-bill note and that F7 recalls the bill after logging back in.

**Stop & Ask if.** The owner prefers discarding to holding. This defaults to holding, so don't block on it; mention it in the PR.

---

## Batch 1.3 — Migration, settings, backup and restore safety

**Branch:** `fix/p1-b3-migration-backup-restore` · **Issues:** #837, #838, #875, #874, #839, #873

**Order:**
1. #837 extracts the migration logic into a service. #874 and #873 reuse it.
2. #838 then #875: settings durability, then secrets.
3. #874: version check on restore.
4. #839: network-mode refusal.
5. #873: the post-restore sequence, which ties it all together.

**Shared refactor (do it inside #837).** Move `run_migrations()` from `main.py:110-183` into a new `cbpos/core/services/schema_migration_service.py`:
- `class SchemaMigrationService` (**not** the existing `cbpos/core/services/migration_service.py` / `MigrationService`, which copies data from SQLite to PostgreSQL for the Network Settings page; leave that file alone and don't reuse its name) with `migrate_to_head(db_uri: str, status=None) -> None`, which raises `MigrationError(code, detail)` instead of returning a string.
- `current_revision(db_uri) -> str | None`.
- `known_revisions() -> set[str]`.

`main.py` keeps a thin `run_migrations()` wrapper that calls it and preserves today's return contract (`str | None`), so the startup error box at `main.py:~407-419` is unchanged. Phase 2 (#799) extends this service to PostgreSQL. Keep it engine-agnostic: take a URI, don't hard-code `Config.DB_URI`.

### #837 — A database without an `alembic_version` table is stamped at head and its migrations are skipped

**Severity:** high · **Size:** M · **Type:** bug (data/upgrade) · **Gate:** agent
**Skills:** systematic-debugging → tdd → migration rules (§0.2 Schema); ponytail-review

**Problem.** Shops on v1.2.2 have a database that was never versioned. When they update, or restore a v1.2.2 backup, CB POS assumes the database is already current and skips 91 schema changes. Login and sales then fail with "no such column", and the failed user count used to trigger the setup dialog (#833, now fixed in 1.1).

**Evidence and root cause.**
- `main.py:154-163`: `if not has_version_table: command.stamp(alembic_cfg, "head")`.
- Release history (from `git tag`): only `v1.2.2` and `v1.3.0` have shipped.
  - `v1.2.2` has no `run_migrations` and builds its DB with `create_all()`, unstamped. Its migration head is `b41b19d9b69a` (`alembic/versions/b41b19d9b69a_add_tax_id_to_customer.py`).
  - `v1.3.0` stamps. So an unversioned DB with tables can only be a v1.2.2 DB, or a developer DB created with `create_all()` at the current head.
- Root cause: "no version table" is treated as "current schema".

**Fix design.**
- *Recommended:* evidence-based baseline detection in `SchemaMigrationService.migrate_to_head`:
  1. **No tables at all**: `create_all` happens elsewhere, so stamp head. That's today's behaviour for a brand-new DB.
  2. **Tables, no `alembic_version`**: fingerprint the schema.
     - **v1.2.2 fingerprint:** `users` exists **and** lacks the column `failed_login_attempts` **and** `sales` lacks `loyalty_points_earned`. Verify these two columns were added after `b41b19d9b69a`: `git log --diff-filter=A -- alembic/versions` plus a grep for the column names in `alembic/versions/*.py`, and pick 2–3 columns that all come from post-v1.2.2 migrations. On a match, stamp `b41b19d9b69a`, then `upgrade head`.
     - **Current-schema fingerprint:** run `alembic.autogenerate.compare_metadata(MigrationContext, Base.metadata)`. If it returns `[]`, the schema already matches head, so stamp head.
     - **Anything else:** raise `MigrationError("unknown_schema", <first 5 diffs>)`. Fail closed, never stamp.
  3. **Version table present**: today's logic. Also handle an **unknown** revision (not in `ScriptDirectory`) by raising `MigrationError("newer_version")`. #874 relies on this.
- Keep a module constant `V1_2_2_HEAD = "b41b19d9b69a"` with a comment saying how it was determined.
- *Rejected alternatives:*
  - "Always upgrade from base": recreating existing tables fails.
  - "Stamp head and run `create_all`": misses column changes and data migrations.
- *Data/schema:* no new migration. The logic runs existing ones.
- *Sync/network impact:* none in this batch. PostgreSQL migration is #799.

**Implementation steps.**
1. Create `schema_migration_service.py` (move the code; keep the Alembic config setup lines `main.py:147-151` identical, including `configure_logger=False`).
2. Implement the fingerprint branch and the unknown-revision check.
3. Make `main.py:run_migrations()` a wrapper that translates `MigrationError` into the existing string return. For `newer_version` and `unknown_schema`, the startup box at `main.py:~407-419` must show a translated message:
   - `startup.migration_newer_version` → "This shop's data was saved by a newer version of CB POS. Install the latest CB POS to open it. Your data has not been changed."
   - `startup.migration_unknown_schema` → "CB POS doesn't recognise this database's layout, so it has stopped to keep your data safe. Restore a backup or contact support."

   Check how that box builds its text today, and keep the existing key for the generic case.
4. Add `SchemaMigrationService` to the graph (`graphify update .`) and update CLAUDE.md's startup flow line only if needed.

**Tests (write first).** `tests/domain/test_schema_migration_service.py`.
- `test_issue_837_unstamped_v122_db_upgrades_to_head`: build a v1.2.2 DB. The most faithful way is to `git show v1.2.2:cbpos/core/models/__init__.py` into a fixture module under `tests/fixtures/models_v122.py` and `create_all` with it into a `tmp_path` SQLite file. After `migrate_to_head`, `compare_metadata(...) == []` and `current_revision == head`.
- `test_issue_837_empty_db_is_stamped_head`.
- `test_issue_837_unstamped_current_schema_is_stamped_head`: `Base.metadata.create_all` then migrate gives head, with no error.
- `test_issue_837_unknown_schema_raises`: drop a table from an otherwise current DB, remove `alembic_version`, and assert `MigrationError("unknown_schema")`.

**UI/UX spec.** Only the two startup messages above. Check they fit the existing error box in si/ta. Run the §0.7 UI gate on the box.

**Do NOT.**
- Do not stamp head when tables exist without proof.
- Do not edit any existing migration file.
- Do not import the current models into the v1.2.2 fixture; it must reflect the old schema.

**Edge cases.**
- A v1.2.2 DB with a partially-applied manual change: falls to `unknown_schema`, fail closed.
- A 0-table DB file: case 1.

**Acceptance criteria.**
- [ ] An unstamped DB built from the v1.2.2 models ends at head with `compare_metadata(...) == []`.
- [ ] An empty or new DB is still stamped at head directly.
- [ ] An unrecognised schema stops startup with a translated message and changes nothing.

**Verify.**
- Focused tests.
- Manually: `git worktree add /tmp/v122 v1.2.2`, run it once to create a DB, copy that DB into a dev data dir, start the current app, and log in.

**Stop & Ask if.** None expected.

### #838 — A corrupt or empty settings.json silently becomes defaults and the next save overwrites it

**Severity:** high · **Size:** M · **Type:** bug (data) · **Gate:** agent
**Skills:** tdd → ponytail

**Problem.** Power cuts are common in Sri Lankan shops. One during a settings save can leave `settings.json` empty or garbled. CB POS then quietly uses defaults, and the first small change (even collapsing the sidebar) writes those defaults over the shop's real settings. The effects:
- A network till drops to standalone.
- VAT is switched off and the VAT number is lost.
- The printer and shop details disappear.

**Evidence and root cause.**
- `config_service.py:320-322`: `except Exception as e: logger.error(... "Using defaults.") ; cls._settings = cls.DEFAULTS.copy()`. Nothing is preserved, and the next `save()` overwrites.
- `_write_restricted` (`config_service.py:~196-206`) writes, then calls `os.replace`, without `flush()`/`os.fsync()`, so the rename can land before the data reaches disk.

**Fix design.**
- *Recommended:*
  1. **Durable write.** In `_write_restricted`, after `f.write(content)`: `f.flush(); os.fsync(f.fileno())`, then `os.replace`. On POSIX, also fsync the directory (`os.open(directory, os.O_RDONLY)`, `os.fsync`, `os.close`, all in `contextlib.suppress(OSError)`; skip on Windows, where `os.open` of a directory fails).
  2. **Last-good copy.** In `save()`, after a successful write, copy the file to `settings.json.bak` using `_write_restricted`, so it is atomic and restricted too.
  3. **Quarantine on load failure.** In `load()`, when parsing fails:
     - rename the bad file to `settings.json.corrupt-<YYYYmmdd-HHMMSS>`;
     - if `settings.json.bak` exists and parses, load it, log a warning, and write it back as `settings.json`;
     - otherwise use `DEFAULTS`, set `cls._loaded_from_defaults_after_failure = True`, and **do not** set `setup_completed` (from #791: the wizard runs again, without the PIN page, because the DB exists).
  4. Add `ConfigService.recovery_notice() -> str | None`. It returns `"restored_from_backup"` or `"defaults_after_corruption"` once, so `MainWindow` can show a one-time notice after login.
- *Rejected alternatives:* "Refuse to start on corrupt settings" leaves the shop unable to work. Quarantining and restoring from `.bak` is safer and keeps them running.
- *Data/schema:* none.

**Implementation steps.**
1. Edit `_write_restricted`, `save` and `load` as above.
2. Add `recovery_notice`, and call it in `MainWindow` after the first login. Find where `MainWindow` handles `login_successful`, and show the notice once with `QMessageBox.warning`.
3. Make sure the `.bak` and `.corrupt-*` files are **not** treated as settings anywhere else (`graft grep "settings.json"`). Backup (`backup_service.py`) should include only `settings.json`.

**Tests (write first).** `tests/domain/test_config_service.py`; point `SETTINGS_FILE` at `tmp_path` via monkeypatch, and reset `ConfigService._settings` between tests.
- `test_issue_838_zero_byte_settings_quarantined_and_bak_used`.
- `test_issue_838_garbage_settings_without_bak_keeps_corrupt_copy`: after load, then `set("sidebar_collapsed", True)`, the `.corrupt-*` file still contains the original garbage.
- `test_issue_838_write_fsyncs_before_replace`: monkeypatch `os.fsync` and `os.replace` to record their call order. Assert `fsync` comes before `replace`.

**UI/UX spec.**
- One-time notice after login.
- `settings.recovered_from_backup` → "Your settings file was damaged, so CB POS loaded the last good copy. Please check your shop details and printer in Settings."
- `settings.reset_after_corruption` → "Your settings file was damaged and no good copy was found. CB POS started with default settings. Please re-enter your shop details, printer and tax settings in Settings. The damaged file was kept as {filename}."
- Run the §0.7 UI gate.

**Do NOT.**
- Do not delete the corrupt file.
- Do not write `.bak` from a defaults-after-failure state. The `.bak` must stay the last *good* file, so skip the `.bak` copy while `_loaded_from_defaults_after_failure` is True.

**Edge cases.**
- A read-only data dir: the rename fails, so log it and continue with defaults in memory, without overwriting (skip `save()` while the flag is set and the rename failed).
- A `.bak` that is also corrupt: treat it as no `.bak`.

**Acceptance criteria.**
- [ ] A 0-byte or garbage `settings.json` is kept as a `.corrupt-*` copy, and values come from `.bak` when one exists.
- [ ] `_write_restricted` calls `os.fsync` before `os.replace`.
- [ ] The owner is told once, in their language.

**Verify.** Focused tests. Manually: truncate `settings.json` on a dev data dir, start the app, and check the notice and restored values.

**Stop & Ask if.** None expected.

### #875 — Restoring on a replacement PC turns encrypted secrets into ciphertext, then double-encrypts them

**Severity:** medium · **Size:** S · **Type:** bug (data) · **Gate:** agent
**Skills:** tdd → ponytail

**Problem.** Backups carry `settings.json`, whose passwords (SMTP, sync secret, network DB password) are encrypted with a key that stays on the old PC. Restoring on a new PC makes CB POS use the encrypted gibberish as the password: emails fail and every till is rejected. The next save encrypts the gibberish again, so the values are lost for good. Nobody is told.

**Evidence and root cause.**
- `config_service.py:244-256` (`_decode_sensitive`): on `InvalidToken` it tries base64, and on failure `return value`, which is the raw ciphertext.
- `load()` (`:312-314`) stores that as the plaintext. `save()` re-encrypts it.

**Fix design.**
- *Recommended:*
  - When decryption fails, return `""` and record the key name in `cls._undecryptable_keys: set[str]`.
  - Keep the legacy base64 fallback **only** when the value doesn't look like a Fernet token (Fernet tokens start with `gAAAAA`). That handles really old base64-encoded values.
  - Add `ConfigService.secrets_needing_reentry() -> list[str]`.
  - After login (the same place as the #838 notice), show which settings to re-enter, with a button that opens Settings on the right tab if a navigation API exists (`graft grep "def open_settings"`); otherwise just the message.
  - When the user saves a new value for a key, remove it from the set.
- *Rejected alternatives:* "Include the encryption key in the backup" defeats the encryption for anyone holding a backup.
- *Data/schema:* none.

**Implementation steps.**
1. Change `_decode_sensitive` and `load()`.
2. In `set()`, discard the key from `_undecryptable_keys` when a sensitive key is set to a non-empty value.
3. Add the post-login notice.

**Tests (write first).**
- `test_issue_875_foreign_key_secret_decodes_to_empty`: encrypt with a different Fernet key, write to the settings file, load, and assert `get("smtp_pass") == ""` and that `"smtp_pass"` is in `secrets_needing_reentry()`.
- `test_issue_875_save_does_not_double_encrypt`: after that load, `save()`. The stored `smtp_pass` decrypts (with the current key) to `""`, not to a token.
- `test_issue_875_legacy_base64_value_still_decodes`.

**UI/UX spec.**
- `settings.secrets_reentry` → "These saved passwords couldn't be read on this computer and need to be entered again: {names}. Open Settings to re-enter them."
- `{names}` are the translated field labels: reuse the existing settings label keys, joined with ", ".
- Run the §0.7 UI gate.

**Do NOT.** Do not return ciphertext as plaintext. Do not log the values.

**Edge cases.** All three secrets blank on a fresh install: the set is empty, so no notice.

**Acceptance criteria.**
- [ ] A settings file encrypted with another key gives `get("smtp_pass") == ""`, and `save()` writes no double-encrypted value.
- [ ] The user is told which secrets to re-enter.

**Verify.** Focused tests.

**Stop & Ask if.** None expected.

### #874 — A backup from a newer app version is accepted, and then the app refuses to start

**Severity:** medium · **Size:** S · **Type:** bug (data) · **Gate:** agent
**Skills:** tdd → ponytail

**Problem.** Restoring, on an older CB POS, a backup made by a newer version "succeeds". The app then can't start, and the only screen that can undo the restore can't be reached. The shop stays down until someone swaps files by hand.

**Evidence and root cause.**
- `backup_service.py:373-393` (`_validate_database`) checks integrity and four table names only, never `alembic_version`.
- `verify_backup` (`:603-645`) uses the same check.

**Fix design.**
- *Recommended:* in `_validate_database`, after the table check, read `SELECT version_num FROM alembic_version` (if the table exists).
  - If a revision is **not** in `SchemaMigrationService.known_revisions()` (from #837), raise `BackupError("newer_version", <rev>)`.
  - If the table is missing, accept it: #837 handles unstamped v1.2.2 DBs on the next start.
  - The restore aborts before the snapshot or any file is touched, because `_validate_database` already runs first (`:254`).
- *Rejected alternatives:* "Downgrade on restore" isn't possible safely.
- *Data/schema:* none.

**Implementation steps.**
1. Change `_validate_database`.
2. Add the i18n key for code `newer_version`, using the existing `BackupError` → message mapping in the data_safety UI. Find it with `graft grep "error_not_a_backup"`, and follow the same pattern for `data_safety.error_newer_version`.

**Tests (write first).** In `tests/ui/test_backup_restore_safety.py` (existing; reuse its helpers in `tests/backup_helpers.py`):
- `test_issue_874_restore_refuses_unknown_revision`: make a backup whose DB has `alembic_version` set to `'f9e8d7c6b5a4'`. `restore_backup` raises `BackupError` with code `newer_version`, and the live DB file's bytes are unchanged.
- `test_issue_874_verify_backup_reports_newer_version`.

**UI/UX spec.**
- `data_safety.error_newer_version` → "This backup was made by a newer version of CB POS. Update CB POS on this computer first, then restore it. Nothing was changed."
- Run the §0.7 UI gate on the restore error state.

**Do NOT.** Do not take the safety snapshot before validation. Order matters.

**Edge cases.** An older backup (a known revision) is accepted, and #873 migrates it.

**Acceptance criteria.**
- [ ] A backup with an unknown Alembic revision is refused by `restore_backup` and `verify_backup(deep=True)`, and the current data is unchanged.
- [ ] `data_safety.error_newer_version` exists in en/si/ta.

**Verify.** Focused tests.

**Stop & Ask if.** None expected.

### #839 — Backup, restore and maintenance work on the local SQLite file in network mode

**Severity:** high · **Size:** M · **Type:** bug (data) · **Gate:** agent
**Skills:** tdd → ponytail; impeccable (harden, clarify) for the Data Safety notice

**Problem.** On a till or Main PC that uses the shared PostgreSQL database, "Backup saved" every night actually saves an old, unused local file. After a server disk failure every backup is worthless. Restore also "succeeds" without touching the real data, and maintenance crashes.

**Evidence and root cause.**
- `backup_service.py:96` and `:247` both use `db_file = Config.DATA_DIR / "cbpos.db"` regardless of `db_mode`.
- `_copy_database` (`:162`) uses `sqlite3`.
- `maintenance_service.py` calls `raw_conn.execute("VACUUM")`, which doesn't exist on psycopg2.
- `grep -rn db_mode cbpos/ui/views/data_safety cbpos/core/services/backup_service.py` returns nothing.

**Fix design.**
- *Recommended (this phase):* refuse honestly.
  - Add `BackupService._require_standalone()`. It raises `BackupError("network_mode")` when `ConfigService.get("db_mode") == "network"`. Call it first in `create_backup`, `run_auto_backup`, `restore_backup` and `verify_backup(deep=True)`.
  - Add the same check (raising a `MaintenanceError("network_mode")`, or reusing the existing error type there) to `vacuum_database`, `integrity_check` and `get_database_info` in `maintenance_service.py`.
  - The auto-backup on close (`main_window.py:~317-331`) must skip silently in network mode, with an info log line. It must **not** report success.
  - Data Safety UI: when in network mode, replace each tab's action area with a notice card (the enterprise card pattern from the Data Safety maintenance tab).
- Real PostgreSQL backup (`pg_dump`) is a feature. Record it as a follow-up issue (§0.9) labelled `enhancement`, `area:multi-terminal`, and reference it in the PR. Don't build it here.
- *Rejected alternatives:* backing up the local file "as well" still misleads.
- *Data/schema:* none.

**Implementation steps.**
1. Add the guards in the services.
2. In `cbpos/ui/views/data_safety/*` tabs, check `DatabaseSetupService`/`ConfigService` mode through a small service query, `BackupService.is_supported() -> bool` (the UI must not read `db_mode` itself, so keep the rule in the service). Show the notice card instead of the actions when it is False.
3. `main_window.py` auto-backup on close: `if not BackupService.is_supported(): return`.

**Tests (write first).** `tests/domain/test_backup_service.py`:
- `test_issue_839_network_mode_create_backup_refused`: monkeypatch `db_mode` to `network`. `create_backup` raises code `network_mode`, and the destination dir is empty.
- `test_issue_839_network_mode_restore_refused`: the local `cbpos.db` bytes are unchanged.
- `test_issue_839_network_mode_auto_backup_refused`.
- `tests/domain/test_maintenance_service.py::test_issue_839_network_mode_vacuum_refused`.

**UI/UX spec.**
- Notice card on each Data Safety tab in network mode, using the icon `icons.info` or the closest existing one in `cbpos/ui/resources/icons.py`.
- Title `data_safety.network_mode_title` → "Backups are made on the database server".
- Body `data_safety.network_mode_body` → "This computer uses the shared shop database on {host}. Back up that database on the server itself (for example with pg_dump or your server's backup tool). Backing up here would only copy an old local file, so it's turned off."
- No action buttons. The `{host}` value comes from a service getter, not from the UI reading settings.
- Run the §0.7 UI gate with screenshots of the card in both themes.

**Do NOT.**
- Do not show "Backup saved" in network mode.
- Do not try `pg_dump` in this batch.
- Do not let the UI branch on raw settings.

**Edge cases.** Switching from network back to standalone: the guards lift and the local file is used again, which is correct.

**Acceptance criteria.**
- [ ] With `db_mode=network`, `create_backup`, `run_auto_backup` and `restore_backup` raise `BackupError("network_mode")` and write nothing.
- [ ] The Data Safety tabs show the network-mode notice instead of actions.
- [ ] Maintenance actions refuse in network mode without crashing.
- [ ] A follow-up issue for a real PostgreSQL backup is filed.

**Verify.** Focused tests. Manually: set `db_mode` to network in a dev settings copy (no server needed), open Data Safety, and check the cards.

**Stop & Ask if.** None expected.

### #873 — After a restore the app keeps running with stale settings and an unmigrated schema

**Severity:** medium · **Size:** M · **Type:** bug (data) · **Gate:** agent
**Skills:** systematic-debugging → tdd → ponytail; impeccable (clarify) for the restart message

**Problem.** After a restore, CB POS only *suggests* a restart. Until the user restarts:
- any small action (collapsing the sidebar, changing the dashboard dates) writes the old in-memory settings over the restored file, silently undoing the restore;
- an older backup's database is used unmigrated, so sales fail with "no such column".

**Evidence and root cause.**
- `backup_service.py:284-289` copies `settings.json` to disk but never resets `ConfigService._settings`.
- Any `ConfigService.set()` (e.g. `collapsible_sidebar.py:254`, `dashboard_view.py:594`, `scheduler_service.py:83`) then saves the stale dict.
- `restore_tab.py:245-256` only recommends a restart.
- No migration runs on the restored DB.

**Fix design.**
- *Recommended:* restore ends in a controlled restart. Nothing runs in between.
  1. In `restore_backup`, after the files are replaced:
     - `ConfigService.reload()` (new: clear `_settings` and `_fernet`, re-run `load()`, which also runs #875's decode handling for the restored file);
     - then `ConfigService.freeze_writes()` (new: a class flag that makes `save()` log and return without writing until the process exits);
     - then `SchemaMigrationService.migrate_to_head(Config.DB_URI)` (from #837) on the restored DB. If migration raises, put the safety snapshot back: restore it with the same `_replace_database` path, and raise `BackupError("migration_failed")`.
  2. `restore_backup` returns normally. The UI (`restore_tab.py`) must then **force** a restart:
     - show one information box: "Restore complete. CB POS will now restart.", with only an OK button;
     - then call `restart_application(self.window())` from `cbpos/ui/app_restart.py:29`;
     - if restart fails, show "Please close and reopen CB POS now" and disable the main window (`self.window().setEnabled(False)`), so the stale session can't be used.
- *Rejected alternatives:* "Reload settings and keep running" leaves stale objects everywhere: the cart, cached services, the `Database` engine. A restart is the only clean boundary.
- *Data/schema:* none.

**Implementation steps.**
1. `config_service.py`: add `reload()` and `freeze_writes()` (also `_frozen: bool = False`; `save()` checks it).
2. `backup_service.py`: implement the post-replace sequence and the migration-failure rollback. Reuse `_replace_database` for the rollback, with the snapshot path from earlier in the same method; keep it in a local variable.
3. `restore_tab.py:245-256`: replace "recommend restart" with the forced restart.

**Tests (write first).** `tests/ui/test_backup_restore_safety.py`:
- `test_issue_873_settings_reloaded_after_restore`: the backup's settings have `shop_name="RESTORED SHOP"`. After `restore_backup`, `ConfigService.get("shop_name") == "RESTORED SHOP"`. A later `set("sidebar_collapsed", True)` doesn't change the on-disk `shop_name`, because writes are frozen.
- `test_issue_873_older_backup_migrated_to_head`: a backup DB stamped at the v1.3.0 head (`b4d6fbce9cf4`, as the issue cites; confirm that revision exists in `alembic/versions`) ends at head after `restore_backup`.
- `test_issue_873_migration_failure_rolls_back_to_snapshot`: monkeypatch `SchemaMigrationService.migrate_to_head` to raise. Then `BackupError("migration_failed")` is raised and the live DB bytes equal the pre-restore bytes.
- `tests/ui/test_app_restart.py`-style test: `restore_tab` calls `restart_application` after a successful restore (mock the service).

**UI/UX spec.**
- Success: `data_safety.restore_done_restarting` → "Restore complete. CB POS will now restart to load the restored data." [OK]
- Restart failed: `data_safety.restore_restart_manual` → "Restore complete. Please close CB POS and open it again before doing anything else." The main window is disabled behind it.
- Migration failed: `data_safety.error_migration_failed` → "The backup couldn't be updated to this version of CB POS, so your previous data was put back. Nothing was lost."
- Run the §0.7 UI gate.

**Do NOT.**
- Do not leave the app usable after a restore without a restart.
- Do not delete the safety snapshot after a successful restore. Keep it, as today.

**Edge cases.**
- Restoring while another dialog is open: the restore tab is itself inside Management, so the restart closes everything.
- Network mode: unreachable, because #839 refuses first.

**Acceptance criteria.**
- [ ] After `restore_backup`, `ConfigService.get("shop_name")` returns the restored value, and a later `set()` cannot undo it.
- [ ] Restoring an older-schema backup leaves the DB at Alembic head before the app touches it again.
- [ ] The app restarts automatically after a restore, or locks itself if it can't.

**Verify.** Focused tests. Manual round trip: back up, change the shop name, restore, and confirm the app restarts with the old name.

**Stop & Ask if.** None expected.

---

## Phase exit gate
- [ ] All 14 issues (#948 + 13) merged and **verified closed** on GitHub with closing comments (§0.10). #832 and #922 checklists updated.
- [ ] Full suite green once per batch (`-n auto`) and `pre-commit` clean.
- [ ] Migration for `login_throttle` (#856) upgrade-tested on a seeded SQLite copy and an empty DB. If a PostgreSQL instance is available, run `alembic upgrade head` against it too, otherwise note "⚠️ PG verify in Phase 2".
- [ ] Manual first-run test on a **clean Windows VM or user profile** with the built exe: wizard → PIN → Start Fresh → log in with the chosen PIN, and `1234` fails. Mark "⚠️ Verify on Windows" until done.
- [ ] Manual v1.2.2 → current upgrade on a copy of a real v1.2.2 shop DB (#837).
- [ ] UI gate screenshots attached for: the DB-unavailable dialog, AdminPinDialog, the lockout state, the last-admin tooltip, the held-bill note on login, the settings recovery notices, the network-mode Data Safety cards, and the restore-restart message.
- [ ] Follow-up filed: real PostgreSQL backup (`pg_dump`) for network mode (from #839).
- [ ] PROGRESS.md updated. Handoff note written if the session ends.
