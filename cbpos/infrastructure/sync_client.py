"""
Sync Client for CB-POS Multi-Terminal LAN Sync.

Runs a background QThread on Terminal PCs.  Periodically pushes
local transactions to the Main PC and pulls catalog/stock updates.

Features:

- Automatic reconnection on network failure
- Resumable sync via sequence numbers
- Qt signals for UI status feedback
- Initial full sync on first connection
"""

import logging
import urllib.error
import urllib.request
from datetime import datetime
from decimal import Decimal
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal
from sqlalchemy import func

from cbpos.core.database import Database
from cbpos.core.models import (
    AuditLog,
    CashMovement,
    CustomerLedgerEntry,
    CustomerPayment,
    Document,
    Product,
    Purchase,
    Sale,
    Shift,
    StockMovement,
    SupplierLedgerEntry,
    SupplierPayment,
)
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.sync_protocol import (
    CATALOG_TABLES,
    EP_PULL_CATALOG,
    EP_PULL_STOCK,
    EP_PUSH_AUDIT,
    EP_PUSH_TRANSACTIONS,
    EP_REGISTER,
    dict_to_model,
    get_model_for_table,
    make_envelope,
    model_to_dict,
    sync_json_dumps,
    sync_json_loads,
)

logger = logging.getLogger(__name__)

# Pushed tables without children, in push order: (table name, model).
_FLAT_PUSH_TABLES: tuple[tuple[str, type], ...] = (
    ("stock_movements", StockMovement),
    ("shifts", Shift),
    ("cash_movements", CashMovement),
    ("customer_payments", CustomerPayment),
    ("customer_ledger", CustomerLedgerEntry),
    ("supplier_payments", SupplierPayment),
    ("supplier_ledger", SupplierLedgerEntry),
)

# Children pushed with their document: relationship names per document type.
_PUSHED_CHILDREN: dict[type, tuple[str, ...]] = {
    Sale: ("items", "payments"),
    Purchase: ("items",),
}


# Balance owner table -> (its ledger model, balance column) (#678).
_BALANCE_LEDGERS: dict[str, tuple[type, str]] = {
    "customers": (CustomerLedgerEntry, "current_debt"),
    "suppliers": (SupplierLedgerEntry, "current_payable"),
}


def _set_local_balance(session: Any, table_name: str, owner_id: int, main_value: Decimal) -> None:
    """Set a customer's debt / supplier's payable on this till from the Main PC's figure.

    The Main PC's balance covers every till's *pushed* ledger rows; this
    till's own rows that are not pushed yet are added on top, so a credit
    sale made since the last push isn't wiped out by a catalog pull.
    """
    ledger_model, balance_column = _BALANCE_LEDGERS[table_name]
    owner = session.get(get_model_for_table(table_name), owner_id)
    if owner is None:
        return
    owner_column = "customer_id" if table_name == "customers" else "supplier_id"
    unpushed = (
        session.query(func.coalesce(func.sum(ledger_model.amount), 0))
        .filter(getattr(ledger_model, owner_column) == owner_id, ledger_model.synced.is_(False))
        .scalar()
    )
    setattr(owner, balance_column, (main_value + Decimal(str(unpushed or 0))).quantize(Decimal("0.01")))


def _fingerprint(obj: Any) -> str:
    """Snapshot a pushed row (and the children pushed with it), ignoring ``synced``."""
    row = model_to_dict(obj)
    row.pop("synced", None)
    for relationship in _PUSHED_CHILDREN.get(type(obj), ()):
        row[relationship] = sorted(
            (model_to_dict(child) for child in getattr(obj, relationship)), key=lambda c: c.get("id") or 0
        )
    return sync_json_dumps(row)


class SyncClient(QThread):
    """Background sync client that connects to the Main PC.

    Signals:

    - status_changed: connection status changed ('connected', 'syncing',
      'disconnected', 'error')
    - sync_completed: a sync cycle finished (pushed_count, pulled_count)
    - initial_sync_completed: the first full catalog sync finished
    - error_signal: an error occurred (error message)
    """

    status_changed = pyqtSignal(str)  # status string
    sync_completed = pyqtSignal(int, int)  # pushed, pulled
    initial_sync_completed = pyqtSignal()
    error_signal = pyqtSignal(str)

    # Connection states
    STATE_DISCONNECTED = "disconnected"
    STATE_CONNECTED = "connected"
    STATE_SYNCING = "syncing"
    STATE_ERROR = "error"

    def __init__(
        self,
        terminal_id: str,
        server_address: str,
        sync_interval: int = 3,
        shared_secret: str = "",
        parent=None,
    ):
        """Initialize the client for a given terminal and Main PC address.

        Normalizes ``server_address`` to always use ``https://`` — sync is
        always over TLS regardless of whether a bare "host:port" or a
        leftover pre-TLS "http://" value was configured.

        Args:
            terminal_id: This terminal's identifier, sent on every request.
            server_address: Main PC host[:port], with or without a scheme.
            sync_interval: Seconds between sync cycles.
            shared_secret: Token sent as ``X-Sync-Token`` on every request.
            parent: Optional QObject parent.
        """
        super().__init__(parent)
        self._terminal_id = terminal_id
        self._server_address = server_address.rstrip("/")
        self._sync_interval = sync_interval  # seconds
        self._shared_secret = shared_secret
        self._running = False
        self._state = self.STATE_DISCONNECTED
        self._push_sequence = 0
        self._last_catalog_sync: datetime | None = None
        self._initial_sync_done = False
        self._consecutive_failures = 0
        self._max_retries = 3

        # Sync is always over TLS — normalize to https:// regardless of
        # what was typed in (bare "host:port", or an old "http://" value
        # left over from before TLS support).
        if self._server_address.startswith("http://"):
            self._server_address = "https://" + self._server_address[len("http://") :]
        elif not self._server_address.startswith("https://"):
            self._server_address = f"https://{self._server_address}"

        from cbpos.infrastructure.sync_tls import build_client_ssl_context

        self._ssl_context = build_client_ssl_context()

    @property
    def state(self) -> str:
        """Return the current connection state string."""
        return self._state

    @property
    def terminal_id(self) -> str:
        """Return this terminal's configured identifier."""
        return self._terminal_id

    @property
    def is_connected(self) -> bool:
        """Return True if currently connected or mid-sync-cycle."""
        return self._state in (self.STATE_CONNECTED, self.STATE_SYNCING)

    @property
    def pending_count(self) -> int:
        """Return number of unsynced transactions."""
        try:
            db = Database()
            with db.get_session() as session:
                return session.query(Document).filter_by(synced=False).count()
        except Exception:
            return 0

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.status_changed.emit(state)

    # --- HTTP Helpers ---

    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
        timeout: int = 10,
    ) -> dict[str, Any] | None:
        """Make an HTTP request to the sync server.

        Returns the parsed JSON response or None on error.
        """
        url = f"{self._server_address}{endpoint}"
        try:
            headers = {"X-Sync-Token": self._shared_secret}
            if data is not None:
                body = sync_json_dumps(data).encode("utf-8")
                headers["Content-Type"] = "application/json; charset=utf-8"
                req = urllib.request.Request(url, data=body, method=method, headers=headers)
            else:
                req = urllib.request.Request(url, method=method, headers=headers)

            with urllib.request.urlopen(req, timeout=timeout, context=self._ssl_context) as resp:
                raw = resp.read().decode("utf-8")
                return sync_json_loads(raw)

        except urllib.error.URLError as e:
            logger.debug("Sync request failed (%s %s): %s", method, endpoint, e)
            return None
        except Exception as e:
            logger.error("Sync request error (%s %s): %s", method, endpoint, e)
            return None

    # --- Main Thread Loop ---

    def run(self):
        """Main sync loop — register, then periodically push and pull."""
        self._running = True
        logger.info(
            "SyncClient starting: terminal=%s, server=%s, interval=%ds",
            self._terminal_id,
            self._server_address,
            self._sync_interval,
        )

        while self._running:
            try:
                # Step 1: Ensure we're registered
                if not self.is_connected:
                    if self._try_register():
                        self._consecutive_failures = 0
                        self._set_state(self.STATE_CONNECTED)

                        # Do initial full sync on first connection
                        if not self._initial_sync_done:
                            self._do_initial_sync()
                    else:
                        self._consecutive_failures += 1
                        self._set_state(self.STATE_DISCONNECTED)
                        # Back off on repeated failures
                        backoff = min(self._sync_interval * self._consecutive_failures, 30)
                        self._sleep(backoff)
                        continue

                # Step 2: Run a sync cycle
                self._set_state(self.STATE_SYNCING)
                pushed, pulled = self._sync_cycle()

                if pushed >= 0 and pulled >= 0:
                    self._consecutive_failures = 0
                    self._set_state(self.STATE_CONNECTED)
                    self.sync_completed.emit(max(pushed, 0), max(pulled, 0))
                else:
                    self._consecutive_failures += 1
                    if self._consecutive_failures >= self._max_retries:
                        self._set_state(self.STATE_DISCONNECTED)

            except Exception as e:
                logger.error("Sync cycle error: %s", e, exc_info=True)
                self._set_state(self.STATE_ERROR)
                self.error_signal.emit(str(e))

            # Wait for next cycle
            self._sleep(self._sync_interval)

        logger.info("SyncClient stopped")

    def _sync_cycle(self) -> tuple[int, int]:
        """Push local changes, then pull the catalog and stock.

        Returns:
            (records pushed, catalog records pulled); -1 for a failed step.
        """
        pushed = self._push_transactions()
        pulled = self._pull_catalog()
        self._pull_stock()
        return pushed, pulled

    def _sleep(self, seconds: int) -> None:
        """Sleep that can be interrupted by stop()."""
        for _ in range(seconds * 10):  # Check every 100ms
            if not self._running:
                return
            self.msleep(100)

    def stop(self):
        """Stop the sync client gracefully."""
        self._running = False
        self.quit()
        self.wait(5000)

    # --- Registration ---

    def _try_register(self) -> bool:
        """Register with the Main PC."""
        result = self._request(
            "POST",
            EP_REGISTER,
            {
                "terminal_id": self._terminal_id,
            },
        )
        if result and result.get("status") == "registered":
            if not self._check_main_identity(result.get("main_instance_id")):
                return False
            logger.info("Registered with Main PC as %s", self._terminal_id)
            return True
        return False

    def _check_main_identity(self, main_instance_id: str | None) -> bool:
        """Verify the Main PC we just registered with is the one we've
        trusted since our first successful connection.

        Terminal mode has no discovery/election protocol — nothing stops
        a second machine from being configured as "Main PC" at the same
        address. Pinning the instance_id on first connection and refusing
        to silently follow a change is what catches that, rather than
        quietly syncing against a different machine than the shop
        actually intended.
        """
        if not main_instance_id:
            return True  # unrecognized server response shape — don't break on it

        known = ConfigService.get("sync_known_main_instance_id") or ""
        if not known:
            ConfigService.set("sync_known_main_instance_id", main_instance_id)
            return True
        if known != main_instance_id:
            logger.error(
                "Main PC identity changed (expected %s, got %s) — refusing to "
                "sync. If you intentionally replaced the Main PC, clear the "
                "trusted identity in Settings > Network > LAN Sync.",
                known,
                main_instance_id,
            )
            return False
        return True

    # --- Initial Full Sync ---

    def _do_initial_sync(self) -> None:
        """Pull the complete catalog from Main PC on first connection."""
        logger.info("Starting initial full catalog sync...")
        self._set_state(self.STATE_SYNCING)

        pulled = self._pull_catalog(full_sync=True)
        self._pull_stock()

        if pulled >= 0:
            self._initial_sync_done = True
            self.initial_sync_completed.emit()
            logger.info("Initial sync complete: %d records pulled", pulled)
        else:
            logger.warning("Initial sync failed, will retry")

    # --- Push Transactions ---

    def _push_transactions(self) -> int:
        """Push unsynced local transactions to the Main PC.

        A row is unsynced when it is new or changed since its last push
        (#677, see sync_change_tracking), so voids, GRN commits and shift
        closes are sent again and the Main PC updates its copy in place.

        Returns the number of records pushed, or -1 on error.
        """
        try:
            payload, fingerprints = self._collect_unsynced()
        except Exception as e:
            logger.error("Error collecting unsynced transactions: %s", e)
            return -1

        if not payload:
            return 0  # Nothing to push

        # Send to server
        self._push_sequence += 1
        envelope = make_envelope(
            self._terminal_id,
            "PUSH_TRANSACTIONS",
            payload,
            sequence=self._push_sequence,
        )

        result = self._request("POST", EP_PUSH_TRANSACTIONS, envelope)
        if result is None:
            return -1

        status = result.get("status")
        if status in ("ok", "partial", "duplicate"):
            # Mark local records as synced
            total_pushed = sum(len(v) for v in payload.values() if isinstance(v, list))
            self._mark_as_synced(fingerprints)
            self._apply_main_balances(result.get("balances") or {})
            logger.info("Pushed %d records (status=%s)", total_pushed, status)
            return total_pushed
        else:
            logger.warning("Push failed: %s", result)
            return -1

    def _collect_unsynced(self) -> tuple[dict[str, list[dict[str, Any]]], dict[tuple[str, int], str]]:
        """Build the push payload from every unsynced row.

        Returns:
            (payload, fingerprints): ``fingerprints`` maps each pushed row
            that carries the ``synced`` flag, as ``(table, id)``, to a
            snapshot of what was sent (see :func:`_fingerprint`), so that a
            row edited while the push was in flight is not marked synced.
        """
        payload: dict[str, list[dict[str, Any]]] = {}
        fingerprints: dict[tuple[str, int], str] = {}
        db = Database()
        with db.get_session() as session:
            # Find unsynced sales (with items and payments)
            unsynced_sales = session.query(Sale).filter_by(synced=False).all()

            if unsynced_sales:
                # Get parent Document data for each sale
                docs = []
                sales = []
                items = []
                payments = []
                for sale in unsynced_sales:
                    docs.append(self._document_row(sale))
                    sales.append(model_to_dict(sale))
                    for item in sale.items:
                        items.append(model_to_dict(item))
                    for pmt in sale.payments:
                        payments.append(model_to_dict(pmt))
                    fingerprints[("sales", sale.id)] = _fingerprint(sale)

                payload["documents"] = docs
                payload["sales"] = sales
                payload["sale_items"] = items
                payload["sale_payments"] = payments

            # Find unsynced purchases
            unsynced_purchases = session.query(Purchase).filter_by(synced=False).all()
            if unsynced_purchases:
                p_docs = []
                purchases = []
                p_items = []
                for purchase in unsynced_purchases:
                    p_docs.append(self._document_row(purchase))
                    purchases.append(model_to_dict(purchase))
                    for item in purchase.items:
                        p_items.append(model_to_dict(item))
                    fingerprints[("purchases", purchase.id)] = _fingerprint(purchase)
                payload.setdefault("documents", []).extend(p_docs)
                payload["purchases"] = purchases
                payload["purchase_items"] = p_items

            for table_name, model_class in _FLAT_PUSH_TABLES:
                rows = session.query(model_class).filter_by(synced=False).all()
                if rows:
                    payload[table_name] = [model_to_dict(r) for r in rows]
                    for row in rows:
                        fingerprints[(table_name, row.id)] = _fingerprint(row)

        return payload, fingerprints

    def _document_row(self, doc: Document) -> dict[str, Any]:
        """The base ``documents`` columns of a sale/purchase, as pushed."""
        return {
            "id": doc.id,
            "document_number": doc.document_number,
            "date": doc.date.isoformat() if doc.date else None,
            "type": doc.type,
            "status": doc.status,
            "user_id": doc.user_id,
            "void_reason_id": doc.void_reason_id,
            "terminal_id": doc.terminal_id,
            "origin_terminal_id": doc.origin_terminal_id or self._terminal_id,
            "synced": True,
        }

    def _mark_as_synced(self, fingerprints: dict[tuple[str, int], str]) -> None:
        """Mark the pushed rows synced after the Main PC acknowledged them.

        A row whose content no longer matches what was sent changed while
        the push was in flight; it stays unsynced so that change goes out
        with the next push instead of being lost (#677).
        """
        db = Database()
        try:
            with db.get_session() as session:
                for (table_name, record_id), sent in fingerprints.items():
                    model_class = get_model_for_table(table_name)
                    obj = session.get(model_class, record_id) if model_class else None
                    if obj is None:
                        continue
                    if _fingerprint(obj) == sent:
                        obj.synced = True
                    else:
                        logger.info("Sync: %s[%s] changed during push; will re-send", table_name, record_id)

                session.commit()
        except Exception as e:
            logger.error("Error marking records as synced: %s", e)

    def _apply_main_balances(self, balances: dict[str, dict[str, str]]) -> None:
        """Take the shop-wide balances the Main PC sent back with a push (#678).

        Each becomes this till's balance plus the ledger amounts this till
        has not pushed yet (see :func:`_local_balance`).
        """
        if not balances:
            return
        db = Database()
        try:
            with db.get_session() as session:
                for table_name, rows in balances.items():
                    if table_name not in _BALANCE_LEDGERS:
                        continue
                    for owner_id, main_value in rows.items():
                        _set_local_balance(session, table_name, int(owner_id), Decimal(str(main_value)))
                session.commit()
        except Exception as e:
            logger.error("Error applying Main PC balances: %s", e)

    # --- Pull Catalog ---

    def _pull_catalog(self, full_sync: bool = False) -> int:
        """Pull catalog updates from the Main PC.

        Args:
            full_sync: If True, pull all records (initial sync).
                       If False, only pull records modified since last sync.

        Returns:
            Number of records pulled, or -1 on error.
        """
        endpoint = EP_PULL_CATALOG + f"?terminal_id={self._terminal_id}"
        if not full_sync and self._last_catalog_sync:
            endpoint += f"&since={self._last_catalog_sync.isoformat()}"

        result = self._request("GET", endpoint)
        if result is None:
            return -1

        payload = result.get("payload", {})
        total_records = result.get("total_records", 0)
        server_timestamp = self._parse_server_timestamp(result)

        if total_records == 0:
            self._last_catalog_sync = server_timestamp
            return 0

        # Apply catalog updates to local database
        db = Database()
        records_applied = 0
        pulled_balances: list[tuple[str, int, Decimal]] = []
        try:
            with db.get_session() as session:
                for table_name in CATALOG_TABLES:
                    records = payload.get(table_name, [])
                    if not records:
                        continue

                    model_class = get_model_for_table(table_name)
                    if model_class is None:
                        continue

                    for record_data in records:
                        try:
                            instance = dict_to_model(model_class, record_data)
                            merged = session.merge(instance)
                            if table_name in _BALANCE_LEDGERS:
                                # The Main PC's figure doesn't include what this
                                # till hasn't pushed yet -- keep that on top (#678).
                                _, balance_column = _BALANCE_LEDGERS[table_name]
                                pulled_balances.append((table_name, merged.id, getattr(merged, balance_column)))
                            records_applied += 1
                        except Exception as e:
                            logger.error(
                                "Error applying catalog record %s[%s]: %s",
                                table_name,
                                record_data.get("id", "?"),
                                e,
                            )

                for table_name, owner_id, main_value in pulled_balances:
                    _set_local_balance(session, table_name, owner_id, main_value or Decimal("0"))

                session.commit()

        except Exception as e:
            logger.error("Error applying catalog update: %s", e)
            return -1

        self._last_catalog_sync = server_timestamp
        logger.info("Pulled %d catalog records", records_applied)
        return records_applied

    @staticmethod
    def _parse_server_timestamp(result: dict[str, Any]) -> datetime:
        """Return the Main PC's own clock reading from a pull-catalog
        response, used as the next ``since`` watermark.

        Using the server's timestamp (rather than this machine's own
        ``datetime.now()``) means catalog sync never depends on the
        Main PC and Terminal agreeing on the time of day — only on the
        Main PC agreeing with itself between one request and the next,
        which it always does.
        """
        raw = result.get("timestamp")
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                pass
        return datetime.now()

    # --- Pull Stock ---

    def _pull_stock(self) -> int:
        """Pull current stock quantities from the Main PC.

        Returns number of products updated, or -1 on error.
        """
        result = self._request("GET", EP_PULL_STOCK)
        if result is None:
            return -1

        products = result.get("products", [])
        if not products:
            return 0

        db = Database()
        updated = 0
        try:
            with db.get_session() as session:
                for stock_data in products:
                    product_id = stock_data.get("id")
                    stock_qty = stock_data.get("stock_qty")
                    if product_id is None or stock_qty is None:
                        continue

                    product = session.get(Product, product_id)
                    if product:
                        product.stock_qty = Decimal(str(stock_qty))
                        updated += 1

                session.commit()

        except Exception as e:
            logger.error("Error applying stock update: %s", e)
            return -1

        if updated > 0:
            logger.debug("Updated stock for %d products", updated)
        return updated

    # --- Push Audit Logs ---

    def push_audit_logs(self) -> int:
        """Push unsynced audit logs to the Main PC.

        Called less frequently than transaction push (e.g., every 30 seconds).
        Returns number of records pushed, or -1 on error.
        """
        db = Database()
        try:
            with db.get_session() as session:
                unsynced = session.query(AuditLog).filter_by(synced=False).limit(100).all()  # Batch size
                if not unsynced:
                    return 0

                audit_records = [model_to_dict(a) for a in unsynced]

        except Exception as e:
            logger.error("Error collecting audit logs: %s", e)
            return -1

        envelope = make_envelope(
            self._terminal_id,
            "PUSH_AUDIT",
            {"audit_logs": audit_records},
        )

        result = self._request("POST", EP_PUSH_AUDIT, envelope)
        if result is None:
            return -1

        if result.get("status") == "ok":
            # Mark as synced
            try:
                with db.get_session() as session:
                    for record in audit_records:
                        record_id = record.get("id")
                        if record_id:
                            obj = session.get(AuditLog, record_id)
                            if obj:
                                obj.synced = True
                    session.commit()
            except Exception as e:
                logger.error("Error marking audit logs as synced: %s", e)

            return len(audit_records)
        return -1
