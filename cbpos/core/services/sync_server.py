"""
Sync Server for CB-POS Multi-Terminal LAN Sync.

Runs an HTTP server in a QThread on the Main PC.  Terminals connect
over LAN to push transactions and pull catalog/stock updates.

The server is intentionally simple — uses Python's built-in
``http.server`` so there are zero external dependencies.
"""

import json
import logging
import socket
import threading
from datetime import datetime
from decimal import Decimal
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from cbpos.core.database import Database
from cbpos.core.models import (
    Product,
    SyncLog,
)
from cbpos.core.services.sync_protocol import (
    SYNC_PROTOCOL_VERSION,
    EP_HEARTBEAT,
    EP_REGISTER,
    EP_PUSH_TRANSACTIONS,
    EP_PULL_CATALOG,
    EP_PULL_STOCK,
    EP_PUSH_AUDIT,
    CATALOG_TABLES,
    TRANSACTION_TABLES,
    model_to_dict,
    dict_to_model,
    sync_json_dumps,
    sync_json_loads,
    validate_envelope,
    get_model_for_table,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connected Terminal Registry
# ---------------------------------------------------------------------------
class TerminalInfo:
    """In-memory state for a connected terminal."""

    __slots__ = (
        "terminal_id",
        "ip_address",
        "registered_at",
        "last_heartbeat",
        "last_push_sequence",
        "last_catalog_sync",
    )

    def __init__(self, terminal_id: str, ip_address: str):
        self.terminal_id = terminal_id
        self.ip_address = ip_address
        self.registered_at = datetime.now()
        self.last_heartbeat = datetime.now()
        self.last_push_sequence: int = 0
        self.last_catalog_sync: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "terminal_id": self.terminal_id,
            "ip_address": self.ip_address,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "last_push_sequence": self.last_push_sequence,
            "last_catalog_sync": (
                self.last_catalog_sync.isoformat() if self.last_catalog_sync else None
            ),
        }


class TerminalRegistry:
    """Thread-safe registry of connected terminals."""

    def __init__(self):
        self._terminals: Dict[str, TerminalInfo] = {}
        self._lock = threading.Lock()

    def register(self, terminal_id: str, ip_address: str) -> TerminalInfo:
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
        with self._lock:
            info = self._terminals.get(terminal_id)
            if info:
                info.last_heartbeat = datetime.now()
                return True
            return False

    def get(self, terminal_id: str) -> Optional[TerminalInfo]:
        with self._lock:
            return self._terminals.get(terminal_id)

    def get_all(self) -> List[TerminalInfo]:
        with self._lock:
            return list(self._terminals.values())

    def update_push_sequence(self, terminal_id: str, sequence: int) -> None:
        with self._lock:
            info = self._terminals.get(terminal_id)
            if info:
                info.last_push_sequence = max(info.last_push_sequence, sequence)

    def update_catalog_sync(self, terminal_id: str) -> None:
        with self._lock:
            info = self._terminals.get(terminal_id)
            if info:
                info.last_catalog_sync = datetime.now()

    def remove(self, terminal_id: str) -> None:
        with self._lock:
            self._terminals.pop(terminal_id, None)
            logger.info("Terminal %s unregistered", terminal_id)


# Module-level registry shared between the request handler and the server
_registry = TerminalRegistry()

# Module-level reference to the server's signal emitter
_signal_emitter: Optional["SyncServer"] = None


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------
class SyncRequestHandler(BaseHTTPRequestHandler):
    """Handles incoming sync HTTP requests from terminals."""

    # Suppress default logging to stderr
    def log_message(self, fmt, *args):
        logger.debug("SyncServer HTTP: %s", fmt % args)

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Send a JSON response."""
        body = sync_json_dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Optional[Dict[str, Any]]:
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

    # --- Routing ---

    def do_GET(self):
        if self.path == EP_HEARTBEAT:
            self._handle_heartbeat()
        elif self.path.startswith(EP_PULL_CATALOG):
            self._handle_pull_catalog()
        elif self.path.startswith(EP_PULL_STOCK):
            self._handle_pull_stock()
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
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
        self._send_json({
            "status": "ok",
            "protocol_version": SYNC_PROTOCOL_VERSION,
            "server_time": datetime.now().isoformat(),
            "terminals_connected": len(_registry.get_all()),
        })

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
        info = _registry.register(terminal_id, ip)

        # Emit signal for UI updates
        if _signal_emitter:
            _signal_emitter.terminal_connected.emit(terminal_id)

        self._send_json({
            "status": "registered",
            "terminal_id": terminal_id,
            "server_time": datetime.now().isoformat(),
            "protocol_version": SYNC_PROTOCOL_VERSION,
        })

    def _handle_pull_catalog(self):
        """GET /sync/pull-catalog?since=ISO_TIMESTAMP&terminal_id=TERM-XX

        Returns all catalog records modified after ``since``.
        If ``since`` is omitted, returns all records (full sync).
        """
        from urllib.parse import urlparse, parse_qs

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

        payload: Dict[str, List[Dict[str, Any]]] = {}
        total_records = 0

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

        now = datetime.now()
        if terminal_id:
            _registry.update_catalog_sync(terminal_id)

        logger.info(
            "Catalog pull for %s: %d records across %d tables (since=%s)",
            terminal_id or "unknown",
            total_records,
            len(payload),
            since_str or "full",
        )

        self._send_json({
            "status": "ok",
            "timestamp": now.isoformat(),
            "total_records": total_records,
            "payload": payload,
        })

    def _handle_pull_stock(self):
        """GET /sync/pull-stock — returns current stock quantities for all products."""
        db = Database()
        with db.get_session() as session:
            products = session.query(
                Product.id, Product.stock_qty, Product.version_id
            ).all()
            stock_data = [
                {
                    "id": p.id,
                    "stock_qty": str(p.stock_qty),
                    "version_id": p.version_id,
                }
                for p in products
            ]

        self._send_json({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "products": stock_data,
        })

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

        # Check for duplicate sequence
        info = _registry.get(terminal_id)
        if info and sequence and sequence <= info.last_push_sequence:
            logger.info(
                "Duplicate push from %s (seq %d <= %d), acknowledging",
                terminal_id, sequence, info.last_push_sequence,
            )
            self._send_json({
                "status": "duplicate",
                "sequence": sequence,
                "message": "Already processed",
            })
            return

        # Process each table in the payload
        records_applied = 0
        errors: List[str] = []
        db = Database()

        try:
            with db.get_session() as session:
                for table_name, records in payload.items():
                    if not isinstance(records, list):
                        continue

                    model_class = get_model_for_table(table_name)
                    if model_class is None:
                        errors.append(f"Unknown table: {table_name}")
                        continue

                    for record_data in records:
                        try:
                            self._apply_record(
                                session, model_class, table_name, record_data
                            )
                            records_applied += 1
                        except Exception as e:
                            error_msg = f"{table_name}[{record_data.get('id', '?')}]: {e}"
                            errors.append(error_msg)
                            logger.error("Error applying record: %s", error_msg)

                # Mark synced
                session.commit()

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
        self._send_json({
            "status": status,
            "sequence": sequence,
            "records_applied": records_applied,
            "errors": errors,
        })

    def _apply_record(
        self,
        session,
        model_class,
        table_name: str,
        record_data: Dict[str, Any],
    ) -> None:
        """Apply a single synced record to the database.

        Uses merge() to handle both INSERT (new record from terminal)
        and UPDATE (e.g., terminal re-sends a corrected record).
        """
        # Handle child records that are nested inside parent records
        # (e.g., Sale.items, Sale.payments come as nested lists)
        child_data = {}
        for key, value in list(record_data.items()):
            if isinstance(value, list):
                child_data[key] = record_data.pop(key)

        instance = dict_to_model(model_class, record_data)
        instance.synced = True  # Mark as synced on the server side
        session.merge(instance)

        # Process children
        for rel_key, children in child_data.items():
            # Determine child model from the relationship
            mapper = model_class.__mapper__
            rel = mapper.relationships.get(rel_key)
            if rel is None:
                continue
            child_class = rel.mapper.class_
            for child_record in children:
                child_instance = dict_to_model(child_class, child_record)
                session.merge(child_instance)

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
            from cbpos.core.models import AuditLog

            with db.get_session() as session:
                for record_data in audit_records:
                    try:
                        entry = dict_to_model(AuditLog, record_data)
                        entry.synced = True
                        session.merge(entry)
                        records_applied += 1
                    except Exception as e:
                        logger.error("Error applying audit log: %s", e)

                session.commit()

        except Exception as e:
            logger.error("Audit push failed: %s", e)
            self._send_json({"error": str(e)}, 500)
            return

        self._log_sync(terminal_id, "PUSH", "AUDIT", records_applied, [])

        self._send_json({
            "status": "ok",
            "records_applied": records_applied,
        })

    @staticmethod
    def _log_sync(
        terminal_id: str,
        direction: str,
        sync_type: str,
        records_count: int,
        errors: List[str],
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
class _ThreadedHTTPServer(HTTPServer):
    """HTTPServer that handles each request in a new thread."""

    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
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
        super().__init__(parent)
        self._port = port
        self._server: Optional[_ThreadedHTTPServer] = None
        self._running = False

    @property
    def port(self) -> int:
        return self._port

    @property
    def registry(self) -> TerminalRegistry:
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
            self._server = _ThreadedHTTPServer(
                ("0.0.0.0", self._port), SyncRequestHandler
            )
            self._running = True

            address = self.get_server_address()
            logger.info("Sync server listening on %s", address)
            self.started_signal.emit(address)

            # Serve until stopped
            while self._running:
                self._server.handle_request()

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
