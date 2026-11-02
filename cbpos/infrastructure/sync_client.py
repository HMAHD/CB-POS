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
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal
from sqlalchemy import func
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import class_mapper

from cbpos.core.database import Database
from cbpos.core.models import (
    AuditLog,
    CashMovement,
    Customer,
    CustomerLedgerEntry,
    CustomerPayment,
    Document,
    InventoryLog,
    LoyaltyLedgerEntry,
    Product,
    Purchase,
    Sale,
    Shift,
    StockMovement,
    SupplierLedgerEntry,
    SupplierPayment,
)
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.sync_change_tracking import SKIP_CHANGE_TRACKING
from cbpos.core.services.sync_customer_renumber import renumber_customers
from cbpos.core.services.sync_protocol import (
    CATALOG_DELETION_ORDER,
    CATALOG_TABLES,
    EP_PULL_CATALOG,
    EP_PULL_STOCK,
    EP_PUSH_TRANSACTIONS,
    EP_REGISTER,
    REJECTED_TABLE_ERROR,
    SYNC_PROTOCOL_VERSION,
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
    ("audit_logs", AuditLog),
    ("customer_payments", CustomerPayment),
    ("customer_ledger", CustomerLedgerEntry),
    ("loyalty_ledger", LoyaltyLedgerEntry),
    ("supplier_payments", SupplierPayment),
    ("supplier_ledger", SupplierLedgerEntry),
    ("inventory_logs", InventoryLog),
)

# Children pushed with their document: relationship names per document type.
_PUSHED_CHILDREN: dict[type, tuple[str, ...]] = {
    Sale: ("items", "payments"),
    Purchase: ("items",),
}


def _is_cert_verify_error(e: Exception) -> bool:
    """Return True if exception indicates a TLS certificate verification failure."""
    if isinstance(e, ssl.SSLCertVerificationError):
        return True
    if isinstance(e, urllib.error.URLError):
        reason = getattr(e, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            return True
        if reason and (
            "CERTIFICATE_VERIFY_FAILED" in str(reason) or "certificate verify failed" in str(reason).lower()
        ):
            return True
    err_str = str(e)
    return "CERTIFICATE_VERIFY_FAILED" in err_str or "certificate verify failed" in err_str.lower()


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _points(value: Any) -> int:
    return int(Decimal(str(value or 0)))


@dataclass(frozen=True, slots=True)
class _Balance:
    """A Main-owned figure that this till's ledger rows move (#678, #716)."""

    owner_table: str  # catalog table holding the figure
    balance_column: str
    ledger: type
    owner_column: str  # ledger column naming the owner row
    amount_column: str  # ledger column the figure moves by
    parse: Callable[[Any], Any]


# Key in the push acknowledgement's "balances" -> the figure.
_BALANCES: dict[str, _Balance] = {
    "customers": _Balance("customers", "current_debt", CustomerLedgerEntry, "customer_id", "amount", _money),
    "suppliers": _Balance("suppliers", "current_payable", SupplierLedgerEntry, "supplier_id", "amount", _money),
    "loyalty_points": _Balance("customers", "loyalty_points", LoyaltyLedgerEntry, "customer_id", "points", _points),
}


def _unpushed(session: Any, balance: _Balance, owner_id: int) -> Any:
    """Sum of this till's ledger rows for ``owner_id`` that the Main PC doesn't have yet."""
    ledger = balance.ledger
    total = (
        session.query(func.coalesce(func.sum(getattr(ledger, balance.amount_column)), 0))
        .filter(getattr(ledger, balance.owner_column) == owner_id, ledger.synced.is_(False))
        .scalar()
    )
    return balance.parse(total)


def _set_local_balance(session: Any, balance: _Balance, owner_id: int, main_value: Any) -> None:
    """Set a debt / payable / points figure on this till from the Main PC's figure.

    The Main PC's figure covers every till's *pushed* ledger rows; this
    till's own rows that are not pushed yet are added on top, so a credit
    sale or points earned since the last push aren't wiped out by a
    catalog pull.
    """
    owner = session.get(get_model_for_table(balance.owner_table), owner_id)
    if owner is None:
        return
    figure = balance.parse(main_value) + _unpushed(session, balance, owner_id)
    if balance.balance_column == "loyalty_points" and figure < 0:
        figure = 0
    setattr(owner, balance.balance_column, figure)


def _rejected_tables(errors: Any) -> set[str]:
    """Tables the Main PC turned away in a ``partial`` push reply.

    A Main PC older than this till rejects tables it doesn't know (e.g.
    "loyalty_ledger" before #716) and applies the rest. Those rows must stay
    unsynced, to go out once the Main PC is upgraded.
    """
    if not isinstance(errors, list):
        return set()
    return {e[len(REJECTED_TABLE_ERROR) :] for e in errors if isinstance(e, str) and e.startswith(REJECTED_TABLE_ERROR)}


def _unpushed_customer_keys(session: Any) -> dict[str, set[Any]]:
    """Ids, phones and loyalty cards of the customers this till created and hasn't pushed."""
    keys: dict[str, set[Any]] = {"id": set(), "phone": set(), "loyalty_card_code": set()}
    try:
        bind = session.get_bind()
        insp = sa_inspect(bind)
        if "customers" not in insp.get_table_names():
            return keys
    except Exception:
        return keys
    for customer in session.query(Customer).filter_by(synced=False):
        for column, values in keys.items():
            value = getattr(customer, column)
            if value is not None:
                values.add(value)
    return keys


def _clashes(record: dict[str, Any], unpushed: dict[str, set[Any]]) -> bool:
    return any(record.get(column) is not None and record.get(column) in values for column, values in unpushed.items())


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
    catalog_reloaded = pyqtSignal(bool, str)
    roles_changed = pyqtSignal()
    error_signal = pyqtSignal(str)

    # Connection states
    STATE_DISCONNECTED = "disconnected"
    STATE_CONNECTED = "connected"
    STATE_SYNCING = "syncing"
    STATE_ERROR = "error"
    STATE_UNPAIRED = "unpaired"

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
        self._error_code: str | None = None
        self._push_sequence = 0
        self._last_catalog_sync: datetime | None = None
        self._initial_sync_done = False
        self._consecutive_failures = 0
        self._max_retries = 3
        self._full_sync_requested = False

        # Sync is always over TLS — normalize to https:// regardless of
        # what was typed in (bare "host:port", or an old "http://" value
        # left over from before TLS support).
        if self._server_address.startswith("http://"):
            self._server_address = "https://" + self._server_address[len("http://") :]
        elif not self._server_address.startswith("https://"):
            self._server_address = f"https://{self._server_address}"

        self._ssl_context: ssl.SSLContext | None = None
        self._loaded_pinned_pem: str = ""
        self.reload_ssl_context()

    @property
    def error_code(self) -> str | None:
        """Return the specific error code if state is STATE_ERROR."""
        return self._error_code

    def reload_ssl_context(self) -> bool:
        """Reload client SSLContext using the currently pinned certificate PEM."""
        from cbpos.infrastructure.sync_tls import build_client_ssl_context

        pinned_pem = ConfigService.get("sync_pinned_cert_pem")
        if not pinned_pem:
            self._ssl_context = None
            self._loaded_pinned_pem = ""
            self._set_state(self.STATE_UNPAIRED)
            return False

        try:
            self._ssl_context = build_client_ssl_context(pinned_pem)
            self._loaded_pinned_pem = pinned_pem
            if self._state in (self.STATE_UNPAIRED, self.STATE_ERROR):
                self._set_state(self.STATE_DISCONNECTED)
            self._error_code = None
            return True
        except Exception as e:
            logger.warning("Could not build pinned SSL context: %s", e)
            self._ssl_context = None
            self._loaded_pinned_pem = ""
            self._set_state(self.STATE_UNPAIRED)
            return False

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
        if self._ssl_context is None:
            self._set_state(self.STATE_UNPAIRED)
            return None

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

        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8")
                err_data = sync_json_loads(raw)
                err_msg = err_data.get("error", str(e))
            except Exception:
                err_msg = str(e)
            logger.error("Sync HTTP %d on %s %s: %s", e.code, method, endpoint, err_msg)
            self._error_code = err_msg
            self._set_state(self.STATE_ERROR)
            self.error_signal.emit(err_msg)
            return None
        except (urllib.error.URLError, ssl.SSLCertVerificationError) as e:
            if _is_cert_verify_error(e):
                self._handle_cert_mismatch(e)
            else:
                logger.debug("Sync request failed (%s %s): %s", method, endpoint, e)
            return None
        except Exception as e:
            if _is_cert_verify_error(e):
                self._handle_cert_mismatch(e)
            else:
                logger.error("Sync request error (%s %s): %s", method, endpoint, e)
            return None

    def _handle_cert_mismatch(self, error: Exception) -> None:
        """Handle a TLS certificate verification failure (potential MITM or replaced cert)."""
        already_mismatch = self._error_code == "cert_mismatch"
        self._error_code = "cert_mismatch"
        self._set_state(self.STATE_ERROR)

        if already_mismatch:
            return  # Avoid repeated audit logs on every retry

        import json
        from urllib.parse import urlsplit

        from cbpos.core.services.logging_service import LoggingService
        from cbpos.i18n import _t
        from cbpos.infrastructure.sync_tls import cert_fingerprint, fetch_server_certificate

        parsed = urlsplit(self._server_address)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8443

        bad_fp = "unknown"
        try:
            pem = fetch_server_certificate(host, port, timeout=5.0)
            bad_fp = cert_fingerprint(pem)
        except Exception as e:
            logger.warning("Could not fetch presented certificate on mismatch: %s", e)

        expected_fp = ConfigService.get("sync_pinned_cert_fp") or "unknown"
        logger.error(
            "Sync TLS certificate mismatch! Expected %s, server presented %s",
            expected_fp,
            bad_fp,
        )

        try:
            details = json.dumps(
                {
                    "presented_fingerprint": bad_fp,
                    "expected_fingerprint": expected_fp,
                    "server_address": self._server_address,
                    "error": str(error),
                }
            )
            LoggingService.log_action(
                user_id=None,
                action="SYNC_CERT_MISMATCH",
                event_type="SECURITY",
                details=details,
            )
        except Exception as e:
            logger.error("Failed to write SYNC_CERT_MISMATCH audit log: %s", e)

        self.error_signal.emit(_t("sync_pairing.changed"))

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
                # Step 0: Ensure client is paired and SSL context is loaded
                if self._ssl_context is None or self._state == self.STATE_UNPAIRED:
                    if not self.reload_ssl_context():
                        self._set_state(self.STATE_UNPAIRED)
                        self._sleep(self._sync_interval)
                        continue

                # Step 0.5: If certificate mismatch, wait until re-paired
                if self._error_code == "cert_mismatch":
                    current_pin = ConfigService.get("sync_pinned_cert_pem") or ""
                    if current_pin != getattr(self, "_loaded_pinned_pem", ""):
                        if not self.reload_ssl_context():
                            self._sleep(self._sync_interval)
                            continue
                    else:
                        self._sleep(self._sync_interval)
                        continue

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

    def request_full_catalog_sync(self) -> None:
        """Schedule a full catalog replacement on the next sync cycle."""
        self._full_sync_requested = True

    def _sync_cycle(self) -> tuple[int, int]:
        """Push local changes, then pull the catalog and stock.

        Returns:
            (records pushed, catalog records pulled); -1 for a failed step.
        """
        full_sync = getattr(self, "_full_sync_requested", False)
        self._full_sync_requested = False
        pushed = self._push_transactions()
        pulled = self._pull_catalog(full_sync=full_sync)
        self._pull_stock()
        if full_sync:
            if pulled >= 0:
                self.catalog_reloaded.emit(True, "")
            else:
                self.catalog_reloaded.emit(False, self._error_code or "catalog_apply_failed")
        return pushed, pulled

    def _sleep(self, seconds: int) -> None:
        """Sleep that can be interrupted by stop() or full sync request."""
        for _ in range(seconds * 10):  # Check every 100ms
            if not self._running or getattr(self, "_full_sync_requested", False):
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
        from cbpos.core.services.local_identity_service import LocalIdentityService

        db_instance_id = LocalIdentityService.get()
        result = self._request(
            "POST",
            EP_REGISTER,
            {
                "terminal_id": self._terminal_id,
                "db_instance_id": db_instance_id,
                "protocol_version": SYNC_PROTOCOL_VERSION,
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
            rejected = _rejected_tables(result.get("errors"))
            if rejected:
                logger.warning("Main PC did not take %s; kept to re-send after it is upgraded", sorted(rejected))
                fingerprints = {key: sent for key, sent in fingerprints.items() if key[0] not in rejected}
            self._mark_as_synced(fingerprints)
            self._adopt_customer_ids((result.get("id_map") or {}).get("customers") or {})
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
            # Customers created on this till first: sales and credit book
            # rows in this batch may point at them (#680).
            new_customers = session.query(Customer).filter_by(synced=False).all()
            if new_customers:
                payload["customers"] = [self._new_customer_row(session, c) for c in new_customers]
                # Their contacts go with them (#717); the Main PC stores them
                # under its own id for the customer.
                contacts = [model_to_dict(contact) for c in new_customers for contact in c.contacts]
                if contacts:
                    payload["customer_contacts"] = contacts

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
                query = session.query(model_class).filter_by(synced=False)
                if table_name == "audit_logs":
                    query = query.limit(500)
                rows = query.all()
                if rows:
                    payload[table_name] = [model_to_dict(r) for r in rows]
                    for row in rows:
                        fingerprints[(table_name, row.id)] = _fingerprint(row)

        return payload, fingerprints

    @staticmethod
    def _new_customer_row(session: Any, customer: Customer) -> dict[str, Any]:
        """A till-created customer as pushed.

        Its points go out as loyalty ledger rows (#716), so the row carries
        only the points no unpushed ledger row accounts for -- the Main PC
        keeps that figure, and every ledger row then adds its own points once.
        """
        row = model_to_dict(customer)
        loyalty = _BALANCES["loyalty_points"]
        row["loyalty_points"] = (customer.loyalty_points or 0) - _unpushed(session, loyalty, customer.id)
        return row

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
        except Exception as e:
            logger.error("Error marking records as synced: %s", e)

    def _adopt_customer_ids(self, id_map: dict[str, int]) -> None:
        """Renumber the customers this till created to the ids the Main PC gave them (#680)."""
        if not id_map:
            return
        db = Database()
        try:
            with db.get_session() as session:
                renumber_customers(session, {int(local): int(server) for local, server in id_map.items()})
        except Exception as e:
            # They stay unsynced and are re-sent; the Main PC answers with
            # the same ids, so the next push tries again.
            logger.error("Error renumbering pushed customers: %s", e)

    def _apply_main_balances(self, balances: dict[str, dict[str, str]]) -> None:
        """Take the shop-wide figures the Main PC sent back with a push (#678, #716).

        Each becomes this till's figure plus the ledger amounts this till
        has not pushed yet (see :func:`_set_local_balance`).
        """
        if not balances:
            return
        db = Database()
        try:
            with db.get_session() as session:
                for reply_key, rows in balances.items():
                    balance = _BALANCES.get(reply_key)
                    if balance is None or not isinstance(rows, dict):
                        continue
                    for owner_id, main_value in rows.items():
                        _set_local_balance(session, balance, int(owner_id), main_value)
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
        if full_sync:
            endpoint += "&full_replace=1"
        elif self._last_catalog_sync:
            endpoint += f"&since={self._last_catalog_sync.isoformat()}"

        result = self._request("GET", endpoint)
        if result is None:
            return -1

        payload = result.get("payload", {})
        total_records = result.get("total_records", 0)
        deletions = result.get("deletions", [])
        requires_full_replace = result.get("requires_full_replace", False) or full_sync
        server_timestamp = self._parse_server_timestamp(result)

        if total_records == 0 and not deletions and not requires_full_replace:
            self._last_catalog_sync = server_timestamp
            return 0

        # Apply catalog updates to local database
        db = Database()
        records_applied = 0
        pulled_balances: list[tuple[_Balance, int, Any]] = []
        held_back = 0
        has_errors = False
        roles_modified = False
        try:
            with db.get_session() as session:
                session.info[SKIP_CHANGE_TRACKING] = True
                bind = session.get_bind()
                insp = sa_inspect(bind)
                existing_tables = set(insp.get_table_names())

                # 1. Process deletions or full replace before upserts to avoid unique constraint collisions
                if requires_full_replace:
                    for table_name in CATALOG_DELETION_ORDER:
                        if table_name == "customers":
                            continue
                        model_class = get_model_for_table(table_name)
                        if model_class is None:
                            continue
                        if getattr(model_class, "__tablename__", None) not in existing_tables:
                            continue
                        incoming_records = payload.get(table_name, [])
                        incoming_ids = {r["id"] for r in incoming_records if "id" in r}
                        local_rows = session.query(model_class).all()
                        for row in local_rows:
                            if row.id not in incoming_ids:
                                try:
                                    with session.begin_nested():
                                        session.delete(row)
                                        session.flush()
                                except Exception as e:
                                    logger.warning(
                                        "Full replace: could not hard-delete %s[%s]: %s",
                                        table_name,
                                        row.id,
                                        e,
                                    )
                                    if hasattr(row, "is_active"):
                                        try:
                                            row.is_active = False
                                            session.flush()
                                        except Exception as e2:
                                            has_errors = True
                                            logger.error("Failed to soft-delete %s[%s]: %s", table_name, row.id, e2)
                elif deletions:
                    order_map = {tbl: i for i, tbl in enumerate(CATALOG_DELETION_ORDER)}
                    sorted_deletions = sorted(deletions, key=lambda d: order_map.get(d.get("table", ""), 999))
                    for item in sorted_deletions:
                        table_name = item.get("table")
                        row_id = item.get("row_id")
                        if table_name == "customers" or not table_name or not row_id:
                            continue
                        model_class = get_model_for_table(table_name)
                        if model_class is None:
                            continue
                        if getattr(model_class, "__tablename__", None) not in existing_tables:
                            continue
                        row = session.get(model_class, row_id)
                        if row is None:
                            continue
                        try:
                            with session.begin_nested():
                                session.delete(row)
                                session.flush()
                        except Exception as e:
                            logger.warning(
                                "Could not hard-delete %s[%s] (referenced by local sales): %s",
                                table_name,
                                row_id,
                                e,
                            )
                            if hasattr(row, "is_active"):
                                try:
                                    row.is_active = False
                                    session.flush()
                                except Exception as e2:
                                    has_errors = True
                                    logger.error("Failed to soft-delete %s[%s]: %s", table_name, row_id, e2)

                # 2. Process upserts
                unpushed_customers = (
                    _unpushed_customer_keys(session)
                    if "customers" in existing_tables
                    else {"id": set(), "phone": set(), "loyalty_card_code": set()}
                )
                for table_name in CATALOG_TABLES:
                    records = payload.get(table_name, [])
                    if not records:
                        continue

                    model_class = get_model_for_table(table_name)
                    if model_class is None:
                        continue
                    if getattr(model_class, "__tablename__", None) not in existing_tables:
                        continue

                    mapper = class_mapper(model_class)
                    version_key = mapper.version_id_col.key if mapper.version_id_col is not None else None

                    for record_data in records:
                        if table_name == "customers" and _clashes(record_data, unpushed_customers):
                            # Would overwrite (or duplicate the phone of) a
                            # customer this till created and hasn't pushed:
                            # wait until the push renumbers it (#680).
                            held_back += 1
                            continue
                        perm_codes = None
                        if table_name == "roles":
                            perm_codes = record_data.get("permission_codes")
                        if version_key:
                            record_data.pop(version_key, None)
                        try:
                            instance = dict_to_model(model_class, record_data)
                            merged = session.merge(instance)
                            if table_name == "roles" and perm_codes is not None:
                                session.flush()
                                from cbpos.core.models import Permission

                                target_perms = session.query(Permission).filter(Permission.code.in_(perm_codes)).all()
                                merged.permissions = target_perms
                                roles_modified = True
                            # The Main PC's figures don't include what this till
                            # hasn't pushed yet -- keep that on top (#678, #716).
                            for balance in _BALANCES.values():
                                if balance.owner_table == table_name and balance.owner_table in existing_tables:
                                    main_value = getattr(merged, balance.balance_column)
                                    pulled_balances.append((balance, merged.id, main_value))
                            records_applied += 1
                        except Exception as e:
                            has_errors = True
                            logger.error(
                                "Error applying catalog record %s[%s]: %s",
                                table_name,
                                record_data.get("id", "?"),
                                e,
                            )

                for balance, owner_id, main_value in pulled_balances:
                    if (
                        balance.owner_table in existing_tables
                        and getattr(balance.ledger, "__tablename__", None) in existing_tables
                    ):
                        _set_local_balance(session, balance, owner_id, main_value)

        except Exception as e:
            logger.error("Error applying catalog update: %s", e)
            self._error_code = "catalog_apply_failed"
            self._set_state(self.STATE_ERROR)
            return -1

        if held_back or has_errors:
            if has_errors:
                logger.warning("One or more catalog records failed to apply; watermark not advanced")
                self._error_code = "catalog_apply_failed"
                self._set_state(self.STATE_ERROR)
            if held_back:
                logger.info("Held back %d pulled customer(s) until this till's new customers are pushed", held_back)
        else:
            self._last_catalog_sync = server_timestamp
            if roles_modified:
                self.roles_changed.emit()
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

        except Exception as e:
            logger.error("Error applying stock update: %s", e)
            return -1

        if updated > 0:
            logger.debug("Updated stock for %d products", updated)
        return updated
