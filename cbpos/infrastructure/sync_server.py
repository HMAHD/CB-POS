"""
Sync Server for CB-POS Multi-Terminal LAN Sync.

Runs an HTTP server in a QThread on the Main PC.  Terminals connect
over LAN to push transactions and pull catalog/stock updates.

The server is intentionally simple — uses Python's built-in
``http.server`` so there are zero external dependencies.
"""

import hmac
import logging
import secrets
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from PyQt6.QtCore import QThread, pyqtSignal
from sqlalchemy.orm.exc import StaleDataError

from cbpos.core.database import Database
from cbpos.core.models import (
    Product,
    SyncLog,
)
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.sync_apply_service import SyncApplyService
from cbpos.core.services.sync_protocol import (
    CATALOG_TABLES,
    EP_HEARTBEAT,
    EP_PULL_CATALOG,
    EP_PULL_STOCK,
    EP_PUSH_AUDIT,
    EP_PUSH_TRANSACTIONS,
    EP_REGISTER,
    SYNC_PROTOCOL_VERSION,
    get_model_for_table,
    model_to_dict,
    sync_json_dumps,
    sync_json_loads,
    validate_envelope,
)

logger = logging.getLogger(__name__)


def get_or_create_main_instance_id() -> str:
    """Return this machine's persistent Main PC identity, generating one
    on first use.

    Terminals remember whichever instance_id they first synced with and
    refuse to keep syncing if it ever changes (see SyncClient) — this is
    what lets a terminal detect "I'm now talking to a different machine
    than the one I trusted", e.g. a second PC accidentally configured as
    Main PC at the same address, without needing any network discovery.
    """
    instance_id = ConfigService.get("main_pc_instance_id")
    if not instance_id:
        instance_id = secrets.token_hex(8)
        ConfigService.set("main_pc_instance_id", instance_id)
    return instance_id


# ---------------------------------------------------------------------------
# Connected Terminal Registry
# ---------------------------------------------------------------------------
class TerminalInfo:
    """In-memory state for a connected terminal."""

    __slots__ = (
        "ip_address",
        "last_catalog_sync",
        "last_heartbeat",
        "last_push_sequence",
        "registered_at",
        "terminal_id",
    )

    def __init__(self, terminal_id: str, ip_address: str):
        """Initialize registration and heartbeat timestamps for a newly connected terminal."""
        self.terminal_id = terminal_id
        self.ip_address = ip_address
        self.registered_at = datetime.now()
        self.last_heartbeat = datetime.now()
        self.last_push_sequence: int = 0
        self.last_catalog_sync: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this terminal's state to a JSON-friendly dict."""
        return {
            "terminal_id": self.terminal_id,
            "ip_address": self.ip_address,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "last_push_sequence": self.last_push_sequence,
            "last_catalog_sync": (self.last_catalog_sync.isoformat() if self.last_catalog_sync else None),
        }


class TerminalRegistry:
    """Thread-safe registry of connected terminals."""

    def __init__(self):
        """Initialize an empty, thread-safe terminal registry."""
        self._terminals: dict[str, TerminalInfo] = {}
        self._lock = threading.Lock()

    def register(self, terminal_id: str, ip_address: str) -> TerminalInfo:
        """Register a terminal by ID, or refresh its IP and heartbeat if already known."""
        with self._lock:
            if terminal_id in self._terminals:
                info = self._terminals[terminal_id]
                info.ip_address = ip_address
                info.last_heartbeat = datetime.now()
                logger.info("Terminal %s re-registered from %s", terminal_id, ip_address)
            else:
                info = TerminalInfo(terminal_id, ip_address)
                self._terminals[terminal_id] = info
                logger.info("Terminal %s registered from %s", terminal_id, ip_address)
            return info

    def heartbeat(self, terminal_id: str) -> bool:
        """Update the last-heartbeat timestamp for a terminal.

        Returns:
            True if the terminal was known and updated, False otherwise.
        """
        with self._lock:
            info = self._terminals.get(terminal_id)
            if info:
                info.last_heartbeat = datetime.now()
                return True
            return False

    def get(self, terminal_id: str) -> TerminalInfo | None:
        """Return the TerminalInfo for a terminal ID, or None if not registered."""
        with self._lock:
            return self._terminals.get(terminal_id)

    def get_all(self) -> list[TerminalInfo]:
        """Return a snapshot list of all registered terminals."""
        with self._lock:
            return list(self._terminals.values())

    def update_push_sequence(self, terminal_id: str, sequence: int) -> None:
        """Record the highest push sequence number seen from a terminal."""
        with self._lock:
            info = self._terminals.get(terminal_id)
            if info:
                info.last_push_sequence = max(info.last_push_sequence, sequence)

    def update_catalog_sync(self, terminal_id: str) -> None:
        """Record that a terminal just completed a catalog pull."""
        with self._lock:
            info = self._terminals.get(terminal_id)
            if info:
                info.last_catalog_sync = datetime.now()

    def remove(self, terminal_id: str) -> None:
        """Unregister a terminal."""
        with self._lock:
            self._terminals.pop(terminal_id, None)
            logger.info("Terminal %s unregistered", terminal_id)


# Module-level registry shared between the request handler and the server
_registry = TerminalRegistry()

# Module-level reference to the server's signal emitter
_signal_emitter: Optional["SyncServer"] = None

# Pushes are applied one at a time. Each request runs on its own thread,
# and applying a batch is "look up the till's id in sync_id_map, insert if
# absent": two overlapping pushes of the same batch (a till retrying while
# its first attempt is still being applied) would otherwise both miss the
# map and both insert. The map's unique constraint would reject the second
# commit anyway; the lock just keeps that from surfacing as a 500.
_push_apply_lock = threading.Lock()


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------
class SyncRequestHandler(BaseHTTPRequestHandler):
    """Handles incoming sync HTTP requests from terminals."""

    # Suppress default logging to stderr
    def log_message(self, fmt, *args):
        """Redirect BaseHTTPRequestHandler's default stderr access log to the app logger."""
        logger.debug("SyncServer HTTP: %s", fmt % args)

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Send a JSON response."""
        body = sync_json_dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any] | None:
        """Read and parse the JSON request body."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return None
            raw = self.rfile.read(length)
            return sync_json_loads(raw.decode("utf-8"))
        except Exception as e:
            logger.error("Failed to read JSON body: %s", e)
            return None

    def _authorized(self) -> bool:
        """Validate the caller against the configured shared secret.

        A blank/unconfigured secret does not mean "open to anyone" — it
        means sync is not correctly set up, so every request is refused
        until a non-empty secret is configured on both ends.
        """
        expected = ConfigService.get("sync_shared_secret") or ""
        if not expected:
            return False
        provided = self.headers.get("X-Sync-Token", "")
        return hmac.compare_digest(provided, expected)

    # --- Routing ---

    def do_GET(self):
        """Route an authorized GET request to heartbeat, pull-catalog, or pull-stock; 401/404 otherwise."""
        if not self._authorized():
            self._send_json({"error": "Unauthorized"}, 401)
            return
        if self.path == EP_HEARTBEAT:
            self._handle_heartbeat()
        elif self.path.startswith(EP_PULL_CATALOG):
            self._handle_pull_catalog()
        elif self.path.startswith(EP_PULL_STOCK):
            self._handle_pull_stock()
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        """Route an authorized POST request to register, push-transactions, or push-audit; 401/404 otherwise."""
        if not self._authorized():
            self._send_json({"error": "Unauthorized"}, 401)
            return
        if self.path == EP_REGISTER:
            self._handle_register()
        elif self.path == EP_PUSH_TRANSACTIONS:
            self._handle_push_transactions()
        elif self.path == EP_PUSH_AUDIT:
            self._handle_push_audit()
        else:
            self._send_json({"error": "Not found"}, 404)

    # --- Endpoint Implementations ---

    def _handle_heartbeat(self):
        """GET /sync/heartbeat — connection health check."""
        self._send_json(
            {
                "status": "ok",
                "protocol_version": SYNC_PROTOCOL_VERSION,
                "server_time": datetime.now().isoformat(),
                "terminals_connected": len(_registry.get_all()),
                "main_instance_id": get_or_create_main_instance_id(),
            }
        )

    def _handle_register(self):
        """POST /sync/register — terminal announces itself."""
        data = self._read_json()
        if not data:
            self._send_json({"error": "Empty body"}, 400)
            return

        terminal_id = data.get("terminal_id")
        if not terminal_id:
            self._send_json({"error": "terminal_id required"}, 400)
            return

        ip = self.client_address[0]
        _registry.register(terminal_id, ip)

        # Emit signal for UI updates
        if _signal_emitter:
            _signal_emitter.terminal_connected.emit(terminal_id)

        self._send_json(
            {
                "status": "registered",
                "terminal_id": terminal_id,
                "server_time": datetime.now().isoformat(),
                "protocol_version": SYNC_PROTOCOL_VERSION,
                "main_instance_id": get_or_create_main_instance_id(),
            }
        )

    def _handle_pull_catalog(self):
        """GET /sync/pull-catalog?since=ISO_TIMESTAMP&terminal_id=TERM-XX

        Returns all catalog records modified after ``since``.
        If ``since`` is omitted, returns all records (full sync).
        """
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        since_str = params.get("since", [None])[0]
        terminal_id = params.get("terminal_id", [None])[0]

        since = None
        if since_str:
            try:
                since = datetime.fromisoformat(since_str)
            except ValueError:
                self._send_json({"error": f"Invalid since format: {since_str}"}, 400)
                return

        payload: dict[str, list[dict[str, Any]]] = {}
        total_records = 0

        # Captured before querying, not after: a row edited while this
        # request is running must have last_modified >= now so it's
        # picked up by the *next* pull. Capturing it after the query loop
        # would let that edit's timestamp fall inside the gap between
        # "already queried" and "new watermark", and it would never be
        # seen again — this is the server-side half of not depending on
        # wall-clock agreement between machines (see SyncClient._pull_catalog,
        # which trusts this timestamp rather than its own clock).
        now = datetime.now()

        db = Database()
        with db.get_session() as session:
            for table_name in CATALOG_TABLES:
                model_class = get_model_for_table(table_name)
                if model_class is None:
                    continue

                query = session.query(model_class)

                # Apply since filter if the model has last_modified
                if since and hasattr(model_class, "last_modified"):
                    query = query.filter(model_class.last_modified > since)

                records = query.all()
                if records:
                    payload[table_name] = [model_to_dict(r) for r in records]
                    total_records += len(records)

        if terminal_id:
            _registry.update_catalog_sync(terminal_id)

        logger.info(
            "Catalog pull for %s: %d records across %d tables (since=%s)",
            terminal_id or "unknown",
            total_records,
            len(payload),
            since_str or "full",
        )

        self._send_json(
            {
                "status": "ok",
                "timestamp": now.isoformat(),
                "total_records": total_records,
                "payload": payload,
            }
        )

    def _handle_pull_stock(self):
        """GET /sync/pull-stock — returns current stock quantities for all products."""
        db = Database()
        with db.get_session() as session:
            products = session.query(Product.id, Product.stock_qty, Product.version_id).all()
            stock_data = [
                {
                    "id": p.id,
                    "stock_qty": str(p.stock_qty),
                    "version_id": p.version_id,
                }
                for p in products
            ]

        self._send_json(
            {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "products": stock_data,
            }
        )

    def _handle_push_transactions(self):
        """POST /sync/push-transactions — terminal pushes new sales/transactions."""
        data = self._read_json()
        if not data:
            self._send_json({"error": "Empty body"}, 400)
            return

        valid, err = validate_envelope(data)
        if not valid:
            self._send_json({"error": err}, 400)
            return

        terminal_id = data["terminal_id"]
        sequence = data.get("sequence", 0)
        payload = data.get("payload", {})

        # No "sequence already seen -> acknowledge without applying" shortcut:
        # a till's sequence restarts at 1 whenever the till app restarts, while
        # this registry keeps the old high-water mark, so that shortcut acked
        # a restarted till's new sales as "duplicate" and the till then marked
        # them synced -- lost. Re-sends are safe to apply: each row is found
        # again through sync_id_map and stock moves only on first arrival.

        # Rows are re-keyed to Main PC ids through sync_id_map (see
        # SyncApplyService, #671), all or nothing: the till marks every row
        # it sent as synced once the push is acknowledged, so a half-applied
        # batch would silently lose the rows that failed. Wrapped in a
        # bounded retry: two terminals pushing StockMovements for the same
        # Product at nearly the same time can lose the optimistic-lock race
        # on Product's version_id column — expected under concurrency, so
        # retry with a fresh read rather than failing the whole batch.
        db = Database()
        max_attempts = 3
        records_applied = 0
        errors: list[str] = []

        for attempt in range(1, max_attempts + 1):
            try:
                with _push_apply_lock, db.get_session() as session:
                    records_applied, errors = SyncApplyService(session, terminal_id).apply_batch(payload)
                    session.commit()
                break  # success — exit retry loop

            except StaleDataError as e:
                logger.warning(
                    "Stock conflict applying push from %s (attempt %d/%d): %s",
                    terminal_id,
                    attempt,
                    max_attempts,
                    e,
                )
                if attempt == max_attempts:
                    self._send_json({"error": f"Conflict applying update, retries exhausted: {e}"}, 409)
                    return
                continue  # retry against a fresh session/read

            except Exception as e:
                logger.error("Transaction push failed: %s", e)
                self._send_json({"error": str(e)}, 500)
                return

        # Update sequence tracking
        if sequence:
            _registry.update_push_sequence(terminal_id, sequence)

        # Log the sync operation
        self._log_sync(terminal_id, "PUSH", "TRANSACTIONS", records_applied, errors)

        # Emit signal for UI updates
        if _signal_emitter:
            _signal_emitter.sync_completed.emit(terminal_id, records_applied)

        status = "ok" if not errors else "partial"
        self._send_json(
            {
                "status": status,
                "sequence": sequence,
                "records_applied": records_applied,
                "errors": errors,
            }
        )

    def _handle_push_audit(self):
        """POST /sync/push-audit — terminal pushes audit log entries."""
        data = self._read_json()
        if not data:
            self._send_json({"error": "Empty body"}, 400)
            return

        valid, err = validate_envelope(data)
        if not valid:
            self._send_json({"error": err}, 400)
            return

        terminal_id = data["terminal_id"]
        payload = data.get("payload", {})
        audit_records = payload.get("audit_logs", [])

        records_applied = 0
        db = Database()

        try:
            # Same id re-keying as transactions (#671): audit ids are per
            # till too, and merging by them overwrote the Main PC's own
            # audit entries and other tills'.
            with _push_apply_lock, db.get_session() as session:
                records_applied, _ = SyncApplyService(session, terminal_id).apply_batch({"audit_logs": audit_records})
                session.commit()

        except Exception as e:
            logger.error("Audit push failed: %s", e)
            self._send_json({"error": str(e)}, 500)
            return

        self._log_sync(terminal_id, "PUSH", "AUDIT", records_applied, [])

        self._send_json(
            {
                "status": "ok",
                "records_applied": records_applied,
            }
        )

    @staticmethod
    def _log_sync(
        terminal_id: str,
        direction: str,
        sync_type: str,
        records_count: int,
        errors: list[str],
    ) -> None:
        """Write a SyncLog entry to the database."""
        try:
            db = Database()
            with db.get_session() as session:
                log = SyncLog(
                    terminal_id=terminal_id,
                    direction=direction,
                    sync_type=sync_type,
                    records_count=records_count,
                    status="SUCCESS" if not errors else "PARTIAL",
                    error_message="; ".join(errors[:5]) if errors else None,
                    started_at=datetime.now(),
                    completed_at=datetime.now(),
                )
                session.add(log)
                session.commit()
        except Exception as e:
            logger.error("Failed to write SyncLog: %s", e)


# ---------------------------------------------------------------------------
# Threaded HTTP Server
# ---------------------------------------------------------------------------
class _ThreadedHTTPServer(ThreadingHTTPServer):
    """Handles each sync request in its own thread.

    Without this, a slow request (e.g. a full catalog pull while the
    product list is large) would block heartbeats, registrations, and
    pushes from every other terminal until it finished.
    """

    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        """Log an unhandled request error instead of printing a traceback to stderr."""
        logger.error("SyncServer error from %s", client_address, exc_info=True)


# ---------------------------------------------------------------------------
# SyncServer QThread — runs the HTTP server in a background thread
# ---------------------------------------------------------------------------
class SyncServer(QThread):
    """QThread that runs the sync HTTP server on the Main PC.

    Signals:
        started_signal: Emitted when the server starts listening.
        stopped_signal: Emitted when the server shuts down.
        terminal_connected: Emitted when a terminal registers (terminal_id).
        sync_completed: Emitted after a sync push is processed (terminal_id, count).
        error_signal: Emitted on server error (error message).
    """

    started_signal = pyqtSignal(str)  # listening address
    stopped_signal = pyqtSignal()
    terminal_connected = pyqtSignal(str)  # terminal_id
    sync_completed = pyqtSignal(str, int)  # terminal_id, records_count
    error_signal = pyqtSignal(str)  # error message

    def __init__(self, port: int = 5555, parent=None):
        """Initialize the server thread on the given port, not yet listening.

        Args:
            port: TCP port to bind when ``run()`` starts the HTTP server.
            parent: Optional QObject parent.
        """
        super().__init__(parent)
        self._port = port
        self._server: _ThreadedHTTPServer | None = None
        self._running = False

    @property
    def port(self) -> int:
        """Return the configured listening port."""
        return self._port

    @property
    def registry(self) -> TerminalRegistry:
        """Return the shared registry of connected terminals."""
        return _registry

    def get_server_address(self) -> str:
        """Return the LAN IP address of this machine."""
        try:
            # Create a UDP socket to determine the LAN IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            # Doesn't actually send data, just opens a route
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            s.close()
            return f"{ip}:{self._port}"
        except Exception:
            return f"127.0.0.1:{self._port}"

    def run(self):
        """Main thread loop — starts the HTTP server."""
        global _signal_emitter
        _signal_emitter = self

        try:
            self._server = _ThreadedHTTPServer(("0.0.0.0", self._port), SyncRequestHandler)

            from cbpos.infrastructure.sync_tls import build_server_ssl_context

            ssl_context = build_server_ssl_context()
            self._server.socket = ssl_context.wrap_socket(self._server.socket, server_side=True)

            self._running = True

            address = self.get_server_address()
            logger.info("Sync server listening on %s (TLS)", address)
            self.started_signal.emit(address)

            # Blocks here, dispatching each request to its own thread,
            # until stop() calls self._server.shutdown().
            self._server.serve_forever(poll_interval=0.2)

        except OSError as e:
            error_msg = f"Sync server failed to start on port {self._port}: {e}"
            logger.error(error_msg)
            self.error_signal.emit(error_msg)
        except Exception as e:
            logger.error("Sync server error: %s", e, exc_info=True)
            self.error_signal.emit(str(e))
        finally:
            if self._server:
                self._server.server_close()
            self._running = False
            _signal_emitter = None
            self.stopped_signal.emit()
            logger.info("Sync server stopped")

    def stop(self):
        """Stop the sync server gracefully."""
        self._running = False
        if self._server:
            self._server.shutdown()
        self.quit()
        self.wait(5000)  # Wait up to 5 seconds for thread to finish
