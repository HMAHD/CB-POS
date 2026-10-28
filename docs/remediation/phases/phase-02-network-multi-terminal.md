# Phase 2 — PostgreSQL Network Mode and LAN Multi-Terminal Sync

> **Agent:** before anything else, read `docs/remediation/RELEASE_PLAN.md` Part 0, `DECISIONS.md` and `PROGRESS.md`.
> This spec was verified against `origin/main` @ `4bcc837` on 2026-10-28. Re-verify every `file:line` before editing (§0.1 step 7).

## Phase brief

CB POS has **two different multi-PC modes**. Don't mix them up:

| Mode | Setting | Data lives | How PCs share |
|---|---|---|---|
| **Network (PostgreSQL)** | `db_mode = "network"` | One shared PostgreSQL DB | Every PC queries the same DB directly |
| **LAN Sync** | `terminal_mode = "main"` / `"terminal"`, `db_mode = "standalone"` | One SQLite DB per PC | Tills push transactions to the Main PC over HTTPS (`sync_server.py` / `sync_client.py`) and pull the catalog |

**Outcome (end state):**
- Network mode: after an app update, the designated Main PC upgrades the shared schema with one guided, locked action. Tills refuse to run on a mismatched schema with a clear message. Transient connection errors reach callers as connection errors.
- LAN Sync:
  - a till trusts only the Main PC certificate the user confirmed;
  - each till has a unique, verified identity, so reinstalling or restoring never overwrites history;
  - catalog edits, deletions and role permissions reach every till;
  - tills can't create catalog rows that clash;
  - audit logs flow to the Main PC;
  - one idle socket can't stall the server;
  - failing pushes are visible.
- Both modes: shifts are per terminal, the dashboard works on PostgreSQL, document numbers never repeat, and two tills can't refund or void the same sale twice.

**Depends on:** Phase 1 merged:
- #833 network-aware setup check;
- #837 `SchemaMigrationService` in `cbpos/core/services/schema_migration_service.py` (**not** the existing `migration_service.py`, which copies SQLite data into PostgreSQL);
- #839 network-mode backup refusal.

Batch 2.6 #914 also depends on Phase 3A.3 (the refund engine and `refunded_qty`).

**Unblocks:** the public release gate's multi-terminal smoke test (RELEASE_PLAN.md §1.3).

### Issues

| # | Title | Sev | Size | Batch | Gate |
|---|---|---|---|---|---|
| #799 | PostgreSQL mode has no schema-upgrade path | high | L | 2.1 | decided (D2) |
| #904 | `get_session()` retries by yielding twice | medium | S | 2.1 | agent |
| #800 | LAN Sync accepts any TLS certificate | high | L | 2.2 | decided (D3) |
| #868 | A promotion with a daily time window breaks catalog sync | high | S | 2.3 | agent |
| #867 | Terminal IDs not unique; TERM-01 collides with the Main PC | high | M | 2.3 | agent (one receipt-format question, recommended answer given) |
| #866 | A reinstalled or restored till overwrites its earlier sales on the Main PC | high | L | 2.3 | agent |
| #869 | Catalog rows created on a till clash with Main PC ids | high | M | 2.3 | agent |
| #836 | Product edits never reach tills (`version_id` merge failure) | critical | S | 2.4 | agent |
| #871 | Deletions on the Main PC never reach tills | high | L | 2.4 | agent |
| #872 | Role permissions never sync | high | M | 2.4 | agent |
| #903 | Till audit and inventory logs never reach the Main PC | medium | M | 2.4 | agent |
| #870 | One idle TCP connection stalls the sync server | high | S | 2.5 | agent |
| #905 | Document sequence found by string sort | medium | S | 2.5 | agent |
| #906 | Failing pushes are invisible; the till shows "Synced" | medium | M | 2.5 | agent |
| #884 | Same cashier on two terminals: shifts count each other's sales | medium | M | 2.6 | agent |
| #886 | Dashboard charts fail on PostgreSQL (`strftime`) | medium | S | 2.6 | agent |
| #914 | Two tills can refund or void the same sale concurrently | low | M | 2.6 | **human**: D11 vs partial refunds (question below) |

### Subsystem map (read before any batch)

**Database engine** — `cbpos/core/database.py`:
- `Database()` singleton; `_initialize()` `:44-88` picks SQLite or PostgreSQL from `db_mode`;
- `_get_postgres_uri()` `:94-117`;
- `test_connection()` `:119-165`;
- `create_tables()` `:167-170` is `create_all` only;
- `get_session()` `:172-220`, which has the retry loop (#904).

**Schema migration:**
- `SchemaMigrationService` from Phase 1 #837 (`migrate_to_head(db_uri)`, `current_revision`, `known_revisions`);
- Alembic env in `alembic/env.py`;
- the SQLite→PostgreSQL data copy is `cbpos/core/services/migration_service.py` (`migrate_sqlite_to_postgres` `:94-232`), used by `ui/views/settings_pages/network.py`.

**Network settings UI** — `cbpos/ui/views/settings_pages/network.py`, which handles both modes. It falls back to `TERM-01` at `:588` and `:607`.

**LAN Sync** — the protocol is `cbpos/core/services/sync_protocol.py`:
- `SYNC_PROTOCOL_VERSION = "1.0"` `:25`;
- `CATALOG_TABLES` `:46-61`, `TRANSACTION_TABLES` `:72-95`;
- `SyncEncoder` `:98-128`, `model_to_dict` `:131-167`, `dict_to_model` `:170-182`, `coerce_columns` `:185-250`;
- `validate_envelope` `:281-296` accepts any `"1."` version.

The client is `cbpos/infrastructure/sync_client.py` (a `QThread`, using `urllib` with `self._ssl_context`):
- request helper `~:285-305` (sends `X-Sync-Token` `:291`);
- `register` `~:380-404`;
- `_check_main_identity` `:405-430`, which already pins the Main PC's **instance id** on first use (copy this pattern);
- `_collect_unsynced` `:502-600`, `_FLAT_PUSH_TABLES` `:65-74`;
- `_pull_catalog` `:659-750`;
- `push_audit_logs` `:801-844`, which has no callers.

The server is `cbpos/infrastructure/sync_server.py`:
- the terminal registry `~:100-125` (logs "re-registered");
- `_handle_register` `:272`;
- the pull handler `~:337-351`;
- `_ThreadedHTTPServer` `:555`, `SyncServer(QThread)` `:574`, and the TLS wrap `:638`.

The rest of LAN Sync:
- TLS: `cbpos/infrastructure/sync_tls.py`: `get_or_create_certificate` `:49-82`, `build_server_ssl_context` `:84-89`, `build_client_ssl_context` `:92-100` (`CERT_NONE`).
- Apply on the Main PC: `cbpos/core/services/sync_apply_service.py`, covering the id spaces (`:94-115`), `_adopt_legacy_row` `~:563-577`, `_update` `~:591-605`, and the sync-id mapping. The `SyncIdMap` model is at `models/__init__.py:872-890`, with a unique key on `(origin_terminal_id, table_name, local_id)`.
- Change tracking: `sync_change_tracking.py`, plus `sync_customer_renumber.py` (#680: till-created customers are allowed and renumbered).
- Status UI: `cbpos/ui/widgets/sync_status_widget.py`. Wiring in `main.py:513-570`.

**Document numbers** — `cbpos/core/services/document_service.py`:
- `_terminal_short` `:42-44` (last "-" segment);
- `render_pattern` `:59-80`;
- `_next_seq` `:163-177` (string sort);
- `generate_number` `:231-300`.

**Tests to copy from:**
- `tests/sync_two_machines.py` (the two-machine harness);
- `test_sync_client.py`, `test_sync_server.py`, `test_sync_protocol.py`, `test_sync_tls.py`, `test_sync_id_collision.py`.

**Use the two-machine harness for every "two-machine test" acceptance item.**

### Domain invariants this phase must preserve

1. On the Main PC, a till's document is identified by `(terminal_id, db_instance_id, table, local_id)`. A re-send of the same row is idempotent, and a different row never overwrites it.
2. A terminal ID is unique across the shop and is never the Main PC's own ID.
3. A sync push or pull never sends the shared secret to a server whose certificate is not the pinned one.
4. Catalog state on a till converges to the Main PC's: updates, deletes and role permissions. The pull watermark only advances when every record in the batch applied.
5. In network mode, no PC runs the app against a schema revision different from the app's head.
6. Document numbers are unique and strictly increasing per prefix.
7. Shift summaries include only the sales and cash movements made on that shift's terminal.

### Batches (one PR each)

| Batch | Branch | Issues (in order) | Why grouped |
|---|---|---|---|
| 2.1 | `fix/p2-b1-pg-schema-ownership` | #904, #799 | The PostgreSQL engine and its schema lifecycle |
| 2.2 | `fix/p2-b2-tls-pinning` | #800 | A security-critical protocol change of its own; reviewed alone |
| 2.3 | `fix/p2-b3-terminal-identity` | #868, #867, #866, #869 | Who a till is and what it may create. #868 is a quick unblocker first |
| 2.4 | `fix/p2-b4-catalog-deletion-permission-sync` | #836, #871, #872, #903 | Catalog convergence and log flow, sharing one protocol bump |
| 2.5 | `fix/p2-b5-sync-server-resilience` | #870, #905, #906 | Server robustness, numbering and honest status |
| 2.6 | `fix/p2-b6-network-shifts-dashboards-locking` | #886, #884, #914 | Correctness with several PCs at once |

**Protocol versioning rule for this phase.**
- Batches 2.2, 2.3 and 2.4 change what peers send. Bump `SYNC_PROTOCOL_VERSION` once per batch: 2.3 → `"1.1"`, 2.4 → `"1.2"`.
- 2.2 changes TLS, not the envelope: no bump, but old tills fail the handshake. Document this in the release notes.
- Make `validate_envelope` reject peers **older** than the minimum this build needs. Return a clear error code `protocol_too_old`, which the till shows as "Update CB POS on this till". **All PCs in a shop must be updated together.** Put this at the top of the release notes.

---

## Batch 2.1 — PostgreSQL schema ownership

**Branch:** `fix/p2-b1-pg-schema-ownership` · **Issues:** #904, then #799

### #904 — `Database.get_session()` retries by yielding twice

**Severity:** medium · **Size:** S · **Gate:** agent · **Skills:** systematic-debugging → tdd → ponytail

**Problem.** In network mode, a brief PostgreSQL drop (server restart, Wi-Fi blip) should either retry or report "connection lost". Instead the app raises a confusing `RuntimeError: generator didn't stop after throw()`. The advertised retry never happens.

**Evidence and root cause.**
- `cbpos/core/database.py:186-216`: `get_session` is a `@contextmanager` generator that loops and `yield`s again after an `OperationalError`.
- A context-manager generator can't yield twice, so any second `yield` raises `RuntimeError`.

**Fix design.**
- *Recommended:* remove the retry loop. Yield exactly once.
  - On an exception: rollback, close, re-raise the original exception unchanged.
  - Make sure `pool_pre_ping=True` is set on the PostgreSQL engine in `_initialize()`. It stops most stale-connection errors before they happen. Add it if missing.
  - Callers that want resilience catch `sqlalchemy.exc.OperationalError` and show the network error. Add a translated error `errors.db_connection_lost` to `translate_error`.
- *Rejected alternatives:* a retry decorator that re-runs the whole unit of work. That is safe only for idempotent reads, adds hidden double-writes risk for sales, and no caller needs it now.
- *Data/schema:* none.

**Implementation steps.**
1. Rewrite `get_session` (keep the `serializable` parameter behaviour for PostgreSQL: set the isolation level on the connection once, then yield).
2. Delete `_MAX_RETRIES` and the retry helpers if they become unused (`graft grep "_MAX_RETRIES"`).
3. Add the translation key and map `OperationalError` in `cbpos/core/utils/error_messages.py`.

**Tests.** `tests/domain/test_database_session.py::test_issue_904_operational_error_reaches_caller`:
- Monkeypatch `Database()._db_mode = "network"` and use a SQLite engine.
- In the body raise `OperationalError("x", {}, Exception())`.
- Assert `pytest.raises(OperationalError)`, and that the body ran exactly once.

**UI/UX.** `errors.db_connection_lost` → "Lost connection to the shop database. Check the network cable or Wi-Fi to the Main PC, then try again. Nothing was saved." Run the §0.7 UI gate on one call site (e.g. completing a sale).

**Do NOT.** Do not yield in a loop. Do not swallow the exception.

**Acceptance.**
- [ ] In network mode, an `OperationalError` raised in the body reaches the caller as `OperationalError`.

### #799 — PostgreSQL network mode has no schema-upgrade path

**Severity:** high · **Size:** L · **Gate:** decided by **D2**: one guided Network Setup flow; an admin on the designated Main PC runs Alembic; tills never migrate and block with "Main PC update required"
**Skills:** brainstorming → codebase-design → write a design note → `/egm-review` → tdd → migration rules → ponytail; impeccable (full UI gate) for the setup flow

**Problem.** In network mode only `create_all` runs on the shared database. It adds new tables but never changes existing ones. After any update with a column change, every PC runs against an outdated schema and crashes or corrupts data.

**Evidence and root cause.**
- `main.py:110-183` (now `SchemaMigrationService` after Phase 1) always uses `Config.DB_URI` (local SQLite).
- `cbpos/core/database.py:169` (`create_tables`) is the only schema step for PostgreSQL.
- `migration_service.py:143` (the SQLite→PG copy) also uses `create_all`.
- No test or CI job covers PostgreSQL.

**Fix design.**
- *Recommended:*
  1. **Engine-agnostic migration.** `SchemaMigrationService.migrate_to_head(db_uri)` already takes a URI (Phase 1). Make sure `alembic/env.py` uses the URI passed in `config.set_main_option("sqlalchemy.url", …)`, and that every migration is PostgreSQL-safe. Run all of them on PostgreSQL in CI (step 6) and fix failures in **new** migrations only. If an old migration is broken on PostgreSQL, **Stop & Ask** (pre-written below).
  2. **Schema owner.** A new setting `network_schema_owner: bool` (default False), set **only** through the Network Setup flow on the PC the user designates as Main PC. Only one PC should have it. Record the owner's hostname in a server-side table so others can see who it is:
     - new table `shop_meta` (`key` PK `String(50)`, `value` `String(200)`), created by migration;
     - row `schema_owner_host`.
  3. **Startup check in network mode** (in `main.py`, after `Database()` is created, before the setup check from #833):
     - `rev = SchemaMigrationService.current_revision(pg_uri)` and `head = …head`.
     - `rev == head`: continue.
     - `rev` unknown (not in `known_revisions()`): block, with "This computer has an older CB POS than the shop database. Update CB POS on this computer."
     - `rev` behind head and this PC is **not** the owner: block, with "The shop database needs updating. Open CB POS on the Main PC ({host}) first, then restart this computer's CB POS." Offer **Retry** and **Close**.
     - `rev` behind head and this PC **is** the owner: show an "Update shop database" dialog. It asks for admin PIN authentication (`AuthService.authenticate_pin`, Phase 1) and advises that all other PCs be closed. Then it runs the upgrade:
       - in a worker thread (never on the UI thread);
       - holding a PostgreSQL advisory lock: `SELECT pg_advisory_lock(727001)` on a dedicated connection, then `migrate_to_head`, then `pg_advisory_unlock`;
       - writing an `AuditLog` row `SCHEMA_UPGRADE` with from/to revisions.
     - `rev` is None (empty DB): the existing first-run flow (#833 `NEEDS_SETUP`), but `create_empty_database` on PostgreSQL must be followed by `stamp head`. Check that `stamp_alembic_head` uses the passed URI, not SQLite.
  4. **Guided Network Setup flow** (`settings_pages/network.py`). Replace the current separate buttons with a 3-step panel:
     1. **Connect**: host, port, database, user, password, SSL mode; **Test connection** (existing `test_connection`).
     2. **Database**: the panel shows the server's state (empty / up to date / needs update / newer than this app):
        - empty: offer **Copy this computer's data to the server** (existing `MigrationService.migrate_sqlite_to_postgres`) or **Start empty**;
        - needs update: offer **Make this the Main PC and update** (sets the owner flag);
        - newer than this app: show "Update CB POS first" with no action.
     3. **Confirm**: summary, then **Switch to network mode**, which saves the settings and restarts the app (`restart_application`).
  5. **Copy flow.** After `migrate_sqlite_to_postgres` (which uses `create_all`), run `stamp head` on the PostgreSQL DB, because the data now matches the current models. Fix that at `migration_service.py:~143` by calling `SchemaMigrationService.stamp_head(pg_uri)`.
  6. **CI.**
     - Add a `postgres` job to `.github/workflows/ci.yml` with a `services: postgres:16` container. It sets `CBPOS_TEST_PG_URL` and runs `uv run python -m pytest tests/unit -m postgres -q`.
     - Add a `postgres` marker to `pyproject.toml` `[tool.pytest.ini_options] markers`.
     - Add a `pg_engine` fixture in `tests/conftest.py` that skips without the env var.
     - Phase 1 #948 restored the `lint` and `unit` CI jobs. Add the `postgres` job alongside them.
- *Rejected alternatives:*
  - Every PC migrates at startup: races and partial migrations.
  - Hide network mode: rejected by D2.
- *Data/schema:* new `shop_meta` table (migration).
- *Sync/network impact:* network mode only. LAN Sync is unaffected.

**Implementation steps.**
1. `schema_migration_service.py`: add `stamp_head(uri)`, `pending(uri) -> bool`, `upgrade_with_lock(uri)` (PostgreSQL advisory lock; on SQLite just upgrade).
2. Migration for `shop_meta`.
3. `main.py`: the network startup check, using translated dialogs. Keep it a small `NetworkSchemaGate` helper in `cbpos/ui/network_schema_gate.py` so `main.py` stays readable. The gate calls services; it never queries.
4. `settings_pages/network.py`: the 3-step flow (see the UI spec).
5. CI job, marker and fixture.

**Tests.**
- `@pytest.mark.postgres` `test_issue_799_upgrade_runs_on_postgres`: create a PostgreSQL DB at the v1.3.0 head (`b4d6fbce9cf4`) by `upgrade` to that revision, then `upgrade_with_lock`, then `current_revision == head`.
- `test_issue_799_non_owner_blocks_when_behind`: unit test of the gate decision function `decide(rev, head, known, is_owner) -> GateAction` (pure, no DB). Table-driven over all branches.
- `test_issue_799_copy_flow_stamps_head` (postgres).
- `test_issue_799_advisory_lock_serialises` (postgres): two threads call `upgrade_with_lock`; both finish and the revision is head. The second finds nothing to do.

**UI/UX spec.**
- Network settings: a 3-step vertical stepper (numbered headers 1 Connect · 2 Database · 3 Confirm), using the enterprise card pattern (as in the Admin Tools hardware tab).
  - Each step is enabled only when the previous one succeeded.
  - Status lines use icons: ok (green), warning (yellow), error (red), from `cbpos/ui/resources/icons.py`.
- Copy keys `network_setup.*`:
  - `step_connect` "Connect to the shop database"
  - `step_database` "Shop database"
  - `step_confirm` "Switch this computer"
  - `state_empty` "The database is empty."
  - `state_ok` "The database is up to date."
  - `state_behind` "The database needs updating for this version of CB POS."
  - `state_newer` "The database belongs to a newer CB POS. Update this computer first."
  - `make_main_update` "Make this the Main PC and update the database"
  - `copy_data` "Copy this computer's data to the server"
  - `start_empty` "Start with an empty database"
  - `switch` "Switch to network mode and restart"
- Startup gate dialog keys `network_gate.*`:
  - `behind_title` "Shop database needs updating"
  - `behind_body` "Open CB POS on the Main PC ({host}) first. It will update the shop database. Then click Retry."
  - `newer_body` "This computer has an older CB POS than the shop database. Install the latest CB POS here."
  - `update_title` "Update the shop database"
  - `update_body` "CB POS will update the shared shop database. Close CB POS on all other computers first. This usually takes less than a minute."
  - `updating` "Updating the shop database…"
  - `update_failed` "The update didn't finish: {error}. The database was not changed. Contact support before trying again."

  (Alembic migrations run in transactions on PostgreSQL. Verify that each migration is transactional, and if any isn't, add that caveat to the message.)
- The update dialog shows indeterminate progress, the buttons are disabled while running, and Esc is disabled.
- Run the §0.7 UI gate with screenshots of every gate state and every setup step.

**Do NOT.**
- Do not let tills migrate.
- Do not run Alembic on the UI thread.
- Do not use `create_all` as a substitute for migrations on PostgreSQL.
- Do not edit shipped migrations.

**Edge cases.**
- The owner PC dies: on another PC, Network Setup offers **Make this the Main PC** (admin PIN), which moves the owner flag and updates the `shop_meta` row.
- Two PCs both think they are the owner (settings copied): the advisory lock serialises them, and the second sees the DB already at head.

**Acceptance criteria.**
- [ ] Owner decision recorded (D2).
- [ ] Migration path in network mode: owner-only, locked, audited, off the UI thread. Tills block on mismatch with a clear message.
- [ ] CI has a PostgreSQL job running `-m postgres` tests, and it passes.

**Verify.** Run the postgres tests locally with Docker (`docker run -e POSTGRES_PASSWORD=pw -p 5432:5432 postgres:16`, then `CBPOS_TEST_PG_URL=postgresql+psycopg2://postgres:pw@localhost/postgres`). Then a manual two-PC test if hardware is available; otherwise mark "⚠️ Verify on Windows, two PCs".

**Stop & Ask if.**
- An old migration fails on PostgreSQL:

  QUESTION (#799): Migration <rev> fails on PostgreSQL (<error>). Editing it changes history. Options: A) add a new corrective migration that brings PostgreSQL to the intended state, and skip the broken op on PG with a dialect check inside the old migration (minimal edit); B) require fresh PG installs to use the copy-and-stamp flow only.
  Recommendation: A, with the minimal dialect guard reviewed by the human.

---

## Batch 2.2 — Pinned TLS pairing

**Branch:** `fix/p2-b2-tls-pinning` · **Issues:** #800

### #800 — LAN Sync accepts any TLS certificate

**Severity:** high · **Size:** L · **Gate:** decided by **D3**: show the SHA-256 fingerprint on both PCs, the user confirms they match, persist the pin, block and audit later changes, and never send the token before the pin is verified
**Skills:** brainstorming → write a design note → `/egm-review` → tdd → ponytail-review (security lens); impeccable (full UI gate)

**Problem.** Tills accept any certificate, and the shared secret goes in every request header. Anyone on the shop Wi-Fi can impersonate the Main PC, read the secret, and then push or pull business data.

**Evidence and root cause.**
- `cbpos/infrastructure/sync_tls.py:92-100`: `check_hostname = False`, `verify_mode = CERT_NONE`.
- The token goes in the header at `sync_client.py:291` and `cbpos/ui/workers.py:~670` (the Test Connection worker).
- The Main PC's self-signed certificate: `sync_tls.py:49-82`.

**Fix design.**
- *Recommended:* **trust only the pinned certificate.**
  - The till stores the Main PC's full certificate (PEM) after the user confirms it, and builds its client context with `verify_mode = CERT_REQUIRED`, `check_hostname = False`, `load_verify_locations(cadata=pinned_pem)` and `verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN`. That flag lets a self-signed leaf be its own trust anchor. Confirm it with a unit test using a certificate from `get_or_create_certificate`.
  - If the server presents any other certificate, the **TLS handshake fails before any HTTP bytes are sent**, so the token never leaves the till.
  1. `sync_tls.py`:
     - `cert_fingerprint(pem: str) -> str`: SHA-256 of the DER, uppercase hex in colon pairs, grouped as 16 groups of 2 per line for display.
     - `fetch_server_certificate(host, port, timeout=5) -> str`: `ssl.get_server_certificate((host, port), timeout=timeout)`. No token, no HTTP.
     - `build_client_ssl_context(pinned_pem: str | None)`: if None, **raise** `UnpairedError`. There is no unverified mode any more.
  2. Settings: `sync_pinned_cert_pem` (sensitive key, encrypted like the other secrets; add it to `ConfigService._SENSITIVE_KEYS`) and `sync_pinned_cert_fp` (display only).
  3. **Pairing flow** (terminal side, Network settings, LAN Sync section):
     - **Pair with Main PC** fetches the certificate and shows the fingerprint next to the instruction "Check this matches the code shown on the Main PC under Settings → Network → This computer's sync code".
     - The buttons are **They match — pair** and **Cancel**.
     - On confirm, save the pin, run a heartbeat, and write an AuditLog `SYNC_PAIRED` with the fingerprint.
  4. **Main PC side:** the Network settings page shows "This computer's sync code" (the fingerprint of `get_or_create_certificate()`) with a **Copy** button.
  5. **Mismatch at runtime:** the client catches `ssl.SSLCertVerificationError` and, in order:
     1. stops syncing (state `ERROR`, code `cert_mismatch`);
     2. writes an AuditLog `SYNC_CERT_MISMATCH` (presented fingerprint, from `fetch_server_certificate`, without a token);
     3. shows a persistent red banner in the status widget, "The Main PC's security code changed. Sync is stopped.", with a **Review** button. That opens the pairing dialog, showing old and new fingerprints side by side and requiring **admin authentication** (`authenticate_pin` with `settings.manage` or the equivalent admin permission) to re-pair.
  6. **Migration path for existing tills:** a till upgraded with no pin is **unpaired**. Sync doesn't start, and the status widget shows "Pair this till with the Main PC" with a button to the pairing flow.

     Don't auto-trust on first use: D3 requires user confirmation.
  7. `cbpos/ui/workers.py:~670` (Test Connection): with no pin, it performs the pairing fetch (no token). With a pin, it uses the pinned context.
- *Rejected alternatives:*
  - Silent trust on first use: rejected by D3.
  - HMAC request signing: still useful, but separate. File it as a follow-up enhancement.
  - Fingerprint check after the handshake inside urllib: the token is already queued, which is too late.
- *Data/schema:* none (settings only).
- *Sync/network impact:* every existing till must be paired once after the update. Release notes must say so prominently, with the steps.

**Implementation steps.** Follow the design steps 1–7. Also:
- remove the module docstring line that says pinning is "left for later" (`sync_tls.py:3-16`);
- add the new settings to the backup exclusion review (#875 handles undecryptable secrets: a restored till on a new PC must re-pair. Confirm `sync_pinned_cert_pem` behaves that way: undecryptable means empty means unpaired).

**Tests** (`tests/domain/test_sync_tls.py`, extending it; there's an existing server/client setup):
- `test_issue_800_pinned_context_accepts_pinned_cert`: start the test server with cert A; client pinned to A, heartbeat ok.
- `test_issue_800_pinned_context_rejects_other_cert_before_request`: server with cert B, client pinned to A. Raises `SSLCertVerificationError`, and the server's request handler saw **no** request (assert the handler counter is 0).
- `test_issue_800_unpaired_client_does_not_sync`.
- `test_issue_800_fingerprint_format`.
- `test_issue_800_mismatch_writes_audit_and_sets_error_state`.

**UI/UX spec.**
- Main PC: Network page card "This computer's sync code". The fingerprint is shown monospaced in 4 lines of 8 pairs, with a Copy button and the help text `sync_pairing.main_help` → "Tills check this code the first time they connect. Read it out or compare it on screen."
- Till: Network page card "Main PC":
  - states: **Not paired** (yellow, button **Pair with Main PC**), **Paired** (green, shows the fingerprint's last 8 pairs plus **Change…**), **Code changed** (red).
- Pairing dialog `SyncPairingDialog`:
  - objectName `SyncPairingDialog`;
  - fingerprint big and monospaced;
  - instruction text;
  - footer `[They match — pair] [Cancel]`, where Cancel is the default button, so Enter doesn't pair by accident;
  - re-pair mode shows "Previously trusted" and "Now presented" side by side and requires admin.
- Keys `sync_pairing.*`:
  - `title` "Pair with the Main PC"
  - `instruction` "Check that this code is exactly the same as the code on the Main PC (Settings → Network → This computer's sync code)."
  - `match` "They match — pair"
  - `paired` "Paired with the Main PC"
  - `not_paired` "This till isn't paired with the Main PC yet. Sales are kept here until it is."
  - `changed` "The Main PC's security code changed. Sync is stopped to keep your data safe."
  - `review` "Review…"
  - `previous` "Previously trusted"
  - `presented` "Now presented"
  - `admin_needed` "An admin must approve the new code."
- Run the §0.7 UI gate with screenshots of all states on both machines.

**Do NOT.**
- Do not keep any `CERT_NONE` client path.
- Do not send `X-Sync-Token` in the pairing fetch.
- Do not make "pair" the default button.
- Do not auto-accept a changed certificate.

**Edge cases.**
- The Main PC regenerates its certificate (the cert file deleted, or a new PC): every till goes to "Code changed", and an admin re-pairs each one. Expected.
- A clock skew makes the certificate look not yet valid: `VERIFY_X509_PARTIAL_CHAIN` still checks validity dates. The certificate is 10-year, created "now". If tests show failures on skewed clocks, generate it with `not_valid_before = now - 1 day` in `get_or_create_certificate` (new certificates only).

**Acceptance criteria.**
- [ ] The till verifies the pinned certificate. A mismatch blocks sync, is audited, and the token is never sent.
- [ ] "Test Sync Connection" shows the fingerprint.
- [ ] Tests for the pin, mismatch, first-use and unpaired flows.

**Verify.** Focused tests. Manually on two PCs (or two data dirs on one PC with different ports): pair, sync, delete the Main PC certificate files, restart the Main, and confirm the till shows "Code changed" and stops.

**Stop & Ask if.** None expected. The design is locked by D3.

---

## Batch 2.3 — Terminal identity and collision-proof sync

**Branch:** `fix/p2-b3-terminal-identity` · **Issues:** #868, #867, #866, #869 · **Protocol:** bump to `"1.1"`; peers below 1.1 are refused with `protocol_too_old`

### #868 — A promotion with a daily time window breaks catalog sync

**Severity:** high · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Root cause.**
- `Promotion.daily_start/daily_end` are `Time` columns (`models/__init__.py:~135-136`).
- `model_to_dict` (`sync_protocol.py:~151-158`) and `SyncEncoder` (`:98-128`) handle only `datetime`/`date`. That raises `TypeError` in the pull reply, the watermark never advances, and every catalog pull fails.
- `coerce_columns` (`:185-250`) has no `Time` branch either.

**Fix.**
- Serialize `datetime.time` with `.isoformat()` in both encoders.
- Add `elif isinstance(col.type, Time): value = time.fromisoformat(value)` in `coerce_columns`.
- Check the branch order: `datetime` is a subclass of `date` but not of `time`, so the order is safe. Add a comment.

**Tests.**
- `test_sync_protocol.py::test_issue_868_promotion_time_round_trip`: `model_to_dict` → `sync_json_dumps` → `sync_json_loads` → `dict_to_model`, with equal `daily_start/daily_end`.
- Two-machine harness: `test_issue_868_happy_hour_promotion_reaches_till`.

**Acceptance.**
- [ ] The round-trip unit test passes.
- [ ] A happy-hour promotion reaches the till (two-machine test).

### #867 — Terminal IDs are not unique

**Severity:** high · **Size:** M · **Gate:** agent (the receipt-prefix format has a recommended answer; apply it and mention it in the PR)
**Skills:** tdd → ponytail; impeccable (harden) for the Network page

**Problem.** Every PC defaults to `TERM-01`, and nothing checks for uniqueness:
- A till left at `TERM-01` numbers receipts exactly like the Main PC and overwrites the Main PC's sales on push.
- "TERM-01" and "TILL-01" both become prefix "01-", so a till's pushes are rejected forever.

**Evidence and root cause.**
- `config_service.py:118`: the default is `"TERM-01"`.
- `settings_pages/network.py:588,607`: fallback to TERM-01.
- `sync_server.py:~110-122`: a registered ID from a new IP just logs "re-registered".
- `document_service.py:42-44`: `_terminal_short` keeps only the last "-" segment.
- `sync_apply_service.py:~563-577`: `_adopt_legacy_row` adopts documents by number.

**Fix design.**
1. **Validation:** terminal IDs match `^[A-Z0-9][A-Z0-9-]{1,15}$` (uppercase, normalised on save). In `terminal` or `main` mode the Network page refuses to save a blank ID. Remove the TERM-01 fallbacks at `network.py:588,607`. Keep the `ConfigService` default only for standalone, where it doesn't matter.
2. **Server side:**
   - `register` rejects (HTTP 409, code `terminal_id_is_main`) when `terminal_id == the Main PC's own terminal_id`.
   - It rejects (409, `terminal_id_taken`) when the ID is already bound to a **different** `db_instance_id` (from #866).
   - `push` applies the same checks.
   - The Main PC's Network page lists registered tills with **Release ID…** (admin), which unbinds an ID so a replacement PC can take it over (with an audit row).
3. **Prefix:** `_terminal_short` becomes "the full ID with non-alphanumerics removed", so "TERM-01" → "TERM01" and "TILL-01" → "TILL01".
   - That changes the visible receipt prefix for **new** documents, e.g. `TILL01-INV-2026-00001`.
   - Check `DOC_NUMBER_MAX_LENGTH` and `validate_doc_pattern` (`document_service.py:82-118`) still pass for a 16-character ID; tighten the ID length if not.
   - Existing numbers are unchanged. `_search_prefix` uses the new prefix, so sequences restart at 1 under it. That is safe because the prefix differs.

**Tests.**
- `test_document_service.py::test_issue_867_prefixes_differ_for_term01_and_till01`.
- `test_sync_server.py::test_issue_867_register_with_main_id_rejected`.
- `test_issue_867_register_same_id_other_instance_rejected`.
- pytest-qt `test_issue_867_network_page_refuses_blank_terminal_id`.

**UI/UX spec.**
- The Network page Terminal ID field has an inline validation message:
  - `network.terminal_id_required` → "Give this computer a unique name, for example TILL-1."
  - `network.terminal_id_invalid` → "Use capital letters, numbers and dashes only (2–16 characters)."
- The Main PC's registered-tills table: ID, last seen, IP, and **Release ID…**.
- Errors shown on the till:
  - `sync.error_terminal_id_is_main` → "This till uses the same name as the Main PC. Give it a different name in Settings → Network."
  - `sync.error_terminal_id_taken` → "Another till already uses the name {id}. Choose a different name, or ask the owner to release it on the Main PC."
- Run the §0.7 UI gate.

**Do NOT.**
- Do not silently rename a terminal.
- Do not change existing document numbers.

**Stop & Ask if.** Pre-decided; mention it in the PR:

QUESTION (#867): New receipt numbers on tills will show the full till name (e.g. `TILL01-INV-2026-00001` instead of `01-INV-2026-00001`). OK?
Recommendation: yes. It's unambiguous and prevents collisions. Proceed unless the owner objects at PR review.

**Acceptance.**
- [ ] A push or register from the Main PC's own ID is refused with a clear error.
- [ ] The TERM-01 and TILL-01 prefixes differ.
- [ ] The Network page won't save terminal mode with a blank or invalid ID. A duplicate ID is refused by the Main PC.

### #866 — A reinstalled or restored till overwrites its earlier sales on the Main PC

**Severity:** high · **Size:** L · **Gate:** agent · **Skills:** domain-modeling → write a design note → `/egm-review` → tdd → migration rules → ponytail

**Problem.** When a till's database starts over under the same name (Windows reinstalled, restored from an old backup, a replacement PC), its new sale #1 overwrites the old sale #1 on the Main PC. The stock movement is skipped as a "re-send". Revenue rows vanish and stock is wrong, silently.

**Evidence and root cause.**
- `SyncIdMap` unique key `(origin_terminal_id, table_name, local_id)` (`models/__init__.py:885-888`).
- `sync_apply_service.py:~309-325, 522-533, 591-605` map an incoming local id to the existing row and `_update` it.
- Root cause: a till's local ids are assumed never to repeat, but a new database restarts them.

**Fix design.**
1. **Database identity:** a new single-row table `local_identity` (`db_instance_id String(36)` PK, `created_at`), created and filled with `uuid4()` by migration (existing DBs get a fresh UUID) and by `create_empty_database`/demo.
   - Add `LocalIdentityService.get()` and `LocalIdentityService.regenerate()`.
   - `BackupService.restore_backup` calls `regenerate()` after replacing the DB (Phase 1 restore path). A restored DB is a new life of the till. Add this to `restore_backup` with a comment referencing #866.
2. **Protocol 1.1:** the envelope carries `db_instance_id`. `register` binds `terminal_id ↔ db_instance_id` on the Main PC, in the registry table. Find where the registry is persisted; if it is only in memory, persist it in a new table `sync_terminals(terminal_id PK, db_instance_id, first_seen, last_seen, last_ip, released bool)`.
3. **Map key:**
   - migration adds `sync_id_map.origin_db_instance_id` (nullable, backfilled `'legacy'`);
   - the unique constraint becomes `(origin_terminal_id, origin_db_instance_id, table_name, local_id)`;
   - SQLite batch mode recreates the constraint.
4. **Rebinding a terminal ID to a new instance** (after an admin **Release ID…** from #867, or the first register by an instance after migration): new rows map under the new instance id, so no overwrite is possible.
5. **Re-sent rows after a restore** (rows that were unsynced in the backup but had been synced from the old DB): on push, before inserting a document, check whether a document with the same `document_number` from the same `terminal_id` exists:
   - same `date`, `total_amount` and item count: treat it as already synced. Add a map entry for the new instance pointing to the existing row, and **don't** apply stock or ledger again;
   - otherwise: raise `PushApplyError("document_number_conflict")`, rejecting **only that document**. Check how the batch handles per-document errors. If one error rejects the whole batch, change it to per-document isolation, because #906 needs that visible anyway.
6. **Minimum guard** (the issue's): `_update` on a mapped document whose stored `document_number` or `date` differs from the pushed one raises `PushApplyError("mapped_row_mismatch")` instead of overwriting.
- *Rejected alternatives:* "Block a restored till from syncing until an admin intervenes" is safe but painful in every reinstall. The identity design handles it automatically.
- *Data/schema:* `local_identity`, `sync_terminals` (if needed), and `sync_id_map.origin_db_instance_id`.
- *Sync impact:* protocol 1.1.

**Tests** (two-machine harness):
- `test_issue_866_recreated_till_keeps_both_sales`: push sale #1, recreate the till DB with the same ID (new instance), sell and push. The Main PC has both sales, stock reflects both, and the ledgers reflect both.
- `test_issue_866_restored_till_resend_is_idempotent`.
- `test_issue_866_mapped_resend_with_different_number_rejected`.
- `test_issue_866_restore_regenerates_instance_id`.

**UI/UX.** Main PC registered-tills table (from #867) shows a short instance id and "new database since {date}" when an ID rebinds. The till shows a per-document error in the sync status (via #906). Run the §0.7 UI gate.

**Do NOT.**
- Do not key only on `terminal_id`.
- Do not overwrite a mapped row whose identity fields differ.
- Do not regenerate the instance id on normal startup.

**Acceptance.**
- [ ] Recreating a till DB with the same terminal ID and pushing keeps both sales, and stock reflects both.
- [ ] A mapped re-send whose document number differs is rejected, not applied.

### #869 — Catalog rows created on a till clash with Main PC ids

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable (harden, clarify)

**Problem.** A till can add products, users, suppliers and so on, though the Main PC owns the catalog. The new row's id clashes with the Main PC's ids:
- every later push fails with a foreign-key error, so the till's sales are stuck;
- once the Main PC creates its own row with that id, the till's sales are booked against the wrong product and the till's row is overwritten.

**Evidence and root cause.**
- There is no `terminal_mode` guard in any catalog service or UI.
- `sync_client.py:~702-711` merges by id.
- `sync_apply_service.py:94-105` id spaces.
- Customers are the deliberate exception (#680, `sync_customer_renumber.py`).

**Fix design.**
- A central guard `cbpos/core/utils/terminal_guard.py`:
  - `def require_catalog_writable() -> None`, which raises `CatalogReadOnlyError` (a `ValueError` subclass, code `catalog_read_only`) when `ConfigService.get("terminal_mode") == "terminal"`;
  - `def catalog_is_read_only() -> bool` for the UI.
- Call `require_catalog_writable()` first in every create, update and delete method of every service whose table is in `CATALOG_TABLES` **except customers**:
  - list them with `graft grep "CATALOG_TABLES"` and then `graft grep "def create_\|def update_\|def delete_" --in cbpos/core/services`;
  - expected: product, category, unit, supplier, user, role/permission, payment method, promotion, price list (+items), void reasons, composite items. Verify against `CATALOG_TABLES`.
  - **Stock movements are not catalog** (sales change stock locally). Product `stock_qty` updates from sales must still work, so the guard goes on **service methods**, not on a mapper event.
- UI: every management tab for those tables checks `catalog_is_read_only()` through a service call, hides or disables add/edit/delete, and shows a top banner.
- *Rejected alternatives:* "Allocate till ids in a separate range" needs every catalog FK remapped: big, risky, and unnecessary when the Main PC owns the catalog.
- *Data/schema:* none.

**Tests.**
- `test_terminal_guard.py`: parametrised over each guarded service method, all raise `CatalogReadOnlyError` in terminal mode and work in main or standalone.
- Customer create still works in terminal mode.
- Two-machine harness: `test_issue_869_till_sale_after_guard_pushes_fine`.

**UI/UX spec.**
- Banner component (reuse an existing notice/callout widget if there is one, e.g. the Admin Tools "notice callout"; otherwise create `ReadOnlyBanner` in `cbpos/ui/widgets/`):
  - `catalog.read_only_banner` → "This till uses the Main PC's product list. Add or change products, prices, suppliers and users on the Main PC; changes arrive here automatically."
  - Buttons are disabled with the tooltip `catalog.read_only_tooltip` → "Change this on the Main PC."
- Run the §0.7 UI gate on the Inventory, Users, Promotions and Price Lists tabs in terminal mode.

**Do NOT.**
- Do not guard customers.
- Do not guard stock changes from sales or returns.
- Do not rely on the UI alone.

**Acceptance.**
- [ ] Product, User, Supplier, Category and the other catalog services raise on create, update or delete in terminal mode.
- [ ] The management UI shows those screens read-only on a till, with the banner.

---

## Batch 2.4 — Catalog, deletion and permission sync

**Branch:** `fix/p2-b4-catalog-deletion-permission-sync` · **Issues:** #836, #871, #872, #903 · **Protocol:** bump to `"1.2"`

### #836 — Product edits on the Main PC never reach a till

**Severity:** critical · **Size:** S · **Gate:** agent · **Skills:** systematic-debugging → tdd → ponytail

**Problem.** The owner changes a price, name, barcode or VAT flag on the Main PC, and every till keeps selling at the old values forever. The sync error is logged and skipped, and the watermark moves on, so it is never retried.

**Evidence and root cause.**
- `Product.version_id` is an optimistic-lock column (`models/__init__.py:~372`). Both PCs bump it independently: on sales, on stock pulls, on edits.
- `sync_client.py:~709-725` (`_pull_catalog`) calls `session.merge(Product(..., version_id=<Main's>))`. SQLAlchemy refuses a merge whose version differs.
- The client logs it and advances `self._last_catalog_sync` anyway.

**Fix.**
1. Before `dict_to_model`, drop every column that is the model's `version_id_col`. Do it generically: `mapper = class_mapper(model); if mapper.version_id_col is not None: data.pop(mapper.version_id_col.key, None)`. That covers any future versioned model.
2. The watermark advances only when **every** record in the pull applied. On any failure, keep the previous `since`, log, and set the client's error state (#906).
3. A till must never push `version_id` back to the Main PC for catalog rows. It doesn't push catalog rows, except customers; confirm customers aren't versioned.

**Tests.**
- Two-machine: `test_issue_836_main_price_edit_reaches_till_after_both_sold`.
- `test_issue_836_failed_record_keeps_watermark`: inject one bad record and assert `since` is unchanged.

**Do NOT.**
- Do not disable optimistic locking on the model; it protects local edits (#862 in Phase 4).
- Do not set the till's `version_id` to the Main PC's value.

**Acceptance.**
- [ ] After a price edit on the Main PC, with both PCs having sold the product, one cycle shows the new price on the till.
- [ ] A record that fails to apply keeps the previous watermark.

### #871 — Deletions on the Main PC never reach the tills

**Severity:** high · **Size:** L · **Gate:** agent · **Skills:** codebase-design → write a design note → `/egm-review` → tdd → migration rules → ponytail

**Problem.** Deleted promotions, price-list overrides, payment methods and categories stay on every till forever. Tills keep giving a removed 10% discount or a special price, so the owner loses money and receipts don't match. Re-creating a row with the same name breaks the merge on a unique constraint.

**Evidence and root cause.**
- The pull (`sync_server.py:~337-351`) sends only existing rows changed since `since`. There are no tombstones.
- The hard deletes: `promotion_service.py:~329`, `price_list_service.py:~254,277`, `payment_service.py:~361`, `category_service.py:~305`.

**Fix design.**
- *Recommended:* tombstones, recorded **automatically**.
  1. A new table `sync_deletions` (`id` PK, `table_name String(50)`, `row_id Integer`, `deleted_at DateTime` indexed, plus `natural_key String(200)` nullable for association rows), created by migration.
  2. A SQLAlchemy `before_flush` session event, registered once in `cbpos/core/services/sync_change_tracking.py` (which already tracks changes; check how it hooks in), adds a `SyncDeletion` row for every deleted instance whose table is in `CATALOG_TABLES`. It fires only on the Main PC or in standalone mode, never on a till applying a pull.

     Association-only tables without ids or `last_modified` (`price_list_items` if it has no id; `composite_items`; `role_permissions`, see #872) are handled by **parent-scoped replacement**: when the parent changes, the pull sends the parent's complete child set, and the till replaces its children for that parent. Touch `last_modified` on the parent whenever children change, in the service methods that edit children.
  3. Pull response: add `"deletions": [{"table", "row_id"}…]` since the watermark. The till deletes those rows locally, in FK-safe order (children first), inside the same transaction as the upserts.
  4. Full pull: deletions since the beginning, capped by a prune policy. The Main PC prunes `sync_deletions` older than 180 days. A till that has been offline longer must run a **full catalog replace**: add `full_replace=true`, which wipes and reloads catalog tables except customers. Add it as an admin action on the till ("Reload catalog from Main PC"), and trigger it automatically when the till's `since` is older than the prune horizon.
  5. Deleting a row the till still references (e.g. a payment method used by past sales): the till must not hard-delete rows referenced by transactions. For PaymentMethod and Category, prefer soft delete (`is_active=False`) **on the Main PC** too: change those services' delete to deactivate when referenced. Check each service's current delete semantics and keep hard delete only for rows with no transactional references (promotions, price-list overrides).
- *Rejected alternatives:* "Soft delete everything" means a schema change to every catalog table plus filtering everywhere, which is too broad.
- *Data/schema:* `sync_deletions` (migration).

**Tests.**
- Unit: deleting a Promotion via the service creates one `SyncDeletion` row. No row is created when the session is in "applying pull" mode (use the flag the change-tracking module uses, or add one).
- Two-machine: `test_issue_871_deleted_promotion_and_override_gone_on_till`.
- Two-machine: `test_issue_871_recreate_same_name_after_delete_syncs`.
- `test_issue_871_stale_till_triggers_full_replace`.

**UI/UX.** On the till, Admin Tools gets the action **Reload catalog from Main PC**, with the confirm text `sync.reload_catalog_confirm` → "Replace this till's products, prices and settings with the Main PC's copy? Sales and customers on this till are kept." Run the §0.7 UI gate.

**Do NOT.**
- Do not delete transactional rows on tills.
- Do not record tombstones for customers. Customers keep the #680 flow.

**Acceptance.**
- [ ] After deleting a promotion and a price-list override on the Main PC, one cycle later neither exists nor applies on the till.

### #872 — Role permissions never sync

**Severity:** high · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail

**Problem.** Removing "Void sale" from the Cashier role on the Main PC has no effect on the tills, where cashiers can still void. Custom roles arrive on tills with no permissions.

**Evidence and root cause.**
- `role_permissions` is not in `CATALOG_TABLES` (`sync_protocol.py:46-61`).
- `model_to_dict` skips relationships (`:160-165`).
- Editing permissions doesn't bump `roles.last_modified`.

**Fix.**
1. In the pull, serialize roles with `permission_codes: [codes…]`, using a role-specific hook in the server's catalog serializer.
2. On the till, after merging the role, replace its permissions with the `Permission` rows whose `code` is in the list. Permission rows are seeded identically everywhere; if a code is missing locally, create it from the Main PC's permission row. Make sure `permissions` is in `CATALOG_TABLES`, or add it.
3. Bump `Role.last_modified = now` in every service method that changes a role's permissions (`RoleService`, `PermissionService`; `graft grep "role.permissions"`).
4. **Take effect immediately:** permissions are cached on the logged-in user object (`AuthService.verify_pin` expunges `user.role.permissions` at login, `auth_service.py:~186-194`). After a pull that changed roles, the client emits `roles_changed`. `AuthService.refresh_current_user()` reloads the current user's role and permissions. Connect it in `main.py` where the client's signals are wired.

**Tests.**
- Two-machine: `test_issue_872_revoked_permission_denied_on_till_after_one_cycle`, which checks `check_permission` on the till for the logged-in cashier.
- `test_issue_872_custom_role_arrives_with_permissions`.

**Do NOT.**
- Do not sync permission ids blindly. Ids can differ per DB, so use codes.

**Acceptance.**
- [ ] After revoking a permission on the Main PC, one cycle later `check_permission` on the till denies it, without re-login.

### #903 — Till audit logs and inventory logs never reach the Main PC

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** tdd → migration rules → ponytail

**Root cause.**
- `_FLAT_PUSH_TABLES` (`sync_client.py:65-74`) lacks `audit_logs` and `inventory_logs`.
- `push_audit_logs()` (`:801-844`) has no caller.
- `InventoryLog` has no `synced` column.

**Fix.**
1. Add `("audit_logs", AuditLog)` to `_FLAT_PUSH_TABLES` and delete `push_audit_logs` (dead).
2. Migration: add `inventory_logs.synced Boolean NOT NULL default False` (and `last_modified` if the change-tracking needs it; mirror how `audit_logs` does it). Add `("inventory_logs", InventoryLog)`.
3. Batch size: reuse the existing per-table batching. Audit logs can be many, so cap them per cycle (e.g. 500) and continue on the next cycle.
4. On the Main PC, audit rows keep `terminal_id`. The Activity Log view (`graft grep "get_recent_activity"`) must show a **Terminal** column and a filter.

**Tests.**
- Two-machine: `test_issue_903_till_login_audit_reaches_main`.
- `test_issue_903_inventory_log_pushed_once`.

**UI/UX.** Activity Log: add a Terminal column and a filter combo (`activity.terminal` "Till", `activity.all_terminals` "All tills"). Run the §0.7 UI gate.

**Acceptance.**
- [ ] A till login audit row appears on the Main PC after one cycle. Inventory logs too.

---

## Batch 2.5 — Server resilience, numbering, honest status

**Branch:** `fix/p2-b5-sync-server-resilience` · **Issues:** #870, #905, #906

### #870 — One idle TCP connection stalls the whole sync server

**Severity:** high · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail-review (security)

**Root cause.**
- `sync_server.py:~633-638` wraps the listening socket with the default `do_handshake_on_connect=True`.
- The handshake runs inside `accept()` on the single `serve_forever` thread, with no timeout.

**Fix.**
- Wrap with `do_handshake_on_connect=False`.
- Override `_ThreadedHTTPServer.finish_request` (or `process_request_thread`) to call `request.settimeout(10); request.do_handshake()` inside the per-request thread. On `ssl.SSLError`/`OSError`/`socket.timeout`: log at debug level and close.
- Also set `timeout = 30` on the request handler class, so slow clients can't hold threads forever.
- Cap concurrent request threads: a semaphore of 16. Excess connections are closed immediately with a log line.

**Test.** `test_sync_server.py::test_issue_870_idle_tcp_does_not_block_heartbeat`: open a raw `socket.create_connection` to the port and send nothing. A TLS heartbeat (using the pinned context from 2.2) answers within 1 s.

**Acceptance.**
- [ ] With an idle raw TCP connection open, a heartbeat over TLS still answers within 1 s.

### #905 — The document sequence is found by string sort

**Severity:** medium · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Root cause.**
- `document_service.py:163-177` (`_next_seq`): `ORDER BY document_number DESC` then parses the trailing digits. "INV-9" sorts above "INV-10".
- The retry loop `:275-288` recomputes the same number.

**Fix.**
- `_next_seq`: select every `document_number` with `LIKE prefix || '%'`, parse the trailing integer with `re.fullmatch(re.escape(prefix) + r"(\d+)", n)`, and take the `max`. Ignore non-matching rows.
- For performance on large shops: the prefix includes the year in default patterns, and the column is indexed, so the `LIKE prefix%` scan is bounded.
- **Recommended later:** a per-prefix counter table. Not now.
- Retry loop: on `IntegrityError` for the number, use `seq + 1` (increment locally) instead of recomputing the same max.

**Tests.**
- `test_issue_905_next_after_inv9_inv10_is_inv11`.
- `test_issue_905_rollover_99999_to_100000_to_100001`.
- `test_issue_905_retry_increments_on_collision`.

**Acceptance.**
- [ ] With INV-9 and INV-10 existing, the next number is INV-11.
- [ ] 99999 is followed by 100000, then 100001.

### #906 — A push that fails every cycle is invisible

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** tdd (pytest-qt) → ponytail; impeccable (harden) for the status widget

**Root cause.**
- `set_pending_count` and `SyncClient.pending_count` have no callers.
- A failed push goes syncing, then disconnected, then re-register, then CONNECTED ("Synced"), and repeats.
- Neither `error_signal` is connected (`main.py:~535-539, 553-556`).
- `on_terminal_connected` counts register events, not terminals.

**Fix.**
1. After each cycle, the client emits `pending_changed(int)` (unsynced row count), connected to `set_pending_count`.
2. A push failure sets the state to `STATE_ERROR` with a code (HTTP status or `PushApplyError` code). It is **not** reset to CONNECTED by a successful register. It only clears after a successful push.
3. Connect `SyncClient.error_signal` and `SyncServer.error_signal` to the widget's error state. A Main PC that fails to bind shows an error badge.
4. Count distinct terminal IDs seen in the last 5 minutes (from `sync_terminals.last_seen`, #866).
5. Per-document rejections (#866) are listed: the widget's details popup shows the last 10 errors with document numbers.

**Tests.**
- `test_issue_906_push_500_shows_error_with_pending`: mock the server returning 500. The widget state is error and pending is > 0.
- `test_issue_906_server_bind_failure_shows_error`.
- `test_issue_906_connected_terminals_counts_distinct`.

**UI/UX spec.**
- Status widget states:
  - **Synced** (green), with nothing pending;
  - **Sending N…** (cyan);
  - **Not sending: {reason}** (red), with a click-to-open details popup listing errors and a **Retry now** button;
  - **Main PC: N tills** (purple);
  - **Main PC error: {reason}** (red).
- Reasons are translated from codes (`sync.reason_*`). For example `sync.reason_protocol_too_old` → "update CB POS on this till", `sync.reason_cert_mismatch` → "Main PC security code changed".
- Run the §0.7 UI gate.

**Acceptance.**
- [ ] A client whose push returns 500 shows the error state with pending > 0.
- [ ] A Main PC whose server fails to bind shows an error.

---

## Batch 2.6 — Network-aware shifts, dashboards and transaction locking

**Branch:** `fix/p2-b6-network-shifts-dashboards-locking` · **Issues:** #886, #884, #914 · **Needs:** Phase 3A merged (`method_kind`, `RefundService`, `refunded_qty`)

### #886 — Dashboard charts fail on PostgreSQL

**Severity:** medium · **Size:** S · **Gate:** agent · **Skills:** tdd → ponytail

**Root cause.** `dashboard_service.py:162,165,226` use `func.strftime`, which is SQLite-only.

**Fix.**
- Replace it with `extract("month", Sale.date)` and `extract("hour", Sale.date)` (SQLAlchemy emits `strftime` on SQLite and `EXTRACT` on PostgreSQL).
- Replace the year filter with a half-open range: `Sale.date >= datetime(year,1,1)` and `Sale.date < datetime(year+1,1,1)`. That is index-friendly and consistent with #912's half-open rule.
- Grep for any other `func.strftime` in `cbpos/core` (`graft grep "func.strftime"`) and fix them the same way. List them in the PR.

**Tests.**
- `test_issue_886_compiled_pg_sql_has_no_strftime`: compile each dashboard query with `postgresql.dialect()` and assert `"strftime" not in str(compiled)`.
- `@pytest.mark.postgres` run of the dashboard methods.

**Acceptance.**
- [ ] The compiled PostgreSQL SQL contains no `strftime`, and the postgres test passes.

### #884 — Same cashier on two terminals: shifts count each other's sales

**Severity:** medium · **Size:** M · **Gate:** agent · **Skills:** tdd → ponytail; impeccable for the force-close UI

**Root cause.**
- `shift_service.py:29-39, 113-117, 148-178` filter by `user_id` and time only. `Shift.terminal_id` exists (`models/__init__.py:642`) but is unused in the summary.
- An orphaned OPEN shift (after a terminal ID change) can't be closed.

**Fix design.**
- *Recommended:* stamp `shift_id` on each Sale.
  - Migration adds `sales.shift_id` (nullable FK `shifts.id`, indexed). `TransactionService` sets it from the open shift for this user **and** terminal when a sale is written.
  - The summary filters `Sale.shift_id == shift.id`.
  - Legacy rows (`shift_id` null) use the old filter plus `Sale.terminal_id == shift.terminal_id`.
- `CashMovement` already has `shift_id`.
- `get_open_shift(user_id)` becomes `get_open_shift(user_id, terminal_id)`. Starting a shift on terminal B while one is open on A is allowed; they are independent.
- **Force-close:** a user with `shift.force_close` (new permission, seeded to Admin and Manager) can close a stale shift from the Shifts screen, entering the counted cash or "unknown". This writes AuditLog `SHIFT_FORCE_CLOSED`.
- Refunds (#850 / 3A): refund documents also get `shift_id` (the refunding user's open shift).
- *Sync:* `shift_id` is a local FK, and shifts sync as transaction rows. Check how `Shift` is pushed and add `shift_id` to the id-space mapping in `sync_apply_service.py:94-115`, so it maps to the Main PC's shift id.

**Tests.**
- `test_issue_884_term02_sale_not_in_term01_summary`.
- `test_issue_884_two_open_shifts_same_user`.
- `test_issue_884_force_close_requires_permission_and_audits`.

**UI/UX.** Shifts management: stale shifts (open more than 24 h, or on a terminal ID that isn't this one) show a warning tag and a **Force close…** button (permission-aware). The dialog asks for the counted cash with a "Don't know" checkbox and a required reason. Run the §0.7 UI gate.

**Acceptance.**
- [ ] A TERM-02 sale is not in the TERM-01 summary. Two open shifts for one user are tested.
- [ ] A manager can force-close a stale shift, and it is audited.

### #914 — Two tills can refund or void the same sale concurrently (network mode)

**Severity:** low · **Size:** M · **Gate:** **human**. D11 says "row locking plus a partial unique index on `refund_of_sale_id`", but D5/#812 (partial refunds) allow **several** refunds per sale, so that index would block valid partial refunds. Ask the question below before implementing the index part. The row locking can be built now.
**Skills:** tdd (postgres) → ponytail-review

**Problem.** In network mode two tills can confirm a refund of the same receipt in the same second. Both succeed: two credit notes, cash paid out twice, stock and debt restored twice.

**Evidence and root cause.**
- `transaction_service.py:540-549` (void) and `:677-694` (refund) read the sale without `with_for_update`.
- There is no DB constraint preventing over-refund.
- PostgreSQL defaults to READ COMMITTED.

**Fix design.**
1. **Row lock (build now, matches D11):** `RefundService.refund` (3A) and `void_sale` load the original sale with `session.get(Sale, id, with_for_update=True)`. The second till waits, then sees the first one's committed refund or void and fails validation. It is a no-op on SQLite.
2. **DB-enforced cap (recommended instead of the unique index):**
   - Phase 3A's `sale_items.refunded_qty` has the CHECK `ck_sale_items_refunded_qty` (`refunded_qty <= qty`).
   - Each refund increments the original lines' `refunded_qty` with an `UPDATE` in the same transaction.
   - Even without the row lock, PostgreSQL row-level write locks serialise the two updates, and the CHECK rejects the over-return of the second.
   - Void sets `sales.status = 'VOID'` under the lock, and refund validation re-reads the status under the lock.

**Tests** (`@pytest.mark.postgres`, two real connections via two `Session`s on `pg_engine`, threads plus a barrier):
- `test_issue_914_concurrent_full_refunds_one_wins`: exactly one refund document, and stock is restored once.
- `test_issue_914_concurrent_void_and_refund_one_wins`.
- `test_issue_914_check_constraint_blocks_over_return`: a direct UPDATE beyond qty raises `IntegrityError`.

**Stop & Ask (before merging):**

QUESTION (#914): D11 asked for a partial unique index on `sales.refund_of_sale_id`, but partial refunds (D5, #812) create several refunds per sale, and that index would block them. Replace the index with the CHECK constraint on `sale_items.refunded_qty` (already in Phase 3A) plus `SELECT … FOR UPDATE` row locks?
Options:
  A) Replace: row lock plus refunded_qty CHECK. Database-enforced, and compatible with partial refunds.
  B) Keep the unique index and drop partial refunds. Contradicts D5.
Recommendation: A. Record it as D16 amending D11.

**Acceptance.**
- [ ] Both methods lock the sale row.
- [ ] A DB constraint prevents over-refund: the CHECK under option A, or the index under option B.
- [ ] The concurrency tests pass on PostgreSQL in CI.

---

## Phase exit gate
- [ ] All 17 issues merged and **verified closed** with closing comments (§0.10). #832 and #922 checklists updated.
- [ ] The CI PostgreSQL job is green, and every `@pytest.mark.postgres` test passes.
- [ ] Migrations (`shop_meta`, `local_identity`, `sync_terminals` if added, `sync_id_map.origin_db_instance_id`, `sync_deletions`, `inventory_logs.synced`, `sales.shift_id`) upgrade-tested on SQLite **and** PostgreSQL.
- [ ] Two-machine harness tests pass for #836, #866, #867, #868, #869, #871, #872 and #903.
- [ ] Real two-PC smoke test, recorded in the PR (or "⚠️ Verify on Windows, two PCs" in PROGRESS.md):
  - pair;
  - sell on both;
  - edit a price, delete a promotion, revoke a permission;
  - refund on the till;
  - reinstall the till DB;
  - confirm everything converges.
- [ ] Release notes: "update every PC together", "re-pair every till once", "receipt prefixes on tills now show the full till name".
- [ ] UI gate screenshots: Network Setup stepper, schema gate dialogs, pairing (both PCs, all states), registered tills table, read-only banner, sync status states, force-close shift.
- [ ] PROGRESS.md updated. The D16 answer recorded.
