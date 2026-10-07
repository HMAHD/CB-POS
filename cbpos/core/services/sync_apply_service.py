"""
Apply rows pushed by a till to the Main PC database (LAN Sync, #671).

Every till numbers its own rows from 1, so a pushed row's ``id`` means
nothing on its own: till A's sale 5 and till B's sale 5 are different
sales, and the Main PC has a sale 5 of its own too. This module never
writes a pushed row under the till's id. The Main PC inserts it under an
id it assigns itself and records ``(till, id space, local id) -> server
id`` in ``sync_id_map``. A re-sent row (lost response, retry, Main PC
restart) is found again through that map and updated in place, so
re-sends stay idempotent.

Ownership of the tables a push touches:

- Till-originated (pushed, re-keyed through the map): every table in
  ``TRANSACTION_TABLES`` -- documents/sales/purchases (one shared id
  space, ``"documents"``), sale_items, sale_payments, purchase_items,
  stock_movements, shifts, cash_movements, customer_payments,
  customer_ledger, supplier_payments, supplier_ledger, audit_logs,
  suspended_transactions, inventory_logs.
- Main-owned (pulled by tills from the Main PC, so their ids already
  agree): everything in ``CATALOG_TABLES`` -- users, roles, products,
  customers, suppliers, void_reasons, payment methods, ... Columns that
  point at these (user_id, product_id, customer_id, supplier_id,
  void_reason_id) are written as-is.
"""

import logging
from typing import Any

from sqlalchemy import inspect as sa_inspect

from cbpos.core.models import Document, Product, SyncIdMap
from cbpos.core.services.sync_protocol import TRANSACTION_TABLES, coerce_columns, get_model_for_table

logger = logging.getLogger(__name__)

# Sales and purchases are joined-table subclasses of Document: a sale's
# id *is* its documents.id, so the three share one id space in the map.
DOCUMENT_ID_SPACE = "documents"
_DOCUMENT_TABLES = frozenset({"documents", "sales", "purchases"})

# Order rows are applied in -- parents before anything that points at
# them. This is deliberately not the payload's order: the till lists
# "documents" before "sales", but a documents row only carries the base
# columns of a sale/purchase, so the full subclass row has to create the
# server row first and the documents row then just updates it.
APPLY_ORDER: tuple[str, ...] = (
    "shifts",
    "sales",
    "purchases",
    "documents",
    "sale_items",
    "sale_payments",
    "purchase_items",
    "stock_movements",
    "cash_movements",
    "customer_payments",
    "customer_ledger",
    "supplier_payments",
    "supplier_ledger",
    "audit_logs",
    "suspended_transactions",
    "inventory_logs",
)
assert set(APPLY_ORDER) == set(TRANSACTION_TABLES), "APPLY_ORDER must cover exactly TRANSACTION_TABLES"


class PushApplyError(Exception):
    """A pushed row can't be applied safely; the whole batch must be rejected."""


def id_space(table_name: str) -> str:
    """Return the sync_id_map ``table_name`` (id space) for a pushed table."""
    return DOCUMENT_ID_SPACE if table_name in _DOCUMENT_TABLES else table_name


class SyncApplyService:
    """Applies one till's pushed batch inside the caller's session.

    The caller owns the transaction: on any exception it must roll back
    the whole batch (the till marks every row it sent as synced as soon as
    the push is acknowledged, so a half-applied batch would lose rows).
    """

    def __init__(self, session: Any, terminal_id: str) -> None:
        """Bind to an open session and the pushing till's terminal id.

        Args:
            session: Open SQLAlchemy session (transaction owned by caller).
            terminal_id: The till that sent the batch (envelope terminal_id).
        """
        if not terminal_id:
            raise PushApplyError("terminal_id required")
        self._session = session
        self._terminal_id = terminal_id
        self._id_cache: dict[tuple[str, int], int] = {}

    # --- Public API ---

    def apply_batch(self, payload: dict[str, Any]) -> tuple[int, list[str]]:
        """Apply every allowed table in ``payload``.

        Args:
            payload: ``{table_name: [row dict, ...]}`` as sent by the till.

        Returns:
            (rows applied, errors for tables that were skipped because they
            may not be pushed). Any row-level problem raises instead.

        Raises:
            PushApplyError: A row can't be applied without risking wrong data.
        """
        errors: list[str] = []
        for table_name, records in payload.items():
            if table_name not in TRANSACTION_TABLES:
                errors.append(f"Table not allowed for push: {table_name}")
                logger.warning("Terminal %s attempted to push disallowed table %r", self._terminal_id, table_name)
            elif not isinstance(records, list):
                raise PushApplyError(f"{table_name}: expected a list of rows")

        applied = 0
        for table_name in APPLY_ORDER:
            records = payload.get(table_name)
            if not records:
                continue
            # Ascending local id: a till's ids only grow, so a row that
            # points at another row of the same table (a refund at its
            # original sale) comes after the row it points at.
            for record in sorted(records, key=lambda r: (r.get("id") is None, r.get("id") or 0)):
                self.apply_record(table_name, dict(record))
                applied += 1
        return applied, errors

    def apply_record(self, table_name: str, record: dict[str, Any]) -> None:
        """Insert or update one pushed row under a server-assigned id.

        Args:
            table_name: Pushed table name (one of TRANSACTION_TABLES).
            record: The till's row, including its local ``id``.

        Raises:
            PushApplyError: The row is malformed or can't be placed safely.
        """
        model_class = get_model_for_table(table_name)
        if model_class is None or table_name not in TRANSACTION_TABLES:
            raise PushApplyError(f"{table_name}: not a pushable table")

        local_id = record.pop("id", None)
        if local_id is None:
            raise PushApplyError(f"{table_name}: row without id")
        local_id = int(local_id)
        if any(isinstance(v, list) for v in record.values()):
            raise PushApplyError(f"{table_name}[{local_id}]: nested rows are not supported")

        values = coerce_columns(model_class, record)
        values.pop("id", None)
        if hasattr(model_class, "synced"):
            values["synced"] = True
        if table_name in _DOCUMENT_TABLES and not values.get("origin_terminal_id"):
            values["origin_terminal_id"] = self._terminal_id

        space = id_space(table_name)
        server_id = self._lookup(space, local_id)
        if server_id is not None:
            row = self._session.get(model_class, server_id)
            if row is None:
                # Mapped row was since deleted on the Main PC; don't resurrect
                # it (and never re-apply a stock movement).
                logger.warning(
                    "Sync: %s[%s] from %s maps to missing server row %s; skipped",
                    table_name,
                    local_id,
                    self._terminal_id,
                    server_id,
                )
                return
            self._update(row, table_name, values)
            return

        row = self._adopt_legacy_row(table_name, model_class, space, local_id, values)
        if row is not None:
            self._remember(space, local_id, row.id)
            self._update(row, table_name, values)
            return

        if table_name == "documents":
            # Only base columns -- the full row comes as sales/purchases.
            raise PushApplyError(f"documents[{local_id}]: no matching sales/purchases row in this push")

        instance = model_class(**values)
        self._session.add(instance)
        self._session.flush()  # assigns the server id
        self._remember(space, local_id, instance.id)
        self._on_insert(table_name, instance)

    # --- Id map ---

    def _lookup(self, space: str, local_id: int) -> int | None:
        key = (space, local_id)
        if key in self._id_cache:
            return self._id_cache[key]
        server_id = (
            self._session.query(SyncIdMap.server_id)
            .filter_by(origin_terminal_id=self._terminal_id, table_name=space, local_id=local_id)
            .scalar()
        )
        if server_id is not None:
            self._id_cache[key] = server_id
        return server_id

    def _remember(self, space: str, local_id: int, server_id: int) -> None:
        self._session.add(
            SyncIdMap(origin_terminal_id=self._terminal_id, table_name=space, local_id=local_id, server_id=server_id)
        )
        self._session.flush()
        self._id_cache[(space, local_id)] = server_id

    def _is_claimed(self, space: str, server_id: int) -> bool:
        """True if ``server_id`` is already some till's mapped row (so not a pre-#671 row)."""
        return self._session.query(SyncIdMap.id).filter_by(table_name=space, server_id=server_id).first() is not None

    # --- Pre-#671 rows ---

    def _adopt_legacy_row(
        self, table_name: str, model_class: type, space: str, local_id: int, values: dict[str, Any]
    ) -> Any | None:
        """Find this row if it already reached the Main PC before the id map existed.

        Back then a pushed row was stored under the till's own id, with no
        map entry. A lost-response retry of such a push must not insert it
        a second time (a duplicate document number would even block the
        till's sync for good), nor re-apply a stock movement.

        Documents are recognised by their unique document number, and only
        if that number belongs to this same till. Any other row only if the
        Main PC row at the till's id is identical column for column -- a
        different till's row (or the Main PC's own) at that id differs.
        """
        if space == DOCUMENT_ID_SPACE:
            number = values.get("document_number")
            if not number:
                return None
            existing = self._session.query(Document).filter_by(document_number=number).one_or_none()
            if existing is None:
                return None
            owner = existing.origin_terminal_id or existing.terminal_id
            if owner != self._terminal_id or self._is_claimed(space, existing.id):
                raise PushApplyError(
                    f"{table_name}[{local_id}]: document number {number} already belongs to another document"
                )
            if values.get("type") and existing.type != values["type"]:
                raise PushApplyError(f"{table_name}[{local_id}]: document {number} is a {existing.type}")
            return existing

        row = self._session.get(model_class, local_id)
        if row is None or self._is_claimed(space, local_id):
            return None
        for key, value in values.items():
            if key == "synced":
                continue
            if getattr(row, key) != value:
                return None
        return row

    # --- Writes ---

    def _update(self, row: Any, table_name: str, values: dict[str, Any]) -> None:
        """Re-send of a row the Main PC already has: refresh it in place."""
        if table_name == "stock_movements":
            # Stock was moved when this movement was first stored; a movement
            # never changes on the till afterwards, so leave it untouched.
            if values.get("qty_change") is not None and values["qty_change"] != row.qty_change:
                logger.warning(
                    "Sync: re-sent stock movement %s from %s has a different qty (%s vs %s); kept the original",
                    row.id,
                    self._terminal_id,
                    values["qty_change"],
                    row.qty_change,
                )
            row.synced = True
            return

        columns = {c.key for c in sa_inspect(type(row)).columns}
        for key, value in values.items():
            if key == "id" or key not in columns:
                continue
            if key == "type" and getattr(row, "type", value) != value:
                raise PushApplyError(f"{table_name}: row {row.id} type {row.type} cannot become {value}")
            setattr(row, key, value)

    def _on_insert(self, table_name: str, instance: Any) -> None:
        """Side effects that belong to a row's first arrival only."""
        if table_name == "stock_movements":
            # The Main PC's Product.stock_qty is what every till later pulls,
            # so it must move with each till's movement -- once. This only
            # runs when the movement's map entry is created, so a re-send
            # (found through the map) can never apply it twice.
            product = self._session.get(Product, instance.product_id)
            if product is not None:
                # Product.version_id is an optimistic-lock column: a concurrent
                # update raises StaleDataError at flush/commit, which the sync
                # server retries with a fresh session.
                product.stock_qty += instance.qty_change
