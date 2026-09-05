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

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal, QTimer

from cbpos.core.database import Database
from cbpos.core.services.config_service import ConfigService
from cbpos.core.models import (
    Document,
    Sale,
    SaleItem,
    SalePayment,
    Purchase,
    PurchaseItem,
    StockMovement,
    AuditLog,
    Shift,
    CashMovement,
    CustomerPayment,
    CustomerLedgerEntry,
    SupplierPayment,
    SupplierLedgerEntry,
    SyncQueue,
    SyncLog,
    Product,
)
from cbpos.core.services.sync_protocol import (
    EP_HEARTBEAT,
    EP_REGISTER,
    EP_PUSH_TRANSACTIONS,
    EP_PULL_CATALOG,
    EP_PULL_STOCK,
    EP_PUSH_AUDIT,
    CATALOG_TABLES,
    model_to_dict,
    dict_to_model,
    make_envelope,
    sync_json_dumps,
    sync_json_loads,
    get_model_for_table,
)

logger = logging.getLogger(__name__)


class SyncClient(QThread):
    """Background sync client that connects to the Main PC.

    Signals:
        status_changed: Emitted when connection status changes
            (status: 'connected', 'syncing', 'disconnected', 'error')
        sync_completed: Emitted after a sync cycle completes
            (pushed_count, pulled_count)
        initial_sync_completed: Emitted after the first full catalog sync.
        error_signal: Emitted on errors (error message).
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
        super().__init__(parent)
        self._terminal_id = terminal_id
        self._server_address = server_address.rstrip("/")
        self._sync_interval = sync_interval  # seconds
        self._shared_secret = shared_secret
        self._running = False
        self._state = self.STATE_DISCONNECTED
        self._push_sequence = 0
        self._last_catalog_sync: Optional[datetime] = None
        self._initial_sync_done = False
        self._consecutive_failures = 0
        self._max_retries = 3

        # Ensure server_address has http:// prefix
        if not self._server_address.startswith("http"):
            self._server_address = f"http://{self._server_address}"

    @property
    def state(self) -> str:
        return self._state

    @property
    def terminal_id(self) -> str:
        return self._terminal_id

    @property
    def is_connected(self) -> bool:
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
        data: Optional[Dict] = None,
        timeout: int = 10,
    ) -> Optional[Dict[str, Any]]:
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

            with urllib.request.urlopen(req, timeout=timeout) as resp:
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
                pushed = self._push_transactions()
                pulled = self._pull_catalog()
                self._pull_stock()

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

    def _check_main_identity(self, main_instance_id: Optional[str]) -> bool:
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

        Returns the number of records pushed, or -1 on error.
        """
        db = Database()
        payload: Dict[str, List[Dict[str, Any]]] = {}

        try:
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
                        # Document base fields
                        doc_dict = model_to_dict(sale)
                        # Remove polymorphic child columns from document
                        docs.append(
                            {
                                "id": doc_dict["id"],
                                "document_number": sale.document_number,
                                "date": sale.date.isoformat() if sale.date else None,
                                "type": sale.type,
                                "status": sale.status,
                                "user_id": sale.user_id,
                                "void_reason_id": sale.void_reason_id,
                                "terminal_id": sale.terminal_id,
                                "origin_terminal_id": sale.origin_terminal_id or self._terminal_id,
                                "synced": True,
                            }
                        )
                        sales.append(model_to_dict(sale))
                        for item in sale.items:
                            items.append(model_to_dict(item))
                        for pmt in sale.payments:
                            payments.append(model_to_dict(pmt))

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
                        p_docs.append(
                            {
                                "id": purchase.id,
                                "document_number": purchase.document_number,
                                "date": purchase.date.isoformat() if purchase.date else None,
                                "type": purchase.type,
                                "status": purchase.status,
                                "user_id": purchase.user_id,
                                "terminal_id": purchase.terminal_id,
                                "origin_terminal_id": purchase.origin_terminal_id or self._terminal_id,
                                "synced": True,
                            }
                        )
                        purchases.append(model_to_dict(purchase))
                        for item in purchase.items:
                            p_items.append(model_to_dict(item))
                    if "documents" in payload:
                        payload["documents"].extend(p_docs)
                    else:
                        payload["documents"] = p_docs
                    payload["purchases"] = purchases
                    payload["purchase_items"] = p_items

                # Find unsynced stock movements
                unsynced_movements = session.query(StockMovement).filter_by(synced=False).all()
                if unsynced_movements:
                    payload["stock_movements"] = [model_to_dict(m) for m in unsynced_movements]

                # Find unsynced shifts
                unsynced_shifts = session.query(Shift).filter_by(synced=False).all()
                if unsynced_shifts:
                    payload["shifts"] = [model_to_dict(s) for s in unsynced_shifts]

                # Find unsynced cash movements
                unsynced_cash = session.query(CashMovement).filter_by(synced=False).all()
                if unsynced_cash:
                    payload["cash_movements"] = [model_to_dict(c) for c in unsynced_cash]

                # Find unsynced customer payments
                unsynced_cpay = session.query(CustomerPayment).filter_by(synced=False).all()
                if unsynced_cpay:
                    payload["customer_payments"] = [model_to_dict(p) for p in unsynced_cpay]

                # Find unsynced customer ledger entries
                unsynced_cledger = session.query(CustomerLedgerEntry).filter_by(synced=False).all()
                if unsynced_cledger:
                    payload["customer_ledger"] = [model_to_dict(e) for e in unsynced_cledger]

                # Find unsynced supplier payments
                unsynced_spay = session.query(SupplierPayment).filter_by(synced=False).all()
                if unsynced_spay:
                    payload["supplier_payments"] = [model_to_dict(p) for p in unsynced_spay]

                # Find unsynced supplier ledger entries
                unsynced_sledger = session.query(SupplierLedgerEntry).filter_by(synced=False).all()
                if unsynced_sledger:
                    payload["supplier_ledger"] = [model_to_dict(e) for e in unsynced_sledger]

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
            self._mark_as_synced(payload)
            logger.info("Pushed %d records (status=%s)", total_pushed, status)
            return total_pushed
        else:
            logger.warning("Push failed: %s", result)
            return -1

    def _mark_as_synced(self, payload: Dict[str, List[Dict[str, Any]]]) -> None:
        """Mark local records as synced after successful push."""
        db = Database()
        try:
            with db.get_session() as session:
                # Mark documents (sales, purchases)
                for table_name in ("documents", "sales", "purchases"):
                    for record in payload.get(table_name, []):
                        record_id = record.get("id")
                        if record_id is not None:
                            model_class = get_model_for_table(table_name)
                            if model_class:
                                obj = session.get(model_class, record_id)
                                if obj:
                                    obj.synced = True

                # Mark other transaction records
                synced_tables = [
                    "stock_movements",
                    "shifts",
                    "cash_movements",
                    "customer_payments",
                    "customer_ledger",
                    "supplier_payments",
                    "supplier_ledger",
                ]
                for table_name in synced_tables:
                    for record in payload.get(table_name, []):
                        record_id = record.get("id")
                        if record_id is not None:
                            model_class = get_model_for_table(table_name)
                            if model_class:
                                obj = session.get(model_class, record_id)
                                if obj:
                                    obj.synced = True

                session.commit()
        except Exception as e:
            logger.error("Error marking records as synced: %s", e)

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

        if total_records == 0:
            self._last_catalog_sync = datetime.now()
            return 0

        # Apply catalog updates to local database
        db = Database()
        records_applied = 0
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
                            session.merge(instance)
                            records_applied += 1
                        except Exception as e:
                            logger.error(
                                "Error applying catalog record %s[%s]: %s",
                                table_name,
                                record_data.get("id", "?"),
                                e,
                            )

                session.commit()

        except Exception as e:
            logger.error("Error applying catalog update: %s", e)
            return -1

        self._last_catalog_sync = datetime.now()
        logger.info("Pulled %d catalog records", records_applied)
        return records_applied

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
